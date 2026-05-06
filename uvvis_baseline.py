"""UV/Vis baseline correction algorithms (Phase 4c CS-15, Phase 4m CS-24,
Phase 4s CS-37 / CS-38 / CS-39 / CS-40, Phase 4t CS-41 + floor-zero
expansion to all six modes).

Pure computational module — no Tk, no graph, no I/O. Each ``compute_*``
takes ``(wavelength_nm, absorbance, params)`` and returns the
baseline-subtracted absorbance as a numpy array of the same shape as
the input.

Six modes:

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
* **scattering+offset** (CS-38) — composite ``B(λ) = a + c · λ^(-n)``
  for samples that carry both a Rayleigh / Mie scattering tail AND
  an instrument or solvent additive offset. Same param schema as
  ``scattering``. The additive constant ``a`` is always fitted; ``n``
  is either supplied numerically or fit alongside ``a`` and ``c``.

CS-37 — ``params["floor_zero"]: bool`` (default False) enforces the
fit-time invariant that the corrected absorbance ``a - B`` is ≥ 0
everywhere. Phase 4t completes the per-mode roadmap: all six modes
ship the constrained-fit code path. Per-mode implementation:
``scattering`` (closed-form constrained ``c``), ``scattering+offset``
(convex QP via SLSQP), ``rubberband`` (no-op — the convex-hull
baseline is already ≤ data by construction), ``linear`` (SLSQP on
``(a_lo, a_hi)``), ``polynomial`` (SLSQP on the polynomial
coefficients), ``spline`` (SLSQP on the per-anchor absorbance values).

CS-39 — ``fit_scattering`` / ``fit_scattering_offset`` return the
resolved fit parameters as ``{"c_fitted", "n_fitted"}`` (and
``"a_fitted"`` for ``scattering+offset``). Apply sites use these to
record the fitted values on the OperationNode for diagnostic /
round-trip purposes.

CS-40 — fit-window error messages include the data's nm range so a
user typing a window outside the spectrum sees the real range without
re-reading the plot.

CS-41 — ``params["n_bounds"]: tuple[float, float]`` (default
``(0.1, 8.0)``) overrides the bounded-scan range used by the
``n="fit"`` branch in ``scattering`` and ``scattering+offset``.
Validated to require ``0 ≤ lo < hi``. No UI exposure today; the
hook is API-only so callers (or a future Tk row) can widen / shrink
the scan when the default range is wrong for their data.

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
    "compute_scattering_offset",
    "fit_scattering",
    "fit_scattering_offset",
    "compute",
    "compute_baseline_curve",
    "BASELINE_MODES",
]


BASELINE_MODES = (
    "linear", "polynomial", "spline", "rubberband",
    "scattering", "scattering+offset",
)


def _floor_zero(params) -> bool:
    """Read the CS-37 ``floor_zero`` flag from a (possibly None) params dict."""
    if params is None:
        return False
    return bool(params.get("floor_zero", False))


# CS-41 (Phase 4t) — default n="fit" scan bounds for the scattering and
# scattering+offset modes. Covers Rayleigh (n=4), large-particle Mie (n≈2),
# and dust-tail (n≈1) comfortably; sub-Rayleigh (n≈0.5) sits at the lower
# bound. Callers can override per-fit by passing ``params["n_bounds"] =
# (lo, hi)`` (validated; both ≥ 0; lo < hi).
_DEFAULT_N_BOUNDS: tuple[float, float] = (0.1, 8.0)


def _resolve_n_bounds(params) -> tuple[float, float]:
    """Read + validate the ``n_bounds`` override (CS-41)."""
    if params is None:
        return _DEFAULT_N_BOUNDS
    raw = params.get("n_bounds", _DEFAULT_N_BOUNDS)
    try:
        lo, hi = float(raw[0]), float(raw[1])
    except (TypeError, ValueError, IndexError, KeyError):
        raise ValueError(
            f"n_bounds must be a (lo, hi) pair of numbers; got {raw!r}"
        )
    if lo < 0 or hi < 0:
        raise ValueError(f"n_bounds entries must be ≥ 0; got ({lo}, {hi})")
    if lo >= hi:
        raise ValueError(f"n_bounds requires lo < hi; got ({lo}, {hi})")
    return lo, hi


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

    CS-37 (Phase 4t) — under ``floor_zero=True`` the two-point line is
    fit by SLSQP with linear inequality ``baseline(wl_i) ≤ a_i`` at
    every full-range sample. The objective minimises L2 distance from
    the unconstrained sampled-anchor values, so when the constraint
    isn't active the result matches the unconstrained two-point line.
    """
    floor_zero = _floor_zero(params)
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
        if floor_zero:
            a_pt = min(a_pt, float(a.min()))
        return a - a_pt
    if lo > hi:
        lo, hi = hi, lo

    order = np.argsort(wl)
    wl_s = wl[order]
    a_s = a[order]
    a_lo = float(np.interp(lo, wl_s, a_s))
    a_hi = float(np.interp(hi, wl_s, a_s))

    if floor_zero:
        a_lo, a_hi = _linear_floor_zero_fit(wl, a, lo, hi, a_lo, a_hi)

    baseline = a_lo + (a_hi - a_lo) * (wl - lo) / (hi - lo)
    return a - baseline


def _linear_floor_zero_fit(wl, a, lo, hi, a_lo_unc, a_hi_unc):
    """SLSQP-fit ``(a_lo, a_hi)`` so the line lies ≤ data everywhere.

    Objective minimises ``(a_lo - a_lo_unc)² + (a_hi - a_hi_unc)²`` so
    the result equals the unconstrained pair when the constraint slack
    is non-binding.
    """
    from scipy.optimize import minimize, LinearConstraint
    weight = (wl - lo) / (hi - lo)  # linear interp coefficient on a_hi
    # baseline_i = (1 - weight_i) * a_lo + weight_i * a_hi   ≤ a_i
    A_constraint = np.column_stack([1.0 - weight, weight])
    cons = LinearConstraint(A_constraint, lb=-np.inf, ub=a)

    # Initial guess: unconstrained pair shifted down by max overage so
    # the SLSQP starting point is feasible.
    residuals = (1.0 - weight) * a_lo_unc + weight * a_hi_unc - a
    max_overage = float(residuals.max()) if residuals.size else 0.0
    shift = max(max_overage, 0.0)
    x0 = [a_lo_unc - shift, a_hi_unc - shift]

    def obj(v):
        return float((v[0] - a_lo_unc) ** 2 + (v[1] - a_hi_unc) ** 2)

    result = minimize(obj, x0, method="SLSQP", constraints=[cons])
    if not result.success:
        raise ValueError(
            "linear floor-zero fit did not converge: "
            f"{result.message}; try widening the anchors or "
            "disabling floor-zero"
        )
    return float(result.x[0]), float(result.x[1])


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

    CS-37 (Phase 4t) — under ``floor_zero=True`` the polynomial
    coefficients are fit by SLSQP minimising the same window L2
    residual as ``np.polyfit`` subject to the linear inequality
    ``polyval(coeffs, wl_i) ≤ a_i`` at every full-range sample.
    Convex problem in the coefficients; the optimum equals the
    unconstrained ``np.polyfit`` result when no constraint binds.
    """
    floor_zero = _floor_zero(params)
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
            f"the fit window [{lo}, {hi}]; found {n_in}; "
            f"data spans [{float(wl.min()):.1f}, {float(wl.max()):.1f}] nm"
        )

    coeffs = np.polyfit(wl[mask], a[mask], order_n)
    if floor_zero:
        coeffs = _polynomial_floor_zero_fit(wl, a, mask, order_n, coeffs)
    baseline = np.polyval(coeffs, wl)
    return a - baseline


def _polynomial_floor_zero_fit(wl, a, mask, order_n, coeffs_unc):
    """SLSQP-fit polynomial coefficients with the floor-zero constraint.

    Returns ``coeffs`` in ``np.polyfit`` ordering (highest power first;
    ``coeffs[-1]`` is the constant term) so the result threads cleanly
    into ``np.polyval``. The SLSQP solve runs in a normalized variable
    ``z = (wl − center) / half_range`` so the design matrix stays
    well-conditioned for arbitrary polynomial order across wide
    wavelength windows; the fitted polynomial is then evaluated at the
    full wavelength grid and re-fit by ``np.polyfit`` to recover the
    wl-space coefficients exactly.
    """
    from scipy.optimize import minimize, LinearConstraint
    wl_w = wl[mask]
    a_w = a[mask]
    wl_min, wl_max = float(wl.min()), float(wl.max())
    wl_center = 0.5 * (wl_min + wl_max)
    wl_half = max(0.5 * (wl_max - wl_min), 1e-12)
    z_w = (wl_w - wl_center) / wl_half
    z_full = (wl - wl_center) / wl_half

    # Ascending-power Vandermonde in z (1, z, z^2, ...).
    powers_asc = np.arange(0, order_n + 1)
    V_w = z_w[:, None] ** powers_asc[None, :]
    V_full = z_full[:, None] ** powers_asc[None, :]

    # Initial guess: fit the unconstrained polynomial directly in
    # z-space (descending, then reverse for ascending). polyfit in
    # the well-conditioned z-axis is the natural starting point.
    z_coef_unc_asc = np.polyfit(z_w, a_w, order_n)[::-1]

    cons = LinearConstraint(V_full, lb=-np.inf, ub=a)
    residuals_full = V_full @ z_coef_unc_asc - a
    max_overage = float(residuals_full.max()) if residuals_full.size else 0.0
    x0 = z_coef_unc_asc.copy()
    if max_overage > 0:
        x0[0] -= max_overage  # shift constant term in z-space

    def obj(c):
        r = V_w @ c - a_w
        return float(np.dot(r, r))

    result = minimize(obj, x0, method="SLSQP", constraints=[cons])
    if not result.success:
        raise ValueError(
            "polynomial floor-zero fit did not converge: "
            f"{result.message}; try widening the fit window or "
            "disabling floor-zero"
        )
    # Convert z-space coefs back to wl-space descending coefs by
    # evaluating the polynomial at every wl sample and re-fitting in
    # wl-space — robust round-trip without manual basis conversion.
    z_coef_fit_asc = result.x
    baseline_full = V_full @ z_coef_fit_asc
    return np.polyfit(wl, baseline_full, order_n)


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

    CS-37 (Phase 4t) — under ``floor_zero=True`` the per-anchor
    absorbance values are fit by SLSQP minimising L2 distance from the
    sampled values subject to the spline (or fallback polynomial)
    evaluated at every full-range sample being ≤ data. The constraint
    is linear in ``anchor_a`` for both the cubic-spline and the
    polynomial fallbacks; SLSQP treats it as nonlinear but the
    underlying problem is convex.
    """
    floor_zero = _floor_zero(params)
    wl, a = _coerce(wavelength_nm, absorbance)
    anchors_in: Sequence = params["anchors"]
    anchors_sorted = sorted({float(x) for x in anchors_in})
    if len(anchors_sorted) < 2:
        raise ValueError("spline baseline requires at least 2 anchors")

    order = np.argsort(wl)
    wl_s = wl[order]
    a_s = a[order]
    anchor_a = np.interp(anchors_sorted, wl_s, a_s)

    if floor_zero:
        anchor_a = _spline_floor_zero_fit(wl, a, anchors_sorted, anchor_a)

    baseline = _spline_evaluate(wl, anchors_sorted, anchor_a)
    return a - baseline


def _spline_evaluate(wl, anchors_sorted, anchor_a):
    """Build the spline (or fallback polynomial) and evaluate at ``wl``.

    Mirrors the branch table in :func:`compute_spline` so the
    constrained-fit path can re-use the same evaluator.
    """
    if len(anchors_sorted) >= 4:
        cs = CubicSpline(anchors_sorted, anchor_a, extrapolate=True)
        return cs(wl)
    if len(anchors_sorted) == 3:
        coeffs = np.polyfit(anchors_sorted, anchor_a, 2)
        return np.polyval(coeffs, wl)
    coeffs = np.polyfit(anchors_sorted, anchor_a, 1)
    return np.polyval(coeffs, wl)


def _spline_floor_zero_fit(wl, a, anchors_sorted, anchor_a_unc):
    """SLSQP-fit the per-anchor absorbance values under the floor-zero constraint."""
    from scipy.optimize import minimize, NonlinearConstraint
    anchor_a_unc = np.asarray(anchor_a_unc, dtype=float)

    def constraint(v):
        # Returns ``a_i - baseline_i`` at every sample; SLSQP requires ≥ 0.
        return a - _spline_evaluate(wl, anchors_sorted, v)

    cons = NonlinearConstraint(constraint, lb=0.0, ub=np.inf)

    # Feasible initial guess: shift unconstrained anchor values down by
    # the worst per-sample overage so SLSQP starts inside the cone.
    baseline_unc = _spline_evaluate(wl, anchors_sorted, anchor_a_unc)
    overages = baseline_unc - a
    max_overage = float(overages.max()) if overages.size else 0.0
    x0 = anchor_a_unc - max(max_overage, 0.0)

    def obj(v):
        r = v - anchor_a_unc
        return float(np.dot(r, r))

    result = minimize(obj, x0, method="SLSQP", constraints=[cons])
    if not result.success:
        raise ValueError(
            "spline floor-zero fit did not converge: "
            f"{result.message}; try moving the anchors or "
            "disabling floor-zero"
        )
    return result.x


# ---------------------------------------------------------------------------
# Rubberband (lower convex hull, parameter-free)
# ---------------------------------------------------------------------------


def compute_rubberband(
    wavelength_nm, absorbance, params: Mapping | None = None,
) -> np.ndarray:
    """Convex-hull (rubberband) lower envelope baseline.

    Parameter-free for the fit itself — ``params`` is accepted (and
    may be ``None`` or an empty mapping) for API symmetry with the
    other modes. ``params["floor_zero"]`` is honoured (CS-37): the
    convex-hull lower envelope is ≤ data by construction so the
    constraint is automatically satisfied; under ``floor_zero=True``
    we lock the invariant with a runtime check that raises if
    numerical drift takes the corrected curve below zero.
    """
    floor_zero = _floor_zero(params)
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
    out = a - baseline
    if floor_zero and out.size and float(out.min()) < -1e-9:
        raise ValueError(
            "rubberband floor-zero invariant violated (numerical drift): "
            f"min(corrected) = {float(out.min()):.3e}"
        )
    return out


# ---------------------------------------------------------------------------
# Scattering (power-law c · λ^(-n) for colloidal / turbid samples — CS-24)
# Plus scattering+offset (CS-38) and shared fit helpers (CS-37/CS-39).
# ---------------------------------------------------------------------------


def _scattering_window(wl, a, params, label="scattering"):
    """Validate the scattering fit window and return ``(wl_w, a_w, lo, hi)``.

    Shared by ``compute_scattering`` / ``compute_scattering_offset``
    and their ``fit_*`` siblings. ``label`` selects the error-message
    prefix so the caller-facing message names the actual mode.
    """
    lo = float(params["fit_lo_nm"])
    hi = float(params["fit_hi_nm"])
    if lo > hi:
        lo, hi = hi, lo
    mask = (wl >= lo) & (wl <= hi)
    n_in = int(mask.sum())
    if n_in < 2:
        raise ValueError(
            f"{label} baseline needs ≥ 2 points in fit window "
            f"[{lo}, {hi}]; found {n_in}; "
            f"data spans [{float(wl.min()):.1f}, {float(wl.max()):.1f}] nm"
        )
    wl_w = wl[mask]
    a_w = a[mask]
    if np.any(wl_w <= 0):
        raise ValueError(
            f"{label} baseline requires positive wavelengths "
            "(λ^(-n) is undefined at λ ≤ 0)"
        )
    return wl_w, a_w, lo, hi


def _scattering_fit(wl, a, wl_w, a_w, lo, hi, n_in, floor_zero,
                    label="scattering", n_bounds=_DEFAULT_N_BOUNDS):
    """Recover ``(c, n)`` for ``B(λ) = c · λ^(-n)``.

    Under ``floor_zero=True`` enforces ``c · λ_i^(-n) ≤ a_i`` at every
    full-range sample by clamping the unconstrained least-squares ``c``
    to ``min_i(a_i · λ_i^n)``; for ``n="fit"`` the constraint is
    enforced inside a 1-D scan over ``n``.

    Without ``floor_zero`` the n="fit" branch falls back to the
    closed-form log–log fit (which requires absorbance > 0 throughout
    the fit window).

    CS-41 — ``n_bounds`` is the ``(lo, hi)`` pair the caller wants the
    n="fit" bounded scan to honour; defaults to ``_DEFAULT_N_BOUNDS``
    when the caller passes nothing.
    """
    fit_n = isinstance(n_in, str) and n_in.lower() == "fit"

    def _c_for_fixed_n(n):
        x_w = wl_w ** (-n)
        denom_w = float(np.dot(x_w, x_w))
        if denom_w == 0.0:
            raise ValueError(
                f"{label} baseline fit is degenerate (λ^(-n) = 0)"
            )
        c_unc = float(np.dot(a_w, x_w) / denom_w)
        if not floor_zero:
            return c_unc
        # Constraint: c · λ_i^(-n) ≤ a_i  ⇔  c ≤ a_i · λ_i^n at every
        # full-range sample. ``wl > 0`` is already guarded.
        c_max = float(np.min(a * (wl ** n)))
        return c_unc if c_unc <= c_max else c_max

    if not fit_n:
        try:
            n_val = float(n_in)
        except (TypeError, ValueError):
            raise ValueError(
                f"{label} baseline 'n' must be a number or \"fit\"; "
                f"got {n_in!r}"
            )
        if n_val < 0:
            raise ValueError(
                f"{label} baseline n must be ≥ 0; got {n_val}"
            )
        c_val = _c_for_fixed_n(n_val)
        return c_val, n_val

    if floor_zero:
        from scipy.optimize import minimize_scalar
        def residual(n):
            try:
                c = _c_for_fixed_n(n)
                pred = c * (wl_w ** (-n))
                return float(np.sum((a_w - pred) ** 2))
            except (ValueError, FloatingPointError):
                return 1e30
        res = minimize_scalar(residual, bounds=n_bounds, method="bounded")
        n_val = float(res.x)
        c_val = _c_for_fixed_n(n_val)
        return c_val, n_val

    # Unconstrained log–log fit.
    if np.any(a_w <= 0):
        raise ValueError(
            f"{label} baseline n='fit' requires absorbance > 0 "
            f"throughout the fit window [{lo}, {hi}] "
            "(log–log fit cannot accept zero or negative values)"
        )
    slope, intercept = np.polyfit(np.log(wl_w), np.log(a_w), 1)
    n_val = float(-slope)
    c_val = float(np.exp(intercept))
    return c_val, n_val


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

    Optional ``params`` keys:

    * ``floor_zero`` (CS-37) — when True, enforces ``a - B ≥ 0``
      everywhere by clamping the fitted ``c`` to ``min_i(a_i · λ_i^n)``.

    With ``n`` numeric, a closed-form linear least-squares fit
    determines the amplitude ``c`` only. With ``n="fit"`` and
    ``floor_zero=False``, the fit is performed in log–log space
    (``log A = log c − n · log λ``); this requires absorbance > 0
    throughout the fit window. With ``n="fit"`` and ``floor_zero=True``,
    a 1-D bounded scan over ``n`` carries the closed-form constrained
    ``c`` step inside.
    """
    wl, a = _coerce(wavelength_nm, absorbance)
    n_in = params["n"]  # KeyError if missing
    wl_w, a_w, lo, hi = _scattering_window(wl, a, params, label="scattering")
    floor_zero = _floor_zero(params)
    n_bounds = _resolve_n_bounds(params)
    c_val, n_val = _scattering_fit(
        wl, a, wl_w, a_w, lo, hi, n_in, floor_zero, label="scattering",
        n_bounds=n_bounds,
    )

    if np.any(wl <= 0):
        raise ValueError(
            "scattering baseline requires positive wavelengths "
            "(λ^(-n) is undefined at λ ≤ 0)"
        )
    baseline = c_val * (wl ** (-n_val))
    return a - baseline


def fit_scattering(
    wavelength_nm, absorbance, params: Mapping,
) -> dict:
    """Recover the resolved scattering fit parameters (CS-39).

    Same ``params`` schema as :func:`compute_scattering`. Returns
    ``{"c_fitted": float, "n_fitted": float}`` where ``c_fitted`` is
    always the resolved amplitude and ``n_fitted`` is the resolved
    exponent (which equals ``params["n"]`` when n is fixed numeric,
    or the recovered value when ``params["n"] == "fit"``).

    Apply sites use this to record the fitted values on the
    OperationNode so a later diagnostic / round-trip can read them
    without re-running ``compute``.
    """
    wl, a = _coerce(wavelength_nm, absorbance)
    n_in = params["n"]
    wl_w, a_w, lo, hi = _scattering_window(wl, a, params, label="scattering")
    floor_zero = _floor_zero(params)
    n_bounds = _resolve_n_bounds(params)
    c_val, n_val = _scattering_fit(
        wl, a, wl_w, a_w, lo, hi, n_in, floor_zero, label="scattering",
        n_bounds=n_bounds,
    )
    return {"c_fitted": c_val, "n_fitted": n_val}


# ---------------------------------------------------------------------------
# Scattering+offset (CS-38) — composite B(λ) = a + c · λ^(-n)
# ---------------------------------------------------------------------------


def _scattering_offset_fit(wl, a, wl_w, a_w, lo, hi, n_in, floor_zero,
                           n_bounds=_DEFAULT_N_BOUNDS):
    """Recover ``(a_param, c, n)`` for ``B(λ) = a_param + c · λ^(-n)``.

    Without ``floor_zero``: 2-D linear least-squares for fixed ``n``,
    1-D bounded scan over ``n`` with closed-form ``(a, c)`` inside for
    ``n="fit"``.

    With ``floor_zero=True``: convex QP with linear inequality
    ``a_param + c · λ_i^(-n) ≤ a_i`` at every full-range sample, solved
    via :func:`scipy.optimize.minimize` with method ``SLSQP``.

    CS-41 — ``n_bounds`` mirrors :func:`_scattering_fit`'s kwarg.
    """
    fit_n = isinstance(n_in, str) and n_in.lower() == "fit"

    def _ac_for_fixed_n(n):
        x_w = wl_w ** (-n)
        # Linear LSQ: minimise ||a_w - (a_param + c * x_w)||².
        A_mat = np.column_stack([np.ones_like(x_w), x_w])
        coeffs, *_ = np.linalg.lstsq(A_mat, a_w, rcond=None)
        a_unc = float(coeffs[0])
        c_unc = float(coeffs[1])
        if not floor_zero:
            return a_unc, c_unc
        # Convex QP via SLSQP. Constraint: a_param + c · λ_i^(-n) ≤ a_i
        # at every full-range sample.
        from scipy.optimize import minimize, LinearConstraint
        x_full = wl ** (-n)
        A_constraint = np.column_stack([np.ones_like(x_full), x_full])
        cons = LinearConstraint(A_constraint, lb=-np.inf, ub=a)
        # Initial guess: project unconstrained solution to feasibility
        # by shifting ``a_param`` down by the worst overage.
        residuals = a_unc + c_unc * x_full - a
        max_overage = float(residuals.max()) if residuals.size else 0.0
        x0 = [a_unc - max(max_overage, 0.0), c_unc]

        def obj(v):
            ap, cp = v
            r = a_w - (ap + cp * x_w)
            return float(np.sum(r ** 2))

        result = minimize(obj, x0, method="SLSQP", constraints=[cons])
        if not result.success:
            raise ValueError(
                "scattering+offset floor-zero fit did not converge: "
                f"{result.message}; try widening the fit window or "
                "disabling floor-zero"
            )
        return float(result.x[0]), float(result.x[1])

    if not fit_n:
        try:
            n_val = float(n_in)
        except (TypeError, ValueError):
            raise ValueError(
                f"scattering+offset baseline 'n' must be a number or "
                f"\"fit\"; got {n_in!r}"
            )
        if n_val < 0:
            raise ValueError(
                f"scattering+offset baseline n must be ≥ 0; got {n_val}"
            )
        a_val, c_val = _ac_for_fixed_n(n_val)
        return a_val, c_val, n_val

    # n="fit": 1-D bounded scan over n with closed-form (a, c) inside.
    from scipy.optimize import minimize_scalar
    def residual(n):
        try:
            a_v, c_v = _ac_for_fixed_n(n)
            pred = a_v + c_v * (wl_w ** (-n))
            return float(np.sum((a_w - pred) ** 2))
        except (ValueError, FloatingPointError):
            return 1e30
    res = minimize_scalar(residual, bounds=n_bounds, method="bounded")
    n_val = float(res.x)
    a_val, c_val = _ac_for_fixed_n(n_val)
    return a_val, c_val, n_val


def compute_scattering_offset(
    wavelength_nm, absorbance, params: Mapping,
) -> np.ndarray:
    """Composite power-law-plus-offset baseline subtraction (CS-38).

    Model: ``B(λ) = a + c · λ^(-n)``, where ``a`` is always fitted
    (additive instrument / solvent offset) and ``c · λ^(-n)`` is the
    Rayleigh / Mie scattering tail. Same ``params`` schema as
    :func:`compute_scattering` — ``n`` (numeric or ``"fit"``),
    ``fit_lo_nm``, ``fit_hi_nm``, optional ``floor_zero``.

    With ``n`` numeric the fit is a 2-D linear least squares in
    ``(a, c)``; with ``n="fit"`` a 1-D bounded scan over ``n`` carries
    the 2-D closed-form step inside. ``floor_zero=True`` enforces
    ``data - B ≥ 0`` everywhere via convex QP (SLSQP).
    """
    wl, a_arr = _coerce(wavelength_nm, absorbance)
    n_in = params["n"]
    wl_w, a_w, lo, hi = _scattering_window(
        wl, a_arr, params, label="scattering+offset",
    )
    floor_zero = _floor_zero(params)
    n_bounds = _resolve_n_bounds(params)
    a_val, c_val, n_val = _scattering_offset_fit(
        wl, a_arr, wl_w, a_w, lo, hi, n_in, floor_zero, n_bounds=n_bounds,
    )
    if np.any(wl <= 0):
        raise ValueError(
            "scattering+offset baseline requires positive wavelengths "
            "(λ^(-n) is undefined at λ ≤ 0)"
        )
    baseline = a_val + c_val * (wl ** (-n_val))
    return a_arr - baseline


def fit_scattering_offset(
    wavelength_nm, absorbance, params: Mapping,
) -> dict:
    """Recover the resolved scattering+offset fit parameters (CS-39).

    Same ``params`` schema as :func:`compute_scattering_offset`.
    Returns ``{"a_fitted", "c_fitted", "n_fitted"}`` — all three are
    always populated (``a_fitted`` and ``c_fitted`` are always fitted;
    ``n_fitted`` equals ``params["n"]`` when fixed or the recovered
    value when ``params["n"] == "fit"``).
    """
    wl, a_arr = _coerce(wavelength_nm, absorbance)
    n_in = params["n"]
    wl_w, a_w, lo, hi = _scattering_window(
        wl, a_arr, params, label="scattering+offset",
    )
    floor_zero = _floor_zero(params)
    n_bounds = _resolve_n_bounds(params)
    a_val, c_val, n_val = _scattering_offset_fit(
        wl, a_arr, wl_w, a_w, lo, hi, n_in, floor_zero, n_bounds=n_bounds,
    )
    return {"a_fitted": a_val, "c_fitted": c_val, "n_fitted": n_val}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


_DISPATCH = {
    "linear":            compute_linear,
    "polynomial":        compute_polynomial,
    "spline":            compute_spline,
    "rubberband":        compute_rubberband,
    "scattering":        compute_scattering,
    "scattering+offset": compute_scattering_offset,
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


# ---------------------------------------------------------------------------
# Display helper — recover the baseline function from a BASELINE node
# ---------------------------------------------------------------------------


def compute_baseline_curve(graph, baseline_node):
    """Recover the baseline curve that was subtracted to produce ``baseline_node``.

    A BASELINE ``DataNode`` stores the *corrected* spectrum
    (``arrays["absorbance"]`` = parent absorbance minus the fitted
    baseline). Plotting the fitted baseline itself for review (Phase
    4o intent A) requires recovering it as
    ``parent.absorbance - baseline_node.absorbance``.

    Parameters
    ----------
    graph : ProjectGraph
        The graph the node lives in. Used to walk
        ``baseline_node`` → BASELINE OperationNode → parent DataNode.
    baseline_node : DataNode
        Must be a ``NodeType.BASELINE`` DataNode with the canonical
        ``wavelength_nm`` + ``absorbance`` array pair.

    Returns
    -------
    tuple[numpy.ndarray, numpy.ndarray] | None
        ``(wavelength_nm, baseline_curve)`` on success, where
        ``baseline_curve`` has the same shape as ``wavelength_nm``.
        Returns ``None`` (does not raise) on every failure mode:
        wrong node type, missing arrays, no graph parent, parent is
        not a DataNode with matching arrays, shape mismatch. Callers
        (the UV/Vis tab's _redraw loop) treat ``None`` as "skip".
    """
    # Imported lazily to keep this module Tk-free + import-cycle-free.
    from nodes import DataNode, NodeType, OperationNode

    if (not isinstance(baseline_node, DataNode)
            or baseline_node.type != NodeType.BASELINE):
        return None
    arrays = baseline_node.arrays
    if "wavelength_nm" not in arrays or "absorbance" not in arrays:
        return None

    parents = graph.parents_of(baseline_node.id)
    if len(parents) != 1:
        return None
    op = graph.nodes.get(parents[0])
    if not isinstance(op, OperationNode) or not op.input_ids:
        return None
    parent_data = graph.nodes.get(op.input_ids[0])
    if (not isinstance(parent_data, DataNode)
            or "absorbance" not in parent_data.arrays):
        return None

    parent_abs = np.asarray(parent_data.arrays["absorbance"], dtype=float)
    child_abs = np.asarray(arrays["absorbance"], dtype=float)
    if parent_abs.shape != child_abs.shape:
        return None
    wl = np.asarray(arrays["wavelength_nm"], dtype=float)
    if wl.shape != child_abs.shape:
        return None
    return wl, parent_abs - child_abs
