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

## Session structure (added end of Phase 4i)

Every phase session follows this shape. The bug-elicitation step
between commits 5 and 6 is **mandatory** — it lets the user fold
in friction they noticed during the session before the BACKLOG
freezes for the hand-off, so issues are not lost between threads.

1. **Verification block** — confirm the previous phase's merge
   SHA is on origin, expected files are present, full suite is
   green. STOP and report on any mismatch.
2. **Decision lock** — for the chosen task, record the design
   decisions explicitly (NodeType vs metadata flag, mode-keyed
   vs single-algorithm, parent set, render path). These go in
   the COMPONENTS.md notes at bookkeeping time.
3. **Commits 1–N** — pure module → tests → integration code →
   integration tests → run-suite verification. Single-input
   UV/Vis operations are six commits; Send-to-Compare-shaped
   tasks are four. Tailor the count to the task; the order is
   fixed.
4. **Run full suite** — must be green before proceeding.
5. **Bug / issue / feature elicitation** — pause and explicitly
   ask the user: *"Any new bugs, issues, or feature ideas to
   add to the BACKLOG before we freeze the docs?"* Surface what
   you noticed during the session (left-pane density, palette
   duplication, slow status messages, a mode that felt
   awkward, …) so the user can confirm or extend. Wait for the
   user's answer before continuing.
6. **Bookkeeping commit** — update BACKLOG.md (mark item ✅,
   add the friction list **including any user-flagged items
   from step 5**) and COMPONENTS.md (new CS-N section,
   doc-version footer bumped).
7. **Merge into redesign/main** in the integration worktree
   (`git merge --no-ff redesign/phase-XX-task-name`). Use the
   established message format: subject + brief intro +
   deliverables list + "Resolved during the session" +
   Co-Authored-By trailer.
8. **Push redesign/main to origin** (never force-push).
9. **End-of-session report** — five sections: test count,
   manual smoke (or "covered by integration tests"), design
   decisions taken for spec ambiguities, friction the next
   session will hit, final git status.
10. **Hand-off brief** — wrap the next-session prompt in **one
    fenced code block** (no nested fences) so the user can
    copy-paste it straight into the next /init prompt. The
    brief must include the verification block, the "do not
    touch" lock list scoped to the next intent, and re-state
    the session structure above (so the loop self-perpetuates).

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

1. ~~**No `BASELINE_*` `OperationType` variants beyond the existing
   `BASELINE`.** [nodes.py:96](nodes.py#L96) lists a single
   `BASELINE` `OperationType`, but Phase 4 (BACKLOG) calls for four
   distinct baseline modes — linear, polynomial, spline, and
   rubberband/convex hull — each with materially different `params`
   schemas. The next session needs to either (a) keep one
   `OperationType` and discriminate via `params["mode"]`, or (b)
   split into four variants. CS-03 §"Params completeness requirement"
   bites either way: define the schema before implementing the UI.~~
   **Resolved (Phase 4c):** kept one `OperationType.BASELINE` and
   discriminate via `params["mode"]`; the four mode sub-schemas
   are documented in CS-15 along with the linear/polynomial/spline/
   rubberband algorithms. Params completeness verified by the
   integration tests in `TestUVVisTabBaseline`.
2. ~~**Normalisation has no UI for parameter capture.** Existing
   top-bar combobox `_norm_mode` (`none`/`peak`/`area`) at
   [uvvis_tab.py:170](uvvis_tab.py#L170) is currently a *display*
   transform applied at draw time, not an operation node. Migrating
   it to a `NORMALISED` `OperationType` (CS-03) means deciding where
   the user enters the parameter (peak position, integration window
   bounds) — top-bar combobox does not have room. Likely lands on
   the left panel per CS-07 §"UV/Vis left panel". Until then, the
   existing draw-time transform stays; new normalisation modes
   (interactive normalisation, normalisation to wavelength) need the
   left panel.~~ **Resolved (Phase 4e):** kept one
   `OperationType.NORMALISE` and discriminate via `params["mode"]
   ∈ {"peak", "area"}` (mirrors CS-15). The new `NormalisationPanel`
   lives in `uvvis_normalise.py` and packs into the left panel
   below the baseline section (Part C 1e7afee, Part E ba17ef4;
   CS-16). The legacy top-bar `Norm:` combobox + `_y_with_norm`
   draw-time transform retired in Part E.
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

### Friction points carried forward from Phase 4c

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4c while implementing baseline correction
and bundling the focused fixes for B-001 / B-003 / B-004. **Do not
fix until the relevant subsequent Phase 4 session.**

1. **No row-selection model on `ScanTreeWidget`.** The baseline
   left panel uses a subject combobox listing every live UVVIS /
   BASELINE node rather than reading a "selected row" from the
   right sidebar (which has no selection state today). Adding a
   selection model would let the left panel auto-track the user's
   focus, but it widens the widget's surface noticeably. Revisit
   when a second user-initiated operation lands (smoothing, peak
   picking) and the duplicated combobox starts to feel like a
   pattern.
2. **Anchor capture from the plot is keyboard-only.** Linear,
   polynomial, and spline modes require nm anchor wavelengths;
   today the user types them in. A click-on-axis gesture
   ("crosshair" mode) would be a major UX win but requires
   matplotlib `mpl_connect` plumbing on the centre figure plus a
   way to wire each anchor to its specific Tk variable. Out of
   scope for Phase 4c; flag for the smoothing / peak-picking
   session.
3. **No live preview.** Each Apply produces a fresh provisional
   node. Iterating means discard + re-apply. A dialog-style
   "preview while sliders move" affordance would feel snappier
   but conflicts with the provisional-node model (every preview
   would mutate or create a node). Decision deferred until the
   user reports it as friction.
4. **Spline anchors are a comma-separated string.** The Tk Entry
   accepting `"250, 350, 620, 750"` is the simplest UI but
   doesn't validate until Apply. A list-managed widget (add /
   remove / drag-reorder rows) is what CS-07 would prefer; the
   spline mode is the only one that needs it. Revisit if the
   peak-picking / smoothing sessions land widgets we can reuse.
5. **`_PALETTE` is duplicated logic between UVVIS load and
   BASELINE Apply.** Both paths index `_PALETTE` to pick a
   default colour. Today it's two two-line snippets, but a third
   path (smoothing, normalisation-as-operation) will make the
   third copy. Probably extract to a `_pick_default_color(graph)`
   helper at that point.
6. **`_uvvis_nodes` vs. `_spectrum_nodes` divergence.** The tab
   now has two near-identical helpers — UVVIS-only (used by
   `_has_existing_load` and the ∀ apply-to-all callback) and
   UVVIS+BASELINE (used by `_redraw`, the subject combobox).
   This is fine today but will calcify into a bigger split if
   normalisation-as-operation introduces a `NORMALISED` node
   type the tab also wants to render. Revisit then.
7. **Legacy "+ Add to TDDFT Overlay" button still synthesises
   from UVVIS only.** `_add_selected_to_overlay` reads
   `self._uvvis_nodes()` and silently skips BASELINE nodes —
   correct today (overlay has no BASELINE knowledge) but the
   shim retires when Phase 7 wires Send-to-Compare. No action
   for Phase 4d/4e.

### Friction points carried forward from Phase 4d

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4d while implementing the responsive row
collapse and StyleDialog completeness for B-002. **Do not fix
until the relevant subsequent Phase 4 session.**

1. **Responsive collapse threshold is hard-coded.**
   `_RESPONSIVE_COLLAPSE_PX = 280` lives at module level in
   `scan_tree_widget.py`. Calibrating it per-display would mean
   binding to the host's DPI / font scaling; today a single value
   is fine because the sidebar widths Tabs use are within the same
   order of magnitude. Revisit if a future tab packs the widget
   into a noticeably different host (e.g., a popover) or if the
   user reports controls collapsing on a comfortable sidebar.
2. **No hysteresis on the collapse threshold.** Crossing 280 px
   either way fires immediately. With a sidebar widget that
   resizes its rows in response to its own contents this could
   oscillate, but in practice the row's `fill="x"` and the host's
   externally-imposed sidebar width keep things stable. If
   oscillation is reported, add a hysteresis margin (e.g.,
   collapse at 280, restore at 340).
3. **`_DEFAULT_STYLE` lives in two places.** Phase 4c friction
   point #6 already flagged this — `scan_tree_widget._DEFAULT_STYLE`
   and `style_dialog._UNIVERSAL_DEFAULTS` carry overlapping
   defaults for the universal style keys. Phase 4d added
   `visible` and `in_legend` to both tables in lockstep; the
   duplication is now larger but still manageable. A single
   shared module (`node_styles.py`?) would eliminate the drift
   risk. Revisit when a third caller (e.g., a save/load
   round-trip) needs the same defaults.
4. **Bulk ∀ exclusion list is a tuple in code, not a derived
   property.** `_BULK_UNIVERSAL_KEYS` enumerates the keys the
   bottom button fans out. Adding a new universal key means
   editing both `_UNIVERSAL_DEFAULTS` and (if the key should be
   bulk-applied) `_BULK_UNIVERSAL_KEYS`. The exclusion of
   `colour` / `visible` / `in_legend` is documented but
   easy to mis-match. Consider a richer registry (`{key: {bulk:
   bool, default: ...}}`) when a fifth or sixth key joins.
5. **UV/Vis fan-out scope is now `_spectrum_nodes`, but
   `_has_existing_load` and the legacy "+ Add to TDDFT Overlay"
   button still read `_uvvis_nodes`.** Phase 4c friction point
   #6 noted the `_uvvis_nodes` / `_spectrum_nodes` divergence
   would calcify; Phase 4d's widening narrowed the divergence
   to two callers. Both are correct today (load duplicate-check
   is UVVIS-specific; the overlay shim retires with Phase 7
   Send-to-Compare). No action for Phase 4e — flag for whoever
   touches the load path or Send-to-Compare.

### Friction points carried forward from Phase 4e

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4e while implementing
normalisation-as-operation and resolving Phase 4a friction point
#2. **Do not fix until the relevant subsequent Phase 4 session.**

1. **`_default_*_style` lives in three places.** Phase 4d friction
   point #3 already flagged the duplication between
   `scan_tree_widget._DEFAULT_STYLE` and
   `style_dialog._UNIVERSAL_DEFAULTS`; Phase 4e adds a third copy
   in `uvvis_normalise._default_normalised_style` (mirrors the
   `uvvis_tab._default_uvvis_style` pattern carried forward from
   Phase 4c). Carried forward per the Phase 4e brief; the smell is
   now visible across three modules. A single shared module
   (`node_styles.py`?) becomes the obvious extraction when the
   fourth caller lands (Phase 5 XANES smoothing, deglitch, or
   shift-energy operations all need the same default).
2. **`_PALETTE` index expression duplicated three times now.**
   Phase 4c friction point #5 flagged the original duplication
   (UVVIS load + BASELINE Apply); Phase 4e adds a third (NORMALISE
   Apply: `_PALETTE[(n_uvvis + n_baseline + n_normalised) %
   len(_PALETTE)]`). Each new spectrum-producing operation will
   widen the index expression. The cleanest extraction is a
   `_pick_default_color(graph)` helper that walks every spectrum
   NodeType and picks the next palette entry. Revisit when a fourth
   spectrum-producing operation lands (smoothing or interactive
   normalisation).
3. **Window endpoints are required nm Entry fields; no
   click-on-axis capture.** Phase 4c friction point #2 flagged
   anchor capture for baseline; the same gesture would benefit
   normalisation (the user often wants to drag a window over a
   visible peak rather than type 400 / 600 nm). Out of scope for
   Phase 4e per the brief; flag for the smoothing / peak-picking
   session that owns the `mpl_connect` plumbing.
4. **No live preview as window endpoints change.** Like Phase 4c
   friction point #3 (baseline), the panel forces discard +
   re-apply to iterate. The provisional-node model conflicts with
   "preview while sliders move" — every preview would mutate or
   create a node. Decision deferred until a user reports it as
   friction.
5. **The status-bar API is fragmented.** The baseline section
   updates `self._status_lbl.config(...)` inline; the
   `NormalisationPanel` calls back through `_set_status_message`
   on the host. Both work, but a future session adding a third
   user-initiated operation (smoothing, deglitch on UV/Vis) should
   pick one convention and migrate the other. The callback shape
   is the cleaner of the two.
6. **`OperationType.NORMALISE` is overloaded across techniques.**
   The Phase 4e brief picked the existing
   `OperationType.NORMALISE` (originally meant for XANES Larch
   normalisation) and reused it for UV/Vis with a different
   `params` schema. The discriminator is the OperationNode's input
   NodeType (UVVIS/BASELINE/NORMALISED → UV/Vis params; XANES →
   Larch params), not anything stored in the op itself. Phase 5
   (XANES) will need to either accept the overload (params shape
   inferred from inputs) or split into `NORMALISE_LARCH` /
   `NORMALISE_UVVIS`. Flagging here since Phase 4e set the
   precedent.

### Friction points carried forward from Phase 4f

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4f while implementing single-node export.
**Do not fix until the relevant subsequent Phase 4 session.**

1. **`node_export._resolve_columns` is UV/Vis-shaped only.** Phase
   4f exports UVVIS / BASELINE / NORMALISED via
   `wavelength_nm` + `absorbance`; XANES (`energy`, `mu`) and
   EXAFS (`k`, `chi`) raise `ValueError`. The cleanest extension
   point is a `NodeType → (col_names, array_keys)` registry the
   tab plugs into at startup, so `node_export` stays
   technique-agnostic. Resolve when Phase 5 / 6 land their first
   exportable node types.
2. **Export is per-row, not per-selection.** The Phase 4f brief
   explicitly forbade adding a row-selection model (Phase 4c
   friction point #1) and forbade multi-node "Export selection".
   Both decisions interlock: a per-selection export needs a
   selection state on `ScanTreeWidget`. Carry both forward
   together.
3. **Provenance header timestamp is the *export* time, not the
   commit time.** The header records `exported_at=<UTC now>`,
   meaning two exports of the same committed node carry different
   timestamps. The committed node's `created_at` (DataNode) and
   the OperationNode's `timestamp` are the science-relevant
   moments and are NOT in the header today. Adding them is
   straightforward (one extra envelope line + two more fields per
   ancestor) but the header was kept lean for this first cut.
   Revisit when project save (CS-13) lands and needs to round-trip
   commit-time information.
4. **`# `-prefixed CSV header is a CSV-spec violation.** RFC 4180
   does not define comment lines. `pandas.read_csv` accepts
   `comment="#"`, but spreadsheet apps (Excel, Numbers) will
   render the header as data rows. The TXT format is fine
   (downstream tools that read tab-separated data tend to be more
   tolerant or already use `#` as a comment). If Excel friendliness
   becomes a requirement, options are: (a) write an `.xlsx`
   instead of `.csv`, (b) write a sidecar `.json` for the
   provenance, (c) move the header into a second
   `<basename>.provenance.txt` file. Decision deferred until a
   user reports it as friction.
5. **Sanitised-basename collision is silent.** Two committed
   nodes with the same label produce the same default
   `initialfile`; if the user accepts the default twice, the
   second export silently overwrites the first (`asksaveasfilename`
   surfaces an OS-level "replace?" prompt on most platforms, so
   data loss is unlikely, but the gesture is noisier than it
   needs to be). A future polish session could append a
   short-hex disambiguator to the basename.
6. **`OperationNode.params` JSON dump uses `default=str`.** Numpy
   scalars or any non-JSON-primitive that slipped past CS-03's
   "must be JSON-serialisable" rule serialise as their `repr`,
   which round-trips as a string — not the original numeric. No
   such cases exist today (BASELINE / NORMALISE params are pure
   Python floats / strings), but the fallback hides a future
   schema regression. Phase 5 / 6 should pin a stricter
   serialiser when params shapes widen.

### Friction points carried forward from Phase 4g

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4g while implementing smoothing-as-operation
and extracting `node_styles.default_spectrum_style` as the
four-caller threshold sibling commit. **Do not fix until the
relevant subsequent Phase 4 session.**

1. **`_PALETTE` is now duplicated in four modules.** Phase 4c
   friction point #5 / Phase 4e friction point #2 flagged the
   duplication; Phase 4g adds a fourth copy in
   `uvvis_smoothing._PALETTE` and a fourth term in the
   `_PALETTE[(n_uvvis + n_baseline + n_normalised + n_smoothed) %
   len(_PALETTE)]` index expression. The cleanest extraction is a
   `_pick_default_color(graph)` helper that walks every
   spectrum-shaped NodeType and picks the next palette entry; the
   helper would also subsume the `n_X` count list. Defer until a
   fifth caller lands (Phase 5 XANES smoothing or deglitch on
   UV/Vis), or pair with the Send-to-Compare session if it touches
   the same files.
2. **The status-bar API split persists.** Phase 4e friction point
   #5 noted that the baseline section updates
   `self._status_lbl.config(...)` inline while the
   `NormalisationPanel` calls back through `_set_status_message`.
   The new `SmoothingPanel` follows the cleaner callback shape, so
   two of three sections are now on the callback path. Migrating
   the inline baseline path is a one-commit sweep but stays out of
   this session's scope per the Phase 4g brief (no-touch list
   includes `uvvis_baseline`).
3. **`SmoothingPanel` reflects the same "no row-selection model"
   workaround as baseline / normalisation.** Phase 4c friction
   point #1 / Phase 4e friction point's subject-combobox carried
   forward — three left-panel subwidgets now host their own
   subject combobox. The pattern is now visible enough that a
   single shared `SubjectComboboxAdapter` (or, as Phase 4c
   originally suggested, a row-selection state on
   `ScanTreeWidget`) would be a real cleanup. Revisit with
   peak-picking (the fourth subject-list caller).
4. **`OperationNode.params` carries `int` for `window_length` /
   `polyorder` instead of resolved-type-tagged values.** Phase 4f
   friction point #6 already flagged the `default=str` JSON
   fallback; SMOOTH params are pure Python ints / strings so they
   round-trip cleanly today, but a future XANES smoothing session
   that wants `Decimal` precision (e.g., for k-window roll-off
   tapers) will hit the same fallback. Phase 5 / 6 should pin a
   stricter serialiser when params shapes widen.
5. **The four panels in the left pane are now visually crowded.**
   The left pane stacks Baseline (subject + mode + per-mode rows +
   button), Normalisation (subject + mode + window rows + button),
   Smoothing (subject + mode + per-mode rows + button) for a total
   of three near-identical sections — and Phase 5 / 6 / OLIS
   correction will add more. Even with the horizontal separators
   the visual hierarchy is starting to flatten. Possibilities for
   a future polish session: collapsible sections per CS-07
   §"left-panel layout grammar", a dropdown that selects "active
   operation" and renders only that section, or a mini-tab strip
   inside the left pane. Decision deferred until a user reports
   it as friction.
6. **`scan_tree_widget._DEFAULT_STYLE` /
   `style_dialog._UNIVERSAL_DEFAULTS` still carry the same eight
   keys as `node_styles.default_spectrum_style`.** Phase 4g
   extracted the spectrum-producing default into the new module
   but kept the two UI-side fallback maps in their original
   widget files (their role is "fallback when `node.style` is
   missing a key", not "factory dict for fresh node creation").
   The duplication is small (one additional key set in two
   places) and the role split is real, so the carry-forward is
   intentional. Revisit if the universal-key list grows further
   or if a future tab needs a non-spectrum style schema (e.g.,
   FEFF paths) where the fallback maps would diverge from the
   spectrum factory anyway.

### Friction points carried forward from Phase 4h

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4h while implementing peak picking and
landing the first non-curve DataNode (PEAK_LIST) in the UV/Vis
path. **Do not fix until the relevant subsequent Phase 4 session.**

1. **`_PALETTE` is now duplicated in five modules.** Phase 4c
   friction #5 / Phase 4e friction #2 / Phase 4g friction #1
   tracked the duplication; Phase 4h adds the fifth copy in
   `uvvis_peak_picking._PALETTE` and a fifth term in the
   `_PALETTE[(n_uvvis + n_baseline + n_normalised + n_smoothed +
   n_peak_list) % len(_PALETTE)]` index expression. Same cleanest
   extraction sketched in Phase 4g friction #1: a
   `_pick_default_color(graph)` helper that walks every
   spectrum-shaped or annotation NodeType and picks the next
   palette entry. Defer until a sixth caller lands (Phase 5 XANES
   migration is the natural next palette consumer) or pair with
   the next Phase 4 polish session that touches the same files.
2. **`_on_uvvis_apply_to_all` does not fan out to PEAK_LIST.**
   The unified style dialog's "apply to all" button writes a
   single style key onto every node returned by
   `_spectrum_nodes()` — UVVIS / BASELINE / NORMALISED /
   SMOOTHED. PEAK_LIST is intentionally absent from that walk
   (CS-19), but the user's mental model for ∀ is probably "every
   row in the sidebar". For colour-style keys this is correct
   behaviour (peak markers usually want a colour distinct from
   their parent). For the universal `visible` / `in_legend`
   toggles it is debatable — if the user toggles "visible off"
   on a UVVIS row's ∀, they probably expect the sibling PEAK_LIST
   to disappear too. Decision deferred until a user reports it
   as friction; the cleanest fix is a per-key fan-out scope
   (curve-style keys → `_spectrum_nodes`; visibility / legend
   keys → every sidebar row).
3. **PEAK_LIST style schema reuses the eight curve-style universal
   keys but only four (color / alpha / visible / in_legend) have
   a scatter analogue.** The remaining four (linestyle, linewidth,
   fill, fill_alpha) are stored on the node and exposed by the
   StyleDialog (CS-05) but the renderer ignores them for scatter.
   The user can edit them with no visible effect, which is mildly
   confusing. A bespoke peak-marker schema (`marker_size`,
   `marker_shape`, `edgewidth`, ...) would resolve this but adds
   the per-node-type style schema CS-05 was designed to avoid.
   Revisit if a "peak label font" or "marker shape" request lands
   from a user.
4. **Click-on-plot to add a peak is unimplemented.** The Phase 4h
   brief explicitly scoped peak picking to the prominence +
   manual-list modes. Click-on-plot is the natural extension of
   manual mode (the user clicks each peak, the renderer
   accumulates the list, then Apply commits). It needs the same
   matplotlib `mpl_connect` dance as the existing
   `_on_mpl_interact` does for axis-limit capture and a small
   amount of in-panel ephemeral state. Decision deferred — the
   manual entry covers the same gesture for the cases users
   typically care about (one or two known band positions).
5. **The left pane is now visibly tall.** Phase 4g friction #5
   already flagged the four-section stack (Baseline + Normalisation
   + Smoothing + ?); Phase 4h lands the fourth section. On a
   720-pixel-tall window the Apply Peak Picking button can be
   below the fold, depending on the user's font-scaling and
   sash position. The collapsible-sections / accordion / mini-tab
   options listed in Phase 4g friction #5 all still apply; the
   forcing function for a redesign is now stronger. Decision
   deferred until a user reports it as friction (or until a fifth
   section lands in OLIS correction or interactive normalisation).
6. **PEAK_LIST is not exportable.** `node_export._resolve_columns`
   is UV/Vis-shaped only (Phase 4f friction #1). PEAK_LIST has
   different array keys (`peak_wavelengths_nm` /
   `peak_absorbances` / optional `peak_prominences`) so the
   row-Export… gesture errors out for a PEAK_LIST row even after
   commit. The cleanest fix is the `NodeType → (col_names,
   array_keys)` registry sketched in Phase 4f friction #1.
   Resolve when Phase 5 / 6 land their first XANES / EXAFS
   exportable nodes.
7. **`scipy.signal.find_peaks` returns peak prominence but not
   peak width / FWHM.** A future "peak table" export will probably
   want widths too. `find_peaks` accepts `width=` and returns the
   widths; adding the array key + a future export column is a
   one-commit sweep. Defer until a peak-table export is in scope.

### Friction points carried forward from Phase 4i

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4i while implementing the second
derivative and landing the second curve-shaped non-spectrum
DataNode (`SECOND_DERIVATIVE` — derivatives are not absorbance,
they share the schema only). **Do not fix until the relevant
subsequent Phase 4 session.**

1. **`_PALETTE` is now duplicated in six modules.** Phase 4c
   friction #5 / Phase 4e friction #2 / Phase 4g friction #1 /
   Phase 4h friction #1 tracked the duplication; Phase 4i adds
   the sixth copy in `uvvis_second_derivative._PALETTE` and a
   sixth term in the `_PALETTE[(n_uvvis + n_baseline +
   n_normalised + n_smoothed + n_second_deriv) %
   len(_PALETTE)]` index expression (PEAK_LIST has its own
   index expression in `uvvis_peak_picking` so it does not add
   to this sum). The `_pick_default_color(graph)` extraction
   would now touch four locked modules to truly de-duplicate;
   the cleanest path is a polish session that bundles it with
   the left-pane density redesign (friction #2 below) so all
   five operation modules can be edited in one phase. Defer
   until a polish session is scheduled or a sixth caller lands
   (Phase 5 XANES is the natural next consumer).
2. **The left pane is now five sections tall — USER-FLAGGED at
   end of Phase 4i, priority escalated to 🔴.** Phase 4g friction
   #5 / Phase 4h friction #5 escalated this internally; the user
   has now explicitly raised it as the next polish target. The
   five sections (Baseline + Normalisation + Smoothing + Peak
   picking + Second derivative) make the left pane unwieldy on
   any window shorter than ~900 px. Decision locked at the
   Phase 4i hand-off: collapsible sections with **all sections
   collapsed by default**. Each section header is a clickable
   strip showing the section title + a chevron (▶ collapsed, ▼
   expanded); clicking toggles the body's pack/forget state.
   Section state is per-tab Tk var (not persisted to project
   yet — that is a Phase 8 concern). Pair with the
   `_pick_default_color(graph)` extraction (friction #1) in the
   same polish session because both touch every operation
   module at once. See the new register entry "Collapsible
   left-pane sections" below.
3. **`_spectrum_nodes` cannot widen to include `SECOND_DERIVATIVE`
   without churning the four locked operation panels.**
   Conceptually a peak-pick or smoothing pass on a second
   derivative is well-defined (peak-picking the d² is a standard
   gesture for finding inflection points in the parent). The
   Phase 4g / 4h locks meant the panels' `parent_node.type`
   tuples could not widen this phase, so `SECOND_DERIVATIVE`
   lives in its own `_second_derivative_nodes()` iteration
   and is never offered as a parent. A future session can widen
   each of `uvvis_smoothing.SmoothingPanel._apply`,
   `uvvis_peak_picking.PeakPickingPanel._apply`,
   `uvvis_normalise.NormalisationPanel._apply` (and the
   baseline path inside `uvvis_tab._apply_baseline`) to accept
   `NodeType.SECOND_DERIVATIVE`, then promote `_spectrum_nodes`
   to include it. Defer until a user reports it as friction.
4. **`SECOND_DERIVATIVE` mean-spacing scaling is approximate
   on non-uniform grids.** `compute()` divides by
   `np.mean(np.abs(np.diff(wl)))` so the output units are
   physical (A/nm² rather than A/sample²). This matches the
   standard analytical-chemistry convention but is only exact
   when the parent's wavelength sampling is uniform. UV/Vis
   instruments produce uniform grids in practice, so this is
   not yet a real issue. A more rigorous path would
   re-interpolate to a uniform grid before differentiating;
   defer until a user loads a non-uniform-grid spectrum.
5. **No `_on_uvvis_apply_to_all` exclusion / inclusion decision
   for `SECOND_DERIVATIVE`.** Phase 4h friction #2 flagged this
   for `PEAK_LIST` (the ∀ button writes to `_spectrum_nodes`,
   which excludes `PEAK_LIST` and now also `SECOND_DERIVATIVE`).
   For curve-style keys (colour, linewidth) the exclusion is
   correct (a derivative wants its own colour). For visibility
   / legend toggles, the user's mental model is probably "every
   row in the sidebar". Same per-key fan-out scope fix as Phase
   4h friction #2; same decision deferral.
6. **Status-bar message coupling deepens.** Five operation panels
   now route their success messages through
   `_set_status_message`; the existing implementation overwrites
   the previous message with each call, so a fast user clicking
   Apply on multiple panels in succession only sees the last one.
   A short-lived toast / status history might be more
   informative; defer until a user reports the message
   overwrites as friction.

| Status | Priority | Item | Notes |
|---|---|---|---|
| ✅ | 🔴 | **Migrate UV/Vis to node model** | UVVisScan → DataNode(type=UVVIS). File load → RAW\_FILE + LOAD + UVVIS triple, all COMMITTED (Phase 4a Part A; CS-13 implementation notes) |
| ✅ | 🔴 | **Replace UV/Vis sidebar with ScanTreeWidget** | Retire existing compact grid table; ScanTreeWidget is the replacement (Phase 4a Part B) |
| ✅ | 🔴 | **Replace UV/Vis style dialog with unified style dialog** | Existing UV/Vis style dialog is the reference; unified dialog supersedes it (Phase 4a Part C) |
| ✅ | 🔴 | **Baseline correction** | Linear (two-point), polynomial (order n), spline, rubberband/convex hull. Each application creates a provisional BASELINE node (Phase 4c; CS-15) |
| ✅ | 🔴 | **Export processed data** | Single-node `.csv` / `.txt` export with `# `-prefixed provenance header. Row Export… gesture on committed nodes; provisional rows render the entry disabled. Pure header builder + pure file writer + widget gesture + dialog flow (Phase 4f; CS-17) |
| ✅ | 🔴 | **Normalisation as explicit operation** | Normalisation creates a provisional NORMALISED node rather than modifying data in place. Two modes (peak / area), each with a window in nm; mirrors the Phase 4c BASELINE shape (Phase 4e; CS-16) |
| ⏳ | 🔴 | **"Send to Compare" action** | Replaces "Add to TDDFT Overlay". Available on committed nodes |
| ✅ | 🔴 | **Plot Settings dialog** | Fonts, grid, background colour, legend position, tick direction, title/label customisation. Accessed via ⚙ in top bar (Phase 4b; CS-14) |
| ✅ | 🟡 | **Peak picking** | Two modes: prominence (`scipy.signal.find_peaks`) and manual (comma-separated wavelengths snapped to the parent grid). Single OperationType.PEAK_PICK with `params["mode"]` ∈ {"prominence", "manual"} (mirrors CS-15 / CS-16 / CS-18). Output is a provisional `PEAK_LIST` DataNode rendered as scatter on top of the parent curve. `PeakPickingPanel` co-located in `uvvis_peak_picking.py` (Phase 4h; CS-19). λ/E annotation labels + optional peak-table export deferred to a future polish session |
| ⏳ | 🟡 | **OLIS integrating sphere correction** | Three-input operation node (sample + reference + blank → corrected). See OQ-004 for multi-input UI design |
| ⏳ | 🟡 | **Interactive normalisation** | Normalise to user-specified wavelength or integration region |
| ⏳ | 🟡 | **Difference spectra** | Two-input operation node. See OQ-004 |
| ✅ | 🟡 | **Smoothing** | Savitzky-Golay or moving average; creates provisional SMOOTHED node. Single OperationType.SMOOTH with `params["mode"]` ∈ {"savgol", "moving_avg"} (mirrors CS-15 / CS-16). `SmoothingPanel` co-located in `uvvis_smoothing.py` (Phase 4g; CS-18). `node_styles.default_spectrum_style` extracted as the four-caller threshold sibling commit |
| ✅ | 🟢 | **Second derivative** | Single-algorithm Savitzky-Golay derivative (`scipy.signal.savgol_filter` with `deriv=2`); no mode discriminator (the savgol routine smooths and differentiates in one pass — naive `np.gradient` would be a footgun mode rather than a useful alternative). Output is a provisional `SECOND_DERIVATIVE` `DataNode` rendered as a curve overlay on the same plot (reuses the `wavelength_nm` / `absorbance` schema; the latter holds d²A/dλ² values). `SecondDerivativePanel` co-located in `uvvis_second_derivative.py` (Phase 4i; CS-20). Chained derivatives intentionally out of scope: `SECOND_DERIVATIVE` is excluded from `_spectrum_nodes` so the locked baseline / normalise / smoothing / peak-picking panels do not surface it as a candidate parent (their parent type checks would silently refuse it) |
| ⏳ | 🟢 | **Beer-Lambert / concentration** | Use known ε to extract concentration, or fit ε from known concentration |
| ⏳ | 🔴 | **Collapsible left-pane sections (polish session)** | USER-FLAGGED at end of Phase 4i. Each of the five operation sections (Baseline / Normalisation / Smoothing / Peak picking / Second derivative) becomes a clickable header that toggles its body's pack/forget state via a chevron (▶ collapsed, ▼ expanded). **Default is all sections collapsed** so the left pane opens as five header strips — the user expands the section they want to use. State is per-tab Tk var (not persisted to project; that is a Phase 8 concern). Pair with `_pick_default_color(graph)` extraction (BACKLOG Phase 4i friction #1) in the same session because both touch every operation module at once and unlock four modules currently held by Phase 4c / 4e / 4g / 4h locks. Resolves Phase 4i friction #2 (and Phase 4g #5 / 4h #5 carry-forwards). Use the regular six-commit shape: extract `_pick_default_color` first (single sweep across `uvvis_baseline` / `uvvis_normalise` / `uvvis_smoothing` / `uvvis_peak_picking` / `uvvis_second_derivative`), then introduce a `CollapsibleSection` wrapper widget, then convert each of the five sections, then tests, then bookkeeping |

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
| **B-001** | ✅ Phase 4c | History expansion (`⌥n` click on a sidebar row) renders at the bottom of the sidebar instead of inline below the clicked row. With two datasets loaded, clicking the top row's history shows expanded entries below the *second* row, making the visual association ambiguous | CS-04 §6.2 ("inline, below row") | Resolved by commit `610746e` — `_render_history` now packs with `after=row`; one history pane open at a time across the widget |
| **B-002** | ✅ Phase 4d | Sidebar row controls do not adapt to sidebar width. At narrow widths the row overflows. The minimum always-visible set should be: dataset name + visibility checkbox + ⚙ gear button. Every other per-row control (colour swatch, legend toggle, linestyle canvas, linewidth entry, fill checkbox, history indicator, ✕) must collapse when the row narrows. The unified StyleDialog (CS-05) must then cover every collapsed control — which it currently does not: `style["visible"]` and `style["in_legend"]` have no controls in the dialog | CS-04 §6.1 + CS-05 universal section | Resolved by commits `85c30f3` (responsive row collapse — `_apply_responsive_layout` hides the optional set below `_RESPONSIVE_COLLAPSE_PX` = 280 px) and `5f7ed47` (StyleDialog universal section gained `visible` and `in_legend` checkbutton rows with per-row ∀ delegates; bulk ∀ excludes both as a footgun guard). The minimum always-visible set landed as state · `[☑]` · label · `[⚙]` · `[✕]` (the brief's listing kept `state` and `[✕]` because dropping them would break provisional/committed affordance and the discard/hide gesture). UV/Vis ∀ fan-out widened from `_uvvis_nodes` to `_spectrum_nodes` (UVVIS + BASELINE) so toggling visibility on one row reaches every row in the same sidebar |
| **B-003** | ✅ Phase 4c | When `Norm: area` is active the X-axis limit entries no longer take effect on Apply / Return. `Norm: none` and `Norm: peak` both work. Likely interaction between `_y_with_norm`'s area integral and the post-render axis-limit application path in `_redraw` ([uvvis_tab.py:583-593](uvvis_tab.py#L583), [uvvis_tab.py:662-671](uvvis_tab.py#L662)) — verify before fixing | UV/Vis tab `_redraw` | Resolved by commit `88ad2bf` — root cause was `np.trapz` removed in numpy 2.x; switched to `np.trapezoid` and took absolute value of the integral |
| **B-004** | ✅ Phase 4c | No way to rename a dataset from the right sidebar via the right-click menu. CS-04 §"Context menu" lists `Rename` as a right-click entry; the implementation only landed Commit / Discard / Send to Compare. In-place double-click rename exists per Phase 2 but is undiscoverable. Add the context-menu entry; consider a label tooltip pointing at it | CS-04 §"Context menu" | Resolved by commit `7314a68` — the Rename menu entry was present since Phase 2 but `_begin_label_edit` raised `TclError` from `entry.pack(before=...)` after `pack_forget`, which silently broke both rename gestures; fixed the pack call |

The Phase 4d responsive-row work (B-002) also needs to add `visible`
and `in_legend` controls to the StyleDialog universal section so the
collapsed row's controls remain reachable through the dialog.

Newly discovered bugs go in this table with a fresh `B-NNN` id and a
phase assignment. Resolved bugs get a ✅ in the Severity column with
the resolving phase + commit SHA appended to the row.

---

*Document version: 1.7 — April 2026*
*1.1: Known Bugs register added 2026-04-27 after Phase 4b manual testing.*
*1.2: Phase 4c — baseline correction lands; B-001 / B-003 / B-004
resolved; Phase 4c friction points logged.*
*1.3: Phase 4d — responsive sidebar row collapse + StyleDialog
universal `visible` / `in_legend`; B-002 resolved; Phase 4d
friction points logged.*
*1.4: Phase 4g — UV/Vis smoothing lands (CS-18); Smoothing item
marked ✅; Phase 4g friction points logged. (Phase 4e — normalisation
as operation — and Phase 4f — single-node export — were logged in
their respective COMPONENTS.md sections; not separately versioned
here.)*
*1.5: Phase 4h — UV/Vis peak picking lands (CS-19); Peak picking
item marked ✅; Phase 4h friction points logged (seven items: fifth
`_PALETTE` copy, ∀ apply-to-all PEAK_LIST exclusion, peak-marker
schema vs universal style schema, deferred click-on-plot gesture,
left-pane height pressure, PEAK_LIST not yet exportable, peak-width
extension for future peak-table export).*
*1.6: Phase 4i — UV/Vis second derivative lands (CS-20); Second
derivative item marked ✅; Phase 4i friction points logged (six
items: sixth `_PALETTE` copy, five-section left pane redesign now
overdue, locked-panel widening to accept SECOND_DERIVATIVE as
parent, mean-spacing approximation on non-uniform grids,
∀ apply-to-all SECOND_DERIVATIVE exclusion, status-bar message
overwrite under fast successive Apply gestures).*
*1.7: Post-Phase-4i — user-flagged the left-pane density issue
(Phase 4i friction #2) and elevated it to 🔴 with a locked
"all sections collapsed by default" decision. New Phase 4
register entry: Collapsible left-pane sections (polish session).
New top-level "Session structure" section formalises the
ten-step pattern every phase session now follows; the bug /
issue / feature elicitation step (5) is mandatory, between
the run-suite verification (4) and the bookkeeping commit (6).*
*Supersedes: BACKLOG.md (original)*
