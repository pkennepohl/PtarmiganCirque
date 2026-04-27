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
| `style_dialog.py` | Unified style dialog | ✅ Phase 3 |
| `plot_settings_dialog.py` | Plot Settings dialog | ✅ Phase 4b |

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

> Phase 4a status: every item below is resolved by the loader migration
> and ScanTreeWidget swap that landed in this phase. Strike-throughs
> indicate items now closed.

1. ~~**`self._entries: List[dict]` is the single source of truth**
   ([uvvis_tab.py:129](uvvis_tab.py#L129)) and is indexed positionally.
   Every helper closure in `_rebuild_table` captures `idx=i` from the
   row loop (`_pick`, `_lw_cb`, `_fill_cb`, `_remove_entry`,
   `_open_style_dialog`). Migration converts every `idx`-keyed
   callsite to `node_id`-keyed.~~ **Resolved (Phase 4a Part A):**
   `_entries` deleted; node lookups are graph-driven via
   `_uvvis_nodes()`.
2. ~~**`in_legend` is a separate `tk.BooleanVar`** sitting alongside
   `style` ([uvvis_tab.py:509](uvvis_tab.py#L509)), not inside it. The
   new architecture stores it at `style["in_legend"]`. No project
   files exist yet so the cutover does not need legend-state
   migration.~~ **Resolved (Phase 4a Part A):** `in_legend` and
   `visible` both live at `node.style[...]`; ScanTreeWidget reads
   them directly.
3. ~~**`_PALETTE[idx % len(_PALETTE)]` colour assignment**
   ([uvvis_tab.py:505](uvvis_tab.py#L505)) lives in the loader. With
   the new model, default colour assignment needs to happen at
   DataNode creation time (inside the load-as-RAW\_FILE pipeline) so
   the same node draws the same colour across tabs. Decide where: in
   the loader, or as a graph-side default-style policy.~~
   **Resolved (Phase 4a Part A):** the loader populates
   `style["color"]` at UVVIS-node creation, indexed by the count of
   pre-existing UVVIS nodes. See COMPONENTS.md CS-13 §"Implementation
   notes (Phase 4a)".
4. ~~**`_rebuild_table` is monolithic**
   ([uvvis_tab.py:306-484](uvvis_tab.py#L306)) — header construction
   and every per-row gesture sit inline. A clean migration deletes
   this method entirely along with `_make_leg_btn`, `_make_ls_canvas`,
   `_make_lw_entry` (all reimplemented in
   [scan_tree_widget.py](scan_tree_widget.py)) and replaces them with
   one `ScanTreeWidget(...)` instantiation.~~ **Resolved (Phase 4a
   Part B):** all four helpers and the table are gone; the right pane
   instantiates one `ScanTreeWidget`.
5. ~~**`_redraw` walks `self._entries` directly.** Once entries become
   DataNodes, `_redraw` must traverse the graph (e.g.
   `graph.nodes_of_type(NodeType.UVVIS, state=None)` then filter
   `state != DISCARDED` and `active`) to find what to plot. This
   pattern repeats in every tab; consider a shared helper.~~
   **Resolved (Phase 4a Part A):** `_redraw` now iterates
   `self._uvvis_nodes()` (filter on the graph). The "shared helper
   across tabs" subpoint is deferred — a single tab does not yet
   justify extracting it.
6. ~~**`_remove_entry` deletes from the list**
   ([uvvis_tab.py:525](uvvis_tab.py#L525)) with no scientific record.
   Migration replaces this with `graph.discard_node` (provisional) or
   `graph.set_active(False)` (committed) — exactly what the new ✕
   button does. Audit external callers of `_remove_entry` during the
   cutover.~~ **Resolved (Phase 4a Part B):** `_remove_entry` deleted;
   ScanTreeWidget's ✕ button calls `discard_node`/`set_active(False)`
   directly.
7. ~~**`_open_style_dialog` is inline**
   ([uvvis_tab.py:697](uvvis_tab.py#L697)). Phase 3 builds the unified
   dialog; Phase 4 connects ScanTreeWidget's gear via
   `style_dialog_cb` and deletes the inline implementation.~~
   **Resolved (Phase 4a Part C):** inline `_open_style_dialog`
   deleted; the gear hand-off goes to the unified factory.

### Friction points carried forward from Phase 3

These are concrete obstacles that Phase 4 will hit when it swaps the
inline `_open_style_dialog` for the unified `StyleDialog`. Identified
during Phase 3 while reading the existing dialog as the reference
implementation. **Do not fix until Phase 4** — they are the migration
checklist for that swap-in.

> Phase 4a status: every item below is resolved by the inline-dialog
> deletion and ∀ fan-out callback that landed in this phase.

1. ~~**`win.grab_set()`** ([uvvis_tab.py:707](uvvis_tab.py#L707)) makes
   the inline dialog application-modal. The unified `StyleDialog` is
   modeless by design (no `transient`, no `grab_set`). Migration
   removes the grab — multiple style dialogs across nodes/tabs must
   be allowed to coexist.~~ **Resolved (Phase 4a Part C):** the
   modal grab is gone with the inline dialog; the unified
   `StyleDialog` is modeless.
2. ~~**Per-row `idx`-keyed gear callbacks**
   ([uvvis_tab.py:697](uvvis_tab.py#L697) takes `idx`). After Phase 4
   the `ScanTreeWidget` invokes `style_dialog_cb(node_id)`. The
   migration converts `_open_style_dialog(idx)` to
   `lambda node_id: open_style_dialog(self, self._graph, node_id,
   on_apply_to_all=...)`.~~ **Resolved (Phase 4a Part B + C):**
   `style_dialog_cb=self._open_style_dialog_for_node` calls
   `open_style_dialog(self, self._graph, node_id,
   on_apply_to_all=self._on_uvvis_apply_to_all)`.
3. ~~**`_push_to_all` writes through `e["style"][key]`**
   ([uvvis_tab.py:725-733](uvvis_tab.py#L725)) and explicitly calls
   `self._rebuild_table()` and `self._redraw()` afterwards. The
   migration provides an `on_apply_to_all` callback to `StyleDialog`
   that uses `graph.set_style` for each visible UVVIS node, then
   relies on the existing graph subscription for the redraw.
   `_rebuild_table` and `_redraw` go away when the sidebar becomes
   ScanTreeWidget.~~ **Resolved (Phase 4a Part B + C):**
   `_on_uvvis_apply_to_all(param, value)` writes through
   `graph.set_style` for every visible UVVIS node; the tab's graph
   subscription drives the resulting redraw.
4. ~~**`auto_col = _PALETTE[idx % len(_PALETTE)]`**
   ([uvvis_tab.py:790](uvvis_tab.py#L790)) computes a per-position
   default colour inside the dialog and passes it to the colour
   swatch as the implicit baseline. The unified dialog has no
   palette knowledge; Reset restores the snapshot colour, not a
   palette default. Phase 4 must assign the default colour at
   DataNode creation time (in the loader / load-as-RAW\_FILE
   pipeline) so `node.style["color"]` is non-empty by the time the
   dialog opens. This is the same friction listed as Phase 2 item 3.~~
   **Resolved (Phase 4a Part A):** loader-side default colour
   assignment, see Phase 2 item 3.
5. ~~**`_orig` snapshot lives in the dialog closure**
   ([uvvis_tab.py:839](uvvis_tab.py#L839)) and is restored by
   `style.update(_orig)` in `_do_cancel`. Replaced wholesale by
   `StyleDialog._snapshot` and the `set_style(snapshot)` revert path.
   Note the same merge-can't-remove-keys limitation applies in both
   implementations and is documented in CS-05 Implementation notes.~~
   **Resolved (Phase 4a Part C):** the closure snapshot is gone with
   the inline dialog; `StyleDialog._snapshot` is now the only
   revert path.
6. ~~**Dialog reads from `entry["style"]` and `entry["scan"]` dicts**
   ([uvvis_tab.py:701-702](uvvis_tab.py#L701)). After migration the
   dialog reads from `graph.get_node(node_id).style` exclusively; the
   `_entries` list disappears as part of the broader Phase 4
   restructure.~~ **Resolved (Phase 4a Part A + C):** `_entries`
   deleted; the unified dialog reads through `graph.get_node`.
7. ~~**`_do_save` calls `_do_apply()` then `win.destroy()`**
   ([uvvis_tab.py:870-871](uvvis_tab.py#L870)). The unified dialog
   has the same flow but lives in `StyleDialog._do_save`. Phase 4
   simply deletes the inline `_open_style_dialog` method (~175 lines)
   and the `_LS_OPTIONS` constant if not needed elsewhere; the
   gear-button hand-off is already in `ScanTreeWidget`
   (`style_dialog_cb` parameter).~~ **Resolved (Phase 4a Part C):**
   ~175 lines + `_LS_OPTIONS` + `_LS_CYCLE`/`_LS_DASH` + `_ToolTip`
   helper deleted.

### Friction points carried forward from Phase 4a

These are concrete obstacles the next Phase 4 session will hit when
it adds baseline correction, normalisation-as-operation, or wires
Send-to-Compare. Identified during Phase 4a while migrating the
loader and sidebar onto the new architecture. **Do not fix until
the relevant subsequent Phase 4 session** — they need to be
addressed in the same change that introduces the new operation/
feature.

> Phase 4b status: friction point #7 (Plot Settings dialog has no
> host yet) is resolved by the ⚙ button + dialog landed in this
> session. Items #1, #2, #3, #5, and #6 remain open. Item #4
> (graph-side view config) was the entry point for #7 and is now
> partially answered: Plot Settings sidesteps the question by living
> in tab-private state. The broader graph-side view-state question
> is still open and now interlocks with persistence (BACKLOG below).

1. **No `BASELINE_*` `OperationType` variants beyond the existing
   `BASELINE`.** [nodes.py:96](nodes.py#L96) lists a single
   `BASELINE` `OperationType`, but Phase 4 (BACKLOG) calls for four
   distinct baseline modes — linear, polynomial, spline, and
   rubberband/convex hull — each with materially different `params`
   schemas. The next session needs to either (a) keep one
   `OperationType` and discriminate via `params["mode"]`, or (b)
   split into four variants. CS-03 §"Params completeness requirement"
   bites either way: define the schema before implementing the UI.
2. **Normalisation has no UI for parameter capture.** Existing
   top-bar combobox `_norm_mode` (`none`/`peak`/`area`) at
   [uvvis_tab.py:170](uvvis_tab.py#L170) is currently a *display*
   transform applied at draw time, not an operation node. Migrating
   it to a `NORMALISED` `OperationType` (CS-03) means deciding where
   the user enters the parameter (peak position, integration window
   bounds) — top-bar combobox does not have room. Likely lands on
   the left panel per CS-07 §"UV/Vis left panel". Until then, the
   existing draw-time transform stays; new normalisation modes
   (interactive normalisation, normalisation to wavelength) need the
   left panel.
3. **Send-to-Compare needs the Compare tab to exist.** ScanTreeWidget
   is constructed with `send_to_compare_cb=None`
   ([uvvis_tab.py:333](uvvis_tab.py#L333)), so the right-click "Send
   to Compare" menu entry renders disabled (CS-04 implementation
   notes). The toolbar's "+ Add to TDDFT Overlay" button is still
   wired to the legacy `_add_scan_fn` callback. Phase 7 builds the
   Compare tab and wires `send_to_compare_cb` to a
   `compare_tab.add_node(node_id)` style hand-off; the toolbar
   button retires at the same time.
4. **No graph subscription for the toolbar/limit-bar UI state.** The
   unit radio buttons and limit entry fields call `self._redraw()`
   directly rather than going through the graph. That is correct —
   axis units and entry-field values are tab-private UI state, not
   graph state — but it means a future session that introduces a
   shared "view config" (e.g. sticky axis limits saved with the
   project) will need to decide where that state lives. The choice
   is between a per-tab UI-state dict in `project.json` vs. a
   graph-side `view_state` payload on each node. Out of scope for
   Phase 4 baseline/normalisation but flagged here so the
   Plot-Settings session has a starting point.
5. **`_add_selected_to_overlay` still constructs `ExperimentalScan`
   from graph nodes.** [uvvis_tab.py:613](uvvis_tab.py#L613) reads
   `node.arrays` and `node.metadata` and synthesises an
   `ExperimentalScan` for the legacy TDDFT-overlay shim. This works
   but means UV/Vis values cross the graph boundary twice (out, then
   into the TDDFT plot's parallel state). Phase 7 deletes both
   sides: Compare consumes the UVVIS DataNode directly. Until then
   the shim is correct but inefficient.
6. **Default `node.style` lives in two places.** The loader's
   `_default_uvvis_style` ([uvvis_tab.py](uvvis_tab.py)) and
   `scan_tree_widget._DEFAULT_STYLE`
   ([scan_tree_widget.py:100](scan_tree_widget.py#L100)) are kept in
   sync by hand. Sane today (six keys, both places set them
   identically), but bound to drift. The cleanest fix is for the
   loader to import the widget defaults — deferred because the
   ScanTreeWidget defaults map is currently module-private and
   exposing it pulls a UI module into the loader's import graph.
   Revisit when XANES/EXAFS migrations need their own defaults.
7. ~~**Plot Settings dialog has no host yet.** The top bar still owns
   per-axis labels, grid, and other plot-level controls inline (the
   existing toolbar layout is unchanged in Phase 4a). The deferred
   Phase 4 session that introduces the ⚙ Plot Settings dialog
   (per CS-06 / ARCHITECTURE.md §3) needs to relocate those controls
   without breaking the existing entry-field bindings (sticky
   limits, unit conversion). Mention the unit-conversion code path
   ([uvvis_tab.py:78-94](uvvis_tab.py#L78)) when planning that
   move.~~ **Resolved (Phase 4b):** ⚙ Plot Settings button added to
   the toolbar, opening `PlotSettingsDialog` (CS-14). The legacy
   inline controls remained in the top bar per CS-06 (axis units,
   sticky limits, normalisation) — only the *new* plot-level
   controls (fonts, grid, background, legend show/position, tick
   direction, title/label text) live in the dialog.

### Friction points carried forward from Phase 4b

These are concrete obstacles the next Phase 4 session will hit when
it wires Plot Settings persistence to `project.json`, extends Plot
Settings to other tabs, or wires Send-to-Compare. Identified during
Phase 4b while integrating the dialog into the UV/Vis pilot tab.
**Do not fix until the relevant subsequent Phase 4 session.**

1. **`_USER_DEFAULTS` is process-lifetime only.** Save-as-Default
   writes to `plot_settings_dialog._USER_DEFAULTS`
   ([plot_settings_dialog.py:152](plot_settings_dialog.py#L152)),
   which evaporates on app restart. CS-13 §"Implementation notes"
   already documents that project I/O lands later; the work needed
   here is a load-time read from `project.json["plot_defaults"]`
   into `_USER_DEFAULTS`, plus a save-time write back. The dialog
   needs no API changes — only `project_io` and `binah.py` glue.
2. **Plot Settings is wired only into UV/Vis.** Phase 4b is
   UV/Vis-only by design. Each subsequent tab (XANES, EXAFS,
   Compare) needs the same three changes: a `self._plot_config`
   dict, a ⚙ button in the toolbar, and a `_redraw` rewrite to
   read from the config. The `_redraw` rewrite is the bulk of the
   work — see [uvvis_tab.py:613-696](uvvis_tab.py#L613) for the
   reference. Each tab's auto-derived axis labels (XANES energy,
   EXAFS k/R-space, Compare's mixed units) need their own
   tab-specific defaults; the dialog itself is unchanged.
3. **Auto-derived label text is recomputed inside `_redraw` every
   time.** When `xlabel_mode == "auto"` the tab computes the
   X-label text from the current x-unit
   ([uvvis_tab.py:660-673](uvvis_tab.py#L660)). This is fine for
   UV/Vis but means the dialog's entry shows the user's last
   *custom* text even when the mode is "auto" — the dialog has no
   way to display the auto-derived value. A future session might
   add an `auto_label_provider` callback so the entry can show the
   current auto value as ghost text; for now the small `(auto)` /
   `(custom)` / `(none)` mode indicator is the only visible cue.
4. **`background_color` factory default is `#ffffff` but
   `_draw_empty` still uses `#f8f8f8`.** The empty-state placeholder
   ([uvvis_tab.py:573-581](uvvis_tab.py#L573)) is unchanged, so a
   user who picks a non-white background sees their colour only
   when at least one spectrum is loaded. Whether the empty-state
   should also pick up the configured background is a UX decision —
   the placeholder text is grey, which may be unreadable on some
   colours. Flag for the project-I/O session.
5. **No persistence handle for `_plot_config` either.** Each tab's
   `_plot_config` ([uvvis_tab.py:166-179](uvvis_tab.py#L166)) is
   currently rebuilt from `_USER_DEFAULTS` on every tab construction.
   When project I/O lands the project file should carry per-tab
   plot configs alongside the graph; otherwise reopening a project
   discards the user's plot choices. Probably a `project.json`
   `tabs[uvvis].plot_config = {...}` payload. CS-13 needs to grow
   a `tabs` section to host it.
6. **Mode indicators inside the Title-and-labels section are
   small.** The `(auto)` / `(custom)` / `(none)` Label is only 8pt
   text and easy to miss
   ([plot_settings_dialog.py:344-349](plot_settings_dialog.py#L344)).
   Acceptable for the pilot but worth revisiting once we see a real
   user trip over it. Possible upgrade: bold/coloured chip, or
   ghost-text in the entry showing the auto value.
7. **Graph-side view-state question is unanswered.** Phase 4a
   friction #4 flagged the choice between per-tab UI state in
   `project.json` vs. graph-side `view_state` per node. Phase 4b
   chose tab-private storage (sidesteps the question). When XANES
   and EXAFS migrate, they will face the same call; if they all
   choose tab-private then `view_state` per node is dead and we
   should formally close the question. If any tab needs per-node
   view state (e.g. Compare overlays where different nodes use
   different tick styles) the graph-side payload returns. Revisit
   in Phase 5/7.

| Status | Priority | Item | Notes |
|---|---|---|---|
| ✅ | 🔴 | **Migrate UV/Vis to node model** | UVVisScan → DataNode(type=UVVIS). File load → RAW\_FILE + LOAD + UVVIS triple, all COMMITTED (Phase 4a Part A; CS-13 implementation notes) |
| ✅ | 🔴 | **Replace UV/Vis sidebar with ScanTreeWidget** | Retire existing compact grid table; ScanTreeWidget is the replacement (Phase 4a Part B) |
| ✅ | 🔴 | **Replace UV/Vis style dialog with unified style dialog** | Existing UV/Vis style dialog is the reference; unified dialog supersedes it (Phase 4a Part C) |
| ⏳ | 🔴 | **Baseline correction** | Linear (two-point), polynomial (order n), spline, rubberband/convex hull. Each application creates a provisional BASELINE node |
| ⏳ | 🔴 | **Export processed data** | Save committed node data to CSV or TXT; include provenance header |
| ⏳ | 🔴 | **Normalisation as explicit operation** | Normalisation creates a provisional NORMALISED node rather than modifying data in place |
| ⏳ | 🔴 | **"Send to Compare" action** | Replaces "Add to TDDFT Overlay". Available on committed nodes |
| ✅ | 🔴 | **Plot Settings dialog** | Fonts, grid, background colour, legend position, tick direction, title/label customisation. Accessed via ⚙ in top bar (Phase 4b; CS-14) |
| ⏳ | 🟡 | **Peak picking** | Click-to-mark peaks; λ/E annotation; optional peak table export |
| ⏳ | 🟡 | **OLIS integrating sphere correction** | Three-input operation node (sample + reference + blank → corrected). See OQ-004 for multi-input UI design |
| ⏳ | 🟡 | **Interactive normalisation** | Normalise to user-specified wavelength or integration region |
| ⏳ | 🟡 | **Difference spectra** | Two-input operation node. See OQ-004 |
| ⏳ | 🟡 | **Smoothing** | Savitzky-Golay or moving average; creates provisional SMOOTHED node |
| ⏳ | 🟢 | **Second derivative** | Creates provisional node; useful for resolving overlapping bands |
| ⏳ | 🟢 | **Beer-Lambert / concentration** | Use known ε to extract concentration, or fit ε from known concentration |

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

## Known Bugs (logged 2026-04-27 — post Phase 4b manual testing)

These were discovered while manually exercising the UV/Vis tab after
Phase 4b landed. Each is assigned to a phase to resolve in. The
"focused fix" assignments grant explicit authorisation for the named
phase to touch files that its primary brief lists as no-modify.

| ID | Severity | Bug | Spec ref | Resolve in |
|---|---|---|---|---|
| **B-001** | 🟡 | History expansion (`⌥n` click on a sidebar row) renders at the bottom of the sidebar instead of inline below the clicked row. With two datasets loaded, clicking the top row's history shows expanded entries below the *second* row, making the visual association ambiguous | CS-04 §6.2 ("inline, below row") | **Phase 4c** focused fix in `scan_tree_widget.py` |
| **B-002** | 🔴 | Sidebar row controls do not adapt to sidebar width. At narrow widths the row overflows. The minimum always-visible set should be: dataset name + visibility checkbox + ⚙ gear button. Every other per-row control (colour swatch, legend toggle, linestyle canvas, linewidth entry, fill checkbox, history indicator, ✕) must collapse when the row narrows. The unified StyleDialog (CS-05) must then cover every collapsed control — which it currently does not: `style["visible"]` and `style["in_legend"]` have no controls in the dialog | CS-04 §6.1 + CS-05 universal section | **Phase 4d** dedicated session (responsive row + StyleDialog completeness) |
| **B-003** | 🟡 | When `Norm: area` is active the X-axis limit entries no longer take effect on Apply / Return. `Norm: none` and `Norm: peak` both work. Likely interaction between `_y_with_norm`'s area integral and the post-render axis-limit application path in `_redraw` ([uvvis_tab.py:583-593](uvvis_tab.py#L583), [uvvis_tab.py:662-671](uvvis_tab.py#L662)) — verify before fixing | UV/Vis tab `_redraw` | **Phase 4c** focused fix in `uvvis_tab.py` |
| **B-004** | 🟡 | No way to rename a dataset from the right sidebar via the right-click menu. CS-04 §"Context menu" lists `Rename` as a right-click entry; the implementation only landed Commit / Discard / Send to Compare. In-place double-click rename exists per Phase 2 but is undiscoverable. Add the context-menu entry; consider a label tooltip pointing at it | CS-04 §"Context menu" | **Phase 4c** focused fix in `scan_tree_widget.py` |

The Phase 4d responsive-row work (B-002) also needs to add `visible`
and `in_legend` controls to the StyleDialog universal section so the
collapsed row's controls remain reachable through the dialog.

Newly discovered bugs go in this table with a fresh `B-NNN` id and a
phase assignment. Resolved bugs get a ✅ in the Severity column with
the resolving phase + commit SHA appended to the row.

---

*Document version: 1.1 — April 2026*
*1.1: Known Bugs register added 2026-04-27 after Phase 4b manual testing.*
*Supersedes: BACKLOG.md (original)*
