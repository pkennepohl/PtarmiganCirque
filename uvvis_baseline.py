"""UV/Vis baseline correction algorithms (Phase 4c CS-15, Phase 4m CS-24).

Pure computational module — no Tk, no graph, no I/O. Each ``compute_*``
takes ``(wavelength_nm, absorbance, params)`` and returns the
baseline-subtracted absorbance as a numpy array of the same shape as
the input.

Five modes:

* **linear** — two-point baseline. Sample the absorbance at
  ``anchor_lo_nm`` and ``anchor_hi_nm`` (linearly interpolated from
  the nearest data points) and subtract the straight line through
  them.
* **polynomial** — fit a polynomial of given ``order`` to the data
  inside the wavelength window ``[fit_lo_nm, fit_hi_nm]`` and subtract
  its evaluation across the full wavelength range. The window is
  meant to be a peak-free region; what's outside the window is
  extrapolation.
* **spline** — build a cubic interpolating spline through anchor
  wavelengths (``anchors``) at the absorbance values sampled from the
  data; subtract. Anchors are meant to sit in peak-free regions.
* **rubberband** — parameter-free convex-hull lower envelope. Builds
  the lower convex hull of the (wavelength, absorbance) point set and
  subtracts it as the baseline.
* **scattering** (CS-24) — power-law baseline ``B(λ) = c · λ^(-n)``
  for colloidal / turbid samples, where ``n`` is either supplied
  numerically (``4`` ≈ Rayleigh, ``2`` ≈ large-particle Mie) or
  fit alongside the amplitude (``n="fit"``). Fit window is the
  peak-free wavelength range; baseline is subtracted across the
  full input range.

Params completeness (CS-03): each mode lists exactly the keys it reads
from ``params``. Missing keys raise ``KeyError`` (the calling tab is
responsible for capturing every parameter the mode needs).
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
from scipy.interpolate import CubicSpline


__all__ = [
    "compute_linear",
    "compute_polynomial",
    "compute_spline",
    "compute_rubberband",
    "compute_scattering",
    "compute",
    "BASELINE_MODES",
]


BASELINE_MODES = ("linear", "polynomial", "spline", "rubberband", "scattering")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _coerce(wavelength_nm, absorbance):
    """Validate inputs and return float64 numpy arrays of equal shape."""
    wl = np.asarray(wavelength_nm, dtype=float)
    a = np.asarray(absorbance, dtype=float)
    if wl.ndim != 1 or a.ndim != 1:
        raise ValueError("wavelength_nm and absorbance must be 1-D arrays")
    if wl.shape != a.shape:
        raise ValueError(
            f"wavelength_nm shape {wl.shape} != absorbance shape {a.shape}"
        )
    return wl, a


# ---------------------------------------------------------------------------
# Linear (two anchors)
# ---------------------------------------------------------------------------


def compute_linear(
    wavelength_nm, absorbance, params: Mapping,
) -> np.ndarray:
    """Two-point baseline subtraction.

    Required ``params`` keys: ``anchor_lo_nm``, ``anchor_hi_nm`` (in nm,
    ordering enforced internally).
    """
    wl, a = _coerce(wavelength_nm, absorbance)
    lo = float(params["anchor_lo_nm"])
    hi = float(params["anchor_hi_nm"])
    if lo == hi:
        # Degenerate window — subtract a constant baseline equal to the
        # interpolated absorbance at that wavelength. This is what the
        # user ends up with if they accidentally pick the same anchor;
        # it matches the limit of the two-anchor formula.
        order = np.argsort(wl)
        a_pt = float(np.interp(lo, wl[order], a[order]))
        return a - a_pt
    if lo > hi:
        lo, hi = hi, lo

    order = np.argsort(wl)
    wl_s = wl[order]
    a_s = a[order]
    a_lo = float(np.interp(lo, wl_s, a_s))
    a_hi = float(np.interp(hi, wl_s, a_s))

    baseline = a_lo + (a_hi - a_lo) * (wl - lo) / (hi - lo)
    return a - baseline


# ---------------------------------------------------------------------------
# Polynomial (order n on a wavelength window)
# ---------------------------------------------------------------------------


def compute_polynomial(
    wavelength_nm, absorbance, params: Mapping,
) -> np.ndarray:
    """Polynomial baseline subtraction.

    Required ``params`` keys: ``order`` (int), ``fit_lo_nm``,
    ``fit_hi_nm``. The polynomial is fit to the data inside the
    wavelength window and evaluated across the full input range.
    """
    wl, a = _coerce(wavelength_nm, absorbance)
    order_n = int(params["order"])
    if order_n < 0:
        raise ValueError(f"polynomial order must be >= 0, got {order_n}")
    lo = float(params["fit_lo_nm"])
    hi = float(params["fit_hi_nm"])
    if lo > hi:
        lo, hi = hi, lo

    mask = (wl >= lo) & (wl <= hi)
    n_in = int(mask.sum())
    if n_in <= order_n:
        raise ValueError(
            f"polynomial order {order_n} requires > {order_n} points in "
            f"the fit window [{lo}, {hi}]; found {n_in}"
        )

    coeffs = np.polyfit(wl[mask], a[mask], order_n)
    baseline = np.polyval(coeffs, wl)
    return a - baseline


# ---------------------------------------------------------------------------
# Spline (cubic through user-supplied anchors)
# ---------------------------------------------------------------------------


def compute_spline(
    wavelength_nm, absorbance, params: Mapping,
) -> np.ndarray:
    """Spline baseline subtraction through user-supplied anchors.

    Required ``params`` keys: ``anchors`` — a sequence of wavelengths
    in nm. The absorbance values at each anchor are sampled from the
    data via linear interpolation; the baseline is then a cubic spline
    through those (anchor, sampled_absorbance) points (or a polynomial
    of degree 1 or 2 when fewer than four anchors are supplied).
    """
    wl, a = _coerce(wavelength_nm, absorbance)
    anchors_in: Sequence = params["anchors"]
    anchors_sorted = sorted({float(x) for x in anchors_in})
    if len(anchors_sorted) < 2:
        raise ValueError("spline baseline requires at least 2 anchors")

    order = np.argsort(wl)
    wl_s = wl[order]
    a_s = a[order]
    anchor_a = np.interp(anchors_sorted, wl_s, a_s)

    if len(anchors_sorted) >= 4:
        cs = CubicSpline(anchors_sorted, anchor_a, extrapolate=True)
        baseline = cs(wl)
    elif len(anchors_sorted) == 3:
        # Quadratic through the three points — CubicSpline needs ≥4.
        coeffs = np.polyfit(anchors_sorted, anchor_a, 2)
        baseline = np.polyval(coeffs, wl)
    else:
        coeffs = np.polyfit(anchors_sorted, anchor_a, 1)
        baseline = np.polyval(coeffs, wl)

    return a - baseline


# ---------------------------------------------------------------------------
# Rubberband (lower convex hull, parameter-free)
# ---------------------------------------------------------------------------


def compute_rubberband(
    wavelength_nm, absorbance, params: Mapping | None = None,
) -> np.ndarray:
    """Convex-hull (rubberband) lower envelope baseline.

    Parameter-free — ``params`` is accepted (and may be ``None`` or an
    empty mapping) for API symmetry with the other modes.
    """
    del params  # unused
    wl, a = _coerce(wavelength_nm, absorbance)
    if wl.size < 2:
        return a - a  # degenerate; baseline-subtracted is zero everywhere

    order = np.argsort(wl)
    wl_s = wl[order]
    a_s = a[order]

    # Andrew's monotone chain — lower hull only. Keep points that turn
    # left (counter-clockwise) as we traverse left to right.
    hull: list[tuple[float, float]] = []
    for x, y in zip(wl_s.tolist(), a_s.tolist()):
        while len(hull) >= 2:
            (x1, y1), (x2, y2) = hull[-2], hull[-1]
            cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
            if cross <= 0:
                hull.pop()
            else:
                break
        hull.append((x, y))

    hx = np.array([p[0] for p in hull])
    hy = np.array([p[1] for p in hull])
    # Linearly interpolate the hull onto the original (sorted) grid.
    base_sorted = np.interp(wl_s, hx, hy)
    # Restore original input ordering.
    inv = np.argsort(order)
    baseline = base_sorted[inv]
    return a - baseline


# ---------------------------------------------------------------------------
# Scattering (power-law c · λ^(-n) for colloidal / turbid samples — CS-24)
# ---------------------------------------------------------------------------


def compute_scattering(
    wavelength_nm, absorbance, params: Mapping,
) -> np.ndarray:
    """Power-law scattering baseline subtraction.

    Required ``params`` keys:

    * ``n`` — either a numeric exponent (``float`` ≥ 0; e.g. ``4`` for
      Rayleigh, ``2`` for large-particle Mie) or the string ``"fit"``
      to recover ``n`` alongside the amplitude.
    * ``fit_lo_nm``, ``fit_hi_nm`` — wavelength window for the fit
      (intended to exclude absorption peaks). The baseline is fit on
      the window and subtracted across the full input range.

    With ``n`` numeric, a closed-form linear least-squares fit
    determines the amplitude ``c`` only. With ``n="fit"``, the fit
    is performed in log–log space (``log A = log c − n · log λ``);
    this requires absorbance > 0 throughout the fit window.
    """
    wl, a = _coerce(wavelength_nm, absorbance)
    n_in = params["n"]  # KeyError if missing
    lo = float(params["fit_lo_nm"])
    hi = float(params["fit_hi_nm"])
    if lo > hi:
        lo, hi = hi, lo

    mask = (wl >= lo) & (wl <= hi)
    if int(mask.sum()) < 2:
        raise ValueError(
            f"scattering baseline needs ≥ 2 points in fit window "
            f"[{lo}, {hi}]; found {int(mask.sum())}"
        )
    wl_w = wl[mask]
    a_w = a[mask]
    if np.any(wl_w <= 0):
        raise ValueError(
            "scattering baseline requires positive wavelengths "
            "(λ^(-n) is undefined at λ ≤ 0)"
        )

    fit_n = isinstance(n_in, str) and n_in.lower() == "fit"
    if fit_n:
        if np.any(a_w <= 0):
            raise ValueError(
                "scattering baseline n='fit' requires absorbance > 0 "
                f"throughout the fit window [{lo}, {hi}] "
                "(log–log fit cannot accept zero or negative values)"
            )
        # log A = log c − n · log λ  →  linear fit in log space.
        slope, intercept = np.polyfit(np.log(wl_w), np.log(a_w), 1)
        n_val = float(-slope)
        c_val = float(np.exp(intercept))
    else:
        try:
            n_val = float(n_in)
        except (TypeError, ValueError):
            raise ValueError(
                f"scattering baseline 'n' must be a number or \"fit\"; "
                f"got {n_in!r}"
            )
        if n_val < 0:
            raise ValueError(
                f"scattering baseline n must be ≥ 0; got {n_val}"
            )
        # B = c · λ^(-n) → minimise Σ (A − c · x)² with x = λ^(-n).
        x = wl_w ** (-n_val)
        denom = float(np.dot(x, x))
        if denom == 0.0:
            raise ValueError(
                "scattering baseline fit is degenerate (λ^(-n) = 0)"
            )
        c_val = float(np.dot(a_w, x) / denom)

    if np.any(wl <= 0):
        raise ValueError(
            "scattering baseline requires positive wavelengths "
            "(λ^(-n) is undefined at λ ≤ 0)"
        )
    baseline = c_val * (wl ** (-n_val))
    return a - baseline


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


_DISPATCH = {
    "linear":     compute_linear,
    "polynomial": compute_polynomial,
    "spline":     compute_spline,
    "rubberband": compute_rubberband,
    "scattering": compute_scattering,
}


def compute(mode: str, wavelength_nm, absorbance, params: Mapping | None):
    """Dispatch to the appropriate compute_* by mode name.

    Convenience for callers that hold the mode as a string (e.g. the
    UV/Vis tab's combobox). Raises ``ValueError`` on unknown modes.
    """
    if mode not in _DISPATCH:
        raise ValueError(
            f"unknown baseline mode {mode!r}; expected one of {BASELINE_MODES}"
        )
    fn = _DISPATCH[mode]
    return fn(wavelength_nm, absorbance, params or {})
