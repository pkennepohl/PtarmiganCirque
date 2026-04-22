"""
uvvis_parser.py — UV/Vis/NIR file parser for Ptarmigan
Supports:
  • Generic two-column CSV / TSV / space-delimited text
  • OLIS (On-Line Instrument Systems) ASCII export format
Returns UVVisScan dataclass objects.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

# ── Physical constants ────────────────────────────────────────────────────────
_HC_NM_EV   = 1239.84193   # h·c in eV·nm  →  E(eV) = 1239.84 / λ(nm)
_EV_TO_CM1  = 8065.54      # 1 eV = 8065.54 cm⁻¹
_NM_TO_CM1  = 1e7          # λ(nm) → ν(cm⁻¹) = 1e7 / λ(nm)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class UVVisScan:
    """One UV/Vis/NIR spectrum.

    Internally always stored as:
      wavelength_nm  : ndarray  (ascending, nm)
      absorbance     : ndarray  (base-10 absorbance units)

    Derived quantities (wavenumber, %T, energy) are computed on the fly.
    """
    label:          str
    source_file:    str
    wavelength_nm:  np.ndarray          # ascending λ (nm)
    absorbance:     np.ndarray          # A  (base-10)
    metadata:       Dict = field(default_factory=dict)

    # ── Derived axes ──────────────────────────────────────────────────────────
    @property
    def wavenumber_cm1(self) -> np.ndarray:
        """ν (cm⁻¹) — descending (matches ascending λ)."""
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(self.wavelength_nm > 0,
                            _NM_TO_CM1 / self.wavelength_nm, 0.0)

    @property
    def energy_ev(self) -> np.ndarray:
        """E (eV) — ascending."""
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(self.wavelength_nm > 0,
                            _HC_NM_EV / self.wavelength_nm, 0.0)

    @property
    def transmittance_pct(self) -> np.ndarray:
        """%T = 100 × 10^(−A)."""
        return 100.0 * np.power(10.0, -np.clip(self.absorbance, -10, 10))

    def display_name(self) -> str:
        return self.label or os.path.basename(self.source_file)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _nm_to_absorbance(wl: np.ndarray, intensity: np.ndarray,
                      y_type: str) -> np.ndarray:
    """Convert raw intensity array to absorbance.

    y_type: 'A'  — already absorbance
            '%T' — percent transmittance
            'T'  — fractional transmittance (0–1)
    """
    if y_type == "A":
        return intensity
    if y_type == "%T":
        t = np.clip(intensity, 1e-10, 100.0) / 100.0
    else:  # 'T'
        t = np.clip(intensity, 1e-10, 1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        return -np.log10(t)


def _guess_y_type(values: np.ndarray) -> str:
    """Heuristic: %T values cluster near 0–100; A values are typically 0–3."""
    med = float(np.nanmedian(values))
    mx  = float(np.nanmax(values))
    if mx > 5.0 or med > 3.0:
        return "%T"
    return "A"


def _guess_x_unit(values: np.ndarray) -> str:
    """Heuristic: nm if median < 3000, else cm⁻¹."""
    med = float(np.nanmedian(values))
    return "nm" if med < 3000 else "cm-1"


def _sort_ascending_nm(wl: np.ndarray, intensity: np.ndarray
                       ) -> Tuple[np.ndarray, np.ndarray]:
    """Ensure wavelength array is ascending."""
    if len(wl) < 2:
        return wl, intensity
    if wl[0] > wl[-1]:
        wl, intensity = wl[::-1], intensity[::-1]
    return wl, intensity


# ── Generic two-column parser ─────────────────────────────────────────────────

_COMMENT_RE = re.compile(r"^\s*[#;!]")
_FLOAT_RE   = re.compile(r"^[+-]?\d")


def _parse_generic(path: str) -> List[UVVisScan]:
    """Parse a generic 2-column (x, y) text file.

    Accepts comma, tab, semicolon, or space as delimiter.
    Auto-detects x-unit (nm / cm⁻¹) and y-unit (A / %T).
    """
    x_vals, y_vals = [], []
    header_lines   = []

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            if _COMMENT_RE.match(line):
                header_lines.append(line)
                continue
            # Try to split into at least two numeric tokens
            for sep in (",", "\t", ";", None):   # None = any whitespace
                parts = line.split(sep) if sep else line.split()
                nums  = []
                for p in parts:
                    p = p.strip().replace(",", ".")
                    try:
                        nums.append(float(p))
                    except ValueError:
                        break
                if len(nums) >= 2:
                    x_vals.append(nums[0])
                    y_vals.append(nums[1])
                    break
            else:
                # Not parseable — treat as header if we haven't seen data yet
                if not x_vals:
                    header_lines.append(line)

    if len(x_vals) < 2:
        raise ValueError(f"Could not read numeric data from {path!r}")

    x = np.array(x_vals, dtype=float)
    y = np.array(y_vals, dtype=float)

    x_unit = _guess_x_unit(x)
    y_type = _guess_y_type(y)

    # Convert x to nm
    if x_unit == "cm-1":
        with np.errstate(divide="ignore", invalid="ignore"):
            wl = np.where(x > 0, _NM_TO_CM1 / x, 0.0)
    else:
        wl = x

    wl, y = _sort_ascending_nm(wl, y)
    absorbance = _nm_to_absorbance(wl, y, y_type)

    label = os.path.splitext(os.path.basename(path))[0]
    meta  = {"x_unit_raw": x_unit, "y_type_raw": y_type,
             "header": "\n".join(header_lines[:10])}

    return [UVVisScan(label=label, source_file=path,
                      wavelength_nm=wl, absorbance=absorbance,
                      metadata=meta)]


# ── OLIS parser ───────────────────────────────────────────────────────────────

def _parse_olis(path: str) -> List[UVVisScan]:
    """Parse an OLIS ASCII export file.

    OLIS files typically look like:
        OLIS DSM-20 UV/Vis/NIR  (or similar instrument header)
        Sample: <name>
        ...key: value pairs...
        (blank line or DATA keyword)
        wavelength   channel1  [channel2 ...]

    Multiple datasets may appear in one file (separated by blank/header lines).
    """
    scans: List[UVVisScan] = []

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()

    # Split file into sections at blank lines or repeated headers
    sections: List[List[str]] = []
    current: List[str] = []
    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line.strip():
            if current:
                sections.append(current)
                current = []
        else:
            current.append(line)
    if current:
        sections.append(current)

    def _try_section(sec: List[str], base_label: str, section_idx: int
                     ) -> Optional[UVVisScan]:
        """Try to extract one spectrum from a section of lines."""
        meta: Dict = {}
        x_vals, y_vals = [], []
        y_type = "A"

        for line in sec:
            # Key-value metadata lines  (e.g. "Sample Name: Foo")
            kv = re.match(r"^([A-Za-z /_-]+)\s*[:=]\s*(.+)$", line)
            if kv:
                key, val = kv.group(1).strip(), kv.group(2).strip()
                meta[key.lower()] = val
                # Look for unit hints
                if "transmit" in key.lower():
                    y_type = "%T"
                elif "absorb" in key.lower():
                    y_type = "A"
                continue

            # Data line: try to parse two+ numbers
            parts = line.split()
            nums  = []
            for p in parts:
                try:
                    nums.append(float(p))
                except ValueError:
                    break
            if len(nums) >= 2:
                x_vals.append(nums[0])
                y_vals.append(nums[1])

        if len(x_vals) < 2:
            return None

        x = np.array(x_vals, dtype=float)
        y = np.array(y_vals, dtype=float)

        # Auto-detect units if not found in metadata
        if "y_type" not in meta:
            y_type = _guess_y_type(y) if y_type == "A" else y_type
        x_unit = _guess_x_unit(x)

        if x_unit == "cm-1":
            with np.errstate(divide="ignore", invalid="ignore"):
                wl = np.where(x > 0, _NM_TO_CM1 / x, 0.0)
        else:
            wl = x

        wl, y = _sort_ascending_nm(wl, y)
        absorbance = _nm_to_absorbance(wl, y, y_type)

        # Try to find a meaningful label
        label = (meta.get("sample name") or
                 meta.get("sample") or
                 meta.get("name") or
                 base_label)
        if section_idx > 0:
            label = f"{label} ({section_idx + 1})"

        meta.update({"x_unit_raw": x_unit, "y_type_raw": y_type,
                     "instrument": "OLIS"})
        return UVVisScan(label=label, source_file=path,
                         wavelength_nm=wl, absorbance=absorbance,
                         metadata=meta)

    base = os.path.splitext(os.path.basename(path))[0]
    for i, sec in enumerate(sections):
        scan = _try_section(sec, base, i if len(sections) > 1 else 0)
        if scan is not None:
            scans.append(scan)

    if not scans:
        raise ValueError(f"No UV/Vis data found in OLIS file {path!r}")
    return scans


# ── Public entry point ────────────────────────────────────────────────────────

# File-extension dispatch table
_OLIS_EXTENSIONS = {".olis", ".olisdat", ".dat", ".asc"}
_GENERIC_EXTENSIONS = {".csv", ".tsv", ".txt", ".prn", ".dpt", ".sp",
                        ".jdx", ".dx"}


def parse_uvvis_file(path: str) -> List[UVVisScan]:
    """Parse a UV/Vis/NIR data file and return a list of UVVisScan objects.

    The parser is chosen based on file extension; ambiguous extensions
    (e.g. .dat, .asc) are tried as OLIS first, then generic.
    """
    ext = os.path.splitext(path)[1].lower()

    if ext in {".olis", ".olisdat"}:
        return _parse_olis(path)

    if ext in {".dat", ".asc"}:
        # Try OLIS first; fall back to generic
        try:
            scans = _parse_olis(path)
            if scans:
                return scans
        except Exception:
            pass
        return _parse_generic(path)

    # Default: generic two-column
    return _parse_generic(path)
