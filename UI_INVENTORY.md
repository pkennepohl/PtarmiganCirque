# Ptarmigan — UI Interaction Inventory

> ## ⚠ IMPORTANT — READ BEFORE USING THIS DOCUMENT
>
> This inventory describes the **current state** of the application UI
> as of the start of the architectural redesign. It is a record of what
> exists in the code, **not a specification of what to build**.
>
> ### Load these documents first
> - **ARCHITECTURE.md** — authoritative design decisions; read in full
> - **BACKLOG.md** — what to build and in what order (eleven phases)
> - **COMPONENTS.md** — detailed specs for each new component
>
> ### Use this inventory for
> - Finding existing callbacks and variable names when migrating code
> - Identifying which controls to relocate during restructuring
> - Confirming the reference implementation details of the UV/Vis tab
>   (the UV/Vis sidebar is the template for the new ScanTreeWidget)
>
> ### Do NOT use this inventory for
> - Deciding what the new UI should look like
> - Determining which controls to implement
> - Understanding the new architecture
>
> ### Tab disposition summary
>
> | Current tab / file | New status |
> |---|---|
> | TDDFT tab (`plot_widget.py`) | Replaced entirely by Compare tab (`compare_tab.py`) |
> | XANES tab (`xas_analysis_tab.py`) | Refactored; most controls retained in new locations |
> | EXAFS tab (`exafs_analysis_tab.py`) | Refactored; FEFF sub-tab extracted entirely to FEFF Workspace |
> | UV/Vis tab (`uvvis_tab.py`) | Reference implementation; least restructuring needed |
> | `binah.py` global controls | Partially retained, partially redistributed |
>
> ### Disposition key (Disposition column)
>
> | Code | Meaning |
> |---|---|
> | **Retain** | Kept as-is or near-as-is in the new architecture |
> | **Relocate → X** | Moves to a different location X |
> | **Supersede** | Replaced by a new component or pattern |
> | **Extract → X** | Physically moved to a new file X (not rewritten) |
> | **Retire** | Removed; new architecture makes it unnecessary |
> | **Rename** | Kept but with a new label or action name |
> | **Investigate** | Purpose unclear; requires code archaeology before deciding |

---

## Column reference

- **Widget** — Tkinter widget type
- **Label / Text** — what the user sees
- **Variable / Callback** — what it is wired to in code
- **Function** — what it does
- **Scope** — `node` (one dataset), `all` (every loaded item),
  `plot` (the axes/figure), `app` (global/persistent),
  `provisional` (dialog-local, not committed)
- **Disposition** — what happens to this control in the redesign

> **Note on Scope:** The original inventory used `scan` for per-item
> scope. This has been updated to `node` throughout to reflect the new
> DataNode model. `provisional` is a new scope value for controls that
> operate within a dialog before any commit action.

---

## Above the Tabs — `binah.py`

### Menu Bar

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Command | New Project | `_new_project()` | Clear all state, start fresh | app | Retain — now creates new .ptproj/ directory |
| Command | Open Project… | `_open_project()` | Load `.otproj` file | app | Retain — updated to load .ptproj/ format |
| Command | Save Project | `_save_project()` | Save to current path | app | Retain |
| Command | Save Project As… | `_save_project_as()` | Save to new path | app | Retain |
| Cascade | Recent Projects | `_recent_menu` | Dynamic submenu of recent files | app | Retain |
| Command | Open .out File… | `_open_file()` | Load single ORCA output file | node | Relocate → Compare tab "Load Calculated…" action |
| Command | Open Multiple Files… | `_open_multiple()` | Load multiple ORCA files | all | Relocate → Compare tab |
| Command | Load Experimental Data… | `_load_experimental()` | Load XAS scan data | node | Rename → "Load Data…"; routes by file type |
| Command | Load SGM Stack… | `_load_sgm_stack()` | Open SGM loader window | node | Retain — produces multiple RAW_FILE DataNodes |
| Command | Exit | `destroy()` | Quit application | app | Retain |
| Command | FEFF Setup / Update… | `_launch_feff_setup()` | Open FEFF installation dialog | app | Retain |
| Command | About | `_show_about()` | Show about box | app | Retain |
| Command | Export Reproducibility Report | *(new)* | Export methods summary for Compare nodes | app | **New — add to File menu** |
| Command | Export Project Archive | *(new)* | Zip .ptproj/ for sharing | app | **New — add to File menu** |

### Keyboard Shortcuts

| Shortcut | Callback | Function | Scope | Disposition |
|----------|----------|----------|-------|-------------|
| Ctrl+N | `_new_project()` | New project | app | Retain |
| Ctrl+O | `_open_file()` | Open ORCA file | node | Reassign → "Load Data…" (general, type-routed) |
| Ctrl+Shift+O | `_open_project()` | Open project | app | Retain |
| Ctrl+S | `_save_project()` | Save project | app | Retain |
| Ctrl+Shift+S | `_save_project_as()` | Save as | app | Retain |
| Ctrl+E | `_load_experimental()` | Load experimental data | node | Consolidate into Ctrl+O |
| Ctrl+Return | *(new)* | Commit selected provisional node | node | **New** |
| Escape | *(new)* | Discard selected provisional node | node | **New** |
| Ctrl+Shift+C | *(new)* | Send selected committed node to Compare | node | **New** |
| Ctrl+D | *(new)* | Discard selected node | node | **New** |

### Top Toolbar

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Button | « | `_toggle_sidebar()` | Hide / show left file-list sidebar | app | Retain — now toggles left engine-parameter panel |
| Button | Open File | `_open_file()` | Load single ORCA file | node | Supersede — tab-aware loading replaces this |
| Button | Reload | `_reload_file()` | Reload current file | node | Retain — reloads source file for selected node |
| Combobox | (section list) | `_section_var` → `_on_section_change()` | Select TDDFT section from current file | node | Relocate → Compare tab (TDDFT node property) |
| Label | (filename) | `_file_label` | Display current loaded filename | node | Supersede — project title in window title bar replaces this |

### Left Sidebar (File List)

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Listbox | (loaded files) | `_file_listbox` → `_on_file_select()` | Switch to selected ORCA file | node | Supersede — ScanTreeWidget on Compare tab replaces this |
| Button | + Add to Overlay | `_add_current_to_overlay()` | Add current section to overlay | node | Retire — "Send to Compare" replaces this concept |
| Button | Load Exp. Data… | `_load_experimental()` | Load XAS scan data | node | Supersede — tab-aware loading replaces this |
| Text (read-only) | (metadata) | `_info_text` | Display spectrum metadata | node | Relocate → DataNode inspector panel (accessible from ScanTreeWidget) |

### Status Bar

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Label | (status text) | `_status` (StringVar) | Application status messages | app | Retain — extended to show last committed operation |

---

## Dialogs spawned from `binah.py`

### SXRMB Import Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Radiobutton | TEY only | `_signal_var` = "tey" | Load TEY channel | node | Retain — each channel becomes a separate RAW_FILE DataNode |
| Radiobutton | Fluorescence only | `_signal_var` = "fluor" | Load fluorescence channel | node | Retain |
| Radiobutton | Both | `_signal_var` = "both" | Load both channels | all | Retain |
| Button | Load | `do_load()` | Parse and load file | node | Retain |
| Button | Cancel | `win.destroy()` | Abort | provisional | Retain |

### BioXAS .dat Options Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Radiobutton | Fluorescence | `mode_var` = "fluorescence" | Fluorescence mode | node | Retain |
| Radiobutton | Transmission | `mode_var` = "transmission" | Transmission mode | node | Retain |
| Checkbutton | Apply Athena-style normalization | `norm_var` (BooleanVar) | Enable normalization on load | node | Retire — normalisation is now an explicit operation after load; raw data is always the first committed node |
| Button | Load | `do_load()` | Parse and load | node | Retain |
| Button | Cancel | `win.destroy()` | Abort | provisional | Retain |

### Athena .prj Scan Selection Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Listbox | (scan list) | `lb` → `do_load()` | Select scans to load from .prj | all | Retain — each selected scan becomes a RAW_FILE DataNode |
| Button | Load Selected | `do_load()` | Load checked scans | all | Retain |
| Button | Select All | `lb.selection_set(0, END)` | Select all scans | all | Retain |
| Button | Cancel | `win.destroy()` | Abort | provisional | Retain |

### Replace-or-Add Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Button | Replace existing | `_choose("replace")` | Replace TDDFT with new file | node | Investigate → OQ-005: may be retired; TDDFT files always load as new nodes in Compare |
| Button | Add as overlay | `_choose("add")` | Add as overlay instead | node | Investigate → OQ-005 |
| Button | Cancel | `_choose("cancel")` | Abort | provisional | Retain |

### FEFF Setup Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Text (read-only) | (log) | `_feff_setup_log` | Installation progress log | app | Retain — app-level FEFF installation management unchanged |
| Label | (status) | `_feff_setup_status` | Status message | app | Retain |
| Button | Close | `win.destroy()` | Close (enabled when done) | app | Retain |

---

## 📈 TDDFT Tab — `plot_widget.py`

> **Disposition summary:** This tab is replaced entirely by the new
> Compare tab (`compare_tab.py`). No controls remain in a "TDDFT tab."
> Controls are redistributed to: Compare tab top bar, Compare tab Plot
> Settings dialog, unified style dialog (CS-05), and ScanTreeWidget
> (CS-04). See COMPONENTS.md CS-08 for the Compare tab specification.
>
> **OQ-001:** The link groups feature in this file requires investigation
> before the Compare tab is implemented. Read the implementation,
> determine what it does, and report before proceeding.

### Controls Bar

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Radiobutton | nm | `_x_unit` = "nm" | X-axis in nanometers | plot | Relocate → Compare tab top bar |
| Radiobutton | cm⁻¹ | `_x_unit` = "cm-1" | X-axis in wavenumber | plot | Relocate → Compare tab top bar |
| Radiobutton | eV | `_x_unit` = "eV" | X-axis in electron volts | plot | Relocate → Compare tab top bar |
| Checkbutton | λ(nm) axis | `_show_nm_axis` (BooleanVar) | Secondary nm axis in cm⁻¹ mode | plot | Relocate → Compare tab top bar |
| Entry | (nm step) | `_nm_step` (StringVar) | Manual tick spacing for nm axis | plot | Relocate → Compare tab Plot Settings dialog |
| Checkbutton | Normalise | `_normalise` (BooleanVar) | Normalize TDDFT spectra | plot | Relocate → Compare tab top bar |
| Checkbutton | Grid | `_show_grid` (BooleanVar) | Show / hide plot grid | plot | Relocate → Compare tab Plot Settings dialog |
| Button | Plot BG… | `_open_plot_bg_dialog()` | Change plot background colour | plot | Relocate → Compare tab Plot Settings dialog |
| Button | Fonts… | `_open_font_dialog()` | Open font settings dialog | plot | Relocate → Compare tab Plot Settings dialog |
| Button | ⁝ Pop Out | `_pop_out_graph()` | Open graph in separate window | plot | Relocate → Compare tab top bar |
| Button | Export CSV | `_export_csv()` | Export plot data to CSV | plot | Relocate → Compare tab top bar |
| Button | Save Fig | `_save_figure()` | Save figure as image | plot | Relocate → Compare tab top bar |

### Axis Limits Bar

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Entry | X lo | `_xlim_lo` (StringVar) → `_replot()` | X-axis lower bound (blank = auto) | plot | Relocate → Compare tab top bar |
| Entry | X hi | `_xlim_hi` (StringVar) → `_replot()` | X-axis upper bound | plot | Relocate → Compare tab top bar |
| Button | Auto X | `_auto_x()` | Reset x to auto | plot | Relocate → Compare tab top bar |
| Entry | Y lo (TDDFT) | `_ylim_lo` (StringVar) → `_replot()` | TDDFT y lower bound | plot | Relocate → Compare tab top bar |
| Entry | Y hi (TDDFT) | `_ylim_hi` (StringVar) → `_replot()` | TDDFT y upper bound | plot | Relocate → Compare tab top bar |
| Button | Auto (TDDFT) | `_auto_y()` | Reset TDDFT y to auto | plot | Relocate → Compare tab top bar |
| Entry | Y lo (Exp) | `_ylim_exp_lo` (StringVar) → `_replot()` | Experimental y lower bound | plot | Relocate → Compare tab top bar |
| Entry | Y hi (Exp) | `_ylim_exp_hi` (StringVar) → `_replot()` | Experimental y upper bound | plot | Relocate → Compare tab top bar |
| Button | Auto (Exp) | `_auto_y_exp()` | Reset experimental y to auto | plot | Relocate → Compare tab top bar |
| Radiobutton | Left | `_tddft_on_left` = "left" | TDDFT on left y-axis | plot | Relocate → Compare tab Plot Settings dialog |
| Radiobutton | Right | `_tddft_on_left` = "right" | TDDFT on right y-axis | plot | Relocate → Compare tab Plot Settings dialog |
| Radiobutton | In | `_tick_direction` = "in" | Inward ticks | plot | Relocate → Compare tab Plot Settings dialog |
| Radiobutton | Out | `_tick_direction` = "out" | Outward ticks | plot | Relocate → Compare tab Plot Settings dialog |
| Radiobutton | Both | `_tick_direction` = "both" | Both-side ticks | plot | Relocate → Compare tab Plot Settings dialog |

### Title & Label Bar

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Entry | (title) | `_custom_title` (StringVar) → `_replot()` | Custom plot title | plot | Relocate → Compare tab Plot Settings dialog |
| Button | Auto | `_auto_title()` | Generate default title | plot | Relocate → Compare tab Plot Settings dialog |
| Button | None | `_clear_title()` | Remove title | plot | Relocate → Compare tab Plot Settings dialog |
| Entry | (x label) | `_custom_x_label` (StringVar) → `_replot()` | Custom x-axis label | plot | Relocate → Compare tab Plot Settings dialog |
| Button | Auto | `_auto_xlabel()` | Generate default x label | plot | Relocate → Compare tab Plot Settings dialog |
| Checkbutton | TDDFT Y: | `_show_left_ylabel` (BooleanVar) | Enable left y label | plot | Relocate → Compare tab Plot Settings dialog |
| Entry | (left y label) | `_custom_left_ylabel` (StringVar) | Custom left y label text | plot | Relocate → Compare tab Plot Settings dialog |
| Checkbutton | Exp Y: | `_show_right_ylabel` (BooleanVar) | Enable right y label | plot | Relocate → Compare tab Plot Settings dialog |
| Entry | (right y label) | `_custom_right_ylabel` (StringVar) | Custom right y label text | plot | Relocate → Compare tab Plot Settings dialog |

### Collapsible: TDDFT Spectrum Style

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Checkbutton | Sticks | `_show_sticks` (BooleanVar) | Show / hide stick lines | plot | Relocate → unified style dialog, Sticks section (TDDFT node type) |
| Checkbutton | Envelope | `_show_env` (BooleanVar) | Show / hide broadened envelope | plot | Relocate → unified style dialog, Envelope section |
| Checkbutton | Transitions | `_show_trans` (BooleanVar) | Show / hide transition labels | plot | Relocate → unified style dialog, Sticks section |
| Radiobutton | Gaussian | `_broadening` = "Gaussian" | Gaussian broadening function | plot | Relocate → unified style dialog, Broadening section |
| Radiobutton | Lorentzian | `_broadening` = "Lorentzian" | Lorentzian broadening function | plot | Relocate → unified style dialog, Broadening section |
| Entry | (FWHM) | `_fwhm` (DoubleVar) | Broadening linewidth in eV | plot | Relocate → unified style dialog, Broadening section |
| Checkbutton | Total | `_comb_total` (BooleanVar) | Show total combined spectrum | plot | Relocate → unified style dialog, Component visibility section |
| Checkbutton | Elec. Dipole (D²) | `_comb_d2` (BooleanVar) | Show electric dipole component | plot | Relocate → unified style dialog, Component visibility section |
| Checkbutton | Mag. Dipole (m²) | `_comb_m2` (BooleanVar) | Show magnetic dipole component | plot | Relocate → unified style dialog, Component visibility section |
| Checkbutton | Elec. Quad. (Q²) | `_comb_q2` (BooleanVar) | Show electric quadrupole component | plot | Relocate → unified style dialog, Component visibility section |

### Collapsible: Envelope Settings

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Entry + Slider | ΔE (eV) | `_delta_e` / `_de_slider_var` | Energy shift | plot | Relocate → unified style dialog, Energy shift section |
| Entry + Slider | Scale | `_tddft_scale` / `_scale_slider_var` | Intensity multiplier | plot | Relocate → unified style dialog, Energy shift section |
| Checkbutton | Fill area | `_env_fill` (BooleanVar) | Fill under envelope | plot | Relocate → unified style dialog, Envelope section |
| Entry | (fill opacity) | `_env_fill_alpha` (DoubleVar) | Fill transparency | plot | Relocate → unified style dialog, Envelope section |

### Collapsible: Sticks Settings

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Checkbutton | Show tip markers | `_stick_markers` (BooleanVar) | Dots at stick tips | plot | Relocate → unified style dialog, Sticks section |
| Entry | (stick height) | `_stick_height` (DoubleVar) | Stick amplitude multiplier | plot | Relocate → unified style dialog, Sticks section |

### Overlay Panel — per-TDDFT-spectrum row

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Button (swatch) | (colour) | → colour picker | Spectrum colour | node | Supersede → ScanTreeWidget row colour swatch |
| Checkbutton | (label) | `vis` (BooleanVar) | Show / hide spectrum | node | Supersede → ScanTreeWidget row visibility checkbox |
| Button | ✓ / – | `in_legend` (BooleanVar) | Include in legend | node | Supersede → ScanTreeWidget row legend toggle |
| OptionMenu | (linestyle) | `env_linestyle` → `_replot()` | Envelope linestyle | node | Supersede → ScanTreeWidget row linestyle canvas |
| Entry | (linewidth) | `env_linewidth` | Envelope line thickness | node | Supersede → ScanTreeWidget row linewidth; full control in unified style dialog |
| Button | Style… | `_open_tddft_spectrum_style_dialog(idx)` | Open per-spectrum style dialog | node | Supersede → ScanTreeWidget ⚙ button → unified style dialog |
| Button | ✕ | `_remove_tddft_idx(idx)` | Remove spectrum | node | Supersede → ScanTreeWidget ✕ button |

### Overlay Panel — per-experimental-scan row

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Button (swatch) | (colour) | → colour picker | Scan colour | node | Supersede → ScanTreeWidget row colour swatch |
| Checkbutton | (label) | `var` (BooleanVar) | Show / hide scan | node | Supersede → ScanTreeWidget row visibility checkbox |
| Button | ✓ / – | `in_legend` (BooleanVar) | Include in legend | node | Supersede → ScanTreeWidget row legend toggle |
| OptionMenu | (linestyle) | `linestyle` → `_replot()` | Line style | node | Supersede → ScanTreeWidget row linestyle canvas |
| Entry | (linewidth) | `linewidth` | Line thickness | node | Supersede → ScanTreeWidget row; full control in unified style dialog |
| Button | Style… | `_open_exp_style_dialog(idx)` | Open exp style dialog | node | Supersede → ScanTreeWidget ⚙ → unified style dialog |
| Button | ✕ | `_remove_exp_scan_idx(idx)` | Remove scan | node | Supersede → ScanTreeWidget ✕ button |

### Plot Canvas Event Bindings

| Event | Handler | Function | Scope | Disposition |
|-------|---------|----------|-------|-------------|
| button_press_event | `_inset_on_press()` | Start inset drag | plot | Retain → Compare tab |
| motion_notify_event | `_inset_on_motion()` | Drag inset boundary | plot | Retain → Compare tab |
| button_release_event | `_inset_on_release()` | Finalize inset | plot | Retain → Compare tab |
| motion_notify_event | `_on_hover()` | Hover tooltip | plot | Retain → Compare tab |
| button_press_event (legend) | `_legend_on_press()` | Start legend drag | plot | Retain → Compare tab |
| motion_notify_event (legend) | `_legend_on_motion()` | Move legend | plot | Retain → Compare tab |
| button_release_event (legend) | `_legend_on_release()` | Finalize legend position | plot | Retain → Compare tab |

---

## Dialogs spawned from the TDDFT Tab

### Per-spectrum TDDFT Style Dialog

> Superseded by the unified style dialog (CS-05, COMPONENTS.md).
> Parameters below map to conditional sections of the unified dialog.

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Checkbutton | Sticks | `show_sticks` | Show sticks | node | Supersede → unified style dialog, Sticks section |
| Checkbutton | Envelope | `show_env` | Show envelope | node | Supersede → unified style dialog, Envelope section |
| Checkbutton | Transitions | `show_trans` | Show transitions | node | Supersede → unified style dialog, Sticks section |
| Radiobutton | Gaussian / Lorentzian | `broadening` | Broadening type | node | Supersede → unified style dialog, Broadening section |
| Entry + Slider | FWHM | `fwhm` | Linewidth | node | Supersede → unified style dialog, Broadening section |
| Checkbutton | (components) | `comb_*` | Component visibility | node | Supersede → unified style dialog, Component visibility section |
| Checkbutton | Fill | `env_fill` | Fill under envelope | node | Supersede → unified style dialog, Envelope section |
| Entry | (fill α) | `env_fill_alpha` | Fill transparency | node | Supersede → unified style dialog, Envelope section |
| Checkbutton | Markers | `stick_markers` | Stick tip dots | node | Supersede → unified style dialog, Sticks section |
| Entry | (stick height) | `stick_height` | Stick amplitude scale | node | Supersede → unified style dialog, Sticks section |
| Button | Apply | `_do_apply()` | Apply to this spectrum | node | Supersede → unified style dialog Apply button |
| Button | Apply to ALL TDDFT | `_apply_to_all()` | Apply to all TDDFT spectra | all | Supersede → unified style dialog ∀ Apply to All button |
| Button | Set as Default | `_save_as_default()` | Persist as default style | app | Supersede → unified style dialog Save button |
| Button | Cancel | `win.destroy()` | Discard changes | provisional | Supersede → unified style dialog Cancel button |

### Experimental Scan Style Dialog

> Superseded by the unified style dialog (CS-05). Parameters map to
> the universal section.

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Radiobutton | Solid / Dashed / Dotted / Dash-dot | `ls_var` | Line style | node | Supersede → unified style dialog, universal section |
| Button (swatch) | (colour) | `_pick_color()` | Open colour chooser | node | Supersede → unified style dialog, universal section |
| Button | Reset to auto | `_reset_color()` | Restore default colour | node | Supersede → unified style dialog Reset button |
| Scale | Line width | `lw_var` (0.5–5.0) | Line thickness | node | Supersede → unified style dialog, universal section |
| Checkbutton | Fill | `fill_var` | Fill under curve | node | Supersede → unified style dialog, universal section |
| Scale | Fill opacity | `alpha_var` (0–0.5) | Fill transparency | node | Supersede → unified style dialog, universal section |
| Button | Apply | `_do_apply()` | Apply to this scan | node | Supersede → unified style dialog Apply button |
| Button | Apply to ALL Exp. | `_apply_to_all()` | Apply to all exp scans | all | Supersede → unified style dialog ∀ Apply to All button |
| Button | Set as Default | `_save_as_default()` | Persist as default style | app | Supersede → unified style dialog Save button |
| Button | Cancel | `win.destroy()` | Discard changes | provisional | Supersede → unified style dialog Cancel button |

### Font Dialog

> Superseded by the Plot Settings dialog (CS-06, COMPONENTS.md), Fonts section.

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Spinbox + Checkbutton | Title size / bold | `_font_title_size`, `_font_title_bold` | Title font | plot | Supersede → Plot Settings dialog, Fonts section |
| Spinbox + Checkbutton | X-label size / bold | `_font_xlabel_size`, `_font_xlabel_bold` | X-axis label font | plot | Supersede → Plot Settings dialog, Fonts section |
| Spinbox + Checkbutton | Y-label size / bold | `_font_ylabel_size`, `_font_ylabel_bold` | Y-axis label font | plot | Supersede → Plot Settings dialog, Fonts section |
| Button | Save as Default | `_save_as_default()` | Persist settings | app | Supersede → Plot Settings dialog Save as Default |
| Button | Reset Defaults | `_reset_all()` | Load saved defaults | app | Supersede → Plot Settings dialog Reset Defaults |
| Button | Factory Reset | `_factory_reset()` | Hardcoded defaults | app | Supersede → Plot Settings dialog Factory Reset |
| Button | Close | `win.destroy()` | Close dialog | provisional | Supersede → Plot Settings dialog Close |

### Legend Labels Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Entry (per spectrum) | (label) | custom entry | Override spectrum legend label | node | Supersede → DataNode label (editable in-place in ScanTreeWidget) |
| Checkbutton (per spectrum) | Show in legend | (BooleanVar) | Include / exclude from legend | node | Supersede → ScanTreeWidget row legend toggle |
| Checkbutton | Show legend on plot | `_show_legend` (BooleanVar) | Display legend box | plot | Relocate → Plot Settings dialog, Legend section |
| Button | Apply | — | Apply changes | plot | Supersede |
| Button | Cancel | `win.destroy()` | Discard | provisional | Supersede |

### Inset Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Entry | X min / X max | `xlo_v`, `xhi_v` | Inset x range | plot | Retain → Compare tab |
| Entry | Y min / Y max | `ylo_v`, `yhi_v` | Inset y range (optional) | plot | Retain → Compare tab |
| Scale + Entry | Width % | `wv` | Inset width | plot | Retain → Compare tab |
| Scale + Entry | Height % | `hv` | Inset height | plot | Retain → Compare tab |
| Button | Apply | — | Create / update inset | plot | Retain → Compare tab |
| Button | Remove Inset | — | Delete inset | plot | Retain → Compare tab |
| Button | Cancel | `win.destroy()` | Discard | provisional | Retain → Compare tab |

### Pop-Out Window

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Checkbutton | Auto-refresh | `_popout_refresh_auto` (BooleanVar) | Auto-update on parent change | plot | Retain → Compare tab |
| Button | Refresh Now | `_do_refresh()` | Manual update | plot | Retain → Compare tab |
| Button | Save Figure… | `_save_popout()` | Save pop-out figure | plot | Retain → Compare tab |
| Button | Close | `_on_close()` | Close window | provisional | Retain → Compare tab |

---

## 🔬 XANES Tab — `xas_analysis_tab.py`

> **Disposition summary:** Refactored in place. The left panel gains an
> engine selector (Larch / bXAS). The scan list is replaced by
> ScanTreeWidget. Auto-run is removed. All operations produce provisional
> nodes. "Add to Overlay" becomes "Send to Compare."

### Top Toolbar

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Combobox | (scan list) | `_scan_var` → `_auto_fill_e0()` | Select active scan | node | Supersede → ScanTreeWidget selection |
| Button | Refresh Scans | `refresh_scan_list()` | Reload scan list | all | Retire — reactive graph eliminates need for manual refresh |
| Button | ▶ Run Analysis | `_run()` | Compute XANES for selected scan | node | Retain → moved to bottom of left panel; creates provisional node |
| Button | + Add to Overlay | `_add_overlay()` | Push result to TDDFT tab | node | Rename → "Send to Compare"; available on committed nodes only |
| Button | Clear Overlay | `_clear_overlay()` | Remove all from overlay | all | Retire — Compare tab manages its own node list |
| Button | ✓ Apply norm to ALL | `_apply_norm_all()` | Apply norm params to all scans | all | Retain — creates provisional nodes for all loaded XANES nodes |
| Button | ∑ Average Scans… | `_show_average_dialog()` | Open averaging dialog | all | Retain — becomes multi-input operation node; see OQ-004 |
| Label | (status) | `_status_lbl` | Status message | — | Retain |

### Collapsible: Loaded Scans

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Button | All | `_show_all_scans()` | Check all scans | all | Supersede → ScanTreeWidget bulk visibility control |
| Button | None | `_hide_all_scans()` | Uncheck all scans | all | Supersede → ScanTreeWidget bulk visibility control |
| Label (swatch, per row) | (colour) | — | Scan colour indicator | node | Supersede → ScanTreeWidget row colour swatch |
| Checkbutton (per row) | — | `_scan_vis_vars[label]` | Include scan in analysis | node | Supersede → ScanTreeWidget row visibility checkbox |
| Label (per row, clickable) | (scan name) | `_select_scan(label)` | Click to select and run | node | Supersede → ScanTreeWidget row selection |

### Collapsible: Visualization

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Checkbutton | Plot μ(E) | `_show_mu` (BooleanVar) | Show raw absorption | plot | Relocate → XANES left panel, Visualisation section |
| Checkbutton | Plot norm | `_show_norm` (BooleanVar) | Show normalized spectrum | plot | Relocate → XANES left panel, Visualisation section |
| Checkbutton | Plot pre-edge | `_show_pre_edge` (BooleanVar) | Show pre-edge fit line | plot | Relocate → XANES left panel, Visualisation section |
| Checkbutton | Plot post-edge | `_show_post_edge` (BooleanVar) | Show post-edge line | plot | Relocate → XANES left panel, Visualisation section |
| Checkbutton | Plot χ(k) | `_show_chi` (BooleanVar) | Show EXAFS oscillations | plot | Relocate → XANES left panel, Visualisation section |
| Combobox | Location | `_legend_loc_var` | Legend position | plot | Relocate → Plot Settings dialog, Legend section |
| Spinbox | Font size | `_legend_size_var` | Legend font size | plot | Relocate → Plot Settings dialog, Fonts section |
| Combobox | Style | `_style_var` | Seaborn plot style | plot | Relocate → Plot Settings dialog, Appearance section |
| Combobox | Context | `_context_var` | Seaborn context | plot | Relocate → Plot Settings dialog, Appearance section |

### Collapsible: Parameters

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Spinbox | E0 (eV) | `_e0_var` | Absorption edge energy | node | Retain → XANES left panel, Larch engine parameters |
| Spinbox | pre1 / pre2 (eV) | `_pre1_var`, `_pre2_var` | Pre-edge region bounds | node | Retain → XANES left panel, Larch engine parameters |
| Spinbox | nor1 / nor2 (eV) | `_nor1_var`, `_nor2_var` | Post-edge normalization region | node | Retain → XANES left panel, Larch engine parameters |
| Radiobutton | Norm order 1 / 2 | `_nnor_var` | Normalization polynomial order | node | Retain → XANES left panel, Larch engine parameters |
| Spinbox | rbkg (Å) | `_rbkg_var` | Background removal range | node | Retain → XANES left panel, Larch engine parameters |
| Radiobutton | k-weight 1 / 2 / 3 | `_kw_var` | k-weighting exponent | node | Retain → XANES left panel, Larch engine parameters |
| Entry | X / Y min / max | `_xanes_x/ymin/max_var` | Manual plot limits | plot | Relocate → XANES tab top bar axis limit entries |
| Button | Apply | — | Set manual limits | plot | Relocate → XANES tab top bar |
| Button | From Plot | `_capture_from_plot()` | Read current plot limits | plot | Relocate → XANES tab top bar |
| Button | Auto | `_auto_limits()` | Reset to auto | plot | Relocate → XANES tab top bar Auto button |
| Button | Auto Deglitch | `_deglitch()` | Remove spikes interactively | node | Retain → XANES left panel, Processing section; creates provisional DEGLITCHED node |
| Button | Reset Scan | `_reset_scan()` | Restore original data | node | Retain → XANES left panel; meaning: discard all provisional nodes back to last committed |
| Button | Smooth Scan | `_smooth_scan()` | Apply smoothing filter | node | Retain → XANES left panel, Processing section; creates provisional SMOOTHED node |
| Button | Shift Energy | `_shift_energy_dialog()` | Open energy shift dialog | node | Retain → XANES left panel, Processing section; creates provisional SHIFTED node |
| Checkbutton | Show FT window | `_show_ft_window` | Highlight FT window on χ(k) plot | plot | Retain → XANES left panel, Visualisation section |
| Button | ★ Set Norm as Default | `_set_norm_default()` | Save normalization params as default | app | Retain → XANES left panel; saves Larch parameter set as app-level default |
| Button | ▶ Run Analysis | `_run()` | Compute analysis | node | Retain → bottom of XANES left panel; creates provisional node |

---

## Dialogs spawned from the XANES Tab

### XAS Scan Style Dialog

> Superseded by the unified style dialog (CS-05). Note: marker controls
> (circle/square/diamond) in this dialog are not present in the UV/Vis
> style dialog. The unified style dialog must include a Markers section
> shown conditionally for XANES and EXAFS node types.

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Radiobutton | Solid / Dashed / Dotted / Dash-dot | `ls_var` | Line style | node | Supersede → unified style dialog, universal section |
| Button (swatch) | (colour) | `_pick_color()` | Open colour chooser | node | Supersede → unified style dialog, universal section |
| Button | Auto | `_reset_color()` | Restore default colour | node | Supersede → unified style dialog Reset button |
| Scale | Line width | `lw_var` | Line thickness | node | Supersede → unified style dialog, universal section |
| Scale | Opacity | `alpha_var` | Line transparency | node | Supersede → unified style dialog, universal section |
| Radiobutton | None / Circle / Square / Diamond | `marker_var` | Marker shape | node | Supersede → unified style dialog, Markers section |
| Spinbox | (marker size) | `ms_var` | Marker size (2–12 px) | node | Supersede → unified style dialog, Markers section |
| Button | Apply | — | Apply to this scan | node | Supersede → unified style dialog Apply button |
| Button | Apply to All Scans | — | Apply to all XAS scans | all | Supersede → unified style dialog ∀ Apply to All |
| Button | Cancel | `win.destroy()` | Discard | provisional | Supersede → unified style dialog Cancel |

### Average Scans Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Checkbutton (per row) | (scan name) | `var` (BooleanVar) | Include in average | node | Retain — becomes multi-input node builder; see OQ-004 |
| Checkbutton | Normalise together | `norm_together_var` | Single norm on averaged result | all | Retain — parameter of the AVERAGE operation node |
| Entry | Output label | `out_label_var` | Name for averaged spectrum | provisional | Retain — becomes the DataNode label |
| Button | ∑ Average & Add | `do_average()` | Compute and add to plot | all | Retain — creates provisional AVERAGED node |
| Button | Cancel | `win.destroy()` | Abort | provisional | Retain |

### Deglitch Mode (Interactive canvas)

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Button | Remove | `_deglitch_mode = "remove"` | Remove spike at click | node | Retain — each click creates a provisional DEGLITCHED node |
| Button | Average | `_deglitch_mode = "average"` | Replace with neighbour average | node | Retain |
| Button | Interpolate | `_deglitch_mode = "interp"` | Interpolate across spike | node | Retain |
| Button | Undo | `_deglitch_undo_btn` | Undo last deglitch operation | node | Retain — meaning: discard last provisional DEGLITCHED node |
| Canvas event | button_press_event | `_on_plot_click()` | Apply selected deglitch at click location | node | Retain |

---

## ⚗ EXAFS Tab — `exafs_analysis_tab.py`

> **Disposition summary:** Refactored in place. The FEFF sub-tab is
> extracted entirely to the FEFF Workspace window and Simulate tab —
> this is the largest single relocation task in the redesign. The
> remaining EXAFS controls follow the same pattern as the XANES tab.

### Top Toolbar

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Combobox | (scan list) | `_scan_var` → `_auto_fill_e0()` | Select active scan | node | Supersede → ScanTreeWidget selection |
| Button | Refresh Scans | `refresh_scan_list()` | Reload scan list | all | Retire — reactive graph eliminates need |
| Button | Run EXAFS | `_run()` | Compute EXAFS | node | Retain → bottom of left panel; creates provisional EXAFS node |
| Button | Update Views | `_redraw()` | Refresh plots | all | Rename → "Redraw" — re-renders current node without recompute |
| Button | + Add to Overlay | `_add_overlay()` | Push to TDDFT tab | node | Rename → "Send to Compare"; committed nodes only |
| Button | Clear Overlay | `_clear_overlay()` | Clear overlay list | all | Retire — Compare tab manages its own list |
| Label | (status) | `_status_lbl` | Status message | — | Retain |

### Parameters Panel

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Spinbox | E0 / pre1 / pre2 / nor1 / nor2 | `_e0/pre/nor_vars` | Background / normalization bounds | node | Retain → EXAFS left panel, Larch engine parameters |
| Spinbox | rbkg (Å) | `_rbkg_var` | Background removal range | node | Retain → EXAFS left panel, Larch engine parameters |
| Spinbox | kmin bkg | `_kmin_bkg_var` | Min k for background fit | node | Retain → EXAFS left panel, Larch engine parameters |
| Radiobutton | Norm order 1 / 2 | `_nnorm_var` | Normalization order | node | Retain → EXAFS left panel, Larch engine parameters |
| Spinbox | q min / q max (Å⁻¹) | `_qmin_var`, `_qmax_var` | k-range for EXAFS window | node | Retain → EXAFS left panel, Q Space section |
| Spinbox | dq taper | `_dq_var` | Window taper width | node | Retain → EXAFS left panel, Q Space section |
| Radiobutton | q-weight 1 / 2 / 3 | `_qweight_var` | k-weighting exponent | node | Retain → EXAFS left panel, Q Space section |
| Combobox | q window | `_qwin_var` | Window function (Hanning, Sine, Welch, Parzen) | node | Retain → EXAFS left panel, Q Space section |
| Button | q from Plot | `_capture_q_window_from_plot()` | Read q limits from plot | plot | Retain → EXAFS left panel |
| Button | Default q | `_reset_q_window()` | Reset q defaults | node | Retain → EXAFS left panel |
| Spinbox | R min / R max (Å) | `_rmin_var`, `_rmax_var` | R range for inverse FT | node | Retain → EXAFS left panel, R Space section |
| Spinbox | dR taper | `_dr_var` | R window taper | node | Retain → EXAFS left panel, R Space section |
| Entry | R display | `_rdisplay_var` | Max R shown on plot | plot | Retain → EXAFS left panel, R Space section |
| Combobox | R window | `_rwin_var` | R window function | node | Retain → EXAFS left panel, R Space section |
| Button | R from Plot | `_capture_r_window_from_plot()` | Read R limits from plot | plot | Retain → EXAFS left panel |
| Button | Default R | `_reset_r_window()` | Reset R defaults | node | Retain → EXAFS left panel |
| Combobox | Style / Context | `_style_var`, `_context_var` | Seaborn plot style | plot | Relocate → Plot Settings dialog, Appearance section |
| Checkbutton | Label k-space as q | `_use_q_label_var` | Use "q" instead of "k" | plot | Retain → EXAFS left panel, Display section |
| Checkbutton | Show q window | `_show_q_window_var` | Highlight q window on plot | plot | Retain → EXAFS left panel, Display section |
| Checkbutton | Show R window | `_show_r_window_var` | Highlight R window on plot | plot | Retain → EXAFS left panel, Display section |
| Checkbutton | Show FEFF markers | `_show_feff_markers_var` | FEFF path reference lines | plot | Retain → EXAFS left panel, Display section |
| Button | Run / Refresh EXAFS | `_run()` | Compute or update | node | Retain → bottom of left panel; creates provisional EXAFS node |
| Button | Redraw Windows Only | `_redraw()` | Refresh without recompute | all | Retain → renamed "Redraw"; re-renders current node only |

### Collapsible: Loaded Scans

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Button | All / None | `_show/hide_all_scans()` | Select / deselect all | all | Supersede → ScanTreeWidget bulk visibility |
| Checkbutton (per row) | — | `_scan_vis_vars[label]` | Include scan | node | Supersede → ScanTreeWidget row visibility |
| Label (per row, clickable) | (scan name) | `_select_scan(label)` | Select and run | node | Supersede → ScanTreeWidget row selection |

### FEFF Sub-tab

> **Extract entirely to FEFF Workspace window (`feff_workspace.py`)
> and Simulate tab (`simulate_tab.py`).** This is the largest single
> relocation task in the redesign. The existing implementation should
> be rehoused, not rewritten. See COMPONENTS.md CS-09 for the FEFF
> Workspace specification.

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Entry + Button | Workdir | `_feff_dir_var` → `_browse_feff_dir()` | FEFF working directory | app | Extract → FEFF Workspace window |
| Button | Load Paths | `_load_feff_paths()` | Read feff*.dat files | all | Extract → FEFF Workspace window |
| Entry + Button | Executable | `_feff_exe_var` → `_browse_feff_exe()` | FEFF executable path | app | Extract → FEFF Workspace window |
| Button | Run FEFF | `_run_feff()` | Execute FEFF | app | Extract → FEFF Workspace window |
| Entry + Button | XYZ file | `_xyz_path_var` → `_browse_xyz_file()` | Load structure file | node | Extract → FEFF Workspace window |
| Button | Load XYZ | `_load_xyz_structure()` | Parse XYZ | node | Extract → FEFF Workspace window |
| Entry | Base name | `_bundle_base_var` | Output file base name | provisional | Extract → FEFF Workspace window |
| Entry | Padding (Å) | `_xyz_padding_var` | Padding in CIF export | node | Extract → FEFF Workspace window |
| Checkbutton | Force cubic cell | `_xyz_cubic_var` | Force cubic cell | node | Extract → FEFF Workspace window |
| Entry | Absorber # | `_xyz_absorber_var` | Absorbing atom index | node | Extract → FEFF Workspace window |
| Combobox | Edge | `_xyz_edge_var` | X-ray edge (K, L1, L2, L3) | node | Extract → FEFF Workspace window |
| Combobox | Spectrum | `_xyz_spectrum_var` | EXAFS or XANES mode | node | Extract → FEFF Workspace window |
| Entry | KMESH | `_xyz_kmesh_var` | k-mesh density | node | Extract → FEFF Workspace window |
| Entry | Equivalence | `_xyz_equiv_var` | Atom equivalence criterion | node | Extract → FEFF Workspace window |
| Button | Write FEFF Bundle | `_write_xyz_feff_bundle()` | Export CIF + feff.inp | node | Extract → FEFF Workspace window |
| Treeview | (path list) | `_feff_tree` → `_on_feff_selection()` | FEFF path table (index, reff, degen, nleg) | node | Extract → FEFF Workspace window |
| Canvas (preview) | (plot) | `_canvas_feff` | FEFF path amplitude plot | node | Extract → FEFF Workspace window |
| Text (read-only) | (log) | `_feff_log` | FEFF execution output | app | Extract → FEFF Workspace window |

---

## 🌈 UV/Vis Tab — `uvvis_tab.py`

> **Disposition summary:** This tab is the reference implementation for
> the new architecture. Its sidebar is the template for ScanTreeWidget.
> Its style dialog is the template for the unified style dialog. It
> requires the least structural change of all four tabs. Primary changes:
> operations become provisional nodes; style dialog is replaced by the
> unified dialog; "Add to TDDFT Overlay" becomes "Send to Compare."

### Top Toolbar

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Button | 📂 Load File… | `_load_files()` | Open file browser | all | Retain |
| Radiobutton | nm / cm⁻¹ / eV | `_x_unit` → `_on_unit_change()` | X-axis unit; converts sticky limits | plot | Retain |
| Radiobutton | Abs / %T | `_y_unit` → `_redraw()` | Y-axis quantity | plot | Retain |
| Combobox | none / peak / area | `_norm_mode` → `_redraw()` | Normalization mode | plot | Retain — normalisation now creates a provisional NORMALISED node |
| Checkbutton | λ(nm) axis | `_show_nm_axis` → `_redraw()` | Secondary nm axis in cm⁻¹ mode | plot | Retain |
| ~~Button~~ | ~~+ Add to TDDFT Overlay~~ | — | — | — | ✅ Removed Phase 4n (CS-27): replaced by per-row → icon on each ScanTreeWidget row, wired to `_send_node_to_compare(node_id)` |
| Label | (status) | `_status_lbl` | Status message | — | Retain |

### Axis Limits Bar

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Entry | X lo / X hi | `_xlim_lo`, `_xlim_hi` → `_redraw()` | X-axis bounds (blank = auto) | plot | Retain |
| Button | Auto X | `_auto_x()` | Reset x to auto | plot | Retain |
| Entry | Y lo / Y hi | `_ylim_lo`, `_ylim_hi` → `_redraw()` | Y-axis bounds | plot | Retain |
| Button | Auto Y | `_auto_y()` | Reset y to auto | plot | Retain |

### Loaded Spectra Sidebar — per-scan row

> **This sidebar is the reference implementation for ScanTreeWidget.**
> These controls carry forward directly into the ScanTreeWidget row.
> The ScanTreeWidget adds: state indicator, history indicator,
> in-place label editing, sweep group representation.

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Button (swatch) | (colour) | `_pick()` → colorchooser | Change scan colour | node | Retain → ScanTreeWidget row colour swatch (reference) |
| Checkbutton | (label) | `vis` (BooleanVar) → `_redraw()` | Show / hide scan | node | Retain → ScanTreeWidget row visibility checkbox (reference) |
| Button | ✓ / – | `in_legend` (BooleanVar) → `_redraw()` | Include in legend | node | Retain → ScanTreeWidget row legend toggle (reference) |
| Canvas (linestyle) | (drawn line) | click → `_cycle()` | Cycle linestyle; draws exact linewidth in scan colour | node | Retain → ScanTreeWidget row linestyle canvas (reference) |
| Entry | (linewidth) | `style["linewidth"]` → `_redraw()` | Line thickness (exact float) | node | Retain → ScanTreeWidget row (reference) |
| Checkbutton | (fill) | `style["fill"]` → `_redraw()` | Fill under curve | node | Retain → ScanTreeWidget row (reference) |
| Button | ⚙ | `_open_style_dialog(idx)` | Open full style dialog | node | Retain → ScanTreeWidget ⚙ button → unified style dialog |
| Button | ✕ | `_remove_entry(idx)` | Delete scan | node | Retain → ScanTreeWidget ✕ button; semantics updated (discard node) |

### Plot Canvas Event Bindings

| Event | Handler | Function | Scope | Disposition |
|-------|---------|----------|-------|-------------|
| button_release_event | `_on_mpl_interact()` | Capture pan/zoom limits into entry fields | plot | Retain |
| scroll_event | `_on_mpl_interact()` | Capture scroll-zoom limits | plot | Retain |

---

## Dialogs spawned from the UV/Vis Tab

### Spectrum Style Dialog

> **This dialog is the reference implementation for the unified style
> dialog (CS-05, COMPONENTS.md).** Its layout, the ∀ per-parameter
> button pattern, and the bottom button bar are carried forward
> directly. The unified dialog extends this with conditional sections
> for other node types.

| Widget | Label / Text | Variable / Callback | Function | Scope | Disposition |
|--------|-------------|---------------------|----------|-------|-------------|
| Radiobutton | Solid / Dashed / Dotted / Dash-dot | `ls_var` | Line style | node | Retain → unified style dialog universal section (reference) |
| Button ∀ | (apply to all) | `_push_to_all("linestyle", ls_var.get)` | Apply linestyle to all | all | Retain → unified style dialog ∀ button pattern (reference) |
| Scale | Line width (0.5–5 pt) | `lw_var` | Line thickness | node | Retain → unified style dialog universal section (reference) |
| Button ∀ | (apply to all) | `_push_to_all("linewidth", lw_var.get)` | Apply linewidth to all | all | Retain → unified style dialog ∀ button pattern (reference) |
| Scale | Line opacity (0–1) | `alpha_var` | Line transparency | node | Retain → unified style dialog universal section (reference) |
| Button ∀ | (apply to all) | `_push_to_all("alpha", alpha_var.get)` | Apply opacity to all | all | Retain → unified style dialog ∀ button pattern (reference) |
| Button (swatch) | (colour) | `_pick_color()` | Open colour chooser | node | Retain → unified style dialog universal section (reference) |
| Button | Reset | `_reset_color()` | Restore palette colour | node | Retain → unified style dialog Reset button (reference) |
| Button ∀ | (apply to all) | `_push_to_all("color", …)` | Apply colour to all | all | Retain → unified style dialog ∀ button pattern (reference) |
| Checkbutton | Show fill under curve | `fill_var` | Fill under curve | node | Retain → unified style dialog universal section (reference) |
| Button ∀ | (apply to all) | `_push_to_all("fill", fill_var.get)` | Apply fill to all | all | Retain → unified style dialog ∀ button pattern (reference) |
| Scale | Fill opacity (0–0.5) | `fill_alpha_var` | Fill transparency | node | Retain → unified style dialog universal section (reference) |
| Button ∀ | (apply to all) | `_push_to_all("fill_alpha", …)` | Apply fill opacity to all | all | Retain → unified style dialog ∀ button pattern (reference) |
| Button | Apply | `_do_apply()` | Apply to this scan, stay open | node | Retain → unified style dialog Apply button (reference) |
| Button | ∀ Apply to All | `_do_apply_all()` | Apply all (except colour) to all | all | Retain → unified style dialog ∀ Apply to All button (reference) |
| Button | Save | `_do_save()` | Apply and close | node | Retain → unified style dialog Save button (reference) |
| Button | Cancel | `_do_cancel()` | Revert and close | provisional | Retain → unified style dialog Cancel button (reference) |

---

*Document version: 2.0 — April 2026*
*Updated from v1.0: added preamble, disposition column, updated scope
vocabulary (scan → node), added new keyboard shortcuts, flagged
reference implementations, marked OQ-001 and OQ-004 inline.*
