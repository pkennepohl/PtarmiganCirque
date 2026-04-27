# Ptarmigan — Project Backlog

## About

Ptarmigan is a Python/Tkinter desktop application and computational
spectroscopy workbench. It manages experimental spectroscopic data
(XANES, EXAFS, UV/Vis/NIR), interfaces with external computational
engines (Larch, FEFF, bXAS), and provides a unified comparison and
presentation surface for overlaying experimental and calculated spectra.

The core workflow is:
**load raw data → process or simulate → commit results → send to Compare → generate figures**

All data manipulation is tracked in a provenance DAG (directed acyclic
graph). Every committed result is reproducible from the original raw files.

Main files (current — will change during restructure):

| File | Current purpose | Status |
|---|---|---|
| `binah.py` | App entry point; notebook + tab wiring | Major restructure |
| `plot_widget.py` | TDDFT tab + overlay panel | → Compare tab |
| `xas_analysis_tab.py` | XANES tab | Refactor |
| `exafs_analysis_tab.py` | EXAFS tab | Refactor; extract FEFF |
| `uvvis_tab.py` | UV/Vis tab | Reference implementation |
| `uvvis_parser.py` | UV/Vis file parser | Retain |
| `experimental_parser.py` | XAS file parser | Retain |
| `graph.py` | ProjectGraph DAG model | ✅ Phase 1 + Phase 2 graph extensions |
| `nodes.py` | DataNode / OperationNode dataclasses | ✅ Phase 1 |
| `project_io.py` | .ptproj/ skeleton + raw file ingestion | ✅ Phase 1 (full graph save/load deferred) |
| `scan_tree_widget.py` | ScanTreeWidget component | ✅ Phase 2 |
| `compare_tab.py` | Compare tab | **New** |
| `simulate_tab.py` | Simulate tab (FEFF session manager) | **New** |
| `feff_workspace.py` | FEFF dedicated workspace window | **New** |
| `bxas_workspace.py` | bXAS dedicated workspace window | **New** |
| `bxas_engine.py` | bXAS Python reimplementation | **New** |
| `style_dialog.py` | Unified style dialog | **New** |
| `plot_settings_dialog.py` | Plot Settings dialog | **New** |

See ARCHITECTURE.md for all structural decisions.

---

## Priority Scale (MoSCoW + Foundation)

| Symbol | Tier | Meaning |
|---|---|---|
| 🔵 | **Foundation** | Architectural prerequisite; no features can be built correctly without this |
| 🔴 | **Must** | Core functionality; the app feels incomplete without it |
| 🟡 | **Should** | Clearly on the roadmap; implement soon after foundations |
| 🟢 | **Could** | Nice to have; implement if time permits |
| ⚪ | **Won't** (for now) | Explicitly deferred |

---

## Implementation Phases

Work must proceed in phase order. Later phases depend on earlier ones.
Within a phase, items can be parallelised.

---

## Phase 1 — Foundation: Data Model  ✅ Complete

*Nothing else should be built until this phase is complete.*

| Status | Priority | Item | Notes |
|---|---|---|---|
| ✅ | 🔵 | **ProjectGraph class** | DAG with add\_node, add\_edge, query, traversal. Reactive observer pattern with subscribe/unsubscribe. Persistence to .ptproj/ deferred until graph contract stabilises |
| ✅ | 🔵 | **DataNode dataclass** | id, type, arrays (npz), metadata, label, state (PROVISIONAL/COMMITTED/DISCARDED), created\_at (tz-aware UTC), active, style |
| ✅ | 🔵 | **OperationNode dataclass** | id, type, engine, engine\_version, params, input\_ids, output\_ids, timestamp (tz-aware UTC), duration\_ms, status, log, state |
| ✅ | 🔵 | **NodeType and OperationType enums** | All variants from CS-02/CS-03 present (RAW\_FILE, XANES, EXAFS, UVVIS, DEGLITCHED, NORMALISED, SMOOTHED, SHIFTED, BASELINE, AVERAGED, DIFFERENCE, TDDFT, FEFF\_PATHS, BXAS\_RESULT) |
| ✅ | 🔵 | **NodeState enum** | PROVISIONAL, COMMITTED, DISCARDED |
| ✅ | 🔵 | **Commit / discard operations** | commit\_node, discard\_node — fire NODE\_COMMITTED / NODE\_DISCARDED. log.jsonl write deferred to project\_io |
| ✅ | 🔵 | **Project file format (skeleton)** | .ptproj/ directory created: project.json, graph/committed/, graph/provisional/, raw/, sessions/, log.jsonl. Full node-level save/load deferred (project\_io stubs raise NotImplementedError) |
| ✅ | 🔵 | **Raw file ingestion** | copy\_raw\_file copies raw input → raw/{id}\_\_{filename}, computes SHA-256, updates raw/manifest.json |
| ⏳ | 🔵 | **Raw file load → RAW\_FILE node** | Loader integration deferred to Phase 4 (UV/Vis pilot tab). No processing runs automatically |
| ⏳ | 🔵 | **Provisional session recovery** | recover\_provisional stub; full implementation deferred until graph save/load is in place |

---

## Phase 2 — Foundation: ScanTreeWidget  ✅ Complete (with caveats)

*Depends on Phase 1.*

Phase 2 also extended the graph with `set_active`, `set_style` (merge),
`clone_node`, `NODE_ACTIVE_CHANGED`, `NODE_STYLE_CHANGED`, and
log-and-continue subscriber dispatch. See COMPONENTS.md CS-01 and CS-04
"Implementation notes" for the full contract.

| Status | Priority | Item | Notes |
|---|---|---|---|
| ✅ | 🔵 | **ScanTreeWidget base component** | Flat list; one row per non-discarded DataNode that passes the filter (sweep groups collapse). Rows: state indicator · colour swatch · visibility checkbox · label · legend toggle · linestyle canvas · history indicator · ⚙ · ✕ |
| ✅ | 🔵 | **State indicator on rows** | 🔒 = committed; ⋯ = provisional. Discarded rows are not rendered |
| ✅ | 🔵 | **History expansion** | Click ⌥n → inline expansion of provenance\_chain. Each entry calls redraw\_cb(focus=id) |
| ✅ | 🔵 | **In-place label editing** | Double-click label → editable Entry; Enter to confirm via set\_label; Escape to cancel |
| ✅ | 🔵 | **Sweep group row** | 2+ provisional DataNodes sharing a DataNode parent collapse to one leader row (lex-smallest id). `✕all` discards every member |
| ✅ | 🔵 | **Commit / discard gestures** | Right-click context menu (Commit / Discard); ✕ on row (discard if provisional, soft-hide if committed). Keyboard shortcuts deferred to tab integration |
| ✅ | 🔵 | **Send to Compare action** | Right-click menu invokes send\_to\_compare\_cb(node\_id) when committed. Widget knows nothing about the Compare tab |
| ✅ | 🔵 | **Reactive updates** | Subscribes on construction, unsubscribes on `<Destroy>`. NODE\_ADDED / DISCARDED / EDGE\_ADDED rebuild; LABEL\_CHANGED / STYLE\_CHANGED refresh one row; ACTIVE\_CHANGED rebuilds (respects "Show hidden") |
| ⏳ | 🟡 | **Sweep group inline expansion** | Per-variant editing (commit/discard one variant at a time) deferred. `_sweep_groups` exposes the grouping, ready for a future session |
| ⏳ | 🟡 | **Keyboard shortcuts** | Ctrl+Return / Escape / Ctrl+Shift+C deferred to first tab integration; the widget's gestures are mouse-driven for now |

---

## Phase 3 — Foundation: Unified Style Dialog  ✅ Complete (with caveats)

*Depends on Phase 2.*

Phase 3 ships `style_dialog.py` and `test_style_dialog.py`. The
dialog is modeless, subscribes to `NODE_STYLE_CHANGED`, mutates
exclusively via `graph.set_style`, and handles cross-node fan-out by
delegating to a tab-supplied `on_apply_to_all` callback. See
COMPONENTS.md CS-05 "Implementation notes" for the full set of
decisions taken for ambiguities the spec left open.

| Status | Priority | Item | Notes |
|---|---|---|---|
| ✅ | 🔵 | **Unified style dialog shell** | Modeless (non-blocking); title shows node label; sections conditional on node type. Module-level `open_style_dialog()` factory enforces one-dialog-per-node (focuses the existing window on a second open) |
| ✅ | 🔵 | **Universal section** | Line style (radio), line width (slider + value), line opacity (slider), colour (swatch + picker + Reset), fill (checkbox + opacity slider). ∀ button per row |
| ✅ | 🔵 | **Markers section** | Shape radio (none/circle/square/diamond), size spinbox. Shown for: XANES, EXAFS, DEGLITCHED, AVERAGED |
| ✅ | 🔵 | **Broadening section** | Gaussian/Lorentzian radio, FWHM slider + entry. Shown for: TDDFT, BXAS\_RESULT |
| ✅ | 🔵 | **Energy shift and scale section** | ΔE entry + slider, scale entry + slider. Shown for: TDDFT, BXAS\_RESULT, FEFF\_PATHS |
| ✅ | 🔵 | **Envelope section** | Line width, fill checkbox + opacity. Shown for: TDDFT, BXAS\_RESULT |
| ✅ | 🔵 | **Sticks section** | Line width, opacity, tip markers checkbox, marker size. Shown for: TDDFT |
| ⏳ | 🔵 | **Uncertainty band section** | Stubbed — schema blocked on **OQ-002**. The section header is present and contains a Label citing OQ-002 so the gap is visible rather than silent. Controls land here once the bXAS uncertainty representation is decided |
| ⏳ | 🔵 | **bXAS compound result grouping** | Stubbed — blocked on **OQ-003** (one row vs three vs expandable group for fit + uncertainty + residuals). Same stub treatment as the uncertainty band section |
| ✅ | 🔵 | **Component visibility section** | Total / D² / m² / Q² checkboxes. Shown for: TDDFT |
| ✅ | 🔵 | **Bottom buttons** | Apply · ∀ Apply to All · Save · Cancel. Matches existing UV/Vis dialog. Cancel reverts via deep-copied snapshot taken at `__init__`; window-close [X] is wired to Cancel so close-without-Cancel still reverts |
| ✅ | 🔵 | **∀ per-parameter apply-to-all** | Universal-section rows only; the dialog delegates `(param_name, value)` via the tab-supplied `on_apply_to_all` callback. Conditional sections deferred — adding ∀ there awaits a tab-side scope decision |
| ✅ | 🔵 | **Bottom ∀ Apply to All** | Fans out every universal-section parameter except colour, per CS-05 |

---

## Phase 4 — UV/Vis Tab (Pilot Tab)

*Depends on Phases 1–3. This is the pilot implementation of the new
architecture. The existing UV/Vis tab is the closest to the new model.*

### Friction points carried forward from Phase 2

These are concrete obstacles that Phase 4 will hit when it migrates
[uvvis_tab.py](uvvis_tab.py) onto ProjectGraph + ScanTreeWidget.
Identified during Phase 2 while reading the existing sidebar as the
reference implementation. **Do not fix until Phase 4** — they need to
be addressed in the same change that wires ScanTreeWidget into the
tab, not piecemeal.

1. **`self._entries: List[dict]` is the single source of truth**
   ([uvvis_tab.py:129](uvvis_tab.py#L129)) and is indexed positionally.
   Every helper closure in `_rebuild_table` captures `idx=i` from the
   row loop (`_pick`, `_lw_cb`, `_fill_cb`, `_remove_entry`,
   `_open_style_dialog`). Migration converts every `idx`-keyed
   callsite to `node_id`-keyed.
2. **`in_legend` is a separate `tk.BooleanVar`** sitting alongside
   `style` ([uvvis_tab.py:509](uvvis_tab.py#L509)), not inside it. The
   new architecture stores it at `style["in_legend"]`. No project
   files exist yet so the cutover does not need legend-state
   migration.
3. **`_PALETTE[idx % len(_PALETTE)]` colour assignment**
   ([uvvis_tab.py:505](uvvis_tab.py#L505)) lives in the loader. With
   the new model, default colour assignment needs to happen at
   DataNode creation time (inside the load-as-RAW\_FILE pipeline) so
   the same node draws the same colour across tabs. Decide where: in
   the loader, or as a graph-side default-style policy.
4. **`_rebuild_table` is monolithic**
   ([uvvis_tab.py:306-484](uvvis_tab.py#L306)) — header construction
   and every per-row gesture sit inline. A clean migration deletes
   this method entirely along with `_make_leg_btn`, `_make_ls_canvas`,
   `_make_lw_entry` (all reimplemented in
   [scan_tree_widget.py](scan_tree_widget.py)) and replaces them with
   one `ScanTreeWidget(...)` instantiation.
5. **`_redraw` walks `self._entries` directly.** Once entries become
   DataNodes, `_redraw` must traverse the graph (e.g.
   `graph.nodes_of_type(NodeType.UVVIS, state=None)` then filter
   `state != DISCARDED` and `active`) to find what to plot. This
   pattern repeats in every tab; consider a shared helper.
6. **`_remove_entry` deletes from the list**
   ([uvvis_tab.py:525](uvvis_tab.py#L525)) with no scientific record.
   Migration replaces this with `graph.discard_node` (provisional) or
   `graph.set_active(False)` (committed) — exactly what the new ✕
   button does. Audit external callers of `_remove_entry` during the
   cutover.
7. **`_open_style_dialog` is inline**
   ([uvvis_tab.py:697](uvvis_tab.py#L697)). Phase 3 builds the unified
   dialog; Phase 4 connects ScanTreeWidget's gear via
   `style_dialog_cb` and deletes the inline implementation.

### Friction points carried forward from Phase 3

These are concrete obstacles that Phase 4 will hit when it swaps the
inline `_open_style_dialog` for the unified `StyleDialog`. Identified
during Phase 3 while reading the existing dialog as the reference
implementation. **Do not fix until Phase 4** — they are the migration
checklist for that swap-in.

1. **`win.grab_set()`** ([uvvis_tab.py:707](uvvis_tab.py#L707)) makes
   the inline dialog application-modal. The unified `StyleDialog` is
   modeless by design (no `transient`, no `grab_set`). Migration
   removes the grab — multiple style dialogs across nodes/tabs must
   be allowed to coexist.
2. **Per-row `idx`-keyed gear callbacks**
   ([uvvis_tab.py:697](uvvis_tab.py#L697) takes `idx`). After Phase 4
   the `ScanTreeWidget` invokes `style_dialog_cb(node_id)`. The
   migration converts `_open_style_dialog(idx)` to
   `lambda node_id: open_style_dialog(self, self._graph, node_id,
   on_apply_to_all=...)`.
3. **`_push_to_all` writes through `e["style"][key]`**
   ([uvvis_tab.py:725-733](uvvis_tab.py#L725)) and explicitly calls
   `self._rebuild_table()` and `self._redraw()` afterwards. The
   migration provides an `on_apply_to_all` callback to `StyleDialog`
   that uses `graph.set_style` for each visible UVVIS node, then
   relies on the existing graph subscription for the redraw.
   `_rebuild_table` and `_redraw` go away when the sidebar becomes
   ScanTreeWidget.
4. **`auto_col = _PALETTE[idx % len(_PALETTE)]`**
   ([uvvis_tab.py:790](uvvis_tab.py#L790)) computes a per-position
   default colour inside the dialog and passes it to the colour
   swatch as the implicit baseline. The unified dialog has no
   palette knowledge; Reset restores the snapshot colour, not a
   palette default. Phase 4 must assign the default colour at
   DataNode creation time (in the loader / load-as-RAW\_FILE
   pipeline) so `node.style["color"]` is non-empty by the time the
   dialog opens. This is the same friction listed as Phase 2 item 3.
5. **`_orig` snapshot lives in the dialog closure**
   ([uvvis_tab.py:839](uvvis_tab.py#L839)) and is restored by
   `style.update(_orig)` in `_do_cancel`. Replaced wholesale by
   `StyleDialog._snapshot` and the `set_style(snapshot)` revert path.
   Note the same merge-can't-remove-keys limitation applies in both
   implementations and is documented in CS-05 Implementation notes.
6. **Dialog reads from `entry["style"]` and `entry["scan"]` dicts**
   ([uvvis_tab.py:701-702](uvvis_tab.py#L701)). After migration the
   dialog reads from `graph.get_node(node_id).style` exclusively; the
   `_entries` list disappears as part of the broader Phase 4
   restructure.
7. **`_do_save` calls `_do_apply()` then `win.destroy()`**
   ([uvvis_tab.py:870-871](uvvis_tab.py#L870)). The unified dialog
   has the same flow but lives in `StyleDialog._do_save`. Phase 4
   simply deletes the inline `_open_style_dialog` method (~175 lines)
   and the `_LS_OPTIONS` constant if not needed elsewhere; the
   gear-button hand-off is already in `ScanTreeWidget`
   (`style_dialog_cb` parameter).

| Priority | Item | Notes |
|---|---|---|
| 🔴 | **Migrate UV/Vis to node model** | UVVisScan → DataNode(type=UVVIS). File load → RAW\_FILE node. All operations produce provisional nodes |
| 🔴 | **Replace UV/Vis sidebar with ScanTreeWidget** | Retire existing compact grid table; ScanTreeWidget is the replacement |
| 🔴 | **Replace UV/Vis style dialog with unified style dialog** | Existing UV/Vis style dialog is the reference; unified dialog supersedes it |
| 🔴 | **Baseline correction** | Linear (two-point), polynomial (order n), spline, rubberband/convex hull. Each application creates a provisional BASELINE node |
| 🔴 | **Export processed data** | Save committed node data to CSV or TXT; include provenance header |
| 🔴 | **Normalisation as explicit operation** | Normalisation creates a provisional NORMALISED node rather than modifying data in place |
| 🔴 | **"Send to Compare" action** | Replaces "Add to TDDFT Overlay". Available on committed nodes |
| 🔴 | **Plot Settings dialog** | Fonts, grid, background colour, legend position, tick direction, title/label customisation. Accessed via ⚙ in top bar |
| 🟡 | **Peak picking** | Click-to-mark peaks; λ/E annotation; optional peak table export |
| 🟡 | **OLIS integrating sphere correction** | Three-input operation node (sample + reference + blank → corrected). See OQ-004 for multi-input UI design |
| 🟡 | **Interactive normalisation** | Normalise to user-specified wavelength or integration region |
| 🟡 | **Difference spectra** | Two-input operation node. See OQ-004 |
| 🟡 | **Smoothing** | Savitzky-Golay or moving average; creates provisional SMOOTHED node |
| 🟢 | **Second derivative** | Creates provisional node; useful for resolving overlapping bands |
| 🟢 | **Beer-Lambert / concentration** | Use known ε to extract concentration, or fit ε from known concentration |

---

## Phase 5 — XANES Tab

*Depends on Phases 1–3. Shares ScanTreeWidget and unified style dialog.*

| Priority | Item | Notes |
|---|---|---|
| 🔴 | **Migrate XANES to node model** | File load → RAW\_FILE node. Larch normalisation → provisional NORMALISED node |
| 🔴 | **Replace scan list with ScanTreeWidget** | Retire existing simple scan list |
| 🔴 | **Engine selector in left panel** | Radio buttons: Larch / bXAS. Switches parameter section below |
| 🔴 | **Larch parameter panel** | E0, pre1/pre2, nor1/nor2, rbkg, kmin\_bkg, norm order. Run button at bottom |
| 🔴 | **Explicit Run (no auto-run)** | Remove auto-run behaviour. Run creates provisional node. Raw data is always the first committed node |
| 🔴 | **Deglitch as provisional operation** | Each deglitch action creates a provisional DEGLITCHED node. Undo = discard last provisional deglitch node |
| 🔴 | **Smooth as provisional operation** | Creates provisional SMOOTHED node |
| 🔴 | **Shift Energy as provisional operation** | Creates provisional SHIFTED node |
| 🔴 | **Reset Scan** | Discard all provisional nodes back to last committed node for this dataset |
| 🔴 | **"Send to Compare"** | Replaces "Add to Overlay" |
| 🔴 | **Apply norm to ALL** | Apply current Larch parameter set as an operation to all loaded XANES nodes; creates provisional nodes for each |
| 🟡 | **bXAS engine selector path** | When bXAS selected: show session manager + ↗ Open bXAS Workspace button |
| 🟡 | **Average Scans** | Multi-input operation node. See OQ-004 for UI design |
| 🟡 | **Difference spectra** | Two-input operation node |
| 🟡 | **Set Norm as Default** | Save Larch parameter set as app-level default |
| 🟢 | **Batch E0 table export** | Export CSV of E0 / edge step values from committed normalised nodes |
| 🟢 | **Parameter sweep UI** | Run normalisation across a range of E0 values; produces sweep group in ScanTreeWidget |

---

## Phase 6 — EXAFS Tab

*Depends on Phases 1–3.*

| Priority | Item | Notes |
|---|---|---|
| 🔴 | **Migrate EXAFS to node model** | File load → RAW\_FILE node. Larch processing → provisional EXAFS node |
| 🔴 | **Replace scan list with ScanTreeWidget** | |
| 🔴 | **Larch parameter panel** | q min/max, dq taper, q-weight, q window, R min/max, dR taper, R display, R window. Run button |
| 🔴 | **"q from Plot" / "R from Plot" capture** | Read current axis limits into parameter fields. Retain existing feature |
| 🔴 | **"Send to Compare"** | Replaces "Add to Overlay" |
| 🔴 | **Extract FEFF sub-tab** | Remove FEFF UI entirely from EXAFS tab. FEFF moves to Simulate tab / FEFF Workspace. This is the largest single relocation task |
| 🟡 | **Update Views vs Redraw clarification** | Rename: "Run EXAFS" = recompute (new provisional node); "Redraw" = re-render current node without recompute |

---

## Phase 7 — Compare Tab

*Depends on Phases 1–3. Replaces plot_widget.py TDDFT tab entirely.*

| Priority | Item | Notes |
|---|---|---|
| 🔴 | **Compare tab shell** | Three-zone layout: no left panel · centre figure · right ScanTreeWidget |
| 🔴 | **Heterogeneous ScanTreeWidget** | Right sidebar lists all committed nodes sent to Compare, grouped by type: Calculated (TDDFT, FEFF, bXAS) · Experimental (XANES, EXAFS, UV/Vis) |
| 🔴 | **TDDFT file loading** | Load ORCA .out file → DataNode(type=TDDFT) in Compare. Replaces "Open File" from TDDFT tab toolbar |
| 🔴 | **TDDFT section selector** | For ORCA files with multiple sections; moves from global toolbar to Compare tab |
| 🔴 | **Dual y-axis support** | TDDFT and experimental data on separate y-axes (left/right). Axis assignment configurable |
| 🔴 | **Axis limits and units** | X-axis unit selector (eV/nm/cm⁻¹/Ha), axis limit entries, Auto buttons |
| 🔴 | **Secondary x-axis** | Energy ↔ wavelength; toggle |
| 🔴 | **Inset** | Retain existing inset dialog and drag functionality |
| 🔴 | **Pop-out window** | Retain existing pop-out with auto-refresh |
| 🔴 | **Save Figure / Export CSV** | Retain; CSV export includes provenance header |
| 🔴 | **Plot Settings dialog** | Fonts, grid, background colour, legend position, tick direction, title/label, tick style. Replaces scattered controls in current TDDFT tab |
| 🟡 | **Uncertainty band display** | Render shaded uncertainty regions for BXAS\_RESULT nodes. See OQ-002 |
| 🟡 | **bXAS compound result display** | Fit curve + uncertainty band + residuals as grouped node. See OQ-003 |
| 🟡 | **Reproducibility report export** | File menu → Export Reproducibility Report. Human-readable methods summary of all committed operations on nodes currently in Compare |
| 🟡 | **Copy plot to clipboard** | One-click copy of figure as image |
| 🟢 | **Plot annotations** | Place arbitrary text labels on figure |
| 🟢 | **Drag-and-drop file loading** | Drop ORCA .out files onto Compare tab to load as TDDFT nodes |

---

## Phase 8 — Simulate Tab

*Depends on Phases 1–3. Thin session manager; most FEFF UI is in the
FEFF Workspace window.*

| Priority | Item | Notes |
|---|---|---|
| 🔴 | **Simulate tab shell** | Three-zone layout: left (session manager) · centre (session summary / last result preview) · right (results available for Compare) |
| 🔴 | **FEFF session list** | Lists active FEFF sessions: name, associated dataset, status, last result quality indicator |
| 🔴 | **↗ Open FEFF Workspace button** | Launches or focuses the FEFF workspace window for the selected session |
| 🔴 | **Session result preview** | When a committed FEFF result exists, preview it on the centre plot |
| 🔴 | **Send to Compare** | Make committed FEFF result available in Compare tab |
| 🟡 | **New FEFF Session** | Create a new named session; associate with a loaded EXAFS dataset |
| 🟡 | **Session save/restore** | FEFF sessions persist in project file sessions/ directory |

---

## Phase 9 — FEFF Workspace Window

*Depends on Phase 8. Extracts and rehouses the existing FEFF sub-tab
from exafs_analysis_tab.py.*

| Priority | Item | Notes |
|---|---|---|
| 🔴 | **FEFF Workspace window shell** | Non-blocking, non-modal, independently resizable. Communicates with main window via ProjectGraph |
| 🔴 | **Extract existing FEFF UI** | Move workdir, executable, XYZ loader, CIF/FEFF bundle export, path treeview, amplitude preview, execution log from EXAFS tab into workspace window. Reuse existing implementation where possible |
| 🔴 | **Path treeview** | FEFF paths with index, reff, degeneracy, nleg. Per-path inclusion toggle |
| 🔴 | **Path amplitude preview** | Canvas plot of selected path amplitude and phase |
| 🔴 | **FEFF execution log** | Scrollable log panel showing FEFF stdout/stderr |
| 🔴 | **Commit result** | Commit selected path set as COMMITTED DataNode(type=FEFF\_PATHS). Makes available in Simulate tab and Compare |
| 🟡 | **Model comparison** | Compare two FEFF path sets side by side |
| 🟡 | **Path grouping** | Group paths by shell, element, or custom grouping |
| 🟢 | **Structure visualisation** | Render XYZ/CIF structure; highlight absorber and scattering atoms |

---

## Phase 10 — bXAS Workspace Window

*Depends on Phase 5 (XANES tab with engine selector). Requires bXAS
Python reimplementation.*

| Priority | Item | Notes |
|---|---|---|
| 🔵 | **bXAS Python engine core** | Reimplementation of BlueprintXAS unified background + fitting pipeline in Python. Statistical framework: lmfit + scipy. Error propagation via uncertainties package. Bayesian option: emcee or dynesty |
| 🔴 | **bXAS Workspace window shell** | Non-blocking, non-modal. Communicates via ProjectGraph |
| 🔴 | **Background model builder** | Parameterise pre-edge background (polynomial / Victoreen). Parameters are part of the unified fit |
| 🔴 | **Spectral model composer** | Build model from components; load reference spectra or theoretical spectrum |
| 🔴 | **Fit execution** | Run unified background + spectral fit. Creates provisional BXAS\_RESULT node |
| 🔴 | **Parameter table** | Show fitted values, uncertainties, and bounds for all parameters |
| 🔴 | **Residuals panel** | Plot of fit residuals |
| 🔴 | **Commit result** | Promote provisional BXAS\_RESULT → committed. Result includes fit curve + uncertainty band + residuals as compound object. See OQ-003 |
| 🟡 | **Correlation matrix display** | Heatmap of parameter correlations |
| 🟡 | **Model comparison** | Compare two bXAS models (e.g. different background orders) side by side with fit statistics |
| 🟡 | **Parameter evolution** | Plot fitted parameter values across a series of datasets (e.g. fitting same model to a temperature series) |
| 🟡 | **Parameter sweep** | Automatically generate sweep of models across a parameter range; produces sweep group |

---

## Phase 11 — App-wide Polish

*Depends on Phases 4–10 being substantially complete.*

| Priority | Item | Notes |
|---|---|---|
| 🔴 | **Provenance log panel** | Collapsible bottom panel. Shows committed operations only. Filterable by dataset / operation / engine / time. Clickable entries navigate to node |
| 🔴 | **Project title in window bar** | "[Project name] — Ptarmigan" with unsaved indicator (●) |
| 🔴 | **Autosave** | Autosave provisional state periodically. Offer recovery on next open |
| 🔴 | **Reproducibility report** | File menu → Export Reproducibility Report |
| 🔴 | **Project archive export** | File menu → Export Project Archive (zip of .ptproj/) |
| 🟡 | **Keyboard shortcuts** | Ctrl+Return = commit; Escape = discard; Ctrl+Shift+C = send to Compare; Ctrl+D = discard node; existing project shortcuts retained |
| 🟡 | **Drag-and-drop file loading** | Drop files onto any tab to load as RAW\_FILE node |
| 🟡 | **Clean up unused branches** | Project maintenance action: discard all DISCARDED nodes and their data permanently. Explicit, warned, never automatic |
| 🟢 | **Keyboard shortcut reference** | Help menu → Keyboard Shortcuts |
| 🟢 | **Session persistence for UI state** | Restore last active tab, axis limits, and sidebar scroll position on project open |
| ⚪ | **Reference spectra database** | Useful but large scope; consider linking to external databases |
| ⚪ | **EXAFS shell fitting (Artemis-style)** | Large feature; bXAS may partially address; defer |

---

## Migrated Design Decisions

These are carried forward from the original BACKLOG.md and remain valid.

- **Internal storage as absorbance + nm** — UVVisScan (→ UVVIS DataNode)
  stores wavelength\_nm and absorbance internally; all other
  representations are computed properties.
- **Sticky axis limits as StringVar** — limits stored as StringVar entry
  fields; empty string = auto. Unit conversion normalises through nm.
- **nm axis inversion** — nm axis rendered descending; stored limits as
  (min, max) swapped to set\_xlim(hi, lo) on draw.
- **∀ apply-to-all factory pattern** — \_push\_to\_all(key, get\_fn)
  generates per-parameter callbacks; get\_fn is a zero-argument callable
  read at call time. Carried into unified style dialog.

## Superseded Design Decisions

- **\_exp\_scans as 5-tuple** — eliminated. DataNode replaces all ad-hoc
  tuple structures. This was the source of silent bugs when tuple
  assumptions diverged across files. Its elimination is a specific
  motivation for the node model.
- **~/.binah\_config.json for style persistence** — eliminated. Style
  defaults are stored in the project file and in an app-level defaults
  section of project.json.

---

## Open Questions

See ARCHITECTURE.md Section 15 for full descriptions.

| ID | Topic | Blocks |
|---|---|---|
| OQ-001 | Link groups (investigate in code) | Compare tab design |
| OQ-002 | bXAS uncertainty band schema | Phase 10, Compare phase 7 |
| OQ-003 | bXAS compound result grouping in ScanTreeWidget | Phase 10 |
| OQ-004 | Multi-input operation node UI gesture | Phase 4 (OLIS), Phase 5 (Average) |
| OQ-005 | Replace-or-Add for TDDFT files | Phase 7 (Compare tab) |

---

*Document version: 1.0 — April 2026*
*Supersedes: BACKLOG.md (original)*
