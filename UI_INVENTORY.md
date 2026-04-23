# Ptarmigan — UI Interaction Inventory

Complete accounting of every user-facing control in the application.
Use this as the basis for UI audit and redesign decisions.

**Columns:**
- **Widget** — Tkinter widget type
- **Label / Text** — what the user sees
- **Variable / Callback** — what it is wired to in code
- **Function** — what it does
- **Scope** — `scan` (one item), `all` (every loaded item), `plot` (the axes/figure), `app` (global/persistent)

---

## Above the Tabs — `binah.py`

### Menu Bar

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Command | New Project | `_new_project()` | Clear all state, start fresh | app |
| Command | Open Project… | `_open_project()` | Load `.otproj` file | app |
| Command | Save Project | `_save_project()` | Save to current path | app |
| Command | Save Project As… | `_save_project_as()` | Save to new path | app |
| Cascade | Recent Projects | `_recent_menu` | Dynamic submenu of recent files | app |
| Command | Open .out File… | `_open_file()` | Load single ORCA output file | scan |
| Command | Open Multiple Files… | `_open_multiple()` | Load multiple ORCA files | all |
| Command | Load Experimental Data… | `_load_experimental()` | Load XAS scan data | scan |
| Command | Load SGM Stack… | `_load_sgm_stack()` | Open SGM loader window | scan |
| Command | Exit | `destroy()` | Quit application | app |
| Command | FEFF Setup / Update… | `_launch_feff_setup()` | Open FEFF installation dialog | app |
| Command | About | `_show_about()` | Show about box | app |

### Keyboard Shortcuts

| Shortcut | Callback | Function | Scope |
|----------|----------|----------|-------|
| Ctrl+N | `_new_project()` | New project | app |
| Ctrl+O | `_open_file()` | Open ORCA file | scan |
| Ctrl+Shift+O | `_open_project()` | Open project | app |
| Ctrl+S | `_save_project()` | Save project | app |
| Ctrl+Shift+S | `_save_project_as()` | Save as | app |
| Ctrl+E | `_load_experimental()` | Load experimental data | scan |

### Top Toolbar

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Button | « | `_toggle_sidebar()` | Hide / show left file-list sidebar | app |
| Button | Open File | `_open_file()` | Load single ORCA file | scan |
| Button | Reload | `_reload_file()` | Reload current file | scan |
| Combobox | (section list) | `_section_var` → `_on_section_change()` | Select TDDFT section from current file | scan |
| Label | (filename) | `_file_label` | Display current loaded filename | scan |

### Left Sidebar (File List)

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Listbox | (loaded files) | `_file_listbox` → `_on_file_select()` | Switch to selected ORCA file | scan |
| Button | + Add to Overlay | `_add_current_to_overlay()` | Add current section to overlay | scan |
| Button | Load Exp. Data… | `_load_experimental()` | Load XAS scan data | scan |
| Text (read-only) | (metadata) | `_info_text` | Display spectrum metadata | scan |

### Status Bar

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Label | (status text) | `_status` (StringVar) | Application status messages | app |

---

## Dialogs spawned from `binah.py`

### SXRMB Import Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Radiobutton | TEY only | `_signal_var` = "tey" | Load TEY channel | scan |
| Radiobutton | Fluorescence only | `_signal_var` = "fluor" | Load fluorescence channel | scan |
| Radiobutton | Both | `_signal_var` = "both" | Load both channels | all |
| Button | Load | `do_load()` | Parse and load file | scan |
| Button | Cancel | `win.destroy()` | Abort | — |

### BioXAS .dat Options Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Radiobutton | Fluorescence | `mode_var` = "fluorescence" | Fluorescence mode | scan |
| Radiobutton | Transmission | `mode_var` = "transmission" | Transmission mode | scan |
| Checkbutton | Apply Athena-style normalization | `norm_var` (BooleanVar) | Enable normalization on load | scan |
| Button | Load | `do_load()` | Parse and load | scan |
| Button | Cancel | `win.destroy()` | Abort | — |

### Athena .prj Scan Selection Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Listbox | (scan list) | `lb` → `do_load()` | Select scans to load from .prj | all |
| Button | Load Selected | `do_load()` | Load checked scans | all |
| Button | Select All | `lb.selection_set(0, END)` | Select all scans | all |
| Button | Cancel | `win.destroy()` | Abort | — |

### Replace-or-Add Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Button | Replace existing | `_choose("replace")` | Replace TDDFT with new file | scan |
| Button | Add as overlay | `_choose("add")` | Add as overlay instead | scan |
| Button | Cancel | `_choose("cancel")` | Abort | — |

### FEFF Setup Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Text (read-only) | (log) | `_feff_setup_log` | Installation progress log | app |
| Label | (status) | `_feff_setup_status` | Status message | app |
| Button | Close | `win.destroy()` | Close (enabled when done) | app |

---

## 📈 TDDFT Tab — `plot_widget.py`

### Controls Bar

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Radiobutton | nm | `_x_unit` = "nm" | X-axis in nanometers | plot |
| Radiobutton | cm⁻¹ | `_x_unit` = "cm-1" | X-axis in wavenumber | plot |
| Radiobutton | eV | `_x_unit` = "eV" | X-axis in electron volts | plot |
| Checkbutton | λ(nm) axis | `_show_nm_axis` (BooleanVar) | Secondary nm axis in cm⁻¹ mode | plot |
| Entry | (nm step) | `_nm_step` (StringVar) | Manual tick spacing for nm axis | plot |
| Checkbutton | Normalise | `_normalise` (BooleanVar) | Normalize TDDFT spectra | plot |
| Checkbutton | Grid | `_show_grid` (BooleanVar) | Show / hide plot grid | plot |
| Button | Plot BG… | `_open_plot_bg_dialog()` | Change plot background colour | plot |
| Button | Fonts… | `_open_font_dialog()` | Open font settings dialog | plot |
| Button | ⁝ Pop Out | `_pop_out_graph()` | Open graph in separate window | plot |
| Button | Export CSV | `_export_csv()` | Export plot data to CSV | plot |
| Button | Save Fig | `_save_figure()` | Save figure as image | plot |

### Axis Limits Bar

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Entry | X lo | `_xlim_lo` (StringVar) → `_replot()` | X-axis lower bound (blank = auto) | plot |
| Entry | X hi | `_xlim_hi` (StringVar) → `_replot()` | X-axis upper bound | plot |
| Button | Auto X | `_auto_x()` | Reset x to auto | plot |
| Entry | Y lo (TDDFT) | `_ylim_lo` (StringVar) → `_replot()` | TDDFT y lower bound | plot |
| Entry | Y hi (TDDFT) | `_ylim_hi` (StringVar) → `_replot()` | TDDFT y upper bound | plot |
| Button | Auto (TDDFT) | `_auto_y()` | Reset TDDFT y to auto | plot |
| Entry | Y lo (Exp) | `_ylim_exp_lo` (StringVar) → `_replot()` | Experimental y lower bound | plot |
| Entry | Y hi (Exp) | `_ylim_exp_hi` (StringVar) → `_replot()` | Experimental y upper bound | plot |
| Button | Auto (Exp) | `_auto_y_exp()` | Reset experimental y to auto | plot |
| Radiobutton | Left | `_tddft_on_left` = "left" | TDDFT on left y-axis | plot |
| Radiobutton | Right | `_tddft_on_left` = "right" | TDDFT on right y-axis | plot |
| Radiobutton | In | `_tick_direction` = "in" | Inward ticks | plot |
| Radiobutton | Out | `_tick_direction` = "out" | Outward ticks | plot |
| Radiobutton | Both | `_tick_direction` = "both" | Both-side ticks | plot |

### Title & Label Bar

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Entry | (title) | `_custom_title` (StringVar) → `_replot()` | Custom plot title | plot |
| Button | Auto | `_auto_title()` | Generate default title | plot |
| Button | None | `_clear_title()` | Remove title | plot |
| Entry | (x label) | `_custom_x_label` (StringVar) → `_replot()` | Custom x-axis label | plot |
| Button | Auto | `_auto_xlabel()` | Generate default x label | plot |
| Checkbutton | TDDFT Y: | `_show_left_ylabel` (BooleanVar) | Enable left y label | plot |
| Entry | (left y label) | `_custom_left_ylabel` (StringVar) | Custom left y label text | plot |
| Checkbutton | Exp Y: | `_show_right_ylabel` (BooleanVar) | Enable right y label | plot |
| Entry | (right y label) | `_custom_right_ylabel` (StringVar) | Custom right y label text | plot |

### Collapsible: TDDFT Spectrum Style

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Checkbutton | Sticks | `_show_sticks` (BooleanVar) | Show / hide stick lines | plot |
| Checkbutton | Envelope | `_show_env` (BooleanVar) | Show / hide broadened envelope | plot |
| Checkbutton | Transitions | `_show_trans` (BooleanVar) | Show / hide transition labels | plot |
| Radiobutton | Gaussian | `_broadening` = "Gaussian" | Gaussian broadening function | plot |
| Radiobutton | Lorentzian | `_broadening` = "Lorentzian" | Lorentzian broadening function | plot |
| Entry | (FWHM) | `_fwhm` (DoubleVar) | Broadening linewidth in eV | plot |
| Checkbutton | Total | `_comb_total` (BooleanVar) | Show total combined spectrum | plot |
| Checkbutton | Elec. Dipole (D²) | `_comb_d2` (BooleanVar) | Show electric dipole component | plot |
| Checkbutton | Mag. Dipole (m²) | `_comb_m2` (BooleanVar) | Show magnetic dipole component | plot |
| Checkbutton | Elec. Quad. (Q²) | `_comb_q2` (BooleanVar) | Show electric quadrupole component | plot |

### Collapsible: Envelope Settings

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Entry + Slider | ΔE (eV) | `_delta_e` / `_de_slider_var` | Energy shift | plot |
| Entry + Slider | Scale | `_tddft_scale` / `_scale_slider_var` | Intensity multiplier | plot |
| Checkbutton | Fill area | `_env_fill` (BooleanVar) | Fill under envelope | plot |
| Entry | (fill opacity) | `_env_fill_alpha` (DoubleVar) | Fill transparency | plot |

### Collapsible: Sticks Settings

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Checkbutton | Show tip markers | `_stick_markers` (BooleanVar) | Dots at stick tips | plot |
| Entry | (stick height) | `_stick_height` (DoubleVar) | Stick amplitude multiplier | plot |

### Overlay Panel — per-TDDFT-spectrum row

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Button (swatch) | (colour) | → colour picker | Spectrum colour | scan |
| Checkbutton | (label) | `vis` (BooleanVar) | Show / hide spectrum | scan |
| Button | ✓ / – | `in_legend` (BooleanVar) | Include in legend | scan |
| OptionMenu | (linestyle) | `env_linestyle` → `_replot()` | Envelope linestyle | scan |
| Entry | (linewidth) | `env_linewidth` | Envelope line thickness | scan |
| Button | Style… | `_open_tddft_spectrum_style_dialog(idx)` | Open per-spectrum style dialog | scan |
| Button | ✕ | `_remove_tddft_idx(idx)` | Remove spectrum | scan |

### Overlay Panel — per-experimental-scan row

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Button (swatch) | (colour) | → colour picker | Scan colour | scan |
| Checkbutton | (label) | `var` (BooleanVar) | Show / hide scan | scan |
| Button | ✓ / – | `in_legend` (BooleanVar) | Include in legend | scan |
| OptionMenu | (linestyle) | `linestyle` → `_replot()` | Line style | scan |
| Entry | (linewidth) | `linewidth` | Line thickness | scan |
| Button | Style… | `_open_exp_style_dialog(idx)` | Open exp style dialog | scan |
| Button | ✕ | `_remove_exp_scan_idx(idx)` | Remove scan | scan |

### Plot Canvas Event Bindings

| Event | Handler | Function | Scope |
|-------|---------|----------|-------|
| button_press_event | `_inset_on_press()` | Start inset drag | plot |
| motion_notify_event | `_inset_on_motion()` | Drag inset boundary | plot |
| button_release_event | `_inset_on_release()` | Finalize inset | plot |
| motion_notify_event | `_on_hover()` | Hover tooltip | plot |
| button_press_event (legend) | `_legend_on_press()` | Start legend drag | plot |
| motion_notify_event (legend) | `_legend_on_motion()` | Move legend | plot |
| button_release_event (legend) | `_legend_on_release()` | Finalize legend position | plot |

---

## Dialogs spawned from the TDDFT Tab

### Per-spectrum TDDFT Style Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Checkbutton | Sticks | `show_sticks` | Show sticks | scan |
| Checkbutton | Envelope | `show_env` | Show envelope | scan |
| Checkbutton | Transitions | `show_trans` | Show transitions | scan |
| Radiobutton | Gaussian / Lorentzian | `broadening` | Broadening type | scan |
| Entry + Slider | FWHM | `fwhm` | Linewidth | scan |
| Checkbutton | (components) | `comb_*` | Component visibility | scan |
| Checkbutton | Fill | `env_fill` | Fill under envelope | scan |
| Entry | (fill α) | `env_fill_alpha` | Fill transparency | scan |
| Checkbutton | Markers | `stick_markers` | Stick tip dots | scan |
| Entry | (stick height) | `stick_height` | Stick amplitude scale | scan |
| Button | Apply | `_do_apply()` | Apply to this spectrum | scan |
| Button | Apply to ALL TDDFT | `_apply_to_all()` | Apply to all TDDFT spectra | all |
| Button | Set as Default | `_save_as_default()` | Persist as default style | app |
| Button | Cancel | `win.destroy()` | Discard changes | — |

### Experimental Scan Style Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Radiobutton | Solid / Dashed / Dotted / Dash-dot | `ls_var` | Line style | scan |
| Button (swatch) | (colour) | `_pick_color()` | Open colour chooser | scan |
| Button | Reset to auto | `_reset_color()` | Restore default colour | scan |
| Scale | Line width | `lw_var` (0.5–5.0) | Line thickness | scan |
| Checkbutton | Fill | `fill_var` | Fill under curve | scan |
| Scale | Fill opacity | `alpha_var` (0–0.5) | Fill transparency | scan |
| Button | Apply | `_do_apply()` | Apply to this scan | scan |
| Button | Apply to ALL Exp. | `_apply_to_all()` | Apply to all exp scans | all |
| Button | Set as Default | `_save_as_default()` | Persist as default style | app |
| Button | Cancel | `win.destroy()` | Discard changes | — |

### Font Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Spinbox + Checkbutton | Title size / bold | `_font_title_size`, `_font_title_bold` | Title font | plot |
| Spinbox + Checkbutton | X-label size / bold | `_font_xlabel_size`, `_font_xlabel_bold` | X-axis label font | plot |
| Spinbox + Checkbutton | Y-label size / bold | `_font_ylabel_size`, `_font_ylabel_bold` | Y-axis label font | plot |
| Button | Save as Default | `_save_as_default()` | Persist settings | app |
| Button | Reset Defaults | `_reset_all()` | Load saved defaults | app |
| Button | Factory Reset | `_factory_reset()` | Hardcoded defaults | app |
| Button | Close | `win.destroy()` | Close dialog | — |

### Legend Labels Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Entry (per spectrum) | (label) | custom entry | Override spectrum legend label | scan |
| Checkbutton (per spectrum) | Show in legend | (BooleanVar) | Include / exclude from legend | scan |
| Checkbutton | Show legend on plot | `_show_legend` (BooleanVar) | Display legend box | plot |
| Button | Apply | — | Apply changes | plot |
| Button | Cancel | `win.destroy()` | Discard | — |

### Inset Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Entry | X min / X max | `xlo_v`, `xhi_v` | Inset x range | plot |
| Entry | Y min / Y max | `ylo_v`, `yhi_v` | Inset y range (optional) | plot |
| Scale + Entry | Width % | `wv` | Inset width | plot |
| Scale + Entry | Height % | `hv` | Inset height | plot |
| Button | Apply | — | Create / update inset | plot |
| Button | Remove Inset | — | Delete inset | plot |
| Button | Cancel | `win.destroy()` | Discard | — |

### Pop-Out Window

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Checkbutton | Auto-refresh | `_popout_refresh_auto` (BooleanVar) | Auto-update on parent change | plot |
| Button | Refresh Now | `_do_refresh()` | Manual update | plot |
| Button | Save Figure… | `_save_popout()` | Save pop-out figure | plot |
| Button | Close | `_on_close()` | Close window | — |

---

## 🔬 XANES Tab — `xas_analysis_tab.py`

### Top Toolbar

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Combobox | (scan list) | `_scan_var` → `_auto_fill_e0()` | Select active scan | scan |
| Button | Refresh Scans | `refresh_scan_list()` | Reload scan list | all |
| Button | ▶ Run Analysis | `_run()` | Compute XANES for selected scan | scan |
| Button | + Add to Overlay | `_add_overlay()` | Push result to TDDFT tab | scan |
| Button | Clear Overlay | `_clear_overlay()` | Remove all from overlay | all |
| Button | ✓ Apply norm to ALL | `_apply_norm_all()` | Apply norm params to all scans | all |
| Button | ∑ Average Scans… | `_show_average_dialog()` | Open averaging dialog | all |
| Label | (status) | `_status_lbl` | Status message | — |

### Collapsible: Loaded Scans

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Button | All | `_show_all_scans()` | Check all scans | all |
| Button | None | `_hide_all_scans()` | Uncheck all scans | all |
| Label (swatch, per row) | (colour) | — | Scan colour indicator | scan |
| Checkbutton (per row) | — | `_scan_vis_vars[label]` | Include scan in analysis | scan |
| Label (per row, clickable) | (scan name) | `_select_scan(label)` | Click to select and run | scan |

### Collapsible: Visualization

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Checkbutton | Plot μ(E) | `_show_mu` (BooleanVar) | Show raw absorption | plot |
| Checkbutton | Plot norm | `_show_norm` (BooleanVar) | Show normalized spectrum | plot |
| Checkbutton | Plot pre-edge | `_show_pre_edge` (BooleanVar) | Show pre-edge fit line | plot |
| Checkbutton | Plot post-edge | `_show_post_edge` (BooleanVar) | Show post-edge line | plot |
| Checkbutton | Plot χ(k) | `_show_chi` (BooleanVar) | Show EXAFS oscillations | plot |
| Combobox | Location | `_legend_loc_var` | Legend position | plot |
| Spinbox | Font size | `_legend_size_var` | Legend font size | plot |
| Combobox | Style | `_style_var` | Seaborn plot style | plot |
| Combobox | Context | `_context_var` | Seaborn context | plot |

### Collapsible: Parameters

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Spinbox | E0 (eV) | `_e0_var` | Absorption edge energy | scan |
| Spinbox | pre1 / pre2 (eV) | `_pre1_var`, `_pre2_var` | Pre-edge region bounds | scan |
| Spinbox | nor1 / nor2 (eV) | `_nor1_var`, `_nor2_var` | Post-edge normalization region | scan |
| Radiobutton | Norm order 1 / 2 | `_nnor_var` | Normalization polynomial order | scan |
| Spinbox | rbkg (Å) | `_rbkg_var` | Background removal range | scan |
| Radiobutton | k-weight 1 / 2 / 3 | `_kw_var` | k-weighting exponent | scan |
| Entry | X / Y min / max | `_xanes_x/ymin/max_var` | Manual plot limits | plot |
| Button | Apply | — | Set manual limits | plot |
| Button | From Plot | `_capture_from_plot()` | Read current plot limits | plot |
| Button | Auto | `_auto_limits()` | Reset to auto | plot |
| Button | Auto Deglitch | `_deglitch()` | Remove spikes interactively | scan |
| Button | Reset Scan | `_reset_scan()` | Restore original data | scan |
| Button | Smooth Scan | `_smooth_scan()` | Apply smoothing filter | scan |
| Button | Shift Energy | `_shift_energy_dialog()` | Open energy shift dialog | scan |
| Checkbutton | Show FT window | `_show_ft_window` | Highlight FT window on χ(k) plot | plot |
| Button | ★ Set Norm as Default | `_set_norm_default()` | Save normalization params as default | app |
| Button | ▶ Run Analysis | `_run()` | Compute analysis | scan |

---

## Dialogs spawned from the XANES Tab

### XAS Scan Style Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Radiobutton | Solid / Dashed / Dotted / Dash-dot | `ls_var` | Line style | scan |
| Button (swatch) | (colour) | `_pick_color()` | Open colour chooser | scan |
| Button | Auto | `_reset_color()` | Restore default colour | scan |
| Scale | Line width | `lw_var` | Line thickness | scan |
| Scale | Opacity | `alpha_var` | Line transparency | scan |
| Radiobutton | None / Circle / Square / Diamond | `marker_var` | Marker shape | scan |
| Spinbox | (marker size) | `ms_var` | Marker size (2–12 px) | scan |
| Button | Apply | — | Apply to this scan | scan |
| Button | Apply to All Scans | — | Apply to all XAS scans | all |
| Button | Cancel | `win.destroy()` | Discard | — |

### Average Scans Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Checkbutton (per row) | (scan name) | `var` (BooleanVar) | Include in average | scan |
| Checkbutton | Normalise together | `norm_together_var` | Single norm on averaged result | all |
| Entry | Output label | `out_label_var` | Name for averaged spectrum | — |
| Button | ∑ Average & Add | `do_average()` | Compute and add to plot | all |
| Button | Cancel | `win.destroy()` | Abort | — |

### Deglitch Mode (Interactive canvas)

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Button | Remove | `_deglitch_mode = "remove"` | Remove spike at click | scan |
| Button | Average | `_deglitch_mode = "average"` | Replace with neighbour average | scan |
| Button | Interpolate | `_deglitch_mode = "interp"` | Interpolate across spike | scan |
| Button | Undo | `_deglitch_undo_btn` | Undo last deglitch operation | scan |
| Canvas event | button_press_event | `_on_plot_click()` | Apply selected deglitch at click location | scan |

---

## ⚗ EXAFS Tab — `exafs_analysis_tab.py`

### Top Toolbar

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Combobox | (scan list) | `_scan_var` → `_auto_fill_e0()` | Select active scan | scan |
| Button | Refresh Scans | `refresh_scan_list()` | Reload scan list | all |
| Button | Run EXAFS | `_run()` | Compute EXAFS | scan |
| Button | Update Views | `_redraw()` | Refresh plots | all |
| Button | + Add to Overlay | `_add_overlay()` | Push to TDDFT tab | scan |
| Button | Clear Overlay | `_clear_overlay()` | Clear overlay list | all |
| Label | (status) | `_status_lbl` | Status message | — |

### Parameters Panel

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Spinbox | E0 / pre1 / pre2 / nor1 / nor2 | `_e0/pre/nor_vars` | Background / normalization bounds | scan |
| Spinbox | rbkg (Å) | `_rbkg_var` | Background removal range | scan |
| Spinbox | kmin bkg | `_kmin_bkg_var` | Min k for background fit | scan |
| Radiobutton | Norm order 1 / 2 | `_nnorm_var` | Normalization order | scan |
| Spinbox | q min / q max (Å⁻¹) | `_qmin_var`, `_qmax_var` | k-range for EXAFS window | scan |
| Spinbox | dq taper | `_dq_var` | Window taper width | scan |
| Radiobutton | q-weight 1 / 2 / 3 | `_qweight_var` | k-weighting exponent | scan |
| Combobox | q window | `_qwin_var` | Window function (Hanning, Sine, Welch, Parzen) | scan |
| Button | q from Plot | `_capture_q_window_from_plot()` | Read q limits from plot | plot |
| Button | Default q | `_reset_q_window()` | Reset q defaults | scan |
| Spinbox | R min / R max (Å) | `_rmin_var`, `_rmax_var` | R range for inverse FT | scan |
| Spinbox | dR taper | `_dr_var` | R window taper | scan |
| Entry | R display | `_rdisplay_var` | Max R shown on plot | plot |
| Combobox | R window | `_rwin_var` | R window function | scan |
| Button | R from Plot | `_capture_r_window_from_plot()` | Read R limits from plot | plot |
| Button | Default R | `_reset_r_window()` | Reset R defaults | scan |
| Combobox | Style / Context | `_style_var`, `_context_var` | Seaborn plot style | plot |
| Checkbutton | Label k-space as q | `_use_q_label_var` | Use "q" instead of "k" | plot |
| Checkbutton | Show q window | `_show_q_window_var` | Highlight q window on plot | plot |
| Checkbutton | Show R window | `_show_r_window_var` | Highlight R window on plot | plot |
| Checkbutton | Show FEFF markers | `_show_feff_markers_var` | FEFF path reference lines | plot |
| Button | Run / Refresh EXAFS | `_run()` | Compute or update | scan |
| Button | Redraw Windows Only | `_redraw()` | Refresh without recompute | all |

### Collapsible: Loaded Scans (same pattern as XANES)

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Button | All / None | `_show/hide_all_scans()` | Select / deselect all | all |
| Checkbutton (per row) | — | `_scan_vis_vars[label]` | Include scan | scan |
| Label (per row, clickable) | (scan name) | `_select_scan(label)` | Select and run | scan |

### FEFF Sub-tab

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Entry + Button | Workdir | `_feff_dir_var` → `_browse_feff_dir()` | FEFF working directory | app |
| Button | Load Paths | `_load_feff_paths()` | Read feff*.dat files | all |
| Entry + Button | Executable | `_feff_exe_var` → `_browse_feff_exe()` | FEFF executable path | app |
| Button | Run FEFF | `_run_feff()` | Execute FEFF | app |
| Entry + Button | XYZ file | `_xyz_path_var` → `_browse_xyz_file()` | Load structure file | scan |
| Button | Load XYZ | `_load_xyz_structure()` | Parse XYZ | scan |
| Entry | Base name | `_bundle_base_var` | Output file base name | — |
| Entry | Padding (Å) | `_xyz_padding_var` | Padding in CIF export | scan |
| Checkbutton | Force cubic cell | `_xyz_cubic_var` | Force cubic cell | scan |
| Entry | Absorber # | `_xyz_absorber_var` | Absorbing atom index | scan |
| Combobox | Edge | `_xyz_edge_var` | X-ray edge (K, L1, L2, L3) | scan |
| Combobox | Spectrum | `_xyz_spectrum_var` | EXAFS or XANES mode | scan |
| Entry | KMESH | `_xyz_kmesh_var` | k-mesh density | scan |
| Entry | Equivalence | `_xyz_equiv_var` | Atom equivalence criterion | scan |
| Button | Write FEFF Bundle | `_write_xyz_feff_bundle()` | Export CIF + feff.inp | scan |
| Treeview | (path list) | `_feff_tree` → `_on_feff_selection()` | FEFF path table (index, reff, degen, nleg) | scan |
| Canvas (preview) | (plot) | `_canvas_feff` | FEFF path amplitude plot | scan |
| Text (read-only) | (log) | `_feff_log` | FEFF execution output | app |

---

## 🌈 UV/Vis Tab — `uvvis_tab.py`

### Top Toolbar

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Button | 📂 Load File… | `_load_files()` | Open file browser | all |
| Radiobutton | nm / cm⁻¹ / eV | `_x_unit` → `_on_unit_change()` | X-axis unit; converts sticky limits | plot |
| Radiobutton | Abs / %T | `_y_unit` → `_redraw()` | Y-axis quantity | plot |
| Combobox | none / peak / area | `_norm_mode` → `_redraw()` | Normalization mode | plot |
| Checkbutton | λ(nm) axis | `_show_nm_axis` → `_redraw()` | Secondary nm axis in cm⁻¹ mode | plot |
| Button | + Add to TDDFT Overlay | `_add_selected_to_overlay()` | Push visible scans to TDDFT | all |
| Label | (status) | `_status_lbl` | Status message | — |

### Axis Limits Bar

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Entry | X lo / X hi | `_xlim_lo`, `_xlim_hi` → `_redraw()` | X-axis bounds (blank = auto) | plot |
| Button | Auto X | `_auto_x()` | Reset x to auto | plot |
| Entry | Y lo / Y hi | `_ylim_lo`, `_ylim_hi` → `_redraw()` | Y-axis bounds | plot |
| Button | Auto Y | `_auto_y()` | Reset y to auto | plot |

### Loaded Spectra Sidebar — per-scan row

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Button (swatch) | (colour) | `_pick()` → colorchooser | Change scan colour | scan |
| Checkbutton | (label) | `vis` (BooleanVar) → `_redraw()` | Show / hide scan | scan |
| Button | ✓ / – | `in_legend` (BooleanVar) → `_redraw()` | Include in legend | scan |
| Canvas (linestyle) | (drawn line) | click → `_cycle()` | Cycle linestyle; draws exact linewidth in scan colour | scan |
| Entry | (linewidth) | `style["linewidth"]` → `_redraw()` | Line thickness (exact float) | scan |
| Checkbutton | (fill) | `style["fill"]` → `_redraw()` | Fill under curve | scan |
| Button | ⚙ | `_open_style_dialog(idx)` | Open full style dialog | scan |
| Button | ✕ | `_remove_entry(idx)` | Delete scan | scan |

### Plot Canvas Event Bindings

| Event | Handler | Function | Scope |
|-------|---------|----------|-------|
| button_release_event | `_on_mpl_interact()` | Capture pan/zoom limits into entry fields | plot |
| scroll_event | `_on_mpl_interact()` | Capture scroll-zoom limits | plot |

---

## Dialogs spawned from the UV/Vis Tab

### Spectrum Style Dialog

| Widget | Label / Text | Variable / Callback | Function | Scope |
|--------|-------------|---------------------|----------|-------|
| Radiobutton | Solid / Dashed / Dotted / Dash-dot | `ls_var` | Line style | scan |
| Button ∀ | (apply to all) | `_push_to_all("linestyle", ls_var.get)` | Apply linestyle to all | all |
| Scale | Line width (0.5–5 pt) | `lw_var` | Line thickness | scan |
| Button ∀ | (apply to all) | `_push_to_all("linewidth", lw_var.get)` | Apply linewidth to all | all |
| Scale | Line opacity (0–1) | `alpha_var` | Line transparency | scan |
| Button ∀ | (apply to all) | `_push_to_all("alpha", alpha_var.get)` | Apply opacity to all | all |
| Button (swatch) | (colour) | `_pick_color()` | Open colour chooser | scan |
| Button | Reset | `_reset_color()` | Restore palette colour | scan |
| Button ∀ | (apply to all) | `_push_to_all("color", …)` | Apply colour to all | all |
| Checkbutton | Show fill under curve | `fill_var` | Fill under curve | scan |
| Button ∀ | (apply to all) | `_push_to_all("fill", fill_var.get)` | Apply fill to all | all |
| Scale | Fill opacity (0–0.5) | `fill_alpha_var` | Fill transparency | scan |
| Button ∀ | (apply to all) | `_push_to_all("fill_alpha", …)` | Apply fill opacity to all | all |
| Button | Apply | `_do_apply()` | Apply to this scan, stay open | scan |
| Button | ∀ Apply to All | `_do_apply_all()` | Apply all (except colour) to all | all |
| Button | Save | `_do_save()` | Apply and close | scan |
| Button | Cancel | `_do_cancel()` | Revert and close | — |
