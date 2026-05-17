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
| ✅ | 🟡 | **Sweep group inline expansion** | Per-variant editing (commit/discard/restyle one variant at a time). Resolved Phase 4q (CS-32): chevron `▸/▾` on the leader row toggles inline rendering of every member as a full-chrome row (state · swatch · ☑ · label · ⌥n · ⚙ · → · 🔒 · ✕) reusing `_populate_node_row`. Expansion state lives in `self._expanded_sweep_groups: set[str]` keyed by parent_id, mirroring `_expanded_history`; survives every rebuild. Group dissolves naturally when a member commits / discards down to <2 — `_compute_sweep_groups` returns no entry, leader row + chevron disappear. Same phase delivered the 🔒 (CS-34) on every provisional row, so committing a single variant is one click. See COMPONENTS.md "CS-32 — Sweep group inline expansion (Phase 4q)" |
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
   *Frequency reduced* in Phase 4q (CS-34): every PROVISIONAL
   row in the right-sidebar now carries a per-row 🔒 commit
   button between → and ✕, so single-click commit no longer
   requires the right-click context menu. The left-pane gesture
   (Accept-last / Discard-last button-pair) remains the open
   convenience-layer follow-up; the register entry stays ⏳ at
   🟡 (dropped from 🔴) because CS-34 satisfies the spirit of
   the original USER-FLAG.
2. ~~**Sweep-group rows hide per-variant gestures.**
   USER-FLAGGED at end of Phase 4k. When a parent has 2+
   provisional children, the right-side ScanTreeWidget collapses
   them into a sweep-group leader row with `✕all`; the user can
   expand to see the variants but cannot commit / discard / style
   any single one. Phase 2 carry-forward "Sweep group inline
   expansion" (🟡) is now actively biting; elevated to 🔴 and
   re-flagged. See the new register entry "Per-variant gestures on
   sweep-group rows". *Frequency reduced* in Phase 4p (CS-31):
   sweep groups no longer fire on identical re-applies, so users
   hit this friction only on real parameter sweeps. **Per-variant
   gestures still pending** — see the Phase 4p register entry
   "Inline expansion + per-variant gestures on sweep-group rows
   (CS-04 §6.3 follow-through)" deferred to Phase 4q (CS-32).~~
   ✅ Resolved in Phase 4q (CS-32). Chevron `▸/▾` on the leader
   row toggles inline rendering of every member as a full-chrome
   row, with CS-34's 🔒 making single-variant commits one click.
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
2. ~~**Scattering n="fit" loses the resolved numeric n in `op.params`.**
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
   the day a future op fits a parameter the user didn't pin.~~
   ✅ Resolved in Phase 4s (CS-39). Public helpers
   `uvvis_baseline.fit_scattering` / `fit_scattering_offset` return
   the resolved fit parameters as `{c_fitted, n_fitted}` (and
   `a_fitted` for the composite); the apply site writes them into
   `op_params` after `compute()` returns successfully. ScanTreeWidget
   tooltip / export header surface still ⏳ — folds into the open
   Diagnostic console / fitted-parameter panel register entry.
3. ~~**Composite "scattering + offset" mode is not covered.** Real
   colloidal samples often have both a Rayleigh / Mie tail AND an
   instrument or solvent offset: `B(λ) = a + c · λ^(-n)`. CS-24
   captures the pure power-law form per the Phase 4l brief; a
   composite mode (additive constant fit alongside c and optionally
   n) is the natural follow-up if users find that pure scattering
   leaves a flat residual. Likely shape: a sixth `mode == "scattering+offset"`
   that fits 2–3 parameters by linear least squares with `x = [1, λ^(-n)]`
   columns (when n is fixed) or by a small nonlinear solver (when
   n is fit alongside c and a).~~ ✅ Resolved in Phase 4s (CS-38).
   `BASELINE_MODES` grew to 6 with the new `"scattering+offset"`
   entry; `compute_scattering_offset` does 2-D linear LSQ for fixed
   `n` and a 1-D bounded scan over `n` for `n="fit"`; UI shares the
   scattering Tk vars + parameter row layout. **Open follow-up:**
   user has flagged that the two-mode split should consolidate into
   a single `scattering` mode with an "Add offset" Checkbutton —
   see new register entry "Consolidate scattering+offset into
   scattering with optional offset toggle" above.
4. ~~**Fit-window-out-of-range errors don't show the spectrum's actual
   nm range.** Polynomial and scattering both raise "needs ≥ N points
   in fit window [x, y]" when the user types a window outside the
   data; the messagebox shows the requested window but not the data
   range, so a user typing "200–350" on a spectrum that starts at
   400 has to re-read the plot to figure out the offset. Trivial to
   widen the error message to include `[wl.min(), wl.max()]`. Touches
   `uvvis_baseline.py` (polynomial + scattering paths). Same diagnostic
   gap likely exists in `uvvis_normalise.py` peak / area windows.~~
   ✅ Resolved in Phase 4s (CS-40). Fit-window error messages in
   `compute_polynomial`, `compute_scattering`, the new
   `compute_scattering_offset` (via shared `_scattering_window`),
   and `uvvis_normalise._window_mask` all append
   `"; data spans [<min>, <max>] nm"` so the user sees the
   spectrum's actual range without re-reading the plot.
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
4. ~~🔴 **Responsive helper does redundant pack/forget work on every
   Configure event.** USER-FLAGGED at end of Phase 4n. CS-26's
   `_apply_responsive_layout` unconditionally pack_forget+repacks
   every optional cell on every call, because Tk's auto-unmap under
   overflow makes `winfo_ismapped()` an unsound oracle for "is this
   widget currently in our intended layout?". Correct but redundant
   on rapid Configure events at the same width. Strategy: cache
   the last applied "threshold band" per row and short-circuit when
   the new width falls in the same band. See the new register entry
   "Threshold-band caching for responsive helper (technical debt)".~~
   ✅ Substantially mitigated in Phase 4p (CS-30): the per-row
   `<Configure>` binding was removed, so the rapid-Configure storm
   that motivated the caching pass no longer fires. The canvas-
   `<Configure>` binding fires once per real sidebar resize, which
   is human-paced and never rapid enough to flicker. The unconditional
   pack_forget+repack pattern remains at the helper level (still the
   correct response to Tk's auto-unmap rule), but the redundant-work
   concern is now empirically inert. The "Threshold-band caching"
   register entry stays ⏳ as defer-until-flicker-observed, not
   as a known live cost.
5. 🔴 ~~**`⌥{n}` always-visible cell grows with digit count for long
   provenance chains.** USER-FLAGGED at end of Phase 4n. The cell
   renders `text=f"⌥{chain_len}"` literally; for `n > 9` the cell's
   natural width grows by ~9 px per digit, which re-triggers the
   responsive overflow pattern at widths today's tests verify safe.~~
   ✅ Threshold-decision impact resolved in Phase 4p (CS-30): the
   helper now keys on `_scroll_canvas.winfo_width()` (the actual
   sidebar width), not row natural width, so the ⌥n digit-count
   contribution to row natural width is irrelevant to whether
   optional cells pack. The visual concern — long ⌥n + long label
   pushing the row's natural width past the canvas width — is now
   the same friction as #6 below (the new Phase 4p friction on
   long node names) and is addressed there. The "Long-provenance
   hist button display options" register entry stays ⏳ as the
   visual-shape decision (cap at ⌥9+ vs two-digit fixed vs hide
   digits vs SI-suffix); the responsive-overflow trigger that
   originally motivated it is gone.
   User has confirmed `n > 9` is realistic for complex workflows.
   See the new register entry "Long-provenance hist button display
   options (USER-FLAGGED)" — four shape options to weigh.

### Friction points carried forward from Phase 4o

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4o while landing the defensive `_redraw`
guard (CS-28) and the dashed baseline-curve overlay (CS-29). Items
1 and 2 are USER-FLAGGED; item 3 is a process-improvement note.
**Do not fix until the relevant subsequent Phase 4 session.**

1. ~~🔴 **No per-node baseline-curve gate (USER-FLAGGED).** The new
   "Baseline curves" toggle is a single tab-level boolean; turning
   it on enables the dashed overlay for *every* visible BASELINE
   node at once. With more than two or three baselines visible the
   plot crowds quickly. Likely shape: a per-row toggle on the
   ScanTreeWidget BASELINE rows (sibling to the existing visibility
   `[☑]`), or a dedicated style-dict key (`style["show_baseline_curve"]`)
   exposed in the StyleDialog universal section so the per-node
   choice is also persistable. Pairs with #2 below (per-node gate
   would naturally limit legend density too). See the new register
   entry "Per-node baseline-curve toggle (USER-FLAGGED)".~~ ✅
   Resolved in Phase 4r (CS-36) — went the per-row gesture route on
   the ScanTreeWidget (not the StyleDialog universal section, which
   stayed locked); `[~]/[–]` button on BASELINE rows only flips
   `style["show_baseline_curve"]` via `set_style`; the CS-29 overlay
   loop adds one filter line consulting the new key. Default-True
   convention parallels `visible`/`in_legend`; backwards compat for
   existing graphs. Pairs with #2 below — per-node hide does drop
   both overlay and legend entry simultaneously, which partially
   mitigates legend density; the standalone "show baseline in
   legend" preference remains open.
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

### Friction points carried forward from Phase 4p

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4p while landing the canvas-driven
responsive layout (CS-30) and the param-equality apply-time
gate (CS-31). Item #1 is the deferred 4p → 4q split; #2 is
USER-FLAGGED with cross-ref to the open Diagnostic console
intent; #3 is USER-FLAGGED and is the obvious next-up
follow-on for the responsive-row work; #4 is a process
improvement note. **Do not fix until the relevant subsequent
Phase 4 session.**

1. ~~🔴 **CS-32 (inline expansion + per-variant gestures on
   sweep-group rows) deferred to Phase 4q.** Originally
   bundled with CS-30 + CS-31 in Phase 4p decision lock, but
   CS-30 expanded scope (the responsive layout fix needed a
   helper-signature change, a per-row Configure-binding
   removal, and a test-stub refactor on top of the inner-frame
   width fix). Splitting CS-32 into its own phase keeps the
   commit budget honest. The register entry stays ⏳ as the
   obvious primary intent for Phase 4q. Phase 4q's hand-off
   inherits the decision-lock notes from this session
   (chevron `▸/▾` toggle, full-chrome inline rows reusing
   `_populate_node_row`, `_expanded_sweep_groups: set[str]`
   keyed by parent_id mirroring `_expanded_history`, `🔒`
   commit button next to `✕` on member rows). No new register
   entry — see the existing "Inline expansion + per-variant
   gestures on sweep-group rows (CS-04 §6.3 follow-through)"
   entry.~~ ✅ Resolved in Phase 4q (CS-32). The 4p decision-
   lock notes were inherited verbatim and the register entry
   landed without scope drift.

2. ~~🔴 **CS-31's "no new node created" status message has weak
   discoverability (USER-FLAGGED).** The duplicate-apply
   message lands on the panel's `_status_cb` (or
   `self._status_lbl` for the baseline path on UVVisTab) — a
   small label below the operation panels. A user clicking
   Apply twice expecting visible action might not notice the
   message and conclude the second click did nothing for an
   unknown reason. This pairs naturally with the existing
   USER-FLAGGED open intent **"Diagnostic console / fitted-
   parameter panel"** (Phase 4n carry-forward, register row
   above): once that landing site exists, every CS-31
   suppression should also write a `dedup` line into the
   console so the message survives subsequent UI actions and
   sits in a place the user actively reads. Until then, the
   panel-level status label is the only surface — acceptable
   but worth elevating once the diagnostic console lands. No
   new register entry — folds into the Diagnostic console
   intent.~~ ✅ Resolved in Phase 4ac (CS-54). The CS-31
   short-circuit is gone, so the "no new node created" status
   message has no path to surface — the apply now creates a
   real sibling. Discoverability concern moot.

3. ~~🔴 **Long node names can push the row's natural width past
   the canvas width (USER-FLAGGED).** Surfaced by the user at
   end of Phase 4p in response to the CS-30 architecture
   note. UV/Vis processing accumulates suffixes onto labels
   (e.g. `NiAqua · baseline (linear) · norm (peak)` is ~40
   chars after two ops; with three or four ops in a chain
   labels reach 60-80 chars). With CS-30, the helper still
   makes the right pack/unpack decisions because it keys on
   canvas width, not row natural width — so all rows uniformly
   show the same column structure (the user-flagged invariant
   is preserved). But the row's *natural* width can exceed the
   canvas width when label + all packed widgets together don't
   fit, causing horizontal overflow / scroll. User explicitly
   said all rows must share column widths — so any mitigation
   has to apply uniformly, not "this one row truncates because
   it has a longer label". Likely shape options: (a) truncate
   labels in the row with full label in tooltip + the
   widget's existing in-place rename gesture (double-click)
   for explicit label viewing; (b) wrap label to two lines
   (changes row height, may interact with sweep-group
   expansion height); (c) move the label to a fixed-width
   column with a fade-out/ellipsis on overflow; (d) reserve
   minimum widths per cell and shrink the label first. (a) is
   the cheapest and matches typical desktop conventions. See
   the new register entry "Truncate long node-name labels in
   ScanTreeWidget rows (USER-FLAGGED)".~~ ✅ Resolved in
   Phase 4q (CS-33), shape (a) — module-level
   `_LABEL_MAX_CHARS = 32` cap with `…` truncation, hover
   tooltip via `_Tooltip` (Toplevel) only when truncation
   actually cut text, in-place rename reads the canonical
   full label from the graph rather than the painted text.
   The cap-from-canvas-width-and-font-metrics follow-up is
   tracked as a new 🟢 register entry.

4. **Test fragility around `_root` state contamination
   (process note).** Surfaced during CS-30 work. The canvas's
   actual width during full-file test runs depends on prior
   test classes — `TestScanTreeWidgetResponsiveRow`'s setUp
   creates `tk.Frame(_root, width=800, height=400)` with
   `pack_propagate(False)`, but the canvas-`<Configure>`
   event still fires at 200 px (rather than 800) when the
   class runs after `TestScanTreeWidget` /
   `TestScanTreeWidgetBugB001` etc. The fix in this phase was
   to bypass `event.width` entirely in the canvas Configure
   handler (read `winfo_width()` instead so test stubs flow
   through) and to extend `_force_width(row, N)` to also stub
   the owning canvas's `winfo_width`. Pattern worth
   replicating in any future widget test class that depends
   on geometry: stub canvas widths explicitly, do not trust
   `event.width` as deterministic across full-file runs. Pair
   with the Phase 4n process note "Test convention:
   `_root.update()` over `update_idletasks()`" — same root
   cause (Tk geometry behaviour on a withdrawn `_root` is
   sensitive to accumulated state). Documentation-style; no
   register entry.

### Friction points carried forward from Phase 4q

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4q while landing the sweep-group inline
expansion (CS-32), label truncation with hover tooltip (CS-33),
and per-row 🔒 commit gesture on provisional rows (CS-34). All
five items below were surfaced by Claude at end-of-session and
confirmed by the user verbatim. **Do not fix until the relevant
subsequent Phase 4 session.**

1. 🟡 **Left-pane Accept-last button-pair still open after CS-34
   (USER-FLAGGED, partially-resolved).** CS-34 lands a per-row
   🔒 commit button on the right-side ScanTreeWidget, which
   replaces the right-click context menu requirement and
   satisfies the spirit of the original Phase 4k friction #1
   ("commit / discard reachable from the left pane after Apply").
   The literal "Accept last / Discard last" button-pair inside
   the left-pane status area (or under each operation panel's
   Apply) remains unbuilt. See the still-open register entry
   "Commit / discard reachable from the left pane after Apply
   (USER-FLAGGED)" — priority dropped from 🔴 to 🟡 because the
   single-click-no-traversal half is now in place.

2. 🟢 **`_LABEL_MAX_CHARS` is hardcoded.** CS-33 caps label
   text at 32 characters regardless of canvas width or font
   metrics. Works for typical UV/Vis chains and the default Tk
   font, but a high-DPI font on a narrow sidebar could fit
   fewer chars and a small monospace font on a wide sidebar
   could fit more. See the new register entry "Compute label-
   truncation cap from canvas width / font metrics (CS-33
   follow-up)". Defer until a user reports either over- or
   under-truncation on their actual setup.

3. 🟢 ~~**`_Tooltip` lives inside `scan_tree_widget.py`.** CS-33
   added a small Toplevel-based hover tooltip co-located in
   the widget module. Other surfaces will eventually need the
   same shape (Plot Settings dialog parameter hints, StyleDialog
   "what does this control" hints, panel-status messages on
   hover). On first cross-module re-use, extract into a
   `tooltip.py` utility module so the second consumer doesn't
   either re-implement or import a private name. See the new
   register entry "Promote `_Tooltip` to a shared utility
   module on first cross-module re-use".~~ ✅ Resolved in
   Phase 4t (CS-42) — `tooltip.py` created with public class
   `Tooltip`; `scan_tree_widget` imports it and renames its
   two existing call sites; second consumer is `uvvis_tab`
   (the floor-zero Checkbutton, CS-43); third consumer is the
   per-row `[~]` baseline-curve toggle (resolves the paired
   Phase 4r friction #1 entry below).

4. **Tooltip rendering is timing-dependent (process note).**
   The `_Tooltip` Toplevel pops after a 600 ms `widget.after`
   delay; the test suite doesn't drive the Tk event loop, so
   `TestTooltip` covers construction, ``update_text``
   rotation, and idempotent `_hide` only. Verifying the
   rendered Toplevel itself is left to manual smoke. Worth
   noting if the delay constant or the rendered widget shape
   ever changes — re-test by hovering over a long-label row
   in the running app. Documentation-style; no register entry.

5. ~~🟢 **Sweep-group expanded members lack visual nesting.**
   After CS-32 lands, a sweep-group member row can also have
   its provenance history expanded via `⌥n`. The existing
   `_render_history` packs the history sub-frame below the
   row at the same indent level as siblings, so visually it
   sits between sweep members rather than indented beneath
   the one it belongs to. Cosmetic; a user could be momentarily
   confused. See the new register entry "Indent expanded sub-
   frames inside sweep groups (visual nesting)".~~ ✅ Resolved
   in Phase 4r (CS-35) — `_SWEEP_MEMBER_INDENT_PX = 16`
   constant + `indent_px` kwarg threaded through
   `_build_node_row`'s `padx=(2 + indent_px, 2)` pack call;
   sweep-expansion branch in `_rebuild` passes the constant.
   The history sub-frame inside an expanded member row
   inherits the parent row's indent (since `_render_history`
   packs into the row's children frame), so visual nesting
   for `⌥n` history under a sweep-member row is also correct
   without separate threading.

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
| ✅ | 🟢 | **Second derivative** | Single-algorithm Savitzky-Golay derivative (`scipy.signal.savgol_filter` with `deriv=2`); no mode discriminator (the savgol routine smooths and differentiates in one pass — naive `np.gradient` would be a footgun mode rather than a useful alternative). Output is a provisional `SECOND_DERIVATIVE` `DataNode` rendered as a curve overlay on the same plot (reuses the `wavelength_nm` / `absorbance` schema; the latter holds d²A/dλ² values). `SecondDerivativePanel` co-located in `uvvis_second_derivative.py` (Phase 4i; CS-20). Chained derivatives intentionally out of scope (SecondDerivativePanel excludes SECOND_DERIVATIVE from its own `ACCEPTED_PARENT_TYPES`). **Phase 4x (CS-49) update:** `SECOND_DERIVATIVE` is no longer hidden from the shared subject combobox — `SmoothingPanel.ACCEPTED_PARENT_TYPES` was widened to include it (closes the user-flagged "Cannot smooth derivative plots" Phase 4w friction #1), so `_refresh_shared_subjects` now walks both `_spectrum_nodes` and `_second_derivative_nodes`. The renderer-side separation (the two helpers as distinct iterations for axis-role routing under CS-44) is unchanged. Baseline / normalise / peak-picking still refuse SECOND_DERIVATIVE per audit decision |
| ⏳ | 🟢 | **Beer-Lambert / concentration** | Use known ε to extract concentration, or fit ε from known concentration |
| ✅ | 🔴 | **Collapsible left-pane sections (polish session)** | Each of the five operation sections (Baseline / Normalisation / Smoothing / Peak picking / Second derivative) is now wrapped in a clickable `CollapsibleSection` header with a chevron (▶ collapsed, ▼ expanded). **All five sections start collapsed.** State is per-tab Tk `BooleanVar` owned by each section widget; not persisted to project (Phase 8 concern). Paired with the `pick_default_color(graph)` extraction in the same phase — both touched every operation module at once and a single phase unlocked all four (Phase 4c / 4e / 4g / 4h). Resolved Phase 4i friction #1 + #2 + Phase 4g #5 / 4h #5 carry-forwards (Phase 4j; CS-21) |
| ✅ | 🔴 | **Unify subject combobox across left-pane sections (architectural)** | USER-FLAGGED at end of Phase 4j. Replaced the five per-panel `_subject_cb` widgets with one shared `_shared_subject_cb` at the top of the left pane (always visible, above every CollapsibleSection). Each operation panel exposes `set_subject(node_id)` + `ACCEPTED_PARENT_TYPES`; the host's StringVar trace fans the selection out to all four panels + the inline baseline section. Apply buttons disable when the shared selection isn't a valid parent for the panel's op. **Phase 4x (CS-49) widening update:** `_BASELINE_ACCEPTED_PARENT_TYPES` is now `(UVVIS, BASELINE, SMOOTHED)`; `SmoothingPanel.ACCEPTED_PARENT_TYPES` is `(UVVIS, BASELINE, NORMALISED, SMOOTHED, SECOND_DERIVATIVE)`. `NormalisationPanel` (UVVIS, BASELINE, NORMALISED) and `PeakPickingPanel` / `SecondDerivativePanel` (UVVIS, BASELINE, NORMALISED, SMOOTHED) intentionally NOT widened — see CS-49 register entry below. Resolved Phase 4j friction #5 (Phase 4k; CS-22) |
| ⏳ | 🟡 | **Commit / discard reachable from the left pane after Apply (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4k. **Partially resolved Phase 4q (CS-34)**: every PROVISIONAL ScanTreeWidget row now carries a per-row 🔒 (commit) button between → and ✕, omitted entirely on committed rows (the leftmost-cell 🔒 state indicator already signals committed state). Right-click context menu retained as the fallback gesture. **Still open**: the literal "Accept last / Discard last" button-pair inside the left-pane status area (or under each operation panel's Apply). The single-click commit gesture now lives on the right sidebar with no traversal cost; the left-pane gesture is a convenience layer that targets the most-recently-applied output of each op. Priority dropped from 🔴 to 🟡 because CS-34 satisfies the spirit of the original USER-FLAG (one click to commit after Apply, no right-click) |
| ✅ | 🔴 | ~~**Per-variant gestures on sweep-group rows (USER-FLAGGED)**~~ | ✅ Resolved in Phase 4q (CS-32). See the canonical entry "Inline expansion + per-variant gestures on sweep-group rows (CS-04 §6.3 follow-through) (USER-FLAGGED)" below — both share the same root and chevron-driven implementation |
| ⏳ | 🟡 | **Expand all / Collapse all gesture on left pane** | Companion polish for the new collapsible sections (Phase 4j). When a user wants to scan parameter choices across multiple sections (e.g. for a screenshot or to copy parameters from one panel to another) they currently have to click each header individually. Options: a small "▼ All / ▶ All" icon button at the top of the left pane (above the Processing label), or a right-click context menu on any section header with "Expand all" / "Collapse all" entries. Either is a small change — adds a method on `UVVisTab` that walks the five `_{name}_section` attributes and calls `expand()` / `collapse()` on each |
| ⏳ | 🟡 | **Unit-aware wavelength / energy picker for operation panels** | USER-FLAGGED at end of Phase 4j. The five operation panels collect wavelength/energy windows via free-form Entry widgets in nm only. The plot itself supports x in nm / cm⁻¹ / eV (top-bar combobox); the panels should follow whatever unit the plot is currently displaying so a user reading peak positions off the plot can type them straight into the entry without a mental unit conversion. Likely shape: a unit-aware Spinbox / Entry that watches the tab's `_x_unit` Tk var, converts the entered value to nm at Apply time (the canonical wavelength_nm storage stays nm), and re-renders the entry's display when the user flips units. Touches every panel that has a wavelength / energy parameter (baseline polynomial fit window, baseline spline anchors, normalisation window, peak-picking manual list). Plan once Phase 4j has bedded in |
| ⏳ | 🟢 | **Keyboard accessibility for `CollapsibleSection`** | The Phase 4j `CollapsibleSection` is a single mouse-clickable strip with no Tab focus indication or keyboard binding. For accessibility (and power users who prefer keyboard navigation) Tab-to-header + Space/Enter-to-toggle would mirror standard disclosure-widget conventions. Phase 11 (app-wide polish) — defer until other accessibility passes happen at the same time |
| ⏳ | 🔴 | **Audit dialog button-row vocabulary across app + write convention into ARCHITECTURE.md (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4l. Phase 4l (CS-23) brought Plot Settings into parity with StyleDialog (`Apply · Save · Cancel`), but other modals in the app (file pickers, future Beer-Lambert preview, future scattering-baseline preview, future Send-to-Compare confirmation) haven't been audited. Without a written convention, future modals re-derive button vocabulary ad-hoc and the user's Cancel-vs-Save mental model erodes. Plan: walk every `tk.Toplevel` / dialog construction site, document the canonical four-button shape (`Apply · ∀ Apply to All · Save · Cancel`) in `ARCHITECTURE.md` as a UI convention with explicit rules for when each slot may be dropped (e.g. `∀ Apply to All` collapses when there is no node-bulk concept; CS-14 demonstrates), and refactor the outliers. Touches every dialog module + ARCHITECTURE.md. Pairs naturally with Phase 4l friction #1 (Plot Settings 3-button special case) |
| ✅ | 🔴 | **Plot config + plot defaults persistence to project.json (CS-13 follow-up) (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4l. **Subsumed Phase 4r** by the broader "Project + per-node persistence with manifest+sidecar+optional-blockchain-anchor architecture" entry below — that entry is the four-phase ladder this row is one rung of. **Resolved Phase 4v (CS-46):** Phase A of the persistence umbrella ships the manifest+sidecar round-trip; top-level `plot_defaults` key now persists through `plot_settings_dialog._USER_DEFAULTS` and per-tab `tabs[<name>].plot_config` carries each tab's plot config payload. **Note:** project-specific plot defaults (vs the app-global `_USER_DEFAULTS`) are tracked separately by the new "Project-specific plot defaults + import from another project" register entry below |
| ⏳ | 🔴 | **Project + per-node persistence with manifest+sidecar+optional-blockchain-anchor architecture (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4r. **Phase A ✅ Resolved Phase 4v (CS-46):** unprotected manifest+sidecar round-trip shipped via the new `project_io.py` (full rewrite). Phases B (subgraph export), C (Merkle/signed), and D (OpenTimestamps) remain ⏳. Umbrella ticket for project-save and per-node-save with eventual tamper-evidence. Existing "Plot config + plot defaults persistence to project.json" entry above is **Phase A** of the ladder. **Architecture (locked Phase 4r):** content-addressed manifest JSON + sidecar HDF5 files referenced by SHA-256 hash. Sidecars carry every raw array (DataNode arrays + the original instrument file as a first-class sidecar). Single `protected: bool` header flag gates the verification path on load. The same on-disk shape supports unprotected and protected; the difference is whether an `integrity` block is present and signed/anchored. **Four-phase ladder (each phase ships independently):** **Phase A** — unprotected manifest + sidecar round-trip; replaces the existing `project_io.py` save/load shape; absorbs the Plot config persistence row above. **Phase B** — per-node subgraph export; same schema with `subgraph_root: <node_id>` + `scope: "ancestors" \| "ancestors_plus_branches" \| "selected"` field; walks `input_ids` upward and (for selected scopes) downward from the root; one `.ptmg` archive contains the full processing history of a single node. **Phase C** — tamper-evident manifest: per-node SHA-256 over canonical-form serialisation, Merkle tree leaves, Ed25519-signed root; `protected: true` makes verification mandatory on load. No external dependencies, no real blockchain. **Phase D** — OpenTimestamps anchoring: submit the Merkle root to the OpenTimestamps aggregator (free, batched into Bitcoin via Merkle proof), store the timestamp proof alongside the manifest. This is the "blockchain protected" piece — third-party verifiable, anchored to Bitcoin. **Schema decisions locked:** sidecar HDF5 always (never inline base64 — bigger files break "single file" UX anyway); `OperationNode` carries a `deterministic: bool` field so deterministic-output DataNodes can skip storing arrays (re-derived on load) while Monte Carlo / non-deterministic outputs always persist; UX bundles the manifest + sidecars into a single `.ptmg` archive (zip-with-extension) for transport, unpacks into a directory for editing — open either form, save to either form. **Affected modules:** `project_io.py` (full rewrite — schema versioning + manifest + sidecar walk), `binah.py` (load-time wiring), every tab's `_plot_config` (Phase A), node export currently scoped to single-node CSV in `node_export.py` (Phase B grows the equivalent with full history + sidecar). `nodes.py` may need a `deterministic: bool` on `OperationNode`. Compatibility with existing project files is NOT a goal (per user). **Phase A is the natural next-up Phase 4 session**; Phases B–D are subsequent. Pairs with: existing "Difference spectra" entry (multi-input op format needs Phase A), every Phase 4l friction #1 dialog-button-vocabulary entry (file dialogs follow the same convention), the upcoming floor-zero feature entry below (per-mode `floor_zero: bool` in params must round-trip Phase A) |
| ✅ | 🔴 | **Remove duplicate section title from operation panels (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4l. Resolved Phase 4n (CS-25): stale `tk.Label` deleted from `uvvis_normalise.py`, `uvvis_smoothing.py`, `uvvis_peak_picking.py`, `uvvis_second_derivative.py`. Baseline Correction was already correct. Each panel's test file gained a `test_no_inline_title_label_inside_panel_body` regression assertion that walks the widget tree and fails if a stale title `tk.Label` returns |
| ✅ | 🔴 | **Right-sidebar responsive layout extension (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4l. Resolved Phase 4n (CS-26): the always-visible minimum grew from five to seven cells (`state · [☑] · label · ⌥n · [⚙] · [→] · [✕]`); ⌥n provenance count was promoted out of the optional set. Single 280 px threshold replaced by three priority-ordered thresholds — swatch @ 240, leg @ 280, ls\_canvas @ 320 — so optional cells reveal in priority order as the row widens. The fourth-priority "line width entry" cell deferred (no per-row line-width control today; reachable via the StyleDialog universal section). `_apply_responsive_layout` reflows `leg` + `ls_canvas` together to preserve the canonical visual order under Tk's overflow auto-unmap |
| ✅ | 🔴 | **Send to Compare per-row icon (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4l (originally Phase 4l friction #7). Folded into CS-27 alongside the "Send to Compare" register row above — the per-row icon replaces the legacy top-bar `+ Add to TDDFT Overlay` bulk button. See the "Send to Compare" register row above and CS-27 in COMPONENTS.md |
| ✅ | 🟡 | **Scattering-functional baseline mode** | USER-FLAGGED at end of Phase 4l. Resolved Phase 4m (CS-24): new `params["mode"] == "scattering"` discriminator on `OperationType.BASELINE`. Helper `compute_scattering(wavelength_nm, absorbance, params)` fits `B(λ) = c · λ^(-n)` over a user-defined peak-free window and subtracts the result across the full input range. `params["n"]` is either a numeric exponent (closed-form least-squares for `c` only) or the string `"fit"` (log–log linear regression for both `c` and `n`; requires absorbance > 0 throughout the fit window). UI parameter row: `n:` Entry (default `"4"` ≈ Rayleigh) + `Fit n` Checkbutton (disables the n entry when checked) + `Fit lo (nm):` / `Fit hi (nm):` entries. `BASELINE_MODES` grew from 4 to 5; combobox auto-pulled the new entry; `_DISPATCH` and `_collect_baseline_params` gained the new branch. Reuses provisional BASELINE node shape from CS-15 — renderer and ScanTreeWidget needed no changes. 472 tests, all green (12 pure-module + 2 integration new) |
| ✅ | 🔴 | **Per-node baseline-curve toggle (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4o. Resolved Phase 4r (CS-36): new `style["show_baseline_curve"]` style key with default-True convention (parallels `visible` / `in_legend`); per-row `tk.Button("~"/"–")` packed between `[☑]` and the label on BASELINE rows ONLY in `_populate_node_row`; click routes through `self._graph.set_style` so `NODE_STYLE_CHANGED` triggers `uvvis_tab._redraw`. The CS-29 overlay loop adds one filter line consulting the new key; global toggle stays as the master switch (CS-29 contract preserved). StyleDialog universal-section path deferred (Phase 4d / 4f lock held; new per-row gesture is more discoverable). Pairs with the legend-density entry below — that one is partially mitigated (per-node hide drops both overlay AND legend entry simultaneously) but the standalone "show baseline in legend" preference is still open. 9 new tests (2 pure-module style-key, 7 integration row-button) |
| ⏳ | 🟡 | **Baseline-curve overlay legend density** | Surfaced in Phase 4o while landing CS-29. With N visible BASELINE nodes and the global "Baseline curves" toggle on, the plot legend grows by N "<label> (baseline)" rows. Stays readable up to ~3 baselines but starts to dominate the frame at 5+. Cheapest mitigation: add a separate "show baseline in legend" preference (style key or top-bar toggle) so the dashed overlay can render without the legend doubling in size. Deeper fix is the per-node baseline-curve gate above (gate the legend at the same time as the overlay). Touches `uvvis_tab._redraw`'s overlay branch and possibly the StyleDialog universal section |
| ✅ | 🔴 | **Show baseline function on the plot (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4n. Resolved Phase 4o (CS-29): new top-bar `tk.Checkbutton` "Baseline curves" wired to `self._show_baseline_curves` Tk BooleanVar (default off — opt-in review aid; no behaviour change for existing flows). When on, `_redraw` walks every visible BASELINE node, calls the new pure helper `uvvis_baseline.compute_baseline_curve(graph, baseline_node)` to recover the fitted baseline as `parent.absorbance - baseline.absorbance`, and plots it dashed (linestyle `"--"`, alpha 0.7) in the BASELINE node's colour. Legend entry is `"<node label> (baseline)"` when `style["in_legend"]` is on. Helper returns `None` on every failure (wrong type, missing arrays, no parent, shape mismatch); the loop simply skips so a malformed graph never crashes the renderer. Per-node toggle elevated as a separate USER-FLAGGED carry-forward (the global toggle clutters when many BASELINE nodes are visible) |
| ✅ | 🟡 | **Scattering baseline fitted-offset (CS-24 follow-up) (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4n. Reframed Phase 4r as the narrower additive-offset variant `B(λ) = a + c·λ^(-n)` (orthogonal to the universal floor-zero constraint). Resolved Phase 4s (CS-38) as a sixth `BASELINE_MODES` entry (`"scattering+offset"`) with `compute_scattering_offset` doing 2-D linear LSQ for fixed `n` and a 1-D bounded scan over `n` for `n="fit"`. UI shares scattering's Tk vars (`_baseline_scattering_n`, `_baseline_scattering_fit_n`, `_baseline_scattering_fit_lo/hi`) — same parameter row layout. Apply persists `params["a_fitted"]` (always) + `params["c_fitted"]` (always) + `params["n_fitted"]` (when `n="fit"`) per CS-39. **Pairs with the new "Consolidate scattering+offset into scattering with optional offset toggle" register entry below** — the user has flagged that the two-mode split should collapse into a single `scattering` mode with an optional offset checkbox (default off ⇒ a=0 ⇒ pure power law) for cleaner UX |
| ✅ | 🔴 | **Floor-zero baseline as fit-time constraint, per mode (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4r. Universal "Floor at zero" toggle in the baseline panel that, when on, guarantees the corrected absorbance (`parent - B`) is ≥ 0 across the entire range, regardless of which baseline mode is active. **Architecture (locked Phase 4r):** the constraint is enforced at *fit time* by passing `floor_zero=True` into the per-mode `compute_*` functions, not by a post-fit shift. **Phase 4s (CS-37) shipped 3/6 modes:** scattering (closed-form constrained `c`); scattering+offset (convex QP via SLSQP); rubberband (no-op + invariant assert). **Phase 4t (CS-37 expansion) shipped the remaining 3/6 modes:** **linear** (SLSQP on the (a_lo, a_hi) anchor pair, objective minimises L2 distance from the unconstrained sampled values, LinearConstraint at every full-range sample). **polynomial** (SLSQP on the polynomial coefficients with z-space normalization `z = (wl - center) / half_range` so the Vandermonde stays well-scaled for arbitrary order; converted back to wl-space `np.polyfit` ordering by evaluating + re-fitting). **spline** (SLSQP on the per-anchor absorbance vector via NonlinearConstraint that re-uses the shared `_spline_evaluate` helper across all three branches — 4-anchor cubic, 3-anchor quadratic, 2-anchor linear). All five SLSQP-based modes surface convergence failure as `ValueError("<mode> floor-zero fit did not converge: …")`. **UI:** panel-level "Floor at zero" `tk.Checkbutton` in `bl_body`. **Params round-trip:** `params["floor_zero"]: bool` recorded on every BASELINE OperationNode at apply time. **Resolved Phase 4t:** all six modes ship the constrained-fit code path; `_FLOOR_ZERO_SUPPORTED_MODES = frozenset(BASELINE_MODES)` (CS-43); `TestFloorZeroNotYetImplemented` removed and replaced with three behavioural test classes (TestLinearFloorZero / TestPolynomialFloorZero / TestSplineFloorZero) plus three new apply-site integration tests in TestUVVisTabBaseline |
| ✅ | 🟡 | **Floor-zero toggle disabled state for unsupported baseline modes (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4s. Resolved Phase 4t (CS-43): module-level `_FLOOR_ZERO_SUPPORTED_MODES: frozenset[str]` initialised to `frozenset(uvvis_baseline.BASELINE_MODES)` (defensive scaffolding — Phase 4t shipped floor-zero for all six modes so the disabled branch never fires today); `_FLOOR_ZERO_DISABLED_TOOLTIP: str` carries the hover hint. New `UVVisTab._refresh_floor_zero_state()` method wired to `_baseline_mode`'s trace alongside `_refresh_baseline_param_rows`; calls `_baseline_floor_zero_cb.config(state="normal" or "disabled")` and rotates the tooltip text via `update_text` between the empty string (supported — Tooltip._show bails) and `_FLOOR_ZERO_DISABLED_TOOLTIP` (unsupported — hover hint paints). The BooleanVar value is preserved across enable/disable transitions per the persistence-umbrella carry-forward design lock. Initial calibration call at end of `_init_left_pane`. Tooltip on the Checkbutton constructed once at panel build time and stored as `_baseline_floor_zero_tooltip` so the refresh method can rotate text in place. Four integration tests in TestUVVisTabBaseline pin the contract |
| ⏳ | 🟡 | **Consolidate scattering+offset into scattering with optional offset toggle (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4s. CS-38 shipped scattering+offset as a sixth `BASELINE_MODES` entry, sharing Tk vars with `scattering`. The user has flagged that the two-mode split is overkill — cleaner UX is a single `scattering` mode with an "Add offset" `tk.Checkbutton` (default off ⇒ a=0 ⇒ pure power law). Concretely: shrink `BASELINE_MODES` back to 5 (drop `scattering+offset`); add `_baseline_scattering_offset: tk.BooleanVar(value=False)` Tk var; surface as a Checkbutton inside the scattering parameter rows; `_collect_baseline_params` reads the var and either calls `compute_scattering` (offset=False) or `compute_scattering_offset` (offset=True) — OR unify both helpers into a single `compute_scattering` that branches on `params["offset"]: bool`. The latter is cleaner (single dispatch entry, one set of fit logic). The shared `_scattering_window` / `_scattering_fit` / `_scattering_offset_fit` helpers in Phase 4s are already the right factoring for this consolidation. **Affected:** `uvvis_baseline.py` (collapse two `compute_*` into one with offset branch; possibly drop `compute_scattering_offset` and `fit_scattering_offset` public names or keep them as thin wrappers), `uvvis_tab.py` (drop `scattering+offset` mode branch in `_refresh_baseline_param_rows` + `_collect_baseline_params`; add offset Checkbutton to scattering rows), tests, COMPONENTS.md (CS-38 section either drops or restructures). Cross-refs the Phase 4m friction #3 register row above (struck through Phase 4s) — the consolidation is the natural follow-up that ships the user's preferred UX shape |
| ⏳ | 🟢 | **Scattering n-fit scan bounds configurable via params** | Surfaced Phase 4s. **API ✅ shipped Phase 4t (CS-41):** `params["n_bounds"]: tuple[float, float]` (default `(0.1, 8.0)`) overrides the bounded-scan range in `_scattering_fit` (under `floor_zero=True` only — the unconstrained branch uses log–log linear regression with no bounds) and `_scattering_offset_fit` (always — its 2-D LSQ requires the bounded scan). Validated via `_resolve_n_bounds(params)` (must be a 2-tuple, both ≥ 0, lo < hi). Eight pure-module tests in TestNFitBoundsConfigurable. **UI ⏳ deferred:** the matching Tk row (two extra Entries surfaced when "Fit n" is checked, default-prefill from `_DEFAULT_N_BOUNDS`) ships when a user reports a fit pinned at the bound. Touches `uvvis_tab.py` (new Tk vars + conditional row in `_refresh_baseline_param_rows`) + `_collect_baseline_params` (thread `n_bounds` into the scattering / scattering+offset params dicts) |
| ⏳ | 🔴 | **OLIS .ols / .asc UV/Vis file format support (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4s. Today the UV/Vis loader handles only the existing supported set (see `uvvis_parser.py`). OLIS instruments produce `.ols` (binary) and/or `.asc` (ASCII column) files that aren't parseable today, blocking import of OLIS spectra into Ptarmigan. Shape depends on the OLIS family — likely a new parser branch in `uvvis_parser.py` keyed on filename suffix (`.ols` → binary header parse + array decode; `.asc` → column-text parse) returning the same `wavelength_nm`/`absorbance` array pair as the existing parsers. Touches `uvvis_parser.py` (new parse_*  function + dispatch by suffix), `binah.py` (file-open dialog filter widens), `test_uvvis_parser.py` (round-trip against a sample OLIS file). Pairs with the persistence umbrella above — the original instrument file is a first-class sidecar in Phase A, so OLIS files need to round-trip the manifest cleanly. The OLIS sample-file format reference will need to be sourced from the user (instrument manufacturer documentation or example files) — implementation session blocks until samples are available |
| ✅ | 🟡 | **Per-row `[~]` baseline-curve toggle column alignment across all node types (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4t. **Resolved Phase 4w (CS-48):** rather than packing a disabled placeholder Button, every row now gets a fixed-width `row_toggle` Frame slot (`tk.Frame(row, width=_CELL_MIN_PX["row_toggle"])` with `pack_propagate(False)`) at the same x-coordinate. On BASELINE rows the `[~]/[–]` Button is parented to that Frame; on every other type the slot is an empty placeholder. Labels start at the same x across UVVIS / BASELINE / NORMALISED / SMOOTHED / PEAK_LIST / SECOND_DERIVATIVE rows. The original lock-decision proposal (`state="disabled"` Button on every row) was rejected during Phase 4w design: an invisible Frame is cheaper (one Tk widget per non-BASELINE row vs a Button + tooltip) and avoids the "what does a disabled `[~]` mean?" UX confusion. CS-36's BASELINE-row behaviour preserved verbatim (button parented inside the Frame slot rather than directly to the row). Five integration tests in TestRowToggleColumnAlignment + the existing TestPerNodeBaselineCurveToggle helper updated to recurse into the slot |
| ✅ | 🟡 | **Second-derivative plot on separate right y-axis (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4t. **Resolved Phase 4u (CS-44):** broadened from the originally-flagged "right axis for SECOND_DERIVATIVE" into a general multi-axis routing system per the user's "we may need to build in other secondary axes for other processes and might even need to add a third y-axis somehow in some cases" expansion. Architecture (locked Phase 4u step 2): `_AXIS_ROLES = ("primary", "secondary", "tertiary")` constant; `_DEFAULT_Y_AXIS_BY_NODETYPE: dict[NodeType, str]` per-NodeType mapping (UVVIS / BASELINE / NORMALISED / SMOOTHED / PEAK_LIST → "primary"; SECOND_DERIVATIVE → "secondary"; future NodeTypes get a one-line table edit); `_NON_PRIMARY_Y_LABEL: dict[(NodeType, x_unit), str]` x-unit-aware label table (d²A/dλ² for nm, d²A/d(cm⁻¹)² for cm-1, d²A/dE² for eV — Q3 user decision); `_TERTIARY_AXIS_OFFSET_FRAC: float = 1.12` module constant (Q2 user decision: tunable later via a Plot Settings field). Two pure helpers — `_resolve_y_axis_role(node_type)` returns the role; `_resolve_non_primary_y_label(node_type, x_unit)` returns the role's label or None. `_redraw` builds `self._axes_by_role: dict[str, Axes]` lazily via an inner `get_axis(role)` closure: primary is always available; secondary creates `_ax.twinx()`; tertiary creates a second `twinx()` with right spine offset by the constant. CS-29 baseline-curve overlay and CS-19 peak-list scatter route through the same resolver for consistency (both → "primary" today). Per-style override hook (`node.style.get("y_axis")`) deferred per Q1 user decision; per-role y-limit Tk vars deferred per Decision 4. Legend handles + labels merged across every populated role before drawn on primary so a SECOND_DERIVATIVE node on the right axis still appears in the unified legend. `_draw_empty` `_fig.clear()`s + reseeds the role map so populated → empty transitions don't leak twin axes. 14 new tests (9 pure-helper + 5 integration including a tertiary-path test that monkey-patches `_resolve_y_axis_role` to validate the offset-spine end-to-end). 651 tests, all green |
| ✅ | 🔴 | **Auditable provenance / process versioning for data processing protocols (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4u (step 5 elicitation). **Resolved Phase 4v (CS-45):** new `operation_hash.py` module hosts a per-OperationType registry mapping each op to the bundle of `compute_*` + shared helpers that constitute its implementation. `compute_implementation_hash(op_type)` returns the SHA-256 of the sorted-by-qualname concatenation of `inspect.getsource()` bytes for every registered callable, domain-separated by op name. Six apply sites (BASELINE / NORMALISE / SMOOTH / PEAK_PICK / SECOND_DERIVATIVE / LOAD) stamp `metadata["implementation_hash"]` at apply time. Project load (CS-46) recomputes the hash and surfaces drift via `LoadedProject.implementation_warnings`, wrapped in a "Implementation Changed Since Save" dialog (Keep cached + Show details; Re-run all changed deferred to the new register entry below). Lock decisions taken: (a) automatic source-hash via `inspect.getsource` (zero developer overhead; auto-detects the Phase 4t conditioning swap that motivated the entry); (b) warn-only messagebox with two buttons (Keep / Show details) — Re-run needs a workflow-replay mechanism deferred to a follow-up. Original framing kept for traceability: the user has flagged that if the datastream and its processing are to be safely logged, the *implementations of the processing protocols themselves* should be tagged, logged, and protected in a way that's auditable. Today every `OperationNode` records `op_type`, `params`, and the Ptarmigan `__version__` at apply time, but the actual code path that produced the result is not pinned — between two Ptarmigan versions a `compute_polynomial` could change its conditioning strategy (Phase 4t did exactly this) without any runtime-detectable trace beyond the version string. Architecture lock pending: most likely shape is a per-OperationType "implementation hash" — either an automatic SHA-256 of the function source bytes (recoverable via `inspect.getsource(compute_*)`) OR a manually-bumped semver string co-located with each `compute_*` (`compute_polynomial.__implementation_version__ = "2.1"`); the chosen value gets stamped into `OperationNode.metadata["implementation_hash"]` at apply time. Project load (Persistence Phase A) verifies each OperationNode's stored hash against the current binary's hash and surfaces a "implementation changed since this project was saved — re-run to refresh, or keep the cached output as-is" dialog. Pairs tightly with the persistence umbrella's "manifest+sidecar+optional-blockchain-anchor architecture" — both are integrity stories at different layers (persistence = bit-level data integrity; this = code-level protocol integrity). Cross-refs CS-03 (params completeness) — the user's question is whether params completeness is enough to *replay* an op, vs whether the code that interprets those params is itself frozen. Touches every `compute_*` module (registration of the version/hash), the `OperationNode` shape (new metadata key), the apply sites (stamp at apply time), the persistence layer (verify at load time), and likely a new "Audit" pane / dialog showing the version diff. Lock decision needed: automatic source-hash vs manual semver; on-mismatch policy (warn-only vs require user action vs auto-rerun) |
| ⏳ | 🔴 | **Baseline as separate first-class node + node algebra for linear combinations (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4u (step 5 elicitation). Architectural change to the BASELINE NodeType. **Two motivating observations from the user:** (a) the baseline curve overlay (CS-29) currently inherits the *corrected* spectrum's color, but it's visually closer to the *parent* spectrum it was subtracted from, so the overlay color should track the parent; (b) when a baseline is fit to one dataset because the background is an instrumental effect, the same fitted curve should be applicable to other datasets with the same instrumental background, but today there's no way to detach the curve from its parent context. **Architecture proposal (lock pending):** introduce a new `NodeType.BASELINE_CURVE` that holds *just the curve* (the y-values being subtracted) — first-class DataNode with `arrays["wavelength_nm"]` + `arrays["absorbance"]` (the term "absorbance" is then a slight abuse but preserves the universal renderer schema), inherits parent style for color, can be re-applied to other UVVIS / NORMALISED / SMOOTHED nodes via a new "Apply baseline curve" gesture. The current `NodeType.BASELINE` (the corrected spectrum) becomes a derived combination — output of a SUBTRACT node-algebra OperationNode (`corrected = parent - baseline_curve`). **Node algebra extension:** new OperationTypes for ADD / SUBTRACT / SCALE / LINEAR_COMBO that take 1–N input DataNodes + scalar coefficients and emit a derived DataNode. Multi-input parent edges already supported by the graph. **Cross-refs:** the existing 🟡 "Difference spectra" register entry in Phase 5 collapses into this entry (`A_ref - A_sample` is just SUBTRACT between two UVVIS); CS-29's baseline-curve overlay branch in `_redraw` becomes a render-time subscription to the BASELINE_CURVE node instead of an ad-hoc walk + `compute_baseline_curve` call. **Affected modules:** `nodes.py` (new NodeType + OperationTypes), `graph.py` (multi-input edge invariants — already there for AVERAGED / DIFFERENCE), `uvvis_baseline.py` (split apply: produce BASELINE_CURVE + SUBTRACT op + corrected DataNode in one apply gesture), `uvvis_tab._redraw` (BASELINE_CURVE renders alongside parent on primary axis with parent's color), `scan_tree_widget` (new row type), `style_dialog` (universal section with new "tied to parent color" checkbox), tests across the board. Multi-phase task; persistence-umbrella prerequisite for the cross-dataset re-apply story (sidecar storage of fitted curves). **Lock decisions for the implementing session:** (i) does the SUBTRACT op auto-create when applying a baseline (preserving today's one-click UX) or does the user place it explicitly? (ii) does BASELINE_CURVE inherit the parent's color via a new `style["color_source"]: "parent"` style key, or via auto-tinting at render time with no per-node persisted color? (iii) is the existing `NodeType.BASELINE` retired, renamed (e.g. CORRECTED), or kept as an alias? |
| ⏳ | 🟡 | **Multinode dataset import + combination for joint analytics (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4u (step 5 elicitation). Two facets to the user's flag: (a) **import** of multinode datasets — instruments produce 2-D scans (e.g. kinetic series, temperature ramps, parameter sweeps) where each row is a spectrum and the second axis carries the sweep variable; today every spectrum loads as a separate top-level UVVIS node, losing the structural relationship; (b) **combine** existing single-node spectra into a "dataset" for joint analytics. Both reduce to the same architectural primitive: a `NodeType.SPECTRUM_DATASET` (or `MULTINODE` / `SERIES`) that carries a list of child node IDs + a sweep-axis vector (`arrays["sweep_axis"]` + a unit/label) + a stacking convention (rows-as-spectra). **Import path:** new parser branch in `uvvis_parser.py` that detects 2-D file shapes and produces N child UVVIS nodes plus one parent SPECTRUM_DATASET node wired by parent edges. **Combine path:** new ScanTreeWidget gesture or panel button "Combine selected → Dataset" that takes the selected nodes and wraps them in a new SPECTRUM_DATASET, validating that they share a common wavelength grid (or interpolating to a shared one as a sub-decision). Pairs with **(a)** the OLIS reader register entry (OLIS files often *are* multinode) and **(b)** the SVD register entry below (SVD operates on the dataset, not on a single spectrum). **Lock decisions for the implementing session:** (i) does `SPECTRUM_DATASET` carry its own `arrays` (the stacked matrix) or only references to its children? (ii) is the wavelength-grid mismatch policy "must be identical" or "auto-interpolate to a shared grid"? (iii) does Apply on a panel produce one DataNode (averaged result) or N DataNodes (one per row)? Multi-phase task; the simpler "combine selected" path can ship before the parser-side multinode detection |
| ⏳ | 🟡 | **Singular value decomposition + multinode chemometric methods (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4u (step 5 elicitation). User's framing: "explore multinode datasets where things are changing — both to formally explore chemically-relevant changes across multiple parameters, but also to explore and handle sample decomposition behaviour during data acquisition." Concretely a chemometrics panel: SVD of the wavelength × sweep matrix (singular values, U/V components), PCA (mean-centred SVD with explained-variance ratios), MCR-ALS (multivariate curve resolution alternating least squares — concentration profiles + pure component spectra under constraints), target factor analysis. **Prerequisite:** the SPECTRUM_DATASET register entry above. **Output shape:** each method emits one or more derived DataNodes (e.g. SVD → N "U-component" spectra + a "singular values" diagnostic + an "S-component" sweep-axis profile per component) wired to the SPECTRUM_DATASET parent. **Affected modules:** new `uvvis_chemometrics.py` (pure-numerical scipy/numpy compute) + new `ChemometricsPanel`, new NodeType(s) for the outputs (`COMPONENT_SPECTRUM`, `COMPONENT_PROFILE`?), new render path for the U/V component pair displayed side-by-side. Pairs with the diagnostic-console register entry (singular values / explained-variance % belong on a diagnostic strip not a popup). **Lock decisions for the implementing session:** (i) which chemometrics methods ship in v1 (SVD-only is the cheapest; MCR-ALS the most user-valuable but heaviest); (ii) whether each method has its own panel or all live in a tabbed "Chemometrics" panel; (iii) how component-count selection works (auto-by-eigenvalue-threshold vs user-driven Spinbox vs scree-plot-click) |
| ✅ | 🟡 | **Dynamic sidebar auto-width for long node labels (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4u (step 5 elicitation); re-flagged at end of Phase 4v (bumped to 🔴). **Resolved Phase 4w (CS-47):** new `ScanTreeWidget.widest_label_pixel_width()` walks current candidate nodes and returns max font.measure(label); `UVVisTab._calibrate_sidebar_width` runs once via `after_idle` after construction, computes target = clamp(widest_label_px + overhead_px, [_SIDEBAR_MIN_WIDTH_PX=240, _SIDEBAR_MAX_CALIBRATED_PX=480]), and calls `body.sash_place(2, paned_width - target, 0)` to size the sash. **Lock decision taken:** one-shot only — `_sidebar_calibrated` flag flips True after the first successful run so manual sash drags persist across rebuilds. Pairs with the new dynamic label-truncation cap (CS-47): the sash auto-bump complements the dynamic label cap so wider sidebars show more text and narrower ones truncate harder. The "every cell + minimum width" scope expansion from Phase 4v step 5 ships as `_CELL_MIN_PX` (documented vocabulary of every row cell's minimum natural width — state, swatch, vis_cb, row_toggle, label, leg, ls_canvas, hist, gear, compare, commit, x) plus `_SIDEBAR_MIN_WIDTH_PX = 240` (pinned floor matching the smallest responsive threshold, also driving the PanedWindow's `body.add(sidebar_pane, minsize=…)`). 18 new integration tests across TestRowToggleColumnAlignment / TestDynamicLabelCapWiring / TestWidestLabelPixelWidth / TestUVVisTabSidebarCalibration |
| ⏳ | 🟡 | **Detachable sidebar windows / pop-out panels (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4u (step 5 elicitation). User has flagged that sidebars (left pane operation panels, right pane ScanTreeWidget) should be detachable into their own top-level windows so a multi-monitor user can keep the plot main-screen and the controls on a side screen. Tk supports this via `Toplevel` + reparenting (`pack_forget` from the original PanedWindow + repack into a new `tk.Toplevel`); on close the panel re-attaches. **Affected:** every tab's left + right pane shell. The simplest shape ships at the host level (`binah.py` adds a "↗ pop out" button per pane that toggles between attached and detached); a per-pane gear menu is a more polished follow-up. Lock decisions needed: (i) one Toplevel per pane vs per tab; (ii) does pane state (collapsed sections, scroll position) survive the round trip; (iii) does the host close → panel close, or does the panel persist and re-attach on host re-open. Cross-refs the long-running CS-04 ScanTreeWidget cohabitation work — the right pane is already widget-shaped enough to detach cleanly; the left pane's collapsible sections (Phase 4f) are too. Multi-phase if both panes ship together |
| ⏳ | 🟡 | **Colour-blind-safe palette (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4u (step 5 elicitation). Today `node_styles.SPECTRUM_PALETTE` is matplotlib's default tab10 sequence (ten entries, e.g. `#1f77b4` blue / `#d62728` red / `#2ca02c` green) — this palette is NOT optimised for colour-blindness; deuteranopia conflates the red/green pair, protanopia conflates the orange/red pair. The user has flagged that colour choices should be limited to a colour-blind-safe palette. **Lock decision needed:** which palette — Wong / Okabe-Ito 8-colour (`#000000 #E69F00 #56B4E9 #009E73 #F0E442 #0072B2 #D55E00 #CC79A7 #999999`), Tol's vibrant 7-colour, ColorBrewer's qualitative palettes? Wong/Okabe-Ito is the de facto scientific-publication standard. **Affected:** `node_styles.SPECTRUM_PALETTE` (CS-21 is *locked* but USER-FLAGGED change supersedes the lock); the existing `pick_default_color` walk works unchanged; existing graphs with previously-assigned colors are unaffected (style dict is immutable per node). New tests: `TestColorBlindSafePalette` validates the palette under simulated dichromacy (luminance-pair distance check). One-file change in node_styles.py + COMPONENTS.md doc-version bump. Pairs structurally with the future StyleDialog colour picker — the picker should ALSO restrict its swatch choices to the same palette unless the user opts into "show all colours" |
| ⏳ | 🟢 | **Parallelize heavy-compute paths (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4u (step 5 elicitation). Today every `compute_*` runs synchronously on the Tk event thread — fine for the current set (linear / polynomial / spline / scattering / scattering+offset / rubberband / savgol smoothing / second derivative / peak picking) which all return in tens of milliseconds on typical UV/Vis grids. The expensive cases that motivate parallelism are **future**: SVD on a large multinode dataset, MCR-ALS iteration, MC bootstrap (when added), Apply-to-All across a large dataset (each apply independent — embarrassingly parallel). **Architecture proposal:** introduce `compute_async` companions that return a `concurrent.futures.Future` and a "compute panel busy" UI state; the Tk event loop polls on `<<ComputeDone>>` virtual events. For NumPy-heavy work `concurrent.futures.ProcessPoolExecutor` releases the GIL; for I/O-bound work (file ingest) `ThreadPoolExecutor` is enough. Pairs with the diagnostic-console register entry (long-running ops surface progress). Defer until at least one user-reported "the UI froze for N seconds" — today's compute set doesn't justify the complexity |
| ✅ | 🟡 | **`_absorbance_to_y` should not transform SECOND_DERIVATIVE values** | Surfaced Phase 4u while writing the multi-axis tests. Pre-existing bug, not introduced by Phase 4u: when `_y_unit` is `"%T"`, `_absorbance_to_y` clips values to `[-10, 10]` and applies `100·10^(-A)` — this conversion is meaningful for absorbance but corrupts d²A/dλ² values (which are typically `~0.001` and can be negative, so the clip → `100·10^(-A)` mapping produces nonsense). **Resolved Phase 4ah (CS-59 Thread B):** helper signature widened to `_absorbance_to_y(absorbance, y_unit, node_type)` with a CS-55-frozenset gate. When `node_type not in _ABSORBANCE_SPACE_NODETYPES` (currently SECOND_DERIVATIVE — the one derivative-space NodeType the tab knows about), the helper short-circuits to a pass-through regardless of y-unit. All three `_redraw` call sites (main per-node loop, baseline-curve overlay, peak-list overlay) updated to pass `node.type` / `bn.type` / `peak_node.type`. PEAK_LIST + BASELINE remain in the frozenset (their values ARE absorbance), so behaviour is byte-identical for them. **Lock decision taken:** extend signature rather than branch at each call site (helper owns the rule — centralised gate keeps the three sites symmetric). 7 new tests in `TestAbsorbanceToYNodeTypeGatePhase4ah`: 1 frozenset-membership pin (drift guard); 4 pure-helper coverage (d²A passthrough on A AND %T, UVVIS conversion preserved, clip preserved on absorbance-space, A passthrough across all absorbance-space NodeTypes); 2 integration coverage (d²A values reach matplotlib unchanged on %T flip; UVVIS values STILL convert on %T flip) |
| ✅ | 🟢 | **Per-style `y_axis` override hook + StyleDialog row (CS-44 follow-up)** | Phase 4u Decision 1 deferred the per-style override (`node.style.get("y_axis")`) per the user's "Default only for now is okay" decision. The hook is wired into `_resolve_y_axis_role` as a one-line addition (read style first, fall back to per-NodeType default); the StyleDialog universal-section row is the bigger lift — a new `ttk.Combobox` choosing `"primary" / "secondary" / "tertiary"`, threaded through `_BULK_UNIVERSAL_KEYS`. Useful when a user wants to send a specific SECOND_DERIVATIVE node back to primary (small-magnitude derivatives that share scale with their parent) or send a UVVIS reference spectrum to a third axis. Defer until a user reports needing it. **Resolved Phase 4y (CS-50):** `node_styles.default_spectrum_style` adds `style["y_axis"]: str \| None` (default `None` = follow the per-NodeType default; non-None = literal CS-44 axis role overrides per-node); `_resolve_y_axis_role` grows an optional `style: Mapping \| None = None` argument and a one-line short-circuit at the front (override beats default; malformed values fall through). Renderer threads `node.style` at three call sites: per-node main loop, BASELINE-curve dashed overlay (resolver moved INSIDE per-bn body so a BASELINE on "secondary" puts both its main render AND its dashed overlay on the same axis), PEAK_LIST scatter loop. StyleDialog universal section gains a read-only `ttk.Combobox` row labelled "Y axis:" with options `["(default)", "primary", "secondary", "tertiary"]`; "(default)" round-trips to `None`. Decision lock taken: (i) cross-typed Apply auto-inherits parent's effective role on the new node IFF NodeType-defaults differ — `SmoothingPanel._apply` writes `style["y_axis"] = parent_effective_role` for smoothed-of-derivative outputs (closes Phase 4x friction #6); (ii) "(default)" = literal `None` semantics; inheritance is a separate apply-time mechanism that writes a literal role string; (iii) `y_axis` is intentionally absent from `_BULK_UNIVERSAL_KEYS` (parallel to Phase 4d's `visible` / `in_legend` carve-out — bottom ∀ Apply-to-All would too easily collapse derivatives onto primary), but the per-row ∀ button widens its scope to every renderable node (UVVIS / BASELINE / NORMALISED / SMOOTHED / SECOND_DERIVATIVE / PEAK_LIST) via `_on_uvvis_apply_to_all`'s special-case for the key. 35 new tests (7 pure-helper + 2 default-style + 16 StyleDialog Combobox + 4 renderer override + 3 cross-typed inheritance + 3 fan-out-scope). 781 tests, all green. Persistence (CS-46) auto-rides — the new key sits in the existing style-dict round-trip; no manifest schema change |
| ✅ | 🟡 | ~~**Y-axis Combobox row appears on non-UVVis StyleDialog instances (Claude-surfaced Phase 4y)**~~ ✅ Resolved in Phase 4aa (CS-52). Path (a) (NodeType-gate the row) landed: the new module-private `_Y_AXIS_VISIBLE_NODETYPES: frozenset[NodeType]` mirrors `uvvis_tab._DEFAULT_Y_AXIS_BY_NODETYPE.keys()` exactly (UVVIS / BASELINE / NORMALISED / SMOOTHED / PEAK_LIST / SECOND_DERIVATIVE), and `_build_universal_section` wraps the `_build_y_axis_row` call in `if self._node_type in _Y_AXIS_VISIBLE_NODETYPES`. For TDDFT / FEFF_PATHS / XANES / EXAFS / DEGLITCHED / AVERAGED / BXAS_RESULT the Combobox is now suppressed — the affordance no longer appears where it would be a no-op. `_read_universal_values` skips the key automatically when its var isn't in `_control_vars`, so Save / Apply / ∀ paths stay self-consistent. The drift test `test_y_axis_visible_node_types_match_routing_table` pins the gate against the routing table so a future widening of `_DEFAULT_Y_AXIS_BY_NODETYPE` (when path (b) — the multi-axis-routing lift to `plot_widget.py` — eventually lands) cannot silently reintroduce the misleading affordance. 15 new integration tests (six routing-NodeType "present" cases + seven non-routing "absent" cases + two self-consistency cases) plus 2 pure-module drift tests. |
| ✅ | 🔴 | **Y-axis label routing follows axis side, not axis role — wrong / missing labels when primary/secondary roles are swapped (USER-FLAGGED, bumped 🟢 → 🔴 in Phase 4ac)** | Originally surfaced by Claude during Phase 4y as 🟢 polish. **Bumped to 🔴 USER-FLAGGED at end of Phase 4ac (step 5 elicitation):** the user reproduced the bug end-to-end — placing Absorbance on the secondary axis and a derivative on the primary axis leaves the Absorbance label rendered on the *left* axis (because the renderer's primary-axis label is hard-coded to "Absorbance / Transmittance (%)") and the right axis appears unlabelled. Symmetrically, a SECOND_DERIVATIVE overridden to "primary" keeps the absorbance label even though the values plotted are d²A. Architecturally: CS-44's `_NON_PRIMARY_Y_LABEL` table is keyed by `(NodeType, x_unit)` and only carries entries for SECOND_DERIVATIVE; the renderer relies on the NodeType-default for the primary label (always "Absorbance" / "Transmittance (%)" today). With the CS-50 override hook landed, the table no longer covers every reachable role × NodeType combination, hence the missing-label and wrong-label visible failures. **Architecture proposal (lock pending):** option (a) introduce a `_PRIMARY_Y_LABEL: dict[(NodeType, x_unit), str]` companion table that mirrors `_NON_PRIMARY_Y_LABEL` so primary's label tracks the *first* node landing on it (CS-44 lock relaxes for both label tables); option (b) fold both into a single `_Y_LABEL_BY_ROLE_FIRST_NODE_TYPE: dict[(NodeType, x_unit), str]` lookup that the renderer reads per role from the role's first node; option (c) keep the two tables separate but widen `_NON_PRIMARY_Y_LABEL` to cover UVVIS / NORMALISED / SMOOTHED / BASELINE / PEAK_LIST on every x-unit AND build a parallel primary-side widening. **Affected:** `uvvis_tab.py` (`_redraw`'s y-label resolution + the new label table), tests pinning each role's label for every NodeType × x_unit combination. Cross-refs Phase 4u friction #9 (`_absorbance_to_y` corrupts d²A on %T) — both surface "primary axis assumes absorbance values" mistakes that pre-date the CS-50 override path. **Resolved Phase 4ad (CS-55):** option (b) variant landed — labels are role-agnostic, dimensionalised by NodeType class instead. New `_ABSORBANCE_SPACE_NODETYPES: frozenset[NodeType]` covering UVVIS / BASELINE / NORMALISED / SMOOTHED / PEAK_LIST + `_ABSORBANCE_Y_LABEL: dict[str, str]` mapping y-unit ("A" / "%T") to label, both module-level in `uvvis_tab`. New pure helper `_resolve_y_axis_label(node_type, x_unit, y_unit) -> Optional[str]`: absorbance-space NodeTypes label by y-unit (independent of x-unit and role); derivative-space NodeTypes fall through to the existing CS-44 `_NON_PRIMARY_Y_LABEL` table (which now feeds both primary and non-primary roles). Renderer in `_redraw` widens `first_node_type_per_role.setdefault` to record primary too (drop the `if role != "primary":` guard), drops the hardcoded `auto_ylabels = {"A": …}` inline lookup for primary, and walks every populated role through the helper. `ylabel_mode = "custom"` still wins for primary (user-text affordance remains primary-only); non-primary always auto. Default routing (UVVIS-only) is byte-identical pre/post — the common case is unchanged. **Lock decision taken:** option (b) variant over (a) and (c) — single helper keyed on NodeType class rather than two parallel tables, because the dimensionality of variability is NodeType nature (absorbance-space vs derivative-space), not axis role. (c) was rejected (two parallel tables would drift); (a) was rejected (mirroring `_NON_PRIMARY_Y_LABEL` for absorbance-space would force y-unit-keyed entries that contradict its `(NodeType, x_unit)` key shape). CS-44 invariants all preserved (`_NON_PRIMARY_Y_LABEL` content + `_resolve_non_primary_y_label` signature byte-identical; the new helper layers on top). 18 new tests (9 pure-module in `TestYAxisLabelResolution`: frozenset membership, drift guard against `_DEFAULT_Y_AXIS_BY_NODETYPE`, dict shape, absorbance-space y-unit invariance across x-units, derivative x-unit invariance across y-units, three `None`-return cases for unknown units / unrouted NodeTypes, backward-compat with CS-44 helper; 9 integration in `TestYAxisLabelRoleSwap`: default-routing preservation, y-unit flip, UVVIS-on-secondary case A, UVVIS-on-secondary %T flip, d²A-on-primary with parent visible, d²A alone on primary, full user-reported scenario, custom-mode wins, x-unit-aware secondary derivative). 882 tests, all green. |
| ⏳ | 🟢 | **DRY cross-typed-Apply y_axis inheritance helper (CS-50 architectural debt)** | Surfaced by Claude during Phase 4y. The CS-50 inheritance block (set `style["y_axis"]` on a new node when its NodeType-default differs from the parent's effective role) lives inside `SmoothingPanel._apply`, today the only widened cross-type panel under CS-49. If a future panel widens its `ACCEPTED_PARENT_TYPES` cross-type (NormalisationPanel accepting SECOND_DERIVATIVE; SecondDerivativePanel accepting NORMALISED on a non-UVVis x-axis; etc.), each panel's `_apply` would copy-paste the same six-line block. Move it into `node_styles.py` (or a new `axis_inheritance.py`) as `inherit_y_axis_for_cross_typed_apply(parent_node, new_node_type) -> str \| None`; every panel calls it next to its `default_spectrum_style(colour)` call. Cheap one-time refactor; defer until a second cross-typed-Apply path lands so the abstraction has two consumers. Cross-refs the four open audit-held tuples (`NormalisationPanel` / `PeakPickingPanel` / `SecondDerivativePanel`) — the next CS-49-style widening will probably be the trigger |
| ⏳ | 🟢 | **Hover/status-bar readout for active y-axis (CS-44 follow-up)** | Surfaced Phase 4u step 5. Once two y-axes coexist (CS-44), the matplotlib toolbar's coordinate readout reports primary-axis values only — a user mousing over a SECOND_DERIVATIVE point sees an absorbance number, not a d²A value. Likely shape: bind a `motion_notify_event` on the canvas, walk every populated `_axes_by_role` axis, transform the cursor's display coords into each axis's data coords, and surface the per-axis readout in a dedicated status strip below the toolbar. Cross-refs the diagnostic-console register entry — both add ambient information surfaces. Defer until two-axis use is common enough to motivate the complexity |
| ⏳ | 🟢 | **Lift multi-axis routing to plot_widget.py (CS-44 follow-up, partial — promote-to-Plot-Settings half closed Phase 4ae)** | Phase 4u Decision 7 kept the multi-axis routing inside `uvvis_tab._redraw` rather than lifting to `plot_widget.py`. The original entry had two halves; **the "promote `_TERTIARY_AXIS_OFFSET_FRAC` to Plot Settings → Appearance row" half closed in Phase 4ae (CS-56)**: new `"tertiary_axis_offset"` key in `_FACTORY_DEFAULTS` (default `1.12`, mirrors the module constant via a drift-pin test in `TestUVVisTabAppearancePhase4ae`); new float `tk.Spinbox` row in `_build_section_appearance` (row=4; bounds `1.00`–`1.50`, increment `0.01`); renderer reads `cfg.get("tertiary_axis_offset", _TERTIARY_AXIS_OFFSET_FRAC)` and passes it to the right-spine offset. The CS-44 module constant stays in place as the canonical fallback. **CS-44 lock relaxation taken in Phase 4ae:** the constant is no longer the sole source of truth — the dict key takes precedence; the helpers (`_AXIS_ROLES`, `_DEFAULT_Y_AXIS_BY_NODETYPE`, `_NON_PRIMARY_Y_LABEL`, `_resolve_y_axis_role`, `_resolve_non_primary_y_label`) stay byte-identical. **Still ⏳:** the larger lift to `plot_widget.py` (or a new `plot_axes.py`) — `_AXIS_ROLES`, `_DEFAULT_Y_AXIS_BY_NODETYPE`, `_NON_PRIMARY_Y_LABEL`, `_resolve_y_axis_role`, `_resolve_non_primary_y_label`, and the `get_axis(role)` lazy-creation closure all stay in `uvvis_tab._redraw` until a second tab (XANES / EXAFS) needs multi-axis routing. Single consumer today; no abstraction tax warranted. The new `tertiary_axis_offset` cfg-key read site lifts naturally alongside when the rest does |
| ✅ | 🟡 | **Top-bar Open File / Reload buttons belong to TDDFT only, not the app top level (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4t. The very top bar of the app currently shows `Open File` + `Reload` buttons that, in practice, only act on the TDDFT tab — they're not relevant to the UV/Vis tab (which has its own subject-loading paths inside the left pane), the XAS / EXAFS tabs (separate file paths), or the planned Compare tab. **Resolved Phase 4ah (commit 3, F):** Path (a) chosen — Open File + Reload removed from `binah._build_top_bar` and re-rendered inside the TDDFT tab's left sidebar, at the top above the "Loaded Files" listbox (`_build_main_area`). The flanking `ttk.Separator` between the buttons and the "TDDFT Section:" combobox is removed too. The `«` sidebar-toggle button + the "TDDFT Section:" combobox + the "No file loaded" file label stay in the top bar this phase (USER-CONFIRMED follow-up: a new 🟢 BACKLOG entry queues the `«` toggle + Section combobox to follow Open File / Reload in a future phase). Global `<Control-o>` keybinding stays bound to `_open_file` — keyboard-shortcut scope-by-tab is the keyboard-shortcuts whole-interface USER-FLAGGED phase's responsibility. **Lock decisions taken:** (i) path (a) over path (b) — each tab owns its own file ingestion, cleaner than tab-context-aware top-bar; (ii) global Ctrl+O unchanged; (iii) no regression test (Lock 13 — manual smoke for a one-button-parent move on a module with no existing test coverage). No test added: binah.py has no test coverage today; a Tk-rendering placement test for one button relocation is over-investment |
| ⏳ | 🔴 | **Diagnostic console / fitted-parameter panel (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4n. Several places in the app produce numeric diagnostics that currently live only in `OperationNode.params` and never surface to the user: scattering log fit's resolved n (Phase 4m friction #2), upcoming scattering+offset's `a_fitted`, polynomial baseline fit residuals, peak-picking match list, rubberband convex-hull point count, etc. The user is asking whether a small read-only "console" or "log" pane (a scrolling text widget at the bottom of the app or a per-tab footer) would carry these. Two shapes worth weighing: (a) **per-tab inline diagnostic strip** — small read-only panel at the bottom of each tab's left pane that names the most recently applied op and lists its key fitted values; refreshed on every Apply; (b) **app-wide log console** — a collapsible bottom drawer (like an IDE's output pane) that streams every op's "results" line plus warnings / errors / debug; survives tab switches. (b) doubles as a place for the `_redraw` KeyError trace (Phase 4n friction #1) and the messagebox messages currently shown via popups (e.g. "no Compare host connected"). Both shapes are non-trivial; pick before any Phase 4 follow-up that needs to surface a fitted value |
| ✅ | 🔴 | **Defensive guard in `_redraw` for non-UVVIS DataNodes** | Surfaced by Phase 4n while writing the Send-to-Compare integration test. Resolved Phase 4o (CS-28): positive guard at the top of the per-node loop body (`if "wavelength_nm" not in node.arrays or "absorbance" not in node.arrays: continue`) and a mirror guard wrapped around the unit==`"nm"` xlim min/max comprehension. Silent skip — the diagnostic-console entry (still ⏳) will eventually surface skipped nodes. The Phase 4n note that BASELINE's schema was `wavelength_nm + baseline` was inaccurate — live BASELINE nodes carry `wavelength_nm + absorbance` (line 937 of `uvvis_tab.py`); the only `baseline`-keyed BASELINE in the codebase was the deliberately-malformed stub in `test_send_node_to_compare_skips_non_uvvis_nodes`, which the Phase 4o follow-up commit simplified to use the new guard rather than stub `graph.get_node` |
| ⏳ | 🟡 | **Long-provenance hist button display options (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4n. The `⌥{n}` always-visible cell (CS-26 promotion) renders the provenance chain length as a literal integer. For complex workflows `n > 9` is realistic — the row's natural width grows with the digit count, which can re-trigger the responsive overflow pattern at the same widths today's tests verify. Options to weigh in the implementing session: (a) cap display at `⌥9+` once n > 9 with the exact count surfaced via tooltip / history sub-frame; (b) two-digit fixed width (`⌥01`...`⌥99`) so the row's natural width is bounded but the count remains readable; (c) hide digits entirely (just `⌥`) and surface the count only via the expanded history sub-frame; (d) SI-suffix style (`⌥9`, `⌥1k` for >999). Touches `scan_tree_widget._populate_node_row` (the `text=f"⌥{chain_len}"` line) and the existing `test_provenance_op_count` style assertions. User has confirmed `n > 9` is "easily seen for complex workflows" so this is not edge-case |
| ⏳ | 🟢 | **Threshold-band caching for responsive helper (technical debt)** | Phase 4n CS-26's `_apply_responsive_layout` unconditionally pack_forget+repacks every optional cell on every call (rather than tracking last-applied state) because Tk auto-unmap under overflow makes `winfo_ismapped()` an unsound "have" oracle. The fix is correct but does redundant work on every `<Configure>` event at the same width. Cache the last applied "threshold band" per row (e.g. one of `(none, swatch, swatch+leg, all)`) and short-circuit the reflow when the new width falls in the same band. Care needed: the cache must be invalidated on `_populate_node_row` (a row rebuild starts fresh). Cheap polish; defer until flicker is observed in real use |
| ⏳ | 🟢 | **Test convention: `_root.update()` over `update_idletasks()` for geometry** | Surfaced during Phase 4n CS-26 test work. `update_idletasks()` flushes idle handlers but does NOT trigger Tk's geometry pass on a withdrawn root; `winfo_ismapped()` lags reality until the next event cycle. Pre-CS-26 responsive tests got away with `update_idletasks` because the helper packed less aggressively; CS-26's unconditional reflow exposed the gap. Document the convention in `test_scan_tree_widget`'s module docstring (and the equivalent docstrings in any future widget tests that read mapped state): "after a layout-changing call on a withdrawn `_root`, use `_root.update()`, not `update_idletasks()`, before reading `winfo_ismapped`". One-paragraph doc edit; no code change |
| ✅ | 🔴 | **Right-sidebar canvas-width binding + responsive helper canvas-Configure rerun (USER-FLAGGED)** | USER-FLAGGED at start of Phase 4p. Resolved Phase 4p (CS-30): the helper now reads `_scroll_canvas.winfo_width()` rather than `row.winfo_width()` (with a `width: int \| None = None` kwarg for explicit overrides). The per-row `<Configure>` binding is removed (it raced with explicit calls and read the wrong width); replaced by a canvas `<Configure>` binding that walks every row in `_optional_row_widgets` on resize. Initial calibration of newly-built rows happens at the end of `_populate_node_row` via a single helper call. Inner `_rows_frame` width is intentionally NOT bound to canvas width (Tk's auto-unmap on overflow would silently drop overflow widgets). Touches `scan_tree_widget._build_chrome` + `_populate_node_row` + the helper signature, plus six new regression tests in `TestScanTreeWidgetCanvasDrivenLayout`. The pre-existing `test_each_row_collapses_independently` test was rewritten to use the explicit `width=` kwarg — under the new contract rows share a canvas, so the per-row independence invariant only survives when callers drive it directly. 540 tests, all green |
| ✅ | 🔴 | ~~**Suppress identical re-applies (param-equality gate on Apply) (USER-FLAGGED)**~~ ✅ Reverted in Phase 4ac (CS-54). USER-FLAGGED at start of Phase 4p. Resolved Phase 4p (CS-31): new graph method `ProjectGraph.find_provisional_op_with_params` + 5-apply-site short-circuit. The user re-flagged this as workflow-blocking at end of Phase 4v (friction #1) — re-applying a tweaked process was being silently blocked. Phase 4ac (CS-54) drops the helper + every short-circuit; identical re-applies now create fresh PROVISIONAL siblings. See the canonical "Drop CS-31 + introduce user-driven node groups" register row above. |
| ✅ | 🔴 | ~~**Inline expansion + per-variant gestures on sweep-group rows (CS-04 §6.3 follow-through) (USER-FLAGGED)**~~ ✅ Reverted in Phase 4ac (CS-54). USER-FLAGGED at start of Phase 4p. Resolved Phase 4q (CS-32): chevron `▸/▾` on a sweep-leader row toggled inline render of every PROVISIONAL sibling sharing one (parent, op_type). Auto-grouping was the second half of the user-flagged workflow problem — siblings disappeared behind a single leader row with the auto-collapsed `_compute_sweep_groups` rule. Phase 4ac (CS-54) drops the entire sweep-grouping machinery (`_compute_sweep_groups` / `_build_sweep_row` / `_toggle_sweep_group` / `_expanded_sweep_groups` / `_sweep_groups` / `_sweep_leaders`); siblings now render as standalone full-chrome rows. The replacement — user-driven `NodeType.NODE_GROUP` (Phase 4ad) — is the carry-forward part (c) of the canonical "Drop CS-31 + introduce user-driven node groups" register row above. |
| ✅ | 🔴 | **Truncate long node-name labels in ScanTreeWidget rows (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4p. Resolved Phase 4q (CS-33): module-level `_LABEL_MAX_CHARS = 32` cap + pure helper `_truncate_label(text, max_chars)` truncates with `…` suffix at exactly the cap; `_populate_node_row` paints the truncated text and attaches a `_Tooltip` (Toplevel, 600 ms hover) ONLY when truncation actually cut text. `_build_sweep_row` applies the same treatment to the parent label inside the leader text. `_begin_label_edit` reads the canonical full label from the graph rather than the painted (potentially truncated) widget text, so rename starts with the untruncated text. Five pure-helper tests in `TestTruncateLabel`, three Tooltip construction/binding tests in `TestTooltip`, three widget-side tests in `TestLabelTruncationInRow`. Pairs with the still-open Phase 4n "Long-provenance hist button display options" register entry — same root (cells whose natural width grows with content), same canvas-width invariant. Sibling Phase 4q friction #2 captures the cap-from-canvas-width-and-font-metrics follow-up |
| ✅ | 🔴 | **🔒 commit gesture on provisional ScanTreeWidget rows** | Resolved Phase 4q (CS-34). Every PROVISIONAL row carries a `tk.Button(text="🔒")` between → and ✕ that invokes `self._safely(self._graph.commit_node, nid)` — same path the right-click context menu's Commit entry uses. Committed rows OMIT the button entirely (the leftmost-cell 🔒 state indicator already signals committed state; double-glyph would be confusing). Right cluster reads `[⌥n] [⚙] [→] [🔒] [✕]` provisional, `[⌥n] [⚙] [→] [✕]` committed. NOT in the responsive-optional set: 🔒 is always-visible (commit twin of ✕). Three integration tests in `TestProvisionalRowCommitButton`. Together with the still-open "Commit / discard reachable from the left pane after Apply" register entry, this covers the right-sidebar half of the original USER-FLAG; the left-pane Accept-last button-pair remains 🟡 |
| ✅ | 🟢 | **Compute label-truncation cap from canvas width / font metrics (CS-33 follow-up)** | Phase 4q friction #2. **Resolved Phase 4w (CS-47):** new pure helper `_label_char_capacity(canvas_width_px, avg_char_px, overhead_px) → int` clamped to `[_LABEL_CHAR_FLOOR=8, _LABEL_CHAR_CEIL=64]` falls back to `_LABEL_MAX_CHARS=32` when canvas is unrealised or font metrics unavailable. Wired into `_populate_node_row` and `_build_sweep_row` via instance method `_current_label_cap` (which delegates to the helper using `_scroll_canvas.winfo_width()` and `tkfont.nametofont("TkDefaultFont").measure("ABCDEFGHIJabcdefghij") // 20`). `_apply_responsive_layout` re-truncates the painted label and rotates the always-attached label tooltip's text whenever the canvas resizes — widening the sash visibly grows the label, narrowing trims it. The pure `_truncate_label` helper stays unchanged (CS-33 invariant preserved). Tooltip rotation uses the empty-string sentinel that `Tooltip._show` already supports, so no create/destroy churn. 12 pure-module + 3 integration tests cover the dynamic-cap behaviour |
| ⏳ | 🟢 | **Promote `_Tooltip` to a shared utility module on first cross-module re-use** | Phase 4q friction #3. CS-33's `_Tooltip` is a small Toplevel-based hover tooltip co-located in `scan_tree_widget.py`. Other surfaces will eventually need similar tooltips (Plot Settings dialog parameter hints, StyleDialog "what does this control" hints, panel-status messages that only fit on hover). On first re-use, extract into `tooltip.py` (pure utility module, no scan-tree-specific imports) so the second consumer doesn't either re-implement or import a private name. Until then, the private name is fine — premature promotion would add an import surface without a second consumer |
| ✅ | 🟢 | **Indent expanded sub-frames inside sweep groups (visual nesting)** | Phase 4q friction #5. Resolved Phase 4r (CS-35): new module-level `_SWEEP_MEMBER_INDENT_PX = 16` constant; `_build_node_row` grew an `indent_px: int = 0` keyword that is threaded into `row.pack(padx=(2 + indent_px, 2), pady=1)`. The sweep-expansion branch in `_rebuild` calls `_build_node_row(member_node, indent_px=_SWEEP_MEMBER_INDENT_PX)`. Pack-arg pass-through chosen over a wrapper-frame to avoid a parallel `_member_frames` dict + collapse cleanup. CS-32's flip-and-rebuild contract preserved verbatim. The history sub-frame inside an expanded member row carries the parent row's indent (since `_render_history` packs into the row's children frame), so visual nesting is correct without separate indent threading there. 7 new tests (2 pure-module constant, 5 integration nesting) |
| ✅ | 🔴 | **Drop CS-31 "no duplicate apply" check + introduce user-driven node groups (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4v (step 5 elicitation). The CS-31 `find_provisional_op_with_params` short-circuit (Phase 4p) prevents the same op-with-same-params from running twice on the same parent — but in practice this prevents the user from re-running an op that they want to re-run, and the auto-collapsed sweep groups (CS-32) bundle related applies into a unit the user can't operate on. The user has flagged that today's behaviour makes work flows unusable: re-applying a process you tweaked once is blocked, and the auto-grouping hides the individual nodes. **Architecture (locked across Phase 4ac + 4af):** (a) **drop CS-31** entirely — every Apply produces a fresh OperationNode + child DataNode regardless of whether identical params were applied before. (b) **drop CS-32 auto-grouping** of provisional ops with identical (parent, op_type) signatures. (c) New `NodeType.NODE_GROUP` holds child node ids + a user-given label; renders as a row with a chevron that expands to show its members; group does not own arrays, has no scientific value of its own. (d) Pairs with the existing 🟡 "Multinode dataset import + combination" register entry above. **Phase 4ac (CS-54) shipped parts (a) + (b):** `find_provisional_op_with_params` removed from `graph.py`; the dedup short-circuit removed from all five apply sites; `_compute_sweep_groups` / `_build_sweep_row` / `_toggle_sweep_group` / `_expanded_sweep_groups` / `_sweep_groups` / `_sweep_leaders` / `_group_key_of` / `_discard_many` / `_datanode_parents` removed from `scan_tree_widget.py`; identical re-applies now create fresh standalone PROVISIONAL siblings. **Phase 4af (CS-57) ships part (c) — fully resolves the register entry:** new `NodeType.NODE_GROUP` variant in `nodes.py` (arrays = `{}`, metadata carries `member_ids: list[str]`, single-membership invariant, flat-only no-nesting invariant); new graph-layer entry points `ProjectGraph.create_group(member_ids, label=None) -> str` + `dissolve_group(group_id)` + `group_of(node_id) -> Optional[str]`; `discard_node` grew an auto-dissolve cascade that recursively discards a group when fewer than two active members remain (bounded at one level by flat-only). `ScanTreeWidget` gained a click-toggle selection model (`_selected_node_ids` set, `<ButtonRelease-1>` so a double-click rename nets zero toggle), a footer "Group selected" button (enabled iff ≥2 selected AND none already grouped AND none is itself a NODE_GROUP — predicate mirrors `create_group`'s validation), a group-row pipeline (`_build_group_row` with chevron ▾/▸ + "(N members)" badge + inline ✕ for ungroup), and a chevron-driven `_expanded_groups` set. Top-level rendering excludes grouped members; expanded groups render members below with `padx=(2 + _SWEEP_MEMBER_INDENT_PX, 2)` — **CS-35's dormant indent constant + `_build_node_row(indent_px=0)` kwarg are now LIVE** (Phase 4ac friction #5 closed). Right-click context menu branches: data rows get a new "Group selected (N)" entry enabled by the same predicate; group rows get a simplified Rename / Expand-or-Collapse / Ungroup menu via `_show_group_context_menu`. **Lock decisions taken (Phase 4af):** (i) **gesture style — context-menu + left-pane footer button** (both surfaces, user choice); (ii) **flat only, no nesting** (rejected at `create_group` time — relaxing later is additive); (iii) **Ungroup lives on context-menu + inline ✕** on the group row; (iv) **indent reuses `_SWEEP_MEMBER_INDENT_PX = 16`** (CS-35 lock survives, purpose realised). Additional Claude-side locks: group default label `"Group N"`, members keep their parent edges (group is view-layer, not structural reparenting), single-membership enforced, NODE_ADDED on create + NODE_DISCARDED on dissolve (no new event types), groups never participate in y-axis routing / redraw (renderer-skip invariant), groups always PROVISIONAL (no commit path), `project_io` round-trips via the existing DataNode schema (arrays={} → empty savez archive; member_ids in metadata is JSON-serialisable). 50 new tests across `test_nodes.py` (1), `test_graph.py` (27 in `TestNodeGroupOps`), `test_scan_tree_widget.py` (21 in `TestScanTreeWidgetNodeGroupsPhase4af`), `test_persistence_phase_a.py` (1 round-trip). Net suite count: 949 (up from 899). |
| ✅ | 🔴 | **Adjustable sidebar still not working — fix next, revisit every cell + minimum width (USER-FLAGGED bumped from 🟡 to 🔴 in Phase 4v)** | USER-FLAGGED at end of Phase 4u as 🟡 (Phase 4u friction #5); re-flagged at end of Phase 4v (bumped to 🔴). **Resolved Phase 4w (CS-47 + CS-48):** the auto-bump scope ships as CS-47 (`widest_label_pixel_width` measurement + `_calibrate_sidebar_width` one-shot via `after_idle`); the cell-vocabulary audit + minimum-width work ships as `_CELL_MIN_PX` (every cell documented in one dict) + `_SIDEBAR_MIN_WIDTH_PX = 240` (pinned floor used by both the responsive helper and the PanedWindow's `minsize`); the column-alignment scope ships as CS-48 (fixed-width `row_toggle` slot). The "minimum width" scope deliberately reused the existing 240 px floor (matching the smallest responsive threshold) rather than introducing a new per-cell sum, because changing the floor would break the existing TestResponsiveCollapse threshold tests. See the canonical resolved entry "Dynamic sidebar auto-width for long node labels" above for full deliverables list |
| ⏳ | 🟡 | **Trash can for discarded nodes — restore from a Trash pane (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4v (step 5 elicitation). Today `ProjectGraph.discard_node` removes the node from `self.nodes` entirely; if the user discards a provisional node they later want back, it's gone. The user has asked for a Trash gesture analogous to a desktop OS recycle bin. **Architecture proposal (lock pending):** (a) new `NodeState.DISCARDED` (joining `PROVISIONAL` / `COMMITTED`); (b) `discard_node` flips state to DISCARDED rather than removing from `self.nodes`; (c) the default sidebar filter hides DISCARDED rows; (d) a "Trash" pane / collapsible section / dialog lists discarded nodes with a Restore gesture that flips state back to PROVISIONAL (or COMMITTED if the node was committed before discard); (e) discarded nodes round-trip through the Phase A manifest (sidecar storage stays). Pairs with: the new sidecar-garbage-collection register entry below (DISCARDED nodes' sidecars stay until the trash is emptied) and Phase 4q friction #4's left-pane Accept/Discard register entry (Discard now preserves recoverability). **Lock decisions for the implementing session:** (i) is Trash a top-of-sidebar collapsible section, a separate pane, or a Toplevel dialog? (ii) does Empty Trash literally remove from `self.nodes` (current discard behaviour) or is even that retained? (iii) does Restore preserve the original ordering / parent edges, or just resurrect the node and let the user reattach edges? **Affected:** `nodes.py` (new NodeState variant), `graph.py` (discard_node implementation + a new restore_node), `scan_tree_widget` (filter + new pane), `uvvis_tab` (pane wiring), `project_io.py` (sidecar persistence — already handled by the array-hash identity, but needs to round-trip the new state) |
| ⏳ | 🟡 | **Project-specific plot defaults + import from another project (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4v (step 5 elicitation). Phase A persistence (CS-46) round-trips `plot_settings_dialog._USER_DEFAULTS` as a top-level `plot_defaults` key, but those defaults are app-global (mutated in place at load time). The user has asked for project-scoped plot defaults that ride with the workflow + an "Import plot settings from another project" gesture in the Plot Settings dialog. **Architecture proposal (lock pending):** three-layer defaults — factory (`_FACTORY_DEFAULTS`, immutable) → user (`~/.binah_config.json`, app-global) → project (manifest, scoped to the loaded `.ptmg`). Lookups walk the layers (project ?? user ?? factory). New "Import plot settings…" file dialog in PlotSettingsDialog reads another `.ptmg`'s `plot_defaults` block and merges into the current project's overrides. Pairs with the still-open Phase 4l friction #1 register entry (audit dialog button-row vocabulary) — the import gesture is a new dialog. **Lock decisions for the implementing session:** (i) does the project layer override every key, or only ones explicitly set? (ii) is the import a copy (snapshot) or a reference (live link to the source project's defaults)? (iii) does the StyleDialog's "Apply to All" reach into the project-defaults layer? **Affected:** `plot_settings_dialog.py` (three-layer lookup + import file dialog), `project_io.py` (no schema change — `plot_defaults` already exists; semantics shift), `binah.py` (load-time wiring of the project layer) |
| ⏳ | 🟡 | **Refactor uvvis_tab.py — extract host shell into separate files; cross-tab generalization (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4v (step 5 elicitation). Today `uvvis_tab.py` is ~2000 LOC mixing five concerns: (a) the left-pane chrome (CollapsibleSection wrappers, shared subject combobox, baseline-section inline panel), (b) the right-pane chrome (ScanTreeWidget host), (c) the matplotlib plot frame + redraw pipeline, (d) graph subscription + apply orchestration, (e) the LOAD path (file-open dialog → parser → DataNode creation). The five operation panels (`uvvis_baseline.py`, `uvvis_normalise.py`, `uvvis_smoothing.py`, `uvvis_peak_picking.py`, `uvvis_second_derivative.py`) are already separate files. **Architecture proposal (lock pending):** (a) extract the left-pane chrome into `processing_pane.py` (or `left_pane.py`) — the shared subject combobox + the CollapsibleSection wrappers + the panel registration mechanism become reusable across XAS / EXAFS / TDDFT tabs once those tabs adopt ProjectGraphs; (b) extract the right-pane chrome (ScanTreeWidget host wiring + `_restore_workflow_payload`) into `tab_shell.py`; (c) extract the matplotlib plot frame + redraw into `plot_pane.py`; (d) leave `uvvis_tab.py` as a thin orchestration class composing the three panes. The cross-tab generalization is a separate larger entry — the four tabs end up with a common `Tab` base class composing the same three pane classes. **Lock decisions for the implementing session:** (i) does the redraw pipeline stay inside the plot pane (lift the multi-axis routing CS-44 helpers along with it), or stay in `uvvis_tab.py` per the current Phase 4u Decision 7? (ii) which tab adopts the cross-tab generalization first — XANES (which has its own plot logic to reconcile) or a fresh "Compare" tab? (iii) is the panel registration mechanism a list of `(name, panel_class, factory)` tuples, a decorator, or hard-wired? Multi-phase task. Pairs with the future plot_widget abstraction lift register entry (CS-44 follow-up). Cross-refs the existing Phase 4t friction #3 / "Top-bar Open File / Reload buttons belong to TDDFT only" register entry — that one removes app-level chrome; this one extracts tab-level chrome |
| ⏳ | 🟡 | **Plot data markers / points (instead of lines) with per-style marker config (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4v (step 5 elicitation). Today every visible spectrum is rendered as a continuous line (`ax.plot(..., linestyle=...)` in `uvvis_tab._redraw`); discrete points are not an option. The user has asked for a markers-only render mode + per-style marker configuration (shape + size). **Architecture proposal (lock pending):** new style keys `style["plot_kind"]: "line" \| "markers" \| "both"` (default `"line"` to preserve existing behaviour), `style["marker"]: str` (matplotlib marker spec — `"o"`, `"s"`, `"^"`, etc.), `style["marker_size"]: float`. The redraw branch in `uvvis_tab._redraw` reads `plot_kind` and switches between `ax.plot(..., linestyle="None", marker=..., markersize=...)` and the existing line path; `"both"` uses the existing line path with a non-`"None"` marker. **StyleDialog universal section:** new Combobox (line / markers / both), new marker-shape Combobox (matplotlib's standard set), new size Spinbox. **Cross-refs:** `node_styles.default_spectrum_style` grows the three new keys with sensible defaults. **Affected:** `node_styles.py` (defaults), `style_dialog.py` (universal section), `uvvis_tab.py` (`_redraw` switch), tests for the new style keys' round-trip and the renderer's branching. Pairs with: the future PEAK_LIST renderer (peaks are inherently markers — CS-19 already uses scatter); this entry generalises the markers path so PEAK_LIST and a markers-only spectrum share the same code |
| ✅ | 🟡 | **Configurable plot grid colour (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4ac (step 5 elicitation). Resolved Phase 4ae (CS-56): new `"grid_color"` key in `plot_settings_dialog._FACTORY_DEFAULTS` (factory default `"#b0b0b0"` — matplotlib's standard light grey, preserves the existing visual). New `_make_colour_swatch` row under Appearance (row=1; existing rows shift one place to accommodate). Renderer (`uvvis_tab._redraw`'s `ax.grid(...)` call) reads the value through `cfg.get("grid_color", "#b0b0b0")`. **Lock decisions taken:** (i) **app-global** in `_USER_DEFAULTS` (consistent with every other Plot Settings key today; per-tab is the future "project-specific plot defaults" register entry above); (ii) **one colour** covering both major + minor grids (matplotlib's `ax.grid(color=...)` already applies to both — two pickers is gold-plating); (iii) **stay plot-wide** (no per-style override; the StyleDialog re-org register entry handles the per-style question if it ever comes up). Round-trips through `project_io.plot_defaults` already (CS-46) — no schema change. 5 new pure-module tests in `TestAppearanceSectionPhase4ae` (factory dict shape + dialog widget creation + write-through + Factory Reset) + 3 integration tests in `TestUVVisTabAppearancePhase4ae` (default + custom colour reach `ax.grid`, off-then-on round-trip) |
| ✅ | 🟡 | **Default to inward-facing axis ticks (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4ac (step 5 elicitation). Resolved Phase 4ae (CS-56): `plot_settings_dialog._FACTORY_DEFAULTS["tick_direction"]` flipped `"out"` → `"in"`. Existing dialog fallback in `_build_section_appearance` and renderer fallback in `uvvis_tab._redraw` (`cfg.get("tick_direction", "out")`) also flipped to `"in"` for consistency. **Lock decisions taken:** (i) **factory-default-only flip** — no migration; existing `_USER_DEFAULTS["tick_direction"] = "out"` entries are left alone (explicit user choice wins). New users + users with no explicit setting get `"in"`. Cheapest, safest path; no migration code to write or test. (ii) **defer** — `_FACTORY_DEFAULTS` is module-level; XANES / EXAFS / TDDFT inherit the new default when they wire Plot Settings (UV/Vis is the only consumer today). (iii) **no-op** — `plot_widget._tick_direction` already defaults to `"in"` at [plot_widget.py:250](plot_widget.py#L250); no flip needed there. 1 new pure-module test in `TestAppearanceSectionPhase4ae` pinning the factory default + 1 integration test in `TestUVVisTabAppearancePhase4ae` confirming a fresh tab's `plot_config` inherits `"in"` |
| ⏳ | 🟡 | **Re-run all changed ops at load (CS-45 follow-up)** | Phase 4v deferral. CS-45's mismatch dialog ships with two buttons (Keep cached / Show details); the third "Re-run all changed" action from the Phase 4v Q2 lock is wired to a placeholder. To implement it properly: walk the graph in topological order; for each OperationNode whose `metadata["implementation_hash"]` differs from the current `compute_implementation_hash(op.type)`, look up the matching `compute_*` helper (dispatching on `op.type` + `op.params["mode"]`), call it with the input arrays + params, replace the output DataNode's arrays in place, re-stamp the implementation hash. ~150 LOC of new replay logic + new test class `TestImplementationDriftReplay`. **Trigger:** when ≥3 ops drift across a release in real practice OR when `.ptmg` files start moving between machines that may run different builds. Until then, manual re-apply (select parent → click Apply) suffices |
| ⏳ | 🟡 | **Original instrument file persistence (Phase A follow-up)** | Phase 4v deferral. The Phase A manifest+sidecar shipped (CS-46) round-trips DataNode arrays via `sidecars/<arrays_hash>.h5` but does NOT yet persist the *original instrument file* the LOAD operation parsed. The persistence-umbrella architecture lock specifies "the original instrument file as a first-class sidecar"; today we only round-trip the *parsed* (wavelength_nm, absorbance) arrays. Implementation: at save time, for each LOAD OperationNode, locate `metadata["source_file"]` on its output UVVIS DataNode (or carry the path on the LOAD op's params), hash the file bytes, copy to `sidecars/raw_<file_hash>.<ext>`, record `raw_file_hash` + `raw_file_format` on the LOAD op's metadata. At load time, the host can offer a "Re-import from original" gesture that re-runs the parser against the cached sidecar. Pairs with the OLIS reader register entry (binary `.ols` files MUST round-trip via this path — re-parsing without the original is impossible). Cross-refs the Phase A `hash_file` helper retained in `project_io.py` exactly for this case |
| ⏳ | 🟢 | **`.ptmg` zip-archive form (CS-46 follow-up)** | Phase 4v deferral. Phase A ships directory-only (`myproject.ptmg/`); the persistence-umbrella architecture lock also calls for a single-archive form (zip-with-extension). One small follow-up phase: wrap `shutil.make_archive` / `unpack_archive` around save/load so the user can choose either form in the file dialog. Open-as-archive: detect that the picked path is a regular file, unpack to a tmp dir, hand over to the existing directory loader, register a save-back hook that re-archives on next Save. Save-as-archive: write to tmp dir, archive, replace destination. Smallish; defer until a user reports wanting it (likely after the first time someone tries to email a project) |
| ⏳ | 🟢 | **Sidecar garbage collection across saves (CS-46 follow-up)** | Phase 4v deferral. Re-saving a project accumulates stale sidecars: when a DataNode's arrays change between saves, the old `<old_hash>.h5` stays in `sidecars/` even after the manifest no longer references it. One-line fix in `save_project`: walk the manifest first (build the live `set(arrays_hash)`), then prune any `sidecars/<hash>.h5` not in that set. Care needed: only prune within the project's own sidecars directory; never touch user files. ~20 LOC + one test. Defer until disk-bloat is observed (typical UV/Vis sidecars are ~3-5 KB; a project with 100 stale entries ≈ 500 KB — not yet alarming) |
| ⏳ | 🟡 | **`_restore_workflow_payload` only on UVVisTab; XAS / EXAFS / TDDFT need equivalents** | Phase 4v carry-forward. CS-46's load gesture relies on each tab having a `_restore_workflow_payload(TabPayload)` method that swaps graph contents in place. Today only `UVVisTab` ships it because only UV/Vis owns a real `ProjectGraph` after the redesign. When XAS / EXAFS / TDDFT migrate to the node model (Phase 5+), each gains its own ProjectGraph and needs a parallel restore method. The cross-tab refactor register entry above is the natural home: a base `Tab` class with a `restore_payload` virtual method per pane. **Trigger:** the first non-UV/Vis tab migration |
| ⏳ | 🟢 | **Test efficiency + per-phase metrics tracking (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4v (step 5 elicitation). The user has flagged that test wall-clock is competing with development wall-clock — a Phase 4u or 4v session spends roughly equal time on test writes / runs / fixes as on production code. Two goals: (a) reduce the wall-clock cost without sacrificing coverage; (b) start tracking per-phase metrics so we can see the trend. **Levers for (a):** (i) reuse a single Tk root across test classes (today many integration tests construct + tear down a Tk root, which is ~1-2s each); (ii) consolidate granular pure-module tests where assertions cluster; (iii) skip the slow integration paths in a "fast" CI mode (full suite stays the gold-standard pre-merge gate). **Shape for (b):** every bookkeeping commit ends with a footer block: `tests added: +N`, `LOC delta: +N -M`, `commit count: 5`, `wall-clock estimate: 4h`. Aggregate over five phases ⇒ visible trend. Touches: bookkeeping commit template + the README's session-structure section. **Lock decisions for the implementing session:** (i) is the metrics block in BACKLOG.md per-phase or in a separate `METRICS.md`? (ii) does it auto-generate from `git log` or is it hand-written? (iii) which Tk-fixture refactor lands first (single-root sharing is the biggest win) |
| ✅ | 🔴 | **Inter-panel parent-type acceptance gaps — baseline can't run on smoothed; smoothing can't run on second-derivative (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4w (step 5 elicitation). **Resolved Phase 4x (CS-49):** widened `_BASELINE_ACCEPTED_PARENT_TYPES` on UVVisTab from `(UVVIS, BASELINE)` to `(UVVIS, BASELINE, SMOOTHED)`; widened `SmoothingPanel.ACCEPTED_PARENT_TYPES` from `(UVVIS, BASELINE, NORMALISED, SMOOTHED)` to add `SECOND_DERIVATIVE`. `_refresh_shared_subjects` extended to walk both `_spectrum_nodes()` and `_second_derivative_nodes()` so the derivative rows appear in the shared subject combobox; `_spectrum_nodes` itself untouched (the renderer uses the two helpers separately for axis-role routing). **Decision lock taken:** (i) explicit type-list gate kept (vs "any DataNode with arrays") — preserves the per-panel deliberate-exclusion comments; (ii) y-axis routing of cross-typed outputs deferred to existing CS-44 by-NodeType routing — smoothed-of-derivative output carries `NodeType.SMOOTHED` → routes to "primary"; the inherent misroute (smoothed d²A on the absorbance axis) is the open Phase 4u friction #10 / per-style `y_axis` override hook (carry-forward T), out of scope for 4x; (iii) audit pass result — `NormalisationPanel` / `PeakPickingPanel` / `SecondDerivativePanel` tuples intentionally NOT widened (existing exclusions are deliberate per panel-side comments; user has not flagged); each unchanged tuple is now pinned by an audit-stability `test_accepted_parent_types_constant` that traps a future widening. 8 new tests across `test_uvvis_smoothing.py` (3) + `test_uvvis_tab.py` (5 in new `TestUVVisTabPhase4xCrossTypeAcceptance`); 3 prior contract tests rewritten to invert the old "SECOND_DERIVATIVE not in combobox" assertions. 746 tests, all green |
| ⏳ | 🟡 | **Configurable secondary-plot pane layout — dock above/below main plot at adjustable fraction (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4w (step 5 elicitation). The CS-44 multi-axis routing puts SECOND_DERIVATIVE on a `twinx()` of the main axes — same canvas, same x-axis, separate y-axis. The user has flagged that for the derivative plot specifically (and any future "secondary" plot of similar character) it would help to optionally render it in a dedicated pane below or above the main plot, at an adjustable height fraction (1/3 of the main plot was suggested as a default). This is a layout-mode toggle, not a routing change. **Architecture proposal (lock pending):** new `_secondary_axis_layout: tk.StringVar` with values `"overlay" | "below" | "above"` and `_secondary_axis_height_frac: tk.DoubleVar` (default 0.33). When `"overlay"` (default — current behaviour) the existing `twinx()` path runs unchanged. When `"below"` / `"above"` the matplotlib Figure swaps to a `gridspec.GridSpec(2, 1, height_ratios=…)` shape with the secondary axes hosted in a separate Axes; the legend merge stays a single legend on the main plot for visual continuity. The two new vars surface in Plot Settings under a new "Secondary axis layout" section. **Lock decisions for the implementing session:** (i) is the layout chosen per-NodeType (so SECOND_DERIVATIVE gets its own dock while a hypothetical fourth-axis-NodeType could overlay) or per-AxisRole (all "secondary" content goes to the same dock)? (ii) does the dock-mode persist in the workflow's `plot_config` block (it's just two new keys) or is it session-only? (iii) does the dock mode survive a `_draw_empty` cycle? **Affected:** `uvvis_tab._redraw` (figure construction switches between `subplots(1,1)` and `subplots(2,1, gridspec_kw={"height_ratios": …})`), `plot_settings_dialog` (new section), `project_io` (two new manifest keys if persisted), tests for each layout mode. Cross-refs CS-44 (the routing system this layout option sits on top of) and the future plot_widget abstraction lift (the layout state is a plot-pane concern that should ride along with the future lift) |
| ⏳ | 🟡 | **UI lexicon / glossary doc — workflow vs project, sidebar vs sash, etc. (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4w (step 5 elicitation). Phase 4v's persistence work (CS-46) shipped the `.ptmg` file format and changed the menu entries from "Save Project" to "Save Workflow" — but the docs (BACKLOG.md, COMPONENTS.md, the in-app messages) still mix "project" and "workflow" interchangeably, and parallel ambiguity exists for several other UI elements (sidebar/sash/pane; row/cell/cluster; gear/style-dialog). The user has asked for a single canonical lexicon document so terminology stays consistent across Claude sessions and human conversations. **Architecture proposal:** new `LEXICON.md` (or `UI_GLOSSARY.md`) at the repo root, structured as a flat list of canonical terms with definitions. Suggested seed entries: **workflow** (a single `.ptmg` save unit covering all open tabs' graphs + plot defaults; what we used to call "project" pre-CS-46), **project** (deprecated synonym for workflow — kept in the codebase only on internal helper names where renaming would create churn for no gain), **sidebar** (the right-pane host for ScanTreeWidget, including the "Loaded Spectra" header strip), **sash** (the PanedWindow drag handle between two panes), **pane** (a top-level layout region inside a tab — left / centre / right), **row** (one ScanTreeWidget entry corresponding to one DataNode), **cell** (one widget within a row — state, swatch, vis_cb, …; see `_CELL_MIN_PX`), **always-visible cluster** (the cells that survive the responsive collapse — state, vis_cb, row_toggle, label, hist, gear, compare, x), **optional cluster** (the cells that collapse — swatch, leg, ls_canvas), **gear** (the ⚙ button that opens the unified style dialog), **scan-tree** (synonym for sidebar's body widget, ScanTreeWidget), **subject** (the parent DataNode the shared subject combobox routes operations against). **Lock decisions for the implementing session:** (i) where does it live — repo root (alongside BACKLOG / COMPONENTS) or `docs/`? (ii) is it a flat list or hierarchical (categorised by area)? (iii) do we add a CI check that rejects new mentions of deprecated synonyms? Cross-refs every doc touched by Phase 4v's "Save Workflow" rename — those mentions should be audited for "project" leakage at the same time |
| ⏳ | 🟢 | **Cross-tab sash calibration — extract `_calibrate_sidebar_width` to shared host (CS-47 follow-up)** | Surfaced Phase 4w. CS-47's auto-bump only fires for `UVVisTab` because that's where it was wired; XAS / EXAFS / the future Compare / Simulate tabs each construct their own PanedWindow + ScanTreeWidget combination and would need parallel calibration. The clean path is to lift `_calibrate_sidebar_width` (plus `_SIDEBAR_MAX_CALIBRATED_PX`, plus the cached `_body_paned` / `_sidebar_pane` / `_sidebar_calibrated` triple) into a shared `tab_shell.py` mixin. Pairs perfectly with the existing 🟡 "Refactor uvvis_tab.py — extract host shell" register entry — that refactor's right-pane chrome extraction is the exact home for this method. Defer until the refactor lands |
| ⏳ | 🟢 | **Re-calibrate sash on first NODE_ADDED after construction (CS-47 follow-up, USER-CONFIRMED)** | Surfaced Phase 4w + user-confirmed. CS-47's `_calibrate_sidebar_width` fires once on `after_idle` after the tab is built, but at that point the graph is empty — `widest_label_pixel_width()` returns 0 and the sash falls through to `_SIDEBAR_MIN_WIDTH_PX = 240`. After the user loads a project (or imports files), longer labels appear but the sash isn't re-bumped (the `_sidebar_calibrated` flag has flipped True). User-acceptable trade-off — predictability beats opportunistic re-bumping for typical workflows — but a simple follow-up: subscribe to `GraphEvent.NODE_ADDED` and clear `_sidebar_calibrated` when the first DataNode appears (one-shot refresh on first content). **Lock decision needed:** does the re-bump fire for every load or only when the *current* widest label exceeds the previously-calibrated target? Defer until the missing re-bump is observed in real use |
| ✅ | 🟢 | ~~**Measure actual row overhead instead of static `_label_overhead_px` estimate (CS-47 follow-up)**~~ ✅ Resolved in Phase 4z (CS-51). The width-aware `_label_overhead_px(width=…)` path now sums `_CELL_MIN_PX[c]` for the always-visible cells PLUS the optional cells revealed at `width` per `_RESPONSIVE_THRESHOLDS_PX`, eliminating the static-estimate drift for the optional-cell axis (the dominant source of error). The commit-cell (🔒, provisional only) drift remains as ≤ 22 px noise, but per-cell-vocabulary truth replaces the post-pack `winfo_reqwidth()` measurement that this entry originally proposed — same goal, simpler implementation, no Tk geometry coupling. Spirit honoured. |
| ✅ | 🟡 | ~~**Loaded Spectra responsive layout drops the ✕ when the swatch reappears at intermediate widths (USER-FLAGGED)**~~ ✅ Resolved in Phase 4z (CS-51). Architecture (a) landed: `_label_overhead_px(width=…)` is now width-aware and sums the optional cells revealed at the current canvas width per CS-26's `_RESPONSIVE_THRESHOLDS_PX`. `_current_label_cap` forwards the canvas width into it, so the dynamic label cap shrinks the moment the swatch reappears at 240 px. CS-26 thresholds + `_label_char_capacity` signature unchanged (decision (iii) — no threshold-value relaxation). Cap recompute lifecycle unchanged (decision (ii) — every `_apply_responsive_layout` call). Calibration site unchanged (no-args path is byte-equivalent to Phase 4w). Pinned by `TestComputeLabelOverheadPx` / `TestVisibleOptionalCellsForWidth` / `TestLabelOverheadPxWidthAware` (19 pure tests) + `TestDynamicLabelCapWiringPhase4z` (5 integration tests). |
| ⏳ | 🟡 | **StyleDialog must surface ALL node-table parameters (incl. label rename) + tighten organisation for scale (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4x (step 5 elicitation). Today the per-node StyleDialog (gear icon) covers the universal style schema (`color`, `linestyle`, `linewidth`, `alpha`, `visible`, `in_legend`, `fill`, `fill_alpha`) plus per-NodeType extensions (CS-05 + CS-36 `show_baseline_curve`). The user has flagged that as more parameters land (label rename gesture, plot_kind from the markers register entry, `y_axis` from carry-forward T, etc.), the dialog will become unwieldy without a re-organisation pass. **Architecture proposal (lock pending):** restructure the dialog around grouped sections — Appearance (color / swatch / linestyle / linewidth / alpha), Legend (in_legend, label-rename Entry), Fill (fill / fill_alpha), Per-type (show_baseline_curve, plot_kind, y_axis, …); each group is a `tk.LabelFrame` so the visual grouping is obvious. **First concrete add:** label-rename Entry — today the only path to rename a node is to double-click the row label in the sidebar (CS-33 `_begin_label_edit`); having it inside the StyleDialog mirrors how the user thinks about "node properties" and avoids competing for the gesture's attention. Cross-refs: CS-33 (label-edit machinery), CS-44 follow-up T (per-style `y_axis` row), the markers register entry above (plot_kind / marker / marker_size). **Lock decisions:** (i) does the dialog get a tabbed shape (Appearance / Provenance / Per-type) — pairs with the next register entry below — or stay single-pane with LabelFrame groupings? (ii) does the label-rename Entry surface a validation error inline (e.g. duplicate-label warning) or rely on the existing CS-33 rules? (iii) which existing widgets lift into per-type groupings vs stay universal? **Affected:** `style_dialog.py` (re-layout + new label-rename Entry), tests for the new section grouping + label-rename round-trip. Pairs with C and D below (same window). **Phase 4aa partial (CS-52):** the **first concrete add** (label-rename Entry) landed in the universal section at the top of the grid — `_build_label_row` builds a `tk.Entry` bound to a `StringVar` whose `trace_add('write')` callback commits each keystroke through the new `_write_label_partial` helper, which routes via `graph.set_label` (label is a top-level DataNode slot, not a style key). Lock decisions taken for the partial: (i) **deferred** — single-pane with the new "Label:" row at the top of the existing universal grid; the LabelFrame re-org + tabbed-shape question stays open and pairs with C and D below in a future combined intent; (ii) **no inline validation** — match CS-33's sidebar gesture, accept any string; (iii) **no widget lifts** — all existing universal rows preserve their relative order (the lock-relaxation reading of "rows + their order stay verbatim"). Companion plumbing: `_snapshot_label` mirrors the existing style snapshot; `_do_cancel` restores both; `_on_graph_event` handles `NODE_LABEL_CHANGED` for sibling-rename refresh + dialog-title update. 10 new integration tests (`TestStyleDialogLabelRename`). **Carry-forward:** the LabelFrame groupings + tabs question (lock decision (i) above) + the rest of the parameter-coverage list (plot_kind from the markers register entry; future per-NodeType rows). **Phase 4ab partial (CS-53):** lock decision (i) **closed — tabbed shape**. The dialog body is now a `ttk.Notebook` with Tab 1 "Style" hosting today's universal + conditional sections verbatim (rows + relative ordering preserved per the CS-52 lock relaxation; only the parent widget changed) and Tab 2 "Provenance" (closes friction #3 below — see the ✅ next entry). Bottom Apply / ∀ / Save / Cancel row stays outside the Notebook so it's visible regardless of which tab is active. The LabelFrame groupings half of the original entry stays ⏳ — the universal rows could grow Identity / Appearance / Legend / Fill / Per-type LabelFrames inside Tab 1 once more parameters land (plot_kind from the markers entry, future per-NodeType rows). Lock decision (ii) and (iii) of the original entry remain as-is (no inline validation; no widget lifts). **Carry-forward narrowed to:** the LabelFrame groupings pass + the rest of the parameter-coverage list. |
| ✅ | 🟡 | ~~**Per-node parameter window: add a Provenance tab (USER-FLAGGED)**~~ ✅ Resolved in Phase 4ab (CS-53). The dialog body is now a `ttk.Notebook`; Tab 2 "Provenance" walks `graph.provenance_chain(self._node_id)` and renders one block per ancestor (header: bold label · type · state badge; body for OperationNodes: pretty-printed sorted params, engine + version, 12-char-prefix truncated implementation hash with the `unregistered:` sentinel preserved through truncation). DISCARDED ancestors render unfiltered with dimmed grey foreground (`#888888`) per Phase 4ab Decision (iv) — the tab is a history view; filtering DISCARDED would defeat the point and pre-empt the "Add to graph" gesture (next entry below). Provenance content is eager-built at `__init__` (Decision (ii)); single scrolling column hosted in a `tk.Canvas` + `ttk.Scrollbar` pair (Decision (iii)). Read-only this phase — bottom button row scopes to the Style tab only. Graph-event refresh fires on `NODE_LABEL_CHANGED / NODE_DISCARDED / NODE_COMMITTED / NODE_ADDED / EDGE_ADDED` (`_PROVENANCE_REFRESHING_EVENTS` frozenset), gated by the existing `_suspend_writes` guard so the dialog's own keystroke-driven label rename does NOT rebuild Provenance per keystroke (perf trade-off; bottom-of-chain block briefly stale during typing). 24 new integration tests (`TestStyleDialogPhase4abNotebook` + `TestStyleDialogPhase4abProvenanceTab`) + 22 pure-helper tests (`TestStyleDialogPhase4abHelpers`). Reused `graph.provenance_chain` rather than introducing the originally proposed `ProjectGraph.ancestors_of` — same return shape, no `graph.py` change. Pairs with the next entry below (the "Add to graph" gesture is now unblocked since the Provenance tab is the surface it lives on). | USER-FLAGGED at end of Phase 4x (step 5 elicitation). The right-sidebar's per-row history dropdown (the `▿` chevron next to the label, opens an ad-hoc list of "Op A → Op B → Op C") is intentionally compact — but the user has asked for a more detailed view that lives inside the gear-icon dialog as a second tab. The new tab would show: ancestor walk back to the RAW_FILE / multi-input source, full op params for each step (params dict pretty-printed), timestamps, engine + engine_version, implementation hash (CS-45), status, log excerpts (when populated). **Architecture proposal (lock pending):** convert the StyleDialog to a `ttk.Notebook` shape — Tab 1 "Style" (today's content, possibly re-organised per the previous register entry); Tab 2 "Provenance" (the new view). Reuses the same Toplevel + button row (Apply · ∀ Apply to All · Save · Cancel). The provenance tab is read-only this phase; the "add historical node" gesture lands as the separate register entry below (D). **Lock decisions:** (i) is the provenance tab populated lazily (on-tab-switch) or eagerly (at dialog construction)? (ii) does it scroll vertically as a single column, or render as a tree with expandable nodes? (iii) does it show DISCARDED ancestors (history-style) or filter them? **Affected:** `style_dialog.py` (Notebook restructure), graph-walk helper for the ancestor list (likely a new `ProjectGraph.ancestors_of(node_id)` method), tests for the tab construction + the ancestor walk. Pairs with B above (same dialog) and D below (same tab — D adds a gesture, this entry adds the read-only view) |
| ⏳ | 🟡 | **"Add to graph" gesture from a node's Provenance tab (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4x (step 5 elicitation). Once C lands (read-only Provenance tab), the user has asked for an "Add to graph" gesture per ancestor — clicking it materialises the historical ancestor as a new live node in the same graph without re-loading from disk. Concrete use case: the user has a SMOOTHED node loaded; they realise they want to compare the smoothed result against the underlying RAW_FILE / UVVIS parent; today the only path is to either (a) un-discard the parent (if it was discarded) or (b) re-load the source file via the LOAD path (which creates a fresh UVVIS DataNode with a different id, breaks the existing graph linkage to the SMOOTHED descendant). The new gesture would walk the ancestor chain, find the requested historical node, flip its `active` flag back to True (if currently inactive) OR clone it as a new live node parented on the same source. **Architecture (lock pending):** (a) does the gesture flip the existing node's `active` flag (cheap; preserves graph identity; couples to the existing CS-22 `_spectrum_nodes` filter), OR clone the node as a new id (preserves the historical node's state but creates a graph-edge fork)? (b) what's the gesture — button per provenance row, right-click, drag-and-drop into the sidebar? (c) does it emit a NODE_ADDED event (clone path) or NODE_STYLE_CHANGED + a re-render trigger (active-flip path)? **Affected:** `style_dialog.py` (the new gesture in the Provenance tab), `graph.py` (a new `restore_ancestor` or similar helper, depending on which architecture lands), `uvvis_tab._refresh_shared_subjects` (re-runs after the gesture so the resurrected node appears in the combobox), tests for both architectures. Pairs with C above (the tab the gesture lives on) AND with the existing 🟡 Trash can register entry (Trash + this gesture overlap conceptually — both surface "previously hidden" nodes). **Phase 4ab unblocks:** the Provenance tab landed (CS-53; entry above marked ✅), so this register entry is now actionable. The tab's per-ancestor block already carries the structural slot (header + body Frame) where a per-row "Add to graph" button would naturally fit — bottom-right of each block, parented to the same Frame the body Label uses. Decision (a) (active-flip vs clone) and Decision (c) (which graph event to emit) still need locking when the implementing session opens. |
| ⏳ | 🟢 | **Visual cue for derivative entries in the shared subject combobox (CS-49 follow-up)** | Surfaced Phase 4x (Claude). Now that `SECOND_DERIVATIVE` rows mix into the shared combobox alongside the four spectrum-shaped types (`_refresh_shared_subjects` widening), the user has no per-row glyph or grouping divider to tell at a glance "this is a derivative" vs "this is an absorbance-domain spectrum". Cheap polish: prefix derivative entries with a `d² ` glyph in the combobox display key (or insert a `─── d²A/dλ² ───` separator entry between the spectrum block and the derivative block). The latter is more disruptive (changes the value-list semantics — the separator can't be selected); the former is one-line in `_refresh_shared_subjects`. Defer until the user reports actual confusion picking among mixed entries; the audit-stability test `test_shared_combobox_orders_spectrum_then_derivative` already pins the spectrum-first ordering so visual scanning is at least left-to-right consistent |
| ⏳ | 🟡 | **Keyboard shortcuts — whole-interface evaluation pass (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4af (step 5 elicitation). User noted while reviewing Phase 4af friction list: "We'll need to evaluate keyboard shortcuts for the whole interface at some point. Not sure if it's better to do that sooner or later. Either way, let's put that into the list." Today the app exposes essentially no keyboard accelerators — gestures are mouse-driven (right-click context menus, footer buttons, dialog Apply/Cancel via mouse). Power-user workflows would benefit from a coherent shortcut vocabulary, but the design needs to be planned holistically rather than gesture-by-gesture so collisions don't compound. **Scope is a design pass before any implementation:** (a) inventory every active gesture (every ScanTreeWidget row gesture, every Plot Settings dialog action, every StyleDialog action, every tab-switch / file-open / save-workflow, every panel Apply, every Combine/Ungroup); (b) propose a shortcut table grouped by surface (App-global vs tab-scoped vs dialog-modal); (c) review for collisions with Tk's built-in bindings (Ctrl+C copy, Ctrl+W close window, F-keys); (d) review for platform consistency (Cmd vs Ctrl — currently Windows-only, but a XANES/EXAFS Mac contributor is plausible). Concrete first candidates the user-facing experience would benefit from: Ctrl+G "Group selected", Ctrl+Shift+G "Ungroup", Ctrl+S "Save workflow" (already present?), Ctrl+O "Open workflow", Delete "Discard selected" (with confirmation if any are COMMITTED), F2 "Rename" (matches the Windows convention CS-33's double-click started from), Enter "Apply" in the active panel. **Lock decisions for the implementing session:** (i) does the table live in `KEYBINDINGS.md` (separate doc, audit-friendly) or in `COMPONENTS.md` as a CS section, or both? (ii) is the implementation a single `key_bindings.py` module that registers all `bind_all` / per-tab `bind` calls at construction, or per-component bindings co-located with the gesture? (iii) does the app surface a "Keyboard shortcuts…" Help menu entry that opens a Toplevel with the table? Cross-refs every prior friction item that ended "would benefit from a keyboard shortcut" deferral (none today — the user has not previously surfaced this, which is why it's a fresh register entry). Multi-phase task; the design pass + a first batch of 3–5 shortcuts is a reasonable first phase. |
| ✅ | 🟡 | ~~**"Add to existing group" gesture — extend an existing NODE_GROUP without dissolve-and-recreate (USER-FLAGGED)**~~ ✅ Resolved in Phase 4ag (CS-58). USER-FLAGGED at end of Phase 4af (step 5 elicitation; "Definitely want that"). Phase 4af shipped only create + dissolve, so once a group existed the only way to add members was dissolve + recreate (losing any user-edited label). **Phase 4ag (CS-58) ships the v2 extend path + a symmetric remove path:** two new graph-layer methods (`ProjectGraph.extend_group(group_id, member_ids)` + `remove_from_group(node_id)`) with validation invariants mirroring CS-57's `create_group`; one new event type (`NODE_GROUP_MEMBERS_CHANGED` payload `{"group_id", "added", "removed"}`) routed to the scan tree's structural-rebuild branch; three new ScanTreeWidget surfaces: footer button now switches its text + click-target on selection (`"Group selected (N)"` in group mode, `"Add to <group label>"` in extend mode, baseline `"Group selected"` disabled otherwise — also closes Phase 4af friction #6); group-row context menu grows a fourth entry `"Add selected to this group (N)"`; data-row context menu grows two sibling entries `"Add selected to <group label> (N)"` + per-row `"Remove from group"`. **Lock decisions taken (Phase 4ag):** (i) **both surfaces** — context menu AND footer button (matches CS-57's two-surface symmetry); (ii) **append** (preserve caller order); (iii) **new event type `NODE_GROUP_MEMBERS_CHANGED`** — rejected NODE_LABEL_CHANGED because the scan tree routes label-changed to targeted row refresh while member changes are structural (rows move between top-level and group-nested rendering); (iv) **yes — symmetric `remove_from_group` ships in the same phase**, reusing CS-57's auto-dissolve threshold (<2 active members) via `discard_node`. **Lock relaxations:** CS-57's `text="Group selected"` initial-label lock is broadened — the button now mutates its text per selection classification (Phase 4af friction #6 polish trigger). The CS-57 narrow "any group in selection → disabled" semantics is also deliberately relaxed: a `1 group + ≥1 ungrouped` selection now routes to the extend gesture (test pinning the old semantics was updated in the same commit). 53 new tests across `test_graph.py` (27 in `TestNodeGroupExtendRemoveOps`), `test_scan_tree_widget.py` (24 in `TestScanTreeWidgetNodeGroupsPhase4ag`), `test_persistence_phase_a.py` (2 round-trip — extend+remove sequence, auto-dissolve cascade). Net suite count: 1002 (up from 949). |
| ✅ | 🟡 | **Grid renders in front of data lines, not behind (USER-FLAGGED bug)** | USER-FLAGGED at end of Phase 4ag (step 5 elicitation). `uvvis_tab._redraw` called `ax.grid(True, linestyle=":", alpha=0.4, color=cfg.get("grid_color", "#b0b0b0"))` without specifying `zorder`; matplotlib's default zorder for the grid is 2.5 while line plots use 2.0, so gridlines painted ON TOP of the data. **Resolved Phase 4ah (commit 1, A.1):** one keyword arg added — `zorder=0` on the `ax.grid(...)` call. Other tabs migrate when they adopt the renderer architecture. **Lock decisions taken:** (i) hard-code `zorder=0`, no Plot Settings key — render-correctness fix, not a user preference; no plausible user wants the grid in front of data. (ii) UV/Vis only this phase — Compare, XANES, EXAFS, TDDFT migrate on renderer adoption. 2 new tests in `TestUVVisTabGridZOrderPhase4ah`: relational invariant (every gridline zorder < every data-line zorder) and the literal value pin (`get_zorder() == 0`). No CS-N section needed — render bug fix, not architecture. |
| ⏳ | 🟡 | **Axis double-click → axis-properties dialog (USER-FLAGGED feature)** | USER-FLAGGED at end of Phase 4ag (step 5 elicitation). User asked: "Double-click a plot axis in order to open a window to change axis-specific parameters? (including min, max, spacing, axis label, fonts, font sizes, axis colour, tick size, etc.)" Today axis-level controls are scattered: x-min / x-max / y-min / y-max sit on the UV/Vis top toolbar (read by `uvvis_tab._on_xmin_changed` etc.); y-axis label is rendered through CS-50 / CS-52 / CS-55 via `_resolve_y_axis_label`; tick direction lives in Plot Settings → Appearance (CS-56); font / font size / axis colour / tick size are NOT user-configurable today (matplotlib defaults). **Architecture proposal (lock pending):** new `axis_settings_dialog.py` modal Toplevel opened by a `<Double-Button-1>` binding on the matplotlib Axes (specifically on the axis-label and tick-label regions; clicking inside the plot area should NOT open it — that conflicts with the existing zoom-box gesture). Dialog covers: limits (min/max + autoscale toggle), tick spacing (major + minor), tick direction (CS-56 lives here too — relocate), tick size, axis label text, axis label font + font size + colour, tick label font + font size + colour, axis line colour. **Lock decisions for the implementing session:** (i) one dialog with primary/secondary/tertiary y selectors, or one dialog *per axis* opened by which axis was double-clicked? (ii) which settings move from Plot Settings → Appearance into the new dialog (avoid duplication) — CS-56 `grid_color` and `tertiary_axis_offset` should probably stay in Plot Settings (figure-level), but `tick_direction` is genuinely per-axis. (iii) Are axis settings per-tab or per-axis-role (left/right/secondary)? Likely per-axis-role for symmetry with how the renderer already constructs them. (iv) Does the dialog respect the existing Apply / ∀ Apply to All / Save / Cancel button row pattern (CS-23 lock)? **Affected:** new `axis_settings_dialog.py`, `uvvis_tab._redraw` (reads per-axis style keys), `_on_canvas_double_click` event hook, regression tests for the double-click region detection + the round-trip of every new style key. Pairs with the existing Plot Settings dialog (some keys may relocate). Multi-phase task — the design pass + the dialog shell + a first batch of 3–4 controls is a reasonable first phase. **Phase 4ai partial (CS-60):** lock decision (i) **closed — one unified dialog with Notebook tabs**, NOT one per axis. The implementation lifts the existing `PlotSettingsDialog` into `PlotConfigDialog` with a `ttk.Notebook` hosting six tabs: Global (today's PlotSettings content unchanged) plus Primary X / Secondary X / Primary Y / Secondary Y / Tertiary Y shells. The ⚙ button opens on Global; double-clicking on a plot axis region opens on that axis's tab via a new `plot_axis_hit_test.classify_axis_double_click(event, axes_by_role, tertiary_offset_frac)` classifier that translates a matplotlib MouseEvent into one of five axis roles × three hit kinds. Lock decision (iv) **closed but broadened — Save · Apply · Apply to All Tabs · Cancel** at the dialog level (CS-23 subsumed into CS-60); existing CS-23 semantics persist (Apply commits and stays open, Save commits and closes, Cancel reverts to snapshot). New cross-tab pending-edit state model: per-tab `" •"` modified marker, `_modified_tabs: set[str]`, `_KEY_TO_TAB` routing map (empty today, every key resolves to Global; populated by 4aj+ as per-axis settings move out of Global). Cancel-with-pending shows `askokcancel("Discard changes?")` confirm. Lock decisions (ii) and (iii) **deferred** — (ii) `tick_direction` likely moves to per-axis tabs in 4aj; `grid_color` and `tertiary_axis_offset` stay Global; (iii) per-axis-role schema invented in 4ak with migration shim from today's flat dict. Each axis tab in Phase 4ai is a shell (placeholder header + "(populated in Phase 4ak)" plot-list + "Per-axis settings land in Phase 4aj+" body); real per-axis settings start landing 4aj. 91 new tests (37 hit-test + 19 Notebook + 25 state model + 10 integration). **Carry-forward:** (a) `tick_direction` relocation to per-axis tabs (Phase 4aj — lock decision (ii) closure); (b) per-axis-role schema invention with migration shim (Phase 4ak — lock decision (iii) closure); (c) axis label override + plot-list (read) + plot routing (write) + range/autoscale + tick spacing — each Phase 4aj→4an step lands one slice. **Phase 4aj partial (CS-61):** lock decision (ii) **partially closed for `tick_direction`** — the widget moves out of Plot Settings → Appearance into a new "Settings" `LabelFrame` on each of the five per-axis Notebook tabs. All five tabs share one Tk var (`_control_vars["tick_direction"]`) so edits on any tab visually update all five radios; the working-copy key stays flat (single `tick_direction` string in `_USER_DEFAULTS`) — no per-axis schema invention (that remains Phase 4ak). `grid_color` and `tertiary_axis_offset` stay in Appearance per the original lock-decision-(ii) reasoning. New module-level `_KEY_TO_TAB` dict (CS-60 lock 4 relaxation — was empty in 4ai) gets its first explicit entry, `{"tick_direction": "primary_x"}`, so editing the radio on ANY per-axis tab marks ONLY Primary X dirty (not the full five-tab flood). The dirty-pin is intentionally independent of the visible tab: tick direction is most visually associated with bottom X-axis ticks in a UV/Vis plot. New `_build_axis_tab_settings(parent, role)` helper, called from `_build_axis_tab_shell`, is the body builder future per-axis ladder phases extend with additional widgets. The fallback reads from `_FACTORY_DEFAULTS["tick_direction"]` not a hard-coded "in" literal (CS-56 schema invariant preserved). **Carry-forward narrows:** (a) is now PARTIAL — only tick_direction has moved; future per-axis settings (axis label override, range/autoscale, tick spacing) still queue. Two acknowledged frictions for 4aj resolved by 4ak: (α) shared-var UX dishonesty (editing on Primary Y updates Primary X's radio); (β) dirty-pin counterintuitive (edit on Primary Y marks Primary X dirty). Both clear when 4ak invents per-axis schema and gives each tab its own slot. 13 new tests in `TestPlotConfigDialogTickDirectionRelocationPhase4aj`; 2 Phase 4ai tests updated in place. **Phase 4ak partial (CS-62):** lock decision (iii) **closed for the schema** — `_FACTORY_DEFAULTS` gains a nested `"axes": {role: {key: value}}` sub-dict housing per-axis `tick_direction` + the new `axis_label_override` key; top-level flat `tick_direction` is removed; `_UNIVERSAL_DEFAULTS` upgrades to a deep copy. Module-level `migrate_plot_config(config)` idempotent shim lifts legacy flat `tick_direction` into all five per-axis slots and back-fills missing keys from factory defaults; runs at dialog `__init__` on the working copy + Reset Defaults / Factory Reset paths. `_KEY_TO_TAB`'s `tick_direction` entry drops out (canonical CS-61 relaxation); per-axis writer `_on_axis_var_write(role, key, value)` carries the role directly and marks that tab dirty without going through `_key_to_tab`. New `self._axis_control_vars: dict[tuple[str, str], tk.Variable]` + `self._axis_control_refresh` analog store per-axis vars keyed by `(role, key)`; `_make_axis_string_var` is idempotent on the `(role, key)` pair so the Global "Per-axis label overrides" mirror section and the per-axis tab Entries share one Tk var. New `_build_section_axis_labels` Global section adds a five-row mirror (one Entry per role) plus `_DEFAULT_SECTIONS` extends to `"axis_labels"` with `_SECTION_TITLES["axis_labels"] = "Per-axis label overrides"`. `plots_by_role: dict[str, tuple[str, ...]] | None` constructor + factory kwarg threads the per-axis inventory; the per-axis tab's "Plots on this axis" `LabelFrame` renders a read-only `tk.Listbox` (height capped at 6) for populated roles, italic "(no plots on this axis)" otherwise — replacing the "(populated in Phase 4ak)" placeholder. Renderer wiring in `uvvis_tab._redraw`: new `_axis_label_override(cfg, tab_role)` helper resolves the per-axis override defensively; primary_x / primary_y / secondary_x / secondary_y / tertiary_y label setters now prefer a non-empty override over the auto/custom logic. Tick direction renders uniformly via `_per_axis_tick_direction(cfg, "primary_x")` — per-axis tick rendering is **explicitly deferred to Phase 4al** so the user observation "editing tick direction on Secondary X changes primary X but not secondary X" is honest about the transitional state. New `_enumerate_plots_by_role` module-level helper + `UVVisTab._compute_plots_by_role` host method feed the inventory at dialog open time (frozen for the dialog's lifetime — re-open to refresh). 39 net new tests (`TestPlotConfigDialogPerAxisSchemaPhase4ak`, `TestEnumeratePlotsByRolePhase4ak`, `TestUVVisTabPerAxisSchemaPhase4ak` plus inversions in `TestPlotConfigDialogTickDirectionRelocationPhase4aj`). **Carry-forward narrows further:** (a) is now narrower still — per-axis tick rendering, range / autoscale (4am), tick spacing (4an), and the "Move to ▾" picker writing `y_axis` style (4al) remain queued. Several frictions for 4ak: (γ) deferred per-axis tick rendering (user-surfaced specifically for Secondary X); (δ) dual-surface primary X/Y label (`axis_label_override` + legacy Title-and-labels section); (ε) `plots_by_role` frozen at open time; (ζ) Listbox is `state="disabled"` — could be clickable for jump-to-node. **Phase 4al partial (CS-63):** (γ) **closed** — `uvvis_tab._redraw` splits its tick_params calls into five per-axis-role invocations: `ax.tick_params(axis="x", direction=_per_axis_tick_direction(cfg, "primary_x"), …)` and the corresponding `axis="y"` call on primary; `get_axis` reads `_per_axis_tick_direction(cfg, "secondary_y" or "tertiary_y")` (via `_Y_AXIS_ROLE_TO_TAB`) at twin-creation time and applies it via `tick_params(axis="y", direction=…)`; the wavelength↔energy secondary_xaxis sibling drops its previously-hardcoded `direction="in"` in favour of `_per_axis_tick_direction(cfg, "secondary_x")`. The user-surfaced Secondary-X bug from Phase 4ak step 5 resolves — editing the radio on the Secondary X tab now visually moves only the secondary X axis ticks. The "Move to ▾" picker lands as a `ttk.Combobox` below the Listbox on the three Y-axis tabs (primary_y / secondary_y / tertiary_y). New module-level `_Y_AXIS_TAB_KEYS` frozenset + `_MOVE_TO_OPTIONS` 4-tuple (Default(None) / Primary Y / Secondary Y / Tertiary Y) + `_MOVE_TO_LABELS` + `_MOVE_TO_VALUE_BY_LABEL` constants drive the Combobox. The dialog speaks tab-role-key space throughout; the host (`UVVisTab._on_route_plot_from_dialog`) translates `target_tab_role` → CS-50 style value via the inverse of `_Y_AXIS_ROLE_TO_TAB` and writes through `graph.set_style`. Lock relaxations vs CS-62: Y-axis tab Listboxes promote `state="disabled"` → `state="normal"` so rows are selectable (X-axis tabs keep `state="disabled"` — no picker there); `_AXIS_KEYS` stays unchanged (the picker writes a per-NODE style key, not a per-axis schema slot). Picker fires immediately on Combobox value change — bypasses dialog Apply because it's a per-node style edit (consistent with the existing CS-50 Style-dialog path), not a per-plot-config edit. Source role disambiguates label collisions across axes: only nodes currently routed to `source_tab_role` are eligible targets. Combobox handler is extracted from a closure into `PlotConfigDialog._on_move_to_choose(role, listbox, var)` so tests can drive the routing path directly without relying on Tk virtual-event dispatch (which is not reliably synchronous in the full-suite run). 31 net new tests (`TestPlotConfigDialogMoveToPickerPhase4al`, `TestUVVisTabPerAxisTickRenderingPhase4al`, `TestUVVisTabMoveToPickerPhase4al`); 1 CS-62 test renamed (`test_plots_listbox_is_read_only` → `test_plots_listbox_is_disabled_on_x_axis_tabs`, pivoted onto the X-axis tab where the lock survives). **Carry-forward narrows further:** range / autoscale / scale-type widgets (4am); tick spacing + per-axis grid + per-axis colour pickers (4an). The Secondary X tab's tick_direction now applies but the rest of the per-axis ladder (range, tick spacing) still queues. One Phase 4al friction: (η) Cancel-with-pending semantics for routing edits — the picker mutates style immediately, so Cancel does NOT revert routing decisions. This is by design (CS-50 style edits commit on pick across the whole app), but a future "live-preview vs Apply" reconciliation phase could revisit. **Phase 4am partial (CS-64):** range / autoscale / scale (linear/log) slice closes — `_AXIS_KEYS` grew 2→6 with `range_lo` / `range_hi` (StringVar, empty = no bound) / `autoscale` (BooleanVar, default-True = ignore schema bounds) / `scale` (one of `{"linear", "log"}`). Each per-axis tab's Settings frame gains three new widget rows below the existing tick-direction + axis-label-override rows: Range Entry pair, Autoscale Checkbutton, Scale Combobox. New `_make_axis_bool_var(role, key)` helper mirrors `_make_axis_string_var` for BooleanVar-backed keys; registers in the same `_axis_control_vars` / `_axis_control_refresh` registries with matching trace + refresh semantics. Renderer wiring in `uvvis_tab._redraw`: four new module-level helpers (`_per_axis_range(cfg, role, key)`, `_per_axis_autoscale(cfg, role)`, `_per_axis_scale(cfg, role)`, `_parse_lim_str(text)`) provide defensive reads with safe fallbacks. Primary X / Primary Y apply scale + range at their existing limit-application sites; twin Y-axes (secondary_y, tertiary_y) apply per-role scale + range at the twin axis after the primary plot loop via a `_Y_AXIS_ROLE_TO_TAB` iteration; secondary X (wavelength-nm sibling) applies inline when active. **Backward compat decision:** legacy top-bar `_xlim_lo` / `_xlim_hi` / `_ylim_lo` / `_ylim_hi` Tk vars remain the fallback for primary_x / primary_y when `autoscale=True` (default) — the existing top-bar Entry UX keeps working unchanged without a sync trace; `autoscale=False` makes the schema bounds win. `set_yscale("log")` applies BEFORE `set_ylim` so log + clamp lands in log space. 39 net new tests (`TestPlotConfigDialogPerAxisRangeScaleSchemaPhase4am` × 6 schema + idempotency + factory shape; `TestPlotConfigDialogPerAxisRangeScaleWidgetsPhase4am` × 13 widget surface + var registry + Apply round-trip + legacy-config fill-on-load; `TestUVVisTabPerAxisRangeScalePhase4am` × 20 helper read paths + primary X/Y autoscale modes + scale=log + twin Y range + only-one-bound + missing-axes defensive). 2 Phase 4ak tests updated in place (`test_factory_defaults_carries_nested_axes` + `test_axis_keys_registry_matches_factory` to assert the 6-tuple shape and the new per-role default values). **Carry-forward narrows further:** only tick spacing + per-axis grid + per-axis colour pickers (4an) remain. Phase 4am frictions: (θ) Range Entry pair edits don't trigger an immediate `_redraw` — the user has to click Apply (or pick Save). The legacy top-bar Entries have an immediate-on-edit hook via their `_on_xmin_changed`/etc. callbacks; the schema-side widgets don't carry an equivalent because Plot Settings is a CS-06 working-copy model where edits don't render until Apply. Folds naturally into the USER-FLAGGED live-preview register entry. (ι) Top-bar legacy Tk vars and schema range_lo/range_hi can drift: a user typing in the top-bar while autoscale=True writes only the Tk var; if they later set autoscale=False via the dialog, the schema's range_lo/range_hi (still empty) "wins" and the top-bar Entry value is silently ignored. By design — preserves the working-copy boundary — but worth a tooltip on the Autoscale Checkbutton clarifying the fallback chain. Polish-level. (κ) Secondary X range Entries currently apply to the visible secondary_xaxis sibling (the wavelength↔energy twin) but only when the twin is active (cm-1 primary unit AND show-nm-axis enabled). Editing the Secondary X range in the dialog with the twin inactive silently no-ops. Documented in the helper docstring; folds into the Twin-X register entry. |
| ⏳ | 🟡 | **`_USER_DEFAULTS` tab-type split — universal vs per-tab-type axis-label keys (USER-FLAGGED, Phase 4ai)** | USER-FLAGGED at end of Phase 4ai (step 5 elicitation). User confirmed the design taxonomy: "for plot and axis settings, these really are tab-dependent. For example, the primary axis label for XANES will definitely NOT be the same as that for UV/Vis. The behaviour of 'Apply to All' therefore also needs to be limited to that tab." Today `plot_settings_dialog._USER_DEFAULTS` is a single module-level flat dict — UV/Vis is the only host that uses it. As XANES / EXAFS / Compare get their own `PlotConfigDialog` wiring, the dict will leak axis labels across tab types (e.g. XANES inherits UV/Vis's "Absorbance (A)" axis label on first construction). **Architecture proposal (lock pending):** two viable shapes — (a) tab-type-namespaced nested dict (`_USER_DEFAULTS["uvvis"]`, `_USER_DEFAULTS["xanes"]`, etc.) with the dialog reading a `tab_type=` argument to pick the right sub-dict, OR (b) split the dict into a universal half (fonts, grid, background — tab-type-agnostic) and a tab-specific half (axis labels, axis label modes — tab-type-scoped). Option (b) is more discoverable but adds complexity in `_FACTORY_DEFAULTS` (which keys belong where). **Lock decisions for the implementing session:** (i) which shape; (ii) does `Save as Default` persist into the universal slot, the per-tab-type slot, or both depending on which key the user touched? (iii) does the `project_io` round-trip schema mirror the new shape (CS-46 manifest `plot_defaults` key)? **Affected:** `plot_settings_dialog._USER_DEFAULTS` shape + `_do_save_as_default` write path; `uvvis_tab.__init__` read path (and equivalents in future tabs); `project_io.save_project` / `load_project` for `plot_defaults` round-trip (CS-46-locked but relaxable for schema evolution); `binah._do_save_workflow` / `_do_open_workflow` mirroring writes. Cross-refs CS-46 (persistence manifest), CS-60 (the dialog that consumes the defaults), the "Refactor uvvis_tab.py — extract host shell" register entry (cross-tab generalization is the same broader effort). Becomes urgent when the dialog gets wired into a second tab type; not urgent today since only UV/Vis uses it. |
| ⏳ | 🟡 | **Twin-X axis — wavelength↔energy with bidirectional range coupling (USER-FLAGGED, Phase 4ai)** | USER-FLAGGED at end of Phase 4ai (step 5 elicitation). User: "Let's wire the Twin-X as a tab as well... we still want to be able to control its behaviour (but in a more limited way since it's mostly tied to the primary x-axis). [Best scenario is that we could pick limits to xmin and xmax in either the primary or twin-x and then an appropriate choice is made for the partner x-axis (future development?)]". Phase 4ai's CS-60 Notebook already includes a Secondary X tab as a shell (double-clicking the top spine opens it); this register entry covers the actual matplotlib machinery for the twin-x axis itself. **Architecture proposal (lock pending):** new `_secondary_x_ax = self._ax.twiny()` in `_build_plot`; a transform function `_x_primary_to_secondary(x_primary, primary_unit, secondary_unit) -> x_secondary` and inverse, keyed on whichever pair of units the user has selected (wavelength_nm ↔ energy_eV, wavenumber_cm-1 ↔ wavelength_nm, etc.). On every `_redraw`, set the secondary axis's xlim from the primary's xlim via the transform. Range coupling is bidirectional in the sense that the Secondary X tab's range entries (when they land in Phase 4am or later) edit either side, with the partner side recomputed automatically. **Lock decisions for the implementing session:** (i) what unit pair routes to the twin-x — fixed (wavelength ↔ energy only), or user-configurable; (ii) does the twin-x exist always (when the primary axis is wavelength_nm) or only when the user explicitly enables it via a Plot Settings checkbox? (iii) does the secondary-x label autoderive ("Energy (eV)" when primary is "Wavelength (nm)") or accept a user override; (iv) which side is the "source of truth" for limits — primary always wins, or last-edited wins? **Affected:** `uvvis_tab._build_plot` (twin-x construction), `_redraw` (transform + xlim sync), new `_X_UNIT_PAIRS: dict` for the transform table, `plot_settings_dialog`'s Secondary X tab content (range / autoscale / label / show-toggle), tests for the transform round-trip and range coupling. Cross-refs CS-60 (the Notebook tab the dialog content lives on), the existing `_convert_xlim` helper in `uvvis_tab.py` (the same transform machinery probably lifts into a shared `x_unit_transforms.py` module). Becomes actionable when Phase 4am-ish range controls land (the tab needs widgets before the wiring matters). |
| ⏳ | 🟢 | **Per-tab tertiary-y-axis default routing schema (USER-FLAGGED design topic)** | USER-FLAGGED at the START of Phase 4ah ("With regards to default multi-axis functionality, we will need to consider what counts as default behaviour differently in different tabs. For UV/Vis, we know that the derivative goes to secondary. Not sure what would need to default to the tertiary y-axis (if anything)."). Today `_DEFAULT_Y_AXIS_BY_NODETYPE` (CS-44-locked, in `uvvis_tab.py`) is a single flat dict mapping `NodeType → axis_role` shared across the codebase. As more tabs adopt the renderer architecture (TDDFT pending UV/Vis-style migration; Compare planned), per-tab routing diverges: UV/Vis derivative → secondary is clear, but TDDFT might want primary=spectrum / secondary=oscillator-strength / tertiary=transition-density-or-state-energy; Compare might be primary-only. **Architecture proposal (lock pending):** (a) extend `_DEFAULT_Y_AXIS_BY_NODETYPE` into `_DEFAULT_Y_AXIS_BY_NODETYPE: dict[str_tab_name, dict[NodeType, role]]` and have each tab read its sub-dict; (b) introduce a per-tab registry pattern where each Tab class owns its own `DEFAULT_Y_AXIS_BY_NODETYPE` class attribute (the renderer reads from `self.DEFAULT_Y_AXIS_BY_NODETYPE` instead of the module-level constant); (c) status quo + per-NodeType-uniqueness invariant (each NodeType belongs to exactly one tab, so the flat dict suffices — only ambiguous if two tabs render the same NodeType). **Lock decisions for the implementing session:** (i) which option (a/b/c); (ii) does d²A stay on secondary by default (current behaviour) or move to tertiary (separate magnitude from d¹A) — Claude's recommendation during the Phase 4ah elicitation was "keep both derivatives on secondary, let users move d²A explicitly"; (iii) TDDFT tertiary candidates — transition density vs state energy vs none; (iv) does this phase relocate CS-44 invariants into a registry, or layer on top. **Affected:** `uvvis_tab._DEFAULT_Y_AXIS_BY_NODETYPE` (CS-44 lock needs deliberate relaxation), every tab's renderer, COMPONENTS.md CS-44 update. Cross-refs the multi-axis routing CS-44 register entries above and the "Refactor uvvis_tab.py — extract host shell" cross-tab generalization entry. Dedicated future phase — Claude recommended NOT bundling into Phase 4ah; queued here for explicit pickup. |
| ⏳ | 🟢 | **Sidebar `«` toggle + "TDDFT Section:" combobox follow Open File / Reload into TDDFT chrome (USER-CONFIRMED follow-up)** | Surfaced Phase 4ah step 5 and USER-CONFIRMED for queueing as a future-phase polish. With commit 3 of Phase 4ah relocating Open File / Reload from `binah._build_top_bar` into the TDDFT sidebar, the top bar still hosts two pieces of TDDFT-only chrome: (a) the `«` sidebar-toggle button (operates on `self._sidebar`, which is the TDDFT-specific Loaded Files pane), and (b) the "TDDFT Section:" combobox + the "No file loaded" file label. None of those make sense for UV/Vis, XANES, EXAFS, or the planned Compare tab. **Architecture proposal (lock pending):** relocate all three into the TDDFT tab — the `«` button into the TDDFT sidebar's own chrome, the section combobox + file label into a small TDDFT-tab top strip. Once done, the app top bar becomes either empty (auto-hidden) or repurposed as a true cross-tab status row. **Lock decisions for the implementing session:** (i) where does the `«` button live — TDDFT sidebar top corner, or inside `_build_main_area`'s spectra-frame chrome? (ii) does the empty top-bar disappear (`pack_forget` when no children), or stay as a status strip? (iii) keyboard shortcuts (none currently bound) — defer. **Affected:** `binah._build_top_bar`, `binah._build_main_area` (TDDFT side), `_toggle_sidebar`'s `self._sidebar_btn` lookup. Cross-refs the larger "Refactor uvvis_tab.py — extract host shell into separate files; cross-tab generalization" register entry (the broader tab-chrome lift). Pairs with the keyboard-shortcuts whole-interface evaluation USER-FLAGGED pass (which may scope `Ctrl+O` to TDDFT at the same time). |
| ✅ | 🟡 | **"Show hidden" toggle should disable when no hidden rows exist (USER-FLAGGED polish)** | USER-FLAGGED at end of Phase 4ag (step 5 elicitation; "If it's not relevant, then it should be greyed out when it's not relevant"). Originally surfaced as a 🟢 Claude polish in Phase 4af friction #5 ("'Show hidden' footer toggle behaviour is opaque"). **Resolved Phase 4ah (CS-59 Thread A, commit 2):** new `_has_hidden_rows()` predicate returns True iff ≥1 non-DISCARDED DataNode with `active=False` passes the tab predicate (or is itself a NODE_GROUP). New companion `_refresh_show_hidden_button_state()` flips the Checkbutton (now stored as `self._show_hidden_btn`) between `"normal"` and `"disabled"`. Called at the end of every `_rebuild` immediately after `_refresh_group_button_state` — the cluster of `_refresh_*_button_state` methods is now the canonical pattern for state-aware footer controls. **Lock decisions taken:** (i) disable-only — no count badge or tooltip (minimal scope, matches the user's "greyed out" phrasing); (ii) cascade preserves `_show_hidden` ON when the last hidden row disappears (toggle stays ON + becomes disabled — never silently flipped, the disabled state is the affordance); (iii) hidden group members count regardless of whether their parent group is expanded (avoids whiplash on expand/collapse — see CS-59 lock 2). 11 new tests in `TestShowHiddenButtonGatingPhase4ah`: 6 pure-helper coverage (empty graph, all-active, one-hidden, discarded-ignored, predicate-excluded-ignored, NODE_GROUP-counts), 5 button-state coverage (fresh-disabled, becomes-hidden, un-hidden-redisables, cascade discard preserves `_show_hidden` ON, hidden group member counts). Closes the chain with Phase 4af friction #5 (now ✅). |
| ⏳ | 🟡 | **External-output plot style presets — journal / presentation / web formatting (USER-FLAGGED, Phase 4aj)** | USER-FLAGGED at end of Phase 4aj (step 5 elicitation). User: "Include plot style formatting defaults that are tailored to specific external outputs. For example, for a figure for J. Am. Chem. Soc. or for a two column powerpoint presentation, etc. I have implemented this in some jupyter notebooks and we can steal some of the code and information from there. This will be a per plot type setting and will need some thought on how to do that." Today every plot inherits the same `_FACTORY_DEFAULTS` (`title_font_size = 12`, `xlabel_font_size = 10`, `tick_label_font_size = 9`, etc. in `plot_settings_dialog.py`) — appropriate for an interactive UI but typically wrong for a journal-figure target (smaller, denser, narrower aspect) or a presentation slide (larger, bolder, wider). **Architecture proposal (lock pending):** new `_OUTPUT_PRESETS: dict[str, dict[str, Any]]` registry mapping preset names → working-copy patch dicts. Concrete first-batch candidates: `"jacs_single_column"` (JACS single-column figure), `"jacs_double_column"` (JACS double-column figure), `"nature_main"` (Nature main-text figure), `"powerpoint_two_column"` (two-column 16:9 slide), `"powerpoint_full"` (full-slide), `"web_compact"` (web/notebook-embed). The user has reference Jupyter notebook code with concrete `rcParams` blocks; **lifting those values is half the work**. New "Preset:" combobox at the top of Plot Settings → Global tab (above the existing section stack) applies the patch on selection; a `"(custom)"` sentinel surfaces when the user departs from any preset. **Lock decisions for the implementing session:** (i) where do presets live — bundled in `plot_settings_dialog.py`, a new `plot_style_presets.py` module (preferred for testability + future user-extensibility), or an external JSON/YAML config the user can extend without code edits? (ii) **"per plot type setting"** — does each tab type (UV/Vis / XANES / EXAFS / Compare) get its own preset list with tab-aware tweaks (JACS-UV/Vis has different sizing than JACS-EXAFS k-space), or is the preset list shared and tab-aware nuances ride elsewhere? Pairs with the existing `_USER_DEFAULTS` tab-type split register entry; should probably wait for that schema to land first (Phase 4ak+). (iii) does selecting a preset commit immediately to working-copy + flip every modified tab dirty, or stage as a separate preview/apply gesture? (iv) is figure aspect ratio / dimensions part of the preset, or out of scope (matplotlib `figure.figsize` lives at canvas-creation time, not in Plot Settings today — would require canvas-recreate plumbing if included)? (v) does the manifest schema (CS-46 `plot_defaults` key) round-trip the preset NAME (so a `.ptmg` "remembers" the user picked JACS), or just the resolved values? **Affected:** `plot_settings_dialog.py` (preset registry + Global-tab picker + "(custom)" sentinel detection on any edit that departs from the active preset), CS-46 manifest schema (maybe — depends on lock (v)), new tests for preset application + the custom-sentinel transitions, possibly `uvvis_tab.py` if figure dimensions land in scope (lock (iv)). Cross-refs: `_FACTORY_DEFAULTS` (CS-23 / CS-56 / CS-60) — presets layer ON TOP of factory defaults, never replace; `_USER_DEFAULTS` tab-type split register entry (per-tab-type behaviour pairs with per-preset behaviour); the existing Plot Settings → Appearance section (Fonts / Background colour / Grid colour). Multi-phase task — design + first-batch (~3-4 presets bundled, single tab type) is one phase; per-tab-type expansion is a later phase. **Reference code source:** user's Jupyter notebooks (paths to be supplied at start of the implementing phase). |
| ✅ | 🟡 | **Live-preview vs Apply button — modal-vs-instant settings reconciliation (USER-FLAGGED, Phase 4ak)** ✅ Resolved Phase 4ap (CS-68). | Resolved Phase 4ap (CS-68). Live-preview lands on `PlotConfigDialog` only — discrete widgets (Combobox, Checkbutton, Spinbox, color picker, Radiobutton) commit every edit immediately via `_apply_changes_live` (mirror `_working` → `_config` + fire `on_apply`); text Entry widgets defer the live commit to `<FocusOut>` / `<Return>` so per-keystroke typing does not redraw a 100-spectrum canvas. Apply button retired. Button row collapses to `Save · Apply to All Tabs · Cancel`. **Lock decisions taken:** (i) live-preview replaces the working-copy commit gesture entirely — `_working` retained as the widget-bound mirror, `_config` is mutated in place by `_apply_changes_live`; (ii) Cancel still reverts via the `_snapshot` copy taken at `__init__` (no undo stack); (iii) scope is Plot Settings only — CS-05 `StyleDialog` was already write-through, project-load mismatch dialog stays modal/working-copy as a confirmation gate; (iv) per-keystroke redraw deferred via `<FocusOut>` / `<Return>` on text Entries — no debounce framework needed. The CS-60 `_modified_tabs` markers semantic broadens to "touched since open" — they persist through live commits and clear only on Cancel revert or destroy. Defaults / Factory Reset bulk reload coalesces to one redraw. Pairs with CS-66 modeless: Phase 4ao friction #9 (modeless × per-row baseline toggle) covered by `TestUVVisTabLivePreviewModelessPhase4ap.test_per_row_toggle_redraws_canvas_with_dialog_open`. 1302 tests green (1285 + 17 new). |
| ⏳ | 🟡 | **Cross-node Style dropdown / multi-node style window (USER-FLAGGED, Phase 4ap)** | USER-FLAGGED at end of Phase 4ap (step 5 elicitation). User: "just like plot settings, I'd like a way of having access to all node plot settings from the pop up window. dropdown menu with all of the loaded nodes?" Today CS-05 `StyleDialog` is opened per-node — there is no single window listing every loaded node's style. The user's request: extend the modeless Plot Settings paradigm (CS-66 / CS-68) to per-node styles, with a Combobox listing every loaded node, switching the per-node controls on selection. **Architecture proposal (lock pending):** spawn a new modeless dialog (working title `NodeStylesDialog` or similar) — OR add a "Node styles" Notebook tab to the existing `PlotConfigDialog` — that carries (a) a Combobox listing every loaded node by `(label, id)`, (b) the existing CS-05 universal section (color, linestyle, linewidth, alpha, visible, in_legend) for the selected node, (c) the per-NodeType extension sections (peak-marker style for PEAK_LIST, etc.) that CS-05 already provides. Live-preview semantic from CS-68 carries forward — every edit writes to the selected node's `style` dict via `graph.set_style` and `GraphEvent.NODE_STYLE_CHANGED` fires the redraw. **Lock decisions for the implementing session:** (i) extend `PlotConfigDialog` as a new "Node Styles" tab (cross-tab routing map / per-tab dirty markers extend) vs. spawn a new sibling dialog (cleaner separation, but the user has to remember two windows); (ii) when a node is added / discarded mid-session, refresh the Combobox (pairs with the long-standing `_plots_by_role` frozen-at-open friction — CS-62 lock relaxation needed); (iii) interaction with the existing per-node CS-05 `StyleDialog` (right-click "Edit Style…") — coexist or subsume; (iv) per-node ∀ apply-to-all flows (CS-05 universal `_push_to_all` factory) — surface the Combobox as the source of "Apply to all of THIS node's siblings"; (v) what does "all loaded nodes" mean — UVVIS only, or every NodeType across every tab (Compare / XANES / EXAFS will eventually have nodes too)? Phase 4 scope answer: UVVIS-tab-private node list. **Affected:** new module `node_styles_dialog.py` (or new tab inside `plot_settings_dialog.py`), new `_open_dialogs`-style registry, host wiring on `UVVisTab`, integration tests. Multi-phase: design + scope decision (extra-high) → Plot Settings tab vs. new dialog (high) → cross-tab adoption later. Pairs naturally with CS-05 / CS-06 / CS-66 / CS-68. |
| ✅ | 🟡 | **Autoscale ↔ Range Entry seed semantics (USER-FLAGGED, Phase 4ap)** ✅ Resolved Phase 4as (CS-71). | Resolved Phase 4as (CS-71) — commits `fd93182` (pure module) + `c5cffc6` (32 unit tests + 2 reframed) + `97a6536` (host wiring + CS-66 fix) + `fa70f9b` (28 integration tests + D15 polish). Lock-decision closures: (i) read-back source — the host's `_compute_axis_displayed_limits()` reads `_axes_by_role["primary"].get_xlim()/get_ylim()` for primary_x/primary_y plus twin axes for secondary_y/tertiary_y; fires from `_redraw` end + `_draw_empty` end + once after `open_plot_config_dialog` returns (the seed-on-open path) — so the dialog sees the limits without needing a separate `on_apply` hook. (ii) seed-on-toggle policy CLOSED — True→False fires `_seed_range_entries_from_display(role)` which writes the displayed-limits snapshot into the canonical schema StringVars via `var.set()`; False→True does NOT touch the canonical StringVars (the user's typed values are preserved in `_working`). (iii) dialog-open with autoscale=True CLOSED — the parallel display StringVar shows the displayed limits AND the Entry is `state="disabled"` from build time; the post-open notify call populates the display var immediately so the user sees actual values not the construction-default empty string. (iv) CS-65 interaction CLOSED — `tick_major`/`tick_minor` Entries are untouched; CS-71's mechanism is exclusive to `range_lo`/`range_hi`. **Mechanism:** new parallel `_axis_range_display_vars[(role, key)]` StringVars built for the four non-secondary_x roles; `Entry.configure(textvariable=…)` swaps between the canonical schema StringVar (autoscale=False, editable) and the display StringVar (autoscale=True, disabled). CS-64 D8 lock relaxation explicit: the Entry's textvariable is no longer permanently the canonical StringVar. **CS-70 composition:** CS-71's `_apply_axis_autoscale_greying(role)` short-circuits for `secondary_x` so CS-69 / CS-70's link greying wins for that role. Two pre-existing CS-69 / CS-70 tests narrowed for the relaxation (`test_other_role_widgets_not_disabled_when_secondary_x_linked` + `test_other_roles_unaffected_by_refresh` — both now skip `range_lo`/`range_hi` in their inner key loops with a CS-71 cross-ref comment). 32 unit + 10 integration test sentinels pin the contract. |
| ✅ | 🟠 | **USER-FLAGGED bug: wavelength as linked secondary axis is broken (B-005, Phase 4ap)** ✅ Resolved Phase 4aq (CS-69). | Resolved Phase 4aq (CS-69) — commits `aedfd81` + `cdd6f61` + `df2542a` + `ab6a178`. Root cause: the secondary X axis was correctly using matplotlib's linked `ax.secondary_xaxis(functions=(_fwd, _fwd))` API, but the renderer then called `sec.set_xlim(...)` from the CS-64 `range_lo` / `range_hi` / `autoscale` schema path. On a linked secondary that call back-propagates through the inverse of `_fwd` and CORRUPTS the primary axis — the user-visible symptom. **Fix landed:** (1) renderer NEVER calls `sec.set_xlim` / `sec.set_xscale` (matplotlib owns linked limits); (2) new per-axis schema key `custom_ticks: str` (comma-separated explicit nm positions like `"300, 400, 500"`) paints `FixedLocator` major ticks via the new `_apply_major_locator` helper, uniform across all per-axis roles (D6b lock); (3) D8 lock relaxation extends the link to BOTH cm⁻¹ (via `1e7 / x`) AND eV (via `_HC_NM_EV / x`); both are self-inverse; (4) new `secondary_x_linked: bool` dialog kwarg snapshotted at open greys out Secondary X tab's range_lo / range_hi / autoscale / scale widgets so the user can't fight the link — custom_ticks / tick_major / tick_minor stay editable. Logged as **B-005** in the Known Bugs table below (now ✅). 45 new tests pin the fix: 27 unit (parse, accessor, link cm⁻¹+eV, renderer FixedLocator) + 18 integration (greying, custom_ticks Entry round-trip, migration shim). |
| ⏳ | 🟡 | **Apply-to-all icon on per-axis Plot Settings tabs — UI consistency with data-node settings (USER-FLAGGED, Phase 4ak)** | USER-FLAGGED at end of Phase 4ak (step 5 elicitation). User: "Use same apply-to-all icon used for data node settings in the axis setting popups." Data-node settings (the per-row → icon on `ScanTreeWidget` rows surfaced by CS-27 / Phase 4n) carry a recognisable "Apply to all" affordance; Plot Settings → per-axis tabs offer only the dialog-level "Apply to All Tabs" button at the bottom (CS-60 button row). The per-axis tabs lack an in-tab "Apply this axis's settings to every other axis" gesture — useful for cases like "apply this tick direction to every axis at once" or "broadcast this axis label override to every Y axis". **Architecture proposal (lock pending):** add a small icon button next to each per-axis widget (or at the per-axis tab top) labelled with the same icon used by `ScanTreeWidget`'s send-to-compare row icon (the → symbol per CS-27). Click → confirm dialog → write the widget's value into every other per-axis role's slot in `self._working`, mark every other per-axis tab dirty. **Lock decisions for the implementing session:** (i) per-widget icon (one per widget on the per-axis tab) or per-tab icon (one icon broadcasts every widget on the tab)? (ii) does the broadcast respect axis-shape semantics (e.g. an X-axis tab's value broadcast to other X tabs only, not Y)? (iii) does the broadcast write through `_USER_DEFAULTS["axes"][role]` directly or stage through `_on_axis_var_write` per-widget (the latter is consistent with the existing dirty-marker contract)? (iv) does the icon match `_send_to_compare_btn`'s exact glyph or use a slightly different one to distinguish axis-to-axis from tab-to-compare? **Affected:** `plot_settings_dialog.py` (new icon widget + broadcast handler; CS-62 `_axis_control_vars` walk), CS-61 / CS-62 layout (icon adds a row or column to the Settings frame), tests for the broadcast path. Cross-refs CS-27 (the existing per-row send-to-compare icon pattern), CS-60 (the dialog-level Apply to All Tabs button — different scope), CS-62 (per-axis Tk var registry). Small-medium phase; depends on having more than one populated per-axis widget (Phase 4ak ships two: tick_direction + axis_label_override, so this is actionable from 4al onward). |
| ⏳ | 🟡 | **Axis nomenclature rename: primary/secondary/tertiary → bottom/top/left/right with `*` suffix for offset (USER-FLAGGED, Phase 4ak)** | USER-FLAGGED at end of Phase 4ak (step 5 elicitation). User: "Maybe we should not use primary, secondary, tertiary for axes and use clear location designations such as bottom/top for the main x-axes and something like bottom* and top* for offset secondary axes for a total of 4 possible axes along x. Similar structure for y with left/right/left*/right*. Open to better nomenclature." The current taxonomy (CS-44: `primary` / `secondary` / `tertiary`; CS-60: `primary_x` / `secondary_x` / `primary_y` / `secondary_y` / `tertiary_y`) is renderer-internal and dialog-facing. Position-based names ("bottom", "top", "left", "right", with `*` for offset/secondary instance) are more discoverable for the user — a UV/Vis researcher doesn't need to know that "secondary" specifically means twinx. The proposal also opens the door to a fourth axis on each side (currently `*` suffix denotes offset, but the rename allows growth to "right*" being a tertiary-stack-style offset on top of "right"). **Architecture proposal (lock pending):** rename across the codebase. Affects: `_AXIS_ROLES = ("primary", "secondary", "tertiary")` (CS-44 lock), `_TAB_KEYS = ("global", "primary_x", "secondary_x", "primary_y", "secondary_y", "tertiary_y")` (CS-60 lock), `_TAB_TITLES` strings (CS-60 lock), `_DEFAULT_Y_AXIS_BY_NODETYPE`'s values (CS-44 lock), `_resolve_y_axis_role`'s return values (CS-44 lock), every test asserting any of the above, plot_settings_dialog's per-axis tab keys, `_Y_AXIS_ROLE_TO_TAB` (CS-62 lock), the `y_axis` style key's value set (CS-50 lock), the manifest's nested `axes` sub-dict keys (round-trip across `_USER_DEFAULTS` via project_io). **Lock decisions for the implementing session:** (i) exact name set — is the `*` suffix preserved or replaced with something more keyboard-friendly (e.g. `"bottom_offset"`)? `*` reads well in UI but parses awkwardly in code paths. (ii) does the rename happen all-at-once (one massive sweep phase) or incrementally with an alias dict mapping old → new during transition? (iii) does the `y_axis` style key's value set (CS-50: `"primary"` / `"secondary"` / `"tertiary"`) rename in lockstep — yes for consistency but increases blast radius. (iv) does the manifest schema gain a migration shim for projects saved with old names (yes, since `.ptmg` files can be years old). (v) what about the existing `_axes_by_role` dict key names (used by tests + matplotlib introspection)? **Affected:** Massive cross-codebase rename. CS-44 / CS-50 / CS-60 / CS-61 / CS-62 locks all need deliberate relaxation. Carries through to manifest round-trip migration shim + every test pinning role names. Multi-phase task — the cleanest path is one phase for the schema rename + migration shim, one phase for the dialog labels + tab titles, one phase for the renderer's internal names, with a final cleanup pass. **Risk:** high blast radius. Could combine with the "Refactor uvvis_tab.py — extract host shell" register entry since both touch axis-handling code paths. |
| ⏳ | 🟡 | **Rich-text axis labels — subscript / superscript / equation markup (USER-FLAGGED, Phase 4ak)** | USER-FLAGGED at end of Phase 4ak (step 5 elicitation). User: "Allow for subscript/superscript and equations in axis labels. How can we do that?" Today axis labels are plain strings written through matplotlib's `set_xlabel` / `set_ylabel` (CS-62's `axis_label_override` is a plain `str`). matplotlib supports a `mathtext` subset of LaTeX inline (e.g. `r"$d^2 A / d\lambda^2$"`) AND the full `usetex=True` LaTeX rendering when a LaTeX installation is on `$PATH`. The user wants the override Entry to accept LaTeX-style markup and render it in the figure. **Architecture proposal (lock pending):** enable matplotlib's mathtext on every axis label setter. Simplest path: change `set_xlabel(text, ...)` → `set_xlabel(text, ...)` with matplotlib's default mathtext parser (no extra config needed — `$...$` is parsed automatically). User types `$d^2 A / d\lambda^2$` into the Plot Settings → Primary Y axis label override Entry → matplotlib renders the math expression. **Lock decisions for the implementing session:** (i) does the Entry widget need any preprocessing or do we trust the user to type `$...$` directly? (ii) is there a "Markup help" tooltip or pop-up showing example expressions (`$\alpha$`, `$d^2A/d\lambda^2$`, `$\Delta E$`)? (iii) does we expose mathtext only, or also the full LaTeX path (`usetex=True`) which requires a LaTeX install? (iv) does the manifest round-trip preserve the raw markup string (yes — it's a plain `str` already). (v) does the same support extend to title (`title_text`) and the legacy xlabel/ylabel custom text path? (likely yes for consistency). **Affected:** `plot_settings_dialog.py` per-axis Entry widgets + the legacy Title-and-labels section's Entry widgets — the markup goes in transparently since `set_xlabel` already supports it. Possibly a tooltip module for the markup help. New test asserting `set_xlabel($d^2A$)` renders without error. Small phase — enabling mathtext is essentially free; the lift is testing + documenting the gesture for users. Cross-refs CS-62 (`axis_label_override` Entry widgets), the legacy "Title and labels" section. **Caveat:** matplotlib's mathtext is a SUBSET of LaTeX (most math symbols work, but `\text{}`, fancy spacing, and some packages don't). Decision (iii) determines whether power users get full LaTeX. |
| ⏳ | 🟡 | **Accessibility features (USER-FLAGGED, Phase 4al)** | USER-FLAGGED at end of Phase 4al (step 5 elicitation). User: "can we implement any accessibility features in the software?" Open-ended architectural question with multiple sub-axes. Today the app has effectively zero accessibility support: no keyboard navigation in the unified PlotConfigDialog or StyleDialog beyond Tab/Enter (no chord shortcuts, no menu mnemonics), no screen-reader hints, no high-contrast / dark mode (background is hardcoded `#ffffff` in `_FACTORY_DEFAULTS["background_color"]`), no colour-blind-safe palette toggle on `node_styles.SPECTRUM_PALETTE` (CS-21 — 10-colour palette with several red/green near-collisions), no large-text / scaling override on the matplotlib font sizes, no focus-visible outline polish for keyboard navigation. **Architecture proposal (lock pending):** scope a first batch by impact-vs-cost. Likely high-impact / low-cost: (1) keyboard shortcuts for common gestures (already a USER-FLAGGED register entry from Phase 4ah — pairs naturally); (2) colour-blind-safe palette as an opt-in `SPECTRUM_PALETTE` swap (e.g. Wong's 8-colour palette or the matplotlib `tab10` deuteranopia-safe variant); (3) global tk option/theme that enlarges font sizes by an `accessibility.scale` multiplier (touches every `font=("", N, ...)` literal across the dialog modules); (4) dialog dismiss via Escape (some dialogs already wire it; auditing for consistency). Lower priority but worth recording: (5) screen reader hints via `accessibility.title` on widgets (Tk has limited a11y story; depends on platform — Windows via UIA, macOS via AX, Linux via AT-SPI); (6) high-contrast mode (toggle that swaps background + grid + spine colours); (7) dyslexia-friendly font option. **Lock decisions for the implementing session:** (i) does accessibility get a new top-level Settings section (e.g. an "Accessibility" tab in PlotConfigDialog or a new app-level Preferences dialog), or live as scattered toggles? (ii) does the colour-blind palette swap commit on click (immediate redraw of every scan) or stage as a working-copy edit? (iii) which dialogs are in scope for the keyboard-nav audit — every modal, or just the high-traffic Plot Settings / Style? (iv) does the font-scale multiplier round-trip through `_USER_DEFAULTS` (yes — it's a persistent preference)? (v) which platforms / screen readers are in the supported matrix? **Affected:** Wide — `node_styles.py` (palette), `plot_settings_dialog.py` (font sizes, possibly a new Accessibility section), `style_dialog.py`, every dialog with `grab_set` (Escape audit), possibly new `accessibility.py` module. Cross-refs CS-21 (SPECTRUM_PALETTE), CS-06 / CS-23 / CS-60 (dialog patterns), existing Keyboard shortcuts USER-FLAGGED register entry (pairs). Multi-phase task — design + scope decision is one phase; first batch (palette + Escape audit + keyboard shortcuts) one phase; broader rollout follows. **Risk:** screen reader support has the highest cost-per-platform; defer until the rest of the batch lands. |
| ✅ | 🟡 | **Modeless dialogs — relax CS-06 / CS-60 `grab_set` so the main window stays interactive (USER-FLAGGED, Phase 4al)** ✅ Resolved in Phase 4ao (CS-66). | USER-FLAGGED at end of Phase 4al (step 5 elicitation). User: "Is it possible for pop ups to not 'lock out' the main window? It would be nice sometimes to be able to have a pop up open (e.g. the Plot Settings window) while also being able to work on the main window." Today CS-06 / CS-23 / CS-60 enforce a modal contract on the Plot Settings dialog (`tk.Toplevel` with `transient(parent)` + `grab_set()` — `plot_settings_dialog.py:584`). The grab makes the main window non-interactive until the dialog is dismissed. **`StyleDialog` is already modeless per CS-05** (`style_dialog.py:553`: "Modeless: no transient / no grab_set"), so the pattern the user wants already exists in the codebase — Plot Settings just chose modal. The user's request is essentially: relax CS-06 / CS-60's modal lock to match CS-05's modeless behaviour. **Architecture proposal (lock pending):** drop `grab_set()` from `PlotConfigDialog.__init__`, keep `transient(parent)` so the dialog stays atop the main window but doesn't block input. The dialog already lives in `_open_dialogs` per-host registry (CS-06: one dialog per tab) — re-opening focuses the existing one rather than constructing a new one, which is exactly what modeless dialogs need. **Lock decisions for the implementing session:** (i) which dialogs are in scope — Plot Settings only (CS-06 / CS-60), or every CS-23 modal (project-load mismatch dialog, Save As, etc.)? (ii) what happens when the user mutates the underlying graph (e.g. adds a node) while Plot Settings is open — does the dialog's `_plots_by_role` need to refresh (pairs with the existing "plots_by_role frozen at open time" Claude-surfaced friction note from Phase 4ak), or is "re-open to refresh" still acceptable? (iii) does Cancel still revert via `_snapshot` (CS-23 semantic preserved), or does live-preview (USER-FLAGGED Phase 4ak register entry) become the natural follow-on? (iv) does the StyleDialog modeless precedent give us a clean playbook to copy, or are there CS-06-specific complications (e.g. cross-tab pending-edit state model from CS-60)? **Affected:** `plot_settings_dialog.py` (`grab_set()` call + module docstring), CS-06 / CS-23 / CS-60 lock relaxations, tests asserting modal behaviour (search `test_plot_settings_dialog.py` for any `grab_set`-aware assertion — likely none today), the load-time project-mismatch dialog (separate question — it SHOULD probably stay modal because it represents an error needing acknowledgement). Cross-refs CS-05 (existing modeless precedent), CS-06 (current modal lock), CS-23 (button row + Cancel semantics), CS-60 (unified PlotConfigDialog), the existing "Live-preview vs Apply button" register entry (pairs — modeless + live-preview together would be the most natural CS-06 evolution), and the Phase 4ak "plots_by_role frozen at open time" friction note (becomes urgent if dialog is modeless and graph mutations happen during open). Small phase if scoped to Plot Settings only (one-line change + test sweep); medium if scoped to all CS-23 modals; pairs with live-preview for a larger meta-UX phase. |
| ✅ | 🟢 | **Retire the global "Baseline curves" top-bar checkbox — per-node toggle has subsumed it (USER-FLAGGED, Phase 4al)** ✅ Resolved in Phase 4ao (CS-67). | USER-FLAGGED at end of Phase 4al (step 5 elicitation). User: "the baseline curves checkbox is probably no longer needed since we've moved that control to the data panel." Today `uvvis_tab.py:686` packs a `tk.Checkbutton("Baseline curves", variable=self._show_baseline_curves)` into the top bar; default off (CS-29). The renderer (`_redraw` line 2232) gates the dashed-baseline overlay loop on BOTH (a) the global `_show_baseline_curves` checkbox AND (b) the per-node `style["show_baseline_curve"]` (CS-36, default True). The per-node gate was added in Phase 4r alongside the data-panel surface for it — the user's observation is correct: the global checkbox is now redundant when every per-node row exposes the same control. Retiring the global gate is a small cleanup: delete the Checkbutton + the `_show_baseline_curves` BooleanVar + the outer `if self._show_baseline_curves.get():` guard in `_redraw`. The per-node `bn.style.get("show_baseline_curve", True)` filter inside the loop is the new single-source-of-truth. **Lock decisions for the implementing session:** (i) does the new default flip from "off globally, on per-node" to "on per-node out of the box" — i.e. baseline overlays appear immediately when a baseline is committed, with the user explicitly hiding via the per-node toggle? (today's off-by-default global gate hides ALL baselines until the user opts in.) Likely yes for consistency with the per-node default of True. (ii) does removal cascade through any test asserting the global checkbox's existence (`grep _show_baseline_curves test_uvvis_tab.py` first; likely a few tests need their setup updated). (iii) does the manifest (CS-46) carry the global `_show_baseline_curves` state? (no — it's tab-private UI state, not in `_plot_config` or the graph). (iv) does CS-29 invariant doc text need updating to reflect the per-node-only model? **Affected:** `uvvis_tab.py` (3 sites: BooleanVar init line 446, Checkbutton lines 686-691, `_redraw` gate line 2232); test_uvvis_tab.py (any test referencing `_show_baseline_curves` or `_baseline_curves_cb` needs its setup adjusted); COMPONENTS.md CS-29 / CS-36 invariant texts. Small phase — half a day at most. Cross-refs CS-29 (the original Phase 4o baseline overlay feature), CS-36 (the Phase 4r per-node toggle), Phase 4r friction context. **Quality-of-life win:** removes one top-bar widget AND clarifies that baseline visibility is per-node concern, not a global toggle. |

### Friction points carried forward from Phase 4r

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4r while landing the per-node baseline-
curve toggle (CS-36) and sweep-group member visual nesting
(CS-35). Items 1–4 were surfaced by Claude at end-of-session and
confirmed by the user verbatim. Items 5 + 6 are USER-FLAGGED
ground-up additions captured during step 5's elicitation; both
are recorded here AND as new register entries (the persistence
umbrella above; the floor-zero-as-fit-time-constraint entry above).
Item 7 is a process note. **Do not fix until the relevant
subsequent Phase 4 session.**

1. 🟡 ~~**Per-row `[~]` toggle has no tooltip.** CS-36's BASELINE-row
   toggle has no hover hint, so a new user has to infer "tilde =
   show baseline curve" from context. The natural attachment point
   is `_Tooltip` (CS-33), but that helper is private to
   `scan_tree_widget.py` until Phase 4q friction #3 promotes it to
   a shared utility module on first cross-module re-use. **Cross-
   ref:** see Phase 4q friction #3 above (canonical entry — still
   open) — promoting `_Tooltip` lets us add a "Show / hide baseline
   curve overlay" tooltip in the same session as the helper move,
   which keeps the tooltip pattern in exactly one place. Until
   then, the gesture is discoverable only via experimentation. No
   new register entry — folds into the `_Tooltip` promotion entry.~~
   ✅ Resolved in Phase 4t (CS-42) — `tooltip.py` extracted +
   `Tooltip(bc_btn, "Show / hide baseline curve overlay")` attached
   in `_populate_node_row` after the bc_btn pack.

2. 🟢 **`~` glyph is a tilde, not the dashed-line glyph it's
   meant to evoke.** CS-36's button reads `~` (when on) / `–`
   (when off) — the legend's `✓/–` vocabulary mapped onto a
   baseline-curve gesture. The dashed overlay it controls is
   visually `--`, not `~`, so a future restyle could pick a more
   evocative glyph (e.g. `╌` or `┄` from box-drawing extras). The
   integration test pins the literal `"~"` so any restyle is
   forced through a deliberate test update. Cosmetic; defer until
   a user reports the glyph is misleading. No register entry —
   noted here as a documentation-style review item; if it
   actually needs changing, a 🟢 register entry can be created.

3. 🟢 **`style["show_baseline_curve"]` has no project-save
   round-trip yet.** The new key is read/written at runtime via
   `set_style`, but the project-save layer doesn't exist in any
   form today. **Cross-ref:** the new register entry "Project +
   per-node persistence with manifest+sidecar+optional-blockchain-
   anchor architecture (USER-FLAGGED)" (Phase 4r) — Phase A of
   that ladder must serialise every style key, including this
   one, to round-trip the user's per-node hide choices. Process
   item: when Phase A lands, the test suite gains a new round-
   trip assertion that walks every node-style key (including
   `show_baseline_curve`) and confirms it survives a save+load
   cycle. No new register entry — folds into the persistence
   umbrella.

4. 🟢 **Legend toggle and baseline-curve toggle both render `–`
   when off.** Disambiguated by row position (legend on
   `side="right"`, baseline-curve on `side="left"`). The
   integration test `_bc_button_in` filters by side + text. If
   a third "off" toggle ever lands on either side, the
   disambiguation breaks. Mitigation when that happens: pick a
   distinct glyph for the new toggle, or attach a Tk widget
   `name=` so `winfo_children()` is searchable by name rather
   than by visual position. Documentation-style; no register
   entry.

5. 🔴 **Project + per-node persistence with manifest+sidecar+
   optional-blockchain-anchor architecture (USER-FLAGGED).** Ground-up
   USER-FLAGGED feature elicited during step 5. Subsumes the
   existing "Plot config + plot defaults persistence to
   project.json" register entry as Phase A of a four-phase
   ladder. **See the new register entry above** (in the Phase 4
   register table) for the full architecture decision lock —
   content-addressed manifest JSON + sidecar HDF5, single
   `protected: bool` header flag, OpenTimestamps anchoring for
   real blockchain protection without running a private chain,
   per-`OperationNode` `deterministic: bool` so non-MC outputs
   skip array storage and re-derive on load. Phase A is the
   natural next-up Phase 4 session.

6. 🔴 ~~**Floor-zero baseline as fit-time constraint, per mode
   (USER-FLAGGED).** Ground-up USER-FLAGGED feature elicited
   during step 5. **See the new register entry above** for the
   full architecture decision lock — universal "Floor at zero"
   panel checkbox + per-mode `compute_*` constrained-fit branch
   + `params["floor_zero"]: bool` for round-trip. **CS-24 lock
   relaxes specifically for adding the constrained-fit code path
   inside each `compute_*` function** — the user clarified that
   post-shift gives the wrong baseline shape for scattering at
   high energies, so the constraint must be enforced at fit
   time. Per-mode work items are independently shippable;
   suggested order is scattering → linear/poly → spline →
   rubberband.~~ ✅ Fully resolved across Phase 4s + Phase 4t
   (CS-37). Phase 4s shipped scattering / scattering+offset /
   rubberband (3/6 modes); Phase 4t shipped the remaining
   linear / polynomial / spline (3/6 modes) plus the disabled-
   state machinery (CS-43). The register entry above is now ✅.
   Supersedes the old "Scattering baseline floor-zero shift
   (CS-24 follow-up)" framing — that entry was reframed
   (priority dropped 🔴 → 🟡) as the scattering-specific
   fitted-offset variant `B(λ) = a + c·λ^(-n)`, ✅ shipped in
   Phase 4s (CS-38), composes orthogonally with the universal
   floor-zero constraint.

7. **Step 5 surfaces large architectural items, not just polish
   (process note).** Phase 4r's step 5 elicitation produced two
   ground-up USER-FLAGGED feature register entries (items 5 + 6
   above) that are larger than the implementation work of the
   phase that elicited them. The phase template handled this
   gracefully — the new register entries are written into
   BACKLOG and the work is deferred — but the ratio is worth
   noting: friction items 1–4 here are 4q-style "small things
   the implementing session noticed", and items 5 + 6 are
   "things the user flagged that have nothing to do with the
   phase that's closing". Both belong in the same friction
   list (the user-flagged additions are confirmation that
   step 5 surfaces strategic intent, not just clean-up); a
   future session structure rev could split them, but the
   single list reads fine in practice. Documentation-style;
   no register entry.

### Friction points carried forward from Phase 4s

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4s while landing the floor-zero scattering
constraint (CS-37), the scattering+offset composite mode (CS-38),
the fit-helper persistence path (CS-39), and the nm-range error
widening (CS-40). Items 1, 2, and 7 are USER-FLAGGED ground-up
elevations from step 5; items 3–6 were surfaced by Claude at
end-of-session and confirmed by the user. **Do not fix until
the relevant subsequent Phase 4 session.**

1. 🟡 ~~**Floor-zero toggle stays clickable for unsupported modes
   (USER-FLAGGED).** The universal "Floor at zero" Checkbutton is
   visible for every mode, but Phase 4s only shipped the
   constrained-fit code path for scattering / scattering+offset /
   rubberband. Linear / polynomial / spline raise a clear
   `ValueError` from the apply path when the toggle is on, but
   the toggle itself stays clickable, so the unsupported state is
   only discoverable by triggering the messagebox. **Cross-ref:**
   see the new register entry "Floor-zero toggle disabled state
   for unsupported baseline modes (USER-FLAGGED)" above for the
   architecture (`_FLOOR_ZERO_SUPPORTED_MODES` constant +
   `_refresh_floor_zero_state()` method called from the mode
   trace). The user has confirmed this should be elevated to a
   register entry. Folds into the open per-mode floor-zero
   register entry — the disabled-state polish ships alongside
   the next per-mode constrained-fit branch.~~ ✅ Resolved in
   Phase 4t (CS-43). Phase 4t shipped both the remaining 3/6
   modes (the disabled state never fires for any mode today)
   AND the disabled-state machinery as defensive scaffolding
   (`_FLOOR_ZERO_SUPPORTED_MODES = frozenset(BASELINE_MODES)`
   plus `_refresh_floor_zero_state()` wired to the mode trace
   plus the empty-string-sentinel Tooltip rotation pattern).

2. 🟡 **Scattering+offset and scattering should consolidate into
   one mode with an "Add offset" toggle (USER-FLAGGED).** CS-38
   shipped scattering+offset as a sixth `BASELINE_MODES` entry,
   but the user has flagged that the two-mode split is overkill
   — a single `scattering` mode with an offset Checkbutton
   (default off ⇒ a=0 ⇒ pure power law) is cleaner UX. **Cross-
   ref:** see the new register entry "Consolidate scattering+
   offset into scattering with optional offset toggle (USER-
   FLAGGED)" above for the architecture (collapse the two
   `compute_*` into one with `params["offset"]: bool`; reuse the
   shared `_scattering_window` / fit helpers from Phase 4s
   directly). The Phase 4s factoring is already the right shape
   for this consolidation.

3. 🟢 ~~**Hardcoded scan bounds `[0.1, 8.0]` in n="fit" branch.**
   Both `_scattering_fit` and `_scattering_offset_fit` call
   `scipy.optimize.minimize_scalar(..., bounds=(0.1, 8.0),
   method="bounded")`. Covers Rayleigh / Mie / dust comfortably,
   but a sub-Rayleigh tail (n ≈ 0.5) or an unusual fit could
   pin at the bound silently. **Cross-ref:** see the new
   register entry "Scattering n-fit scan bounds configurable
   via params" above. Defer until a fit pins at the bound in
   real use.~~ ✅ API resolved in Phase 4t (CS-41) —
   `params["n_bounds"]: tuple[float, float]` (default
   `(0.1, 8.0)`) overrides the bounded-scan range with
   `_resolve_n_bounds(params)` validation. Eight pure-module
   tests in TestNFitBoundsConfigurable. UI ⏳ deferred per the
   register entry above (the Tk row ships when a user reports
   a fit pinned at the bound).

4. 🟡 **`fit_scattering` runs the fit twice per apply
   (process note).** The apply site calls `compute()` and then
   `fit_scattering` for the diagnostic-key persistence; both
   re-run the same `_scattering_fit` internally. For 601-point
   spectra the cost is microseconds (closed-form closed-form
   linear LSQ; the n="fit" minimize_scalar is also negligible).
   Acceptable today; if a future op fits a parameter that's
   genuinely expensive (e.g. a global nonlinear solver across
   thousands of points), the right factoring is to thread the
   info dict back out of `compute_*` directly rather than re-
   running. Documentation-style; no register entry.

5. 🟢 **`c_fitted` / `a_fitted` aren't surfaced in any UI yet.**
   CS-39 records them on `OperationNode.params` but the
   ScanTreeWidget tooltip, export header, and StyleDialog don't
   read them. **Cross-ref:** see the open Diagnostic console /
   fitted-parameter panel register entry — that's the natural
   consumer. Phase 4m friction #2 is now struck through, but the
   surface-side work folds into the diagnostic-console intent.

6. 🟢 **SLSQP convergence-failure path uncovered by tests.**
   `_scattering_offset_fit` raises `ValueError("scattering+offset
   floor-zero fit did not converge: ...")` on `result.success ==
   False`, which the apply site surfaces via messagebox — but no
   test exercises that path against the actual optimiser (hard
   to construct a failure case for SLSQP with linear inequality
   constraints on a small problem). Defer until observed in
   real use. Documentation-style; no register entry.

7. 🔴 **OLIS .ols / .asc UV/Vis file format support
   (USER-FLAGGED).** Ground-up USER-FLAGGED feature elicited
   during step 5. Today's UV/Vis loader (`uvvis_parser.py`)
   doesn't handle OLIS instrument output. Blocks importing
   OLIS spectra. **See the new register entry above** for the
   full architecture — likely a new parser branch dispatched
   by filename suffix returning the same `wavelength_nm` /
   `absorbance` array pair. Implementation session blocks
   until OLIS sample files / format reference are available.

### Friction points carried forward from Phase 4t

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4t while landing the floor-zero
expansion to all six baseline modes (CS-37 expansion), the
n_bounds API hook (CS-41), the Tooltip module promotion
(CS-42), and the floor-zero disabled-state machinery (CS-43).
Items 1, 2, and 3 are USER-FLAGGED ground-up elevations from
step 5; items 4 + 5 are session-time discoveries Claude
flagged for confirmation. **Do not fix until the relevant
subsequent Phase 4 session.**

1. ~~🟡 **Per-row `[~]` toggle column alignment across all node
   types (USER-FLAGGED).** CS-36's BASELINE-row-only render of
   the `[~]/[–]` toggle leaves the right-sidebar columns
   misaligned across rows of different node types. The user
   has flagged that the toggle cell should be present for
   every row but greyed out when not applicable.~~ ✅ Resolved
   in Phase 4w (CS-48) — implemented as a fixed-width
   `row_toggle` Frame slot rather than a disabled Button on
   every row (cheaper, no "what does a disabled `[~]` mean?"
   UX confusion). See the canonical register entry above.

2. ~~🟡 **Second-derivative plot on separate right y-axis
   (USER-FLAGGED).** Today CS-20's `SECOND_DERIVATIVE`
   DataNode shares the absorbance y-axis with parent /
   NORMALISED / SMOOTHED / BASELINE nodes. Magnitudes are
   typically 1/100x to 1/1000x the parent absorbance, so the
   trace either dominates the y-range or is invisible. The
   user has flagged that it should render on a separate right
   y-axis (matplotlib `ax.twinx()`). **Cross-ref:** see the
   new register entry "Second-derivative plot on separate right
   y-axis (USER-FLAGGED)" above for the architecture (lazy
   `_ax2 = self._ax.twinx()`; per-NodeType default vs.
   per-style-key opt-in is a lock decision for the
   implementing session). Touches `uvvis_tab._redraw`,
   possibly `style_dialog` / `node_styles` for a new
   `style["y_axis"]` key, plus integration tests for the
   twin-axis presence + per-NodeType default.~~ ✅ Resolved in
   Phase 4u (CS-44). Broadened into a general multi-axis
   routing system per the user's "we may need to build in
   other secondary axes for other processes and might even
   need to add a third y-axis somehow in some cases"
   expansion: `_AXIS_ROLES` tuple, `_DEFAULT_Y_AXIS_BY_NODETYPE`
   per-NodeType table, `_NON_PRIMARY_Y_LABEL` x-unit-aware
   label table, `_TERTIARY_AXIS_OFFSET_FRAC` tunable constant,
   `_axes_by_role` lazy dict in `_redraw`. Per-style override +
   per-role y-limits deferred per Decisions 1 and 4 in the
   Phase 4u step-2 design lock. **Phase 4y note (CS-50):**
   Decision 1's per-style override hook is now ✅ Resolved
   (`style["y_axis"]` short-circuit + StyleDialog Combobox row).
   Decision 4 (per-role y-limit Tk vars) remains deferred.

3. 🟡 ~~**Top-bar Open File / Reload buttons belong to TDDFT
   only, not the app top level (USER-FLAGGED).** The top-bar
   buttons in `binah.py` only act on the TDDFT tab in practice
   but visually suggest cross-tab gestures.~~ ✅ Resolved in
   Phase 4ah (commit 3, F). Path (a) chosen — Open File +
   Reload removed from `binah._build_top_bar` and re-rendered
   inside the TDDFT tab's left sidebar at the top, above
   "Loaded Files". Flanking `ttk.Separator` removed. The `«`
   sidebar toggle + "TDDFT Section:" combobox + file label
   stay in the top bar this phase; a new 🟢 BACKLOG entry
   ("Sidebar `«` toggle + 'TDDFT Section:' combobox follow
   Open File / Reload into TDDFT chrome") queues the
   follow-up.

4. 🟢 **`_FLOOR_ZERO_SUPPORTED_MODES` is currently dead code.**
   CS-43's constant is initialised to `frozenset(BASELINE_MODES)`
   because Phase 4t shipped floor-zero for all six modes —
   the disabled branch never fires. Today it's defensive
   scaffolding that catches a future new mode added without
   floor-zero coverage. Three options weighed: (a) leave
   as-is + document as defensive (chosen this session); (b)
   rip it out and add it back when an unsupported mode lands
   (cleaner but loses the auto-grey safety net); (c) add a
   "remove if unused by Phase X" reminder. Sticking with (a)
   — the constant + refresh method is small (~25 lines); the
   removal cost when CS-43 stops earning its keep is also
   small. Documentation-style; no register entry.

5. 🟢 **Polynomial floor-zero needs z-space conditioning to
   converge.** Initial implementation used the raw
   `wl ∈ [200, 800]` Vandermonde for SLSQP and failed with
   "Inequality constraints incompatible" for order ≥ 2 (the
   columns span 6 orders of magnitude). Fix: solve in
   normalized `z = (wl - center) / half_range` with z-space
   polyfit for the initial guess; convert back to wl-space by
   evaluating + re-fitting via `np.polyfit`. Pattern worth
   noting for any future SLSQP-on-coefficients work in the
   codebase — wide-domain Vandermondes are the trap.
   Documentation-style; the conditioning is captured in CS-37
   under the polynomial bullet. No register entry.

### Friction points carried forward from Phase 4u

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4u while landing the multi-axis plot
routing (CS-44). Items 1–8 are USER-FLAGGED ground-up additions
captured during step 5's elicitation, all recorded here AND as
new register entries above (auditable provenance, baseline as
separate node + node algebra, multinode datasets, SVD &
chemometrics, dynamic sidebar width, detachable sidebars,
colour-blind palette, parallelization). Items 9–11 are
Phase-4u-specific friction points (the pre-existing %T-conversion
bug, the deferred per-style override, the future plot_widget
lift / hover readout). **Do not fix until the relevant
subsequent Phase 4 session.**

1. 🔴 ~~**Auditable provenance / process versioning for data
   processing protocols (USER-FLAGGED).** Implementation hash
   per OperationType stamped on the OperationNode at apply
   time; verified at project load. **Cross-ref:** see the new
   register entry for the full architecture; pairs with the
   persistence umbrella (Phase 4r friction #5).~~ ✅ Resolved
   in Phase 4v (CS-45) alongside persistence Phase A (CS-46).

2. 🔴 **Baseline as separate first-class node + node algebra
   (USER-FLAGGED).** New `NodeType.BASELINE_CURVE` holding just
   the curve; current BASELINE becomes a SUBTRACT-derived
   spectrum. Cross-dataset re-apply story unlocks instrumental-
   background workflows. ADD / SUBTRACT / SCALE / LINEAR_COMBO
   OperationTypes for composite spectra. **Cross-ref:** see the
   new register entry; collapses the existing 🟡 "Difference
   spectra" Phase 5 entry.

3. 🟡 **Multinode dataset import + combination (USER-FLAGGED).**
   New `NodeType.SPECTRUM_DATASET` aggregates child spectra +
   sweep axis. Pairs with the OLIS reader (multinode files) and
   the SVD entry (operates on the dataset). **Cross-ref:** see
   the new register entry.

4. 🟡 **Singular value decomposition + multinode chemometrics
   (USER-FLAGGED).** SVD / PCA / MCR-ALS panel on
   SPECTRUM_DATASET parents. Prerequisite: friction #3 above.
   **Cross-ref:** see the new register entry.

5. ~~🔴 **Dynamic sidebar auto-width for long labels — STILL OPEN
   (USER-FLAGGED, bumped from 🟡 in Phase 4v).** Auto-bump the
   PanedWindow sash position to fit the widest label-cell
   natural width.~~ ✅ Resolved in Phase 4w (CS-47 + CS-48). See
   the canonical register entry "Adjustable sidebar still not
   working" above for the full deliverables list.

6. 🟡 **Detachable sidebar windows (USER-FLAGGED).** Pop out
   left / right pane into a `tk.Toplevel` for multi-monitor
   workflows. **Cross-ref:** see the new register entry.

7. 🟡 **Colour-blind-safe palette (USER-FLAGGED).** Replace tab10
   with Wong / Okabe-Ito (or equivalent); CS-21 lock relaxes for
   this single-file change. **Cross-ref:** see the new register
   entry.

8. 🟢 **Parallelize heavy-compute paths (USER-FLAGGED).** Async
   compute façade for SVD / MCR-ALS / Apply-to-All / future MC
   bootstrap. Pairs with the diagnostic-console entry. Defer
   until a "UI froze" report. **Cross-ref:** see the new
   register entry.

9. 🟡 ~~**`_absorbance_to_y` corrupts SECOND_DERIVATIVE on %T y-unit.**
   Pre-existing bug surfaced while pinning the multi-axis tests.
   The conversion clips + maps `100·10^(-A)` which is meaningless
   for d²A values. Fix: gate the conversion on NodeType.~~ ✅
   Resolved in Phase 4ah (CS-59 Thread B, commit 4). Helper
   signature widened to `_absorbance_to_y(absorbance, y_unit,
   node_type)`; CS-55-frozenset gate short-circuits to
   pass-through for derivative-space NodeTypes (currently
   SECOND_DERIVATIVE). All three `_redraw` call sites updated.
   PEAK_LIST + BASELINE remain absorbance-space — byte-identical
   behaviour. 7 tests in `TestAbsorbanceToYNodeTypeGatePhase4ah`.
   Chain note: this also closes the Phase 4ac friction #1 chain
   (label-routing) ✅ resolved Phase 4ad CS-55 — Phase 4u #9 was
   the values half of that chain; both halves are now closed.

10. ~~🟢 **Per-style `y_axis` override hook + StyleDialog row.**
    Phase 4u Decision 1 deferred this — per-NodeType defaults
    only ship today. Reasonable scope for the same phase that
    needs Decision-2-style "send this UVVIS to the right axis"
    UX. **Cross-ref:** see the new register entry.~~ ✅
    Resolved in Phase 4y (CS-50). Default-None style key +
    `_resolve_y_axis_role` short-circuit + StyleDialog
    Combobox row. The canonical register entry above is now
    ✅; the smoothed-of-derivative misroute that Phase 4x
    friction #6 made newly reachable is closed too.

11. 🟢 **Plot_widget abstraction lift + hover readout for
    active axis + tertiary offset Plot Settings promotion.** Three
    follow-ups that naturally land in one phase, triggered when
    a second tab (XANES / EXAFS) needs multi-axis routing or
    when the two-axis use becomes ambient. **Cross-ref:** see
    the two new register entries (lift; hover readout).

### Friction points carried forward from Phase 4v

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4v while landing per-OperationType
implementation hash (CS-45) and persistence Phase A (CS-46).
Items 1–7 are USER-FLAGGED ground-up additions captured during
step 5's elicitation, all recorded here AND as new register
entries above. Items 8–13 are Phase 4v deferrals + carry-
forwards. **Do not fix until the relevant subsequent Phase 4
session.**

1. ~~🔴 **Drop CS-31 dedup + introduce user-driven node groups
   (USER-FLAGGED).** Today's "no duplicate apply" check
   (Phase 4p / CS-31) blocks legitimate re-applies; the auto-
   collapsed sweep groups (Phase 4q / CS-32) hide individual
   nodes so the user can't operate on them. The user has flagged
   that this makes workflows unusable. Drop CS-31; replace
   CS-32's automatic grouping with a user-driven "Combine
   selected → Group" gesture; introduce `NodeType.NODE_GROUP`
   for the explicit group container. Pairs with the existing
   🟡 multinode dataset register entry. **Cross-ref:** see the
   new register entry above.~~ ✅ Resolved in Phase 4ac
   (CS-54), parts (a) + (b). Re-applies + auto-grouping both
   gone; the Phase 4ad carry-forward is part (c) — user-driven
   `NodeType.NODE_GROUP` + "Combine selected → Group" gesture.
   See the canonical register entry above.

2. ~~🔴 **Adjustable sidebar still not working — bumped to 🔴
   (USER-FLAGGED).** See Phase 4u friction #5 above.~~ ✅
   Resolved in Phase 4w (CS-47 + CS-48). The Phase 4u
   canonical entry is now struck-through too; chain closed.

3. 🟡 **Trash can for discarded nodes (USER-FLAGGED).** New
   `NodeState.DISCARDED`; `discard_node` flips state instead of
   removing from the graph; a Trash pane lists discarded nodes
   with a Restore gesture. Pairs with the new sidecar GC entry
   (DISCARDED nodes' sidecars stay until the trash is emptied).
   **Cross-ref:** see the new register entry above.

4. 🟡 **Project-specific plot defaults + import from another
   project (USER-FLAGGED).** Three-layer defaults: factory →
   user → project. New "Import plot settings from another
   project…" gesture in the Plot Settings dialog reads another
   `.ptmg`'s `plot_defaults` block. Pairs with the resolved
   Phase 4l "Plot config + plot defaults persistence" register
   row (now ✅ via CS-46) — this entry is the next layer of
   plot-defaults shape. **Cross-ref:** see the new register
   entry above.

5. 🟡 **Refactor uvvis_tab.py — extract host shell into
   separate files; cross-tab generalization (USER-FLAGGED).**
   `uvvis_tab.py` is ~2000 LOC mixing five concerns; extract
   left-pane chrome / right-pane chrome / plot pane into
   reusable modules (`processing_pane.py` / `tab_shell.py` /
   `plot_pane.py`). Cross-tab generalization is a separate
   larger entry — the four tabs end up with a common base class.
   **Cross-ref:** see the new register entry above.

6. 🟡 **Plot data markers / points (USER-FLAGGED).** New style
   keys `style["plot_kind"]: "line" \| "markers" \| "both"`,
   `style["marker"]`, `style["marker_size"]`. StyleDialog
   universal section grows the UI. **Cross-ref:** see the new
   register entry above.

7. 🟢 **Test efficiency + per-phase metrics tracking
   (USER-FLAGGED).** Reuse a single Tk root across test classes;
   consolidate granular pure-module tests; start a per-phase
   metrics block (tests added, LOC delta, commit count, wall-
   clock estimate). Aggregate over five phases ⇒ visible trend.
   **Cross-ref:** see the new register entry above.

8. 🟡 **Re-run all changed ops at load (CS-45 follow-up).** The
   mismatch dialog ships with two buttons (Keep cached / Show
   details); the third "Re-run all changed" action from the
   Q2 lock is wired to a placeholder. Needs a workflow-replay
   mechanism (~150 LOC). **Cross-ref:** see the new register
   entry above.

9. 🟡 **Original instrument file persistence (Phase A
   follow-up).** Phase A round-trips parsed arrays via the
   sidecar but does NOT yet persist the original instrument
   file. Pairs with the OLIS reader register entry (binary
   `.ols` files MUST round-trip via this path).
   **Cross-ref:** see the new register entry above.

10. 🟢 **`.ptmg` zip-archive form (CS-46 follow-up).** Phase A
    ships directory-only; one-file zip-archive form is a small
    follow-up. **Cross-ref:** see the new register entry above.

11. 🟢 **Sidecar garbage collection across saves (CS-46
    follow-up).** Re-saves accumulate stale sidecars. One-line
    fix in `save_project`. **Cross-ref:** see the new register
    entry above.

12. 🟡 **`_restore_workflow_payload` only on UVVisTab — XAS /
    EXAFS / TDDFT need equivalents.** Fires when a non-UV/Vis
    tab migrates to the node model. **Cross-ref:** see the new
    register entry above.

13. 🟡 **Modal Tk messagebox during tests (resolved mid-Phase
    4v).** ~~The full suite stalled on every messagebox.showerror /
    showinfo / askyesno an apply-site error path produced —
    running locally meant clicking through each modal before the
    suite continued.~~ ✅ Resolved in Phase 4v via the new
    `_test_silence` module (silences every messagebox primitive
    at test-module load time); wired into `run_tests.py` and
    `test_persistence_phase_a.py`. Future test files that drive
    apply gestures should `from _test_silence import
    silence_all_messageboxes; silence_all_messageboxes()` at
    module top.

### Friction points carried forward from Phase 4w

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4w while landing the adjustable-sidebar
work (CS-47 + CS-48). Items 1–3 are USER-FLAGGED ground-up
additions captured during step 5's elicitation, all recorded
here AND as new register entries above. Items 4–6 are CS-47
follow-ups Claude flagged, items 7–8 are user-confirmed /
user-decided alongside the elicitation. **Do not fix until the
relevant subsequent Phase 4 session.**

1. ~~🔴 **Inter-panel parent-type acceptance gaps — baseline
   can't run on smoothed; smoothing can't run on
   second-derivative (USER-FLAGGED).** User reported during
   Phase 4w step 5: "Cannot do baseline correction from a
   smoothed spectrum. Cannot smooth derivative plots." Both
   are gaps in the panel-side `ACCEPTED_PARENT_TYPES` tuples
   (CS-22) — `BaselinePanel` is missing SMOOTHED, `Smoothing
   Panel` is missing SECOND_DERIVATIVE. The math works in
   both cases; only the parent-type gate is rejecting.
   **Cross-ref:** see the new register entry above for the
   architecture (widen the tuples; audit the other panels
   while in there). Workflow-blocking, hence 🔴.~~ ✅
   **Resolved in Phase 4x (CS-49).** `_BASELINE_ACCEPTED_PARENT_TYPES`
   widened to `(UVVIS, BASELINE, SMOOTHED)`; `SmoothingPanel.ACCEPTED_PARENT_TYPES`
   widened to add `SECOND_DERIVATIVE`. `_refresh_shared_subjects`
   walks both `_spectrum_nodes` and `_second_derivative_nodes`
   so derivative rows surface in the shared combobox.
   Audit pass result: NormalisationPanel / PeakPickingPanel /
   SecondDerivativePanel intentionally NOT widened (existing
   exclusions are deliberate per panel-side comments). Y-axis
   misroute for smoothed-of-derivative output deferred to the
   open T (per-style `y_axis` override hook) carry-forward —
   see Phase 4x friction #1 for the cross-ref.

2. 🟡 **Configurable secondary-plot pane layout — dock above /
   below main plot at adjustable fraction (USER-FLAGGED).**
   User has flagged that CS-44's `twinx()` overlay for
   SECOND_DERIVATIVE on the same canvas as the parent
   absorbance is suboptimal — a separate sub-pane below or
   above the main plot at ~1/3 height would be clearer.
   **Cross-ref:** see the new register entry above for the
   architecture (matplotlib `gridspec` swap + new Plot
   Settings keys). Pairs with the future plot_widget
   abstraction lift register entry (the layout state belongs
   in plot_widget once the lift lands).

3. 🟡 **UI lexicon / glossary doc — workflow vs project,
   sidebar vs sash, etc. (USER-FLAGGED).** Phase 4v renamed
   "Save Project" to "Save Workflow" but the surrounding
   docs still mix the two terms. The user has asked for a
   single canonical glossary. **Cross-ref:** see the new
   register entry above. Pairs with the upcoming Phase 4w
   bookkeeping audit — every doc edit touched by the
   project→workflow rename should align on the canonical
   term.

4. 🟢 **Cross-tab sash calibration is UVVisTab-only
   today.** CS-47's `_calibrate_sidebar_width` lives on
   `UVVisTab`; XAS / EXAFS / future Compare / Simulate tabs
   each have their own PanedWindow + ScanTreeWidget combo
   that doesn't auto-bump. Pairs with the existing 🟡
   "Refactor uvvis_tab.py — extract host shell" register
   entry: that refactor's right-pane chrome extraction is
   the natural home for the calibration mixin.
   **Cross-ref:** see the new register entry above.

5. 🟢 **Initial calibration uses an empty graph (USER-
   CONFIRMED).** CS-47 fires once on `after_idle` after
   construction; at that point no DataNodes exist, so
   `widest_label_pixel_width()` returns 0 and the sash falls
   through to the floor. After files load, the longer labels
   don't trigger a re-bump (the calibrated flag has flipped).
   User confirmed during step 5 that re-bumping on first
   NODE_ADDED is desirable. **Cross-ref:** see the new
   register entry above.

6. ~~🟢 **Static label-overhead estimate vs measured per-row
   overhead.** `_label_overhead_px` returns a static ~186 px
   sum-of-cell-mins + slack rather than measuring the actual
   per-row overhead (which varies with whether commit /
   swatch / leg / ls_canvas are packed). Drift is bounded at
   ≤30 px so the dynamic cap is in the right ballpark.
   Cheap polish; defer until a too-aggressive or too-loose
   truncation is reported. **Cross-ref:** see the new
   register entry above.~~ ✅ Resolved in Phase 4z (CS-51) for
   the optional-cell visibility axis (the dominant source of
   drift). The width-aware `_label_overhead_px(width=…)` now
   sums optional cells revealed at the current canvas width
   per CS-26's thresholds. Commit-cell (🔒, provisional only)
   drift remains as ≤22 px residual noise but is well within
   the existing slack term — defer until a real-world
   truncation regression is reported on a provisional row.

7. 🟢 **`_optional_row_widgets` inner type relaxed from
   `dict[str, tk.Widget]` to `dict[str, Any]` to accommodate
   the `Tooltip | None` slot.** Documentation-style note: the
   relaxation is well-scoped (only `label_tooltip` is the
   non-Widget value) but type-checker users may want a
   tighter `Union[tk.Widget, "Tooltip", None]` later. Defer
   until typing tooling shows up in CI; no register entry.

8. 🟢 **Sidebar minimum width pinned at 240 px deliberately
   matches the smallest responsive threshold rather than
   summing the always-visible per-cell mins (~186 px +
   padding).** The mismatch is intentional: tightening the
   floor below 240 would either (a) break the existing
   TestResponsiveCollapse threshold tests (which assert that
   at width 240+ the swatch maps) or (b) require widening
   those thresholds in lock-step. The current floor is the
   cheapest correct choice. Documentation-style; no register
   entry.

### Friction points carried forward from Phase 4x

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4x while landing the cross-type panel
parent acceptance widening (CS-49). Items 1–4 are USER-FLAGGED
ground-up additions captured during step 5's elicitation, all
recorded here AND as new register entries above. Item 5 is a
Claude-surfaced 🟢 polish item also recorded as a register entry.
Items 6–8 are documentation-style notes / cross-refs without
new register entries. **Do not fix until the relevant subsequent
Phase 4 session.**

1. ~~🟡 **Loaded Spectra responsive layout drops the ✕ when the
   swatch reappears at intermediate widths (USER-FLAGGED).**
   User reproduced during Phase 4x step 5: minimum sash width
   fits cleanly (no swatch, ✕ visible); incrementing the sash
   triggers swatch re-appearance, but ✕ falls off the right
   edge. Suspected root cause: `_label_overhead_px` (CS-47)
   doesn't account for the swatch's width when it returns at
   the same threshold, so the dynamic label cap stays generous
   and right-side cells get clipped. Pairs with **Phase 4w
   friction #6** (measure actual row overhead). User has
   explicitly flagged "tempted to leave it for a little
   while". **Cross-ref:** see the new register entry above for
   the architecture (three options for tying label cap to
   optional-cell visibility).~~ ✅ Resolved in Phase 4z (CS-51).
   Architecture (a) landed: `_label_overhead_px(width=…)`
   width-aware, summing optional cells revealed per CS-26 at
   the current canvas width; `_current_label_cap` forwards the
   width. The pure helpers `_compute_label_overhead_px` and
   `_visible_optional_cells_for_width` mirror
   `_apply_responsive_layout`'s reveal predicate so the cap and
   the row layout cannot drift. The bug-fix invariant is pinned
   by `test_cap_at_swatch_threshold_smaller_than_static_overhead_path`.

2. 🟡 **StyleDialog must surface ALL node-table parameters
   incl. label rename + tighten organisation for scale
   (USER-FLAGGED).** User has flagged that as more parameters
   land (label rename, plot_kind from the markers register
   entry, `y_axis` from carry-forward T), the gear-icon dialog
   will become unwieldy. Concrete first add: label-rename
   Entry (today the only path is the sidebar's CS-33
   double-click `_begin_label_edit`). **Cross-ref:** see the
   new register entry above. Pairs with friction #3 + #4 below
   (same window). **Phase 4aa partial:** the label-rename
   Entry shipped (CS-52, see register entry); the LabelFrame
   re-org + tabbed-shape lock question (decision (i)) stays
   open as the carry-forward — the canonical entry above is
   still ⏳, narrower in scope. ~~**Phase 4ab partial (CS-53):**
   the tabbed-shape half of decision (i) closed — the dialog
   body is now a `ttk.Notebook` with Tab 1 "Style" hosting
   today's universal + conditional sections verbatim and
   Tab 2 "Provenance" hosting the read-only ancestor walk
   (closes friction #3 below). The LabelFrame groupings
   half stays open; cross-ref carry-forward narrowed in the
   register entry above.~~

3. ~~🟡 **Per-node parameter window: add a Provenance tab
   (USER-FLAGGED).** User has asked for a more detailed
   provenance view than the right-sidebar's per-row history
   dropdown — second tab inside the StyleDialog, showing
   ancestor walk back to RAW_FILE / multi-input source, full
   op params per step, timestamps, engine + version,
   implementation hash (CS-45), status. **Cross-ref:** see the
   new register entry above. Pairs with #2 above (same dialog)
   and #4 below (same tab).~~ ✅ Resolved in Phase 4ab (CS-53).
   Tab 2 "Provenance" lands as a Canvas + Scrollbar pair with
   one block per ancestor; DISCARDED ancestors render dimmed
   grey (#888888) rather than filtered (Decision (iv)). Eager
   construction at `__init__`; refreshes on the five
   `_PROVENANCE_REFRESHING_EVENTS` graph events. 24 integration
   tests + 22 pure-helper tests pinning the contract.

4. 🟡 **"Add to graph" gesture from a node's Provenance tab
   (USER-FLAGGED).** Once #3 lands, the user has asked for a
   per-ancestor "Add to graph" gesture that materialises the
   historical ancestor as a live node without re-loading from
   disk. Concrete use case: surface a SMOOTHED node's parent
   UVVIS for side-by-side comparison without breaking the
   existing graph linkage. **Cross-ref:** see the new register
   entry above. Pairs with #3 above (same tab) and the open 🟡
   Trash can register entry (both surface "previously hidden"
   nodes). **Phase 4ab unblocks:** #3 landed; this entry is now
   actionable — the per-ancestor block already has a structural
   slot (parented to the same Frame the body Label uses) where
   the new button fits cleanly. Lock decisions (a) active-flip
   vs clone and (c) which graph event still need taking when
   the implementing session opens.

5. 🟢 **Visual cue for derivative entries in the shared
   subject combobox (CS-49 follow-up).** Surfaced by Claude.
   Now that SECOND_DERIVATIVE rows mix into the combobox
   alongside the four spectrum-shaped types, no per-row glyph
   distinguishes derivative entries from absorbance-domain
   spectra. Cheap one-liner (`d² ` prefix in
   `_refresh_shared_subjects`). **Cross-ref:** see the new
   register entry above. Defer until the user reports actual
   confusion picking among mixed entries; the audit-stability
   test `test_shared_combobox_orders_spectrum_then_derivative`
   already pins the spectrum-first ordering so visual scanning
   is left-to-right consistent.

6. ~~🟢 **Smoothed-of-derivative output misroutes to the primary
   axis (CS-49 + CS-44 interaction, USER-NOTED).** The
   `SMOOTHED` output of "smooth a SECOND_DERIVATIVE" is routed
   by `_DEFAULT_Y_AXIS_BY_NODETYPE[SMOOTHED] == "primary"`
   under CS-44. Visually it stacks on the absorbance axis even
   though its values are smoothed d²A/dλ². Already covered by
   the open carry-forward register entry **T (per-style
   `y_axis` override hook + StyleDialog row)** from Phase 4u
   friction #10 — Phase 4x makes this misroute newly
   reachable, so T's priority arguably ticks up. User has
   acknowledged that T is the right next session's intent.
   No new register entry; cross-ref only.~~ ✅ Resolved in
   Phase 4y (CS-50). The cross-typed-Apply inheritance hook
   in `SmoothingPanel._apply` writes
   `style["y_axis"] = parent_effective_role` on the new
   SMOOTHED node when (and only when) the parent's effective
   role differs from SMOOTHED's NodeType-default — so a
   smoothed-of-derivative output now lands on "secondary"
   alongside its parent. Pinned by
   `test_smoothed_of_second_derivative_inherits_secondary` in
   the new `TestUVVisTabPhase4yCrossTypedInheritance` class.

7. 🟢 **`_BASELINE_ACCEPTED_PARENT_TYPES` is the only
   acceptance tuple still living on `UVVisTab` rather than its
   panel.** The other four panels carry `ACCEPTED_PARENT_TYPES`
   as a class constant; the inline baseline section's tuple is
   an instance attribute on the host. The friction note from
   Phase 4k friction #6 already documents this drift ("when
   the inline section is extracted into a `BaselinePanel`
   widget, `_BASELINE_ACCEPTED_PARENT_TYPES` should join the
   public `ACCEPTED_PARENT_TYPES` API"). Phase 4x widened the
   inline tuple in place — cheap-correct but reinforces the
   carry-forward. Cross-ref to **Phase 4k friction #6**; no
   new register entry.

8. 🟢 **"Tuple" is a Python-ism that leaks into our docs
   (USER-NOTED, lexicon candidate).** During Phase 4x step 5
   the user asked for clarification on what "tuple" means
   (Python: a fixed, ordered sequence in parentheses, vs a
   list which is mutable; we use it for the ACCEPTED_PARENT_TYPES
   class-policy that shouldn't change at runtime). The
   carry-forward **C (UI lexicon doc)** register entry is the
   right home — when `LEXICON.md` lands, the seed entries
   should include "tuple" alongside the UI terms. Cross-ref
   only; no new register entry.

### Friction points carried forward from Phase 4y

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4y while landing the per-style `y_axis`
override hook + StyleDialog Combobox row (CS-50 / carry-forward
T from Phase 4u Decision 1). Items 1–3 are Claude-surfaced
during step 5 and carry fresh register entries above. Items 4–6
are documentation-style notes / cross-refs without new register
entries. **Do not fix until the relevant subsequent Phase 4
session.**

1. ~~🟡 **Y-axis Combobox row appears on non-UVVis StyleDialog
   instances (Claude-surfaced).** The CS-50 "Y axis:" row
   landed in the *universal* section so it appears for every
   NodeType — XANES / EXAFS / TDDFT / FEFF_PATHS / BXAS_RESULT
   / DEGLITCHED / AVERAGED — even though only `uvvis_tab._redraw`
   reads the override today. Persisted `style["y_axis"]` is
   harmless on non-UVVis nodes but the user-visible Combobox
   is a misleading affordance there. Pairs with the open
   "Lift multi-axis routing to plot_widget.py" carry-forward —
   once that lifts, the affordance becomes meaningful for
   every tab. **Cross-ref:** see the new register entry above.~~
   ✅ Resolved in Phase 4aa (CS-52). Path (a) (NodeType-gate)
   landed: `_Y_AXIS_VISIBLE_NODETYPES` mirrors the routing
   table exactly; the row is now suppressed on the seven
   non-routing NodeTypes. Drift test
   `test_y_axis_visible_node_types_match_routing_table` pins
   the gate so a future routing-table widening cannot
   silently reintroduce the misleading affordance.

2. ~~🟢 **Per-NodeType primary y-axis label gap when override
   reroutes nodes (Claude-surfaced).** Two minor surprises with
   the CS-50 hook: (a) UVVIS overridden to "secondary" leaves
   the secondary axis unlabelled (no `(UVVIS, x_unit)` entry
   in `_NON_PRIMARY_Y_LABEL`); (b) SECOND_DERIVATIVE overridden
   to "primary" keeps the absorbance label, which is wrong for
   d²A values. Reasonable degradation today (the user
   explicitly chose the override) but a future polish could
   widen the label table to cover non-default routings. Cross-
   refs Phase 4u friction #9 (`_absorbance_to_y` corrupts d²A
   on %T) — both surface "primary axis assumes absorbance
   values" mistakes. **Cross-ref:** see the new register entry
   above.~~ ✅ Resolved in Phase 4ad (CS-55). The user bumped
   this 🟢 → 🔴 at end of Phase 4ac with end-to-end reproduction;
   Phase 4ad landed `_resolve_y_axis_label(node_type, x_unit,
   y_unit)` plus the `_ABSORBANCE_SPACE_NODETYPES` /
   `_ABSORBANCE_Y_LABEL` companions. Both surprises closed:
   UVVIS-on-secondary now labels secondary "Absorbance"; d²A-on-
   primary now labels primary "d²A/dλ²". Cross-ref Phase 4u
   friction #9 stays open — that's the value-corruption half
   (`_absorbance_to_y` clip), independent of label routing.

3. 🟢 **DRY cross-typed-Apply y_axis inheritance helper (CS-50
   architectural debt, Claude-surfaced).** The inheritance
   block in `SmoothingPanel._apply` (set `style["y_axis"]` on
   a new node when its NodeType-default differs from the
   parent's effective role) is the only consumer today.
   Refactor into `node_styles.inherit_y_axis_for_cross_typed_apply`
   when a second cross-typed-Apply path lands so the
   abstraction has two consumers. **Cross-ref:** see the new
   register entry above.

4. 🟡 **Phase 4u friction #9 (`_absorbance_to_y` corrupts d²A
   on %T) is now newly reachable from the UI.** Pre-CS-50 the
   bug required hand-editing a project file's style dict to
   land a SECOND_DERIVATIVE on primary; post-CS-50 the
   StyleDialog Combobox makes it a single click. Priority of
   the canonical Phase 4u friction #9 register entry arguably
   ticks up; defer the fix until either a user reports
   nonsense %T values or the next phase that touches the
   per-node loop's y-unit branch. Cross-ref to **Phase 4u
   friction #9**; no new register entry — that entry already
   exists and Phase 4y added a note inline.

5. 🟢 **`_apply_baseline()` tuple return shape isn't pinned
   in COMPONENTS.md (Claude-surfaced doc-debt).** While
   writing the Phase 4y baseline-overlay test I tripped on
   `_apply_baseline()` returning `(op_id, baseline_id)` —
   the panel-`_apply` shape is consistent across all five
   panels (NormalisationPanel / SmoothingPanel /
   PeakPickingPanel / SecondDerivativePanel / inline baseline)
   but isn't called out in CS-15 / CS-16 / CS-18 / CS-19 /
   CS-20 docstrings. Minor; fold into the next phase that
   touches CS-15's docstring or a future "panel apply
   contract" CS section. No new register entry; cross-ref
   only.

6. 🟢 **Combobox "(default)" label could be more
   descriptive (Claude-surfaced polish).** Phase 4y Decision
   (ii) locked the literal-None semantics; the Combobox label
   "(default)" is technically accurate but a new user may not
   immediately understand why their per-NodeType routing
   choice isn't visible. A future polish could spell it
   "(default — follow type)" or "follow type default" so the
   semantics surface in the dropdown. Defer until a usability
   report. No new register entry; cross-ref only.

### Friction points carried forward from Phase 4z

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4z while landing the width-aware label-
cell overhead helper (CS-51) — closing both Phase 4x friction
#1 (USER-FLAGGED) and Phase 4w friction #6. All three items
below are Claude-surfaced 🟢 polish notes flagged during step 5;
none have new register entries (the user explicitly accepted no
new items at step 5). **Do not fix until the relevant subsequent
Phase 4 session.**

1. 🟢 **`_calibrate_sidebar_width` still uses the no-args
   (always-visible-only) overhead path (Claude-surfaced).** The
   one-shot sash calibration calls `self._label_overhead_px()`
   without a width arg, so the calibrated target reflects the
   always-visible cluster only. At the calibration target width
   itself the optionals (swatch / leg / ls_canvas) WILL be
   visible, so the calibration may undershoot the ideal sash
   width by up to 84 px (sum of all three optional cell mins).
   `_SIDEBAR_MAX_CALIBRATED_PX = 480` usually swallows the
   shortfall; not a bug today. Cheap follow-up: use a fixed-
   point or single-pass derivation that targets a width where
   the optionals will be visible. No new register entry; defer
   until a "calibration too narrow" regression is reported.

2. 🟢 **Floor clamping at narrow widths masks the bug-fix
   visual cue between 239→240 px (Claude-surfaced).** At those
   widths both the static and dynamic `_label_char_capacity`
   results clamp to `_LABEL_CHAR_FLOOR = 8`, so the painted
   label is identical at 239 and 240. The right-side cells are
   no longer clipped (the user-flagged bug IS fixed) because
   the cap correctly accounts for the swatch's overhead in the
   dynamic path — but the visible label-truncation cue only
   fires at the leg / ls_canvas boundaries (279→280, 319→320).
   Cosmetic: a future polish could lower `_LABEL_CHAR_FLOOR`
   to 6 (or fold the floor into the threshold-derivation logic
   so it scales with width). No new register entry.

3. 🟢 **`_OVERHEAD_SLACK_PX = 30` is still a heuristic
   constant (Claude-surfaced).** Lifted from Phase 4w as-is.
   Now that the per-cell-vocabulary axis is honest, the
   inter-cell padding slack could be tightened (Tk's pack
   `padx=2` etc. sums to less than 30 px in practice). Cheap
   follow-up: instrument one paint cycle, measure
   `row.winfo_reqwidth() - sum(child.winfo_reqwidth())`
   across the always-visible set, pin the constant to the
   measurement. No new register entry; defer until either too-
   tight or too-loose truncation surfaces in real use. Closes
   the residual portion of the now-✅ Phase 4w friction #6
   that wasn't addressed by the per-cell-vocabulary path.

### Friction points carried forward from Phase 4ab

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4ab while landing the StyleDialog
Notebook restructure + Provenance tab (CS-53) — closing
Phase 4x friction #3 (USER-FLAGGED) in full and the
tabbed-shape half of Phase 4x friction #2's lock decision (i).
All six items below are Claude-surfaced 🟢 polish notes flagged
during step 5; the user invoked `/loop continue Phase 4ab` as
the step 5 answer (no new items elicited). **Do not fix until
the relevant subsequent Phase 4 session.**

1. 🟢 **Mouse-wheel scrolling not bound to the Provenance Canvas
   (Claude-surfaced).** Standard tkinter Canvas+Scrollbar pattern
   — wheel events do not auto-route to the Canvas's `yview_scroll`.
   The user has to drag the scrollbar manually for long ancestor
   chains (or has no scrolling at all if their input device lacks
   a draggable scrollbar surface). Cheap one-liner fix in
   `_build_provenance_tab`: `canvas.bind_all("<MouseWheel>", lambda
   e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))`. The
   `bind_all` vs `bind` decision matters — `bind_all` lets the
   wheel scroll regardless of widget focus, but it also captures
   wheel events anywhere in the dialog (including over the Style
   tab's sliders, where wheel events should change slider value).
   A safer scoped binding is `canvas.bind("<Enter>", _bind_wheel)`
   + `canvas.bind("<Leave>", _unbind_wheel)`. Defer until the user
   actually hits a long enough chain to need it.

2. 🟢 **Implementation hash truncated to 12 chars with no way to
   see the full digest (Claude-surfaced).** A user investigating
   a project-load hash mismatch warning needs the full 64-char
   sha256 to compare against persisted manifests, but the
   Provenance tab only shows the prefix. Cheap polish: hover
   tooltip via `tooltip.Tooltip` (CS-42) showing the full hash;
   click-to-copy via `dlg.clipboard_clear() + clipboard_append`.
   Defer until the user reports a real verification workflow
   that needs the full digest.

3. 🟢 **OperationNode block does not show parent input_ids
   (Claude-surfaced).** For multi-input ops (AVERAGE / DIFFERENCE)
   the visual association of "which two parents combined into
   this op" is implicit in the topo sort — the user has to count
   blocks above the op and trust the order. Adding a `parents:
   [id-a, id-b]` line to the body block would make multi-input
   forks obvious. The block already has the structural slot (the
   Courier body Label). Defer until AVERAGE / DIFFERENCE op land
   and the user actually sees a multi-input fork in their
   workflow — current single-parent chains don't motivate the
   change.

4. 🟢 **Self-keystroke rename leaves the Provenance bottom-of-
   chain block stale during typing (Claude-surfaced).** The
   `_on_graph_event` `_suspend_writes` guard skips
   `_refresh_provenance` for events the dialog itself fires; the
   trade-off accepted in Phase 4ab is "stale display during
   typing" over "rebuild Provenance on every keystroke". A user
   who notices might be confused. A cheap targeted fix lives in
   `_refresh_label`: after pushing the new label into the Entry
   (under `_suspend_writes=True`), also call `_refresh_provenance`
   directly so the bottom-of-chain block updates without the full
   guard-bypass. This special-cases the dialog's own node label
   without affecting the keystroke perf trade for everything else.
   Defer until a user reports the staleness as confusing.

5. 🟢 **Provenance refresh fires for graph events on any node,
   not just ancestors of the dialog's own node (Claude-surfaced).**
   For a graph with many disjoint chains the dialog rebuilds its
   tab on label changes / state changes / node adds for nodes
   that aren't even in the displayed walk. Per-rebuild cost is
   small (BFS bounded by graph size; widget tree of a few dozen
   widgets), so this hasn't been observed as a problem. Cheap
   optimisation: cache the ancestor-id set at construction time
   in `self._ancestor_ids: frozenset[str]`, refresh it inside
   `_render_provenance_blocks` after each rebuild, and gate the
   refresh in `_on_graph_event` on `event.node_id in
   self._ancestor_ids`. Defer until measurable.

6. 🟢 **No "as of" / "last updated" indicator on the Provenance
   tab (Claude-surfaced).** If a project loads via `restore_workflow_payload`
   (CS-46) or a graph mutates while the dialog is closed,
   Provenance content updates only when the dialog re-opens. No
   visible cue tells the user "this view was last refreshed at
   HH:MM:SS" — they have to trust that the rebuild fired on
   `GRAPH_LOADED` (it doesn't currently — that event is not in
   `_PROVENANCE_REFRESHING_EVENTS`). Two-part fix when this
   matters: (a) add `GRAPH_LOADED` to the refreshing-events set;
   (b) add a small "as of HH:MM:SS" Label below the per-ancestor
   blocks. Defer until persistence-driven workflows surface the
   inconsistency in real use.

---

### Friction points carried forward from Phase 4aa

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4aa while landing the StyleDialog y-axis
visibility predicate + label-rename Entry (CS-52) — closing
Phase 4y friction #1 in full and the "first concrete add" half of
Phase 4x friction #2 (USER-FLAGGED). All six items below are
Claude-surfaced 🟢 polish notes flagged during step 5; none have
new register entries (the user explicitly accepted no new items
at step 5). **Do not fix until the relevant subsequent Phase 4
session.**

1. ~~🟢 **"Tighten organisation for scale" half of Phase 4x
   friction #2 stays open (Claude-surfaced).** Phase 4aa
   landed only the "first concrete add" — the label-rename
   Entry. The LabelFrame re-org pass (Appearance / Legend /
   Fill / Per-type groupings) and the open lock decision (i)
   on tabbed shape vs single-pane are deferred. The canonical
   Phase 4x friction #2 register entry stays ⏳ with an inline
   "Phase 4aa partial" note; will likely combine with the
   Phase 4x friction #3 + #4 register entries (Provenance tab
   + "Add to graph" gesture) in a future intent — all three
   live in the same window and the tabbed-shape question is
   the natural pivot. **Cross-ref:** Phase 4x friction #2 + #3
   + #4 canonical register entries above.~~ ✅ Partly resolved
   in Phase 4ab (CS-53). The tabbed-shape half of lock
   decision (i) closed — `ttk.Notebook` with Style + Provenance
   tabs landed (closes Phase 4x friction #3 in full). The
   LabelFrame groupings half is still ⏳ but is no longer
   coupled to the pivot question — the Notebook restructure is
   independent of any future Identity / Appearance / Legend /
   Fill grouping pass. Carry-forward narrowed; canonical entry
   above (Phase 4x friction #2) carries the remaining scope.

2. 🟢 **Live-trace label commits = `NODE_LABEL_CHANGED` per
   keystroke (Claude-surfaced).** The Phase 4aa label-rename
   Entry uses `trace_add('write')` so every keystroke commits
   through `graph.set_label`, firing one event per character.
   Sliders behave the same way under the universal-section
   live-write convention (every drag-tick fires
   `NODE_STYLE_CHANGED`), so the convention is established —
   but for a longer label string the volume is more
   intentional. Could add a debounce (e.g. commit-after-200ms-
   idle) or commit-on-blur if the noise becomes a problem.
   Phase 4aa accepted the trade as deliberate (avoids the
   "type, forget Enter, close, no save" footgun); revisit if
   a user reports event-bus noise during typing.

3. 🟢 **Two rename gestures coexist — sidebar's CS-33 double-
   click + StyleDialog "Label:" Entry (Claude-surfaced).**
   Both gestures route through `graph.set_label`, so
   round-trip behaviour is identical (no validation, accept
   any string). Two paths to the same change is cheap UX
   debt; a future "tighten organisation" pass might prune the
   sidebar gesture if the dialog Entry feels first-class.
   Today both are first-class; cross-ref to Phase 4x friction
   #2 (the same canonical register entry that motivated the
   Entry).

4. 🟢 **`_Y_AXIS_VISIBLE_NODETYPES` is structurally coupled to
   `_DEFAULT_Y_AXIS_BY_NODETYPE` (Claude-surfaced doc-debt).**
   The two sets are literally identical today (the drift test
   pins them). A future cleanup could replace the explicit
   constant with `frozenset(uvvis_tab._DEFAULT_Y_AXIS_BY_NODETYPE.keys())`
   computed at import time, eliminating the constant + the
   drift test in one pass. Trade-off: the explicit constant
   is greppable + fast-fails on drift via the pinning test;
   the computed expression adds an import-time `uvvis_tab`
   dependency to `style_dialog.py`. Stuck with explicit +
   drift-test for now. No register entry.

5. ~~🟢 **Phase 4y friction #2 (per-NodeType primary y-axis
   label gap) is now narrower in scope but still open
   (Claude-surfaced cross-ref).** With the Phase 4aa
   visibility gate, the override Combobox is only reachable
   for the six routing NodeTypes — but the friction's two
   cases (UVVIS overridden to "secondary" leaves the
   secondary axis unlabelled; SECOND_DERIVATIVE overridden to
   "primary" keeps the absorbance label, wrong for d²A
   values) still apply. Phase 4aa did not touch
   `_NON_PRIMARY_Y_LABEL`. **Cross-ref:** Phase 4y friction
   #2 canonical register entry "Per-NodeType primary y-axis
   label for override use case" stays open; no new register
   entry.~~ ✅ Resolved in Phase 4ad (CS-55) — same fix as
   Phase 4y friction #2 above. `_resolve_y_axis_label` is the
   new entry point; CS-44 invariants on `_NON_PRIMARY_Y_LABEL`
   and `_resolve_non_primary_y_label` all preserved.

6. 🟢 **Cancel always re-emits the snapshot label (Claude-
   surfaced).** `_do_cancel` calls
   `_write_label_partial(self._snapshot_label)`
   unconditionally; `set_label` early-returns when old==new
   so the call is a no-op when the user never renamed, but
   it costs a function dispatch on every Cancel. Cheap to
   gate behind an inequality check; not worth the diff for
   cosmetic gain. No register entry.

### Friction points carried forward from Phase 4ac

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4ac while landing the CS-31 dedup drop +
CS-32 sweep auto-grouping removal (CS-54) — closing the (a) + (b)
parts of Phase 4v friction #1 (USER-FLAGGED) and unblocking the
USER-FLAGGED Phase 4ad intent. Items 1–3 are USER-FLAGGED ground-
up additions captured during step 5's elicitation, all recorded
here AND as new (or bumped) register entries above. Items 4–6 are
Claude-surfaced 🟢 polish notes flagged during step 5; none have
new register entries beyond the cross-refs noted. **Do not fix
until the relevant subsequent Phase 4 session.**

1. ~~🔴 **Y-axis label routing follows axis side, not axis role —
   wrong / missing labels when primary/secondary roles are
   swapped (USER-FLAGGED, bumped 🟢 → 🔴 in Phase 4ac).** User
   reproduced end-to-end at end of Phase 4ac (step 5
   elicitation): placing Absorbance on the secondary axis and a
   derivative on the primary axis leaves the Absorbance label
   on the *left* axis (because the renderer's primary-axis
   label is hard-coded to "Absorbance / Transmittance (%)") and
   the right axis appears unlabelled. CS-44's
   `_NON_PRIMARY_Y_LABEL` table only carries
   SECOND_DERIVATIVE entries; with the CS-50 override hook
   landed, the table no longer covers every reachable role ×
   NodeType combination. **Cross-ref:** the canonical "Per-
   NodeType primary y-axis label …" register entry above is
   the single home (newly bumped to 🔴 USER-FLAGGED with the
   user-reproduction context). Pairs with Phase 4u friction #9
   (`_absorbance_to_y` corrupts d²A on %T) — both surface
   "primary axis assumes absorbance values" mistakes.~~ ✅
   Resolved in Phase 4ad (CS-55) — option (b) variant of the
   three architecture options landed; see the canonical register
   row above for full deliverables. Phase 4u friction #9 (value-
   corruption half) stays open as a separate fix.

2. ~~🟡 **Configurable plot grid colour (USER-FLAGGED).** User
   has asked for a per-plot grid-colour picker. Today the grid
   renders at the matplotlib default (light grey) with no user
   control. **Cross-ref:** see the new register entry above.
   Pairs with #3 below (both surface in the Plot Settings →
   Appearance section).~~ ✅ Resolved in Phase 4ae (CS-56) —
   new `"grid_color"` factory key + colour-swatch row in
   Appearance + renderer reads through. See the canonical
   register entry above for full deliverables.

3. ~~🟡 **Default to inward-facing axis ticks (USER-FLAGGED).**
   User has asked that the factory default for tick direction
   flip from `"out"` to `"in"`. Infrastructure already exists
   in `plot_settings_dialog._FACTORY_DEFAULTS["tick_direction"]`;
   the change is a one-line factory-default flip plus an audit
   pass for existing user `~/.binah_config.json` files. **Cross-
   ref:** see the new register entry above. Pairs with #2
   above.~~ ✅ Resolved in Phase 4ae (CS-56) — factory-default-
   only flip per decision lock (i); no migration needed.
   `plot_widget._tick_direction` already defaulted to `"in"` so
   question (iii) collapsed.

4. ~~🟡 **Phase 4ad: NodeType.NODE_GROUP + user-driven "Combine
   selected → Group" gesture (carry-forward from Phase 4v
   friction #1 part (c)).** Phase 4ac shipped parts (a) + (b)
   of the original Phase 4v friction #1 architecture; part (c)
   — the explicit user-driven group container — is the natural
   Phase 4ad intent. Lock decisions still pending: (i) gesture
   style (context-menu / left-pane button / drag-and-drop), (ii)
   nested groups, (iii) where the "Ungroup" gesture lives, (iv)
   does Phase 4ad reuse `_SWEEP_MEMBER_INDENT_PX = 16` (CS-35
   constant survives Phase 4ac for exactly this reason) or pick
   a fresh indent? **Cross-ref:** the canonical "Drop CS-31 +
   introduce user-driven node groups" register entry above
   carries the architecture; the Phase 4ac partial note narrows
   the carry-forward to part (c).~~ ✅ Resolved in Phase 4af
   (CS-57) — the intent slipped two phases (Phase 4ad shipped
   CS-55's label routing; Phase 4ae shipped CS-56's Appearance
   pass) but landed in Phase 4af with all four lock decisions
   taken: (i) context-menu + left-pane footer button (both
   surfaces); (ii) flat only (no nesting); (iii) ungroup via
   context-menu + inline ✕ on the group row; (iv) reuse
   `_SWEEP_MEMBER_INDENT_PX = 16` (CS-35 lock survives,
   purpose realised). See the canonical register entry above
   for full deliverables.

5. ~~🟢 **`_SWEEP_MEMBER_INDENT_PX` is a dormant constant
   awaiting Phase 4ad re-use (Claude-surfaced).** The constant
   + the `indent_px=0` kwarg on `_build_node_row` survive Phase
   4ac on the bet that Phase 4ad's user-driven NODE_GROUP
   container will reuse them for group-member visual nesting
   (CS-35 lock survives). If Phase 4ad lands a different indent
   shape (e.g. tree-style left-rule lines instead of pure pack
   padding), the constant becomes dead weight — re-evaluate at
   the close of Phase 4ad: keep, retune, or remove. No new
   register entry; folds into the Phase 4ad intent.~~ ✅
   Resolved in Phase 4af (CS-57) — the constant is now LIVE:
   `_rebuild` calls `_build_node_row(member, indent_px=_SWEEP_MEMBER_INDENT_PX)`
   for every member of an expanded NODE_GROUP. The CS-35 lock
   on the constant value + `_build_node_row(indent_px=0)`
   kwarg signature carries forward into Phase 4af's lock list.

6. 🟢 **No "which one is which?" cue when N identical
   PROVISIONAL siblings render (Claude-surfaced).** With auto-
   grouping gone, clicking Apply 5x with identical params
   produces 5 PROVISIONAL siblings rendered as 5 separate full-
   chrome rows. They look identical except for the underlying
   node id (which the user can't see). Polish-level: rendering
   an ordinal marker like `(1)`, `(2)` … in the label, or a
   subtle colour/badge cue, would help the user tell them
   apart. Defer until reported in real use; CS-33 label-
   truncation already pins the no-suffix-pollution invariant
   for the regular case. No register entry.

### Friction points carried forward from Phase 4ad

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4ad while landing the role-agnostic
y-axis label helper (CS-55) — closing Phase 4ac friction #1
(USER-FLAGGED 🔴) and the Phase 4y / Phase 4aa cross-refs to
the same root issue. The user accepted no new items at step 5
("nothing to add at the moment"); all five items below are
Claude-surfaced 🟢 polish notes flagged during step 5; none
have new register entries. **Do not fix until the relevant
subsequent Phase 4 session.**

1. 🟢 **First-node-on-primary wins the label when multiple
   NodeType classes coexist on primary (Claude-surfaced).** The
   `first_node_type_per_role` map records the FIRST NodeType
   to land on a role; when both UVVIS (default routing) and a
   user-overridden SECOND_DERIVATIVE coexist on primary, the
   UVVIS landed first so primary stays labelled "Absorbance"
   — under-informative for the derivative-on-primary half.
   The integration test
   `test_second_derivative_on_primary_labels_primary_with_derivative`
   documents this as intentional behaviour. A future polish
   could (a) split the label e.g. "Absorbance / d²A/dλ²" when
   the role hosts multiple NodeType classes; (b) prefer the
   most recently added; (c) prefer the explicitly-overridden
   NodeType. Defer until reported. No register entry.

2. 🟢 **`_NON_PRIMARY_Y_LABEL` is now misnamed
   (Claude-surfaced doc-debt).** Post-CS-55 the table is
   consulted for both primary and non-primary derivative-space
   labels. The name worked under CS-44 because the table only
   fed the non-primary post-loop. A rename to
   `_DERIVATIVE_Y_LABEL` or `_Y_LABEL_BY_NODETYPE_AND_X_UNIT`
   would read cleaner, but CS-44 locks the name by tests
   pinning the constant. A future CS-N can relax the name
   lock; cheap rename. No register entry.

3. 🟢 **Empty primary is silently unlabelled
   (Claude-surfaced).** When a user overrides every visible
   node off primary (everything routed to secondary/tertiary),
   primary now shows no label. Pre-CS-55 it incorrectly showed
   "Absorbance" — strictly an improvement. A future polish
   could surface "(no data)" or similar to make the empty axis
   visually explicit. Defer until reported. No register entry.

4. 🟢 **Phase 4u friction #9 (`_absorbance_to_y` corrupts d²A
   on %T) cross-refs CS-55's label fix (Claude-surfaced
   cross-ref).** CS-55 fixes the label routing — d²A on
   primary now labels "d²A/dλ²" — but the values plotted are
   still transformed by `_absorbance_to_y` on %T toggle, which
   clips to `[-10, 10]` and applies `100·10^(-A)`. Cross-refs
   Phase 4u friction #9 register entry (still ⏳). Natural
   co-pickup with the next session that touches the per-node
   redraw loop's y-unit branch. No new register entry; cross-
   ref only.

5. ~~🟢 **BACKLOG.md changelog gap: no `*1.28: Phase 4ac...*`
   entry (Claude-surfaced doc-debt).** Phase 4ac's bookkeeping
   commit bumped the body version 1.27 → 1.28 but did not add
   a corresponding `*1.28: Phase 4ac — drop CS-31 + CS-32
   (CS-54)...*` line at the bottom of the changelog list.
   Phase 4ad's `*1.29:` entry references "Phase 4ad" so the
   gap is visible. A retroactive one-liner would fix it; not
   blocking. No register entry.~~ ✅ Resolved in Phase 4ae
   (CS-56) — retroactive `*1.28: Phase 4ac...*` entry inserted
   between 1.27 and 1.29 in this bookkeeping commit.

### Friction points carried forward from Phase 4ae

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4ae while landing the three new Plot
Settings → Appearance controls (CS-56) — closing Phase 4ac
friction #2 + #3 (both USER-FLAGGED 🟡) plus the
promote-to-Plot-Settings half of the CS-44 follow-up register
entry, plus the Phase 4ad friction #5 doc-debt. The user
accepted no new items at step 5 ("proceed"); all five items
below are Claude-surfaced 🟢 polish notes flagged during step
5; none have new register entries. **Do not fix until the
relevant subsequent Phase 4 session.**

1. 🟢 **`_make_colour_swatch` has no `trace_add` on its
   `StringVar` (Claude-surfaced footgun).** Writes to
   `_working` happen only via the colorchooser's `_pick`
   callback explicitly calling `_on_var_write`. Setting the
   var directly (e.g. programmatic restore, a test, a future
   "import plot settings from another project" gesture) silently
   drops the write — `_working[key]` keeps its prior value
   while the widget displays the new value. The CS-56 test
   `test_grid_color_swatch_writes_through_to_working` was
   originally written assuming a trace fired on `var.set()`
   and had to be rewritten to call `_on_var_write` directly
   to expose the real path. The existing `background_color`
   swatch has the same gap. **Fix shape:** one-line
   `var.trace_add("write", lambda *_, k=key, v=var:
   self._on_var_write(k, v.get()))` inside the helper. Touches
   both swatch consumers (`grid_color` + `background_color`) +
   any future swatch addition. Cheap, but worth its own phase
   rather than a drive-by since it changes write semantics on
   an existing widget. No register entry.

2. 🟢 **No targeted persistence test for the new Appearance
   keys round-tripping through `project_io` (Claude-surfaced
   coverage gap).** The existing `TestPlotDefaultsRoundTrip.
   test_user_defaults_round_trip` exercises the manifest
   serialiser generically; the new keys ride along *if* they
   reach `_USER_DEFAULTS`. There's no test that asserts
   saving a `.ptmg` with `cfg["grid_color"] = "#ff0000"` and
   `cfg["tertiary_axis_offset"] = 1.30`, reloading it, and
   confirming both values land back at `_redraw` time. Likely
   works (the schema doesn't reject unknown keys; CS-46 round-
   trips arbitrary `plot_defaults` content) but unproven. **Fix
   shape:** one new test in `test_persistence_phase_a.
   TestPlotDefaultsRoundTrip` that mutates the two keys before
   save and checks them after load. No register entry.

3. 🟢 **`tick_direction` factory-default flip is observable
   to existing users with no `_USER_DEFAULTS` entry (Claude-
   surfaced behaviour-change visibility).** Per decision (i) of
   the inward-tick lock, no migration runs — users who pin
   `"out"` explicitly are unaffected, but users with no
   `~/.binah_config.json` "tick_direction" entry will see ticks
   suddenly point inward on next launch. This is the intended
   path, but it's a visible behaviour change worth surfacing
   somewhere user-facing once a release-note / CHANGELOG flow
   exists. Today there is none. No register entry; folds into
   the future release-note infrastructure when one lands.

4. 🟢 **Tertiary-axis offset Spinbox bounds `1.00`–`1.50` are
   a Claude pick, not a user lock (Claude-surfaced minor
   choice).** User confirmed "as long as the user can change
   this somehow in the plot settings and also have a way of
   changing the default" — both reachable today (Spinbox
   in-band edit + Save-as-Default via the CS-23 Save button).
   `tk.Spinbox` lets the user type values outside the bounds
   (the arrows clamp, typed input does not), so the band is
   really a soft suggestion. If a user reports wanting a
   stricter band, a wider band, or a hard cap, retune. Until
   then, locked. No register entry.

5. 🟢 **Dialog row order in `_build_section_appearance`
   (Claude-surfaced minor choice).** Phase 4ae inserted Grid
   colour at row=1 (immediately under Grid checkbox at row=0;
   Background dropped to row=2). The cluster-by-concept order
   (Grid + Grid colour together) won over cluster-by-widget
   (both colour swatches adjacent). If a future user-facing
   review prefers a different grouping — or if a planned
   LabelFrame re-org pass (cross-refs the StyleDialog
   LabelFrame-groupings register entry above) reshapes the
   section — re-sort then. Until then, locked. No register
   entry.

### Friction points carried forward from Phase 4af

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4af while landing the user-driven
NODE_GROUP container + Combine/Ungroup gestures (CS-57) — closing
Phase 4v friction #1 part (c) (USER-FLAGGED 🔴), Phase 4ac
friction #4 + #5. The user contributed two new USER-FLAGGED
register entries at step 5 ("keyboard shortcuts whole-interface
evaluation" + "Add to existing group" gesture) and a design
constraint ("no info bleed between tabs unless explicitly user-
driven"). The polish-level items below stay 🟢. **Do not fix
until the relevant subsequent Phase 4 session.**

1. 🟡 **USER-FLAGGED Keyboard shortcuts — whole-interface
   evaluation pass.** User-flagged at end of Phase 4af. **Cross-
   ref:** see the new canonical register entry above. The Phase
   4af gestures (Combine selected, Ungroup, chevron expand) all
   ship mouse-only; first candidates for the eventual shortcut
   pass are Ctrl+G / Ctrl+Shift+G / F2 / Delete. Multi-phase
   task — the design pass needs to inventory every existing
   gesture before any binding lands.

2. ~~🟡 **USER-FLAGGED "Add to existing group" gesture (Phase
   4ag candidate).** User-flagged at end of Phase 4af
   ("Definitely want that"). Today the only way to add a member
   to an existing NODE_GROUP is dissolve + recreate, which is
   bad UX once a group has any non-default state (user-edited
   label, future per-group style). **Cross-ref:** see the new
   canonical register entry above. Pairs with the canonical
   "Drop CS-31 + introduce user-driven node groups" register
   entry (now ✅ for the v1 create/dissolve path); this is the
   natural v2 extend path.~~ ✅ Resolved in Phase 4ag (CS-58).
   Shipped both surfaces (footer + context menus), append
   ordering, new `NODE_GROUP_MEMBERS_CHANGED` event, AND the
   symmetric "Remove from group" gesture in the same phase.

3. 🟢 **Design constraint — no information bleed between tabs
   unless explicit (USER-CONFIRMED).** User confirmed at end of
   Phase 4af: "We don't want information to bleed from one tab
   to another unless explicitly done so by the user (or in some
   very specific cases, but I can't think of any at the
   moment)." Today this is honoured for the new Phase 4af
   selection model: each ScanTreeWidget owns its own
   `_selected_node_ids` set, and selections are NOT
   synchronised across tabs. Recording this as a design
   constraint so future cross-tab work (e.g. a shared
   "selection bus" idea, multi-tab Apply gestures) is
   evaluated against it explicitly. No register entry yet; the
   constraint is more of a North Star than an actionable item.
   If/when a need for cross-tab propagation surfaces, the
   register entry that ships it must call out the explicit
   user gesture that triggers it (e.g. a "Send selection to
   Compare" button, not an implicit sync).

4. 🟢 **Group "(N members)" suffix is always appended, even
   for user-renamed groups (Claude-surfaced polish, USER-
   CONFIRMED polish-level).** `_build_group_row` appends
   `"  (N members)"` to whatever `node.label` carries, so a
   user-renamed "my Ni²⁺ aquo series" renders as
   "my Ni²⁺ aquo series  (2 members)". User acknowledged at
   end of Phase 4af: "Good call - something definitely for
   polishing rather than mission critical." Future polish
   options: (a) drop the suffix once the user explicitly
   renames; (b) move the count to its own widget cell so it
   doesn't compete for label width; (c) keep the current
   behaviour and accept the visual noise. Defer until reported
   in real use. No register entry.

5. ~~🟢 **"Show hidden" footer toggle behaviour is opaque
   (USER-CONFIRMED; polish-level).** User noted at end of
   Phase 4af: "I've not yet seen an example where 'show
   hidden' actually uncovers anything... I'll have to play
   around with it some more to see how it behaves. Definitely
   polish level." The toggle reveals committed nodes whose
   `active` flag is False (set via the context-menu Hide
   action or the future Trash-can register entry); on a fresh
   workflow no nodes are hidden, so the toggle is a no-op.~~
   ~~🟡 **Upgraded to USER-FLAGGED in Phase 4ag step 5:** the
   user verified during Phase 4ag and re-flagged ("doesn't
   allow me to select it ... if it's not relevant, then it
   should be greyed out when it's not relevant"). **Cross-ref:**
   see the new canonical register entry "Show hidden toggle
   should disable when no hidden rows exist".~~ ✅ Chain
   closed in Phase 4ah (CS-59 Thread A, commit 2) — the
   canonical register entry is now resolved; this friction
   item, Phase 4ag friction #3, and the canonical entry all
   reference the same fix. Chain collapsed: this is the
   first occurrence in the friction-history record and stays
   as the canonical breadcrumb.

6. ~~🟢 **Footer "Group selected" button label is static —
   doesn't say how many will be combined (Claude-surfaced
   polish, USER-CONFIRMED).** Today the button reads "Group
   selected" regardless of selection size; the context-menu
   companion entry shows "(N)". Easy polish: bind button text
   to `len(_selected_node_ids)`, e.g. "Group selected (3)".
   User confirmed at end of Phase 4af. Defer until reported.
   No register entry.~~ ✅ Resolved in Phase 4ag (CS-58). The
   button now mutates its text per selection classification:
   `"Group selected (N)"` in group mode, `"Add to <group
   label>"` in extend mode, baseline `"Group selected"`
   disabled otherwise. CS-57's `text="Group selected"` initial-
   label lock was relaxed in this phase (the relaxation
   trigger was always this friction item).

7. 🟢 **`_show_group_context_menu` is monkey-patched in one
   test (Claude-surfaced testing-shape note, USER-CONFIRMED).**
   `test_group_row_uses_group_context_menu_branch` swaps in a
   spy callable rather than inspecting a real `tk.Menu`'s
   items, because Tk menus don't expose their entries to
   introspection without significant scaffolding. The
   monkey-patch is the most surgical approach given Tk's
   API surface; if a future test refactor lifts a shared
   "menu inspection" helper, this test can be retired. No
   register entry. **Phase 4ag note:** the spy-menu pattern
   was reproduced (with an enriched form that captures every
   add_command kwarg dict) in `TestScanTreeWidgetNodeGroups-
   Phase4ag`. Same root cause; same root mitigation. Cross-
   ref to the new "Spy-menu helper duplication" carry-forward
   below.

### Friction points carried forward from Phase 4ag

These are concrete obstacles the next Phase 4 session will hit.
Identified during Phase 4ag while landing the extend / remove
gestures + footer button state-aware label (CS-58). Phase 4ag
closed the highest-pain USER-FLAGGED 🟡 carry-forward from Phase
4af ("Add to existing group") and incidentally closed Phase 4af
friction #6 (static button label). The user contributed THREE new
USER-FLAGGED register entries at step 5 (grid z-order bug, axis
double-click dialog, "Show hidden" disable-gating) — all 🟡, all
above. The Claude-surfaced 🟢 items below are polish-level and
deferrable. **Do not fix until the relevant subsequent Phase 4
session.**

1. 🟡 ~~**USER-FLAGGED Grid renders in front of data lines,
   not behind.** User-flagged at end of Phase 4ag step 5
   ("Grid should be behind the datasets, not in front").
   `uvvis_tab._redraw` calls `ax.grid(...)` without a
   `zorder` kwarg; matplotlib's default grid zorder (2.5) is
   above the line plots' default zorder (2.0).~~ ✅ Resolved
   in Phase 4ah (commit 1, A.1). One-line fix landed —
   `ax.grid(...)` now passes `zorder=0`. 2 regression tests
   in `TestUVVisTabGridZOrderPhase4ah`.

2. 🟡 ~~**USER-FLAGGED Axis double-click → axis-properties
   dialog.** User-flagged at end of Phase 4ag step 5
   ("Double-click a plot axis in order to open a window to
   change axis-specific parameters? including min, max,
   spacing, axis label, fonts, font sizes, axis colour, tick
   size, etc."). Multi-phase task — significant new dialog
   shell + per-axis-role style schema + matplotlib event
   binding work.~~ ✅ Foundation resolved in Phase 4ai
   (CS-60). The user's design call was a unified
   PlotConfigDialog with a Notebook (one Global tab matching
   today's PlotSettings + one tab per axis role), not a
   second dialog. The ⚙ button opens on Global; double-
   clicking on a plot axis region opens on that axis's tab
   via the new `plot_axis_hit_test.classify_axis_double_click`
   classifier. CS-23 subsumed into CS-60. Per-axis settings
   continue landing Phase 4aj+. See the canonical register
   entry above for the multi-phase ladder.

3. 🟡 ~~**USER-FLAGGED "Show hidden" toggle should disable
   when no hidden rows exist.** Upgraded from Phase 4af
   friction #5 🟢 by user flag during Phase 4ag step 5.~~
   ✅ Resolved in Phase 4ah (CS-59 Thread A, commit 2). New
   `_has_hidden_rows()` predicate + `_refresh_show_hidden_
   button_state()` companion called from `_rebuild`'s tail.
   Disable-only — no count badge or tooltip. Cascade
   preserves `_show_hidden` ON when the last hidden row
   disappears. 11 tests in `TestShowHiddenButtonGatingPhase4ah`.

4. 🟢 **`_can_group_selection` preserved as a thin alias of
   `_classify_selection()["mode"] == "group"` (Claude-
   surfaced refactor note).** Phase 4ag introduced
   `_classify_selection` as the canonical analysis (returns
   one of `"none"` / `"group"` / `"extend"` / `"invalid"`)
   but kept `_can_group_selection` because it's referenced
   by an existing Phase 4af test and the data-row context
   menu's "Group selected (N)" predicate. Duplication a
   future refactor could collapse — both walks check the
   same per-id rules. Defer until a refactor naturally
   touches this region. No register entry.

5. 🟢 **Spy-menu pattern duplicated between Phase 4af and
   Phase 4ag UI tests (Claude-surfaced testing-shape note).**
   Both `TestScanTreeWidgetNodeGroupsPhase4af` and
   `TestScanTreeWidgetNodeGroupsPhase4ag` reach into Tk's
   `Menu` constructor via mock to capture `add_command`
   entries — the Phase 4ag form is enriched (captures every
   keyword dict for state/label/command introspection). A
   future test refactor could lift a shared `_SpyMenu`
   helper into a test-utilities module. Cross-ref Phase 4af
   friction #7 (same root cause). No register entry.

6. 🟢 **"Add to <group label>" footer button truncation
   cap is hand-tuned at 24 chars (Claude-surfaced polish).**
   `_refresh_group_button_state` calls `_truncate_label(...,
   max_chars=24)` so a long user-renamed group ("my Ni²⁺
   aquo series across 12 °C → 80 °C") doesn't stretch the
   footer. The cap is not responsive — a wider window leaves
   horizontal slack unused. Future polish: derive the cap
   from the actual footer width (similar to CS-47's dynamic
   label cap for sidebar rows). Defer until the user reports
   real-world friction (e.g. a long group label being
   over-truncated). No register entry.

7. 🟢 **Right-click-target / selection-payload convention
   used by Phase 4ag's context-menu gestures isn't recorded
   in CS-04 (Claude-surfaced spec gap).** Both the group-row
   "Add selected to this group" entry and the data-row
   "Remove from group" entry follow the pattern: the
   right-clicked row IDENTIFIES the target / scope; the
   current selection identifies the payload (what gets
   added / acted on). CS-04 §"Context menu" doesn't yet
   document this convention. When CS-04 next gets touched
   (e.g. a keyboard-shortcuts phase or a new gesture
   landing), record the convention so future implementers
   converge to the same shape. No register entry.

8. 🟢 **Group "(N members)" suffix relocation
   (Phase 4af friction #4 carry-over).** The current
   inline rendering (`<user label>  (N members)` inside
   the main label widget) refreshes correctly on the
   new structural-rebuild path, so the cosmetic polish
   (move count to its own widget cell so it doesn't
   compete for label width) is deferrable. Originally
   surfaced in Phase 4af; Phase 4ag explicitly scoped it
   OUT during decision lock because moving the suffix
   would force a brittle test update on the existing
   `test_group_row_displays_member_count_suffix` pin for
   a 🟢 polish. Stays deferred until reported in real use
   or until a phase naturally touches that test. No
   register entry.

### Friction points carried forward from Phase 4ah

These are concrete obstacles the next Phase 4 session will hit.
Phase 4ah was a polish bundle (A.1 grid zorder + A.2 show-
hidden gating + F TDDFT button relocation + G d²A %T fix)
that resolved four BACKLOG register entries without
introducing new architecture beyond CS-59. The user
contributed TWO new BACKLOG entries at step 5 / session
start: 🟢 sidebar `«` + "TDDFT Section:" combobox follow
Open File / Reload into TDDFT chrome (USER-CONFIRMED
follow-up), and 🟢 per-tab tertiary-y-axis default routing
schema (USER-FLAGGED design topic raised by the user at
the start of Phase 4ah — "what counts as tertiary axis
default per tab"). The Claude-surfaced 🟢 items below are
polish-level and deferrable. **Do not fix until the
relevant subsequent Phase 4 session.**

1. 🟢 **Sidebar `«` toggle + "TDDFT Section:" combobox
   follow Open File / Reload into TDDFT chrome (USER-
   CONFIRMED follow-up).** Phase 4ah commit 3 (F) moved
   Open File + Reload into the TDDFT sidebar but left
   three other pieces of TDDFT-only chrome at the app
   top level: the `«` sidebar-toggle button, the "TDDFT
   Section:" combobox, and the "No file loaded" file
   label. The user confirmed during Phase 4ah step 5 that
   these should follow in a future phase. **Cross-ref:**
   see the new canonical register entry above. Pairs
   with the larger "Refactor uvvis_tab.py — extract host
   shell" cross-tab generalization entry (the broader
   tab-chrome lift).

2. 🟢 **Per-tab tertiary-y-axis default routing schema
   (USER-FLAGGED design topic).** Raised by the user at
   the START of Phase 4ah ("With regards to default
   multi-axis functionality, we will need to consider
   what counts as default behaviour differently in
   different tabs"). Today `_DEFAULT_Y_AXIS_BY_NODETYPE`
   is a single flat dict shared across the codebase
   (CS-44-locked). TDDFT / Compare / future tabs may
   need their own defaults — TDDFT plausibly wants
   secondary=oscillator-strength / tertiary=transition-
   density-or-state-energy; UV/Vis's tertiary default
   is unclear (Claude recommended keeping d²A on
   secondary by default rather than moving it to
   tertiary). **Cross-ref:** see the new canonical
   register entry above. Dedicated future phase —
   Claude explicitly recommended NOT bundling into
   Phase 4ah.

3. 🟢 **`_has_hidden_rows()` walks every graph node every
   rebuild (Claude-surfaced perf note).** O(N) per
   `_rebuild`. Fine at the dataset counts the widget
   targets (tens, per `_rebuild`'s docstring), but if
   `_rebuild` ever needs optimisation, `_has_hidden_rows`
   joins `_candidate_nodes` and `_refresh_group_button_
   state` in the per-rebuild walk cluster. Defer until
   profiling shows a hot spot. No register entry.

4. 🟢 **Phase 4ah comment block in `binah._build_top_bar`
   is dead structural commentary (Claude-surfaced /
   USER-DECIDED-KEEP).** The block at `_build_top_bar`
   explains why Open File + Reload are NOT there. Future
   readers may find it useful for ~one phase and noise
   thereafter. Claude flagged during step 5; user
   decided "keep it for now". Revisit when a future
   phase naturally touches `_build_top_bar`. No register
   entry.

5. 🟢 **Global `<Control-o>` keybinding still bound to
   `_open_file` even though the button is now TDDFT-
   only (Claude-surfaced / Phase 4ah Lock 12 deferral).**
   Phase 4ah Lock 12 explicitly deferred scope-by-tab
   binding to the keyboard-shortcuts whole-interface
   USER-FLAGGED pass. Re-cross-refs the keyboard
   shortcuts register entry. No new register entry.

6. 🟡 ~~**USER-FLAGGED Axis double-click → axis-properties
   dialog (Phase 4ag carry-over).**~~ ✅ Foundation resolved
   in Phase 4ai (CS-60). Chain-collapsed — canonical
   strike-through is at Phase 4ag friction #2 above.

7. 🟢 **`_can_group_selection` thin-alias cleanup
   (Phase 4ag carry-over).** Phase 4ag friction #4 —
   still open. Defer until a refactor naturally touches
   this region. No register entry.

### Friction points carried forward from Phase 4ai

These are concrete obstacles the next Phase 4 session will hit.
Phase 4ai shipped the CS-60 foundation for the long-standing
USER-FLAGGED 🟡 axis double-click feature: unified
PlotConfigDialog with a Notebook hosting Global + five axis-
role tabs, cross-tab pending-edit state model, new
Save / Apply / Apply to All Tabs / Cancel button row, and
the UV/Vis figure double-click → tab integration. The user
contributed TWO new USER-FLAGGED register entries at step 5:
🟡 `_USER_DEFAULTS` tab-type split (becomes urgent when the
dialog wires into a second tab type — XANES axis labels can't
share UV/Vis's slot); 🟡 Twin-X axis wavelength↔energy with
bidirectional range coupling (the Secondary X Notebook tab
exists as a shell today; the matplotlib twin-x machinery is
the larger feature). The Claude-surfaced 🟢 items below are
polish-level and deferrable. **Do not fix until the relevant
subsequent Phase 4 session.**

1. 🟡 ~~**USER-FLAGGED Per-axis settings ladder — ~~Phase 4aj
   through~~ ~~Phase 4ak through~~ ~~Phase 4al through 4an~~
   ~~Phase 4am through 4an~~ Phase 4an only.** CS-60 is the
   foundation only.~~ ✅ Ladder fully closed in Phase 4an
   (CS-65). All five canonical slots resolved: 4aj (CS-61
   tick_direction relocation) → 4ak (CS-62 schema invention) →
   4al (CS-63 per-axis tick rendering + Move-to picker) → 4am
   (CS-64 range / autoscale / scale) → 4an (CS-65 tick
   spacing + per-axis grid + axis colour).
   ~~The next five phases each ship one slice: 4aj
   relocates `tick_direction` from Plot Settings → per-axis
   tabs (CS-56 relaxation, smallest possible first
   relocation);~~ ✅ Phase 4aj slot closed (CS-61):
   `tick_direction` widget mirrored across all five per-axis
   tabs sharing one Tk var; new
   `_KEY_TO_TAB["tick_direction"] = "primary_x"` dirty pin;
   flat schema preserved. ~~4ak invents the per-axis-role
   nested schema in `_USER_DEFAULTS` with migration shim +
   axis label override mirrored on Global + populates the
   read-only "Plots on this axis" list;~~ ✅ Phase 4ak slot
   closed (CS-62): `_FACTORY_DEFAULTS["axes"]` nested per-
   axis sub-dict; `migrate_plot_config` idempotent legacy-
   flat-to-nested shim; per-axis Tk vars in
   `_axis_control_vars[(role, key)]` (each tab owns its own
   slot); Global "Per-axis label overrides" mirror section
   sharing Tk vars with per-axis tab Entries; `plots_by_role`
   constructor kwarg + `tk.Listbox` rendering for populated
   roles. ~~Per-axis tick_direction RENDERING is deferred to
   Phase 4al (the schema stores per-axis values; the
   renderer still applies primary_x's value uniformly across
   all axes).~~ ✅ Phase 4al slot closed (CS-63): the
   renderer splits its tick_params calls into five per-axis-
   role invocations (primary_x / primary_y / secondary_x
   sibling / secondary_y twin / tertiary_y twin); the
   wavelength twin's previously-hardcoded `direction="in"`
   reads through `_per_axis_tick_direction(cfg,
   "secondary_x")`; the Move-to Combobox lands on each of
   the three Y-axis tabs writing `style["y_axis"]` via
   `graph.set_style`. axis_label_override RENDERING was
   wired in Phase 4ak for all five roles. ~~The remaining
   two phases each ship one slice: 4am adds range /
   autoscale / scale (linear/log);~~ ✅ Phase 4am slot
   closed (CS-64): `_AXIS_KEYS` grew 2→6 with `range_lo` /
   `range_hi` / `autoscale` / `scale`; per-axis tabs gain
   Range Entry pair + Autoscale Checkbutton + Scale
   Combobox (linear/log) below the existing tick-direction
   + axis-label-override rows; `_make_axis_bool_var(role,
   key)` mirrors `_make_axis_string_var` for the
   BooleanVar-backed `autoscale` key; renderer reads each
   axis's own `cfg["axes"][role][...]` slot at its limit-
   application site via four new module-level helpers
   (`_per_axis_range` / `_per_axis_autoscale` /
   `_per_axis_scale` / `_parse_lim_str`). Legacy top-bar
   `_xlim_lo` / `_ylim_lo` Tk vars stay the fallback when
   `autoscale=True` (default), so the existing top-bar UX
   keeps working unchanged; `autoscale=False` makes the
   schema bounds win. Twin Y-axes (secondary_y, tertiary_y)
   apply per-role scale + range at the twin axis after the
   primary plot loop. ~~The remaining one phase ships:
   4an handles tick spacing + polish.~~ ✅ Phase 4an slot
   closed (CS-65): `_AXIS_KEYS` grew 6→10 with `tick_major` /
   `tick_minor` / `grid_show` / `axis_color`; every per-axis
   tab gains four new widget rows (tick-spacing Entry pair,
   Show gridlines Checkbutton, Axis colour swatch +
   `colorchooser` picker Button); renderer reads each axis's
   own slot via five new helpers (`_parse_tick_str` /
   `_per_axis_tick_major` / `_per_axis_tick_minor` /
   `_per_axis_grid` / `_per_axis_color`) applied at five
   call sites (primary X / primary Y / both twin Y axes /
   secondary X wavelength sibling). The global
   `cfg["grid"]` master switch remains the top-level
   precedence — `False` disables everything; `True` falls
   through to per-axis `grid_show` keys on `primary_x` and
   `primary_y` (twin axes share the primary grid).
   `matplotlib.ticker.MultipleLocator` underpins the tick-
   spacing override. **Cross-ref:** see the canonical
   axis-double-click register entry above for the multi-
   phase plan AND the Phase 4aj + 4ak + 4al + 4am + 4an
   partial annotations. Reasoning level ~~for 4ak is
   extra-high (schema invention + migration shim + dual-
   surface UI);~~ ~~for 4al is now slightly higher than
   originally scoped (mechanical against the locked schema
   PLUS per-axis tick rendering wire-up);~~ ~~4am stays
   normal;~~ ~~4an stays medium.~~ Ladder fully complete.

2. 🟡 **USER-FLAGGED `_USER_DEFAULTS` tab-type split.**
   See the new canonical register entry above. Becomes
   urgent when the dialog wires into a second tab type
   (XANES / EXAFS / TDDFT / Compare). Not urgent for
   Phase 4aj–4an because UV/Vis is still the only host.
   Cross-refs CS-46 (manifest `plot_defaults` round-trip)
   and the existing "Refactor uvvis_tab.py — extract host
   shell" register entry.

3. 🟡 **USER-FLAGGED Twin-X axis full wiring.** See the new
   canonical register entry above. The Secondary X Notebook
   tab already exists and the top-spine double-click opens
   it; the actual `twinx()` machinery + wavelength↔energy
   transform + bidirectional range coupling are the larger
   feature. Becomes actionable when Phase 4am-ish range
   controls land (the tab needs widgets before the wiring
   matters).

4. 🟢 **"Apply to All Tabs" callback is unwired (Claude-
   surfaced polish).** The button exists in the new CS-60
   row but is disabled because no host today passes
   `on_apply_all_tabs`. Wiring it requires Binah to know
   about its sibling UV/Vis notebook tabs and replicate
   `_plot_config` to them (scoped to same-tab-type
   siblings; cross-tab-type replication is NOT a thing
   per CS-60 lock 14). Defer until the polish phase
   (~Phase 4an) or until the user reports needing it. No
   new register entry.

5. 🟢 **`_AXIS_TAB_PLACEHOLDER_BADGE` is static (Claude-
   surfaced polish).** Today each axis tab carries a static
   italic badge ("(plots routed via y_axis style)" etc.).
   Phase 4ak swaps in live "(used by N nodes)" / "(unused)"
   / "(derived)" markers driven by the host tab's
   `_axes_by_role` plus the graph's nodes. Natural Phase 4ak
   follow-up; no register entry (folds into the per-axis
   ladder above).

6. 🟢 **`hit_kind` from the classifier is ignored at the
   dialog level (Claude-surfaced polish).** Every band of
   the same axis (spine / tick_labels / axis_label) opens
   the same tab. The data is on `AxisHit.hit_kind` if a
   future phase wants per-band behaviour (e.g. tick-label
   click jumps directly to the Ticks section once that
   lands in 4an). No register entry — folds into the
   per-axis ladder.

7. 🟢 **Tertiary x-axis is not classifiable today (Claude-
   surfaced polish).** Secondary X has a Notebook tab and
   the top-band hit-test opens it, but there's no real
   matplotlib secondary x-axis until the Twin-X register
   entry above lands. Until then the Secondary X tab is
   reachable only via the top-spine double-click gesture
   (no actual ticks/spine to click on for a tertiary X). No
   register entry — folds into the Twin-X register entry
   above.

8. 🟢 **Band-size constants may need tuning if matplotlib
   layout changes (Claude-surfaced polish).** The hit-test
   bands (`_TOTAL_BAND_PX=40` / `_SPINE_BAND_PX=6` /
   `_TICK_BAND_PX=18` / `_TERTIARY_BAND_PX=24`) were
   picked from the current matplotlib tick-label sizing.
   If a future styling change widens tick labels or a
   different backend ships, the bands may need recalibration.
   Tests use the constants symbolically so values can shift
   without test churn; no register entry.

### Friction points carried forward from Phase 4aj

These are concrete obstacles the next Phase 4 session will hit.
Phase 4aj shipped CS-61 — the first slice of the per-axis
settings ladder (canonical plan in Phase 4ai friction #1
above): the `tick_direction` widget relocates from Plot
Settings → Appearance to a new "Settings" `LabelFrame` on
each of the five per-axis Notebook tabs, mirrored across all
five tabs via a shared Tk var, schema stays flat, and the
new `_KEY_TO_TAB` routing map gets its first explicit entry
(`"tick_direction" → "primary_x"`) so the dirty bullet pins
to Primary X regardless of which tab the user edited on.
The user contributed ONE new USER-FLAGGED register entry at
step 5 (external-output plot style presets — JACS /
PowerPoint / etc., with reference Jupyter notebook code to
lift from) plus ONE 🟢 USER-FLAGGED friction note
(`TestAppearanceSectionPhase4ae` class-name drift). Three
Claude-surfaced 🟢 items below are polish-level and
deferrable. **Do not fix until the relevant subsequent
Phase 4 session.**

1. 🟡 ~~**USER-FLAGGED Per-axis settings ladder continues —
   ~~Phase 4ak through 4an~~ ~~Phase 4am through 4an~~
   Phase 4an only.**~~ ✅ Resolved in Phase 4an (CS-65).
   Cross-ref Phase 4ai friction #1 above — ladder fully
   closed: 4aj (CS-61) → 4ak (CS-62) → 4al (CS-63) → 4am
   (CS-64) → 4an (CS-65).

2. 🟢 ~~**Shared-var UX is dishonest by design (Claude-
   surfaced, Phase 4aj artifact).** Editing the
   `tick_direction` radio on Primary Y visually updates the
   radios on Primary X / Secondary X / Secondary Y /
   Tertiary Y because all five tabs share one
   `_control_vars["tick_direction"]` Tk var. Acknowledged
   trade-off — Phase 4aj's brief authorized it as the
   smallest possible real relocation, no schema invention.
   **Resolved naturally by Phase 4ak's per-axis schema
   invention** (each tab gets its own per-axis slot →
   each tab gets its own var). No register entry; folds
   into the canonical per-axis ladder above.~~ ✅ Resolved
   in Phase 4ak (CS-62) — `_axis_control_vars[(role, key)]`
   gives each tab its own Tk var; edits on one tab no
   longer reflect on the other four.

3. 🟢 ~~**Dirty-pin is counterintuitive (Claude-surfaced,
   Phase 4aj artifact).** `_KEY_TO_TAB["tick_direction"] =
   "primary_x"` is set so edits on any per-axis tab mark
   ONLY Primary X dirty — chosen over the alternative
   (mark all five tabs dirty per edit, five-bullet flood)
   as the better of two imperfect 4aj options. A first-
   time user editing tick direction on Primary Y will see
   the bullet appear on Primary X and briefly wonder why.
   **Resolved naturally by Phase 4ak's per-axis schema
   invention** (each per-axis tab owns its own
   `tick_direction` slot → each tab's edit marks its own
   tab dirty → no surprising cross-tab dirty bullet). No
   register entry; folds into the canonical per-axis
   ladder above.~~ ✅ Resolved in Phase 4ak (CS-62) —
   `_KEY_TO_TAB["tick_direction"]` removed (the dict is
   now empty); `_on_axis_var_write(role, key, value)`
   carries the role directly and marks that tab dirty.

4. 🟢 ~~**`_build_axis_tab_settings` is single-purpose today
   (Claude-surfaced, Phase 4aj artifact).** Helper builds
   only the Tick direction Radiobutton row + manages the
   shared-var registration on first call. When Phase 4ak
   adds the second per-axis widget (axis label override
   mirrored on Global), the helper either grows a switch
   on `role` or splits into per-widget builders. Today
   the helper's signature `(parent, role)` is right-sized
   for the single widget; the generalisation lock decision
   is a Phase 4ak sub-question, not blocking. No register
   entry — folds into the canonical per-axis ladder above.~~
   ✅ Resolved in Phase 4ak (CS-62) — helper grew inline
   (the canonical lock-relaxation): two widget builders
   (tick_direction Radiobutton row + axis_label_override
   Entry) live side-by-side in the same helper.
   Signature `(parent, role)` preserved.

5. 🟢 **USER-FLAGGED `TestAppearanceSectionPhase4ae`
   class-name drift after Phase 4aj relocation.** The
   test class still owns
   `test_tick_direction_factory_default_is_in` and
   `test_factory_reset_restores_new_appearance_keys`
   (which uses `dlg._control_vars["tick_direction"]`) even
   though the tick_direction widget no longer lives in the
   Appearance section after CS-61. The tests stay correct
   (factory-default schema invariants + control-var
   reachability are independent of widget location), so
   the class name is the only thing that's misleading.
   Renaming it requires a sweep of any test-runner
   invocations targeting the class by name (`python -m
   unittest test_plot_settings_dialog.TestAppearanceSectionPhase4ae`)
   and is the kind of test-housekeeping work that fits
   naturally into a future Phase that already touches the
   class for content reasons (e.g. when 4ak invents per-
   axis schema and the factory defaults grow nested keys).
   Defer until a future phase naturally touches the
   class. No register entry — folds in alongside the
   per-axis ladder above.

6. 🟡 **USER-FLAGGED External-output plot style presets
   continues.** See the new canonical register entry above
   (added in Phase 4aj step 5). Independent of the per-
   axis ladder — could happen alongside or after. Becomes
   actionable when the user is ready to share the
   reference Jupyter notebook code. **Cross-ref:** see
   canonical register entry "External-output plot style
   presets — journal / presentation / web formatting
   (USER-FLAGGED, Phase 4aj)" above.

7. 🟡 **USER-FLAGGED `_USER_DEFAULTS` tab-type split
   (Phase 4ai carry-over).** Cross-ref Phase 4ai friction
   #2 above. Becomes urgent when the dialog wires into a
   second tab type. Still open after 4aj — schema stayed
   flat. Pairs naturally with Phase 4ak's per-axis
   schema invention (both touch `_USER_DEFAULTS` shape).

8. 🟡 **USER-FLAGGED Twin-X axis full wiring (Phase 4ai
   carry-over).** Cross-ref Phase 4ai friction #3 above.
   Still open after 4aj — the Secondary X tab now has a
   tick_direction radio (mirrors the other four tabs) but
   no actual matplotlib twin-x machinery, transform, or
   range coupling. Becomes actionable when Phase 4am-ish
   range controls land.

### Friction points carried forward from Phase 4ak

These are concrete obstacles the next Phase 4 session will
hit. Phase 4ak shipped CS-62 — the per-axis schema invention
slice of the ladder (canonical plan in Phase 4ai friction
#1 above, with Phase 4ak slot now ✅): `_FACTORY_DEFAULTS`
gains a nested `"axes"` sub-dict, the legacy flat
`tick_direction` migrates per-axis via
`migrate_plot_config`, each per-axis tab owns its own Tk
vars in `_axis_control_vars[(role, key)]`, a new Global
"Per-axis label overrides" section mirrors all five
`axis_label_override` Entries via shared vars, the
`plots_by_role` constructor kwarg threads the per-axis
plot inventory into read-only Listboxes, and the renderer
applies `axis_label_override` per axis for all five roles.
The user contributed FIVE new USER-FLAGGED register
entries at step 5 (live-preview vs Apply, apply-to-all
icon on per-axis tabs, axis nomenclature rename to
position-based names, rich-text axis labels with
mathtext) plus FOUR new register entries above (well, two
already-canonical entries cross-referenced + two new ones
just added) AND ONE user-surfaced bug (secondary X tick
direction doesn't apply to the secondary X axis — by
design in CS-62 since per-axis tick rendering is deferred
to Phase 4al). Three Claude-surfaced 🟢 items below are
polish-level and deferrable. ONE 🟢 item carries forward
unresolved from Phase 4aj. **Do not fix until the
relevant subsequent Phase 4 session.**

1. 🟡 ~~**USER-FLAGGED Per-axis settings ladder continues
   (Phase 4am through 4an).**~~ ✅ Resolved in Phase 4an
   (CS-65). Cross-ref Phase 4ai friction #1 above —
   ladder fully closed.

2. ~~🟠 **USER-FLAGGED bug: changing Secondary X tick
   direction affects Primary X but not Secondary X.**~~
   ✅ Resolved in Phase 4al (CS-63). The renderer now
   splits `ax.tick_params(direction=...)` into five
   per-axis-role calls (primary_x / primary_y / secondary_x
   sibling / secondary_y twin / tertiary_y twin) and the
   wavelength twin's previously-hardcoded `direction="in"`
   reads from `_per_axis_tick_direction(cfg,
   "secondary_x")`. Editing the Secondary X tick direction
   radio in Plot Settings now visually moves only the
   secondary X axis ticks. Test
   `test_secondary_x_distinct_from_primary_x` pins the
   non-collision.

3. 🟡 ~~**USER-FLAGGED Live-preview vs Apply button**
   continues.~~ ✅ Resolved in Phase 4ap (CS-68). All four
   open lock decisions resolved — see the canonical
   register entry above for the full landed shape.
   `PlotConfigDialog` now runs in live-preview mode for
   discrete widgets; text Entries debounce to `<FocusOut>`
   / `<Return>`; Apply button retired. CS-23 / CS-60 / CS-66
   working-copy passthrough partially relaxed (`_snapshot`
   retained for Cancel; `_modified_tabs` semantic broadened
   to "touched since open"). **Canonical resolution
   record** — later cross-refs in 4al/4am/4an/4ao friction
   sections collapse to one-liners pointing here.

4. 🟡 **USER-FLAGGED Apply-to-all icon on per-axis tabs**
   continues. See the new canonical register entry above
   (added in Phase 4ak step 5). Becomes actionable from
   Phase 4al onward — multiple per-axis widgets per tab
   make the broadcast affordance meaningful. **Cross-ref:**
   see canonical register entry "Apply-to-all icon on
   per-axis Plot Settings tabs — UI consistency with
   data-node settings (USER-FLAGGED, Phase 4ak)" above.

5. 🟡 **USER-FLAGGED Axis nomenclature rename
   (primary/secondary/tertiary → bottom/top/left/right
   with `*` suffix for offset)** continues. See the new
   canonical register entry above (added in Phase 4ak
   step 5). Massive cross-codebase rename — CS-44 / CS-50 /
   CS-60 / CS-61 / CS-62 locks all need deliberate
   relaxation. Multi-phase task with high blast radius.
   **Cross-ref:** see canonical register entry "Axis
   nomenclature rename" above.

6. 🟡 **USER-FLAGGED Rich-text axis labels (mathtext /
   subscript / superscript / equations)** continues. See
   the new canonical register entry above (added in Phase
   4ak step 5). Small phase — enabling matplotlib's
   mathtext is essentially free; the lift is testing +
   documenting the gesture. **Cross-ref:** see canonical
   register entry "Rich-text axis labels — subscript /
   superscript / equation markup" above.

7. 🟢 **Dual-surface primary X / Y label
   (Claude-surfaced, Phase 4ak artifact).** The legacy
   "Title and labels" section on Global still carries X
   label / Y label rows (CS-23 → CS-60 invariants) for
   primary_x and primary_y. Phase 4ak's per-axis
   `axis_label_override` is a SECOND surface editing the
   same conceptual label, with override winning via
   precedence: `axes.primary_x.axis_label_override` >
   `xlabel_mode == "custom"` > auto. The dual-surface is
   a discoverability hazard — a user setting the legacy
   Title-and-labels X label won't see it take effect if
   `axis_label_override` is non-empty. A future phase
   could unify by deprecating the legacy rows in favour
   of the cleaner override semantic. Defer until the user
   reports confusion or a refactor phase touches the
   Title-and-labels section. No register entry — folds
   into the canonical per-axis ladder above.

8. 🟢 ~~**`plots_by_role` frozen at dialog open time
   (Claude-surfaced, Phase 4ak artifact).**~~ ✅ **Resolved
   in Phase 4as (CS-72).** The dialog
   stores `self._plots_by_role` at construction; if the
   graph mutates while the dialog is open (e.g. a node
   load / discard / sweep-group change), the Listboxes
   don't refresh. The user must close + reopen the
   dialog to see updated content. Acceptable for now
   (modal dialog UX rarely live-binds to graph state);
   pairs with the user-flagged live-preview register
   entry above — both questions converge on "should the
   dialog be reactive". No register entry; folds into
   the live-preview register entry above. **Phase 4ar
   (CS-70) architectural opening:** the live-refresh
   mechanism CS-70 lands for the `secondary_x_linked`
   greying — host walks `plot_settings_dialog._open_dialogs
   [id(self)]` and calls a public `refresh_*` method on
   the dialog — is **reusable** for this friction. A future
   phase can copy the CS-70 shape: add
   `refresh_plots_by_role(plots)` on `PlotConfigDialog`,
   wire `UVVisTab` to fire it from its `GraphEvent`
   subscribers (`NODE_ADDED` / `NODE_DISCARDED` /
   `NODE_GROUPED`). Pattern is proven; the slot remains
   queued. **Phase 4as adopted the recipe in full** — see
   CS-72 (`refresh_plots_by_role` on dialog + `_notify_plots
   _by_role_change` on host wired into `_on_graph_event`
   for the six role-affecting events; `NODE_STYLE_CHANGED`
   excluded per CS-72 D15 to avoid mid-interaction Move-to
   picker destruction; actual event name is
   `NODE_GROUP_MEMBERS_CHANGED`, not `NODE_GROUPED`).

9. 🟢 **"Plots on this axis" Listbox is `state="disabled"`
   (Claude-surfaced, Phase 4ak artifact).** Read-only
   today (Tk Listbox with disabled state). A future
   enhancement could enable single-click selection to
   navigate to the corresponding node in the sidebar
   ScanTreeWidget (jump-to-node gesture). Pairs naturally
   with the user-flagged apply-to-all-icon register
   entry above (both add interactivity to the per-axis
   tab). No register entry; folds into the canonical
   per-axis ladder above.

10. 🟢 **USER-FLAGGED `TestAppearanceSectionPhase4ae`
    class-name drift after Phase 4ak relocation
    (carry-over from Phase 4aj friction #5).** The test
    class still owns
    `test_tick_direction_factory_default_is_in` and
    `test_factory_reset_restores_new_appearance_keys`,
    BOTH UPDATED in Phase 4ak to read the nested
    `axes[<role>]["tick_direction"]` form. The tests
    stay correct (the schema invariants ARE Appearance-
    section-adjacent in factory-defaults shape), so the
    class name is still the only thing that's misleading.
    Renaming requires a sweep of any test-runner
    invocations targeting the class by name. Defer until
    a future phase naturally touches the class for
    content reasons (e.g. a future Appearance section
    refactor). No register entry — folds in alongside
    the per-axis ladder above.

### Friction points carried forward from Phase 4al

These are concrete obstacles the next Phase 4 session will hit.
Phase 4al shipped CS-63 — the second slice of the per-axis
settings ladder after CS-62's schema invention: the renderer
splits `ax.tick_params(direction=...)` into five per-axis-role
calls (primary_x / primary_y / secondary_x sibling / secondary_y
twin / tertiary_y twin), the wavelength↔energy twin's
previously-hardcoded `direction="in"` reads through
`_per_axis_tick_direction(cfg, "secondary_x")`, and the three
Y-axis tabs gain a Move-to Combobox below their plot-list
Listbox that writes the CS-50 `style["y_axis"]` value via
`graph.set_style`. The Phase 4ak USER-FLAGGED bug (editing
Secondary X tick direction visually moved Primary X instead) is
resolved. The user contributed THREE new USER-FLAGGED register
entries at step 5 (accessibility features umbrella; modeless
dialogs / drop `grab_set` from Plot Settings; retire the global
"Baseline curves" top-bar checkbox now that the per-node
toggle has subsumed it). FOUR Claude-surfaced 🟢 items below
are polish-level and deferrable. **Do not fix until the
relevant subsequent Phase 4 session.**

1. 🟡 ~~**USER-FLAGGED Per-axis settings ladder continues
   ~~(Phase 4am through 4an)~~ (Phase 4an only).**~~
   ✅ Resolved in Phase 4an (CS-65). Cross-ref Phase 4ai
   friction #1 above — ladder fully closed.

2. 🟡 **USER-FLAGGED Accessibility features umbrella.** See
   the new canonical register entry above (added in Phase
   4al step 5). Open-ended architectural question — first
   batch likely keyboard shortcuts (pairs with the existing
   USER-FLAGGED register entry) + colour-blind-safe palette
   swap + Escape-dismiss audit + font-scale multiplier.
   Becomes actionable any time; reasoning level **extra-high**
   for the first design pass (scope decision + lock decisions
   span ~5 sub-axes), **normal** for individual sub-batches
   thereafter.

3. ~~🟡 **USER-FLAGGED Modeless dialogs — drop `grab_set` from
   Plot Settings.** See the new canonical register entry
   above (added in Phase 4al step 5). One-line change to
   `plot_settings_dialog.py:584`; lock relaxation across
   CS-06 / CS-23 / CS-60. StyleDialog already modeless per
   CS-05 — playbook exists. Pairs naturally with the
   existing Phase 4ak USER-FLAGGED "Live-preview vs Apply"
   register entry; together they form the most natural
   evolution of CS-06's modal contract. Reasoning level:
   **normal** if scoped to Plot Settings only; **extra-high**
   if scoped to all CS-23 modals.~~ ✅ Resolved in Phase 4ao
   (CS-66).

4. ~~🟡 **USER-FLAGGED Retire global "Baseline curves" top-bar
   checkbox.** See the new canonical register entry above
   (added in Phase 4al step 5). Per-node CS-36 toggle in
   the data panel has subsumed the global CS-29 toggle.
   Small phase — half a day at most. Reasoning level:
   **normal**.~~ ✅ Resolved in Phase 4ao (CS-67).

5. 🟡 ~~**USER-FLAGGED Live-preview vs Apply button**
   continues.~~ ✅ Resolved in Phase 4ap (CS-68). Cross-ref
   Phase 4ak friction #3 above (canonical resolution
   record).

6. 🟡 **USER-FLAGGED Apply-to-all icon on per-axis tabs**
   continues. Cross-ref Phase 4ak friction #4. Now more
   actionable: per-axis tabs carry three real widgets
   (tick_direction + axis_label_override from Phase 4ak +
   the Phase 4al Move-to Combobox). See canonical register
   entry "Apply-to-all icon on per-axis Plot Settings tabs"
   above.

7. 🟡 **USER-FLAGGED Axis nomenclature rename** continues.
   Cross-ref Phase 4ak friction #5. Phase 4al's CS-63
   inherits CS-62's locks unchanged for axis role names —
   the rename's blast radius (CS-44 / CS-50 / CS-60 / CS-61
   / CS-62 / CS-63) grows by one CS-section per ladder
   phase. See canonical register entry "Axis nomenclature
   rename" above.

8. 🟡 **USER-FLAGGED Rich-text axis labels (mathtext)**
   continues. Cross-ref Phase 4ak friction #6. Independent
   of the per-axis ladder. See canonical register entry
   "Rich-text axis labels" above.

9. 🟢 **Cancel-with-pending semantics for routing edits
   (Claude-surfaced, Phase 4al artifact).** The Move-to
   Combobox writes `style["y_axis"]` immediately via
   `graph.set_style` — bypassing the dialog's working-copy
   model. Consistent with CS-50 Style-dialog behaviour
   (per-node style edits commit on pick across the whole
   app) but ASYMMETRIC with the rest of Plot Settings'
   Apply/Save/Cancel contract: the user can route a plot
   from primary_y to secondary_y, click Cancel, and the
   routing change persists. The asymmetry is intentional
   (working-copy makes no sense for per-node style edits)
   but worth documenting for users. Folds naturally into
   the USER-FLAGGED Live-preview register entry above —
   the reconciliation that phase ships should explicitly
   address per-node-style edits' commits-on-pick model.
   No register entry; folds into live-preview.

10. 🟢 **Move-to picker silent-no-op without listbox row
    (Claude-surfaced, Phase 4al artifact).** Selecting a
    Combobox value with no Listbox row selected silently
    no-ops — the combobox resets to its empty placeholder
    but no toast / tooltip / hint label says "Select a
    plot first". A user accustomed to error feedback might
    be briefly confused. Polish-level; could surface a
    Tooltip via the existing `tooltip.py` (CS-42) or an
    inline status label below the Combobox. No register
    entry; folds into the per-axis ladder above.

11. 🟢 **Label-collision tie-breaker is first-match-wins
    (Claude-surfaced, Phase 4al artifact).** If two visible
    nodes on the same source axis share a label, the
    `_on_route_plot_from_dialog` host method routes only
    the first match (in `_spectrum_nodes()` →
    `_second_derivative_nodes()` → `_peak_list_nodes()`
    iteration order). Rare in practice (labels are
    typically unique within a graph) but could surprise a
    user. Mitigations: (a) require unique labels via a
    sidebar validation (existing CS-33 label-edit gate
    already enforces some discipline); (b) walk EVERY
    match and route them all (current label-collision
    model is "first match" — could become "all matches");
    (c) prompt the user with a node-ID picker. Polish-
    level; no register entry; folds into the per-axis
    ladder above.

12. 🟢 **Combobox virtual event dispatch unreliable in suite
    mode (Claude-surfaced, Phase 4al testing artifact).**
    During Phase 4al test development, `event_generate("<<ComboboxSelected>>")`
    fired synchronously in isolation but intermittently
    dropped when the full suite had populated/destroyed
    many Toplevels first (5 tests originally failed).
    Refactor: extracted the closure handler into
    `PlotConfigDialog._on_move_to_choose(role, listbox,
    var)` so tests call the method directly. The
    underlying Tk event dispatch behaviour was not
    investigated — could be a Tk version interaction or
    matplotlib TkAgg canvas grab leakage from prior test
    classes. The refactored testing pattern (extract
    closure → method; tests bypass event system) is
    worth applying to any other event-driven UI tests
    that exhibit similar flakiness. No register entry;
    surface if it bites again.

### Friction points carried forward from Phase 4am

These are concrete obstacles the next Phase 4 session will hit.
Phase 4am shipped CS-64 — the third slice of the per-axis settings
ladder after CS-62 (schema invention) and CS-63 (per-axis tick
rendering + Move-to picker). `_AXIS_KEYS` grew from 2 → 6 with
`range_lo` / `range_hi` / `autoscale` / `scale`; every per-axis
tab gains three new widget rows (Range Entry pair, Autoscale
Checkbutton, Scale Combobox); the renderer reads each axis's own
`cfg["axes"][role][...]` slot via four new module-level helpers.
Legacy top-bar `_xlim_lo` / `_ylim_lo` Tk vars stay the fallback
when `autoscale=True` (default). User had nothing to add at step
5 elicitation. Four Claude-surfaced 🟢 polish notes below are
deferrable. **Do not fix until the relevant subsequent Phase 4
session.**

1. 🟡 ~~**USER-FLAGGED Per-axis settings ladder continues —
   Phase 4an only.**~~ ✅ Resolved in Phase 4an (CS-65).
   Cross-ref Phase 4ai friction #1 above — ladder fully
   closed (all five canonical slots resolved).

2. 🟡 **USER-FLAGGED Accessibility features umbrella**
   continues. Cross-ref Phase 4al friction #2. See
   canonical register entry "Accessibility features
   umbrella". Reasoning level: **high** for the first
   design pass, **medium** for individual sub-batches.

3. ~~🟡 **USER-FLAGGED Modeless dialogs — drop `grab_set`
   from Plot Settings** continues. Cross-ref Phase 4al
   friction #3. Pairs naturally with the Phase 4ak
   USER-FLAGGED "Live-preview vs Apply" register entry.
   Reasoning level: **medium** if scoped to Plot Settings
   only; **high** if scoped to all CS-23 modals.~~ ✅ Resolved
   in Phase 4ao (CS-66).

4. ~~🟡 **USER-FLAGGED Retire global "Baseline curves"
   top-bar checkbox** continues. Cross-ref Phase 4al
   friction #4. Small phase — half a day at most.
   Reasoning level: **medium**.~~ ✅ Resolved in Phase 4ao
   (CS-67).

5. 🟡 ~~**USER-FLAGGED Live-preview vs Apply button**
   continues.~~ ✅ Resolved in Phase 4ap (CS-68). Cross-ref
   Phase 4ak friction #3 above (canonical resolution
   record).

6. 🟡 **USER-FLAGGED Apply-to-all icon on per-axis tabs**
   continues. Cross-ref Phase 4al friction #6. Even more
   actionable now: per-axis tabs carry five widget rows
   (tick_direction + axis_label_override + Range Entry pair
   + Autoscale Checkbutton + Scale Combobox + Move-to
   Combobox on Y tabs). See canonical register entry
   "Apply-to-all icon on per-axis Plot Settings tabs".

7. 🟡 **USER-FLAGGED Axis nomenclature rename** continues.
   Cross-ref Phase 4al friction #7. CS-64 inherits CS-62 /
   CS-63 locks unchanged — the rename's blast radius now
   covers CS-44 / CS-50 / CS-60 / CS-61 / CS-62 / CS-63 /
   CS-64. See canonical register entry.

8. 🟡 **USER-FLAGGED Rich-text axis labels (mathtext)**
   continues. Cross-ref Phase 4al friction #8. Independent
   of the per-axis ladder. See canonical register entry.

9. 🟢 **Range Entry edits don't trigger immediate `_redraw`
   (Claude-surfaced, Phase 4am artifact).** The per-axis
   Range Entry pair and the Autoscale Checkbutton + Scale
   Combobox all write into the dialog's working copy and
   only render on Apply (or Save). The legacy top-bar
   Entries (Range, near `_clear_xlim` / `_clear_ylim`
   buttons) DO have an immediate-on-edit hook via their
   `_on_xmin_changed` / etc. callbacks. A user expecting
   typing to update the plot live will be briefly confused.
   By design — CS-06 working-copy model — but exactly the
   kind of asymmetry the USER-FLAGGED "Live-preview vs
   Apply button" register entry already exists to address.
   No new register entry; folds into live-preview.

10. 🟢 **Top-bar legacy Tk vars + schema range bounds can
    drift silently (Claude-surfaced, Phase 4am artifact).**
    Sequence: (1) user types `0.3` into the top-bar Y Entry
    (with default schema `autoscale=True`) → writes only to
    `_ylim_lo` Tk var; renderer honours it as fallback;
    plot clamps to 0.3. (2) User opens Plot Settings → Primary
    Y tab → unchecks Autoscale (now `autoscale=False`).
    (3) Renderer now reads schema `range_lo` (empty string)
    → no bound → plot autoscales freely. The `0.3` top-bar
    value is silently ignored. This is by design (working-copy
    boundary), but worth a tooltip on the Autoscale
    Checkbutton clarifying the fallback chain ("Autoscale on:
    top-bar Range fallback applies. Autoscale off: only the
    Range entries above apply."). Polish-level; no register
    entry; folds into the per-axis ladder.

11. 🟢 **Secondary X range Entries silent-no-op without active
    twin (Claude-surfaced, Phase 4am artifact).** The
    Secondary X tab's Range / Autoscale / Scale widgets only
    apply to the matplotlib `sec` (wavelength↔energy sibling)
    when the twin is active (cm-1 primary unit AND
    show-nm-axis checked). Editing them with the twin inactive
    silently no-ops — same surface as a secondary_y tab edit
    when no secondary_y plots exist. Documented in the helper
    docstring. Folds naturally into the USER-FLAGGED Twin-X
    register entry above. No new register entry.

12. 🟢 **`_do_apply` vs `_apply` naming discoverability
    (Claude-surfaced, Phase 4am testing artifact).** When
    writing widget-Apply round-trip tests, instinct was to
    call `dlg._apply()` — that's an AttributeError; the
    actual method is `_do_apply`. Caused one test failure
    during Phase 4am Commit 2 development that was
    immediately resolved. The `_do_` prefix convention is
    consistent across the dialog (`_do_apply`, `_do_save`,
    `_do_cancel`, `_do_factory_reset`) and matches CS-23's
    naming, but the bare `apply` parameter name on the
    `open_plot_config_dialog` factory creates a discoverability
    cliff. Polish-level; consider adding a "Test entry points"
    docstring section listing `_do_apply` / `_do_save` /
    `_do_cancel` / `_do_factory_reset` as the canonical
    test hooks. No register entry; surface if it bites again.

### Friction points carried forward from Phase 4an

These are concrete obstacles the next Phase 4 session will hit.
Phase 4an shipped CS-65 — the **final canonical slice** of the
per-axis settings ladder. `_AXIS_KEYS` grew from 6 → 10 with
`tick_major` / `tick_minor` / `grid_show` / `axis_color`. Every
per-axis tab gains four new widget rows (tick-spacing Entry pair,
Show gridlines Checkbutton, Axis colour swatch + `colorchooser`
picker Button). The renderer reads each axis's own slot via five
new module-level helpers (`_parse_tick_str` / `_per_axis_tick_
major` / `_per_axis_tick_minor` / `_per_axis_grid` /
`_per_axis_color`) applied at five call sites. `cfg["grid"]`
remains the master switch; per-axis `grid_show` overrides apply
on `primary_x` and `primary_y` (twin axes share the primary grid).
User had nothing to add at step 5. Five Claude-surfaced notes
below — one renderer-bug-fix surfaced by the integration tests
(grid-styling-kwargs override visible=False, already fixed in
commit 5) plus four 🟢 polish notes. **Do not fix until the
relevant subsequent Phase 4 session.**

1. 🟡 **USER-FLAGGED Accessibility features umbrella**
   continues. Cross-ref Phase 4am friction #2. See canonical
   register entry "Accessibility features umbrella". Reasoning
   level: **high** for the first design pass (scope decision +
   lock decisions span ~5 sub-axes), **medium** for individual
   sub-batches thereafter (keyboard shortcuts, colour-blind
   palette, Escape-dismiss audit, font-scale).

2. ~~🟡 **USER-FLAGGED Modeless dialogs — drop `grab_set` from
   Plot Settings** continues. Cross-ref Phase 4am friction #3.
   Pairs naturally with the USER-FLAGGED "Live-preview vs Apply"
   register entry. Reasoning level: **medium** if scoped to
   Plot Settings only; **high** if scoped to all CS-23 modals.~~
   ✅ Resolved in Phase 4ao (CS-66). `grab_set()` dropped from
   `PlotConfigDialog.__init__`; `transient(parent)` retained for
   WM Z-order grouping. CS-06 one-per-host uniqueness invariant
   preserved.

3. ~~🟡 **USER-FLAGGED Retire global "Baseline curves" top-bar
   checkbox** continues. Cross-ref Phase 4am friction #4.
   Small phase — half a day at most. Reasoning level: **medium**.~~
   ✅ Resolved in Phase 4ao (CS-67). `_show_baseline_curves`
   BooleanVar + top-bar Checkbutton + `_redraw` outer guard all
   deleted. CS-36's per-node `style["show_baseline_curve"]` is now
   the single source of truth (default True — overlays now render
   by default).

4. 🟡 ~~**USER-FLAGGED Live-preview vs Apply button** continues.~~
   ✅ Resolved in Phase 4ap (CS-68). Cross-ref Phase 4ak friction
   #3 above (canonical resolution record). Phase 4am friction (θ)
   (Range Entry no-immediate-`_redraw`) is now resolved as a side
   effect — the Range Entries debounce to `<FocusOut>` / `<Return>`
   per the CS-68 text-Entry policy.

5. 🟡 **USER-FLAGGED Apply-to-all icon on per-axis tabs**
   continues. Cross-ref Phase 4am friction #6. Even more
   actionable now: per-axis tabs carry **nine** widget rows
   each (tick_direction + axis_label_override + Range Entry
   pair + Autoscale Checkbutton + Scale Combobox + Tick
   spacing Entry pair + Show gridlines Checkbutton + Axis
   colour picker + Move-to Combobox on Y tabs). Reasoning
   level: **medium**.

6. 🟡 **USER-FLAGGED Axis nomenclature rename** continues.
   Cross-ref Phase 4am friction #7. CS-65 inherits CS-62 /
   CS-63 / CS-64 locks unchanged — the rename's blast radius
   now covers CS-44 / CS-50 / CS-60 / CS-61 / CS-62 / CS-63 /
   CS-64 / CS-65. See canonical register entry. Reasoning
   level: **extra-high**.

7. 🟡 **USER-FLAGGED Rich-text axis labels (mathtext)**
   continues. Cross-ref Phase 4am friction #8. Independent
   of the per-axis ladder (which is now closed). Reasoning
   level: **medium**.

8. 🟡 **USER-FLAGGED External-output plot style presets**
   carries forward from Phase 4aj. See canonical register
   entry. Independent of the per-axis ladder. User has
   reference Jupyter notebook code (paths TBD at session
   start). Reasoning level: **high** (five open lock
   decisions; new `_OUTPUT_PRESETS` registry).

9. 🟡 **USER-FLAGGED Keyboard shortcuts — first batch.**
   Carry-over from Phase 4ah. Self-contained. Pairs with the
   accessibility umbrella above. Reasoning level: **medium**.

10. 🟢 **matplotlib grid-styling override quirk (Claude-
    surfaced, Phase 4an artifact — already fixed).** Calling
    `ax.grid(False, axis="x", linestyle=":", alpha=0.4,
    color=...)` ENABLES the grid because matplotlib interprets
    the presence of styling kwargs as "you must have meant
    visible=True", overriding the explicit `False`. The
    Phase 4an renderer wiring caught this in commit 5
    integration tests; the per-axis-disable branch now calls
    `ax.grid(False, axis=...)` with NO styling kwargs.
    Documented inline in the renderer; surfaced here so the
    next phase touching gridline code knows the trap exists.
    No register entry.

11. 🟢 **`grid_show` on non-primary tabs is schema-only
    (Claude-surfaced, Phase 4an artifact).** The Checkbutton
    renders on all five per-axis tabs for ladder consistency,
    but the renderer ignores `grid_show` for `secondary_x` /
    `secondary_y` / `tertiary_y` (twin axes share the primary's
    grid). A user toggling the box on a non-primary tab gets
    no visible feedback beyond the inline "(twin axes share
    the primary grid)" hint label. Three resolution paths
    when this surfaces: (a) hide the box on non-primary tabs,
    (b) show a disabled box, (c) actually implement
    per-twin-axis grids. Currently option (a)-adjacent via
    the hint; defer until reported. No register entry.

12. 🟢 **`tick_minor` doesn't force minor ticks to render
    (Claude-surfaced, Phase 4an artifact).** Setting
    `tick_minor: "0.05"` installs the MultipleLocator but
    doesn't call `ax.minorticks_on()` — if matplotlib's
    minor ticks are disabled (some themes do this), the
    minor ticks stay invisible despite the locator. Fix
    requires either a renderer-side `ax.minorticks_on()`
    call when `_per_axis_tick_minor` is non-None, or
    documenting the "set major to see minor" expectation.
    Polish-level; folds into a future "tick rendering
    polish" sub-batch (or the accessibility umbrella's
    visibility audit). No register entry.

13. 🟢 **`_AXIS_KEYS` is now 10 entries — readability cliff
    approaches (Claude-surfaced, Phase 4an artifact).** The
    factory-default per-role sub-dict on each of the five
    axes is now a 10-key dict. If a future polish slice
    adds more keys (e.g. label rotation, padding,
    formatter), consider grouping into nested sub-dicts
    (`axes[role]["limits"]["lo"]`, `axes[role]["ticks"]
    ["major"]`, etc.) for readability — but this is a
    schema-refactor decision that pairs naturally with the
    USER-FLAGGED `_USER_DEFAULTS` tab-type split (Phase
    4ai canonical entry). Not urgent. No register entry.

14. 🟢 **Colour swatch is a `tk.Frame`, not a ttk widget
    (Claude-surfaced, Phase 4an artifact).** The per-axis
    Axis Colour row uses `tk.Frame(bg=hex)` for the swatch
    with `relief="solid"` + `bd=1` for the border. Renders
    fine on Windows but not cross-platform-verified —
    macOS may need a `ttk.Frame` + style for the border
    to paint as expected. Defer until cross-platform
    feedback surfaces. No register entry.

### Friction points carried forward from Phase 4ao

These are concrete obstacles the next Phase 4 session will hit.
Phase 4ao landed two small USER-FLAGGED follow-ups bundled into one
phase: CS-66 (modeless Plot Settings — `grab_set()` dropped, main
window stays interactive while the dialog is open; `transient(parent)`
retained for WM Z-order grouping; CS-06 one-per-host uniqueness
preserved) AND CS-67 (retired the global "Baseline curves" top-bar
Checkbutton + `_show_baseline_curves` BooleanVar + `_redraw` outer
guard — CS-36's per-node `style["show_baseline_curve"]` is now the
single source of truth, default True so overlays render by default).
User had nothing to add at step 5. Five Claude-surfaced notes
below — none rise to register-entry severity. **Do not fix until
the relevant subsequent Phase 4 session.**

1. 🟡 **USER-FLAGGED Accessibility features umbrella**
   continues. Cross-ref Phase 4an friction #1. See canonical
   register entry "Accessibility features umbrella". Reasoning
   level: **high** for the first design pass, **medium** for
   individual sub-batches thereafter.

2. 🟡 ~~**USER-FLAGGED Live-preview vs Apply button** continues.~~
   ✅ Resolved in Phase 4ap (CS-68). Cross-ref Phase 4ak friction
   #3 above (canonical resolution record).

3. 🟡 **USER-FLAGGED Apply-to-all icon on per-axis tabs**
   continues. Cross-ref Phase 4an friction #5. Reasoning
   level: **medium**.

4. 🟡 **USER-FLAGGED Axis nomenclature rename** continues.
   Cross-ref Phase 4an friction #6. Massive cross-codebase
   rename. Reasoning level: **extra-high**.

5. 🟡 **USER-FLAGGED Rich-text axis labels (mathtext)**
   continues. Cross-ref Phase 4an friction #7. Reasoning
   level: **medium**.

6. 🟡 **USER-FLAGGED External-output plot style presets**
   continues. Cross-ref Phase 4an friction #8. User has
   reference Jupyter notebook code (paths TBD at session
   start). Reasoning level: **high**.

7. 🟡 **USER-FLAGGED Keyboard shortcuts — first batch**
   continues. Cross-ref Phase 4an friction #9. Pairs with
   the accessibility umbrella. Reasoning level: **medium**.

8. 🟢 **`grab_status()` return-value variation across Tk
   builds (Claude-surfaced, Phase 4ao artifact).** On the
   Phase 4ao Tk build `grab_status()` returns `None` when no
   grab is held; some other builds return the literal empty
   string `""`. The Phase 4ao test sweep accepts both via
   `assertFalse(status)`. If a future modeless-related test
   regresses with `assertEqual(status, "")`, the failure
   mode is opaque — the docstring on
   `test_no_grab_set_on_visible_window` names the gotcha.
   No register entry.

9. 🟢 ~~**Modeless + per-node baseline-toggle integration
   surface is uncovered.**~~ ✅ Covered in Phase 4ap (CS-68) by
   `TestUVVisTabLivePreviewModelessPhase4ap.test_per_row_toggle_
   redraws_canvas_with_dialog_open` — opens Plot Settings,
   toggles per-row `~` on a BASELINE row, asserts the dashed
   overlay disappears AND the dialog stays alive. The flow now
   has explicit regression coverage.

10. 🟢 ~~**`_plots_by_role` staleness is now more reachable
    (Claude-surfaced, Phase 4ao artifact).**~~ ✅ **Resolved
    in Phase 4as (CS-72).** Cross-ref the canonical entry
    at Phase 4ak ε (now ✅). The modeless reachability
    concern is moot — CS-72 live-refreshes the per-axis
    Listboxes on every role-affecting graph event.

11. 🟢 **Default-flip surface for legacy `.ptmg` projects
    (Claude-surfaced, Phase 4ao artifact).** With the global
    Baseline-curves gate retired and CS-36's per-node default
    being True, any `.ptmg` project saved before CS-36 (or
    saved with the global gate off) will display baseline
    overlays the user didn't see before. This is the
    documented intent of the default flip but worth a manual
    smoke check on the first reload of a pre-CS-36 project.
    No register entry — expected behaviour, surfaced here so
    the next session knows the user-visible delta exists.

12. 🟢 ~~**`scan_tree_widget.py:822` still mentions the
    "CS-29 global ``Baseline curves`` checkbox".**~~ ✅ Resolved
    in Phase 4ap (CS-68 commit `a6b07ea`) — comment refreshed
    to credit CS-67 / Phase 4ao for the retirement and CS-36
    as the now-single source of truth.

### Friction points carried forward from Phase 4ap

These are concrete obstacles the next Phase 4 session will hit.
Phase 4ap shipped CS-68 — live-preview semantics on the unified
`PlotConfigDialog`. Discrete widgets (Combobox, Checkbutton,
Spinbox, color picker, Radiobutton) commit every edit immediately
to the live config and fire `on_apply`; text Entries (`title_text`
/ `xlabel_text` / `ylabel_text`, per-axis `axis_label_override`,
`range_lo` / `range_hi`, `tick_major` / `tick_minor`, plus the
Global mirror `axis_label_override`) defer to `<FocusOut>` /
`<Return>` so per-keystroke typing does not redraw a 100-spectrum
canvas. Apply button retired; button row collapses to `Save ·
Apply to All Tabs · Cancel`. Defaults / Factory Reset coalesces
to one redraw. New `TestPlotConfigDialogLivePreviewPhase4ap` (14
sentinels) and `TestUVVisTabLivePreviewModelessPhase4ap` (3
integration tests, including the modeless × per-row baseline
toggle flow) pin the contract. The user contributed THREE new
USER-FLAGGED items at step 5 (cross-node Style dropdown / multi-
node window; wavelength secondary axis broken — B-005; Autoscale
↔ Range Entry seed semantics). Four Claude-surfaced notes below
are polish-level and deferrable. **Do not fix until the relevant
subsequent Phase 4 session.**

1. 🟡 **USER-FLAGGED Cross-node Style dropdown / multi-node
   style window.** See the new canonical register entry above
   (added in Phase 4ap step 5). Becomes actionable any time —
   open scope question is "extend `PlotConfigDialog` with a new
   Notebook tab" vs "spawn a new sibling modeless dialog". Pairs
   with CS-05 / CS-06 / CS-66 / CS-68. Reasoning level:
   **extra-high** for the first design pass + lock decisions
   (5 lock decisions span dialog scope + dropdown semantics +
   refresh-on-graph-event interaction + ∀ apply-to-all
   coexistence + cross-tab vs UVVIS-only scope), **high** for
   the implementation phase that follows.

2. 🟠 ~~**USER-FLAGGED Wavelength secondary axis broken (B-005).**~~
   ✅ Resolved Phase 4aq (CS-69) — commits `aedfd81` + `cdd6f61`
   + `df2542a` + `ab6a178`. Root cause was matplotlib's linked
   secondary axis being corrupted by the CS-64 `set_xlim`
   path back-propagating through the inverse of `_fwd`.
   Renderer no longer calls `sec.set_xlim` / `sec.set_xscale`;
   new `custom_ticks` schema key + FixedLocator path; dialog
   greys range / autoscale / scale on Secondary X tab when
   link active; D8 extension covers both cm⁻¹ and eV unit
   paths. See B-005 row in the Known Bugs table below (✅).

3. 🟡 ~~**USER-FLAGGED Autoscale ↔ Range Entry seed semantics.**~~
   ✅ **Resolved in Phase 4as (CS-71).** The canonical
   register entry above is now ✅. Two-way binding mechanism:
   parallel `_axis_range_display_vars` populated from
   `_compute_axis_displayed_limits()` post-redraw; Entry
   textvariable swaps on autoscale toggle.

4. 🟡 **USER-FLAGGED Apply-to-all icon on per-axis tabs**
   continues. Cross-ref Phase 4ao friction #3. Even more
   actionable now that live-preview shipped — the "I changed
   the tick direction on Primary Y, now I want it on every Y
   axis" gesture has no affordance, and the live commit means
   every per-axis change requires manual repetition. Reasoning
   level: **medium**.

5. 🟡 **USER-FLAGGED Accessibility features umbrella**
   continues. Cross-ref Phase 4ao friction #1. Reasoning
   level: **high** for the first design pass, **medium** for
   individual sub-batches thereafter.

6. 🟡 **USER-FLAGGED Axis nomenclature rename** continues.
   Cross-ref Phase 4ao friction #4. Massive cross-codebase
   rename. Reasoning level: **extra-high**.

7. 🟡 **USER-FLAGGED Rich-text axis labels (mathtext)**
   continues. Cross-ref Phase 4ao friction #5. Reasoning
   level: **medium**.

8. 🟡 **USER-FLAGGED External-output plot style presets**
   continues. Cross-ref Phase 4ao friction #6. User has
   reference Jupyter notebook code (paths TBD at session
   start). Reasoning level: **high**.

9. 🟡 **USER-FLAGGED Keyboard shortcuts — first batch**
   continues. Cross-ref Phase 4ao friction #7. Pairs with
   the accessibility umbrella. Reasoning level: **medium**.

10. 🟢 ~~**`_plots_by_role` staleness even more reachable now
    (Claude-surfaced, Phase 4ap artifact).**~~ ✅ **Resolved
    in Phase 4as (CS-72).** Cross-ref the canonical entry at
    Phase 4ak ε (now ✅). The "live-preview makes staleness
    worse" concern landed correctly — and CS-72 closes it.

11. 🟢 **Text Entry `<FocusOut>` debounce vs click-elsewhere
    (Claude-surfaced, Phase 4ap artifact).** The CS-68 text-
    Entry policy fires the live commit on `<FocusOut>` /
    `<Return>`. `<FocusOut>` triggers reliably when the user
    Tabs to another widget OR clicks another widget that
    accepts focus (other Entry / Spinbox). It does NOT trigger
    when the user clicks on a Tk Label or empty dialog space —
    those don't take focus, so the Entry retains it. The
    typed value is still in `_working` (the trace fired) but
    the live commit waits until focus moves. In practice the
    Save button click (focus shift to button) flushes the
    pending edit. Acceptable — but worth a manual smoke check
    if a user reports "I typed and clicked Save but nothing
    happened" symptoms. No register entry.

12. 🟢 **Text Entry mode-flip cascade fires per-keystroke
    commit on `title_text` / `xlabel_text` / `ylabel_text`
    (Claude-surfaced, Phase 4ap artifact).** When the user
    types into the title/label Entry while the mode is
    currently "auto" or "none", the first keystroke flips
    `mode_var` to "custom" — mode_var's trace IS in the
    discrete-commit path, so it fires `_apply_changes_live`
    immediately. Subsequent keystrokes don't flip mode again
    so they correctly defer. Net effect: ONE redraw per text
    Entry session, on the first keystroke. Strictly an
    improvement vs the canonical "no commit until FocusOut"
    semantic but worth documenting. No register entry.

13. 🟢 **`_apply_changes_live` deep-copy cost grows with
    per-axis schema (Claude-surfaced, Phase 4ap artifact).**
    The live commit calls `copy.deepcopy(self._working)` on
    every discrete-widget edit. The working copy now carries
    a nested `axes` sub-dict with five role entries × ~10 keys
    each (CS-61 → CS-65 ladder) — totalling ~50 dict ops per
    deepcopy. Negligible at current scale; if future per-axis
    work doubles the schema width or if the user makes
    sustained Spinbox-arrow edits, profile the deepcopy.
    Alternative: key-level diff + apply (more code, faster).
    No register entry. *Phase 4aq update: schema grew to 11
    keys per role (now 55 dict ops per deepcopy) — still
    negligible.*

### Friction points carried forward from Phase 4aq

These are concrete obstacles the next Phase 4 session will hit.
Phase 4aq shipped CS-69 — the B-005 wavelength-secondary-axis
fix. The renderer at `uvvis_tab.py:_redraw` now NEVER calls
`sec.set_xlim` / `sec.set_xscale` on the matplotlib-linked
secondary X axis (matplotlib's `secondary_xaxis(functions=(_fwd,
_fwd))` API owns the link via the forward function; the
buggy CS-64 `set_xlim` path back-propagated through the inverse
and corrupted the primary axis). The CS-64 schema's `range_lo`
/ `range_hi` / `autoscale` / `scale` keys for `secondary_x`
are inert when the link is active; the dialog greys those
widgets via the new `secondary_x_linked: bool` constructor
kwarg. New per-axis schema key `custom_ticks` (D6b uniform,
CS-65 ladder grew from 10 → 11) carries the user's
comma-separated explicit nm positions and paints `FixedLocator`
major ticks via the new `_apply_major_locator` helper. D8 lock
relaxation extends the wavelength link to BOTH cm⁻¹ (via
`1e7 / x`) and eV (via `_HC_NM_EV / x`); both are self-inverse.
The user contributed FOUR new USER-FLAGGED items at step 5 —
all four were explicitly queued for the next phase as small
polish fixes. **Do not fix until the relevant subsequent Phase
4 session.**

1. 🟡 ~~**USER-FLAGGED `plot_widget.py` Compare tab has the same
   buggy `sec.set_xlim` pattern as the pre-CS-69 UVVisTab.**~~
   ❌ **Dropped in Phase 4ar (CS-70) after evidence-based
   investigation.** `plot_widget.py` has zero `sec.set_xlim` /
   `sec.set_xscale` calls on its `secondary_xaxis`, zero
   `cfg["axes"]` schema, zero `plot_settings_dialog` per-axis
   integration. The trigger condition above ("if the user
   toggles it ON with a populated
   `cfg["axes"]["secondary_x"]["range_lo"]` / `range_hi`")
   cannot be reached because that schema isn't wired into the
   Compare tab at all — its UI is a flat toolbar of Tk vars,
   not the schema-driven per-axis tab Notebook from CS-60+.
   The "mirror" was speculative architecture forecasting "if
   Compare adopts the schema later", not a present bug. **Moot
   until Compare adopts the per-axis schema.** See CS-70 §
   "Item 1 dropped" for the full reasoning.

2. 🟡 ~~**USER-FLAGGED Live-refresh of `secondary_x_linked`
   greying when the user toggles `λ(nm) axis` with the dialog
   open.**~~ ✅ **Resolved in Phase 4ar (CS-70).** New
   `PlotConfigDialog.refresh_axis_link_state(linked)` public
   method + internal `_apply_secondary_x_link_greying()`. Host
   (`UVVisTab._notify_axis_link_state_change`) walks
   `plot_settings_dialog._open_dialogs[id(self)]` (CS-66
   registry) and calls the refresh method. Fired from
   `_on_unit_change` and from `_nm_cb`'s new `_on_nm_cb_toggle`
   command. CS-69 D4 lock explicitly relaxed. **Lock decisions
   resolved:** (i) direct host→dialog notification path (not a
   shared event bus — minimal coupling, reuses `_open_dialogs`);
   (ii) `_modified_tabs` markers persist across refresh (test
   pin `test_refresh_does_not_clear_modified_tabs`); (iii)
   refresh does NOT route through `_apply_changes_live` (test
   pin `test_refresh_does_not_trigger_apply_changes_live`).
   17 unit tests + 15 host-side integration tests. **The same
   architectural shape is now reusable for the long-standing
   `_plots_by_role` staleness carry-forward** (Phase 4ak ε /
   Phase 4ao τ / Phase 4ap τ) — a future phase can copy
   CS-70's pattern (`refresh_plots_by_role(plots)` on the
   dialog, fired from host graph-event subscribers). **Phase
   4as adopted the recipe** — see CS-72 (Phase 4as friction
   section below).

3. 🟡 ~~**USER-FLAGGED `λ(nm) axis` Checkbutton stays visible
   when `unit == "nm"`.**~~ ✅ **Resolved in Phase 4ar (CS-70).**
   New `UVVisTab._update_nm_cb_state()` disables `_nm_cb` and
   forces `_show_nm_axis` False when `_x_unit == "nm"`. Mirrors
   `plot_widget.py:1232–1239`'s symmetric pattern on the
   Compare tab (which had this feature from inception). Called
   once after `_nm_cb` is built (initial paint state: DISABLED
   because default unit is "nm") and on every `_on_unit_change`.
   Forced-False decision matches Compare-tab contract — state
   does NOT persist across nm round-trips; user re-checks if
   they re-want the wavelength secondary axis after a nm
   detour. 7 dedicated tests in
   `TestUVVisTabLiveLinkStatePhase4ar`.

4. 🟡 ~~**USER-FLAGGED greying label hard-codes "while the λ(nm)
   toggle is on" — slightly misleading when `unit == "eV"`.**~~
   ✅ **Resolved in Phase 4ar (CS-70).** New wording: "Range /
   Autoscale / Scale are derived from the primary axis while
   the wavelength secondary axis is shown — use Custom ticks
   above to name explicit nm positions." Covers both cm⁻¹ and
   eV unit cases under the D8 relaxation. Sentinel test
   `test_greying_label_wording_phase4ar` pins the new text and
   asserts the old "λ(nm) toggle is on" framing is absent.

### Friction points carried forward from Phase 4ar

These are concrete obstacles the next Phase 4 session will hit.
Phase 4ar landed CS-70 — three of the four Phase 4aq carry-
forward USER-FLAGGED polish items bundled into one wavelength-
secondary-axis follow-up: live-refresh of the secondary-X
greying replaces CS-69's D4 snapshot-at-open lock with a
host→dialog notification path via the existing
`_open_dialogs[id(self)]` registry (CS-66) + new public
`PlotConfigDialog.refresh_axis_link_state(linked)` +
`_apply_secondary_x_link_greying()` internal method (widget-
state only, does NOT mutate `_working`, trigger
`_apply_changes_live`, or clear `_modified_tabs`); new
`UVVisTab._update_nm_cb_state()` / `_on_nm_cb_toggle()` /
`_notify_axis_link_state_change()` methods; `_on_unit_change`
chains update → notify → redraw; `_nm_cb`'s command moves
from `self._redraw` to `self._on_nm_cb_toggle`; toolbar nm-cb
greys when `_x_unit == "nm"` (forces `_show_nm_axis` False);
greying label rephrased to cover both cm⁻¹ and eV under D8.
The fourth carry-forward item (Phase 4aq item 1 — Compare-tab
`plot_widget.py` CS-69 mirror) was **dropped** after
evidence-based investigation: `plot_widget.py` has zero
`sec.set_xlim` / `sec.set_xscale` calls on its secondary, zero
`cfg["axes"]` schema, no `plot_settings_dialog` per-axis
integration — the trigger condition cannot be reached.
USER had nothing to add at step 5. **No new carry-forward
items.** The bundle was scoped tight; nothing surfaced during
implementation. **Architectural opening:** CS-70's host→dialog
notification pattern (host walks `_open_dialogs[id(self)]` +
calls a public `refresh_*` method on the dialog) is reusable
for the long-standing `_plots_by_role` staleness friction
(Phase 4ak item #8 ε / Phase 4ao item #10 τ / Phase 4ap
item #10) — a future phase can copy the shape:
`refresh_plots_by_role(plots)` on the dialog, fired from
host `GraphEvent` subscribers. Pattern is proven; the slot
remains queued as a separate friction (see Phase 4ak item #8
for canonical reference). **Do not fix until the relevant
subsequent Phase 4 session.** **Phase 4as adopted the
recipe** — see Phase 4as friction section below.

### Friction points carried forward from Phase 4as

These are concrete obstacles the next Phase 4 session will hit.
Phase 4as bundled **two CS-70-pattern adoptions** in one
session: CS-71 (Autoscale ↔ Range Entry seed + live ax-limit
display) closes the USER-FLAGGED Phase 4ap friction where the
per-axis `range_lo` / `range_hi` Entries showed stale schema
values while `autoscale=True`; CS-72 (live-refresh of
`_plots_by_role` inventory) closes the long-standing
Claude-surfaced friction chain (Phase 4ak ε / Phase 4ao τ /
Phase 4ap τ / Phase 4ap item #10) where the Plot Settings
per-axis "Plots on this axis" Listbox was frozen at
dialog-open time. Both adopt CS-70's host→dialog
notification pattern via `_open_dialogs[id(self)]`; the
canonical `refresh_*(state)` + `_notify_*_change()` recipe
is now used by three concrete refresh methods (CS-70 link
greying / CS-71 displayed limits / CS-72 plots inventory).
**Lock relaxations:** CS-64 D8 (per-axis range Entry's
textvariable swaps between canonical schema StringVar and
parallel display StringVar based on autoscale state) and
CS-66 (`_on_destroy` filters on `event.widget is self` to
survive CS-72's destroy-rebuild Tk event propagation —
pre-existing latent fragility CS-72 surfaced). No schema keys
added — PTMG_FORMAT_VERSION unchanged. USER had nothing to add
at step 5. **One new carry-forward item** (α below) plus a
clean **architectural-opening closure note**.

1. 🟢 **`NODE_GROUP_MEMBERS_CHANGED` is missing from
   `_on_graph_event`'s `_redraw` trigger list (Claude-surfaced,
   Phase 4as artifact).** The pre-existing dispatch at
   `uvvis_tab.py:_on_graph_event` triggers `_redraw` for
   NODE_ADDED / NODE_DISCARDED / NODE_ACTIVE_CHANGED /
   NODE_STYLE_CHANGED / NODE_LABEL_CHANGED / GRAPH_LOADED /
   GRAPH_CLEARED — but **not** NODE_GROUP_MEMBERS_CHANGED.
   Grouping or ungrouping nodes today doesn't repaint the
   plot (only the sidebar updates via its own listener). CS-72
   correctly fires `_notify_plots_by_role_change` for that
   event so the dialog's Listbox updates, but the plot visual
   stays stale until some other event triggers `_redraw`. Pre-
   existing issue surfaced during the CS-72 wiring pass; not
   in Phase 4as scope. Suggested fix: add
   `GraphEventType.NODE_GROUP_MEMBERS_CHANGED` to the existing
   `_redraw` trigger tuple at `uvvis_tab.py:_on_graph_event`
   (one-line change). Reasoning level: **low** — narrow
   single-token addition + 1 regression test. Could be
   bundled into any larger Phase 4at intent at near-zero
   marginal cost.

2. ✅ **Architectural opening from Phase 4ar closed.** Phase
   4ar's bookkeeping flagged the CS-70 host→dialog notification
   pattern as reusable for the `_plots_by_role` staleness chain.
   Phase 4as adopted it in CS-72 (plots inventory) AND extended
   it to a second target (CS-71 displayed limits). The canonical
   recipe is now well-trodden — `refresh_*(state)` public on
   dialog with the widget-state-only contract (no `_working`
   touch, no `_apply_changes_live`, no `_modified_tabs` clear),
   plus `_notify_*_change()` on host that looks up
   `_open_dialogs[id(self)]` and fires from the appropriate
   state-mutation site. Any Phase 4at intent that needs a
   fourth `refresh_*` method has a polished pattern to copy
   (e.g. Cross-node Style dropdown's Combobox refresh on
   NODE_ADDED, when that intent is picked).

3. 🟢 **D15 (CS-72) edge case during empty-graph
   transitions.** Initial Phase 4as implementation fired CS-72
   from `_draw_empty` end as well; `_redraw` falls through to
   `_draw_empty` when no live nodes exist, which would have
   leaked CS-72 firings into NODE_STYLE_CHANGED-triggered
   redraws on empty graphs (a vacuously safe leak — no nodes →
   no Move-to picker to destroy — but a lock violation).
   Resolved in Commit 4 by removing the CS-72 fire from
   `_draw_empty`; explicit `_on_graph_event` +
   `_on_unit_change` + `_on_nm_cb_toggle` are the sole CS-72
   sources. CS-71 fires from both `_redraw` end AND
   `_draw_empty` end (safe — no widget-destruction risk).
   No carry-forward; documented here for the pattern's
   future adoptions.

4. ✅ **Pre-existing CS-66 `_on_destroy` fragility
   surfaced + fixed.** Tk's `<Destroy>` event propagates up the
   widget tree; the pre-CS-72 `_on_destroy` handler did NOT
   filter on `event.widget is self`. Pre-CS-72 this was
   latent (no destroy-rebuild paths existed in the dialog).
   CS-72's `refresh_plots_by_role` destroys children of plots-
   block parents; those events bubbled up to the Toplevel
   and popped the dialog from `_open_dialogs` mid-lifetime.
   Fixed in Commit 3 with a defensive `event.widget is self`
   filter (CS-66 lock relaxation, documented in CS-72). The
   pattern's other adopters benefit too — any future
   destroy-rebuild path now operates on a robust handler.

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
| **B-005** | ✅ Phase 4aq | USER-FLAGGED at end of Phase 4ap (step 5): "wavelength as linked secondary axis is broken". **Resolved Phase 4aq (CS-69)** — commits `aedfd81` (pure module), `cdd6f61` (27 unit tests), `df2542a` (dialog integration + greying), `ab6a178` (18 integration tests). Root cause: the secondary X axis at `uvvis_tab.py:2585–2613` was already using matplotlib's linked `secondary_xaxis("top", functions=(_fwd, _fwd))` API, but the renderer then called `sec.set_xlim(...)` whenever `cfg["axes"]["secondary_x"]["autoscale"]=False` carried non-empty `range_lo` / `range_hi` (CS-64 schema). On matplotlib's linked secondary axis the `set_xlim` call back-propagates through the inverse of `_fwd` and **corrupts the primary axis's xlim** — user-visible as the wavelength axis "going stale" or the primary axis snapping to unexpected limits. Companion issue: `tick_major` (MultipleLocator) produced evenly-spaced ticks in cm⁻¹ / eV that didn't land on round nm positions. Fix: (1) the renderer NEVER calls `sec.set_xlim` / `sec.set_xscale` — matplotlib owns linked limits via the forward function; the `secondary_x` schema's `range_lo` / `range_hi` / `autoscale` / `scale` keys become inert when the link is active. (2) New per-axis schema key `custom_ticks: str` (comma-separated explicit positions, e.g. `"300, 400, 500, 700, 900"`) paints `FixedLocator` major ticks via the new `_apply_major_locator` helper. (3) D8 lock relaxation: link extends to BOTH `unit == "cm-1"` (via `1e7 / x`) and `unit == "eV"` (via `_HC_NM_EV / x`); the same `_show_nm_axis` Tk var gates both branches. (4) Dialog greying state-machine: new `secondary_x_linked: bool` constructor kwarg the host snapshots at dialog open; when True, the Secondary X tab's `range_lo` / `range_hi` / `autoscale` / `scale` widgets render `state="disabled"` so the user can't push values into them. `custom_ticks` / `tick_major` / `tick_minor` stay editable — they're the user's real affordances on the linked axis | CS-44 / CS-61–65 / `uvvis_tab._redraw` | ✅ Resolved Phase 4aq (CS-69) |

The Phase 4d responsive-row work (B-002) also needs to add `visible`
and `in_legend` controls to the StyleDialog universal section so the
collapsed row's controls remain reachable through the dialog.

Newly discovered bugs go in this table with a fresh `B-NNN` id and a
phase assignment. Resolved bugs get a ✅ in the Severity column with
the resolving phase + commit SHA appended to the row.

---

*Document version: 1.44 — May 2026*
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
*1.15: Phase 4p — canvas-driven responsive layout (CS-30) +
suppress identical re-applies (CS-31). CS-32 (inline expansion
+ per-variant gestures on sweep-group rows) was bundled at
decision lock but deferred to Phase 4q after CS-30 took longer
than expected. Three register entries logged up front; two
marked ✅ at landing. Phase 4n friction #4 (responsive helper
redundant Configure work) struck through — substantially
mitigated because the per-row `<Configure>` storm that
motivated it no longer fires; the threshold-band caching
register entry stays ⏳ as defer-until-flicker-observed. Phase
4n friction #5 (⌥n digit overflow) struck through for the
threshold-decision impact (CS-30 keys on canvas width, not row
natural width); the visual-shape decision register entry stays
⏳. Phase 4k friction #2 (sweep-group rows hide per-variant
gestures) annotated with "frequency reduced by CS-31" but
remains open for CS-32. Phase 4p friction logged (four items):
🔴 CS-32 deferred to 4q, 🔴 CS-31 status-message
discoverability folded into the existing Diagnostic console
intent (USER-FLAGGED), 🔴 Long node-name labels overflowing
canvas width (USER-FLAGGED, new register entry), test-fragility
process note. One new register entry: 🔴 Truncate long node-
name labels in ScanTreeWidget rows (USER-FLAGGED). 540 tests,
all green.*
*1.16: Phase 4q — sweep-group inline expansion (CS-32),
label truncation with hover tooltip (CS-33), and per-row 🔒
commit gesture on provisional ScanTreeWidget rows (CS-34).
Three register entries marked ✅ (CS-32 promotes BACKLOG row
187 from ⏳ as well; the merged Phase 4k/4p sweep-group entry
collapses to a cross-ref to its canonical successor). Phase
4k friction #2 (sweep-group rows hide per-variant gestures)
struck through — fully resolved by CS-32. Phase 4p friction #1
(CS-32 deferred to 4q) struck through. Phase 4p friction #3
(long node-name labels overflowing canvas width) struck
through — resolved by CS-33 with shape (a) truncate-with-
tooltip. Phase 4k friction #1 (no left-pane accept gesture)
annotated with "frequency reduced by CS-34" and dropped from
🔴 to 🟡 — the right-sidebar half is in place; the left-pane
button-pair remains the open follow-up. Three new register
entries (all 🟢, none USER-FLAGGED): cap-from-canvas-width
follow-up to CS-33, promote `_Tooltip` on first cross-module
re-use, indent expanded sub-frames inside sweep groups. Phase
4q friction logged (five items): 🟡 left-pane Accept-last
still open, 🟢 hardcoded `_LABEL_MAX_CHARS`, 🟢 `_Tooltip`
co-location, tooltip-rendering process note (no register),
🟢 sweep-group nesting visual indent. 561 tests, all green
(540 + 21 new: 5 in TestTruncateLabel, 3 in TestTooltip, 1 in
TestExpandedSweepGroupsField, 6 in TestSweepGroupInlineExpansion,
3 in TestProvisionalRowCommitButton, 3 in
TestLabelTruncationInRow).*
*1.17: Phase 4r — sweep-group member visual nesting (CS-35) and
per-node baseline-curve toggle (CS-36). Two register entries
marked ✅ (the sweep-group nesting entry promoted from Phase 4q
friction #5; the per-node baseline-curve toggle from Phase 4o
friction #1). Step 5 elicitation produced two ground-up USER-
FLAGGED feature register entries that are larger than the
phase that elicited them: 🔴 Project + per-node persistence
with manifest+sidecar+optional-blockchain-anchor architecture
(four-phase ladder; subsumes the existing Plot config persistence
row as Phase A); 🔴 Floor-zero baseline as fit-time constraint,
per mode (universal toggle with per-mode `compute_*`
constrained-fit branches; reframes the previous CS-24 follow-up
to be the narrower scattering+offset additive variant). Phase 4r
friction logged (seven items): 🟡 [~] toggle has no tooltip,
🟢 `~` glyph cosmetic, 🟢 style-key project-save round-trip,
🟢 legend + baseline both render `–`, 🔴 USER-FLAGGED
persistence umbrella (item 5), 🔴 USER-FLAGGED floor-zero
(item 6), process note on step-5 surfacing strategic intent.
579 tests, all green (561 + 18 new).*
*1.18: Phase 4s — combined floor-zero scattering + scattering+
offset + fit helpers + nm-range error widening (CS-37 / CS-38 /
CS-39 / CS-40). Two register entries marked ✅ ("Scattering
baseline fitted-offset (CS-24 follow-up)" → CS-38;
"Floor-zero baseline" partially-resolved with 3/6 modes done
in CS-37, register entry stays ⏳ until linear/polynomial/spline
ship). Phase 4m friction #2 (scattering n="fit" loses resolved
n) struck through — resolved by CS-39. Phase 4m friction #3
(composite scattering+offset) struck through — resolved by
CS-38. Phase 4m friction #4 (fit-window error data range)
struck through — resolved by CS-40. Phase 4r friction #6
(floor-zero per mode) struck through with partial-completion
note (3/6 modes shipped). Four new register entries: 🟡 USER-
FLAGGED Floor-zero toggle disabled state for unsupported
baseline modes, 🟡 USER-FLAGGED Consolidate scattering+offset
into scattering with optional offset toggle, 🟢 Scattering
n-fit scan bounds configurable via params, 🔴 USER-FLAGGED
OLIS .ols / .asc UV/Vis file format support. Phase 4s
friction logged (seven items): 🟡 USER-FLAGGED greyed-toggle,
🟡 USER-FLAGGED scattering+offset UX consolidation,
🟢 hardcoded scan bounds, 🟡 fit-twice process note,
🟢 `c_fitted`/`a_fitted` not surfaced (folds into Diagnostic
console), 🟢 SLSQP failure path uncovered, 🔴 USER-FLAGGED
OLIS file reader (item 7). 615 tests, all green (579 + 36
new: 28 pure-module in test_uvvis_baseline + test_uvvis_normalise;
8 integration in test_uvvis_tab.TestUVVisTabBaseline).*
*1.19: Phase 4t — combined A+E+R+N intent: completes the
floor-zero per-mode roadmap (CS-37 expansion to all 6 modes
via SLSQP), adds the n_bounds API hook (CS-41), promotes
Tooltip to its own module with three consumers (CS-42), and
ships the floor-zero disabled-state machinery as defensive
scaffolding (CS-43). Three register entries marked ✅
(Floor-zero per mode → CS-37 expansion; Floor-zero disabled
state → CS-43; Promote Tooltip — was a Phase 4q friction
section entry → CS-42). One register entry partial-marked
(Scattering n-fit scan bounds: API ✅ / UI ⏳ → CS-41).
Phase 4q friction #3 + Phase 4r friction #1 struck through
(both resolved by CS-42 — the paired Tooltip promotion +
[~] toggle hover hint). Phase 4r friction #6 fully-struck
(was partial after Phase 4s; now ✅ Resolved across Phase 4s
+ Phase 4t). Phase 4s friction #1 struck through (resolved
by CS-43). Phase 4s friction #3 partial-struck (API ✅ /
UI ⏳ matching the register row). Three new USER-FLAGGED
register entries from step 5: 🟡 Per-row [~] toggle column
alignment across all node types; 🟡 Second-derivative plot
on separate right y-axis; 🟡 Top-bar Open File / Reload
buttons belong to TDDFT only. Phase 4t friction logged
(five items): 🟡 USER-FLAGGED [~] column alignment (item
1), 🟡 USER-FLAGGED 2nd-derivative right-axis (item 2),
🟡 USER-FLAGGED top-bar TDDFT-only (item 3),
🟢 _FLOOR_ZERO_SUPPORTED_MODES dead code today (item 4),
🟢 polynomial z-space conditioning pattern (item 5). 637
tests, all green (615 + 22 net new: 19 pure-module in
test_uvvis_baseline; 7 integration in test_uvvis_tab +
test_scan_tree_widget; 1 replaced; 4 removed from
TestFloorZeroNotYetImplemented).*
*1.20: Phase 4u — multi-axis plot routing lands (CS-44).
SECOND_DERIVATIVE renders on a lazily-created right y-axis;
the architecture broadens to a per-NodeType role table
(`_DEFAULT_Y_AXIS_BY_NODETYPE`) plus a tertiary offset-spine
machinery wired but unused, so a future NodeType (Beer-Lambert
concentration, difference spectra, MCR component profile)
lands as a one-line table edit. X-unit-aware secondary y-label
("d²A/dλ²" / "d²A/d(cm⁻¹)²" / "d²A/dE²"). Phase 4t friction
#2 struck through (resolved by CS-44). One register entry
flipped ✅ (Second-derivative plot on separate right y-axis →
CS-44, broadened from the originally-flagged shape per the
user's "may need other secondary axes / 3rd y-axis somehow"
expansion). Eight new USER-FLAGGED register entries from
step 5: 🔴 Auditable provenance for data processing protocols;
🔴 Baseline as separate first-class node + node algebra for
linear combinations; 🟡 Multinode dataset import + combination
for joint analytics; 🟡 SVD + multinode chemometric methods;
🟡 Dynamic sidebar auto-width for long labels; 🟡 Detachable
sidebar windows; 🟡 Colour-blind-safe palette;
🟢 Parallelize heavy-compute paths. Three CS-44-derived
register entries: 🟡 `_absorbance_to_y` corruption on %T;
🟢 per-style y_axis override hook + StyleDialog row;
🟢 hover/status-bar readout for active y-axis;
🟢 plot_widget abstraction lift + `_TERTIARY_AXIS_OFFSET_FRAC`
Plot Settings promotion (folded into one combined entry).
Phase 4u friction logged (eleven items): items 1–8 mirror
the eight new USER-FLAGGED register entries; items 9–11 are
the CS-44 follow-ups (%T conversion bug, per-style override
deferral, plot_widget lift + hover readout). 651 tests, all
green (637 + 14 new: 9 pure-helper in TestMultiAxisRoutingHelpers
+ 5 integration in TestUVVisTabSecondDerivativeIntegration /
TestUVVisTabTertiaryAxisPath; 3 existing SECOND_DERIVATIVE
assertions updated to the new "primary has 1, secondary has 1"
shape).*
*1.21: Phase 4v — per-OperationType implementation hash (CS-45)
+ persistence Phase A manifest+sidecar round-trip (CS-46) land
together. Two prior 🔴 USER-FLAGGED register rows flipped ✅ —
"Auditable provenance / process versioning for data processing
protocols" (Phase 4u friction #1) and "Plot config + plot defaults
persistence to project.json" (Phase 4l). The umbrella row "Project
+ per-node persistence with manifest+sidecar+optional-blockchain-
anchor architecture" gains a Phase A ✅ partial mark; B / C / D
remain ⏳. Seven new USER-FLAGGED register entries from step 5:
🔴 Drop CS-31 dedup + introduce user-driven node groups; 🔴
Adjustable sidebar still not working (bumped from 🟡, scope
expanded to per-cell minimum widths); 🟡 Trash can for discarded
nodes; 🟡 Project-specific plot defaults + import from another
project; 🟡 Refactor uvvis_tab.py — extract host shell + cross-
tab generalization; 🟡 Plot data markers / points + per-style
marker config; 🟢 Test efficiency + per-phase metrics tracking.
Plus six Phase-4v-specific deferrals: 🟡 Re-run all changed ops
at load (CS-45 follow-up); 🟡 Original instrument file
persistence (Phase A follow-up); 🟢 .ptmg zip-archive form;
🟢 Sidecar GC across saves; 🟡 _restore_workflow_payload only on
UVVisTab; resolved-mid-phase entry "Modal Tk messagebox during
tests" (✅ via _test_silence module). 708 tests, all green
(651 + 45 new pure-module: 8 in test_nodes_metadata_field +
15 in test_operation_hash + 22 in test_project_io; + 12 new
integration in test_persistence_phase_a covering apply-site
stamping for all six op types, save→load round-trip,
_restore_workflow_payload, and the implementation-mismatch
surface).*
*1.22: Phase 4w — adjustable-sidebar UX work (CS-47 + CS-48)
lands together. Four prior register rows flipped ✅ —
"Per-row `[~]` toggle column alignment across all node types"
(Phase 4t friction #1; resolved as a fixed-width row_toggle
Frame slot, cheaper than the originally-proposed disabled-
button-on-every-row); "Dynamic sidebar auto-width for long
node labels" (Phase 4u friction #5, the canonical sidebar
entry); "Compute label-truncation cap from canvas width /
font metrics" (Phase 4q friction #2); "Adjustable sidebar
still not working" (Phase 4v friction #2, the bumped 🔴 entry
that referenced Phase 4u friction #5). Three new USER-FLAGGED
register entries from step 5: 🔴 Inter-panel parent-type
acceptance gaps (baseline can't run on smoothed; smoothing
can't run on second-derivative); 🟡 Configurable secondary-
plot pane layout (above/below main at adjustable fraction);
🟡 UI lexicon doc (workflow vs project, etc.). Three new 🟢
CS-47 follow-ups: cross-tab sash calibration extraction
(pairs with the existing refactor entry); re-calibrate on
first NODE_ADDED (user-confirmed); measure actual row
overhead instead of static estimate. CS-47 ships
`_label_char_capacity` pure helper + `_CELL_MIN_PX`
documented vocabulary + `_SIDEBAR_MIN_WIDTH_PX = 240` pinned
floor + `widest_label_pixel_width` measurement +
`UVVisTab._calibrate_sidebar_width` one-shot via
after_idle. CS-48 ships the fixed-width `row_toggle` Frame
slot at `_CELL_MIN_PX["row_toggle"] = 22` so labels start at
the same x across every node type. 738 tests, all green
(708 + 30 new: 12 pure-module across TestCellMinPxVocabulary
+ TestSidebarMinWidth + TestLabelCharCapacity; 18 integration
across TestRowToggleColumnAlignment + TestDynamicLabelCap
Wiring + TestWidestLabelPixelWidth +
TestUVVisTabSidebarCalibration). The existing
TestPerNodeBaselineCurveToggle helper updated to recurse into
the new row_toggle slot; no behavioural test changes.*
*1.23: Phase 4x — cross-type panel parent acceptance widening
(CS-49). Resolves Phase 4w friction #1 (USER-FLAGGED 🔴 —
"Cannot do baseline correction from a smoothed spectrum.
Cannot smooth derivative plots."). Two tuples widened:
`UVVisTab._BASELINE_ACCEPTED_PARENT_TYPES` from `(UVVIS,
BASELINE)` to `(UVVIS, BASELINE, SMOOTHED)`;
`SmoothingPanel.ACCEPTED_PARENT_TYPES` from `(UVVIS, BASELINE,
NORMALISED, SMOOTHED)` to add `SECOND_DERIVATIVE`.
`UVVisTab._refresh_shared_subjects` extended to walk both
`_spectrum_nodes()` and `_second_derivative_nodes()` so the
combobox surfaces derivative rows; `_spectrum_nodes` itself
untouched (the renderer uses both helpers as separate
iterations for axis-role routing under CS-44). Audit-pass
result: NormalisationPanel / PeakPickingPanel /
SecondDerivativePanel intentionally NOT widened — existing
exclusions are deliberate per panel-side comments; user has
not flagged. Each unchanged tuple is now pinned by an
audit-stability `test_accepted_parent_types_constant`.
Smoothed-of-derivative output's y-axis misroute (carries
SMOOTHED → "primary" axis under CS-44) deferred to the open
T (per-style `y_axis` override hook) carry-forward. Four new
USER-FLAGGED register entries from step 5: 🟡 Loaded Spectra
responsive layout drops ✕ when swatch reappears at
intermediate widths (suspected `_label_overhead_px` /
optional-cell-visibility coupling, pairs with Phase 4w
friction #6); 🟡 StyleDialog must surface ALL node-table
parameters incl. label rename + tighten organisation for
scale; 🟡 Per-node parameter window add a Provenance tab; 🟡
"Add to graph" gesture from a node's Provenance tab. One new
🟢 Claude-surfaced CS-49 follow-up: visual cue for derivative
entries in the shared combobox. Phase 4x friction logged
(eight items): 🟡 USER-FLAGGED Loaded Spectra responsive
layout (#1), 🟡 USER-FLAGGED StyleDialog parameter coverage
(#2), 🟡 USER-FLAGGED Provenance tab (#3), 🟡 USER-FLAGGED
"Add to graph" gesture (#4), 🟢 derivative combobox visual
cue (#5), 🟢 USER-NOTED smoothed-of-derivative misroute
elevation cross-ref (#6, → carry-forward T), 🟢 inline
baseline tuple drift cross-ref (#7, → Phase 4k friction #6),
🟢 USER-NOTED tuple terminology lexicon candidate (#8, →
carry-forward C). Three pre-existing contract tests rewritten
to match the new behaviour (the "SECOND_DERIVATIVE not in
combobox" inversion + the SMOOTHED-baseline-now-enabled
half). 746 tests, all green (738 + 8 new: 3 in
TestSmoothingPanel for SECOND_DERIVATIVE acceptance + 5 in
new TestUVVisTabPhase4xCrossTypeAcceptance for end-to-end
flows + audit stability + combobox order).*
*1.24: Phase 4y — per-style `y_axis` override hook + StyleDialog
Combobox row (CS-50). Closes the carry-forward T from Phase 4u
Decision 1 (USER-LOCKED "Default only for now is okay"; the
deferral was the canonical Phase 4u friction #10 register entry,
now ✅) and Phase 4x friction #6 (smoothed-of-derivative
misroute, USER-NOTED) in one phase. `node_styles.default_spectrum_style`
adds `style["y_axis"]: str | None` (default None = follow
NodeType default; non-None = literal CS-44 axis role overrides
per-node); `uvvis_tab._resolve_y_axis_role` grows an optional
`style: Mapping | None = None` argument with a one-line short-
circuit at the front (override beats default; malformed values
fall through). Renderer threads `node.style` at three call sites
(per-node main loop; BASELINE-curve dashed overlay moved INSIDE
per-bn body so main + overlay land on the same axis; PEAK_LIST
scatter moved INSIDE per-peak loop). StyleDialog universal
section gains a read-only `ttk.Combobox` row labelled "Y axis:"
with options `["(default)", "primary", "secondary", "tertiary"]`;
"(default)" round-trips to `None`. `_BULK_UNIVERSAL_KEYS`
intentionally NOT extended (parallel to Phase 4d's `visible` /
`in_legend` carve-out — bottom ∀ would too easily collapse
derivatives onto primary); per-row ∀ button widens its scope to
every renderable node via `_on_uvvis_apply_to_all`'s special-
case for the key. `SmoothingPanel._apply` writes
`style["y_axis"] = parent_effective_role` on cross-typed
outputs (today: smoothed-of-derivative → "secondary"). Decision
lock taken: (i) cross-typed-Apply auto-inheritance fires IFF
NodeType-defaults differ; (ii) "(default)" = literal None
semantics, inheritance is a separate apply-time mechanism; (iii)
y_axis bulk-fan-out scope = renderable nodes only. Three new
Claude-surfaced register entries from step 5: 🟡 Y-axis Combobox
row appears on non-UVVis StyleDialog instances; 🟢 per-NodeType
primary y-label gap when override reroutes nodes; 🟢 DRY cross-
typed-Apply y_axis inheritance helper (architectural debt).
Phase 4y friction logged (six items): 🟡 non-UVVis Combobox
reach (#1), 🟢 primary y-label gap (#2), 🟢 inheritance helper
DRY (#3), 🟡 Phase 4u friction #9 priority bump (#4 cross-ref),
🟢 panel-`_apply` tuple-shape doc-debt (#5), 🟢 "(default)"
label could be more descriptive (#6). 781 tests, all green
(746 + 35 new: 7 pure-helper in TestResolveYAxisRoleStyleOverride
+ 2 in TestDefaultSpectrumStyle + 16 in TestStyleDialogYAxisOverride
+ 4 in TestUVVisTabPhase4yYAxisOverride + 3 in
TestUVVisTabPhase4yCrossTypedInheritance + 3 in
TestUVVisTabPhase4yApplyToAllScope). The
`TestUVVisTabTertiaryAxisPath` monkey-patched resolver widened
to `(node_type, style=None)` in lockstep with the helper
signature; `test_per_row_buttons_emit_one_call_per_universal_key`
asserts nine per-row ∀ buttons (was eight) and includes
`y_axis` in the expected key list.*
*1.25: Phase 4z — width-aware label-cell overhead helper (CS-51).
Closes Phase 4x friction #1 (USER-FLAGGED Loaded Spectra row drops
the ✕ when the swatch reappears at intermediate sash widths) AND
Phase 4w friction #6 (measure actual row overhead). Two new pure
module-level helpers in `scan_tree_widget.py` —
`_compute_label_overhead_px(visible_optional_cells=())` and
`_visible_optional_cells_for_width(width_px)` — and a width-aware
`_label_overhead_px(width=None)` instance method whose width-aware
path sums the always-visible cell mins PLUS the optional cells
revealed at the current canvas width per CS-26's
`_RESPONSIVE_THRESHOLDS_PX`. `_current_label_cap` forwards the
canvas width into it so the dynamic label cap shrinks the moment
the swatch (or leg / ls_canvas) reappears at its reveal threshold,
preventing the right-side cells (incl. the ✕) from being clipped.
Calibration site (`_calibrate_sidebar_width`) keeps the no-args
path — byte-equivalent to Phase 4w. Decisions taken: (i)
architecture (a) — width-aware overhead, NOT post-pack
`winfo_reqwidth()`; (ii) cap recompute lifecycle unchanged (every
`_apply_responsive_layout` call); (iii) NO change to
`_RESPONSIVE_THRESHOLDS_PX` integer values (CS-26 lock preserved;
only CS-47 lock relaxes for the `_label_overhead_px` signature).
Three new Claude-surfaced 🟢 friction items captured at step 5
without new register entries: calibration still uses the no-args
path (may undershoot by up to 84 px); floor clamping at 239→240
masks the visual cue (right-side cells still un-clipped, but
label-truncation diff hidden); `_OVERHEAD_SLACK_PX = 30` is a
heuristic constant. 805 tests, all green (781 + 24 new: 7 in
TestComputeLabelOverheadPx + 7 in TestVisibleOptionalCellsForWidth
+ 5 in TestLabelOverheadPxWidthAware + 5 in
TestDynamicLabelCapWiringPhase4z).*
*1.26: Phase 4aa — StyleDialog y-axis visibility predicate +
label-rename Entry (CS-52). Closes Phase 4y friction #1 in full
(Claude-surfaced "Y-axis Combobox row appears on non-UVVis
StyleDialog instances") and the "first concrete add" half of
Phase 4x friction #2 (USER-FLAGGED "StyleDialog must surface ALL
node-table parameters incl. label rename"). New module-private
`_Y_AXIS_VISIBLE_NODETYPES: frozenset[NodeType]` mirrors
`uvvis_tab._DEFAULT_Y_AXIS_BY_NODETYPE.keys()` exactly; the
universal-section `_build_y_axis_row` call is gated by
`if self._node_type in _Y_AXIS_VISIBLE_NODETYPES`, suppressing the
Combobox on the seven non-routing NodeTypes (TDDFT / FEFF_PATHS /
XANES / EXAFS / DEGLITCHED / AVERAGED / BXAS_RESULT) where it was
a misleading affordance. Drift test pins the gate to the routing
table so a future routing-table widening cannot silently re-
introduce the affordance. New "Label:" Entry at the top of the
universal grid; live `trace_add('write')` callback commits each
keystroke through the new `_write_label_partial` helper, which
routes via `graph.set_label` (label is a top-level DataNode slot,
not a style key) under the same `_suspend_writes` re-entrancy
guard `_write_partial` uses. `__init__` snapshots `node.label`;
`_do_cancel` reverts both label and style. `_on_graph_event`
gains a `NODE_LABEL_CHANGED` branch that refreshes the Entry +
the dialog title in place (sibling rename gestures from the
sidebar's CS-33 path or another open dialog flow through the
same path). Lock decisions taken: (i) DEFER — single-pane with
"Label:" at top this phase; LabelFrame re-org + tabbed-shape
question pairs with Phase 4x friction #3 + #4 (Provenance tab +
"Add to graph" gesture) in a future combined intent; (ii) NO
inline validation — match CS-33's sidebar gesture behaviour;
(iii) NO widget lifts — universal rows preserve relative order.
Six new Claude-surfaced 🟢 friction items captured at step 5
without new register entries: tighten-organisation half stays
open; live-trace per-keystroke event volume; two rename gestures
coexist; `_Y_AXIS_VISIBLE_NODETYPES` structurally coupled to
routing table; Phase 4y friction #2 narrower in scope but still
open; Cancel always re-emits snapshot label. 832 tests, all
green (805 + 27 new: 2 in TestStyleDialogPhase4aaConstants + 15
in TestStyleDialogYAxisVisibility + 10 in
TestStyleDialogLabelRename).*
*1.27: Phase 4ab — StyleDialog Notebook restructure + Provenance
tab (CS-53). Closes Phase 4x friction #3 (USER-FLAGGED "Per-node
parameter window: add a Provenance tab") in full plus the
"tabbed shape" half of Phase 4x friction #2's lock decision (i).
Dialog body becomes a `ttk.Notebook` with Tab 1 "Style" hosting
today's universal + conditional sections verbatim (rows + relative
ordering preserved per the CS-52 lock relaxation; only the parent
widget changes) and Tab 2 "Provenance" hosting the read-only
ancestor walk. Bottom Apply / ∀ / Save / Cancel row stays outside
the Notebook so it's visible regardless of which tab is active.
Three new module-level constants — `_NOTEBOOK_TAB_TITLES` (tuple
locking tab order); `_PROVENANCE_STATE_DISPLAY` (NodeState →
display text + foreground colour with DISCARDED dimmed grey
#888888); `_PROVENANCE_REFRESHING_EVENTS` (the five graph-event
types that mutate the displayed walk: NODE_LABEL_CHANGED /
NODE_DISCARDED / NODE_COMMITTED / NODE_ADDED / EDGE_ADDED). Three
new pure helpers (`_provenance_state_display`,
`_format_provenance_op_params`, `_format_provenance_node_summary`)
reduce graph nodes to display strings — Tk-free, fully unit-
tested. Provenance tab uses a Canvas + Scrollbar pair with an
inner Frame; eager construction at `__init__` (Decision (ii));
single scrolling column (Decision (iii)). Each per-ancestor block
carries a header (bold label · type · state badge) plus, for
OperationNodes, a Courier body block with pretty-printed sorted
params, engine + version, and a 12-char-prefix truncated
implementation hash; the `unregistered:` sentinel from CS-45
survives truncation as an explicit suffix marker. DISCARDED
ancestors render unfiltered with the dimmed foreground (Decision
(iv)). `_on_graph_event` restructured to run a Provenance rebuild
before the existing same-node early-return; the `_suspend_writes`
guard still gates BOTH halves so the dialog's own keystroke-driven
label rename does NOT rebuild Provenance per keystroke (perf
trade-off; bottom-of-chain block briefly stale during typing).
`graph.provenance_chain` reused as the ancestor walk source — no
`graph.py` change. Phase 4x friction #3 register entry marked ✅;
Phase 4x friction #4 ("Add to graph" gesture) now unblocked;
Phase 4x friction #2 register entry's "tabbed shape" half closed,
LabelFrame groupings half stays carry-forward. Phase 4aa friction
#1 marked ~~struck through~~ ✅ Partly resolved (the tabbed-shape
half — LabelFrame groupings half stays carry-forward, narrowed in
scope). Six new Claude-surfaced 🟢 friction items captured at
step 5 without new register entries (user invoked /loop continue
as the step 5 answer): mouse-wheel scrolling not bound to
Provenance Canvas; implementation hash truncation opaque; op-node
parents not shown; self-keystroke leaves bottom-of-chain stale;
refresh fires for any node not just ancestors; no "as of"
indicator. 878 tests, all green (832 + 46 new: 22 pure-module
helpers in `TestStyleDialogPhase4abHelpers` + 9 Notebook structure
in `TestStyleDialogPhase4abNotebook` + 15 Provenance tab in
`TestStyleDialogPhase4abProvenanceTab`).*
*1.28: Phase 4ac — drop CS-31 dedup short-circuit + retire CS-32
sweep auto-grouping machinery (CS-54). Closes the (a) + (b) parts
of Phase 4v friction #1 (USER-FLAGGED "Drop CS-31 + introduce
user-driven node groups"); the (c) part — user-driven NODE_GROUP
container — stays carry-forward to a future phase. Retroactive
entry inserted in Phase 4ae per Phase 4ad friction #5 ✅.*
*1.29: Phase 4ad — y-axis label routing follows NodeType, not
axis side (CS-55). Closes Phase 4ac friction #1 (USER-FLAGGED
🔴) in full plus Phase 4y friction #2 and Phase 4aa friction
#5 (same root issue, struck through). The user reproduced the
bug end-to-end at end of Phase 4ac (placing Absorbance on
secondary and a derivative on primary left the Absorbance
label on the empty left axis and the right side unlabelled);
Phase 4ad's fix is structural — labels are role-agnostic,
dimensionalised by NodeType class instead. New
`_ABSORBANCE_SPACE_NODETYPES: frozenset[NodeType]` covering
UVVIS / BASELINE / NORMALISED / SMOOTHED / PEAK_LIST +
`_ABSORBANCE_Y_LABEL` y-unit → label dict, plus pure helper
`_resolve_y_axis_label(node_type, x_unit, y_unit)`:
absorbance-space NodeTypes label by y-unit (independent of
x-unit and role); derivative-space NodeTypes fall through to
the existing CS-44 `_NON_PRIMARY_Y_LABEL` table (which now
feeds both primary and non-primary roles). Renderer in
`_redraw` widens `first_node_type_per_role.setdefault` to
record primary too, drops the hardcoded primary-ylabel inline
lookup, and walks every populated role through the helper.
`ylabel_mode = "custom"` still wins for primary (user-text
affordance remains primary-only); non-primary always auto.
Default routing (UVVIS-only) is byte-identical pre/post — the
common case is unchanged. **Lock decision taken:** option (b)
variant of the three architecture options surveyed in the
canonical register entry — single helper keyed on NodeType
class rather than two parallel tables, because the
dimensionality of variability is NodeType nature (absorbance-
space vs derivative-space), not axis role. CS-44 invariants
all preserved (`_NON_PRIMARY_Y_LABEL` content +
`_resolve_non_primary_y_label` signature byte-identical; the
new helper layers on top). CS-50 + CS-52 + CS-53 + CS-54
unaffected. Five Claude-surfaced 🟢 friction items captured
at step 5 without new register entries (user accepted no new
items): first-node-on-primary wins label policy is
under-informative when multi-class; `_NON_PRIMARY_Y_LABEL` is
now misnamed (CS-44 lock); empty-primary is silently
unlabelled; Phase 4u friction #9 cross-refs CS-55's fix; the
Phase 4ac changelog-gap doc-debt. 882 tests, all green (864
+ 9 pure-module in `TestYAxisLabelResolution` + 9 integration
in `TestYAxisLabelRoleSwap`).*
*1.30: Phase 4ae — Plot Settings → Appearance gains three new
controls (CS-56). Closes Phase 4ac friction #2 (USER-FLAGGED
🟡 "Configurable plot grid colour") and Phase 4ac friction #3
(USER-FLAGGED 🟡 "Default to inward-facing axis ticks") in
full, plus the "promote `_TERTIARY_AXIS_OFFSET_FRAC` to Plot
Settings" half of the CS-44 follow-up register entry (the
larger lift to `plot_widget.py` stays carry-forward), plus the
Phase 4ad friction #5 changelog-gap doc-debt via a retroactive
`*1.28: Phase 4ac…*` insertion. Three new entries in
`plot_settings_dialog._FACTORY_DEFAULTS`: `"grid_color"` =
`"#b0b0b0"`, `"tertiary_axis_offset"` = `1.12`, and
`"tick_direction"` flipped `"out"` → `"in"`. Two new rows in
`_build_section_appearance`: a `_make_colour_swatch` for
`grid_color` at row=1 (existing Background + Tick direction
rows shift down by one), and an inline `tk.Spinbox` (bounds
`1.00`–`1.50`, increment `0.01`) for `tertiary_axis_offset` at
row=4 bound to a new `_on_float_var_write` helper (analogue of
`_on_int_var_write`; skips mid-edit garbage). Three new
renderer reads in `uvvis_tab._redraw`: `ax.grid(color=...)`,
the inward-tick fallback flip, and `tertiary_offset` local
that replaces the bare `_TERTIARY_AXIS_OFFSET_FRAC` consumer
in the `get_axis(role)` closure. The CS-44 module constant
stays in place as the canonical fallback; a drift-pin test
asserts `_FACTORY_DEFAULTS["tertiary_axis_offset"]` equals
`_TERTIARY_AXIS_OFFSET_FRAC`. **Lock decisions taken:** grid
colour is app-global / single-colour / plot-wide; tick flip is
factory-default-only / no migration / no plot_widget.py change
(already `"in"` at line 250); tertiary offset is row-only
(plot_widget.py lift stays carry-forward). Five Claude-surfaced
🟢 friction items captured at step 5 without new register
entries (user accepted no new items, "proceed"): `_make_colour_
swatch` lacks a `trace_add` on its `StringVar`; no targeted
persistence test for the new keys; the tick flip is observable
to existing users with no `_USER_DEFAULTS["tick_direction"]`;
Spinbox bounds `1.00`–`1.50` are a Claude pick not a user lock;
the dialog row order in `_build_section_appearance` is a
cluster-by-concept choice. 899 tests, all green (882 + 17 new:
10 pure-module in `TestAppearanceSectionPhase4ae` + 7
integration in `TestUVVisTabAppearancePhase4ae`).*
*1.31: Phase 4af — user-driven `NodeType.NODE_GROUP` container
+ "Combine selected → Group" gesture (CS-57). FULLY resolves
the canonical Phase 4v friction #1 "Drop CS-31 + introduce
user-driven node groups" register entry (USER-FLAGGED 🔴) —
Phase 4ac shipped parts (a) + (b), Phase 4af ships part (c).
Also closes Phase 4ac friction #4 (the Phase 4ad → 4af NODE_
GROUP carry-forward — intent slipped two phases because
Phase 4ad shipped CS-55 label routing and Phase 4ae shipped
CS-56 Appearance pass) and Phase 4ac friction #5 (the dormant
`_SWEEP_MEMBER_INDENT_PX` constant + `_build_node_row(indent_
px=0)` kwarg — now LIVE, used by every member of an expanded
group). Graph layer: new `NodeType.NODE_GROUP` enum variant
(carries `arrays={}` + `metadata["member_ids"]: list[str]`);
new `ProjectGraph.create_group(member_ids, label=None) -> str`
+ `dissolve_group(group_id)` + `group_of(node_id) -> Optional
[str]`; `discard_node` grew an auto-dissolve cascade that
recursively discards a group when fewer than two active
members remain (bounded at one level by the flat-only
invariant). UI layer: ScanTreeWidget gained a click-toggle
selection model (`_selected_node_ids` set, `<ButtonRelease-1>`
binding so a double-click rename gesture nets out to zero
toggle), a footer "Group selected" button (predicate mirrors
`create_group`'s validation: ≥2 selected AND none already
grouped AND none a NODE_GROUP), a group-row pipeline
(`_build_group_row` with chevron ▾/▸ + "(N members)" badge +
inline ✕), a chevron-driven `_expanded_groups` set, and a
`_show_group_context_menu` branch for the simplified group
menu (Rename / Expand-or-Collapse / Ungroup). Top-level
rendering excludes grouped members; expanded groups render
members below with `padx=(2 + _SWEEP_MEMBER_INDENT_PX, 2)`.
Right-click context menu on data rows grew a "Group selected
(N)" entry enabled by the same predicate. **Lock decisions
taken:** (i) **gesture style — context-menu + left-pane
footer button** (both surfaces); (ii) **flat only, no
nesting**; (iii) **Ungroup via context-menu + inline ✕** on
group rows; (iv) **indent reuses `_SWEEP_MEMBER_INDENT_PX
= 16`** (CS-35 lock survives, purpose realised). Additional
Claude-side locks: default label `"Group N"`, members keep
their parent edges (group is view-layer, not structural
reparenting), single-membership enforced, NODE_ADDED on
create + NODE_DISCARDED on dissolve (no new event types),
groups skip y-axis routing / redraw, groups always
PROVISIONAL, `project_io` round-trips through the existing
DataNode schema (arrays={} → empty savez archive; member_ids
in metadata is JSON-serialisable). Two new USER-FLAGGED
register entries surfaced at step 5: 🟡 "Keyboard shortcuts —
whole-interface evaluation pass" (multi-phase design pass) +
🟡 "'Add to existing group' gesture (Phase 4ag candidate)".
Recorded design constraint: no information bleed between tabs
unless explicit (USER-CONFIRMED). Four Claude-surfaced 🟢
polish notes folded into Phase 4af friction (group "(N
members)" suffix on user-renamed groups; "Show hidden" toggle
opacity; footer button label is static not size-aware; menu-
introspection monkey-patch). 949 tests, all green (899 + 50
new: 1 in `test_nodes.py` pinning NODE_GROUP as a distinct
variant + 27 in `test_graph.TestNodeGroupOps` + 21 in
`test_scan_tree_widget.TestScanTreeWidgetNodeGroupsPhase4af` +
1 in `test_persistence_phase_a.TestSaveLoadRoundTrip` for the
NODE_GROUP `.ptmg` round-trip).*
*1.32: Phase 4ag — Extend / remove gestures for NODE_GROUP
(CS-58). Fully resolves the canonical Phase 4af follow-up
"'Add to existing group' gesture" register entry (USER-FLAGGED
🟡); also closes Phase 4af friction #6 (static footer button
label) by extending CS-57's `_group_btn` lock-relaxation
trigger (the button now mutates its text per selection
classification — `"Group selected (N)"` in group mode,
`"Add to <group label>"` in extend mode, baseline
`"Group selected"` disabled otherwise). Graph layer: new
`ProjectGraph.extend_group(group_id, member_ids)` +
`remove_from_group(node_id)` methods; new
`GraphEventType.NODE_GROUP_MEMBERS_CHANGED` event with
payload `{"group_id", "added", "removed"}`. UI layer:
ScanTreeWidget's `_on_graph_event` routes the new event to
the structural-rebuild branch; new `_classify_selection`
helper returns `{"mode": "none"|"group"|"extend"|"invalid",
...}` so the footer button + both context menus read from
one canonical analysis; group-row context menu grows a
fourth entry "Add selected to this group (N)" (right-click
identifies target / selection identifies payload); data-row
context menu grows two siblings — "Add selected to <group
label> (N)" + per-row "Remove from group". **Lock decisions
taken (Phase 4ag):** (i) both surfaces — context menu AND
footer button; (ii) append (preserve caller order); (iii)
new `NODE_GROUP_MEMBERS_CHANGED` event type (rejected
NODE_LABEL_CHANGED — scan tree routes that to targeted
row refresh, but member changes are structural); (iv) yes —
symmetric `remove_from_group` ships in the same phase,
reusing CS-57's auto-dissolve threshold (<2 active members)
via `discard_node`. **Lock relaxations:** CS-57's
`text="Group selected"` initial-label lock broadened (Phase
4af friction #6 polish trigger); CS-57's narrow "any group
in selection → disabled" semantics relaxed (a 1 group +
≥1 ungrouped selection now routes to the extend gesture).
Three new USER-FLAGGED register entries surfaced at step 5:
🟡 "Grid renders in front of data lines, not behind"
(one-line fix, bundleable into the next phase regardless of
intent); 🟡 "Axis double-click → axis-properties dialog"
(multi-phase, dialog shell + per-axis style schema); 🟡
"Show hidden toggle should disable when no hidden rows
exist" (upgraded from Phase 4af friction #5 🟢 by user flag).
1002 tests, all green (949 + 53 new: 27 in
`test_graph.TestNodeGroupExtendRemoveOps` + 24 in
`test_scan_tree_widget.TestScanTreeWidgetNodeGroupsPhase4ag`
+ 2 in `test_persistence_phase_a.TestSaveLoadRoundTrip` for
the extend+remove and auto-dissolve cascade round-trips).*
*1.33: Phase 4ah — polish bundle resolving four BACKLOG
register entries in one phase (CS-59). (A.1) USER-FLAGGED
Phase 4ag friction #1 "Grid renders in front of data lines"
— `ax.grid(...)` in `uvvis_tab._redraw` now takes `zorder=0`
so gridlines paint behind data lines. (A.2 — CS-59 Thread A)
USER-FLAGGED Phase 4ag friction #3 / Phase 4af friction #5
chain "'Show hidden' toggle should disable when no hidden
rows exist" — new `_has_hidden_rows()` predicate +
`_refresh_show_hidden_button_state()` companion called from
`_rebuild`'s tail; Checkbutton stored as `self._show_hidden_
btn`; cascade contract locked (never silently flip
`_show_hidden`); member-of-collapsed-group counts as hidden
(avoids whiplash on expand/collapse). (F) USER-FLAGGED Phase
4t friction #3 "Top-bar Open File / Reload buttons belong to
TDDFT only" — path (a) chosen: buttons removed from
`binah._build_top_bar` and re-rendered inside the TDDFT tab's
left sidebar at the top above "Loaded Files"; flanking
`ttk.Separator` removed too; the `«` sidebar toggle + "TDDFT
Section:" combobox + file label stay in the top bar this
phase (USER-CONFIRMED follow-up queued). (G — CS-59 Thread B)
Phase 4u friction #9 "`_absorbance_to_y` corrupts d²A on %T"
— helper signature widened to `_absorbance_to_y(absorbance,
y_unit, node_type)`; CS-55-frozenset gate short-circuits to
pass-through for derivative-space NodeTypes (currently
SECOND_DERIVATIVE); all three `_redraw` call sites updated.
**Lock decisions taken (Phase 4ah):** (i) hard-code
`zorder=0`, no Plot Settings key (render correctness, not
preference); (ii) UV/Vis only this phase; (iii) disable-only
on Show hidden — no count badge or tooltip; (iv) cascade
preserves `_show_hidden` ON; (v) member-of-collapsed-group
counts as hidden; (vi) TDDFT chrome path (a) re-render in
tab; (vii) `«` + section combobox follow-up queued; (viii)
global Ctrl+O stays bound (keyboard-shortcuts phase's job);
(ix) `_absorbance_to_y` extends signature, helper owns the
rule. **Lock relaxations:** none to CS-55, CS-57, CS-58,
CS-44; CS-55 invariant 1 explicitly RE-LOCKED here. Two new
🟢 BACKLOG entries queued at step 5 + session start:
sidebar `«` toggle + "TDDFT Section:" combobox follow-up
(USER-CONFIRMED); per-tab tertiary-y-axis default routing
schema (USER-FLAGGED design topic raised at session start).
1022 tests, all green (1002 + 20 new across two files: 2 in
`test_uvvis_tab.TestUVVisTabGridZOrderPhase4ah` + 11 in
`test_scan_tree_widget.TestShowHiddenButtonGatingPhase4ah` +
7 in `test_uvvis_tab.TestAbsorbanceToYNodeTypeGatePhase4ah`).
F intent added no tests — Lock 13 accepted manual smoke for
the binah.py button-parent move (module has no existing
test coverage).*
*1.34: Phase 4ai — unified PlotConfigDialog Notebook + cross-tab
pending-edit state model (CS-60). FOUNDATION resolves the
canonical Phase 4ag-era USER-FLAGGED 🟡 "Axis double-click →
axis-properties dialog" register entry — the user's design call
was a unified dialog with axis-tab selector, not a separate
modal per axis. Chain-collapsed across Phase 4ag friction #2
(canonical strike-through) + Phase 4ah friction #6 (one-line
cross-ref). Five code commits across the phase: (1) new
`plot_axis_hit_test.py` module with `AxisHit` dataclass + a
duck-typed `classify_axis_double_click(event, axes_by_role,
tertiary_offset_frac)` classifier returning one of five
axis roles × three hit kinds; (2) rename
`PlotSettingsDialog` → `PlotConfigDialog` + factory
`open_plot_settings_dialog` → `open_plot_config_dialog`
(file name preserved to minimise import churn); (3) Notebook
restructure — Global tab hosts the legacy section LabelFrames
unchanged, five axis tabs ship placeholder shells whose real
settings land Phase 4aj+; (4) cross-tab pending-edit state
model with `" •"` modified marker, `_modified_tabs` source of
truth, `_KEY_TO_TAB` routing map (empty in 4ai — every key
defaults to Global), new Save / Apply / Apply to All Tabs /
Cancel button row, askokcancel "Discard changes?" confirm on
Cancel-with-pending; (5) UV/Vis figure double-click integration
binding `button_press_event` to a dispatcher that opens the
dialog on the matching axis's tab. **Lock decisions taken
(Phase 4ai):** (i) one unified dialog with Notebook tabs, not
one per axis; (ii) module file name `plot_settings_dialog.py`
preserved (binah / project_io / persistence keep imports
unchanged); (iii) cross-tab pending edits persist across tab
switches (navigation, not commit); (iv) modified marker is
`" •"` IntelliJ bullet; (v) "Apply to All Tabs" replicates
to same-tab-type siblings only — cross-tab-type plot-setting
replication is NOT a thing (CS-60 lock 14); (vi) Cancel-
confirm uses askokcancel (returns True in `_test_silence`,
preserves CS-23's "Cancel always closes" test contract);
(vii) hit-test bands 40/6/18/24 px; (viii) tertiary band
tested first so secondary-y is clipped at the offset spine;
(ix) right-side click with no twinx maps to primary_y;
(x) axis tabs are shells in 4ai. **Lock relaxations:**
CS-23 subsumed into CS-60 — class name, factory name,
button row vocabulary all evolve; the locked semantics
persist (Apply commits + stays open, Save commits + closes,
Cancel reverts to snapshot). Two new USER-FLAGGED 🟡
register entries surfaced at step 5: `_USER_DEFAULTS`
tab-type split (becomes urgent when the dialog wires into
XANES / EXAFS — different tab types can't share UV/Vis's
axis label slot); Twin-X axis full wiring (wavelength↔
energy transform + bidirectional range coupling; the
Secondary X Notebook tab is a shell today, the matplotlib
twin-x machinery is the larger feature). Five Claude-
surfaced 🟢 polish notes folded into the new Phase 4ai
friction list: Apply-to-All-Tabs callback unwired; static
axis-tab badges (live "(used by N)" deferred to 4ak);
`hit_kind` ignored at dialog level; tertiary x-axis not
classifiable today; hit-test band-size tuning if matplotlib
layout changes. Per-axis settings ladder (Phase 4aj→4an)
queued as friction #1 with reasoning-level tags per phase.
1113 tests, all green (1022 + 91 new: 37 in
`test_plot_axis_hit_test` + 19 in
`test_plot_settings_dialog.TestPlotConfigDialogNotebookPhase4ai`
+ 25 in `TestPlotConfigDialogStateModelPhase4ai` +
`TestPlotConfigDialogButtonRowPhase4ai` + 10 in
`test_uvvis_tab.TestUVVisTabAxisDoubleClickPhase4ai`).*
*1.35: Phase 4aj — CS-61 tick_direction widget relocation to
per-axis tabs. First slice of the per-axis settings ladder
(Phase 4aj→4an); closes Phase 4ai friction #1's 4aj slot
without committing to schema-invention decisions (those wait
for Phase 4ak). The widget moves out of Plot Settings →
Appearance row 3 (tertiary_axis_offset slides from row 4 →
row 3) into a new "Settings" `LabelFrame` on each of the five
per-axis Notebook tabs. All five tabs share one Tk var
(`_control_vars["tick_direction"]`) — single working-copy
key, schema stays flat. New `_KEY_TO_TAB` routing map (empty
in 4ai) gets its first explicit entry,
`{"tick_direction": "primary_x"}`, so editing the radio on
ANY per-axis tab marks ONLY Primary X dirty regardless of
which tab the user was looking at — no five-bullet flood.
The pin is independent of the visible tab; tick direction is
most visually associated with the bottom X-axis ticks in a
UV/Vis plot. New `_build_axis_tab_settings(parent, role)`
helper, called from `_build_axis_tab_shell` for each non-
Global role, is the body builder future per-axis ladder
phases extend. Fallback reads from
`_FACTORY_DEFAULTS["tick_direction"]` not a hard-coded "in"
literal so a future schema flip cannot drift. **Lock
relaxations:** CS-60 lock 4 (the routing map was empty) —
intentional growth via the first entry, not a lock break;
CS-56 invariant — `_build_section_appearance` no longer grids
tick_direction. **Locks held:** every CS-56 / CS-60 invariant
except the two relaxations; `_FACTORY_DEFAULTS
["tick_direction"] = "in"` schema (CS-56 Phase 4ae flip);
`_USER_DEFAULTS` flat shape; all CS-44 / CS-49 / CS-50 /
CS-55 / CS-57 / CS-58 / CS-59 invariants unchanged. **Lock
decision taken (Phase 4aj):** (i) widget mirrors across ALL
FIVE per-axis tabs sharing one Tk var (not Global tab; not
one arbitrary axis tab in isolation; not five independent
vars — that's 4ak's job); (ii)
`_KEY_TO_TAB["tick_direction"] = "primary_x"` (Primary X
canonical home for the dirty pin); (iii) Appearance section
row 3 deletes cleanly; tertiary_axis_offset slides to row 3;
grid_color and tertiary_axis_offset stay in Appearance.
Friction acknowledged for 4aj (resolved by 4ak):
shared-var UX dishonesty (edit on Primary Y updates radio on
Primary X); dirty-pin counterintuitive (edit on Primary Y
marks Primary X dirty). One new USER-FLAGGED 🟡 register
entry from step 5: external-output plot style presets
(J. Am. Chem. Soc. / two-column PowerPoint / etc.) with
reference Jupyter notebook code the user offered to lift
from. One 🟢 USER-FLAGGED friction note:
`TestAppearanceSectionPhase4ae` class-name drift (class
still contains tick_direction tests even though widget no
longer lives in Appearance). Four code commits this phase:
(1) widget relocation + `_KEY_TO_TAB` entry + Appearance row
renumber + docstring updates; (2)
`TestPlotConfigDialogTickDirectionRelocationPhase4aj` with 13
invariants; (3) two pre-existing Phase 4ai tests updated for
the relocation
(`test_axis_tab_shell_carries_phase_4aj_placeholder` renamed
+ inverted; `test_key_to_tab_defaults_to_global` narrowed to
skip keys in `_KEY_TO_TAB`); (4) hard-coded "in" fallback in
`_build_axis_tab_settings` routed through `_FACTORY_DEFAULTS`
(CS-56 schema invariant guard against future drift). 1126
tests, all green (1113 + 13 new in
`TestPlotConfigDialogTickDirectionRelocationPhase4aj`).*
*1.41: Phase 4ap — CS-68 live-preview semantics in
`PlotConfigDialog` (USER-FLAGGED single-target phase).
Discrete widgets (Combobox, Checkbutton, Spinbox, color
picker, Radiobutton) commit every edit immediately to the
live config and fire `on_apply`; text Entries (`title_text`
/ `xlabel_text` / `ylabel_text`, per-axis
`axis_label_override`, `range_lo` / `range_hi`, `tick_major`
/ `tick_minor`, plus the Global mirror
`axis_label_override`) defer the live commit to
`<FocusOut>` / `<Return>`. Apply button retired (per user's
literal "negate the need to have an apply button"); button
row collapses to `Save · Apply to All Tabs · Cancel`.
`_apply_changes_live`, `_bind_entry_live_commit`,
`_defer_apply_keys`, `_defer_apply_axis_keys` are the new
seam pieces. `_working` retained as widget-bound mirror;
`_snapshot` retained as Cancel-revert source.
`_modified_tabs` markers persist through live commits
(semantic broadens to "touched since open"); only Cancel-
revert / Save / `[X]` clears them. Defaults / Factory Reset
coalesces to ONE redraw via the suspend-guarded refresh +
single trailing `_apply_changes_live`. **Lock relaxations:**
CS-23 button-row passthrough partially relaxed (Apply
button + `_do_apply` removed; live commit replaces explicit
Apply gesture); CS-66 lock 4 (CS-23 button-row passthrough)
partially relaxed via the same. **Locks held:** CS-06
singleton, CS-23 `_snapshot`-as-revert source + close-on-
Cancel silenced-`askokcancel`, CS-29 retirement (CS-67),
CS-36 default-True per-node, CS-46 manifest schema, CS-60
cross-tab Notebook + `_KEY_TO_TAB` routing + per-tab
`_modified_tabs`, CS-61 / CS-62 / CS-63 / CS-64 / CS-65
per-axis ladder schemas + widgets, CS-66 modeless contract.
**Decision lock taken (Phase 4ap):** (DM1) scope
`PlotConfigDialog` only; (DM2) `_working` retained as
mirror; (DM3) `_snapshot`-only revert; (DM4) Apply button
retired; (DM5) text Entry per-keystroke debounce via
`<FocusOut>` / `<Return>`; (DM6) Defaults / Factory Reset
coalesces to one redraw; (DM7) `_modified_tabs` markers
persist through live commits; (DM8) Phase 4ao friction #9
covered by new integration test; (DM9) Phase 4ao friction
#12 (stale CS-29 comment) refreshed opportunistically.
USER contributed THREE new USER-FLAGGED items at step 5:
cross-node Style dropdown / multi-node window (new
register entry); wavelength secondary axis broken (B-005
in Known Bugs); Autoscale ↔ Range Entry seed semantics
(new register entry). Four Claude-surfaced carry-forwards
documented in BACKLOG's "Friction points carried forward
from Phase 4ap" section. Five code commits this phase: (1)
`plot_settings_dialog.py` live-preview seam (`cfcf77d`);
(2) `test_plot_settings_dialog.py` test rewrites + 14 new
sentinels in `TestPlotConfigDialogLivePreviewPhase4ap`
(`4d3f527`); (3) `scan_tree_widget.py:822` cosmetic
stale-comment refresh (`a6b07ea`); (4) `test_uvvis_tab.py`
new `TestUVVisTabLivePreviewModelessPhase4ap` 3
integration tests (`22f29a8`); (5) `test_uvvis_tab.py`
host-side test sweep dropping vestigial `_do_apply`
(`8a6c3ab`). 1302 tests, all green (1285 + 14 new live-
preview sentinels + 3 new modeless × live-preview
integration tests).*
*1.42: CS-69 — B-005 wavelength-secondary-axis fix lands in
Phase 4aq. Root cause: matplotlib's linked
`ax.secondary_xaxis(functions=(_fwd, _fwd))` was being
corrupted by the renderer's CS-64 `sec.set_xlim` call (it
back-propagates through the inverse of `_fwd` and corrupts
the primary axis). Fix: renderer NEVER calls `sec.set_xlim`
/ `sec.set_xscale`; `secondary_x` schema's range / autoscale
/ scale keys become inert when link is active. New per-axis
schema key `custom_ticks: str` (comma-separated explicit
positions, e.g. `"300, 400, 500, 700, 900"`) paints
`FixedLocator` major ticks via new `_apply_major_locator`
helper, uniform across all per-axis roles (D6b lock). D8
lock relaxation: link extends to BOTH `unit == "cm-1"` (via
`1e7 / x`) AND `unit == "eV"` (via `_HC_NM_EV / x`); both
self-inverse. New dialog kwarg `secondary_x_linked: bool`
snapshotted at open greys Secondary X tab's range_lo /
range_hi / autoscale / scale widgets so the user can't fight
the link (custom_ticks / tick_major / tick_minor stay
editable). New `_axis_control_widgets[(role, key)]` registry
on `PlotConfigDialog` parallel to `_axis_control_vars` —
hook for greying and future per-axis widget state-machines.
CS-65 `_AXIS_KEYS` registry grew from 10 → 11. `_AXIS_KEYS`
sentinel test renamed `test_axis_keys_grew_to_eleven_after_
phase_4aq`. B-005 ✅ in Known Bugs. **Decision lock taken
(Phase 4aq):** D1 link is matplotlib-side (already correct);
D2 renderer skips `sec.set_xlim` / `sec.set_xscale`; D3
dialog greys range / autoscale / scale on linked secondary;
D4 greying snapshotted at dialog open (mirrors `plots_by_role`
pattern); D5 schema key uniform across roles; D6 typed Entry
defer-commit per CS-68; D7 custom_ticks wins on major ticks
only; D8 cm⁻¹ + eV both supported; D9 toggle OFF keeps tab
editable; D10 no PTMG_FORMAT_VERSION bump; D11 CS-69
section + COMPONENTS doc-version bump 1.42 → 1.43; D12
commit order (pure module → tests → integration → tests).
USER contributed FOUR new USER-FLAGGED items at step 5,
all queued for the next phase: Compare-tab CS-69 mirror;
live-refresh of greying on toggle change; `λ(nm)`
Checkbutton greying when `unit == "nm"`; greying label
wording polish. Four code commits this phase: (1)
`uvvis_tab.py` pure-module link fix + helpers (`aedfd81`);
(2) `test_uvvis_tab.py` 27 unit-test sentinels across 4
classes (`cdd6f61`); (3) `plot_settings_dialog.py` + 
`uvvis_tab.py` dialog wiring + greying + 2 sentinel updates
(`df2542a`); (4) `test_plot_settings_dialog.py` 18 dialog
integration tests across 3 classes (`ab6a178`). 1347 tests,
all green (1302 + 27 unit + 18 integration).*
*1.44: Phase 4as — bundled CS-71 + CS-72 (two CS-70 pattern
adoptions in one session). CS-71 (Autoscale ↔ Range Entry
seed + live ax-limit display) closes USER-FLAGGED Phase 4ap
friction (canonical entry now ✅); CS-72 (live-refresh of
`_plots_by_role` inventory) closes the long-standing
Claude-surfaced staleness chain (Phase 4ak ε / Phase 4ao τ /
Phase 4ap τ / Phase 4ap item #10 — all now ✅ or struck
through with cross-refs). Lock relaxations: CS-64 D8
(textvariable swap) + CS-66 (`_on_destroy` widget filter).
PTMG_FORMAT_VERSION unchanged (no schema keys added). Five
phase commits: pure module + 32 unit tests + host wiring +
28 integration tests + this bookkeeping. 1441 tests, all
green (1379 baseline + 62 net new). One new carry-forward
(item α: NODE_GROUP_MEMBERS_CHANGED missing from `_redraw`
trigger list — pre-existing one-line gap, suggested for
low-cost bundling into Phase 4at).*
*Supersedes: BACKLOG.md (original)*
