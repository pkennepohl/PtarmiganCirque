# Ptarmigan — Project Register

## About

Ptarmigan is a Python/Tkinter desktop application for spectroscopic data
analysis. It embeds matplotlib figures and provides four analysis tabs:
**TDDFT** (TD-DFT calculation overlay), **XANES**, **EXAFS**, and **UV/Vis/NIR**.
The core workflow is: load raw data → inspect and process → push selected
spectra to the TDDFT overlay for comparison with calculated spectra.

Main files:
| File | Purpose |
|---|---|
| `binah.py` | App entry point; notebook + tab wiring |
| `plot_widget.py` | TDDFT tab + overlay panel |
| `xas_analysis_tab.py` | XANES tab |
| `exafs_analysis_tab.py` | EXAFS tab |
| `uvvis_tab.py` | UV/Vis/NIR tab |
| `uvvis_parser.py` | UV/Vis file parser (generic + OLIS) |
| `experimental_parser.py` | XAS file parser |

---

## Priority Scale (MoSCoW)

| Symbol | Tier | Meaning |
|---|---|---|
| 🔴 | **Must** | Core functionality; the app feels incomplete without it |
| 🟡 | **Should** | Clearly on the roadmap; do soon |
| 🟢 | **Could** | Nice to have; do if time permits |
| ⚪ | **Won't** (for now) | Explicitly deferred — not forgotten, just not yet |

---

## Current Features

### 📈 TDDFT Tab
- Load TD-DFT calculation output files (multiple formats via `experimental_parser`)
- Load experimental scans (`ExperimentalScan` dataclass)
- Scrollable overlay panel — compact grid table with per-scan controls:
  - Colour swatch, visibility checkbox, legend toggle (✓/–)
  - Linestyle OptionMenu, linewidth entry, fill checkbox
  - Style… button → modal dialog (linestyle radios, linewidth slider,
    colour picker + reset, fill + fill_alpha slider)
  - Style dialog: Apply / Apply to ALL Exp. / Set as Default / Save / Cancel
- Broadening controls: FWHM slider, ΔE shift, scale factor
- Envelope (convolved) and stick spectrum display
- Per-spectrum component toggles
- Link groups for experimental scans
- Secondary x-axis (energy ↔ wavelength)
- Sticky axis limit controls
- Collapsible Style bar (grid lines, background colour, fonts)
- Shared style defaults persisted to `~/.binah_config.json`
- `_ToolTip` hover tooltips on panel widgets

### 🔬 XANES Tab
- Load XAS data files (multi-format via `experimental_parser`)
- Scan list with per-scan visibility toggles
- Auto-run all loaded scans
- E0 detection (automatic) with manual override
- Pre-edge background fitting
- Post-edge normalisation fitting
- Normalised μ(E) display
- Results panel (E0, edge step, normalisation parameters)
- Push selected scan to TDDFT overlay

### ⚗ EXAFS Tab
- Load XAS data (same files as XANES)
- k-space display: χ(k) vs k with k¹/k²/k³ weighting
- Window function (Hanning, etc.) with kmin/kmax/dk controls
- R-space display: |χ(R)| via Fourier transform
- Push selected scan to TDDFT overlay

### 🌈 UV/Vis Tab
- Load spectra: generic (CSV / TSV / TXT / PRN / DPT / SP) and OLIS ASCII format
- Absorbance and %T display with live conversion
- X-axis unit switching: nm / cm⁻¹ / eV
- Sticky axis limits that convert correctly when switching units
- Inverted nm axis (high → low wavelength)
- Secondary λ(nm) axis in cm⁻¹ mode (toggle)
- Basic normalisation: none / peak / area
- Compact grid table sidebar:
  - Colour swatch (click → colour picker)
  - Visibility checkbox + label
  - Legend toggle (✓/–)
  - Linestyle canvas — draws actual dash pattern in scan colour; click to cycle
    solid → dashed → dotted → dashdot; renders exact float linewidth
  - Fill checkbox
  - ⚙ style dialog button (with tooltip)
  - ✕ remove button
- ⚙ Per-scan style dialog:
  - Linestyle radio buttons
  - Line width slider (0.5–5 pt, exact float)
  - Line opacity slider
  - Colour swatch + picker + Reset to auto
  - Fill checkbox + fill opacity slider
  - Per-parameter ∀ button — applies just that one setting to all spectra
  - Apply / ∀ Apply to All (style only, not colour) / Save / Cancel
- Push visible spectra to TDDFT overlay

### 🗂 App-wide
- Four-tab notebook: TDDFT / XANES / EXAFS / UV/Vis
- Overlay system: XANES / EXAFS / UV/Vis → TDDFT overlay panel
- `_ToolTip` class (plot_widget.py and uvvis_tab.py)
- Shared style config persistence (`~/.binah_config.json`)

---

## To-Do

### 🌈 UV/Vis Tab

| Priority | Feature | Notes |
|---|---|---|
| 🔴 | **Baseline correction** | Linear (two-point), polynomial (order n), spline, rubberband/convex hull |
| 🔴 | **Export processed data** | Save displayed spectrum (post-conversion / normalisation / baseline) to CSV or TXT |
| 🔴 | **Scan renaming** | Edit label in-place in the table (double-click) |
| 🟡 | **Peak picking** | Click-to-mark peaks; display λ/E annotation; optional peak table export |
| 🟡 | **OLIS integrating sphere correction** | Sample + reference + blank workflow → corrected absorbance |
| 🟡 | **Interactive normalisation** | Normalise to a user-specified wavelength or chosen integration region |
| 🟡 | **Difference spectra** | Subtract one loaded spectrum from another |
| 🟡 | **Smoothing** | Savitzky-Golay or moving average; controlled by order/window parameters |
| 🟢 | **Second derivative** | Useful for resolving overlapping bands |
| 🟢 | **Beer-Lambert / concentration** | Use known ε to extract concentration, or fit ε from known concentration |

### 🔬 XANES Tab

| Priority | Feature | Notes |
|---|---|---|
| 🟡 | **Unified sidebar** | Replace current scan list with the UV/Vis-style grid table + ⚙ style dialog |
| 🟡 | **Difference spectra** | Subtract one XANES scan from another |
| 🟢 | **Batch E0 table export** | Export a CSV of E0 / edge step values across all loaded scans |

### ⚗ EXAFS Tab

| Priority | Feature | Notes |
|---|---|---|
| 🟡 | **Unified sidebar** | Same as XANES |

### 📈 TDDFT Tab

| Priority | Feature | Notes |
|---|---|---|
| 🟡 | **Sidebar polish** | Bring click-to-cycle linestyle canvas and per-parameter ∀ buttons into the ⚙ style dialog, matching UV/Vis |
| 🟢 | **Scan renaming** | Edit experimental scan label in-place |

### 🗂 App-wide

| Priority | Feature | Notes |
|---|---|---|
| 🔴 | **Unified sidebar component** | Extract grid table + ⚙ style dialog into a shared `ScanTableWidget` class; eliminates growing code duplication across tabs |
| 🟡 | **Copy plot to clipboard** | One-click copy of the current figure as an image |
| 🟡 | **Drag-and-drop file loading** | Drop files onto any tab to load them |
| 🟢 | **Session persistence** | Save and restore loaded files, axis limits, and style settings between runs |
| 🟢 | **Keyboard shortcuts** | e.g. Delete to remove selected scan, Ctrl+Z to undo add/remove |
| 🟢 | **Plot annotations** | Place arbitrary text labels on the figure |
| ⚪ | **EXAFS shell fitting** | Large feature; better served by a dedicated tool (Artemis etc.) |
| ⚪ | **Reference spectra database** | Useful but large scope; consider linking to existing databases |

---

## Design Decisions (non-obvious choices)

- **Internal storage as absorbance + nm** — `UVVisScan` stores wavelength_nm and
  absorbance internally; all other representations (%T, cm⁻¹, eV) are computed
  properties. This keeps conversion logic in one place.
- **Sticky axis limits** — limits are stored in StringVar entry fields rather than
  as floats so the user can clear them (empty string = auto). Unit conversion on
  switch is handled by `_convert_xlim` which always normalises through nm.
- **nm axis inversion** — nm axis is rendered descending (high → low); stored
  limits are always kept as (min, max) in nm and swapped to `set_xlim(hi, lo)`
  on draw to maintain the inversion.
- **`_push_to_all(key, get_fn)` factory** — generates per-parameter apply-to-all
  callbacks in the style dialog without repeating boilerplate; `get_fn` is a
  zero-argument callable (e.g. `var.get`) so it reads the current value at
  call time rather than at closure creation time.
- **`_exp_scans` is a 5-tuple** — `(label, ExperimentalScan, BooleanVar,
  style_dict, in_legend_var)`; must be unpacked as 5-tuple everywhere.
  Previously caused silent bugs when upstream merged 4-tuple assumptions.
