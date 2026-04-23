# Ptarmigan — Feature Backlog

Items are grouped by tab/area. Checked items are done. Priorities are approximate.

---

## 🌈 UV/Vis Tab

### Analysis tools
- [ ] **Peak picking** — click-to-mark peaks on the plot; display peak wavelength/energy as annotation; optionally export peak table
- [ ] **Baseline correction** — subtract a fitted baseline; options: linear (two-point), polynomial (order n), spline, rubberband/convex hull
- [ ] **Normalisation (interactive)** — expand beyond the current none/peak/area dropdown; allow normalising to a user-specified wavelength or over a chosen integration region
- [ ] **OLIS integrating sphere correction** — dedicated workflow for converting raw integrating sphere data (sample + reference + blank) into corrected absorbance

### Data management
- [ ] **Export** — save the currently displayed spectrum (after any conversion, normalisation, baseline subtraction) to CSV or TXT
- [ ] **Scan renaming** — allow the label to be edited in-place in the table (double-click to edit)

---

## 🔬 XANES Tab

- [ ] **Unified sidebar** — replace the current scan list with the same compact grid table + ⚙ style dialog used in the UV/Vis tab (colour swatch, linestyle canvas, linewidth, fill, legend toggle, ✕ remove)

---

## ⚗ EXAFS Tab

- [ ] **Unified sidebar** — same as XANES (grid table + ⚙ style dialog)

---

## 📈 TDDFT Tab

- [ ] **Unified sidebar** — the TDDFT panel already has a grid table; bring the click-to-cycle linestyle canvas and per-parameter ∀ apply-to-all into the ⚙ style dialog, replacing the current OptionMenu

---

## 🗂 App-wide / Infrastructure

- [ ] **Unified sidebar component** — extract the grid table + ⚙ style dialog into a shared `ScanTableWidget` class that all four tabs can instantiate; eliminates the current code duplication
- [ ] **Session persistence** — save and restore loaded files, axis limits, and style settings between runs (JSON sidecar or similar)
- [ ] **Keyboard shortcuts** — e.g. Delete to remove selected scan, Ctrl+Z to undo last add/remove

---

## ✅ Done (recent)

- [x] UV/Vis tab Phase 1: file import (generic + OLIS), A/%T display, nm/cm⁻¹/eV axis switching with sticky limits
- [x] UV/Vis sidebar: TDDFT-style compact grid table (colour swatch, visibility, legend toggle, click-to-cycle linestyle canvas with exact float linewidth, fill checkbox, ⚙ style dialog)
- [x] UV/Vis ⚙ style dialog: sliders for width/opacity/fill + per-parameter ∀ apply-to-all buttons
- [x] UV/Vis: push visible spectra to TDDFT overlay
- [x] Rename tabs: Spectra→TDDFT, XAS Analysis→XANES, EXAFS Studio→EXAFS
- [x] Fix overlay table not updating when dataset added from XANES tab
- [x] Fix ✕ remove button; unify all removal into `_remove_dataset(lst, idx)`
- [x] Fix "+ Add to Overlay" in XANES doing nothing (auto_run_all pre-selection bug)
- [x] Fix upstream merge bugs: `_yleft_lo` alias, `_show_left` UnboundLocalError, 4-tuple `_exp_scans` unpacking
