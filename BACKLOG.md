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
6. **Bookkeeping commit** — three responsibilities:

   a. **Mark the new register item ✅** and add a fresh
      "Friction points carried forward from Phase 4X" section
      **including any user-flagged items from step 5**.

   b. **Mark resolved prior-phase friction items** —
      strike-through the matching entries in earlier friction
      lists with `~~original text~~` followed by
      `✅ **Resolved in Phase 4X (CS-NN).**` plus a one-line
      explanation. Walk every prior friction section the
      current phase plausibly touches, not just the immediate
      predecessor — palette duplication chained across five
      phase sections before CS-21 retired it; subject combobox
      chained across three before CS-22; the cleanup is wasted
      if it only catches the most-recent occurrence.

   c. **Collapse repeating chains to one canonical entry.**
      When the same root issue appears in N≥2 friction lists,
      keep the first occurrence with full prose and replace
      later occurrences with one-line cross-references:
      `~~**Short title.**~~ See 4X #N above (canonical entry
      — still open).` New friction items added in the current
      phase should also cross-ref any prior entry with the
      same root, so a future cleanup pass can find the chain.

   COMPONENTS.md updates: new CS-N section + doc-version
   footer bumped.

   **Pruning policy (after ~3 phases of staleness):** items
   that have been struck-through for three or more phases,
   AND whose chain is fully closed, should be pruned from
   their per-phase friction sections into a single
   "Resolved friction history" log at the bottom of Phase 4
   (one line per resolved chain: `Palette duplication
   (4c→4e→4g→4h→4i): ✅ resolved Phase 4j (CS-21)`). The
   per-phase sections then carry only items still open or
   recently-resolved. This keeps active friction lists from
   re-bloating over the long phase 5 / 6 / 7 sequence; the
   audit trail survives in the consolidated log.
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
3. ~~**Send-to-Compare needs the Compare tab to exist.**~~
   ✅ **Partially resolved in Phase 4n (CS-27).** UVVisTab now wires
   `send_to_compare_cb=self._send_node_to_compare` so the right-click
   menu entry is enabled on committed UV/Vis rows AND the new per-row
   → icon (CS-27) routes to the same handler. The toolbar's
   "+ Add to TDDFT Overlay" button is gone. The actual Compare tab
   itself is still Phase 7; CS-27 routes through the existing
   `_add_scan_fn` (TDDFT overlay) hook for now.
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
5. **`_send_node_to_compare` still constructs `ExperimentalScan`
   from graph nodes.** (Renamed from `_add_selected_to_overlay` in
   Phase 4n CS-27 — single-node refactor of the bulk method.) Reads
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
   USER-FLAGGED at end of Phase 4l as important; canonical entry
   for the persistence chain. See the new register entry
   "Plot config + plot defaults persistence to project.json
   (CS-13 follow-up)" below; Phase 4b #5 cross-refs this.
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
   a `tabs` section to host it. See 4b #1 above (canonical entry —
   still open) and the new register entry "Plot config + plot
   defaults persistence to project.json (CS-13 follow-up)".
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
   focus, but it widens the widget's surface noticeably. **Subject-
   combobox aspect resolved in Phase 4k (CS-22)** — a single shared
   combobox at top of left pane replaces the per-panel duplication.
   Per-row selection on the right-side ScanTreeWidget is still
   open and now forcing-functioned by the Phase 4k register entry
   "Per-variant gestures on sweep-group rows" (USER-FLAGGED 🔴).
   Cross-refs: 4f #2 (export per-row, not per-selection), 4g #3
   (subject-combobox aspect — resolved with this).
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
5. ~~**`_PALETTE` is duplicated logic between UVVIS load and
   BASELINE Apply.**~~ ✅ **Resolved in Phase 4j (CS-21).**
   Original duplication chain: 4c #5 → 4e #2 → 4g #1 → 4h #1
   → 4i #1. `node_styles.pick_default_color(graph)` collapses
   all five call sites and `node_styles.SPECTRUM_PALETTE` is
   the single source of truth.
6. ~~**`_uvvis_nodes` vs. `_spectrum_nodes` divergence.**~~ ✅
   **Largely sidestepped (Phase 4c → 4d → 4j evolution).**
   The two helpers continued to coexist as their roles
   diverged: `_uvvis_nodes` is now used only by
   `_has_existing_load` (UVVIS-specific duplicate-load check)
   and the legacy "+ Add to TDDFT Overlay" shim — both correct
   today. The shim retires with Phase 7 (Send-to-Compare); the
   load-path use is intentionally type-narrow. No further
   convergence work needed.
7. ~~**Legacy "+ Add to TDDFT Overlay" button still synthesises
   from UVVIS only.**~~ ✅ **Partially resolved in Phase 4n
   (CS-27).** The button itself is gone (replaced by the per-row
   → icon). The single-node helper `_send_node_to_compare`
   continues to skip non-UVVIS rows silently — correct today (the
   TDDFT overlay still has no BASELINE knowledge). The shim
   retires when Phase 7 wires the actual Compare tab.

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
3. ~~**`_DEFAULT_STYLE` lives in two places.**~~ ✅ **Partially
   resolved in Phase 4g (CS-18 sibling commit).** The
   spectrum-producing factory dict is now
   `node_styles.default_spectrum_style` — a single source of
   truth for fresh-node creation. The two UI-side fallback maps
   (`scan_tree_widget._DEFAULT_STYLE`, `style_dialog._UNIVERSAL_DEFAULTS`)
   intentionally remain in their widget files: their role is
   "fallback when `node.style` is missing a key" rather than
   "factory dict for fresh node creation" (Phase 4g #6
   documents the role split). Residual chain: 4d #3 → 4e #1
   → 4g #6 (intentional carry-forward).
4. **Bulk ∀ exclusion list is a tuple in code, not a derived
   property.** `_BULK_UNIVERSAL_KEYS` enumerates the keys the
   bottom button fans out. Adding a new universal key means
   editing both `_UNIVERSAL_DEFAULTS` and (if the key should be
   bulk-applied) `_BULK_UNIVERSAL_KEYS`. The exclusion of
   `colour` / `visible` / `in_legend` is documented but
   easy to mis-match. Consider a richer registry (`{key: {bulk:
   bool, default: ...}}`) when a fifth or sixth key joins.
5. ~~**UV/Vis fan-out scope is now `_spectrum_nodes`, but
   `_has_existing_load` and the legacy "+ Add to TDDFT Overlay"
   button still read `_uvvis_nodes`.**~~ ✅ **Closed — both
   residual callers are correct as-is.** See 4c #6 above; the
   load-path read is intentionally UVVIS-specific and the
   overlay shim retires with Phase 7 (Send-to-Compare). No
   convergence work needed.

### Friction points carried forward from Phase 4e

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4e while implementing
normalisation-as-operation and resolving Phase 4a friction point
#2. **Do not fix until the relevant subsequent Phase 4 session.**

1. ~~**`_default_*_style` lives in three places.**~~ ✅ **Resolved
   in Phase 4g (CS-18 sibling commit).** `node_styles.default_spectrum_style`
   is now the single factory dict for spectrum-producing
   operations; every `_default_*_style` call site collapses to it.
   Same chain as 4d #3 above. Residual fallback maps are
   intentional (4g #6).
2. ~~**`_PALETTE` index expression duplicated three times now.**~~
   ✅ **Resolved in Phase 4j (CS-21).** See 4c #5 above for the
   full chain.
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
   updates `self._status_lbl.config(...)` inline; the four
   operation panels (`NormalisationPanel`, `SmoothingPanel`,
   `PeakPickingPanel`, `SecondDerivativePanel`) all call back
   through `_set_status_message`. Migrating the inline baseline
   path is a one-commit sweep. **Plus:** the existing
   `_set_status_message` overwrites the previous message with
   each call (Phase 4i #6), so a fast user clicking Apply on
   multiple panels in succession only sees the last one — a
   short-lived toast / status history might be more
   informative. Cross-refs: 4g #2, 4i #6 (same root issue —
   tracked here as the canonical entry).
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
2. **Export is per-row, not per-selection.** A per-selection
   export needs a row-selection model on `ScanTreeWidget` —
   tracked at 4c #1 (still open after Phase 4k partial
   resolution; right-side selection is still the gap, now
   forcing-functioned by the Phase 4k "Per-variant gestures"
   register entry).
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
   such cases exist today (BASELINE / NORMALISE / SMOOTH /
   PEAK_PICK / SECOND_DERIVATIVE params are all pure Python
   floats / ints / strings), but the fallback hides a future
   schema regression. Phase 5 / 6 should pin a stricter
   serialiser when params shapes widen (e.g., XANES Larch
   k-window taper `Decimal` precision). Cross-ref: 4g #4 (same
   root issue — tracked here as the canonical entry).

### Friction points carried forward from Phase 4g

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4g while implementing smoothing-as-operation
and extracting `node_styles.default_spectrum_style` as the
four-caller threshold sibling commit. **Do not fix until the
relevant subsequent Phase 4 session.**

1. ~~**`_PALETTE` is now duplicated in four modules.**~~ ✅
   **Resolved in Phase 4j (CS-21).** See 4c #5 above for the
   full chain.
2. ~~**The status-bar API split persists.**~~ See 4e #5 above
   (canonical entry — still open).
3. ~~**`SmoothingPanel` reflects the same "no row-selection model"
   workaround as baseline / normalisation.**~~ ✅ **Subject-
   combobox aspect resolved in Phase 4k (CS-22).** Row-selection
   on the right-side ScanTreeWidget is the residual gap — see
   4c #1.
4. ~~**`OperationNode.params` carries `int` for `window_length` /
   `polyorder` instead of resolved-type-tagged values.**~~ See
   4f #6 above (canonical entry — still open).
5. ~~**The four panels in the left pane are now visually crowded.**~~
   ✅ **Resolved in Phase 4j (CS-21).** Each section is now a
   `CollapsibleSection` (collapsed-by-default); the user expands
   only the section they're working in.
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

1. ~~**`_PALETTE` is now duplicated in five modules.**~~ ✅
   **Resolved in Phase 4j (CS-21).** See 4c #5 above for the
   full chain.
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
5. ~~**The left pane is now visibly tall.**~~ ✅ **Resolved in
   Phase 4j (CS-21).** See 4g #5 above for the full chain.
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

1. ~~**`_PALETTE` is now duplicated in six modules.**~~ ✅
   **Resolved in Phase 4j (CS-21).** The
   `node_styles.pick_default_color(graph)` helper now walks every
   spectrum-shaped NodeType (UVVIS, BASELINE, NORMALISED,
   SMOOTHED, SECOND_DERIVATIVE, **and** PEAK_LIST — folded in)
   in one go, and `node_styles.SPECTRUM_PALETTE` is the single
   source of truth. All six pre-4j call sites collapse to
   `colour = pick_default_color(self._graph)`. Behaviour change
   intentional: peak_picking and second_derivative now see each
   other's nodes in the palette counter (pre-4j they were
   mutually palette-invisible). xas_analysis_tab and
   exafs_analysis_tab keep their local `_PALETTE` literals — Phase
   0 / pre-redesign code, out of scope.
2. ~~**The left pane is now five sections tall.**~~ ✅
   **Resolved in Phase 4j (CS-21).** Each of the five operation
   sections is now wrapped in a `CollapsibleSection` widget
   (`collapsible_section.py`); all five start collapsed (locked
   default) and the header strip shows `▶ Title` (collapsed) or
   `▼ Title` (expanded). Click anywhere on the header strip
   toggles. Section state is per-tab Tk `BooleanVar` owned by
   each section widget; not persisted to project (Phase 8
   concern, by design). The four `ttk.Separator` strips between
   sections are gone — each section's bold-font header serves
   as the divider.
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
5. ~~**No `_on_uvvis_apply_to_all` exclusion / inclusion decision
   for `SECOND_DERIVATIVE`.**~~ See 4h #2 above (canonical entry
   — still open). The per-key fan-out scope fix would cover
   PEAK_LIST and SECOND_DERIVATIVE in one pass.
6. ~~**Status-bar message coupling deepens.**~~ See 4e #5 above
   (canonical entry — still open). Phase 4i was the last phase
   that added a panel-side `_set_status_message` caller; the
   "overwrites previous message" friction now affects five
   sections rather than three.

### Friction points carried forward from Phase 4j

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4j while implementing the
`pick_default_color` helper extraction and the collapsible left-pane
sections (CS-21). **Do not fix until the relevant subsequent Phase 4
session.**

1. ~~**`tk.StringVar` in `scan_tree_widget._begin_label_edit` falls
   back to `tkinter._default_root`.**~~ ✅ **Resolved in-phase
   (commit 6).** Surfaced when `test_collapsible_section` joined the
   suite as a fifth `tk.Tk()`-using test module; loading it before
   `test_scan_tree_widget` shifted `_default_root` and the rename
   Entry's textvariable bound to a different interpreter than its
   master, rendering the Entry empty even with `value=current`. Fix:
   pass `master=row_frame` explicitly to the StringVar constructor.
   Defence-in-depth — also makes future plugin tabs / workspace
   windows that spawn their own Tk root safe.
2. **Behaviour change from the unified palette counter.**
   `pick_default_color` walks all six spectrum-shaped NodeTypes
   including PEAK_LIST and SECOND_DERIVATIVE. Pre-4j a user creating
   one PEAK_LIST then one SECOND_DERIVATIVE would get palette[1] for
   both (each module saw "one prior spectrum, palette[1]"). Post-4j
   they get palette[1] then palette[2]. This is the intended
   behaviour — the Phase 4j brief locked it as "order-independent" —
   but worth recording for visual-regression audits and any
   screenshot-bearing docs that assumed pre-4j ordering.
3. **CollapsibleSection collapse state is lost on tab teardown.**
   Per the Phase 4j brief, persistence is a Phase 8 concern; the
   per-section `tk.BooleanVar` lives inside the widget and dies with
   it, so re-opening a project re-collapses every section. Phase 8's
   project save / load pass should serialise the five section flags
   alongside the rest of the per-tab UI state.
4. **First-run UX shows five blank chevron strips.** A user opening
   the app for the first time sees the left pane as five collapsed
   header strips with no parameter inputs visible. The chevron
   glyph + `cursor="hand2"` is the only affordance. Locked design
   decision (the user prefers click-to-expand to be the affordance
   rather than auto-expand the first section), but worth logging as
   a perceptual carry forward in case onboarding feedback later
   contradicts.
5. ~~**Per-panel subject combobox feels redundant.**~~ ✅
   **Resolved in Phase 4k (CS-22).** USER-FLAGGED at end of
   Phase 4j. Replaced by a single shared `_shared_subject_cb`
   at top of left pane; each panel exposes
   `set_subject(node_id)` + `ACCEPTED_PARENT_TYPES`. See the
   "Unify subject combobox across left-pane sections" register
   entry above (now ✅).
6. **Per-panel Entry widgets for wavelength windows are unit-naïve.**
   USER-FLAGGED at end of Phase 4j. The plot's x-axis can be in nm
   / cm⁻¹ / eV; the panels' parameter Entry widgets only accept nm.
   Friction when the user reads peak positions off the plot in
   non-nm units and has to mentally convert before typing into the
   panel. See the new register entry "Unit-aware wavelength / energy
   picker for operation panels" below.

### Friction points carried forward from Phase 4k

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4k while replacing the per-panel subject
combobox with the shared `_shared_subject_cb` at the top of the
left pane (CS-22). **Do not fix until the relevant subsequent
Phase 4 session.**

1. **No "accept" gesture reachable from the left pane.**
   USER-FLAGGED at end of Phase 4k. After Apply on the left, the
   only path to commit / discard the new provisional node is the
   right-click context menu on the right-side ScanTreeWidget row.
   Important when sequential operations need to be logged; the
   user wants confirm-as-they-go, not "remember which row was just
   added and traverse to it". See the new register entry
   "Commit / discard reachable from the left pane after Apply".
2. **Sweep-group rows hide per-variant gestures.**
   USER-FLAGGED at end of Phase 4k. When a parent has 2+
   provisional children, the right-side ScanTreeWidget collapses
   them into a sweep-group leader row with `✕all`; the user can
   expand to see the variants but cannot commit / discard / style
   any single one. Phase 2 carry-forward "Sweep group inline
   expansion" (🟡) is now actively biting; elevated to 🔴 and
   re-flagged. See the new register entry "Per-variant gestures on
   sweep-group rows".
3. ~~**Plot Settings dialog has no Save & Close button.**
   USER-FLAGGED at end of Phase 4k. The dialog applies changes
   live but offers only Cancel; closing via [X] takes the Cancel
   path silently. Inconsistent with the unified StyleDialog's
   `Apply · ∀ Apply to All · Save · Cancel` shape (CS-05). See
   the new register entry "Plot Settings dialog: Save & Close
   (consistent dialog button shape)".~~ ✅ Resolved in Phase 4l (CS-23).
4. **Auto-fall-back on subject deletion uses graph-insertion order.**
   When the shared subject vanishes (set_active=False, discard,
   GRAPH_CLEARED), `_refresh_shared_subjects` falls back to
   `items[0]` — the first UVVIS in graph insertion order. In a
   long session with several spectra, that may not be the user's
   mental "next thing"; "previous in list" or "freshly-added"
   policies may feel less surprising. Lock-worthy debate, not
   urgent.
5. **Apply-disabled state has no inline explanation.**
   Picking a SMOOTHED node with the normalisation section
   expanded leaves the Apply button disabled with no hint as to
   why. A small inline "Selected node is not a valid parent for
   this op" caption inside each panel (or a tooltip on the
   disabled button) would teach the user the per-op acceptance
   set without consulting docs.
6. **`_baseline_subject_id` lives on `UVVisTab`; `_subject_id` lives
   on each panel.** Inconsistent naming + visibility. The inline
   baseline section will likely become a `BaselinePanel` widget
   in a later phase; at that point `_BASELINE_ACCEPTED_PARENT_TYPES`
   should join the public `ACCEPTED_PARENT_TYPES` API the four
   operation panels already expose, and `_baseline_subject_id`
   should become `_subject_id` to match.

### Friction points carried forward from Phase 4l

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4l while adding the Save button to the
Plot Settings dialog (CS-23) plus end-of-session bug-elicitation
items the user surfaced from testing redesign/main. **Do not fix
until the relevant subsequent Phase 4 session.**

1. **Plot Settings dialog has no `∀ Apply to All` analogue.**
   StyleDialog's button row is `Apply · ∀ Apply to All · Save ·
   Cancel` (CS-05); CS-23 chose `Apply · Save · Cancel` for Plot
   Settings because today there is one tab-private config dict per
   dialog and no node bulk to fan out to. If a future feature ever
   shares Plot Settings across tabs (e.g. "apply this title font
   size to every tab in the project"), the row will need that
   fourth button. Cheap to add when the use-case lands, but worth
   flagging now so the convention work in #4 below treats Plot
   Settings as a 3-button special case rather than a 4-button
   regression.
2. **`_do_apply` (and Save) fires `on_apply` unconditionally.**
   Save inherits Apply's behaviour — even when the working copy is
   identical to the live config, `on_apply` (typically `_redraw`)
   fires. Cheap and safe today, but redundant; if the redraw grows
   expensive (e.g. matplotlib re-tick of large overlays the user
   pulled in via Compare) it could become noticeable. Tighten with
   `if dict(self._working) != dict(self._config)` mirroring
   `_do_cancel`'s "only revert if changed" guard.
3. **Save fires `on_apply` BEFORE `destroy`.** Today's only
   `on_apply` callback is `_redraw`, so no risk of re-entrancy. But
   if any future callback ever opens a follow-up Toplevel parented
   to the dialog (e.g. a "saved!" toast, a confirmation sheet), the
   parent Toplevel will be tearing down underneath it. The ordering
   should be pinned in the docstring or a test before the contract
   gets an unexpected user.
4. **Dialog button-row vocabulary not audited across the app.**
   USER-FLAGGED at end of Phase 4l. Plot Settings ↔ StyleDialog
   parity is now in place, but other modals (file pickers, future
   Beer-Lambert preview, future scattering-baseline preview, etc.)
   haven't been audited. The "consistent dialog button shape"
   principle would be more durable as a written convention in
   COMPONENTS.md (or ARCHITECTURE.md) so future modals start from
   the same vocabulary rather than re-deriving it. See the new
   register entry "Audit dialog button-row vocabulary across app
   + write convention into ARCHITECTURE.md (USER-FLAGGED)".
5. **`_USER_DEFAULTS` and `_plot_config` still process-lifetime
   only.** USER-FLAGGED at end of Phase 4l. Phase 4b friction #1
   + #5 already capture this; user explicitly asked it be elevated
   to a discrete register item so it doesn't get lost. See the new
   register entry "Plot config + plot defaults persistence to
   project.json (CS-13 follow-up) (USER-FLAGGED)" below; canonical
   chain entries are 4b #1 (USER_DEFAULTS) + 4b #5 (_plot_config).
6. ~~**Duplicate section title in Processing left sidebar.**
   USER-FLAGGED at end of Phase 4l. All four operation
   `CollapsibleSection` panels except "Baseline Correction" render a
   second title label inside the section body (below the clickable
   header).~~ ✅ **Resolved in Phase 4n (CS-25).** Stale `tk.Label`
   deleted from each of the four operation modules; regression test
   added per panel.
7. ~~**+Add to TDDFT Overlay top-bar button is ambiguous + the
   gesture should be per-row.** USER-FLAGGED at end of Phase 4l.~~
   ✅ **Resolved in Phase 4n (CS-27).** The top-bar button is gone;
   each ScanTreeWidget row carries a per-row → icon between ⚙ and ✕,
   wired to `UVVisTab._send_node_to_compare(node_id)` (single-node
   refactor of the old `_add_selected_to_overlay`).
8. ~~**Right-sidebar responsive layout — minimum visible set is too
   narrow.** USER-FLAGGED at end of Phase 4l. Phase 4d's B-002
   landed the minimum always-visible set as
   `state · [☑] · label · [⚙] · [✕]` collapsing below 280 px.~~
   ✅ **Resolved in Phase 4n (CS-26).** Always-visible minimum
   grew to seven cells `state · [☑] · label · ⌥n · [⚙] · [→] ·
   [✕]`; ⌥n promoted from optional. Single 280 px threshold replaced
   by three priority-ordered thresholds (swatch @ 240, leg @ 280,
   ls\_canvas @ 320). Fourth-priority "line width" cell deferred (no
   per-row line-width control today).
9. ~~**Scattering-functional baseline subtraction.** USER-FLAGGED at
   end of Phase 4l. Existing baseline modes (linear, polynomial,
   spline, rubberband) are general-purpose; UV/Vis spectra of
   colloidal / turbid samples have a baseline that follows
   wavelength-dependent scattering (typically 1/λ^n with n ≈ 2–4
   for Mie / Rayleigh regimes). A dedicated mode that fits a
   `1/λ^n` form (n either fitted or user-fixed, e.g. n=4 for
   Rayleigh) over a user-defined window would handle this far
   better than forcing a polynomial. Single new
   `OperationType.BASELINE` mode (`params["mode"] == "scattering"`,
   plus `params["n"]` either numeric or `"fit"`); reuses the
   provisional BASELINE node shape from CS-15. See the new
   register entry "Scattering-functional baseline mode".~~ ✅ Resolved in Phase 4m (CS-24).

### Friction points carried forward from Phase 4m

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4m while adding the scattering-functional
baseline mode (CS-24). All five are observed-during-session items;
no new user-flagged elevations this phase. **Do not fix until the
relevant subsequent Phase 4 session.**

1. **Scattering "Fit n" Tk var state survives mode flips and
   re-enters the rebuild on every refresh.** When the user enables
   Fit-n, switches to e.g. polynomial, then comes back to scattering,
   `_baseline_scattering_fit_n` is still `True` and the Entry's
   "disabled" state is set by `_sync_n_entry_state` as part of the
   refresh callback. It works today only because the refresh call
   the checkbox was registered on is invoked at the end of the
   builder. Same brittleness pattern as the polynomial-order Spinbox
   pre-CS-21. Cheap to harden by lifting the checkbox-disables-entry
   contract into a single declarative guard rather than relying on
   the rebuild ordering.
2. **Scattering n="fit" loses the resolved numeric n in `op.params`.**
   With the Fit-n checkbox on, `_collect_baseline_params` writes
   `params["n"] = "fit"` verbatim — this is reproducible (rerunning
   the op recovers the same n via the same log fit), but the
   recovered n is never persisted, so a downstream consumer
   (export header, provenance footer, future "show fit results")
   can't read it without re-running. CS-03 says params must be
   sufficient to reproduce; this satisfies the letter but loses the
   diagnostic. Plan: add a sibling `params["n_fitted"]` (float) on
   the OperationNode whenever the fit ran, and surface it in the
   ScanTreeWidget tooltip and the export header. Same shape applies
   the day a future op fits a parameter the user didn't pin.
3. **Composite "scattering + offset" mode is not covered.** Real
   colloidal samples often have both a Rayleigh / Mie tail AND an
   instrument or solvent offset: `B(λ) = a + c · λ^(-n)`. CS-24
   captures the pure power-law form per the Phase 4l brief; a
   composite mode (additive constant fit alongside c and optionally
   n) is the natural follow-up if users find that pure scattering
   leaves a flat residual. Likely shape: a sixth `mode == "scattering+offset"`
   that fits 2–3 parameters by linear least squares with `x = [1, λ^(-n)]`
   columns (when n is fixed) or by a small nonlinear solver (when
   n is fit alongside c and a).
4. **Fit-window-out-of-range errors don't show the spectrum's actual
   nm range.** Polynomial and scattering both raise "needs ≥ N points
   in fit window [x, y]" when the user types a window outside the
   data; the messagebox shows the requested window but not the data
   range, so a user typing "200–350" on a spectrum that starts at
   400 has to re-read the plot to figure out the offset. Trivial to
   widen the error message to include `[wl.min(), wl.max()]`. Touches
   `uvvis_baseline.py` (polynomial + scattering paths). Same diagnostic
   gap likely exists in `uvvis_normalise.py` peak / area windows.
5. **No integration test asserting the Fit-n checkbox disables the
   `n` Entry.** The mode-rebuild test confirms the scattering branch
   produces three rows; CS-03 capture is asserted via the params
   round-trip; but the visual state contract (checkbox on → entry
   disabled) is only covered by the inner `_sync_n_entry_state`
   wiring, not by an integration assertion. One short test that
   toggles `_baseline_scattering_fit_n` and re-reads the n Entry's
   `state` would pin the contract before someone refactors the
   rebuild order.

### Friction points carried forward from Phase 4n

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4n while removing duplicate panel titles
(CS-25), extending the right-sidebar responsive layout (CS-26),
and adding the per-row → Send-to-Compare icon (CS-27). Items 1, 4,
5 plus the four register-elevated feature requests are
USER-FLAGGED. **Do not fix until the relevant subsequent Phase 4
session.**

1. ~~🔴 **`_redraw` raises `KeyError: 'absorbance'` for non-UVVIS
   DataNodes.** USER-FLAGGED at end of Phase 4n. `uvvis_tab._redraw`
   walks every NodeType the sidebar filter accepts and reads
   `node.arrays["absorbance"]` unconditionally, but BASELINE's array
   schema is `wavelength_nm` + `baseline`. When a BASELINE node
   enters the graph (via tests today; via the user's normal Apply
   flow tomorrow once review tooling improves) the trace escapes to
   stderr from inside the Tk graph-event handler. Defensive
   per-NodeType branching in `_redraw` is the cheap fix. See the new
   register entry "Defensive guard in `_redraw` for non-UVVIS
   DataNodes". Pairs with the diagnostic-console entry (which would
   route the trace somewhere visible).~~ ✅ Resolved in Phase 4o
   (CS-28). The friction note's claim about BASELINE's schema was
   inaccurate — live BASELINE nodes carry `wavelength_nm + absorbance`
   (line 937 of `uvvis_tab.py`); the only `baseline`-keyed BASELINE in
   the codebase was the deliberately-malformed stub in
   `test_send_node_to_compare_skips_non_uvvis_nodes`. The CS-28 guard
   protects `_redraw` against any future malformed entry regardless
   of which key is missing.
2. **Test convention not documented: full `_root.update()` is
   required for geometry-sensitive assertions on a withdrawn
   root.** `update_idletasks()` flushes idle handlers but does not
   trigger Tk's geometry pass on a withdrawn root; `winfo_ismapped`
   lags reality until the next event cycle. Pre-CS-26 responsive
   tests got away with `update_idletasks` because the helper packed
   less aggressively. The convention should live in
   `test_scan_tree_widget`'s module docstring (and the equivalent
   doc for any future widget tests). One-paragraph doc edit. See
   the new register entry "Test convention: `_root.update()` over
   `update_idletasks()` for geometry".
3. **Responsive test setUp didn't pin host frame size, leading to
   intermittent overflow auto-unmap.** Phase 4n CS-26 added
   `tk.Frame(_root, width=800, height=400)` + `pack_propagate(False)`
   + `widget.pack(fill="both", expand=True)` to the responsive class
   setUp. Without these, the host's natural size is 1 px, Tk
   auto-unmaps overflowed widgets, and `winfo_ismapped()` reports
   False even for widgets that ARE in the pack list. Capture this
   as a setUp pattern worth replicating in any future widget test
   class that exercises responsive / overflow behaviour. (The
   pattern is now in place for `TestScanTreeWidgetResponsiveRow`
   and `TestScanTreeWidgetSendToCompareButton`; future widget
   classes can copy.) Documentation-style; no register entry.
4. 🔴 **Responsive helper does redundant pack/forget work on every
   Configure event.** USER-FLAGGED at end of Phase 4n. CS-26's
   `_apply_responsive_layout` unconditionally pack_forget+repacks
   every optional cell on every call, because Tk's auto-unmap under
   overflow makes `winfo_ismapped()` an unsound oracle for "is this
   widget currently in our intended layout?". Correct but redundant
   on rapid Configure events at the same width. Strategy: cache
   the last applied "threshold band" per row and short-circuit when
   the new width falls in the same band. See the new register entry
   "Threshold-band caching for responsive helper (technical debt)".
5. 🔴 **`⌥{n}` always-visible cell grows with digit count for long
   provenance chains.** USER-FLAGGED at end of Phase 4n. The cell
   renders `text=f"⌥{chain_len}"` literally; for `n > 9` the cell's
   natural width grows by ~9 px per digit, which re-triggers the
   responsive overflow pattern at widths today's tests verify safe.
   User has confirmed `n > 9` is realistic for complex workflows.
   See the new register entry "Long-provenance hist button display
   options (USER-FLAGGED)" — four shape options to weigh. Pairs
   with #4 above (any caching pass should account for cells whose
   natural width changes after the row was first measured).

### Friction points carried forward from Phase 4o

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4o while landing the defensive `_redraw`
guard (CS-28) and the dashed baseline-curve overlay (CS-29). Items
1 and 2 are USER-FLAGGED; item 3 is a process-improvement note.
**Do not fix until the relevant subsequent Phase 4 session.**

1. 🔴 **No per-node baseline-curve gate (USER-FLAGGED).** The new
   "Baseline curves" toggle is a single tab-level boolean; turning
   it on enables the dashed overlay for *every* visible BASELINE
   node at once. With more than two or three baselines visible the
   plot crowds quickly. Likely shape: a per-row toggle on the
   ScanTreeWidget BASELINE rows (sibling to the existing visibility
   `[☑]`), or a dedicated style-dict key (`style["show_baseline_curve"]`)
   exposed in the StyleDialog universal section so the per-node
   choice is also persistable. Pairs with #2 below (per-node gate
   would naturally limit legend density too). See the new register
   entry "Per-node baseline-curve toggle (USER-FLAGGED)".
2. **Baseline-curve overlay legend density.** With N visible
   BASELINE nodes and the global toggle on, the legend grows by N
   "<label> (baseline)" rows. At today's overlay defaults the legend
   stays readable up to ~3 baselines but starts to dominate the
   plot frame at 5+. Cheapest mitigation: gate the legend label on
   a separate condition (e.g. `style["in_legend"]` AND a new
   "show baseline in legend" preference); deeper fix is the per-node
   gate from #1. See the new register entry "Baseline-curve overlay
   legend density".
3. **Friction notes occasionally describe schema that doesn't match
   live code.** Phase 4n friction #1 said BASELINE's array schema
   was `wavelength_nm + baseline`; the live code at
   `uvvis_tab.py:937` uses `wavelength_nm + absorbance`. The friction
   note's claim only matched a deliberately-malformed test stub
   (`test_send_node_to_compare_skips_non_uvvis_nodes`), not any
   live construction site. Process improvement: when writing a
   friction entry that names array keys / dataclass fields / Tk
   var names, grep the codebase for one live construction site and
   quote the actual key names rather than reasoning from memory.
   No register entry — documentation-style note for the session
   structure.

| Status | Priority | Item | Notes |
|---|---|---|---|
| ✅ | 🔴 | **Migrate UV/Vis to node model** | UVVisScan → DataNode(type=UVVIS). File load → RAW\_FILE + LOAD + UVVIS triple, all COMMITTED (Phase 4a Part A; CS-13 implementation notes) |
| ✅ | 🔴 | **Replace UV/Vis sidebar with ScanTreeWidget** | Retire existing compact grid table; ScanTreeWidget is the replacement (Phase 4a Part B) |
| ✅ | 🔴 | **Replace UV/Vis style dialog with unified style dialog** | Existing UV/Vis style dialog is the reference; unified dialog supersedes it (Phase 4a Part C) |
| ✅ | 🔴 | **Baseline correction** | Linear (two-point), polynomial (order n), spline, rubberband/convex hull. Each application creates a provisional BASELINE node (Phase 4c; CS-15) |
| ✅ | 🔴 | **Export processed data** | Single-node `.csv` / `.txt` export with `# `-prefixed provenance header. Row Export… gesture on committed nodes; provisional rows render the entry disabled. Pure header builder + pure file writer + widget gesture + dialog flow (Phase 4f; CS-17) |
| ✅ | 🔴 | **Normalisation as explicit operation** | Normalisation creates a provisional NORMALISED node rather than modifying data in place. Two modes (peak / area), each with a window in nm; mirrors the Phase 4c BASELINE shape (Phase 4e; CS-16) |
| ✅ | 🔴 | **"Send to Compare" action** | Replaces "Add to TDDFT Overlay". Available on committed nodes. Resolved Phase 4n (CS-27): per-row → icon between ⚙ and ✕, disabled on provisional rows and when no `send_to_compare_cb` is wired (deferred-tab convention shared with Export…). UVVisTab wires `_send_node_to_compare(node_id)` (single-node refactor of the old `_add_selected_to_overlay` bulk method). Top-bar `+ Add to TDDFT Overlay` button removed — the per-row icon is the only gesture. Right-click context-menu "Send to Compare" entry retained as the fallback |
| ✅ | 🔴 | **Plot Settings dialog** | Fonts, grid, background colour, legend position, tick direction, title/label customisation. Accessed via ⚙ in top bar (Phase 4b; CS-14). Button row matches CS-05 StyleDialog vocabulary `Apply · Save · Cancel` (Phase 4l; CS-23) |
| ✅ | 🔴 | **Plot Settings dialog: Save & Close (consistent dialog button shape) (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4k. Resolved Phase 4l (CS-23): added a Save button between Apply and Cancel, equivalent to `_do_apply()` + `destroy()`. Mirrors StyleDialog's `Apply · Save · Cancel` shape (the `∀ Apply to All` slot is dropped — Plot Settings has no node-bulk concept; a future cross-tab-bulk feature would re-introduce it, see Phase 4l friction #1). Cancel + window-close [X] revert path unchanged (deep-copy snapshot was already in place). 458 tests, all green |
| ✅ | 🟡 | **Peak picking** | Two modes: prominence (`scipy.signal.find_peaks`) and manual (comma-separated wavelengths snapped to the parent grid). Single OperationType.PEAK_PICK with `params["mode"]` ∈ {"prominence", "manual"} (mirrors CS-15 / CS-16 / CS-18). Output is a provisional `PEAK_LIST` DataNode rendered as scatter on top of the parent curve. `PeakPickingPanel` co-located in `uvvis_peak_picking.py` (Phase 4h; CS-19). λ/E annotation labels + optional peak-table export deferred to a future polish session |
| ⏳ | 🟡 | **OLIS integrating sphere correction** | Three-input operation node (sample + reference + blank → corrected). See OQ-004 for multi-input UI design |
| ⏳ | 🟡 | **Interactive normalisation** | Normalise to user-specified wavelength or integration region |
| ⏳ | 🟡 | **Difference spectra (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4n. Two-input operation node — produces `A_ref - A_sample` (or vice versa) as a provisional DIFFERENCE node. See OQ-004 for multi-input UI design. Likely shape mirrors CS-15 / CS-16 but with two parents instead of one; the shared subject combobox (CS-22) needs a sibling "reference" combobox or a two-pane subject picker. Touches `uvvis_tab.py`, a new `uvvis_difference.py` panel, possibly `nodes.py` (new `NodeType.DIFFERENCE`), and `scan_tree_widget.py` filter |
| ✅ | 🟡 | **Smoothing** | Savitzky-Golay or moving average; creates provisional SMOOTHED node. Single OperationType.SMOOTH with `params["mode"]` ∈ {"savgol", "moving_avg"} (mirrors CS-15 / CS-16). `SmoothingPanel` co-located in `uvvis_smoothing.py` (Phase 4g; CS-18). `node_styles.default_spectrum_style` extracted as the four-caller threshold sibling commit |
| ✅ | 🟢 | **Second derivative** | Single-algorithm Savitzky-Golay derivative (`scipy.signal.savgol_filter` with `deriv=2`); no mode discriminator (the savgol routine smooths and differentiates in one pass — naive `np.gradient` would be a footgun mode rather than a useful alternative). Output is a provisional `SECOND_DERIVATIVE` `DataNode` rendered as a curve overlay on the same plot (reuses the `wavelength_nm` / `absorbance` schema; the latter holds d²A/dλ² values). `SecondDerivativePanel` co-located in `uvvis_second_derivative.py` (Phase 4i; CS-20). Chained derivatives intentionally out of scope: `SECOND_DERIVATIVE` is excluded from `_spectrum_nodes` so the locked baseline / normalise / smoothing / peak-picking panels do not surface it as a candidate parent (their parent type checks would silently refuse it) |
| ⏳ | 🟢 | **Beer-Lambert / concentration** | Use known ε to extract concentration, or fit ε from known concentration |
| ✅ | 🔴 | **Collapsible left-pane sections (polish session)** | Each of the five operation sections (Baseline / Normalisation / Smoothing / Peak picking / Second derivative) is now wrapped in a clickable `CollapsibleSection` header with a chevron (▶ collapsed, ▼ expanded). **All five sections start collapsed.** State is per-tab Tk `BooleanVar` owned by each section widget; not persisted to project (Phase 8 concern). Paired with the `pick_default_color(graph)` extraction in the same phase — both touched every operation module at once and a single phase unlocked all four (Phase 4c / 4e / 4g / 4h). Resolved Phase 4i friction #1 + #2 + Phase 4g #5 / 4h #5 carry-forwards (Phase 4j; CS-21) |
| ✅ | 🔴 | **Unify subject combobox across left-pane sections (architectural)** | USER-FLAGGED at end of Phase 4j. Replaced the five per-panel `_subject_cb` widgets with one shared `_shared_subject_cb` at the top of the left pane (always visible, above every CollapsibleSection). Each operation panel exposes `set_subject(node_id)` + `ACCEPTED_PARENT_TYPES`; the host's StringVar trace fans the selection out to all four panels + the inline baseline section. Apply buttons disable when the shared selection isn't a valid parent for the panel's op (e.g. peak_picking accepts UVVIS/BASELINE/NORMALISED/SMOOTHED but not PEAK_LIST or SECOND_DERIVATIVE; baseline accepts UVVIS/BASELINE only). Resolved Phase 4j friction #5 (Phase 4k; CS-22) |
| ⏳ | 🔴 | **Commit / discard reachable from the left pane after Apply (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4k. Today the only "accept this provisional node" path is the right-click context menu on the right-side ScanTreeWidget row. After hitting Apply on the left, the user has no nearby accept gesture — they must traverse to the right sidebar and find the new row. Important when sequential operations need to be logged: each Apply makes a provisional node, and the user wants to confirm-as-they-go. Likely shape: a small "Accept last / Discard last" button-pair in the left-pane status area, or an "Accept" gesture inline below each operation panel's Apply button that targets the most recently-applied output of that op. The right-sidebar gesture stays as the canonical control surface; the left-pane gesture is a convenience layer |
| ⏳ | 🔴 | **Per-variant gestures on sweep-group rows (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4k. Phase 2 carry-forward "Sweep group inline expansion" (already in the backlog as 🟡) is now actively biting: when two or more provisional siblings share a parent, the right-side ScanTreeWidget collapses them into a single sweep-group leader row with `✕all`. The leader row exposes only the bulk-discard gesture; the user can expand to SEE the variants but cannot commit / discard / style any single one. Elevated from 🟡 to 🔴 and re-flagged as USER-FLAGGED. Plan: per-variant inline rows under the leader with the same row chrome (state indicator · ⚙ · ✕ · label), gated by the Phase 4c friction #1 row-selection model decision |
| ⏳ | 🟡 | **Expand all / Collapse all gesture on left pane** | Companion polish for the new collapsible sections (Phase 4j). When a user wants to scan parameter choices across multiple sections (e.g. for a screenshot or to copy parameters from one panel to another) they currently have to click each header individually. Options: a small "▼ All / ▶ All" icon button at the top of the left pane (above the Processing label), or a right-click context menu on any section header with "Expand all" / "Collapse all" entries. Either is a small change — adds a method on `UVVisTab` that walks the five `_{name}_section` attributes and calls `expand()` / `collapse()` on each |
| ⏳ | 🟡 | **Unit-aware wavelength / energy picker for operation panels** | USER-FLAGGED at end of Phase 4j. The five operation panels collect wavelength/energy windows via free-form Entry widgets in nm only. The plot itself supports x in nm / cm⁻¹ / eV (top-bar combobox); the panels should follow whatever unit the plot is currently displaying so a user reading peak positions off the plot can type them straight into the entry without a mental unit conversion. Likely shape: a unit-aware Spinbox / Entry that watches the tab's `_x_unit` Tk var, converts the entered value to nm at Apply time (the canonical wavelength_nm storage stays nm), and re-renders the entry's display when the user flips units. Touches every panel that has a wavelength / energy parameter (baseline polynomial fit window, baseline spline anchors, normalisation window, peak-picking manual list). Plan once Phase 4j has bedded in |
| ⏳ | 🟢 | **Keyboard accessibility for `CollapsibleSection`** | The Phase 4j `CollapsibleSection` is a single mouse-clickable strip with no Tab focus indication or keyboard binding. For accessibility (and power users who prefer keyboard navigation) Tab-to-header + Space/Enter-to-toggle would mirror standard disclosure-widget conventions. Phase 11 (app-wide polish) — defer until other accessibility passes happen at the same time |
| ⏳ | 🔴 | **Audit dialog button-row vocabulary across app + write convention into ARCHITECTURE.md (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4l. Phase 4l (CS-23) brought Plot Settings into parity with StyleDialog (`Apply · Save · Cancel`), but other modals in the app (file pickers, future Beer-Lambert preview, future scattering-baseline preview, future Send-to-Compare confirmation) haven't been audited. Without a written convention, future modals re-derive button vocabulary ad-hoc and the user's Cancel-vs-Save mental model erodes. Plan: walk every `tk.Toplevel` / dialog construction site, document the canonical four-button shape (`Apply · ∀ Apply to All · Save · Cancel`) in `ARCHITECTURE.md` as a UI convention with explicit rules for when each slot may be dropped (e.g. `∀ Apply to All` collapses when there is no node-bulk concept; CS-14 demonstrates), and refactor the outliers. Touches every dialog module + ARCHITECTURE.md. Pairs naturally with Phase 4l friction #1 (Plot Settings 3-button special case) |
| ⏳ | 🔴 | **Plot config + plot defaults persistence to project.json (CS-13 follow-up) (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4l. Two persistence gaps elevated from Phase 4b friction #1 (`_USER_DEFAULTS` evaporates on app restart) + Phase 4b #5 (per-tab `_plot_config` rebuilt from scratch on every tab construction). Both should write through to `project.json` so reopening a project restores both the user's saved-default fonts/colours/etc. AND the per-tab plot configuration that was last in effect. Likely shape: `project.json` grows a top-level `plot_defaults` key (mirrors `plot_settings_dialog._USER_DEFAULTS`) plus a per-tab `tabs[<name>].plot_config = {...}` payload. `project_io.py` handles serialisation; `binah.py` wires load-time read into the dialog module + each tab's `_plot_config`. Dialog API is unchanged. Important so a user who customises font sizes (e.g. for accessibility) doesn't have to redo the work each session |
| ✅ | 🔴 | **Remove duplicate section title from operation panels (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4l. Resolved Phase 4n (CS-25): stale `tk.Label` deleted from `uvvis_normalise.py`, `uvvis_smoothing.py`, `uvvis_peak_picking.py`, `uvvis_second_derivative.py`. Baseline Correction was already correct. Each panel's test file gained a `test_no_inline_title_label_inside_panel_body` regression assertion that walks the widget tree and fails if a stale title `tk.Label` returns |
| ✅ | 🔴 | **Right-sidebar responsive layout extension (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4l. Resolved Phase 4n (CS-26): the always-visible minimum grew from five to seven cells (`state · [☑] · label · ⌥n · [⚙] · [→] · [✕]`); ⌥n provenance count was promoted out of the optional set. Single 280 px threshold replaced by three priority-ordered thresholds — swatch @ 240, leg @ 280, ls\_canvas @ 320 — so optional cells reveal in priority order as the row widens. The fourth-priority "line width entry" cell deferred (no per-row line-width control today; reachable via the StyleDialog universal section). `_apply_responsive_layout` reflows `leg` + `ls_canvas` together to preserve the canonical visual order under Tk's overflow auto-unmap |
| ✅ | 🔴 | **Send to Compare per-row icon (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4l (originally Phase 4l friction #7). Folded into CS-27 alongside the "Send to Compare" register row above — the per-row icon replaces the legacy top-bar `+ Add to TDDFT Overlay` bulk button. See the "Send to Compare" register row above and CS-27 in COMPONENTS.md |
| ✅ | 🟡 | **Scattering-functional baseline mode** | USER-FLAGGED at end of Phase 4l. Resolved Phase 4m (CS-24): new `params["mode"] == "scattering"` discriminator on `OperationType.BASELINE`. Helper `compute_scattering(wavelength_nm, absorbance, params)` fits `B(λ) = c · λ^(-n)` over a user-defined peak-free window and subtracts the result across the full input range. `params["n"]` is either a numeric exponent (closed-form least-squares for `c` only) or the string `"fit"` (log–log linear regression for both `c` and `n`; requires absorbance > 0 throughout the fit window). UI parameter row: `n:` Entry (default `"4"` ≈ Rayleigh) + `Fit n` Checkbutton (disables the n entry when checked) + `Fit lo (nm):` / `Fit hi (nm):` entries. `BASELINE_MODES` grew from 4 to 5; combobox auto-pulled the new entry; `_DISPATCH` and `_collect_baseline_params` gained the new branch. Reuses provisional BASELINE node shape from CS-15 — renderer and ScanTreeWidget needed no changes. 472 tests, all green (12 pure-module + 2 integration new) |
| ⏳ | 🔴 | **Per-node baseline-curve toggle (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4o. The Phase 4o "Baseline curves" toggle (CS-29) is global — turning it on enables the dashed overlay for *every* visible BASELINE node at once, which crowds the plot when more than two or three baselines are visible. Likely shape: a per-row gesture on the ScanTreeWidget BASELINE rows (sibling to the existing visibility `[☑]`), or a `style["show_baseline_curve"]` key surfaced in the StyleDialog universal section so the per-node choice is also persistable per node and survives a project reload. Touches `scan_tree_widget._populate_node_row` (or `style_dialog.py` if going the style-key route) and `uvvis_tab._redraw`'s baseline-curve overlay loop (gate on the per-node key in addition to the global toggle). Pairs with the legend-density entry below |
| ⏳ | 🟡 | **Baseline-curve overlay legend density** | Surfaced in Phase 4o while landing CS-29. With N visible BASELINE nodes and the global "Baseline curves" toggle on, the plot legend grows by N "<label> (baseline)" rows. Stays readable up to ~3 baselines but starts to dominate the frame at 5+. Cheapest mitigation: add a separate "show baseline in legend" preference (style key or top-bar toggle) so the dashed overlay can render without the legend doubling in size. Deeper fix is the per-node baseline-curve gate above (gate the legend at the same time as the overlay). Touches `uvvis_tab._redraw`'s overlay branch and possibly the StyleDialog universal section |
| ✅ | 🔴 | **Show baseline function on the plot (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4n. Resolved Phase 4o (CS-29): new top-bar `tk.Checkbutton` "Baseline curves" wired to `self._show_baseline_curves` Tk BooleanVar (default off — opt-in review aid; no behaviour change for existing flows). When on, `_redraw` walks every visible BASELINE node, calls the new pure helper `uvvis_baseline.compute_baseline_curve(graph, baseline_node)` to recover the fitted baseline as `parent.absorbance - baseline.absorbance`, and plots it dashed (linestyle `"--"`, alpha 0.7) in the BASELINE node's colour. Legend entry is `"<node label> (baseline)"` when `style["in_legend"]` is on. Helper returns `None` on every failure (wrong type, missing arrays, no parent, shape mismatch); the loop simply skips so a malformed graph never crashes the renderer. Per-node toggle elevated as a separate USER-FLAGGED carry-forward (the global toggle clutters when many BASELINE nodes are visible) |
| ⏳ | 🔴 | **Scattering baseline floor-zero shift (CS-24 follow-up) (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4n. The current `compute_scattering` returns `A - c·λ^(-n)`. For colloidal samples the corrected spectrum's minimum is often slightly negative (the fitted scattering tail can over- or under-shoot in the peak-free window). The user wants the corrected spectrum's minimum guaranteed ≥ 0 across the whole range — a sibling fitted offset `a` such that `B(λ) = a + c·λ^(-n)` and the post-subtraction floor is explicitly clamped (or fitted) to zero. Two paths: (a) extend `compute_scattering` to fit a constant offset alongside `c` (and `n`, if not pinned) — overlaps with Phase 4m friction #3 (composite `scattering+offset` mode); (b) post-subtraction shift to make `min(corrected) == 0` (preserves the fit but adds a fixed offset to every point). User's intent reads more like (a). Pin the params naming so the fitted offset is exportable (Phase 4m friction #2 / `n_fitted` analog: `params["a_fitted"]`) |
| ⏳ | 🔴 | **Diagnostic console / fitted-parameter panel (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4n. Several places in the app produce numeric diagnostics that currently live only in `OperationNode.params` and never surface to the user: scattering log fit's resolved n (Phase 4m friction #2), upcoming scattering+offset's `a_fitted`, polynomial baseline fit residuals, peak-picking match list, rubberband convex-hull point count, etc. The user is asking whether a small read-only "console" or "log" pane (a scrolling text widget at the bottom of the app or a per-tab footer) would carry these. Two shapes worth weighing: (a) **per-tab inline diagnostic strip** — small read-only panel at the bottom of each tab's left pane that names the most recently applied op and lists its key fitted values; refreshed on every Apply; (b) **app-wide log console** — a collapsible bottom drawer (like an IDE's output pane) that streams every op's "results" line plus warnings / errors / debug; survives tab switches. (b) doubles as a place for the `_redraw` KeyError trace (Phase 4n friction #1) and the messagebox messages currently shown via popups (e.g. "no Compare host connected"). Both shapes are non-trivial; pick before any Phase 4 follow-up that needs to surface a fitted value |
| ✅ | 🔴 | **Defensive guard in `_redraw` for non-UVVIS DataNodes** | Surfaced by Phase 4n while writing the Send-to-Compare integration test. Resolved Phase 4o (CS-28): positive guard at the top of the per-node loop body (`if "wavelength_nm" not in node.arrays or "absorbance" not in node.arrays: continue`) and a mirror guard wrapped around the unit==`"nm"` xlim min/max comprehension. Silent skip — the diagnostic-console entry (still ⏳) will eventually surface skipped nodes. The Phase 4n note that BASELINE's schema was `wavelength_nm + baseline` was inaccurate — live BASELINE nodes carry `wavelength_nm + absorbance` (line 937 of `uvvis_tab.py`); the only `baseline`-keyed BASELINE in the codebase was the deliberately-malformed stub in `test_send_node_to_compare_skips_non_uvvis_nodes`, which the Phase 4o follow-up commit simplified to use the new guard rather than stub `graph.get_node` |
| ⏳ | 🟡 | **Long-provenance hist button display options (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4n. The `⌥{n}` always-visible cell (CS-26 promotion) renders the provenance chain length as a literal integer. For complex workflows `n > 9` is realistic — the row's natural width grows with the digit count, which can re-trigger the responsive overflow pattern at the same widths today's tests verify. Options to weigh in the implementing session: (a) cap display at `⌥9+` once n > 9 with the exact count surfaced via tooltip / history sub-frame; (b) two-digit fixed width (`⌥01`...`⌥99`) so the row's natural width is bounded but the count remains readable; (c) hide digits entirely (just `⌥`) and surface the count only via the expanded history sub-frame; (d) SI-suffix style (`⌥9`, `⌥1k` for >999). Touches `scan_tree_widget._populate_node_row` (the `text=f"⌥{chain_len}"` line) and the existing `test_provenance_op_count` style assertions. User has confirmed `n > 9` is "easily seen for complex workflows" so this is not edge-case |
| ⏳ | 🟢 | **Threshold-band caching for responsive helper (technical debt)** | Phase 4n CS-26's `_apply_responsive_layout` unconditionally pack_forget+repacks every optional cell on every call (rather than tracking last-applied state) because Tk auto-unmap under overflow makes `winfo_ismapped()` an unsound "have" oracle. The fix is correct but does redundant work on every `<Configure>` event at the same width. Cache the last applied "threshold band" per row (e.g. one of `(none, swatch, swatch+leg, all)`) and short-circuit the reflow when the new width falls in the same band. Care needed: the cache must be invalidated on `_populate_node_row` (a row rebuild starts fresh). Cheap polish; defer until flicker is observed in real use |
| ⏳ | 🟢 | **Test convention: `_root.update()` over `update_idletasks()` for geometry** | Surfaced during Phase 4n CS-26 test work. `update_idletasks()` flushes idle handlers but does NOT trigger Tk's geometry pass on a withdrawn root; `winfo_ismapped()` lags reality until the next event cycle. Pre-CS-26 responsive tests got away with `update_idletasks` because the helper packed less aggressively; CS-26's unconditional reflow exposed the gap. Document the convention in `test_scan_tree_widget`'s module docstring (and the equivalent docstrings in any future widget tests that read mapped state): "after a layout-changing call on a withdrawn `_root`, use `_root.update()`, not `update_idletasks()`, before reading `winfo_ismapped`". One-paragraph doc edit; no code change |

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

*Document version: 1.14 — May 2026*
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
*1.8: Phase 4j — collapsible left-pane sections lands (CS-21);
Collapsible left-pane sections register entry marked ✅; Phase
4i friction #1 (palette duplication) and #2 (left-pane density)
both resolved in this phase. New `node_styles.pick_default_color`
helper unifies the six pre-4j palette-index expressions; new
`collapsible_section.py` widget wraps each of the five operation
sections with a clickable chevron header. Production fix landed
in-phase: `scan_tree_widget._begin_label_edit` now binds its
StringVar to an explicit master so multi-Tk-root code paths stay
correct. Phase 4j friction logged (six items: StringVar fix
already resolved, palette-counter behaviour change, section
state not persisted, first-run UX, per-panel subject combobox
redundancy, unit-naïve wavelength entries). Four new register
entries: 🔴 Unify subject combobox across left-pane sections
(architectural, USER-FLAGGED), 🟡 Expand all / Collapse all
gesture, 🟡 Unit-aware wavelength / energy picker (USER-FLAGGED),
🟢 Keyboard accessibility for CollapsibleSection (Phase 11).*
*1.9: Phase 4k — shared subject combobox lands (CS-22); Unify
subject combobox register entry marked ✅; Phase 4j friction #5
resolved. The five per-panel `_subject_cb` widgets are gone;
each operation panel now exposes `set_subject(node_id)` +
`ACCEPTED_PARENT_TYPES` (panel-class constant) and disables its
Apply button when the shared selection isn't a valid parent.
The host's StringVar trace fans the change out to all four
panels + the inline baseline section. Phase 4k friction logged
(six items: no left-pane accept gesture USER-FLAGGED, sweep-
group per-variant gestures USER-FLAGGED, Plot Settings dialog
Save & Close USER-FLAGGED, fall-back-on-deletion uses insertion
order, no inline explanation for disabled Apply, baseline-vs-
panel naming inconsistency). Three new register entries: 🔴
Commit / discard reachable from the left pane after Apply
(USER-FLAGGED), 🔴 Per-variant gestures on sweep-group rows
(USER-FLAGGED, elevated from Phase 2 carry-forward), 🔴 Plot
Settings dialog: Save & Close (USER-FLAGGED).*
*1.10: Post-Phase-4k — friction-list cleanup pass. USER-FLAGGED
that the cumulative friction list (13 sections, 83 items)
was getting unwieldy and increasingly misleading: many items
were silently resolved by later phases without strike-through,
and three repeating chains (palette duplication, left-pane
density, status-bar API split) had grown to 5 / 3 / 3
duplicate entries each. Cleanup pass: strikethrough + ✅
resolution stamps on 11 silently-resolved items (palette dup
chain 4c→4h, left-pane density chain 4g/4h, default-style
duplication chain 4d/4e, subject-combobox chain 4c/4g/4j,
`_uvvis_nodes` divergence 4c/4d). Cross-references added to
collapse repeating chains to one canonical entry per root
issue (status-bar at 4e #5; ∀ apply-to-all scope at 4h #2;
JSON `default=str` at 4f #6; click-on-axis at 4c #2). Session
structure step 6 extended with three responsibilities
(register update + prior-phase strike-through + chain
collapse) plus a pruning policy: items struck-through for
≥3 phases collapse into a "Resolved friction history" log at
end of Phase 4 to keep active lists from re-bloating.*
*1.11: Phase 4l — Plot Settings dialog Save button lands
(CS-23); Phase 4k friction #3 struck through. Five new
register entries logged: 🔴 Audit dialog button-row
vocabulary across the app + write convention into
ARCHITECTURE.md (USER-FLAGGED), 🔴 Plot config + plot defaults
persistence to project.json (USER-FLAGGED, elevated from
Phase 4b friction #1 + #5), 🔴 Remove duplicate section title
from operation panels (USER-FLAGGED, surfaced from testing
redesign/main), 🔴 Right-sidebar responsive layout extension
(USER-FLAGGED — minimum visible set widened to six cells with
provenance + Send-to-Compare icons), 🟡 Scattering-functional
baseline mode (USER-FLAGGED — `1/λ^n` form for colloidal /
turbid samples). Existing "Send to Compare" register entry
extended with the Phase 4l USER-FLAGGED constraint that the
gesture be a per-row icon, not a top-bar button. Phase 4b
friction #1 + #5 cross-ref the new persistence register
entry as the canonical chain.*
*1.14: Phase 4o — defensive `_redraw` guard (CS-28) + dashed
baseline-curve overlay (CS-29). Phase 4n register entries "Show
baseline function on the plot" and "Defensive guard in `_redraw`
for non-UVVIS DataNodes" both marked ✅. Phase 4n friction #1
(`KeyError 'absorbance'`) struck through with a clarification
that the friction note's BASELINE schema description was
inaccurate (live nodes carry `wavelength_nm + absorbance`; the
only `baseline`-keyed BASELINE was a deliberately-malformed test
stub). Phase 4o friction logged (three items: per-node baseline-
curve gate USER-FLAGGED, overlay legend density, friction-note
schema accuracy as a process improvement). Two new register
entries: 🔴 Per-node baseline-curve toggle (USER-FLAGGED), 🟡
Baseline-curve overlay legend density. The
`test_send_node_to_compare_skips_non_uvvis_nodes` get_node stub
workaround was simplified to use the new guard instead of the
lambda override.*
*Supersedes: BACKLOG.md (original)*
