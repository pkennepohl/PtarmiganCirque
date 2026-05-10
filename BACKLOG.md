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

2. 🔴 **CS-31's "no new node created" status message has weak
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
   intent.

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
| ⏳ | 🟡 | **`_absorbance_to_y` should not transform SECOND_DERIVATIVE values** | Surfaced Phase 4u while writing the multi-axis tests. Pre-existing bug, not introduced by Phase 4u: when `_y_unit` is `"%T"`, `_absorbance_to_y` clips values to `[-10, 10]` and applies `100·10^(-A)` — this conversion is meaningful for absorbance but corrupts d²A/dλ² values (which are typically `~0.001` and can be negative, so the clip → `100·10^(-A)` mapping produces nonsense). Fix: gate the conversion on the node's NodeType — only UVVIS / BASELINE / NORMALISED / SMOOTHED really live in absorbance space; SECOND_DERIVATIVE always renders as raw d²A/dλ² regardless of the y-unit toggle (the secondary y-axis label already encodes the unit context post-CS-44, so the toggle doesn't need to mutate the values). Touches `uvvis_tab._redraw` per-node loop (pass NodeType into the conversion or branch on it before calling). Test impact: a new `test_second_derivative_values_unchanged_by_percent_t_y_unit` in `TestUVVisTabSecondDerivativeIntegration` |
| ✅ | 🟢 | **Per-style `y_axis` override hook + StyleDialog row (CS-44 follow-up)** | Phase 4u Decision 1 deferred the per-style override (`node.style.get("y_axis")`) per the user's "Default only for now is okay" decision. The hook is wired into `_resolve_y_axis_role` as a one-line addition (read style first, fall back to per-NodeType default); the StyleDialog universal-section row is the bigger lift — a new `ttk.Combobox` choosing `"primary" / "secondary" / "tertiary"`, threaded through `_BULK_UNIVERSAL_KEYS`. Useful when a user wants to send a specific SECOND_DERIVATIVE node back to primary (small-magnitude derivatives that share scale with their parent) or send a UVVIS reference spectrum to a third axis. Defer until a user reports needing it. **Resolved Phase 4y (CS-50):** `node_styles.default_spectrum_style` adds `style["y_axis"]: str \| None` (default `None` = follow the per-NodeType default; non-None = literal CS-44 axis role overrides per-node); `_resolve_y_axis_role` grows an optional `style: Mapping \| None = None` argument and a one-line short-circuit at the front (override beats default; malformed values fall through). Renderer threads `node.style` at three call sites: per-node main loop, BASELINE-curve dashed overlay (resolver moved INSIDE per-bn body so a BASELINE on "secondary" puts both its main render AND its dashed overlay on the same axis), PEAK_LIST scatter loop. StyleDialog universal section gains a read-only `ttk.Combobox` row labelled "Y axis:" with options `["(default)", "primary", "secondary", "tertiary"]`; "(default)" round-trips to `None`. Decision lock taken: (i) cross-typed Apply auto-inherits parent's effective role on the new node IFF NodeType-defaults differ — `SmoothingPanel._apply` writes `style["y_axis"] = parent_effective_role` for smoothed-of-derivative outputs (closes Phase 4x friction #6); (ii) "(default)" = literal `None` semantics; inheritance is a separate apply-time mechanism that writes a literal role string; (iii) `y_axis` is intentionally absent from `_BULK_UNIVERSAL_KEYS` (parallel to Phase 4d's `visible` / `in_legend` carve-out — bottom ∀ Apply-to-All would too easily collapse derivatives onto primary), but the per-row ∀ button widens its scope to every renderable node (UVVIS / BASELINE / NORMALISED / SMOOTHED / SECOND_DERIVATIVE / PEAK_LIST) via `_on_uvvis_apply_to_all`'s special-case for the key. 35 new tests (7 pure-helper + 2 default-style + 16 StyleDialog Combobox + 4 renderer override + 3 cross-typed inheritance + 3 fan-out-scope). 781 tests, all green. Persistence (CS-46) auto-rides — the new key sits in the existing style-dict round-trip; no manifest schema change |
| ✅ | 🟡 | ~~**Y-axis Combobox row appears on non-UVVis StyleDialog instances (Claude-surfaced Phase 4y)**~~ ✅ Resolved in Phase 4aa (CS-52). Path (a) (NodeType-gate the row) landed: the new module-private `_Y_AXIS_VISIBLE_NODETYPES: frozenset[NodeType]` mirrors `uvvis_tab._DEFAULT_Y_AXIS_BY_NODETYPE.keys()` exactly (UVVIS / BASELINE / NORMALISED / SMOOTHED / PEAK_LIST / SECOND_DERIVATIVE), and `_build_universal_section` wraps the `_build_y_axis_row` call in `if self._node_type in _Y_AXIS_VISIBLE_NODETYPES`. For TDDFT / FEFF_PATHS / XANES / EXAFS / DEGLITCHED / AVERAGED / BXAS_RESULT the Combobox is now suppressed — the affordance no longer appears where it would be a no-op. `_read_universal_values` skips the key automatically when its var isn't in `_control_vars`, so Save / Apply / ∀ paths stay self-consistent. The drift test `test_y_axis_visible_node_types_match_routing_table` pins the gate against the routing table so a future widening of `_DEFAULT_Y_AXIS_BY_NODETYPE` (when path (b) — the multi-axis-routing lift to `plot_widget.py` — eventually lands) cannot silently reintroduce the misleading affordance. 15 new integration tests (six routing-NodeType "present" cases + seven non-routing "absent" cases + two self-consistency cases) plus 2 pure-module drift tests. |
| ⏳ | 🟢 | **Per-NodeType primary y-axis label for override use case (CS-50 follow-up)** | Surfaced by Claude during Phase 4y. CS-44's `_NON_PRIMARY_Y_LABEL` table is keyed by `(NodeType, x_unit)` and only carries entries for SECOND_DERIVATIVE — the renderer relies on the *NodeType-default* for primary's label (always "Absorbance" / "Transmittance (%)" today). With the CS-50 override hook landed, two minor surprise cases exist: (a) UVVIS overridden to "secondary" leaves the secondary axis unlabelled (no `(UVVIS, x_unit)` entry in the table); (b) SECOND_DERIVATIVE overridden to "primary" keeps the absorbance label, which is wrong for d²A values. Reasonable degradation today (the user explicitly chose the override), but a future polish could introduce a `_PRIMARY_Y_LABEL: dict[(NodeType, x_unit), str]` companion table so primary's label tracks the *first* node landing on it (parallel to the existing non-primary path), or — simpler — fold both into a single `_Y_LABEL_BY_ROLE_FIRST_NODE_TYPE` lookup. Touches `_redraw`'s y-label resolution + a small expansion of `_NON_PRIMARY_Y_LABEL` to cover UVVIS / NORMALISED / etc. on every x-unit. Cross-refs Phase 4u friction #9 (`_absorbance_to_y` corrupts d²A on %T) — both surface "primary axis assumes absorbance values" mistakes. Defer until a user reports actual confusion |
| ⏳ | 🟢 | **DRY cross-typed-Apply y_axis inheritance helper (CS-50 architectural debt)** | Surfaced by Claude during Phase 4y. The CS-50 inheritance block (set `style["y_axis"]` on a new node when its NodeType-default differs from the parent's effective role) lives inside `SmoothingPanel._apply`, today the only widened cross-type panel under CS-49. If a future panel widens its `ACCEPTED_PARENT_TYPES` cross-type (NormalisationPanel accepting SECOND_DERIVATIVE; SecondDerivativePanel accepting NORMALISED on a non-UVVis x-axis; etc.), each panel's `_apply` would copy-paste the same six-line block. Move it into `node_styles.py` (or a new `axis_inheritance.py`) as `inherit_y_axis_for_cross_typed_apply(parent_node, new_node_type) -> str \| None`; every panel calls it next to its `default_spectrum_style(colour)` call. Cheap one-time refactor; defer until a second cross-typed-Apply path lands so the abstraction has two consumers. Cross-refs the four open audit-held tuples (`NormalisationPanel` / `PeakPickingPanel` / `SecondDerivativePanel`) — the next CS-49-style widening will probably be the trigger |
| ⏳ | 🟢 | **Hover/status-bar readout for active y-axis (CS-44 follow-up)** | Surfaced Phase 4u step 5. Once two y-axes coexist (CS-44), the matplotlib toolbar's coordinate readout reports primary-axis values only — a user mousing over a SECOND_DERIVATIVE point sees an absorbance number, not a d²A value. Likely shape: bind a `motion_notify_event` on the canvas, walk every populated `_axes_by_role` axis, transform the cursor's display coords into each axis's data coords, and surface the per-axis readout in a dedicated status strip below the toolbar. Cross-refs the diagnostic-console register entry — both add ambient information surfaces. Defer until two-axis use is common enough to motivate the complexity |
| ⏳ | 🟢 | **Lift multi-axis routing to plot_widget.py + promote `_TERTIARY_AXIS_OFFSET_FRAC` to Plot Settings (CS-44 follow-up)** | Phase 4u Decision 7 kept the multi-axis routing inside `uvvis_tab._redraw` rather than lifting to `plot_widget.py`. This pairs with Q2's user decision to make `_TERTIARY_AXIS_OFFSET_FRAC` tunable later — both follow-ups land naturally in the same phase. Trigger: when a second tab (XANES / EXAFS) needs multi-axis routing, lift `_AXIS_ROLES` + `_DEFAULT_Y_AXIS_BY_NODETYPE` + `_NON_PRIMARY_Y_LABEL` + `_TERTIARY_AXIS_OFFSET_FRAC` + `_resolve_y_axis_role` + `_resolve_non_primary_y_label` + the `get_axis(role)` lazy-creation closure into `plot_widget.py` (or a new `plot_axes.py`). At the same time, surface the tertiary offset as a Plot Settings → Appearance row. Until then, the in-tab home is the right shape — single consumer, no abstraction tax |
| ⏳ | 🟡 | **Top-bar Open File / Reload buttons belong to TDDFT only, not the app top level (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4t. The very top bar of the app currently shows `Open File` + `Reload` buttons that, in practice, only act on the TDDFT tab — they're not relevant to the UV/Vis tab (which has its own subject-loading paths inside the left pane), the XAS / EXAFS tabs (separate file paths), or the planned Compare tab. Today they're rendered at app top level (in `binah.py` or wherever the chrome lives), giving the user a false signal that they're cross-tab gestures. The user has flagged that they should be removed from the top-level row entirely and either (a) re-rendered inside the TDDFT tab where they belong, OR (b) become tab-context-aware so they only show when the TDDFT tab is active. Lock decision needed: (a) is structurally cleaner (each tab owns its own file ingestion); (b) preserves the existing "always-on top bar" pattern. Touches `binah.py` (top-bar removal) + the TDDFT tab module (button re-render, if path (a) chosen). Pairs with any future tab-chrome refactor — the file-open responsibility per tab is also relevant to the OLIS reader register entry above and to the persistence umbrella's `.ptmg` archive UX (load-project gestures stay app-level; load-instrument-file gestures are per-tab) |
| ⏳ | 🔴 | **Diagnostic console / fitted-parameter panel (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4n. Several places in the app produce numeric diagnostics that currently live only in `OperationNode.params` and never surface to the user: scattering log fit's resolved n (Phase 4m friction #2), upcoming scattering+offset's `a_fitted`, polynomial baseline fit residuals, peak-picking match list, rubberband convex-hull point count, etc. The user is asking whether a small read-only "console" or "log" pane (a scrolling text widget at the bottom of the app or a per-tab footer) would carry these. Two shapes worth weighing: (a) **per-tab inline diagnostic strip** — small read-only panel at the bottom of each tab's left pane that names the most recently applied op and lists its key fitted values; refreshed on every Apply; (b) **app-wide log console** — a collapsible bottom drawer (like an IDE's output pane) that streams every op's "results" line plus warnings / errors / debug; survives tab switches. (b) doubles as a place for the `_redraw` KeyError trace (Phase 4n friction #1) and the messagebox messages currently shown via popups (e.g. "no Compare host connected"). Both shapes are non-trivial; pick before any Phase 4 follow-up that needs to surface a fitted value |
| ✅ | 🔴 | **Defensive guard in `_redraw` for non-UVVIS DataNodes** | Surfaced by Phase 4n while writing the Send-to-Compare integration test. Resolved Phase 4o (CS-28): positive guard at the top of the per-node loop body (`if "wavelength_nm" not in node.arrays or "absorbance" not in node.arrays: continue`) and a mirror guard wrapped around the unit==`"nm"` xlim min/max comprehension. Silent skip — the diagnostic-console entry (still ⏳) will eventually surface skipped nodes. The Phase 4n note that BASELINE's schema was `wavelength_nm + baseline` was inaccurate — live BASELINE nodes carry `wavelength_nm + absorbance` (line 937 of `uvvis_tab.py`); the only `baseline`-keyed BASELINE in the codebase was the deliberately-malformed stub in `test_send_node_to_compare_skips_non_uvvis_nodes`, which the Phase 4o follow-up commit simplified to use the new guard rather than stub `graph.get_node` |
| ⏳ | 🟡 | **Long-provenance hist button display options (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4n. The `⌥{n}` always-visible cell (CS-26 promotion) renders the provenance chain length as a literal integer. For complex workflows `n > 9` is realistic — the row's natural width grows with the digit count, which can re-trigger the responsive overflow pattern at the same widths today's tests verify. Options to weigh in the implementing session: (a) cap display at `⌥9+` once n > 9 with the exact count surfaced via tooltip / history sub-frame; (b) two-digit fixed width (`⌥01`...`⌥99`) so the row's natural width is bounded but the count remains readable; (c) hide digits entirely (just `⌥`) and surface the count only via the expanded history sub-frame; (d) SI-suffix style (`⌥9`, `⌥1k` for >999). Touches `scan_tree_widget._populate_node_row` (the `text=f"⌥{chain_len}"` line) and the existing `test_provenance_op_count` style assertions. User has confirmed `n > 9` is "easily seen for complex workflows" so this is not edge-case |
| ⏳ | 🟢 | **Threshold-band caching for responsive helper (technical debt)** | Phase 4n CS-26's `_apply_responsive_layout` unconditionally pack_forget+repacks every optional cell on every call (rather than tracking last-applied state) because Tk auto-unmap under overflow makes `winfo_ismapped()` an unsound "have" oracle. The fix is correct but does redundant work on every `<Configure>` event at the same width. Cache the last applied "threshold band" per row (e.g. one of `(none, swatch, swatch+leg, all)`) and short-circuit the reflow when the new width falls in the same band. Care needed: the cache must be invalidated on `_populate_node_row` (a row rebuild starts fresh). Cheap polish; defer until flicker is observed in real use |
| ⏳ | 🟢 | **Test convention: `_root.update()` over `update_idletasks()` for geometry** | Surfaced during Phase 4n CS-26 test work. `update_idletasks()` flushes idle handlers but does NOT trigger Tk's geometry pass on a withdrawn root; `winfo_ismapped()` lags reality until the next event cycle. Pre-CS-26 responsive tests got away with `update_idletasks` because the helper packed less aggressively; CS-26's unconditional reflow exposed the gap. Document the convention in `test_scan_tree_widget`'s module docstring (and the equivalent docstrings in any future widget tests that read mapped state): "after a layout-changing call on a withdrawn `_root`, use `_root.update()`, not `update_idletasks()`, before reading `winfo_ismapped`". One-paragraph doc edit; no code change |
| ✅ | 🔴 | **Right-sidebar canvas-width binding + responsive helper canvas-Configure rerun (USER-FLAGGED)** | USER-FLAGGED at start of Phase 4p. Resolved Phase 4p (CS-30): the helper now reads `_scroll_canvas.winfo_width()` rather than `row.winfo_width()` (with a `width: int \| None = None` kwarg for explicit overrides). The per-row `<Configure>` binding is removed (it raced with explicit calls and read the wrong width); replaced by a canvas `<Configure>` binding that walks every row in `_optional_row_widgets` on resize. Initial calibration of newly-built rows happens at the end of `_populate_node_row` via a single helper call. Inner `_rows_frame` width is intentionally NOT bound to canvas width (Tk's auto-unmap on overflow would silently drop overflow widgets). Touches `scan_tree_widget._build_chrome` + `_populate_node_row` + the helper signature, plus six new regression tests in `TestScanTreeWidgetCanvasDrivenLayout`. The pre-existing `test_each_row_collapses_independently` test was rewritten to use the explicit `width=` kwarg — under the new contract rows share a canvas, so the per-row independence invariant only survives when callers drive it directly. 540 tests, all green |
| ✅ | 🔴 | **Suppress identical re-applies (param-equality gate on Apply) (USER-FLAGGED)** | USER-FLAGGED at start of Phase 4p. Resolved Phase 4p (CS-31): new graph method `ProjectGraph.find_provisional_op_with_params(parent_id, op_type, params) -> str \| None` (full dict equality on params; returns first match in graph insertion order). Threaded through every UV/Vis apply site (`uvvis_tab._apply_baseline` + `uvvis_normalise.NormalisationPanel._apply` + `uvvis_smoothing.SmoothingPanel._apply` + `uvvis_peak_picking.PeakPickingPanel._apply` + `uvvis_second_derivative.SecondDerivativePanel._apply`). Check fires after params are validated and BEFORE `compute()` runs (so the dedup decision never depends on the deterministic numerical output). On hit: no graph mutation, status message "<op> (<mode>) with these parameters already applied to <parent label> — no new node created.", `_apply` returns `None`. 10 helper tests in `TestFindProvisionalOpWithParams` + 5 panel-side integration test pairs (suppress + different-params, one per apply site). Real parameter sweeps (different params on each click) still flow into the sweep-grouping detector unchanged. 540 tests, all green |
| ✅ | 🔴 | **Inline expansion + per-variant gestures on sweep-group rows (CS-04 §6.3 follow-through) (USER-FLAGGED)** | USER-FLAGGED at start of Phase 4p. Resolved Phase 4q (CS-32): chevron `▸/▾` on the leader row toggles `parent_id` membership in `self._expanded_sweep_groups: set[str]` (parallels `_expanded_history`), routes through `_rebuild`, which after `_build_sweep_row(group_key)` iterates `self._sweep_groups[group_key]` in deterministic sorted order and calls `_build_node_row` per member. Members render with full chrome — state · swatch · ☑ · label · ⌥n · ⚙ · → · 🔒 · ✕ — picking up the new CS-34 commit gesture along with everything else. Group dissolution is automatic: `_compute_sweep_groups` only returns groups with ≥2 members, so committing/discarding one variant down to 1 makes the parent_id absent from `_sweep_groups` on the next rebuild and the chevron + leader row + remaining inline members all dissolve naturally. Six new integration tests in `TestSweepGroupInlineExpansion` (chevron read, toggle, second toggle, persistence across rebuild, member full-chrome, group dissolution); promotes BACKLOG row 187 from ⏳ to ✅ |
| ✅ | 🔴 | **Truncate long node-name labels in ScanTreeWidget rows (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4p. Resolved Phase 4q (CS-33): module-level `_LABEL_MAX_CHARS = 32` cap + pure helper `_truncate_label(text, max_chars)` truncates with `…` suffix at exactly the cap; `_populate_node_row` paints the truncated text and attaches a `_Tooltip` (Toplevel, 600 ms hover) ONLY when truncation actually cut text. `_build_sweep_row` applies the same treatment to the parent label inside the leader text. `_begin_label_edit` reads the canonical full label from the graph rather than the painted (potentially truncated) widget text, so rename starts with the untruncated text. Five pure-helper tests in `TestTruncateLabel`, three Tooltip construction/binding tests in `TestTooltip`, three widget-side tests in `TestLabelTruncationInRow`. Pairs with the still-open Phase 4n "Long-provenance hist button display options" register entry — same root (cells whose natural width grows with content), same canvas-width invariant. Sibling Phase 4q friction #2 captures the cap-from-canvas-width-and-font-metrics follow-up |
| ✅ | 🔴 | **🔒 commit gesture on provisional ScanTreeWidget rows** | Resolved Phase 4q (CS-34). Every PROVISIONAL row carries a `tk.Button(text="🔒")` between → and ✕ that invokes `self._safely(self._graph.commit_node, nid)` — same path the right-click context menu's Commit entry uses. Committed rows OMIT the button entirely (the leftmost-cell 🔒 state indicator already signals committed state; double-glyph would be confusing). Right cluster reads `[⌥n] [⚙] [→] [🔒] [✕]` provisional, `[⌥n] [⚙] [→] [✕]` committed. NOT in the responsive-optional set: 🔒 is always-visible (commit twin of ✕). Three integration tests in `TestProvisionalRowCommitButton`. Together with the still-open "Commit / discard reachable from the left pane after Apply" register entry, this covers the right-sidebar half of the original USER-FLAG; the left-pane Accept-last button-pair remains 🟡 |
| ✅ | 🟢 | **Compute label-truncation cap from canvas width / font metrics (CS-33 follow-up)** | Phase 4q friction #2. **Resolved Phase 4w (CS-47):** new pure helper `_label_char_capacity(canvas_width_px, avg_char_px, overhead_px) → int` clamped to `[_LABEL_CHAR_FLOOR=8, _LABEL_CHAR_CEIL=64]` falls back to `_LABEL_MAX_CHARS=32` when canvas is unrealised or font metrics unavailable. Wired into `_populate_node_row` and `_build_sweep_row` via instance method `_current_label_cap` (which delegates to the helper using `_scroll_canvas.winfo_width()` and `tkfont.nametofont("TkDefaultFont").measure("ABCDEFGHIJabcdefghij") // 20`). `_apply_responsive_layout` re-truncates the painted label and rotates the always-attached label tooltip's text whenever the canvas resizes — widening the sash visibly grows the label, narrowing trims it. The pure `_truncate_label` helper stays unchanged (CS-33 invariant preserved). Tooltip rotation uses the empty-string sentinel that `Tooltip._show` already supports, so no create/destroy churn. 12 pure-module + 3 integration tests cover the dynamic-cap behaviour |
| ⏳ | 🟢 | **Promote `_Tooltip` to a shared utility module on first cross-module re-use** | Phase 4q friction #3. CS-33's `_Tooltip` is a small Toplevel-based hover tooltip co-located in `scan_tree_widget.py`. Other surfaces will eventually need similar tooltips (Plot Settings dialog parameter hints, StyleDialog "what does this control" hints, panel-status messages that only fit on hover). On first re-use, extract into `tooltip.py` (pure utility module, no scan-tree-specific imports) so the second consumer doesn't either re-implement or import a private name. Until then, the private name is fine — premature promotion would add an import surface without a second consumer |
| ✅ | 🟢 | **Indent expanded sub-frames inside sweep groups (visual nesting)** | Phase 4q friction #5. Resolved Phase 4r (CS-35): new module-level `_SWEEP_MEMBER_INDENT_PX = 16` constant; `_build_node_row` grew an `indent_px: int = 0` keyword that is threaded into `row.pack(padx=(2 + indent_px, 2), pady=1)`. The sweep-expansion branch in `_rebuild` calls `_build_node_row(member_node, indent_px=_SWEEP_MEMBER_INDENT_PX)`. Pack-arg pass-through chosen over a wrapper-frame to avoid a parallel `_member_frames` dict + collapse cleanup. CS-32's flip-and-rebuild contract preserved verbatim. The history sub-frame inside an expanded member row carries the parent row's indent (since `_render_history` packs into the row's children frame), so visual nesting is correct without separate indent threading there. 7 new tests (2 pure-module constant, 5 integration nesting) |
| ⏳ | 🔴 | **Drop CS-31 "no duplicate apply" check + introduce user-driven node groups (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4v (step 5 elicitation). The CS-31 `find_provisional_op_with_params` short-circuit (Phase 4p) prevents the same op-with-same-params from running twice on the same parent — but in practice this prevents the user from re-running an op that they want to re-run, and the auto-collapsed sweep groups (CS-32) bundle related applies into a unit the user can't operate on. The user has flagged that today's behaviour makes work flows unusable: re-applying a process you tweaked once is blocked, and the auto-grouping hides the individual nodes. **Architecture (lock pending):** (a) **drop CS-31** entirely — every Apply produces a fresh OperationNode + child DataNode regardless of whether identical params were applied before; the CS-31 register entry below flips ✅→reverted-by-CS-N. (b) **drop CS-32 auto-grouping** of provisional ops with identical (parent, op_type) signatures — the inline expansion stays as the rendering primitive, but the GROUPING decision moves from automatic to user-driven via a new "Combine selected → Group" gesture. (c) New `NodeType.NODE_GROUP` (or `USER_GROUP`) holds child node ids + a user-given label; renders as a row with a chevron that expands to show its members; group does not own arrays, has no scientific value of its own. (d) Pairs with the existing 🟡 "Multinode dataset import + combination" register entry above — both are user-driven combination UX; they may collapse into one OperationType (`SPECTRUM_DATASET` for sweep-grid-aware datasets, `NODE_GROUP` for everything else). **Lock decisions for the implementing session:** (i) does CS-32's sweep-group inline-expansion machinery survive (rebranded as "user group expansion") or get rewritten? (ii) does the group support nested groups? (iii) what's the gesture — context-menu "Group selected", left-pane button, drag-and-drop into a group node? **Affected modules:** `graph.py` (drop the `find_provisional_op_with_params` call from every apply site or remove the helper entirely), `uvvis_baseline.py` / `uvvis_normalise.py` / `uvvis_smoothing.py` / `uvvis_peak_picking.py` / `uvvis_second_derivative.py` (drop the dedup short-circuit), `scan_tree_widget.py` (replace the `_compute_sweep_groups` auto-grouping with a `_user_groups` set + user-driven gesture), `nodes.py` (new NodeType + dataclass changes), tests across the board. Multi-phase task |
| ✅ | 🔴 | **Adjustable sidebar still not working — fix next, revisit every cell + minimum width (USER-FLAGGED bumped from 🟡 to 🔴 in Phase 4v)** | USER-FLAGGED at end of Phase 4u as 🟡 (Phase 4u friction #5); re-flagged at end of Phase 4v (bumped to 🔴). **Resolved Phase 4w (CS-47 + CS-48):** the auto-bump scope ships as CS-47 (`widest_label_pixel_width` measurement + `_calibrate_sidebar_width` one-shot via `after_idle`); the cell-vocabulary audit + minimum-width work ships as `_CELL_MIN_PX` (every cell documented in one dict) + `_SIDEBAR_MIN_WIDTH_PX = 240` (pinned floor used by both the responsive helper and the PanedWindow's `minsize`); the column-alignment scope ships as CS-48 (fixed-width `row_toggle` slot). The "minimum width" scope deliberately reused the existing 240 px floor (matching the smallest responsive threshold) rather than introducing a new per-cell sum, because changing the floor would break the existing TestResponsiveCollapse threshold tests. See the canonical resolved entry "Dynamic sidebar auto-width for long node labels" above for full deliverables list |
| ⏳ | 🟡 | **Trash can for discarded nodes — restore from a Trash pane (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4v (step 5 elicitation). Today `ProjectGraph.discard_node` removes the node from `self.nodes` entirely; if the user discards a provisional node they later want back, it's gone. The user has asked for a Trash gesture analogous to a desktop OS recycle bin. **Architecture proposal (lock pending):** (a) new `NodeState.DISCARDED` (joining `PROVISIONAL` / `COMMITTED`); (b) `discard_node` flips state to DISCARDED rather than removing from `self.nodes`; (c) the default sidebar filter hides DISCARDED rows; (d) a "Trash" pane / collapsible section / dialog lists discarded nodes with a Restore gesture that flips state back to PROVISIONAL (or COMMITTED if the node was committed before discard); (e) discarded nodes round-trip through the Phase A manifest (sidecar storage stays). Pairs with: the new sidecar-garbage-collection register entry below (DISCARDED nodes' sidecars stay until the trash is emptied) and Phase 4q friction #4's left-pane Accept/Discard register entry (Discard now preserves recoverability). **Lock decisions for the implementing session:** (i) is Trash a top-of-sidebar collapsible section, a separate pane, or a Toplevel dialog? (ii) does Empty Trash literally remove from `self.nodes` (current discard behaviour) or is even that retained? (iii) does Restore preserve the original ordering / parent edges, or just resurrect the node and let the user reattach edges? **Affected:** `nodes.py` (new NodeState variant), `graph.py` (discard_node implementation + a new restore_node), `scan_tree_widget` (filter + new pane), `uvvis_tab` (pane wiring), `project_io.py` (sidecar persistence — already handled by the array-hash identity, but needs to round-trip the new state) |
| ⏳ | 🟡 | **Project-specific plot defaults + import from another project (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4v (step 5 elicitation). Phase A persistence (CS-46) round-trips `plot_settings_dialog._USER_DEFAULTS` as a top-level `plot_defaults` key, but those defaults are app-global (mutated in place at load time). The user has asked for project-scoped plot defaults that ride with the workflow + an "Import plot settings from another project" gesture in the Plot Settings dialog. **Architecture proposal (lock pending):** three-layer defaults — factory (`_FACTORY_DEFAULTS`, immutable) → user (`~/.binah_config.json`, app-global) → project (manifest, scoped to the loaded `.ptmg`). Lookups walk the layers (project ?? user ?? factory). New "Import plot settings…" file dialog in PlotSettingsDialog reads another `.ptmg`'s `plot_defaults` block and merges into the current project's overrides. Pairs with the still-open Phase 4l friction #1 register entry (audit dialog button-row vocabulary) — the import gesture is a new dialog. **Lock decisions for the implementing session:** (i) does the project layer override every key, or only ones explicitly set? (ii) is the import a copy (snapshot) or a reference (live link to the source project's defaults)? (iii) does the StyleDialog's "Apply to All" reach into the project-defaults layer? **Affected:** `plot_settings_dialog.py` (three-layer lookup + import file dialog), `project_io.py` (no schema change — `plot_defaults` already exists; semantics shift), `binah.py` (load-time wiring of the project layer) |
| ⏳ | 🟡 | **Refactor uvvis_tab.py — extract host shell into separate files; cross-tab generalization (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4v (step 5 elicitation). Today `uvvis_tab.py` is ~2000 LOC mixing five concerns: (a) the left-pane chrome (CollapsibleSection wrappers, shared subject combobox, baseline-section inline panel), (b) the right-pane chrome (ScanTreeWidget host), (c) the matplotlib plot frame + redraw pipeline, (d) graph subscription + apply orchestration, (e) the LOAD path (file-open dialog → parser → DataNode creation). The five operation panels (`uvvis_baseline.py`, `uvvis_normalise.py`, `uvvis_smoothing.py`, `uvvis_peak_picking.py`, `uvvis_second_derivative.py`) are already separate files. **Architecture proposal (lock pending):** (a) extract the left-pane chrome into `processing_pane.py` (or `left_pane.py`) — the shared subject combobox + the CollapsibleSection wrappers + the panel registration mechanism become reusable across XAS / EXAFS / TDDFT tabs once those tabs adopt ProjectGraphs; (b) extract the right-pane chrome (ScanTreeWidget host wiring + `_restore_workflow_payload`) into `tab_shell.py`; (c) extract the matplotlib plot frame + redraw into `plot_pane.py`; (d) leave `uvvis_tab.py` as a thin orchestration class composing the three panes. The cross-tab generalization is a separate larger entry — the four tabs end up with a common `Tab` base class composing the same three pane classes. **Lock decisions for the implementing session:** (i) does the redraw pipeline stay inside the plot pane (lift the multi-axis routing CS-44 helpers along with it), or stay in `uvvis_tab.py` per the current Phase 4u Decision 7? (ii) which tab adopts the cross-tab generalization first — XANES (which has its own plot logic to reconcile) or a fresh "Compare" tab? (iii) is the panel registration mechanism a list of `(name, panel_class, factory)` tuples, a decorator, or hard-wired? Multi-phase task. Pairs with the future plot_widget abstraction lift register entry (CS-44 follow-up). Cross-refs the existing Phase 4t friction #3 / "Top-bar Open File / Reload buttons belong to TDDFT only" register entry — that one removes app-level chrome; this one extracts tab-level chrome |
| ⏳ | 🟡 | **Plot data markers / points (instead of lines) with per-style marker config (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4v (step 5 elicitation). Today every visible spectrum is rendered as a continuous line (`ax.plot(..., linestyle=...)` in `uvvis_tab._redraw`); discrete points are not an option. The user has asked for a markers-only render mode + per-style marker configuration (shape + size). **Architecture proposal (lock pending):** new style keys `style["plot_kind"]: "line" \| "markers" \| "both"` (default `"line"` to preserve existing behaviour), `style["marker"]: str` (matplotlib marker spec — `"o"`, `"s"`, `"^"`, etc.), `style["marker_size"]: float`. The redraw branch in `uvvis_tab._redraw` reads `plot_kind` and switches between `ax.plot(..., linestyle="None", marker=..., markersize=...)` and the existing line path; `"both"` uses the existing line path with a non-`"None"` marker. **StyleDialog universal section:** new Combobox (line / markers / both), new marker-shape Combobox (matplotlib's standard set), new size Spinbox. **Cross-refs:** `node_styles.default_spectrum_style` grows the three new keys with sensible defaults. **Affected:** `node_styles.py` (defaults), `style_dialog.py` (universal section), `uvvis_tab.py` (`_redraw` switch), tests for the new style keys' round-trip and the renderer's branching. Pairs with: the future PEAK_LIST renderer (peaks are inherently markers — CS-19 already uses scatter); this entry generalises the markers path so PEAK_LIST and a markers-only spectrum share the same code |
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
| ⏳ | 🟡 | **StyleDialog must surface ALL node-table parameters (incl. label rename) + tighten organisation for scale (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4x (step 5 elicitation). Today the per-node StyleDialog (gear icon) covers the universal style schema (`color`, `linestyle`, `linewidth`, `alpha`, `visible`, `in_legend`, `fill`, `fill_alpha`) plus per-NodeType extensions (CS-05 + CS-36 `show_baseline_curve`). The user has flagged that as more parameters land (label rename gesture, plot_kind from the markers register entry, `y_axis` from carry-forward T, etc.), the dialog will become unwieldy without a re-organisation pass. **Architecture proposal (lock pending):** restructure the dialog around grouped sections — Appearance (color / swatch / linestyle / linewidth / alpha), Legend (in_legend, label-rename Entry), Fill (fill / fill_alpha), Per-type (show_baseline_curve, plot_kind, y_axis, …); each group is a `tk.LabelFrame` so the visual grouping is obvious. **First concrete add:** label-rename Entry — today the only path to rename a node is to double-click the row label in the sidebar (CS-33 `_begin_label_edit`); having it inside the StyleDialog mirrors how the user thinks about "node properties" and avoids competing for the gesture's attention. Cross-refs: CS-33 (label-edit machinery), CS-44 follow-up T (per-style `y_axis` row), the markers register entry above (plot_kind / marker / marker_size). **Lock decisions:** (i) does the dialog get a tabbed shape (Appearance / Provenance / Per-type) — pairs with the next register entry below — or stay single-pane with LabelFrame groupings? (ii) does the label-rename Entry surface a validation error inline (e.g. duplicate-label warning) or rely on the existing CS-33 rules? (iii) which existing widgets lift into per-type groupings vs stay universal? **Affected:** `style_dialog.py` (re-layout + new label-rename Entry), tests for the new section grouping + label-rename round-trip. Pairs with C and D below (same window). **Phase 4aa partial (CS-52):** the **first concrete add** (label-rename Entry) landed in the universal section at the top of the grid — `_build_label_row` builds a `tk.Entry` bound to a `StringVar` whose `trace_add('write')` callback commits each keystroke through the new `_write_label_partial` helper, which routes via `graph.set_label` (label is a top-level DataNode slot, not a style key). Lock decisions taken for the partial: (i) **deferred** — single-pane with the new "Label:" row at the top of the existing universal grid; the LabelFrame re-org + tabbed-shape question stays open and pairs with C and D below in a future combined intent; (ii) **no inline validation** — match CS-33's sidebar gesture, accept any string; (iii) **no widget lifts** — all existing universal rows preserve their relative order (the lock-relaxation reading of "rows + their order stay verbatim"). Companion plumbing: `_snapshot_label` mirrors the existing style snapshot; `_do_cancel` restores both; `_on_graph_event` handles `NODE_LABEL_CHANGED` for sibling-rename refresh + dialog-title update. 10 new integration tests (`TestStyleDialogLabelRename`). **Carry-forward:** the LabelFrame groupings + tabs question (lock decision (i) above) + the rest of the parameter-coverage list (plot_kind from the markers register entry; future per-NodeType rows). |
| ⏳ | 🟡 | **Per-node parameter window: add a Provenance tab (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4x (step 5 elicitation). The right-sidebar's per-row history dropdown (the `▿` chevron next to the label, opens an ad-hoc list of "Op A → Op B → Op C") is intentionally compact — but the user has asked for a more detailed view that lives inside the gear-icon dialog as a second tab. The new tab would show: ancestor walk back to the RAW_FILE / multi-input source, full op params for each step (params dict pretty-printed), timestamps, engine + engine_version, implementation hash (CS-45), status, log excerpts (when populated). **Architecture proposal (lock pending):** convert the StyleDialog to a `ttk.Notebook` shape — Tab 1 "Style" (today's content, possibly re-organised per the previous register entry); Tab 2 "Provenance" (the new view). Reuses the same Toplevel + button row (Apply · ∀ Apply to All · Save · Cancel). The provenance tab is read-only this phase; the "add historical node" gesture lands as the separate register entry below (D). **Lock decisions:** (i) is the provenance tab populated lazily (on-tab-switch) or eagerly (at dialog construction)? (ii) does it scroll vertically as a single column, or render as a tree with expandable nodes? (iii) does it show DISCARDED ancestors (history-style) or filter them? **Affected:** `style_dialog.py` (Notebook restructure), graph-walk helper for the ancestor list (likely a new `ProjectGraph.ancestors_of(node_id)` method), tests for the tab construction + the ancestor walk. Pairs with B above (same dialog) and D below (same tab — D adds a gesture, this entry adds the read-only view) |
| ⏳ | 🟡 | **"Add to graph" gesture from a node's Provenance tab (USER-FLAGGED)** | USER-FLAGGED at end of Phase 4x (step 5 elicitation). Once C lands (read-only Provenance tab), the user has asked for an "Add to graph" gesture per ancestor — clicking it materialises the historical ancestor as a new live node in the same graph without re-loading from disk. Concrete use case: the user has a SMOOTHED node loaded; they realise they want to compare the smoothed result against the underlying RAW_FILE / UVVIS parent; today the only path is to either (a) un-discard the parent (if it was discarded) or (b) re-load the source file via the LOAD path (which creates a fresh UVVIS DataNode with a different id, breaks the existing graph linkage to the SMOOTHED descendant). The new gesture would walk the ancestor chain, find the requested historical node, flip its `active` flag back to True (if currently inactive) OR clone it as a new live node parented on the same source. **Architecture (lock pending):** (a) does the gesture flip the existing node's `active` flag (cheap; preserves graph identity; couples to the existing CS-22 `_spectrum_nodes` filter), OR clone the node as a new id (preserves the historical node's state but creates a graph-edge fork)? (b) what's the gesture — button per provenance row, right-click, drag-and-drop into the sidebar? (c) does it emit a NODE_ADDED event (clone path) or NODE_STYLE_CHANGED + a re-render trigger (active-flip path)? **Affected:** `style_dialog.py` (the new gesture in the Provenance tab), `graph.py` (a new `restore_ancestor` or similar helper, depending on which architecture lands), `uvvis_tab._refresh_shared_subjects` (re-runs after the gesture so the resurrected node appears in the combobox), tests for both architectures. Pairs with C above (the tab the gesture lives on) AND with the existing 🟡 Trash can register entry (Trash + this gesture overlap conceptually — both surface "previously hidden" nodes) |
| ⏳ | 🟢 | **Visual cue for derivative entries in the shared subject combobox (CS-49 follow-up)** | Surfaced Phase 4x (Claude). Now that `SECOND_DERIVATIVE` rows mix into the shared combobox alongside the four spectrum-shaped types (`_refresh_shared_subjects` widening), the user has no per-row glyph or grouping divider to tell at a glance "this is a derivative" vs "this is an absorbance-domain spectrum". Cheap polish: prefix derivative entries with a `d² ` glyph in the combobox display key (or insert a `─── d²A/dλ² ───` separator entry between the spectrum block and the derivative block). The latter is more disruptive (changes the value-list semantics — the separator can't be selected); the former is one-line in `_refresh_shared_subjects`. Defer until the user reports actual confusion picking among mixed entries; the audit-stability test `test_shared_combobox_orders_spectrum_then_derivative` already pins the spectrum-first ordering so visual scanning is at least left-to-right consistent |

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

3. 🟡 **Top-bar Open File / Reload buttons belong to TDDFT
   only, not the app top level (USER-FLAGGED).** The top-bar
   buttons in `binah.py` (or wherever the app chrome lives)
   only act on the TDDFT tab in practice but visually suggest
   cross-tab gestures. The user has flagged that they should
   be removed from the top-level row entirely. **Cross-ref:**
   see the new register entry "Top-bar Open File / Reload
   buttons belong to TDDFT only" above for the architecture
   (lock decision needed: re-render inside the TDDFT tab vs.
   tab-context-aware show/hide on the existing top bar).
   Touches `binah.py` + the TDDFT tab module. Pairs with the
   OLIS reader register entry (per-tab file ingestion) and
   the persistence umbrella's `.ptmg` archive UX (load-project
   gestures stay app-level; load-instrument gestures are
   per-tab).

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

9. 🟡 **`_absorbance_to_y` corrupts SECOND_DERIVATIVE on %T y-unit.**
   Pre-existing bug surfaced while pinning the multi-axis tests.
   The conversion clips + maps `100·10^(-A)` which is meaningless
   for d²A values. Fix: gate the conversion on NodeType. One
   per-node-loop edit + one regression test. **Cross-ref:** see
   the new register entry. **Phase 4y note (CS-50):** the override
   hook makes a SECOND_DERIVATIVE-on-primary configuration newly
   reachable from the StyleDialog UI; before CS-50 the user had
   to hand-edit a project file's style dict to land the bug. The
   canonical register entry's priority arguably ticks up post-4y;
   defer the fix until either a user reports nonsense %T values or
   the next phase that touches the per-node loop's y-unit branch.

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

1. 🔴 **Drop CS-31 dedup + introduce user-driven node groups
   (USER-FLAGGED).** Today's "no duplicate apply" check
   (Phase 4p / CS-31) blocks legitimate re-applies; the auto-
   collapsed sweep groups (Phase 4q / CS-32) hide individual
   nodes so the user can't operate on them. The user has flagged
   that this makes workflows unusable. Drop CS-31; replace
   CS-32's automatic grouping with a user-driven "Combine
   selected → Group" gesture; introduce `NodeType.NODE_GROUP`
   for the explicit group container. Pairs with the existing
   🟡 multinode dataset register entry. **Cross-ref:** see the
   new register entry above.

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
   still ⏳, narrower in scope.

3. 🟡 **Per-node parameter window: add a Provenance tab
   (USER-FLAGGED).** User has asked for a more detailed
   provenance view than the right-sidebar's per-row history
   dropdown — second tab inside the StyleDialog, showing
   ancestor walk back to RAW_FILE / multi-input source, full
   op params per step, timestamps, engine + version,
   implementation hash (CS-45), status. **Cross-ref:** see the
   new register entry above. Pairs with #2 above (same dialog)
   and #4 below (same tab).

4. 🟡 **"Add to graph" gesture from a node's Provenance tab
   (USER-FLAGGED).** Once #3 lands, the user has asked for a
   per-ancestor "Add to graph" gesture that materialises the
   historical ancestor as a live node without re-loading from
   disk. Concrete use case: surface a SMOOTHED node's parent
   UVVIS for side-by-side comparison without breaking the
   existing graph linkage. **Cross-ref:** see the new register
   entry above. Pairs with #3 above (same tab) and the open 🟡
   Trash can register entry (both surface "previously hidden"
   nodes).

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

2. 🟢 **Per-NodeType primary y-axis label gap when override
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
   above.

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

1. 🟢 **"Tighten organisation for scale" half of Phase 4x
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
   + #4 canonical register entries above.

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

5. 🟢 **Phase 4y friction #2 (per-NodeType primary y-axis
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
   entry.

6. 🟢 **Cancel always re-emits the snapshot label (Claude-
   surfaced).** `_do_cancel` calls
   `_write_label_partial(self._snapshot_label)`
   unconditionally; `set_label` early-returns when old==new
   so the call is a no-op when the user never renamed, but
   it costs a function dispatch on every Cancel. Cheap to
   gate behind an inequality check; not worth the diff for
   cosmetic gain. No register entry.

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

*Document version: 1.26 — May 2026*
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
*Supersedes: BACKLOG.md (original)*
