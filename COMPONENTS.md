# Ptarmigan — Component Specifications

> **How to use this document in a Code session:**
> Load ARCHITECTURE.md always. Load only the section(s) of this
> document relevant to the component being implemented. Each section
> is self-contained. Do not implement anything that touches an Open
> Question (OQ-xxx) without resolving it in a Design session first.

---

## CS-01: ProjectGraph

**File:** `graph.py`
**Depends on:** CS-02 (DataNode), CS-03 (OperationNode)
**Depended on by:** Everything

### Responsibility

The ProjectGraph is the single source of truth for all data in the
application. It is a directed acyclic graph (DAG) of DataNodes and
OperationNodes. Every tab, sidebar, and dialog reads from and writes
to the graph. No tab stores its own list of scans or spectra.

### Core interface

```python
class ProjectGraph:
    # Node management
    def add_node(node: DataNode | OperationNode) -> None
    def get_node(id: str) -> DataNode | OperationNode
    def commit_node(id: str) -> None      # PROVISIONAL → COMMITTED
    def discard_node(id: str) -> None     # PROVISIONAL → DISCARDED

    # Per-node visualization edits (allowed on any state)
    def set_label(id: str, new_label: str) -> None
    def set_active(id: str, value: bool) -> None
    def set_style(id: str, partial: dict) -> None       # merges
    def clone_node(id: str) -> str                      # new uuid4 id

    # Edge management
    def add_edge(parent_id: str, child_id: str) -> None
    def parents_of(id: str) -> list[str]
    def children_of(id: str) -> list[str]

    # Queries
    def nodes_of_type(type: NodeType,
                      state: NodeState = COMMITTED) -> list[DataNode]
    def active_node_for(dataset_id: str) -> DataNode | None
    def provenance_chain(id: str) -> list[DataNode | OperationNode]

    # Persistence
    def save(path: Path) -> None          # write to .ptproj/ directory
    def load(path: Path) -> None          # read from .ptproj/ directory
    def export_log(path: Path) -> None    # write log.jsonl

    # Observers (for reactive UI updates)
    def subscribe(callback: Callable) -> None
    def unsubscribe(callback: Callable) -> None
    def _notify(event: GraphEvent) -> None
```

### Visualization-edit semantics

The four per-node visualization methods (`set_label`, `set_active`,
`set_style`, `clone_node`) are the widget-facing surface for everything
that is *display state*, not *scientific data*. They are allowed on any
node state, including COMMITTED, because COMMITTED only locks `arrays`
and `metadata` — not `label`, `active`, or `style`.

* `set_label` — emits `NODE_LABEL_CHANGED`. No-op when the new label
  equals the current one.
* `set_active` — emits `NODE_ACTIVE_CHANGED`. No-op when the value is
  unchanged. `active=False` is the canonical "soft-hide" signal the
  ScanTreeWidget reads to omit a row.
* `set_style` — **merges** `partial` into `node.style` (does NOT
  replace). Emits `NODE_STYLE_CHANGED` with payload
  `{"partial": ..., "new_style": ...}`. No-op on an empty `partial`.
* `clone_node` — produces a fresh `PROVISIONAL` `DataNode` with a new
  `uuid4` id. `arrays` is a **shared reference** (numpy not deep-copied,
  by design — committed scientific data is immutable so sharing is
  safe and avoids duplicating large beamline tensors). `metadata` and
  `style` are deep-copied. Label is suffixed with `" (copy)"`. The
  caller is responsible for wiring edges (`add_edge`) — `clone_node`
  itself only emits `NODE_ADDED`.

### Reactivity

The graph uses an observer pattern. UI components subscribe to graph
events. When a node is added, committed, or discarded, the graph
notifies all subscribers. This eliminates the need for "Refresh"
buttons anywhere in the UI.

GraphEvent types:
- NODE\_ADDED(node\_id)
- NODE\_COMMITTED(node\_id)
- NODE\_DISCARDED(node\_id)
- NODE\_LABEL\_CHANGED(node\_id, payload={old\_label, new\_label})
- NODE\_ACTIVE\_CHANGED(node\_id, payload={old\_value, new\_value})
- NODE\_STYLE\_CHANGED(node\_id, payload={partial, new\_style})
- EDGE\_ADDED(payload={parent\_id, child\_id})
- GRAPH\_LOADED
- GRAPH\_CLEARED

Subscribers must NOT prevent each other from receiving an event. If a
subscriber raises, ``_notify`` logs the exception at WARNING level via
the standard ``logging`` module and continues dispatch to remaining
subscribers. This isolates UI panels from each other — a buggy sidebar
cannot break the log panel by raising on a `NODE_ADDED`.

### Persistence layout

```
projectname.ptproj/
├── project.json           # metadata: name, created, modified,
│                          # app version, active tab, compare config
├── graph/
│   ├── committed/
│   │   ├── {id}.json      # DataNode or OperationNode metadata
│   │   └── {id}.npz       # DataNode arrays (DataNodes only)
│   └── provisional/       # same structure; cleared or recovered on open
├── raw/
│   ├── {id}__{filename}   # original file copy, prefixed with node id
│   └── manifest.json      # {node_id: {original_path, sha256, copied_at}}
├── sessions/
│   ├── feff_{id}/
│   └── bxas_{id}/
└── log.jsonl              # append-only; one JSON object per line
```

### log.jsonl format

Each line is a complete JSON record of one committed operation:

```json
{
  "timestamp": "2026-04-25T14:35:02",
  "op_id": "op_003",
  "op_type": "NORMALISE",
  "engine": "larch",
  "engine_version": "0.9.80",
  "params": {"e0": 2470.3, "pre1": -150, "pre2": -30,
              "nor1": 19, "nor2": 119, "nnorm": 2},
  "input_ids": ["ds_002"],
  "output_ids": ["ds_004"],
  "duration_ms": 43,
  "status": "SUCCESS"
}
```

### What this component does NOT do

- Does not know anything about Tkinter widgets
- Does not trigger redraws — that is the ScanTreeWidget's job on
  receiving a graph event
- Does not validate scientific parameters — that is the engine's job

---

## CS-02: DataNode

**File:** `nodes.py`
**Depends on:** nothing
**Depended on by:** CS-01, CS-05, CS-06, all tabs

### Definition

```python
from dataclasses import dataclass, field
from enum import Enum, auto
from datetime import datetime
from typing import Any

class NodeType(Enum):
    RAW_FILE    = auto()   # original loaded file; never processed
    XANES       = auto()   # processed XANES (normalised μ(E))
    EXAFS       = auto()   # processed EXAFS (χ(k), |χ(R)|)
    UVVIS       = auto()   # UV/Vis/NIR spectrum
    DEGLITCHED  = auto()   # scan with spikes removed
    NORMALISED  = auto()   # normalised result (XANES or UV/Vis)
    SMOOTHED    = auto()   # smoothed result
    SHIFTED     = auto()   # energy-shifted result
    BASELINE    = auto()   # baseline-corrected UV/Vis
    AVERAGED    = auto()   # average of multiple input nodes
    DIFFERENCE  = auto()   # difference of two input nodes
    TDDFT       = auto()   # TD-DFT calculated spectrum (from ORCA)
    FEFF_PATHS  = auto()   # FEFF simulation result
    BXAS_RESULT = auto()   # bXAS unified fit result
    # Add further types as new operations are implemented

class NodeState(Enum):
    PROVISIONAL = auto()
    COMMITTED   = auto()
    DISCARDED   = auto()

@dataclass
class DataNode:
    id: str                          # uuid4, assigned at creation
    type: NodeType
    arrays: dict[str, Any]           # e.g. {"energy": np.ndarray,
                                     #        "mu": np.ndarray}
    metadata: dict[str, Any]         # technique-specific; see below
    label: str                       # user-editable display name
    state: NodeState = NodeState.PROVISIONAL
    created_at: datetime = field(    # tz-aware UTC; see _utcnow helper
        default_factory=_utcnow)
    active: bool = True              # False = hidden from default views
    style: dict = field(            # display style; not scientific data
        default_factory=dict)
```

`created_at` is constructed via the module-private `_utcnow()` helper,
which returns `datetime.now(timezone.utc)` (timezone-aware). This
replaces the deprecated `datetime.utcnow()` form (Python 3.12+).
ISO 8601 serialisation includes the `+00:00` offset.

### Metadata conventions by NodeType

These are conventions, not enforced schema. Keys should be consistent
within each type.

**RAW\_FILE:**
```python
{"original_path": str, "sha256": str, "file_format": str,
 "copied_to": str}   # path within project raw/ directory
```

**XANES / NORMALISED (from Larch):**
```python
{"e0": float, "edge_step": float, "pre1": float, "pre2": float,
 "nor1": float, "nor2": float, "nnorm": int, "rbkg": float,
 "technique": "XANES", "edge": str, "element": str}
```

**EXAFS:**
```python
{"e0": float, "qmin": float, "qmax": float, "dq": float,
 "qweight": int, "qwindow": str, "rmin": float, "rmax": float,
 "technique": "EXAFS"}
```

**UVVIS:**
```python
{"x_unit": str,           # "nm" | "cm-1" | "eV"
 "y_unit": str,           # "absorbance" | "transmittance"
 "instrument": str}       # e.g. "OLIS", "generic"
```
Note: arrays always stored as wavelength\_nm and absorbance.
Other representations are computed on access.

**TDDFT:**
```python
{"section": str,          # e.g. "Electric Dipole"
 "states": int,
 "source_file": str,      # original ORCA .out filename
 "broadening": str,       # "Gaussian" | "Lorentzian"
 "fwhm": float,
 "delta_e": float,
 "scale": float}
```

**BXAS\_RESULT:**
```python
{"fit_quality": float,    # χ² or R-factor
 "n_params": int,
 "n_points": int,
 "background_model": str,
 "spectral_model": str,
 "parameters": dict}      # {name: {value, stderr, min, max}}
```

### What this component does NOT do

- Does not compute anything — it stores results, not procedures
- Does not know about its parent or child nodes — the graph manages edges
- The style dict is for display only and does not affect scientific data

---

## CS-03: OperationNode

**File:** `nodes.py` (same file as CS-02)
**Depends on:** CS-02 (NodeType, NodeState)
**Depended on by:** CS-01, CS-05

### Definition

```python
@dataclass
class OperationType(Enum):
    LOAD          = auto()
    DEGLITCH      = auto()
    NORMALISE     = auto()
    SMOOTH        = auto()
    SHIFT_ENERGY  = auto()
    BASELINE      = auto()  # mode-discriminated; CS-15
    AVERAGE       = auto()
    DIFFERENCE    = auto()
    FEFF_RUN      = auto()
    BXAS_FIT      = auto()
    # Add further types as new operations are implemented
    #
    # NORMALISE (above) is mode-discriminated for UV/Vis via
    # params["mode"] ∈ {"peak", "area"}; see CS-16. The mirror
    # convention for BASELINE lives in CS-15.

@dataclass
class OperationNode:
    id: str
    type: OperationType
    engine: str              # "internal" | "larch" | "feff" | "bxas"
    engine_version: str
    params: dict             # complete snapshot; must be sufficient
                             # to reproduce the operation exactly
    input_ids: list[str]     # DataNode ids consumed
    output_ids: list[str]    # DataNode ids produced
    timestamp: datetime = field(default_factory=_utcnow)  # tz-aware UTC
    duration_ms: int = 0
    status: str = "SUCCESS"  # "SUCCESS" | "FAILED" | "PARTIAL"
    log: str = ""            # engine stdout/stderr
    state: NodeState = NodeState.PROVISIONAL
```

### Params completeness requirement

The params dict must contain every value needed to reproduce the
operation from the input DataNodes. This is a correctness requirement,
not optional. Before implementing any new operation, define its
complete params schema.

Example — Larch normalisation:
```python
params = {
    "e0": 2470.35,
    "pre1": -150.0, "pre2": -30.0,
    "nor1": 19.0, "nor2": 119.3,
    "nnorm": 2,
    "rbkg": 1.0,
    "kmin_bkg": 0.5
}
```

---

## CS-04: ScanTreeWidget

**File:** `scan_tree_widget.py`
**Depends on:** CS-01 (ProjectGraph), CS-02 (DataNode)
**Depended on by:** All tabs

### Responsibility

The right sidebar component. Displays the set of DataNodes relevant
to the current tab context. Subscribes to ProjectGraph events and
updates reactively. Provides per-node controls and gestures.

### Per-row layout (left to right)

```
[state] [swatch] [☑] [label ············] [✓/–] [~~~~] [⌥n] [⚙] [✕]
```

- **state** — icon: 🔒 = committed, ⋯ (dashed) = provisional
- **swatch** — coloured rectangle; click → colour picker
- **☑** — visibility checkbox; toggles node on/off in plot
- **label** — truncated display name; double-click to edit in-place
- **✓/–** — legend toggle
- **~~~~** — linestyle canvas; click to cycle solid→dashed→dotted→dashdot;
  renders in node colour at exact linewidth
- **⌥n** — history indicator; n = number of operations in provenance
  chain; click to expand/collapse history below row
- **⚙** — open unified style dialog for this node
- **✕** — discard (provisional nodes) or hide (committed nodes)

#### Responsive collapse (B-002, Phase 4d)

The row reflows on narrow sidebars. Below
`scan_tree_widget._RESPONSIVE_COLLAPSE_PX` (currently 280 px) the
optional set — **swatch**, **✓/–** legend toggle, **~~~~** linestyle
canvas, **⌥n** history indicator — is `pack_forget`-ed. The minimum
always-visible set survives every width:

```
[state] [☑] [label ············] [⚙] [✕]
```

Every collapsed control remains reachable through the unified style
dialog (CS-05 §"Universal section" carries `visible` and `in_legend`
controls so the row's `[☑]` and `[✓/–]` toggles have dialog parity
even when the row is too narrow to render them).

### History expansion (inline, below row)

```
    ↳ normalise [larch 0.9.80] · 2026-04-25 14:35 · E0=2470.3
    ↳ deglitch [internal] · 2026-04-25 14:32 · interp@2471.3
    ↳ source: scan1.dat [sha256: abc123···]
```

Each line is clickable. Clicking a history entry loads that
DataNode into the plot as a provisional preview.

### Sweep group row

When multiple provisional nodes share the same parent (parameter
sweep), they are collapsed into one row:

```
[~] [▪▪▪] [☑] scan1 · E0 sweep (10)  [expand▾] [✕all]
           best: E0=2470.3 · χ²=0.0023
```

Expanding shows all variants, ranked by fit metric. Each variant
has its own commit/discard controls.

### Committed node ✕ behaviour

✕ on a committed node does not discard it from the graph. It hides
it from the current tab's view (sets active=False). A "Show hidden"
toggle at the bottom of the sidebar reveals hidden committed nodes.
Committed nodes are never deleted except by explicit "Clean up" action.

### Context menu (right-click on any row)

- Commit (if provisional)
- Discard (if provisional)
- Send to Compare (if committed)
- Rename
- Export… (if committed; CS-17, Phase 4f)
- Show history
- Hide / Show
- Duplicate (creates a new provisional copy for alternative exploration)

### Reactive behaviour

ScanTreeWidget subscribes to ProjectGraph. On NODE\_ADDED: inserts row.
On NODE\_COMMITTED: updates state indicator. On NODE\_DISCARDED: removes
row. On NODE\_LABEL\_CHANGED: updates label text. No manual refresh.

### What this component does NOT do

- Does not store its own list of nodes — reads exclusively from graph
- Does not decide what to display — the tab tells it which NodeTypes
  to show via a filter parameter at construction time
- Does not trigger plot redraws directly — it calls a redraw callback
  provided by the tab

### Implementation notes (Phase 2)

These record decisions taken when implementing CS-04 for ambiguities
the spec left open. They are descriptive, not prescriptive — a future
design session can revisit any of them.

**Construction signature.**
```python
ScanTreeWidget(
    parent,                     # tk.Widget host frame
    graph,                      # ProjectGraph
    node_filter,                # list[NodeType] OR Callable[[DataNode], bool]
    redraw_cb,                  # callable: redraw_cb() = full redraw,
                                #           redraw_cb(focus=id) = preview a node
    send_to_compare_cb=None,    # called with node_id; widget knows nothing
                                # about Compare
    style_dialog_cb=None,       # called with node_id; widget knows nothing
                                # about the dialog (Phase 3)
    export_cb=None,             # called with node_id; host opens the file
                                # dialog and writes the file (CS-17, Phase 4f)
)
```

The callable form of `node_filter` is for the Compare tab, which mixes
types and groups them by category; analysis tabs pass the list form.

**`[☑]` (visibility) vs `[✕]` (discard / hide) — different concerns.**

| Control | Writes | Effect |
|---|---|---|
| `[☑]` checkbox | `style["visible"]` | Toggles whether the line is drawn on the plot |
| `[✕]` on PROVISIONAL | `discard_node` | DataNode → DISCARDED; row vanishes |
| `[✕]` on COMMITTED | `set_active(False)` | Soft-hide — row vanishes, "Show hidden" reveals it |

The two layers stayed separate because conflating them broke the
"Show hidden" gesture in early drafts.

**Other style keys written by row controls.** `style["color"]` (colour
swatch), `style["linestyle"]` (linestyle canvas, cycled through
solid → dashed → dotted → dashdot), `style["in_legend"]` (legend
toggle). The unified style dialog (CS-05) is the place for the full
list; these are the keys the row controls touch directly.

**Default flat view** = every non-discarded DataNode that passes the
filter and has `active=True` (sweep groups collapse). The "currently
active node for each loaded dataset" reading of §6.1 is left to the
filter — a tab can supply a callable filter that returns only
`graph.active_node_for(root)` ids if it wants stricter
one-per-lineage semantics.

**Sweep group leader** = lexicographically smallest member id, so the
collapsed row renders deterministically. Group detection walks each
candidate's parents through one OperationNode hop to find its
DataNode parents (per the Phase 1 rule: "sweep group = multiple
provisional DataNodes sharing the same parent DataNode").

**Duplicate** (right-click → Duplicate) calls `graph.clone_node` and
then replicates every direct parent edge of the source onto the
clone, so the clone sits in the same lineage and appears via
`provenance_chain`.

**History entry click** calls `redraw_cb(focus=id)`. If the integration
hasn't been updated to accept `focus=`, the widget catches `TypeError`
and falls back to a regular `redraw_cb()` rather than swallowing the
gesture silently.

**Subscription teardown.** The widget binds `<Destroy>` and drops its
graph subscription automatically when destroyed; an explicit
`unsubscribe()` is also exposed for tabs that detach without
destroying.

**Sweep group inline expansion** (per-variant editing) is deferred —
the collapsed row currently exposes only `✕all`. The data needed for
per-variant rendering is exposed via `_sweep_groups`, so a future
session can extend without redesigning.

---

## CS-05: Unified Style Dialog

**File:** `style_dialog.py`
**Depends on:** CS-02 (DataNode, NodeType)
**Depended on by:** CS-04 (ScanTreeWidget ⚙ button), all tabs

### Responsibility

Single modeless dialog for all per-node style editing, regardless of
tab or node type. Sections shown are conditional on the node type of
the selected node.

### Window properties

- Title: "Style — {node.label}"
- Modeless (non-blocking Toplevel)
- Stays on top of main window but does not block it
- Changes apply live to plot (on Apply or slider release)
- One instance per node; opening ⚙ on a second node opens a second
  dialog or focuses existing one for that node

### Universal section (always shown)

| Control | Widget | Range / Options |
|---|---|---|
| Line style | Radio: Solid/Dashed/Dotted/Dash-dot | — |
| Line width | Scale + value label | 0.5–5.0 pt |
| Line opacity | Scale + value label | 0.0–1.0 |
| Colour | Swatch button → colorchooser + Reset button | — |
| Fill area | Checkbutton | — |
| Fill opacity | Scale + value label | 0.0–0.5 |
| Visible | Checkbutton | — |
| In legend | Checkbutton | — |

Each parameter row has a ∀ button (rightmost) that applies that
parameter to all visible nodes of the same type in the current tab.
This carries forward the existing UV/Vis \_push\_to\_all pattern.

The bottom **∀ Apply to All** button fans out every universal-section
parameter except **Colour**, **Visible**, and **In legend**. The
last two were added in Phase 4d (B-002) to give the dialog parity
with the per-row `[☑]` / `[✓/–]` controls when the sidebar collapses,
but bulk-applying them is a footgun (one click can hide every
sibling); the per-row ∀ next to each checkbox stays available for
deliberate fan-out.

### Conditional sections

Sections appear only when the selected node's type matches. They
appear below the universal section, separated by a horizontal rule
and a section label.

**Markers** — shown for: XANES, EXAFS, DEGLITCHED, AVERAGED
```
Marker shape:  ○ None  ○ Circle  ○ Square  ○ Diamond
Marker size:   [spinbox 2–12 px]
```

**Broadening** — shown for: TDDFT, BXAS\_RESULT
```
Function:  ● Gaussian  ○ Lorentzian
FWHM:      [entry]  eV  [slider]
```

**Energy shift and scale** — shown for: TDDFT, BXAS\_RESULT, FEFF\_PATHS
```
ΔE:     [entry]  eV  [slider]
Scale:  [entry]  ×   [slider]
```

**Envelope** — shown for: TDDFT, BXAS\_RESULT
```
Line width:    [slider]  pt
Fill area:     [checkbutton]
Fill opacity:  [slider]
```

**Sticks** — shown for: TDDFT
```
Line width:       [slider]  pt
Opacity:          [slider]
Tip markers:      [checkbutton]
Marker size:      [spinbox]  px
```

**Uncertainty band** — shown for: BXAS\_RESULT
```
Show band:   [checkbutton]
Band colour: [swatch]  (default: same as line, lighter)
Opacity:     [slider]
```
See OQ-002 before implementing.

**Component visibility** — shown for: TDDFT
```
☑ Total    ☑ Electric Dipole (D²)
☑ Mag. Dipole (m²)    ☑ Elec. Quad. (Q²)
```

### Bottom buttons

```
[ Apply ]  [ ∀ Apply to All ]  [ Save ]  [ Cancel ]
```

- **Apply** — apply to this node; dialog stays open
- **∀ Apply to All** — apply all style settings (except colour) to
  all visible nodes of the same type in current tab
- **Save** — apply and close
- **Cancel** — revert all changes since dialog opened; close

### Reference implementation

The existing UV/Vis Spectrum Style dialog in uvvis\_tab.py is the
reference implementation. Its layout, ∀ button pattern, and button
bar are carried forward directly. The unified dialog extends this
with conditional sections.

### Implementation notes (Phase 3)

These record decisions taken when implementing CS-05 for ambiguities
the spec left open. They are descriptive, not prescriptive — a future
design session can revisit any of them.

**Construction signature.**
```python
StyleDialog(
    parent,                  # tk.Widget for the Toplevel parent
    graph,                   # ProjectGraph
    node_id,                 # the DataNode being edited
    on_apply_to_all=None,    # callable(param_name, value)
)
```

The module-level factory `open_style_dialog(parent, graph, node_id,
on_apply_to_all=None)` enforces the per-node "focus existing"
contract: a second open request for the same `node_id` raises the
existing Toplevel rather than creating a duplicate.

**Modeless.** No `transient`, no `grab_set`. Multiple dialogs (one
per node) coexist with each other and with the main window.

**Live writes via variable traces.** Each control's Tk variable is
wired with `trace_add("write", ...)` rather than the widget's
`command=`. The trace fires for any source of change (slider drag,
`scale.set`, programmatic `var.set`, radiobutton click), which makes
the write path uniformly testable. The Scale's own `command` is not
fired by all `var.set` paths in CPython 3.12 Tk 8.6, so trace-based
wiring was preferred.

**Re-entrancy guard.** A single boolean `_suspend_writes` covers
both directions: it is set during `_write_partial` so the resulting
`NODE_STYLE_CHANGED` event delivered back to `_on_graph_event` is
treated as "our own" and skipped, and it is set during widget
refreshes triggered by external events so the Tk variable's trace
callbacks don't loop back into `set_style`.

**Cancel snapshot semantics.** `__init__` deep-copies `node.style`
into `_snapshot`. Cancel sends the snapshot through `set_style` as
a single partial. Because `set_style` merges (CS-01), keys added
during the session that were absent from the snapshot remain on the
node — the graph contract has no "remove key" verb, and threading
one in for a single dialog's revert path was deemed out of scope.
This matches the existing UV/Vis dialog's behaviour
(`uvvis_tab._do_cancel`).

**Window-close [X] is Cancel.** With live updates the window-close
gesture is wired to `_do_cancel` via `WM_DELETE_WINDOW`, so closing
the window without explicit Cancel still reverts to the snapshot.
Save closes after applying the current widget state explicitly.

**Apply is idempotent.** Live writes already keep the graph in
sync, so Apply re-emits the current widget state as one
`set_style` call (a safety net for any control whose write path
the dialog might miss). Save = Apply + destroy. Cancel = revert +
destroy.

**∀ button scope.** Per-row ∀ buttons appear only on the universal
section's six rows. Conditional sections do not carry per-row ∀
buttons because the tab-side scope of "same node" is less
well-defined for, say, a TDDFT broadening setting (does it fan out
to every TDDFT node? to every node showing a stick spectrum? to
every node sharing a parent dataset?). Adding ∀ to conditional
rows is a small follow-up once a tab needs it.

**∀ delegation.** The dialog never enumerates other nodes itself.
Per-row ∀ calls `on_apply_to_all(param_name, value)` and also
writes the value to its own node so the local widgets stay in sync
with the graph (the tab's fan-out is free to skip the dialog's own
node id; either way the dialog's node ends up with the value).

**Bottom ∀ Apply to All.** Fans out every universal-section
parameter except colour, per CS-05. The exclusion of colour is
intentional — bulk recolouring is rarely the user intent and would
collapse a meaningful palette to a single shade.

**Disabled-button affordance.** When `on_apply_to_all` is `None`
both the per-row ∀ buttons and the bottom ∀ Apply to All button
are rendered with `state=tk.DISABLED`. The user sees the
affordance and understands it's a no-op for the current host
context, rather than seeing it silently disappear.

**Style key namespacing.** Conditional sections use prefixed keys
to avoid collisions: `marker_shape`, `marker_size`,
`broadening_function`, `broadening_fwhm`, `delta_e`, `scale`,
`envelope_linewidth`, `envelope_fill`, `envelope_fill_alpha`,
`stick_linewidth`, `stick_alpha`, `stick_tip_markers`,
`stick_marker_size`, `component_total`, `component_d2`,
`component_m2`, `component_q2`. The universal-section keys
(`color`, `linestyle`, `linewidth`, `alpha`, `fill`, `fill_alpha`)
match `scan_tree_widget._DEFAULT_STYLE` so the row controls and the
dialog read/write the same dict.

**Defaults table.** `_UNIVERSAL_DEFAULTS` (kept in sync with the
scan-tree-widget defaults) and `_CONDITIONAL_DEFAULTS` together
provide a fallback for every key the dialog reads. `node.style`
takes precedence; the defaults are only consulted when the key is
absent.

**Hidden sections consume zero vertical space.** A node type absent
from `_SECTIONS_BY_TYPE` gets only the universal section. Each
conditional section is a `tk.LabelFrame` constructed only when its
name appears in the type's tuple — there is no placeholder frame,
no `pack_forget`, no hidden geometry.

**Section dispatch.** Section names map to `_build_section_<name>`
methods on the dialog class. A name with no corresponding method
is logged at WARNING and skipped, which makes it safe to add a
section name to the type table before the builder lands.

**Reset (colour) restores snapshot, not a palette default.** The
swatch's Reset button writes the colour that was in `node.style`
when the dialog opened. The dialog has no palette knowledge — the
default colour for a freshly created node is the loader's
responsibility (cf. Phase 4 friction point about
`_PALETTE[idx % len(_PALETTE)]`). Reset means "undo my colour
edits in this dialog session," not "restore an app-wide default."

**Stubbed sections.**

* **Uncertainty band** (`BXAS_RESULT`) — schema blocked on OQ-002.
  The `LabelFrame` is constructed and contains an explanatory Label
  citing OQ-002 so the gap is visible to the user rather than
  silently absent.
* **Compound result components** (`BXAS_RESULT`) — bXAS compound
  result grouping (one row vs. three vs. expandable group) is
  OQ-003. Same stub treatment as Uncertainty band.

**Subscription teardown.** The dialog binds `<Destroy>` and drops
its graph subscription and registry entry automatically. Both the
WM close hook and Tk's `<Destroy>` event can fire; the underlying
ops are idempotent.

**Plot redraw is the tab's job.** The dialog never calls a redraw
callback. Per the graph contract the tab is already subscribed to
`NODE_STYLE_CHANGED` and will redraw in response to dialog-driven
mutations.

### Implementation notes (Phase 4d)

* **`visible` / `in_legend` joined the universal section (B-002).**
  Two `tk.Checkbutton` rows live below "Fill opacity", reading
  `style["visible"]` and `style["in_legend"]` respectively. Both
  keys were added to `_UNIVERSAL_DEFAULTS` (`True` for both, the
  same defaults `scan_tree_widget._DEFAULT_STYLE` uses, so the row
  controls and the dialog read the same fallback). Toggling either
  fires a write through `_write_partial` → `set_style` exactly like
  every other universal row; the re-entrancy guard already covers
  these paths.
* **Bulk ∀ exclusion is intentional.** The `_BULK_UNIVERSAL_KEYS`
  tuple still lists only `linestyle`, `linewidth`, `alpha`,
  `fill`, `fill_alpha`. `visible` and `in_legend` are
  reachable through their per-row ∀ buttons (deliberate fan-out)
  but excluded from the bottom "∀ Apply to All" because
  bulk-applying visibility is a footgun — one click could hide
  every sibling node in the sidebar. `colour` is excluded for the
  same family of reasons (Phase 3 implementation note).
* **`_build_universal_checkbox_row` helper.** Factored out so
  `visible` / `in_legend` share construction with the existing
  `Fill area` checkbox (label + `Checkbutton` + per-row ∀ +
  refresher). The helper returns nothing — it registers into
  `_control_vars` and `_control_refresh` like every other
  universal row builder.
* **Fan-out scope (UV/Vis tab).** The tab's
  `_on_uvvis_apply_to_all` widened from `_uvvis_nodes` (UVVIS-only)
  to `_spectrum_nodes` (UVVIS + BASELINE). The widening applies to
  every key, not just the new boolean ones — a user who clicks ∀
  on a sidebar mixing UVVIS and BASELINE rows expects the value to
  reach every row regardless of type. Future BASELINE-specific
  style keys may need a tighter scope; revisit then.

---

## CS-06: Top Bar (per-tab specification)

**Defined in:** each tab's file
**Principle:** thin. Only the most-used plot controls and the primary
action. Everything else goes in Plot Settings dialog (⚙ button).

### XANES tab top bar

```
[📂 Load…]  E0: [entry]  X: [lo]→[hi] [Auto]  Y: [lo]→[hi] [Auto]
[▶ Run]  [Send to Compare]  [⚙ Plot Settings]  [status label]
```

Primary action: ▶ Run (creates provisional NORMALISED node)

### EXAFS tab top bar

```
[📂 Load…]  X: [lo]→[hi] [Auto]  Y: [lo]→[hi] [Auto]
[▶ Run EXAFS]  [Send to Compare]  [⚙ Plot Settings]  [status label]
```

Primary action: ▶ Run EXAFS (creates provisional EXAFS node)

### UV/Vis tab top bar

```
[📂 Load…]  X: ○nm ○cm⁻¹ ○eV  Y: ○Abs ○%T  Norm: [combobox]
☑ λ(nm) axis  X: [lo]→[hi] [Auto]  Y: [lo]→[hi] [Auto]
[Send to Compare]  [⚙ Plot Settings]  [status label]
```

No primary "Run" action — UV/Vis processing operations are initiated
from the left panel.

### Simulate tab top bar

```
[+ New FEFF Session]  [↗ Open FEFF Workspace]
[Send to Compare]  [status label]
```

### Compare tab top bar

```
[📂 Load Calculated…]  X: ○eV ○nm ○cm⁻¹ ○Ha  ☑ λ(nm) axis
X: [lo]→[hi] [Auto]  Y(calc): [lo]→[hi] [Auto]  Y(exp): [lo]→[hi] [Auto]
TDDFT axis: ○Left ○Right  ☑ Normalise
[Save Fig]  [Export CSV]  [⊞ Pop Out]  [⚙ Plot Settings]
```

### Plot Settings dialog contents (all tabs)

Accessed via ⚙ button in top bar. Modal dialog.

```
Fonts:
  Plot title:    Size [spinbox]  ☑ Bold
  X-axis label:  Size [spinbox]  ☑ Bold
  Y-axis label:  Size [spinbox]  ☑ Bold
  Tick labels:   Size [spinbox]
  Legend:        Size [spinbox]
  [Save as Default]  [Reset Defaults]  [Factory Reset]

Appearance:
  ☑ Grid
  Background: [colour swatch]
  Tick direction: ○In ○Out ○Both

Legend:
  ☑ Show legend
  Position: [combobox]

Title and labels:
  Title:    [entry]  [Auto]  [None]
  X label:  [entry]  [Auto]
  Y label:  [entry]  [Auto]

[Apply]  [Close]
```

---

## CS-07: Left Panel (per-tab specification)

**Defined in:** each tab's file
**Principle:** engine parameters for inline engines; session manager
for workspace-window engines; absent on Compare tab.

### XANES left panel — Larch engine selected

```
Engine: ● Larch  ○ bXAS
─────────────────────────────
Edge / Normalisation
  E0 (eV):      [spinbox]  [Auto]
  pre1 (eV):    [spinbox]
  pre2 (eV):    [spinbox]
  nor1 (eV):    [spinbox]
  nor2 (eV):    [spinbox]
  Norm order:   ○1  ●2
─────────────────────────────
AUTOBK
  rbkg (Å):     [spinbox]
  kmin bkg:     [spinbox]
─────────────────────────────
Visualisation
  ☑ μ(E) raw    ☑ Pre-edge fit
  ☑ Post-edge   ☑ Normalised μ(E)
  ☐ Background  ☐ Derivative dμ/dE
  ☑ FT window on χ(k)
─────────────────────────────
Processing
  [Auto Deglitch]  [Smooth]
  [Shift Energy…]  [Reset Scan]
  [★ Set as Default]
─────────────────────────────
              [ ▶ Run Analysis ]
```

### XANES left panel — bXAS engine selected

```
Engine: ○ Larch  ● bXAS
─────────────────────────────
bXAS Sessions
  [session list — name, status]
  [+ New Session]
─────────────────────────────
Active session: scan1 bXAS fit 1
  Status: ● Fitted  χ²=0.0023
  [↗ Open bXAS Workspace]
─────────────────────────────
              [Send to Compare]
```

### EXAFS left panel

```
Engine: ● Larch  (○ future)
─────────────────────────────
Edge / Background
  E0 (eV):   [spinbox]
  pre1–nor2: [spinboxes]
  rbkg (Å):  [spinbox]
  kmin bkg:  [spinbox]
  Norm order: ○1 ●2
─────────────────────────────
Q Space / Window
  q min (Å⁻¹): [spinbox]
  q max (Å⁻¹): [spinbox]
  dq taper:    [spinbox]
  q-weight:    ○1 ●2 ○3
  q window:    [combobox]
  [q from Plot]  [Default q]
─────────────────────────────
R Space / Window
  R min (Å):   [spinbox]
  R max (Å):   [spinbox]
  dR taper:    [spinbox]
  R display:   [entry]
  R window:    [combobox]
  [R from Plot]  [Default R]
─────────────────────────────
Display
  ☑ Show q window  ☑ Show R window
  ☑ Show FEFF markers
  ☐ Label k-space as q
─────────────────────────────
       [ ▶ Run EXAFS ]  [ Redraw ]
```

Note: "Run EXAFS" = recompute (new provisional node).
"Redraw" = re-render current result without recompute.

### UV/Vis left panel

Each operation has its own collapsible section (Phase 4j; CS-21).
All five sections start COLLAPSED — the user clicks the chevron
header of the section they want to use. The headers stack as five
short bold-font strips when everything is collapsed:

```
Processing
▶ Baseline correction
▶ Normalisation
▶ Smoothing
▶ Peak picking
▶ Second derivative
```

Expanding a section reveals its body (the existing per-operation
parameters + Apply button):

```
Processing
▶ Baseline correction
▼ Normalisation
   Spectrum: [combobox]
   Mode:     [peak | area]
   Window lo (nm): [entry]
   Window hi (nm): [entry]
   [Apply Normalisation]
▶ Smoothing
▶ Peak picking
▶ Second derivative
```

Header click anywhere on the strip toggles the section. State is
held in a per-section `tk.BooleanVar` owned by the section widget;
not persisted to project files this phase (Phase 8 concern). See
CS-21 for the widget contract.

Processing operations create provisional nodes. No "Run" button needed
for UV/Vis because operations are applied on demand, not in batch.

### Simulate left panel

```
FEFF Sessions
  ┌─────────────────────────────┐
  │ name          status        │
  │ Cu-mnt fit 1  ● committed   │
  │ Cu-mnt fit 2  ~ provisional │
  └─────────────────────────────┘
  [+ New FEFF Session]  [Delete]
─────────────────────────────
Selected: Cu-mnt fit 1
  Dataset: JZP-NK-Cu-mnt_1
  Paths: 8 included
  Result: χ²=0.0041
  [↗ Open FEFF Workspace]
─────────────────────────────
              [Send to Compare]
```

### Compare left panel

Absent. No engine, no parameters. The Compare tab is solely for
composing and presenting datasets already committed elsewhere.

---

## CS-08: Compare Tab

**File:** `compare_tab.py`
**Depends on:** CS-01, CS-02, CS-04, CS-05
**Depended on by:** nothing (terminal in the workflow)

### Responsibility

The Compare tab receives COMMITTED DataNodes sent from any other tab
and displays them together on a shared matplotlib figure with dual
y-axes (calculated left/right, experimental opposite). It provides
the figure generation, styling, and export capabilities for
publication-quality output.

### Layout

Three-zone: no left panel · centre (matplotlib figure) · right
(ScanTreeWidget, heterogeneous).

### Right sidebar — heterogeneous ScanTreeWidget

Nodes grouped by category, within a single ScanTreeWidget instance:

```
── Calculated ─────────────────────
[●] TDDFT · Electric Dipole     [⚙][⌥][✕]
[●] FEFF · Cu-mnt fit 1         [⚙][⌥][✕]
── Experimental ───────────────────
[●] JZP-NK TEY normalised       [⚙][⌥][✕]
[●] NiAqua-Ebroadened           [⚙][⌥][✕]
```

Groups are collapsible. Ordering within groups is drag-reorderable
(controls legend order and plot draw order).

### TDDFT file loading

Accessed via [📂 Load Calculated…] in top bar, or File menu.
Loading an ORCA .out file creates a DataNode(type=TDDFT) directly
as a COMMITTED node in the Compare tab graph. The section selector
(Electric Dipole, Magnetic Dipole, etc.) appears after load as a
property of the TDDFT node, editable from its metadata panel.

### Dual y-axis

Calculated data (TDDFT, FEFF, bXAS) defaults to the left y-axis.
Experimental data (XANES, EXAFS, UV/Vis) defaults to the right y-axis.
The user can override per-node via the style dialog or top bar radio.

### Canvas interactions (retained from existing implementation)

- Inset drag (create, move, resize)
- Legend drag
- Hover tooltip on data points

### Open questions affecting this component

- OQ-002: uncertainty band display for bXAS results
- OQ-003: bXAS compound result grouping in sidebar
- OQ-005: Replace-or-Add for TDDFT files

---

## CS-09: FEFF Workspace Window

**File:** `feff_workspace.py`
**Depends on:** CS-01, CS-02
**Source:** Extract and rehouse the existing FEFF sub-tab from
`exafs_analysis_tab.py`. Reuse the existing implementation where
possible; the goal is relocation, not rewrite.

### Window properties

- Non-blocking Toplevel window
- Independently resizable
- Title: "FEFF Workspace — {session name}"
- Multiple instances supported (one per active session)
- Survives main window tab switches
- Communicates with main window via shared ProjectGraph

### Layout

```
┌─────────────────────────────────────────────────────┐
│ Session: [name entry]   Dataset: [label]   [▶ Run FEFF] │
├──────────────┬──────────────────────────────────────┤
│ Structure    │  Path list (treeview)                │
│              │  index · reff · degen · nleg · ☑     │
│ [XYZ/CIF    │                                      │
│  loader]     │  Path amplitude preview (canvas)     │
│              │                                      │
│ FEFF params  ├──────────────────────────────────────┤
│              │  FEFF execution log                  │
└──────────────┴──────────────────────────────────────┘
│ [Commit Result]  [Discard]  [Send to Compare]       │
└─────────────────────────────────────────────────────┘
```

### Relocation checklist

The following controls exist in the current EXAFS FEFF sub-tab and
must be relocated here:

- Workdir entry + browse button → `_feff_dir_var`
- Executable entry + browse button → `_feff_exe_var`
- Load Paths button → `_load_feff_paths()`
- Run FEFF button → `_run_feff()`
- XYZ file entry + browse + Load XYZ → `_xyz_path_var`
- Base name entry, padding entry, force cubic checkbox,
  absorber entry, edge combobox, spectrum combobox,
  KMESH entry, equivalence entry
- Write FEFF Bundle button → `_write_xyz_feff_bundle()`
- Path treeview → `_feff_tree`
- Path amplitude canvas → `_canvas_feff`
- Execution log text widget → `_feff_log`

### Commit behaviour

Committing a FEFF result creates a DataNode(type=FEFF\_PATHS) with:
- arrays: path amplitudes, phases, and the total simulated EXAFS
- metadata: path list with parameters, FEFF version, working directory
- provenance: linked to the EXAFS DataNode that was the input

---

## CS-10: bXAS Workspace Window

**File:** `bxas_workspace.py`
**Depends on:** CS-01, CS-02, CS-11 (bXAS engine)
**Depended on by:** XANES tab (engine selector)

### Window properties

Same as FEFF Workspace: non-blocking, independently resizable, one
per session.

### Layout

```
┌──────────────────────────────────────────────────────┐
│ Session: [name]  Dataset: [label]  [▶ Fit]  [Reset]  │
├───────────────────┬───────────────────────────────────┤
│ Background model  │  Main plot: data + fit + residuals │
│ [poly / Victoreen]│                                   │
│ order n: [spinbox]│                                   │
│                   ├───────────────────────────────────┤
│ Spectral model    │  Residuals panel                  │
│ [component list]  │                                   │
│ [+ Add component] ├───────────────────────────────────┤
│                   │  Parameter table                  │
│ Fit bounds        │  name · value · stderr · min · max│
│ E min: [entry]    │                                   │
│ E max: [entry]    │                                   │
│                   │  [Correlation matrix] (collapsible)│
└───────────────────┴───────────────────────────────────┘
│ [Commit Result]  [Discard]  [New Branch]  [Compare Models] │
└────────────────────────────────────────────────────────┘
```

### Commit behaviour

Committing a bXAS result creates a DataNode(type=BXAS\_RESULT).
See OQ-002 and OQ-003 for the uncertainty band and compound result
design decisions that must be resolved before implementing this.

---

## CS-11: bXAS Engine

**File:** `bxas_engine.py`
**Depends on:** CS-02 (DataNode)
**Depended on by:** CS-10 (bXAS Workspace)

### Responsibility

Python reimplementation of the BlueprintXAS unified background
subtraction + spectral fitting pipeline. Background and spectral model
parameters are fitted simultaneously so that errors from background
choices propagate into fitted spectral parameters.

### Dependencies (external packages)

- `lmfit` — parameter management, fitting, uncertainty estimation
- `scipy` — numerical routines (integration, interpolation)
- `numpy` — array operations
- `uncertainties` — (optional) explicit error propagation arithmetic

### Core model

The observable is:

```
μ_obs(E) = background(E; θ_bg) + edge_step × normalised_model(E; θ_model)
```

Where:
- `background(E; θ_bg)` is a Victoreen or polynomial function
- `normalised_model` is either a theoretical spectrum (from TDDFT or
  FEFF) or an empirical lineshape
- `θ_bg` and `θ_model` are optimised simultaneously by lmfit

### Interface

```python
class BXASEngine:
    def __init__(self, data_node: DataNode)

    def set_background_model(self, model: str,
                              order: int = 2) -> None
        # model: "victoreen" | "polynomial"

    def set_spectral_model(self, model_node: DataNode) -> None
        # model_node: a TDDFT or FEFF_PATHS node

    def set_fit_range(self, e_min: float, e_max: float) -> None

    def fit(self) -> tuple[DataNode, OperationNode]
        # returns (BXAS_RESULT DataNode, OperationNode)
        # both PROVISIONAL until committed

    def get_residuals(self) -> np.ndarray

    def get_parameter_table(self) -> pd.DataFrame
        # columns: name, value, stderr, min, max, vary

    def get_correlation_matrix(self) -> np.ndarray
```

### What this component does NOT do

- Does not interact with Tkinter directly
- Does not commit nodes — the workspace window handles commit/discard
- Does not validate that the input node is appropriate type — the
  workspace window handles that

---

## CS-12: Provenance Log Panel

**File:** `log_panel.py`
**Depends on:** CS-01 (ProjectGraph)
**Depended on by:** binah.py (main window)

### Responsibility

Collapsible panel at the bottom of the main window. Shows committed
operations in reverse chronological order. The human-readable audit
trail of the scientific record.

### States

**Collapsed (default):** single line showing last committed operation.
```
14:35 · normalise [larch] · scan1 TEY → scan1 TEY normalised    [▲]
```

**Expanded:** scrollable list, filterable.
```
Filter: [all types ▾]  [all datasets ▾]  [all engines ▾]   [Export…]
────────────────────────────────────────────────────────────────────
14:35  NORMALISE   scan1 TEY → scan1 TEY normalised      larch 0.9.80
14:32  DEGLITCH    scan1 TEY → scan1 TEY deglitched      internal
14:28  LOAD        scan1.dat → scan1 TEY raw             internal
14:15  LOAD        cumnt.out → TDDFT Electric Dipole     internal
```

Each row is clickable. Clicking navigates to the corresponding node
in whichever tab owns it.

### What does and does not appear

**Appears:** COMMITTED operations only.
**Does not appear:** provisional operations, discarded branches,
style changes, axis limit adjustments, plot setting changes.

### Export

[Export…] button opens a save dialog. Exports the filtered log view
as a JSONL file or as a human-readable text summary suitable for a
methods section.

---

## CS-13: Project File I/O

**File:** `project_io.py`
**Depends on:** CS-01, CS-02, CS-03
**Depended on by:** binah.py (File menu actions)

### Responsibility

Serialise and deserialise the ProjectGraph to/from the .ptproj/
directory format. Handle raw file copying, hash verification, and
provisional session recovery.

### Save

1. Write project.json (metadata, graph index, app UI state)
2. For each COMMITTED DataNode: write {id}.json + {id}.npz to
   graph/committed/
3. For each COMMITTED OperationNode: write {id}.json to
   graph/committed/
4. For each PROVISIONAL node: write to graph/provisional/
5. Append new committed operations to log.jsonl
6. Verify raw/ copies are current (copy any new raw files)

### Load

1. Read project.json
2. Load all nodes from graph/committed/ → restore to graph as COMMITTED
3. Check graph/provisional/ → if present, offer recovery dialog:
   "This project has unsaved provisional work. Restore or discard?"
4. Restore app UI state (active tab, sidebar scroll, etc.)

### Raw file handling

On first load of any external file:
1. Copy file to raw/{node\_id}__{original\_filename}
2. Compute SHA-256 hash of copy
3. Store in raw/manifest.json

On project load: verify hashes of existing raw copies. Warn if any
hash does not match (file tampering or corruption).

### Reproducibility report

```python
def export_reproducibility_report(
    graph: ProjectGraph,
    compare_node_ids: list[str],
    output_path: Path,
    format: str = "text"  # "text" | "json"
) -> None
```

Generates a human-readable or machine-readable summary of all
committed operations that contributed to the specified Compare
output nodes, traversing the full provenance chain.

### Implementation notes (Phase 4a)

These record the load-time decisions taken during Phase 4a (UV/Vis
pilot tab) for the parts of CS-13 that the spec left open. They
are descriptive — a future design session can revisit any of them
— and they apply uniformly to every tab that loads experimental
data into the graph.

**Load is a three-node operation, not one.** A file load creates
*three* graph entries together:

1. a `COMMITTED RAW_FILE` `DataNode` — the immutable provenance
   anchor (ARCHITECTURE.md §5.3),
2. a `COMMITTED LOAD` `OperationNode` — the audit-trail counterpart,
3. a `COMMITTED` technique-specific `DataNode` (e.g. `UVVIS`) —
   carrying the parsed arrays.

Edges wire `RAW_FILE → LOAD → UVVIS` via `add_edge`. All three
land COMMITTED in the same gesture. The rationale: parsing the
on-disk format into numpy arrays is bookkeeping, not science. The
analyst did not yet make any analytic choice, so the parsed result
is as canonical as the raw bytes — there is no reason to require a
separate "commit" step before the user can see the spectrum on the
plot. Analytic operations (baseline correction, normalisation,
smoothing) start PROVISIONAL as before; the load is the only path
that lands directly at COMMITTED for the technique node.

**Default colour assignment lives in the loader.** The loader
populates `node.style["color"] = _PALETTE[i % len(_PALETTE)]` at
UVVIS-DataNode creation, where `i` is the count of pre-existing
UVVIS nodes (any state) at the moment of load. This resolves Phase
2 friction point #3: a freshly-loaded node opens the unified
`StyleDialog` with a non-empty starting colour, and Reset restores
that snapshot. The palette is module-private to the loader; the
`StyleDialog` (CS-05) has no palette knowledge.

**No automatic raw-file copy or SHA-256 yet.** Until project I/O is
wired into the tab the RAW_FILE node only records `original_path`
and `file_format` in its metadata. The `sha256` and `copied_to`
fields land later, the first time the project is saved into a
`.ptproj/` directory via `project_io.copy_raw_file`. Hash
verification on subsequent project loads (CS-13 §"Raw file
handling") is unaffected — it kicks in once the manifest exists.

**Duplicate detection is `(source_file, label)`-keyed.** Reloading
a file already in the graph is a no-op: `_has_existing_load`
checks both the source path and the label of every non-DISCARDED
UVVIS node. This matches the existing pre-graph behaviour and
avoids creating a second RAW_FILE/LOAD pair for the same on-disk
file. Whether to use a stronger SHA-256-based identity is left for
the project-I/O wiring session.

**Parser metadata is stored under a namespaced key.** The CS-02
UVVIS metadata convention reserves `x_unit`, `y_unit`,
`instrument`, and `source_file` for the canonical fields. The
parser's free-form metadata dict (e.g. OLIS sample name, raw
y-unit hint, header-line preamble) is preserved under
`metadata["parser_metadata"]` so tabs can reach it without
colliding with the convention.

### Forward-compat note (Phase 4f)

CS-17 introduces a single-node export path that is **not** project
save. The exported `.csv` / `.txt` files carry a `# `-prefixed
provenance header whose shape (Ptarmigan version, ISO 8601 UTC
timestamp, full node id, node label, then a topologically-sorted
list of ancestor lines) mirrors what a future CS-13 full-project
serialiser will need for the per-node JSON sidecar. Treat CS-17 as
a forward-compat probe of the header shape: when CS-13 lands,
either reuse `provenance_export.build_provenance_header` directly or
ensure the project sidecar records at least the same set of fields
under structurally-similar JSON keys.

---

## CS-14: Plot Settings Dialog

**File:** `plot_settings_dialog.py`
**Depends on:** nothing in the graph layer (tab-private UI state)
**Depended on by:** every tab's top bar ⚙ button; first wired into
`uvvis_tab.py` in Phase 4b

### Responsibility

Single modal dialog for plot-level rendering controls — fonts, grid,
background colour, legend show/position, tick direction, title and
axis-label text. Per ARCHITECTURE.md §3 and CS-06, every analysis tab
hosts one ⚙ button in its top bar that opens a Plot Settings dialog
configured for that tab. The dialog mutates a tab-private
configuration dict; the tab's `_redraw` reads from that dict.

### Window properties

- Title: "Plot Settings"
- Modal — `transient(parent)` + `grab_set()`
- One dialog per tab; opening ⚙ on a tab that already has a dialog
  open focuses the existing window rather than creating a duplicate
- `[X]` window-close is treated as Cancel (matches CS-05 StyleDialog)

### Sections (per CS-06)

| Section | Controls |
|---|---|
| **Fonts** | Title / X-label / Y-label / Tick label / Legend font sizes; Title / X-label / Y-label bold; Save-as-Default / Reset Defaults / Factory Reset row |
| **Appearance** | Grid on/off; background colour swatch; tick direction (in / out / both) |
| **Legend** | Show legend; position (matplotlib `loc` combobox) |
| **Title and labels** | Title / X-label / Y-label text entries with `[Auto]` (and `[None]` on Title) buttons that flip per-label mode |

Each section is rendered into its own `tk.LabelFrame`. Hidden
sections consume zero vertical space — they simply aren't created.
The configuration dict's `_sections` key (or the `sections=`
constructor argument) controls which sections render; default is all
four.

### Construction

```python
PlotSettingsDialog(
    parent,                 # tk.Widget; also the registry key
    config,                 # dict — tab-private plot config,
                            # mutated in place on Apply
    on_apply=None,          # callable(); invoked after Apply (and
                            # again on Cancel that reverts an Apply)
    sections=None,          # explicit section filter; falls back to
                            # config["_sections"] then to the
                            # all-four module default
)
```

Or via the module-level factory which handles the per-host registry:

```python
open_plot_settings_dialog(parent, config, on_apply=None, sections=None)
```

### Bottom buttons

```
[ Apply ]  [ Save ]  [ Cancel ]
```

- **Apply** — copy the working copy into the caller's config dict
  (in place), invoke `on_apply`, dialog stays open for further edits
- **Save** — `_do_apply()` + `destroy()`. The "Save & Close" gesture;
  commits the working copy, fires `on_apply`, and closes the dialog.
  Mirrors `style_dialog.StyleDialog._do_save` so the Cancel-vs-Save
  mental model reads the same across every modal in the app
  (Phase 4l; CS-23)
- **Cancel** — revert config to the snapshot taken at `__init__`,
  invoke `on_apply` if anything had to be reverted, destroy

The `∀ Apply to All` slot from CS-05 StyleDialog's four-button row is
absent here — Plot Settings is one tab-private config dict per dialog
with no node-bulk concept to fan out to. A future cross-tab-bulk
feature ("apply this title font size to every tab") would re-introduce
the slot; flagged as Phase 4l friction #1 in BACKLOG.md.

### Implementation notes (Phase 4b)

These record decisions taken when implementing CS-14 for the
ambiguities the spec left open. Descriptive, not prescriptive — a
future design session can revisit any of them.

**Modal contract.** `transient(parent.winfo_toplevel())` plus
`grab_set()` exactly per CS-06. The transient call is best-effort
(wrapped in a try/except for the unusual case where the parent is
detached), but `grab_set` is unconditional — the modal contract is
the dialog's primary affordance and must not be silently skipped.
This is the deliberate difference from CS-05 StyleDialog, which is
modeless. CS-14 dialogs do not coexist; CS-05 dialogs do.

**Per-host registry, not per-node.** `_open_dialogs` keys on
`id(parent)` rather than a node id (CS-05) because a tab's plot
settings are tab-scoped, not node-scoped. A second
`open_plot_settings_dialog(parent, ...)` call on the same parent
focuses the existing window.

**Working-copy semantics.** Slider, spinbox, checkbox, and combobox
edits update an in-memory `self._working` dict via Tk variable
`trace_add("write")` callbacks. Nothing reaches the caller's config
or the plot until Apply. This differs from CS-05 — the StyleDialog
writes through the graph on every keystroke for live preview, but a
modal Plot Settings dialog with a single Apply gesture is what
CS-06 calls for. Live preview is still possible: Apply commits the
current state but leaves the dialog open, so the user can iterate.

**Cancel is a session-snapshot revert, not an undo stack.** The
snapshot is taken in `__init__` and restored on Cancel regardless of
how many Applies happened in between. This matches the user's
expectation of a Cancel gesture in a modal dialog. There is no
"revert just my last change" affordance.

**Save = Apply + close (CS-23).** The Save button added in Phase 4l
is a thin wrapper: `_do_save()` calls `_do_apply()` and then
`destroy()`. It exists so the user has an explicit "I'm done — keep
my edits" gesture; before CS-23 the only path to commit-and-close was
Apply followed by [X], and the protocol handler treated [X] as Cancel
(silently reverting the just-committed edit). Save fires `on_apply`
once before destroy — the ordering is documented but not yet
test-pinned (Phase 4l friction #3). The `Save` button label was
chosen over `Save & Close` to mirror the CS-05 StyleDialog vocabulary
exactly: every modal in the app uses the same word for the same
gesture.

**Save-as-Default / Reset Defaults / Factory Reset are working-copy
operations.** None of the three commits to the caller's config; only
Apply does. So the user flow is "Save as Default, then Apply" if
they want the tab to also adopt the saved values. The buttons sit
inside the Fonts section (per CS-06 layout) but their scope is the
full working copy — they are not Fonts-only.

**`_FACTORY_DEFAULTS` / `_UNIVERSAL_DEFAULTS` / `_USER_DEFAULTS`.**
Three module-level dicts. `_FACTORY_DEFAULTS` is the
ship-with-the-app baseline; `_UNIVERSAL_DEFAULTS` is currently a
shallow copy alias kept distinct so a future design session can
split "fallback for unset keys" from "what Factory Reset writes"
without a global rename. `_USER_DEFAULTS` is mutable and starts
empty — Save-as-Default writes the working copy here, Reset Defaults
reads from here (with `_FACTORY_DEFAULTS` fallback when empty).

**Persistence to project.json is deferred (CS-13 follow-up).** The
`_USER_DEFAULTS` lifetime is the process. Persistence to project
files lands in the project-I/O wiring session; CS-14 does not write
to disk. The tab initialises its config from `_USER_DEFAULTS` if
non-empty, falling back to `_FACTORY_DEFAULTS`, so newly opened
dialogs in the same session pick up the user's saved values.

**Title / X-label / Y-label modes.** Each label row carries both a
text and a mode field (`"auto" | "none" | "custom"`, with X/Y rows
omitting `"none"` per CS-06). The dialog cannot compute the
auto-derived label text — that is tab-specific (e.g. "Wavelength
(nm)" for UV/Vis, depending on the active x-unit). So Auto and
None are mode flags; the entry shows whatever the user typed; the
tab's `_redraw` picks `xlabel_text` only when `xlabel_mode ==
"custom"` and otherwise computes the auto value itself.

**Subscription teardown.** The dialog binds `<Destroy>` and drops
its registry entry automatically. Both the WM close hook and Tk's
`<Destroy>` event can fire; the underlying op is idempotent.

**No graph subscription.** Plot Settings is tab-private UI state,
not graph state — the dialog never subscribes to `GraphEvent` and
the tab's `_redraw` is invoked through the explicit `on_apply`
callback rather than via `NODE_STYLE_CHANGED`. This matches Phase
4a friction point #4: a graph-side view-state payload would be the
larger refactor; Plot Settings sidesteps it by keeping the config
on the tab.

---

## CS-15: UV/Vis Baseline Correction

**File:** `uvvis_baseline.py` (pure module) +
`uvvis_tab.py` left panel + `_apply_baseline`
**Depends on:** CS-01 (ProjectGraph), CS-02 (DataNode `BASELINE`
variant), CS-03 (OperationNode `BASELINE` variant), CS-07 (UV/Vis
left panel), `numpy`, `scipy.interpolate.CubicSpline`
**Depended on by:** UV/Vis tab — first user-initiated processing
operation in the new architecture (Phase 4c)

### Responsibility

Subtract a baseline from a UV/Vis spectrum, producing a new
`BASELINE` `DataNode`. Each Apply gesture is a single
provisional operation; the user inspects the result and decides
to commit (lock in) or discard via the right-sidebar
`ScanTreeWidget`.

### Five modes (single OperationType, params discriminated by mode)

A single `OperationType.BASELINE` covers all five. The
discriminator is `params["mode"]`; the remaining keys are the
mode-specific sub-schema.

| Mode | Required `params` keys | Algorithm |
|---|---|---|
| `linear`     | `anchor_lo_nm`, `anchor_hi_nm`              | Two-point baseline through the absorbance values at the two anchor wavelengths (linearly interpolated from neighbouring data points). |
| `polynomial` | `order` (int), `fit_lo_nm`, `fit_hi_nm`     | Polynomial of given order fit (`np.polyfit`) to the data inside the wavelength window; evaluated across the full input range. |
| `spline`     | `anchors` (list of nm)                      | Cubic interpolating spline (`scipy.interpolate.CubicSpline`) through `(anchor, sampled_absorbance)` points. Falls back to quadratic / linear when `len(anchors) < 4`. |
| `rubberband` | (none)                                       | Lower convex hull (Andrew's monotone chain) of the `(wavelength, absorbance)` point set, linearly interpolated onto the input grid. |
| `scattering` (CS-24) | `n` (float ≥ 0 OR string `"fit"`), `fit_lo_nm`, `fit_hi_nm` | Power-law `B(λ) = c · λ^(-n)` for colloidal / turbid samples. Fixed `n` → closed-form least-squares for the amplitude `c` only. `n="fit"` → log–log linear regression (`log A = log c − n · log λ`) recovers both; requires absorbance > 0 throughout the fit window. Baseline is fit on the window and subtracted across the full input range. |

### Pure module

`uvvis_baseline` is Tk-free and graph-free:

```python
import uvvis_baseline
corrected = uvvis_baseline.compute(
    "linear", wavelength_nm, absorbance,
    {"anchor_lo_nm": 200.0, "anchor_hi_nm": 800.0},
)
```

Each `compute_*` returns the baseline-subtracted absorbance as a
numpy array of the same shape as `absorbance`. Missing required
params raise `KeyError`; bad inputs (shape mismatch, polynomial
order without enough points) raise `ValueError`. The tab catches
both and reports them via `messagebox`.

### Provisional / Commit / Discard flow

Per ARCHITECTURE.md §5. One Apply gesture creates exactly two
nodes wired `parent → op → child`:

* **`OperationNode`** (`type=BASELINE`,
  `engine="internal"`, `engine_version=PTARMIGAN_VERSION`,
  `params={"mode": ..., **mode_specific}`,
  `state=PROVISIONAL`).
* **`DataNode`** (`type=BASELINE`,
  arrays `{wavelength_nm: parent_wl, absorbance: parent_a -
  computed_baseline}`, metadata carried forward from the parent
  plus `baseline_mode` + `baseline_parent_id`,
  `state=PROVISIONAL`, default style picked from the loader's
  palette so the new curve is visually distinct).

The UV/Vis tab subscribes to graph events as before; the
ScanTreeWidget filter expanded from `[NodeType.UVVIS]` to
`[NodeType.UVVIS, NodeType.BASELINE]` so the new node appears
in the right sidebar with the provisional indicator. Commit
(`graph.commit_node`) and discard (`graph.discard_node`) flow
through the existing `ScanTreeWidget` gestures.

`_redraw` iterates `self._spectrum_nodes()` (UVVIS + BASELINE)
and renders both via the same matplotlib code path — both share
the `arrays["wavelength_nm"]` + `arrays["absorbance"]`
convention, so no rendering branch is needed.

### Left-panel UI (CS-07 §"UV/Vis left panel" + Phase 4c)

* **Subject combobox** — chooses which UVVIS / BASELINE node to
  act on. Re-populated on graph events that change the live set
  (`NODE_ADDED`, `NODE_DISCARDED`, `NODE_LABEL_CHANGED`,
  `NODE_ACTIVE_CHANGED`).
* **Baseline mode combobox** — `linear` / `polynomial` /
  `spline` / `rubberband` / `scattering`. On change, the parameter
  row frame rebuilds. Combobox values pull from
  `uvvis_baseline.BASELINE_MODES` so adding a mode in the pure
  module auto-grows the combobox.
* **Conditional parameter rows** —
  * linear: two anchor entries (nm).
  * polynomial: order spinbox + two fit-window entries (nm).
  * spline: comma-separated anchor entry (nm).
  * rubberband: a single "(parameter-free convex hull)" label.
  * scattering (CS-24): `n:` Entry (default `"4"` ≈ Rayleigh) +
    `Fit n` Checkbutton (disables the n entry when checked) +
    two fit-window entries (nm). When the checkbox is on,
    `_collect_baseline_params` emits `params["n"] = "fit"`.
* **`Apply Baseline` button** — runs `_apply_baseline()`.

Anchor capture from the plot (click-drag-on-axis) is out of
scope for Phase 4c; the user types nm values directly. Live
preview is also out of scope — each Apply produces a fresh
provisional node, and iteration is via discard + re-apply.

### Implementation notes (Phase 4c)

* **Single `OperationType.BASELINE` decision (Phase 4a friction
  point #1).** Resolved in favour of one variant + a
  `mode`-discriminated params dict rather than four separate
  `OperationType` variants. The four sub-schemas live next to
  each other in the params dict; reproducibility (CS-03 params
  completeness) holds because every key needed to recompute the
  exact baseline is captured.
* **Subject is selected, not implicit.** The left panel hosts a
  combobox of every live UVVIS / BASELINE node rather than
  inferring the subject from the right sidebar (which has no
  selection model yet). Adding a row-selection state to
  `ScanTreeWidget` was deferred — the combobox is a smaller
  surface that does not require a widget-wide refactor.
* **BASELINE renders identically to UVVIS.** Both share the
  array-key convention. The sidebar filter was widened rather
  than building a parallel rendering branch.
* **Default colour picked from the same palette.** A BASELINE
  node's default colour is `_PALETTE[(n_uvvis + n_baseline) %
  len(_PALETTE)]` so a parent and its derived baseline are
  visually distinct without requiring the user to pick a colour.
* **B-001, B-003, B-004 fixes shipped alongside.** Phase 4c is
  the first user-initiated operation node, so the bug register
  was the first time Phase 4 manually exercised the sidebar's
  Rename / history / norm-area paths under load. Each fix is its
  own commit; CS-04 §"Context menu" + §6.2 explicitly call out
  what those fixes restore.

### Implementation notes (Phase 4m, CS-24 — scattering mode)

* **Power-law form per the brief.** `B(λ) = c · λ^(-n)` — a pure
  proportional fit with no additive constant. This matches the
  Phase 4l USER-FLAGGED register entry verbatim (`A_scatter(λ) ∝
  1/λ^n`). A composite "scattering+offset" mode (`B(λ) = a + c ·
  λ^(-n)`) is the natural follow-up if users find that the pure
  form leaves a flat residual; deferred to a future session and
  logged as Phase 4m friction #3.
* **Fit window vocabulary reused from polynomial mode.** Same
  `fit_lo_nm` / `fit_hi_nm` keys, same semantics ("peak-free
  window; baseline subtracted across the full input range"),
  same swap-on-out-of-order tolerance. The user types nm anchors
  directly, identical to the polynomial flow.
* **`n` is dual-typed: numeric or `"fit"`.** Numeric `n` → linear
  least-squares for `c` only via the closed-form `c = Σ(A·λ^-n) /
  Σ(λ^-2n)`. `n="fit"` → linear regression in log space (`log A =
  log c − n·log λ`) recovers both parameters simultaneously.
  Log-fit requires absorbance > 0 throughout the fit window —
  otherwise raises `ValueError` (the dialog routes to messagebox
  like the other modes). Numeric n tolerates noise dipping
  negative.
* **`params["n"] = "fit"` is preserved verbatim in `op.params`.**
  CS-03's "params sufficient to reproduce" rule is satisfied
  because rerunning the op recovers the same n via the same log
  fit. The recovered numeric n is *not* persisted into the
  OperationNode today; surfacing it in a sibling
  `params["n_fitted"]` (so export headers and tooltips can read
  it without re-running the fit) is logged as Phase 4m friction
  #2 — same shape applies to any future op that fits a parameter
  the user didn't pin.
* **No new enum, no renderer changes.** `OperationType.BASELINE`
  + `NodeType.BASELINE` already exist (CS-15); `_DISPATCH` and
  `BASELINE_MODES` grew by one entry; `_collect_baseline_params`
  gained a single branch. The provisional → commit / discard
  flow, the ScanTreeWidget filter, the curve render path, and
  `_spectrum_nodes()` all needed zero changes.
* **UI: Fit-n disables the n entry on rebuild.** The "Fit n"
  Checkbutton's command calls `_sync_n_entry_state` which sets
  the n Entry's `state="disabled"` while the checkbox is on. The
  contract relies on the param-row rebuild order
  (`_refresh_baseline_param_rows` calls `_sync_n_entry_state` at
  the end of the scattering branch); same brittleness pattern as
  the polynomial-order Spinbox pre-CS-21. Logged as Phase 4m
  friction #1.

---

## CS-16: UV/Vis Normalisation

**File:** `uvvis_normalise.py` (pure module + `NormalisationPanel`
co-located) + `uvvis_tab.py` left panel
**Depends on:** CS-01 (ProjectGraph), CS-02 (DataNode `NORMALISED`
variant), CS-03 (OperationNode `NORMALISE` variant), CS-07 (UV/Vis
left panel), `numpy`
**Depended on by:** UV/Vis tab — second user-initiated processing
operation in the new architecture (Phase 4e); resolves Phase 4a
friction point #2

### Responsibility

Divide a UV/Vis spectrum by a scalar derived from a chosen window of
its absorbance values, producing a new `NORMALISED` `DataNode`. Each
Apply gesture is a single provisional operation; the user inspects
the result and decides to commit (lock in) or discard via the
right-sidebar `ScanTreeWidget`.

### Two modes (single OperationType, params discriminated by mode)

A single `OperationType.NORMALISE` covers both. The discriminator is
`params["mode"]`; the remaining keys are the mode-specific
sub-schema. Mirrors the CS-15 BASELINE convention.

| Mode | Required `params` keys | Algorithm |
|---|---|---|
| `peak` | `peak_lo_nm`, `peak_hi_nm` | Divide the absorbance by `np.nanmax(np.abs(absorbance[mask]))` where `mask` selects samples whose wavelength is in `[peak_lo_nm, peak_hi_nm]`. |
| `area` | `area_lo_nm`, `area_hi_nm` | Divide the absorbance by `abs(np.trapezoid(np.abs(absorbance[mask]), wavelength_nm[mask]))` over the same window. The absolute value protects against descending wavelength arrays (B-003 root cause from Phase 4c). |

There is no `none` mode — the absence of normalisation is the
absence of a NORMALISED node, not a no-op operation. The dispatcher
rejects `"none"` (and any other unknown mode) with `ValueError`.

### Pure module

The compute layer is Tk-free and graph-free:

```python
import uvvis_normalise as un
normalised = un.compute(
    "peak", wavelength_nm, absorbance,
    {"peak_lo_nm": 400.0, "peak_hi_nm": 600.0},
)
```

Each `compute_*` returns the normalised absorbance as a numpy array
of the same shape as `absorbance`. Missing required params raise
`KeyError`; bad inputs (shape mismatch, empty window, zero divisor)
raise `ValueError`. The panel catches both and reports them via
`messagebox`.

### Provisional / Commit / Discard flow

Per ARCHITECTURE.md §5. One Apply gesture creates exactly two nodes
wired `parent → op → child`:

* **`OperationNode`** (`type=NORMALISE`,
  `engine="internal"`, `engine_version=PTARMIGAN_VERSION`,
  `params={"mode": ..., **mode_specific}`,
  `state=PROVISIONAL`).
* **`DataNode`** (`type=NORMALISED`,
  arrays `{wavelength_nm: parent_wl, absorbance: parent_a /
  divisor}`, metadata carried forward from the parent plus
  `normalisation_mode` + `normalisation_parent_id`,
  `state=PROVISIONAL`, default style picked from the loader's
  palette so the new curve is visually distinct).

The UV/Vis tab subscribes to graph events as before; the
`ScanTreeWidget` filter expanded from `[NodeType.UVVIS,
NodeType.BASELINE]` to `[NodeType.UVVIS, NodeType.BASELINE,
NodeType.NORMALISED]` so the new node appears in the right sidebar
with the provisional indicator. Commit (`graph.commit_node`) and
discard (`graph.discard_node`) flow through the existing
`ScanTreeWidget` gestures.

`_redraw` iterates `self._spectrum_nodes()` (UVVIS + BASELINE +
NORMALISED) and renders all three via the same matplotlib code path
— they share the `arrays["wavelength_nm"]` + `arrays["absorbance"]`
convention, so no rendering branch is needed. The tab's draw-time
`_y_with_norm` transform retired with this session.

### Left-panel UI (CS-07 §"UV/Vis left panel" + Phase 4e)

`NormalisationPanel` is a `tk.Frame` subclass that lives below the
baseline section in the left panel, separated by a horizontal
`ttk.Separator`. The panel hosts:

* **Subject combobox** — chooses which UVVIS / BASELINE /
  NORMALISED node to normalise. Chained normalisation is allowed (a
  NORMALISED node is itself a candidate subject). Re-populated on
  graph events that change the live set (`NODE_ADDED`,
  `NODE_DISCARDED`, `NODE_LABEL_CHANGED`, `NODE_ACTIVE_CHANGED`).
* **Mode combobox** — `peak` / `area`. On change the parameter row
  frame rebuilds.
* **Window entries** — two `tk.Entry` rows for the window endpoints
  (`Peak lo / hi (nm)` or `Area lo / hi (nm)`). Required for both
  modes; blanks are rejected at Apply per CS-03 params completeness.
* **`Apply Normalisation` button** — runs `_apply()`.

Anchor capture from the plot (click-on-axis) is out of scope for
Phase 4e; the user types nm values directly. Live preview is also
out of scope — each Apply produces a fresh provisional node, and
iteration is via discard + re-apply.

### Implementation notes (Phase 4e)

* **Single `OperationType.NORMALISE` decision.** Resolved in favour
  of one variant + a `mode`-discriminated params dict rather than
  separate `NORMALISE_PEAK` / `NORMALISE_AREA` variants. Mirrors
  the CS-15 BASELINE precedent so the two user-initiated UV/Vis
  operations share the same shape.
* **Subject is selected, not implicit.** The panel hosts its own
  combobox of every live UVVIS / BASELINE / NORMALISED node, fed by
  a callable the host hands over (`spectrum_nodes_fn`). Adding a
  row-selection state to `ScanTreeWidget` was deferred (Phase 4c
  friction point #1).
* **NORMALISED renders identically to UVVIS / BASELINE.** All three
  share the array-key convention. The sidebar filter and
  `_spectrum_nodes` walk were widened rather than building a
  parallel rendering branch.
* **Default colour picked from the same palette.** A NORMALISED
  node's default colour is `_PALETTE[(n_uvvis + n_baseline +
  n_normalised) % len(_PALETTE)]` so a parent and its derivatives
  are visually distinct without requiring the user to pick a colour.
  Phase 4c friction point #5 already flagged the `_PALETTE`
  duplication; carried forward here per the Phase 4e brief.
* **Panel co-located with compute.** The brief explicitly asked for
  the panel to live in `uvvis_normalise.py` rather than inline in
  `uvvis_tab.py` (which is where the baseline panel lives). The
  panel subscribes directly to graph events so the host does not
  need to fan refresh calls into the subwidget.
* **Phase 4a friction point #2 resolved.** The legacy
  `_norm_mode` Tk var, top-bar `Norm:` combobox, and draw-time
  `_y_with_norm` transform are gone. Normalisation is now an
  explicit operation with reproducible parameters in
  `OperationNode.params`.

---

## CS-17: Single-node export

**Files:** `provenance_export.py` (pure header builder) +
`node_export.py` (file writer) + `scan_tree_widget.py` row gesture
+ host tab dialog flow
**Depends on:** CS-01 (`ProjectGraph.provenance_chain`), CS-02
(`DataNode.arrays` keys), CS-03 (`OperationNode.params` /
`engine` / `engine_version`), CS-04 (row context-menu),
CS-15 (BASELINE export shape), CS-16 (NORMALISED export shape)
**Depended on by:** UV/Vis tab (Phase 4f); Phase 5 / 6 will
extend the writer to XANES / EXAFS shapes.

### Responsibility

Save a single committed `DataNode` to a user-chosen `.csv` or
`.txt` file with a complete `# `-prefixed provenance header. The
header lets a future re-import path (or a human reader) reconstruct
exactly which operations produced the data. Multi-node export is
out of scope for Phase 4f.

### Two formats: `.csv` and `.txt`

Format dispatch is keyed off the path extension. Both formats
write the same provenance header lines (each prefixed `# `, no
trailing newline) followed by a column-header row and the data
block. CSV uses `,` as the data delimiter; TXT uses `\t`. The
column-header row carries the same array names for both formats
(`wavelength_nm,absorbance` for UV/Vis-shaped nodes).

### Provenance header

The header is built by
`provenance_export.build_provenance_header(graph, node_id)`. It
returns a list of `# `-prefixed strings, no newlines. The shape:

```
# ptarmigan_version=<version>
# exported_at=<ISO 8601 UTC>
# node_id=<full hex>
# node_label=<label>
# ancestor[0] type=<NodeType.name> id=<short_hex> label=<label>
# ancestor[1] op=<OperationType.name> engine=<engine> engine_version=<version> params=<json>
# ancestor[2] type=<NodeType.name> id=<short_hex> label=<label>
...
```

* DataNode lines carry `type=<NodeType.name>`, `id=<short_hex>`
  (first 8 characters of the uuid4 hex), and `label=<label>`.
* OperationNode lines carry `op=<OperationType.name>`, `engine`,
  `engine_version`, and a single-line JSON-serialised
  `params=<json>` payload. `params` is dumped with `sort_keys=True`
  so two exports of the same operation diff cleanly; `default=str`
  protects against numpy scalars or anything else that slipped past
  CS-03's "must be JSON-serialisable" rule.
* Ancestors are emitted in the topological order returned by
  `graph.provenance_chain(node_id)`: root first, requested node
  last. The leaf (the requested node) appears as the highest-index
  ancestor.

The envelope (top four lines) is identical across CSV and TXT and
across two exports of the same node modulo `exported_at`. The
ancestor lines are also identical between CSV and TXT, so two
exports of the same node can be diffed for header equivalence by
stripping the `exported_at` line.

### Exportable node types (Phase 4f scope)

| `NodeType` | Exported columns |
|---|---|
| `UVVIS` / `BASELINE` / `NORMALISED` | `wavelength_nm`, `absorbance` |

Other node types raise `ValueError` from `node_export.export_node_to_file`. Phase 5 (XANES) and Phase 6 (EXAFS) widen the table.

### Provisional nodes are not exportable

The right-click `Export…` menu entry on `ScanTreeWidget` is
disabled when the row's node is `PROVISIONAL`. This forces the
commit-or-discard discipline: a derivative cannot leak into a
file before it is locked into the scientific record. The widget
gates the gesture; `node_export.export_node_to_file` itself does
not check state, so a future programmatic caller (e.g. a batch
export) could in principle export a provisional node — but no
such caller exists today.

### Row gesture + host hand-off

The widget exposes the gesture via a new `export_cb=None`
constructor kwarg (CS-04). When the user invokes the menu entry,
the widget calls `export_cb(node_id)` and stops there — it has no
file-system knowledge. The host (a tab) wires `export_cb` to a
method that:

1. opens `tkinter.filedialog.asksaveasfilename` filtered to `.csv`
   / `.txt`, defaulting `initialfile` to the node label sanitised
   for the filesystem;
2. delegates to `node_export.export_node_to_file(graph, node_id,
   path)` on a non-empty return;
3. on success, nudges the tab's status bar; on `ValueError` /
   `KeyError` / `OSError`, surfaces via `messagebox.showerror`.

The UV/Vis tab is the first host (`UVVisTab._on_export_node`).

### Implementation notes (Phase 4f)

* **Header builder is pure.** `provenance_export.py` has no Tk,
  matplotlib, or file-system imports. Test coverage in
  `test_provenance_export.py` does not need a Tk display.
* **File writer is pure.** `node_export.py` writes via the
  standard library only; tests use `tempfile.mkdtemp` against a
  real `ProjectGraph` and inspect the written files.
* **Format dispatch is case-insensitive on the extension.** A path
  ending in `.CSV` is treated identically to `.csv`. Anything else
  raises `ValueError` rather than silently picking a default —
  protects against typos like `.cvs`.
* **Numeric values use `repr(float(...))`.** Floats round-trip
  losslessly via Python's `repr` on every supported version, where
  `str(float)` historically truncated. The wavelength / absorbance
  arrays are cast to `float` first so numpy dtypes do not leak
  into the file.
* **Default basename = sanitised label.** Filesystem-hostile
  characters (`<>:"/\|?*` plus runs of whitespace) collapse to
  underscores; the trimmed result falls back to `"export"` if the
  label is all-bad.
* **Forward-compat with CS-13.** The provenance header shape is
  what a future `.ptproj/` serialiser will need anyway. Phase 4f
  is the first place this shape is exercised against real graphs.

---

## CS-18: UV/Vis Smoothing

**File:** `uvvis_smoothing.py` (pure module + `SmoothingPanel`
co-located) + `uvvis_tab.py` left panel
**Depends on:** CS-01 (ProjectGraph), CS-02 (DataNode `SMOOTHED`
variant), CS-03 (OperationNode `SMOOTH` variant), CS-07 (UV/Vis
left panel), `numpy`, `scipy.signal.savgol_filter`
**Depended on by:** UV/Vis tab — third user-initiated processing
operation in the new architecture (Phase 4g); fourth
spectrum-producing operation (counting LOAD as the zeroth)

### Responsibility

Smooth a UV/Vis spectrum, producing a new `SMOOTHED` `DataNode`.
Each Apply gesture is a single provisional operation; the user
inspects the result and decides to commit (lock in) or discard
via the right-sidebar `ScanTreeWidget`.

### Two modes (single OperationType, params discriminated by mode)

A single `OperationType.SMOOTH` covers both. The discriminator is
`params["mode"]`; the remaining keys are the mode-specific
sub-schema. Mirrors the CS-15 (BASELINE) / CS-16 (NORMALISE)
convention.

| Mode | Required `params` keys | Algorithm |
|---|---|---|
| `savgol`     | `window_length` (odd int, > `polyorder`, ≤ len(absorbance)), `polyorder` (int ≥ 0) | `scipy.signal.savgol_filter`. The default starting parameters in the panel are `window_length=5`, `polyorder=2` (canonical UV/Vis Savitzky-Golay). |
| `moving_avg` | `window_length` (int ≥ 1, ≤ len(absorbance))                                       | Reflect-padded uniform moving average. `window_length == 1` is the identity (returns a copy). Odd `window_length` keeps the kernel centred at every sample; the panel's spinbox steps in 2s to encourage that. |

There is no `none` mode — the absence of smoothing is the absence
of a SMOOTHED node, not a no-op operation. The dispatcher rejects
`"none"` (and any other unknown mode) with `ValueError`.

### Pure module

The compute layer is Tk-free and graph-free:

```python
import uvvis_smoothing as us
smoothed = us.compute(
    "savgol", wavelength_nm, absorbance,
    {"window_length": 11, "polyorder": 2},
)
```

Each `compute_*` returns the smoothed absorbance as a numpy array
of the same shape as `absorbance`. Missing required params raise
`KeyError`; bad inputs (shape mismatch, even window length, polyorder
≥ window length, window length > signal length) raise `ValueError`.
The panel catches both and reports them via `messagebox`.

### Provisional / Commit / Discard flow

Per ARCHITECTURE.md §5. One Apply gesture creates exactly two nodes
wired `parent → op → child`:

* **`OperationNode`** (`type=SMOOTH`,
  `engine="internal"`, `engine_version=PTARMIGAN_VERSION`,
  `params={"mode": ..., **mode_specific}`,
  `state=PROVISIONAL`).
* **`DataNode`** (`type=SMOOTHED`,
  arrays `{wavelength_nm: parent_wl, absorbance: smoothed}`,
  metadata carried forward from the parent plus
  `smoothing_mode` + `smoothing_parent_id`,
  `state=PROVISIONAL`, default style picked from the loader's
  palette so the new curve is visually distinct).

The UV/Vis tab subscribes to graph events as before; the
`ScanTreeWidget` filter expanded from `[NodeType.UVVIS,
NodeType.BASELINE, NodeType.NORMALISED]` to `[NodeType.UVVIS,
NodeType.BASELINE, NodeType.NORMALISED, NodeType.SMOOTHED]` so
the new node appears in the right sidebar with the provisional
indicator. Commit (`graph.commit_node`) and discard
(`graph.discard_node`) flow through the existing `ScanTreeWidget`
gestures.

`_redraw` iterates `self._spectrum_nodes()` (UVVIS + BASELINE +
NORMALISED + SMOOTHED) and renders all four via the same
matplotlib code path — they share the `arrays["wavelength_nm"]` +
`arrays["absorbance"]` convention, so no rendering branch is
needed.

### Left-panel UI (CS-07 §"UV/Vis left panel" + Phase 4g)

`SmoothingPanel` is a `tk.Frame` subclass that lives below the
normalisation section in the left panel, separated by a horizontal
`ttk.Separator`. The panel hosts:

* **Subject combobox** — chooses which UVVIS / BASELINE /
  NORMALISED / SMOOTHED node to smooth. Chained smoothing is
  allowed (a SMOOTHED node is itself a candidate subject).
  Re-populated on graph events that change the live set
  (`NODE_ADDED`, `NODE_DISCARDED`, `NODE_LABEL_CHANGED`,
  `NODE_ACTIVE_CHANGED`).
* **Mode combobox** — `savgol` / `moving_avg`. On change the
  parameter row frame rebuilds.
* **Per-mode parameter rows** —
  * savgol: window-length spinbox (odd, default 5) + polyorder
    spinbox (default 2).
  * moving_avg: window-length spinbox (odd, default 5).
* **`Apply Smoothing` button** — runs `_apply()`.

Anchor capture from the plot is not relevant for smoothing
(the operation is global, not window-bounded). Live preview is
out of scope per CS-15 / CS-16 — each Apply produces a fresh
provisional node, and iteration is via discard + re-apply.

### Implementation notes (Phase 4g)

* **Single `OperationType.SMOOTH` decision.** Resolved in favour
  of one variant + a `mode`-discriminated params dict rather than
  separate `SMOOTH_SAVGOL` / `SMOOTH_MOVING_AVG` variants. Mirrors
  the CS-15 / CS-16 precedent so all three user-initiated UV/Vis
  operations share the same shape.
* **Subject is selected, not implicit.** The panel hosts its own
  combobox of every live spectrum-shaped node, fed by a callable
  the host hands over (`spectrum_nodes_fn`). Adding a row-selection
  state to `ScanTreeWidget` was deferred (Phase 4c friction
  point #1; carried forward through Phase 4e and 4g).
* **SMOOTHED renders identically to UVVIS / BASELINE / NORMALISED.**
  All four share the array-key convention. The sidebar filter and
  `_spectrum_nodes` walk were widened rather than building a
  parallel rendering branch.
* **Default colour picked from the same palette.** A SMOOTHED
  node's default colour is `_PALETTE[(n_uvvis + n_baseline +
  n_normalised + n_smoothed) % len(_PALETTE)]` so a parent and its
  derivatives are visually distinct without requiring the user to
  pick a colour. Phase 4c friction point #5 / Phase 4e friction
  point #2 already flagged the index-expression duplication;
  carried forward per the Phase 4g brief.
* **Default-style extraction (`node_styles.default_spectrum_style`).**
  Phase 4d friction point #3 / Phase 4e friction point #1 set the
  four-caller threshold for extracting the spectrum-producing
  default-style dict. Phase 4g lands that extraction as a sibling
  commit: `uvvis_tab._default_uvvis_style`,
  `uvvis_normalise._default_normalised_style`, and the new
  `uvvis_smoothing` SMOOTHED-node creation all import
  `default_spectrum_style` from `node_styles.py`. The widget /
  dialog UI fallbacks (`scan_tree_widget._DEFAULT_STYLE`,
  `style_dialog._UNIVERSAL_DEFAULTS`) are intentionally kept
  adjacent to the widgets that read them — their role is "fallback
  when `node.style` is missing a key" rather than "factory dict
  for fresh node creation".
* **Reflect-padded edges in moving_avg.** A boxcar convolution
  with zero padding pulls edge samples toward zero; reflect mode
  preserves the local mean, so a constant signal comes out
  exactly constant (pinned in the unit tests). The Savitzky-Golay
  filter handles edges via scipy's default `mode="interp"` — also
  edge-aware, also exact on polynomials of order ≤ `polyorder`.

---

## CS-19: UV/Vis Peak Picking

**File:** `uvvis_peak_picking.py` (pure module + `PeakPickingPanel`
co-located) + `uvvis_tab.py` left panel + render path
**Depends on:** CS-01 (ProjectGraph), CS-02 (DataNode `PEAK_LIST`
variant), CS-03 (OperationNode `PEAK_PICK` variant), CS-07 (UV/Vis
left panel), `numpy`, `scipy.signal.find_peaks`
**Depended on by:** UV/Vis tab — fourth user-initiated processing
operation in the new architecture (Phase 4h); first
non-spectrum-producing operation (the output is an annotation, not
a curve)

### Responsibility

Pick peaks of a UV/Vis spectrum, producing a new `PEAK_LIST`
`DataNode`. Each Apply gesture is a single provisional operation;
the user inspects the result (rendered as scatter markers on top of
the parent curve) and decides to commit or discard via the
right-sidebar `ScanTreeWidget`.

### Two modes (single OperationType, params discriminated by mode)

A single `OperationType.PEAK_PICK` covers both. The discriminator is
`params["mode"]`; the remaining keys are the mode-specific
sub-schema. Mirrors the CS-15 (BASELINE) / CS-16 (NORMALISE) /
CS-18 (SMOOTH) convention.

| Mode | Required `params` keys | Algorithm |
|---|---|---|
| `prominence` | `prominence` (float ≥ 0.0); optional `distance` (int ≥ 1, samples; default 1) | `scipy.signal.find_peaks` with the prominence threshold + minimum sample-spacing. Wavelength array is sorted ascending before the search; output is sorted ascending. Empty result on no-peaks-above-threshold is not an error. |
| `manual`     | `wavelengths_nm` (list[float], length ≥ 1) | User-supplied wavelengths snapped to the parent's nearest sample; duplicates collapse so the output is deduplicated and sorted ascending. No prominence is computed for hand-picked peaks (the `peak_prominences` array is omitted from the output node). |

There is no `none` mode — the absence of peak picking is the
absence of a PEAK_LIST node, not a no-op operation. The dispatcher
rejects `"none"` (and any other unknown mode) with `ValueError`.

### Pure module

The compute layer is Tk-free and graph-free:

```python
import uvvis_peak_picking as pp
peak_wl, peak_a, peak_prom = pp.compute(
    "prominence", wavelength_nm, absorbance,
    {"prominence": 0.05, "distance": 5},
)
```

Each `compute_*` returns three numpy arrays of equal length:
`peak_wavelengths_nm`, `peak_absorbances`, `peak_prominences`. The
prominence array is empty (length 0) for manual mode. Missing
required params raise `KeyError`; bad inputs (shape mismatch,
non-1-D arrays, empty arrays, negative prominence, zero distance,
non-finite manual wavelengths) raise `ValueError`. The panel catches
both and reports them via `messagebox`.

### Provisional / Commit / Discard flow

Per ARCHITECTURE.md §5. One Apply gesture creates exactly two nodes
wired `parent → op → child`:

* **`OperationNode`** (`type=PEAK_PICK`,
  `engine="internal"`, `engine_version=PTARMIGAN_VERSION`,
  `params={"mode": ..., **mode_specific}`,
  `state=PROVISIONAL`).
* **`DataNode`** (`type=PEAK_LIST`,
  arrays `{peak_wavelengths_nm, peak_absorbances,
  peak_prominences (prominence mode only)}`,
  metadata carried forward from the parent plus
  `peak_picking_mode` + `peak_picking_parent_id` + `peak_count`,
  `state=PROVISIONAL`, default style picked from the loader's
  palette so the markers are distinct from the parent curve).

The UV/Vis tab subscribes to graph events as before; the
`ScanTreeWidget` filter expanded from `[NodeType.UVVIS,
NodeType.BASELINE, NodeType.NORMALISED, NodeType.SMOOTHED]` to
include `NodeType.PEAK_LIST` so the new node appears in the right
sidebar with the provisional indicator. Commit (`graph.commit_node`)
and discard (`graph.discard_node`) flow through the existing
`ScanTreeWidget` gestures.

### Render path — scatter, not line

PEAK_LIST nodes render as a scatter overlay (`ax.scatter`,
`marker="v"`, `s=40`, `edgecolor="none"`, `zorder=3`) on top of the
curves drawn by `_redraw`'s spectrum loop. Empty peak lists (zero
samples — typically the result of a too-strict prominence threshold)
skip rendering without error.

The renderer reads only the universal style keys that have a
scatter analogue: `color`, `alpha`, `visible`, `in_legend`. The
remaining universal keys (`linestyle`, `linewidth`, `fill`,
`fill_alpha`) are stored on the node for schema uniformity but
ignored by the scatter draw.

### Why PEAK_LIST is *not* in `_spectrum_nodes`

`UVVisTab._spectrum_nodes` returns the curve-shaped nodes that
baseline / normalisation / smoothing accept as parents and that
`_redraw` plots as lines. PEAK_LIST nodes carry different array
keys (`peak_wavelengths_nm` / `peak_absorbances` instead of the
curve `wavelength_nm` / `absorbance`), are not candidate parents
for further peak picking (chained peak picking is undefined), and
render through a separate scatter path. They live in
`_peak_list_nodes()` instead and are walked separately by
`_redraw`.

### Left-panel UI (CS-07 §"UV/Vis left panel" + Phase 4h)

`PeakPickingPanel` is a `tk.Frame` subclass that lives below the
smoothing section in the left panel, separated by a horizontal
`ttk.Separator`. The panel hosts:

* **Subject combobox** — chooses which UVVIS / BASELINE /
  NORMALISED / SMOOTHED node to peak-pick. PEAK_LIST nodes are
  *not* themselves candidate subjects. Re-populated on graph events
  that change the live set (`NODE_ADDED`, `NODE_DISCARDED`,
  `NODE_LABEL_CHANGED`, `NODE_ACTIVE_CHANGED`).
* **Mode combobox** — `prominence` / `manual`. On change the
  parameter row frame rebuilds.
* **Per-mode parameter rows** —
  * prominence: `Prominence` entry (float, default 0.05) +
    `Min distance` spinbox (samples, default 1).
  * manual: `Wavelengths (nm, comma-separated)` text entry.
* **`Apply Peak Picking` button** — runs `_apply()`.

Click-on-plot to add a peak (the live-pointer gesture) is out of
scope for Phase 4h — manual mode accepts a comma-separated list of
wavelengths instead. A future polish session can add the gesture
without changing the OperationNode schema (the persisted params
are still a list of wavelengths).

### Implementation notes (Phase 4h)

* **PEAK_LIST is the first non-curve DataNode in the UV/Vis path.**
  CS-15 / CS-16 / CS-18 all produced new spectra (`BASELINE`,
  `NORMALISED`, `SMOOTHED`) that share the curve array convention
  and ride the same `_spectrum_nodes` walk + `_redraw` line loop.
  PEAK_LIST broke that uniformity: a separate `_peak_list_nodes()`
  helper + a separate render branch land in `uvvis_tab.py`. The
  alternative (annotation-only metadata stored on the parent's
  OperationNode without a downstream DataNode) was rejected because
  the established four-operation pattern (op + data) makes the
  scatter act like a first-class graph citizen — it has its own
  row in the sidebar, its own commit / discard gestures, its own
  style controls.
* **Single `OperationType.PEAK_PICK` decision.** Resolved in favour
  of one variant + a `mode`-discriminated params dict rather than
  separate `PEAK_PICK_PROMINENCE` / `PEAK_PICK_MANUAL` variants.
  Mirrors the CS-15 / CS-16 / CS-18 precedent.
* **Subject is selected, not implicit.** The panel hosts its own
  combobox of every live spectrum-shaped node, fed by a callable
  the host hands over (`spectrum_nodes_fn`). Adding a row-selection
  state to `ScanTreeWidget` was deferred (Phase 4c friction
  point #1; carried forward through Phase 4e / 4g and now 4h).
* **Default colour picked from the same palette.** A PEAK_LIST
  node's default colour is `_PALETTE[(n_uvvis + n_baseline +
  n_normalised + n_smoothed + n_peak_list) % len(_PALETTE)]` so
  the scatter is visually distinct from the parent curve. Phase 4g
  friction point #1 already flagged the duplicated index expression
  + duplicated `_PALETTE`; Phase 4h adds the fifth copy and the
  fifth term per the brief, with extraction deferred until a
  `_pick_default_color(graph)` helper is worth the indirection.
* **Reuses `node_styles.default_spectrum_style`.** The eight
  universal style keys cover the four scatter-relevant keys (color,
  alpha, visible, in_legend) plus four ignored-by-scatter keys
  (linestyle, linewidth, fill, fill_alpha). Carrying the four
  ignored keys on the node keeps the universal style dialog (CS-05)
  working without a per-node-type schema branch — the renderer
  reads what it can use and ignores the rest. A bespoke
  `default_peak_marker_style` was considered and deferred: the
  payoff (a `marker_size` / `marker_shape` schema) is real but
  needs a parallel column in the style dialog and a
  per-node-type style schema, which is bigger than peak-picking
  itself.
* **Marker is fixed at "v" pointing down at each peak.** A future
  marker-style schema decision could expose this to the user.
* **Empty peak list is a successful result, not an error.** A
  high-prominence Apply that filters every peak still creates the
  op + data nodes (`peak_count = 0` in the metadata footer) so the
  user can see that the operation ran. The renderer skips the
  scatter call when `peak_wavelengths_nm.size == 0`.
* **Manual mode snaps to the parent's wavelength grid.** This means
  the user's request "wavelengths_nm: [349.7]" persists in the
  OperationNode params verbatim, but the node arrays carry the
  snapped value (e.g. 349.5 if that is the nearest sample). The
  snapped wavelength is what gets rendered and what the future
  per-row export will write. The persisted params are sufficient
  to re-run the operation on the same parent (CS-03 params
  completeness): re-applying yields the same snapped sample.

---

## CS-20: UV/Vis Second Derivative

**File:** `uvvis_second_derivative.py` (pure module +
`SecondDerivativePanel` co-located) + `uvvis_tab.py` left panel +
render path
**Depends on:** CS-01 (ProjectGraph), CS-02 (DataNode
`SECOND_DERIVATIVE` variant), CS-03 (OperationNode
`SECOND_DERIVATIVE` variant), CS-07 (UV/Vis left panel), `numpy`,
`scipy.signal.savgol_filter`
**Depended on by:** UV/Vis tab — fifth user-initiated processing
operation in the new architecture (Phase 4i); second curve-shaped
derived node whose units are not absorbance (the `wavelength_nm` /
`absorbance` schema is reused, but the latter array holds d²A/dλ²
values measured in A/nm²)

### Responsibility

Compute the second derivative of a UV/Vis spectrum, producing a new
`SECOND_DERIVATIVE` `DataNode`. Each Apply gesture is a single
provisional operation; the user inspects the result (rendered as a
curve overlay on the same plot) and decides to commit or discard
via the right-sidebar `ScanTreeWidget`. The d² of an absorption
band has a sharp negative trough at each band centre and shoulders
at each inflection point — the standard analytical-chemistry
gesture for resolving overlapping bands.

### Single algorithm — no mode discriminator

Unlike CS-15 (BASELINE) / CS-16 (NORMALISE) / CS-18 (SMOOTH) /
CS-19 (PEAK_PICK), `OperationType.SECOND_DERIVATIVE` carries a
single algorithm and no `mode` discriminator in `params`. The
algorithm is `scipy.signal.savgol_filter` with `deriv=2`. A naive
`np.gradient(np.gradient(absorbance))` alternative was considered
and rejected: the second-difference of a noisy signal amplifies
noise without bound, so a "naive" mode would be a footgun rather
than a useful alternative. The Savitzky-Golay derivative smooths
and differentiates in one polynomial-fit pass, which is the de
facto standard in spectroscopy (Owen 1995, Agilent App. Note
"Derivative spectroscopy").

| Required `params` keys | Constraints |
|---|---|
| `window_length` | odd int, ``> polyorder``, ``≤ len(absorbance)`` |
| `polyorder`     | int ``≥ 2`` (second derivative is undefined for lower orders) |

The polyorder lower bound is the key difference from CS-18: a
second derivative needs at least a quadratic local fit, so
polyorder ``< 2`` is rejected at compute time.

### Pure module

The compute layer is Tk-free and graph-free:

```python
import uvvis_second_derivative as usd
d2 = usd.compute(
    wavelength_nm, absorbance,
    {"window_length": 11, "polyorder": 3},
)
```

`compute` returns a single numpy array of the same shape as the
input. The output is scaled by the mean wavelength spacing so the
units are A/nm² (physical) rather than A/sample² (which would
change with the parent's sampling density). Missing required
params raise `KeyError`; bad inputs (shape mismatch, non-1-D
arrays, single-sample input, even `window_length`,
`polyorder < 2`, `polyorder >= window_length`, oversize
`window_length`) raise `ValueError`. The panel catches both and
reports them via `messagebox`.

### Provisional / Commit / Discard flow

Per ARCHITECTURE.md §5. One Apply gesture creates exactly two
nodes wired `parent → op → child`:

* **`OperationNode`** (`type=SECOND_DERIVATIVE`,
  `engine="internal"`, `engine_version=PTARMIGAN_VERSION`,
  `params={"window_length": ..., "polyorder": ...}`,
  `state=PROVISIONAL`).
* **`DataNode`** (`type=SECOND_DERIVATIVE`,
  arrays `{wavelength_nm, absorbance}` (the latter holds d²A/dλ²
  values), metadata carried forward from the parent plus
  `second_derivative_parent_id` (no `_mode` key — single
  algorithm), `state=PROVISIONAL`, default style picked from the
  loader's palette so the curve is distinct from the parent).

The UV/Vis tab subscribes to graph events as before; the
`ScanTreeWidget` filter expanded from `[NodeType.UVVIS,
NodeType.BASELINE, NodeType.NORMALISED, NodeType.SMOOTHED,
NodeType.PEAK_LIST]` to include `NodeType.SECOND_DERIVATIVE` so
the new node appears in the right sidebar with the provisional
indicator. Commit (`graph.commit_node`) and discard
(`graph.discard_node`) flow through the existing `ScanTreeWidget`
gestures.

### Render path — line, on the shared Y-axis

`SECOND_DERIVATIVE` nodes render as `ax.plot` lines through the
same code path as `_redraw`'s spectrum loop — the schema reuse
(`wavelength_nm` + `absorbance`) means the loop treats them as
just another curve. The only change in `_redraw` is widening the
`live` source list with the result of `_second_derivative_nodes()`.

The renderer reads the full eight universal style keys from
`default_spectrum_style` (color, linestyle, linewidth, alpha,
visible, in_legend, fill, fill_alpha) — every key is meaningful
for a curve, unlike CS-19 where the four scatter-irrelevant keys
were ignored. nm-axis autoscaling and user-supplied x-limits also
pick up the derivative's wavelength range automatically because
the same `live` list drives both.

The Y-axis is shared with the absorbance curves: derivatives and
absorbance plot on the same axis even though their units differ
(A/nm² vs dimensionless A). This matches the standard
analytical-chemistry convention (overlay the d² on the spectrum to
read off where the troughs sit relative to the absorption band)
rather than introducing a secondary Y-axis. A user who wants the
derivative on its own axis can hide the parent curve via the
sidebar visibility toggle.

### Why SECOND_DERIVATIVE is *not* in `_spectrum_nodes`

`UVVisTab._spectrum_nodes` returns the curve-shaped nodes that
baseline / normalisation / smoothing / peak-picking accept as
parents. SECOND_DERIVATIVE is intentionally absent from that walk
because the locked panels (Phase 4c / 4e / 4g / 4h) reject any
node whose type is outside `{UVVIS, BASELINE, NORMALISED,
SMOOTHED}` — adding it to `_spectrum_nodes` would surface
candidates those panels would silently refuse on Apply.
SECOND_DERIVATIVE lives in `_second_derivative_nodes()` instead
and is walked separately by `_redraw` (alongside, not part of, the
curve loop). Chained second derivatives (the derivative of a
derivative) are out of scope this phase as a result.

A future polish session can widen each of `SmoothingPanel._apply`,
`PeakPickingPanel._apply`, `NormalisationPanel._apply`, and the
`uvvis_tab._apply_baseline` parent-type tuple to accept
`NodeType.SECOND_DERIVATIVE`, then promote `_spectrum_nodes` to
include it. Tracked in BACKLOG Phase 4i friction #3.

### Left-panel UI (CS-07 §"UV/Vis left panel" + Phase 4i)

`SecondDerivativePanel` is a `tk.Frame` subclass that lives below
the peak-picking section in the left panel, separated by a
horizontal `ttk.Separator`. The panel hosts:

* **Subject combobox** — chooses which UVVIS / BASELINE /
  NORMALISED / SMOOTHED node to differentiate. SECOND_DERIVATIVE
  itself is *not* a candidate subject (chained derivatives out of
  scope; see above). Re-populated on graph events that change the
  live set (`NODE_ADDED`, `NODE_DISCARDED`, `NODE_LABEL_CHANGED`,
  `NODE_ACTIVE_CHANGED`).
* **Window length spinbox** — odd integers from 5 upward, default
  11. Lower bound 5 (not 3 as in smoothing) because polyorder
  must be ``≥ 2`` and savgol requires `window_length > polyorder`.
* **Poly order spinbox** — integers from 2 upward, default 3.
  Defaults are wider than CS-18 because the second derivative is
  more noise-sensitive than the spectrum itself.
* **`Apply Second Derivative` button** — runs `_apply()`.

No mode combobox and no per-mode parameter rows (single algorithm
— see above), so the panel is structurally simpler than the four
earlier user-operation panels.

### Implementation notes (Phase 4i)

* **Single algorithm vs mode-discriminated decision.** Resolved in
  favour of a single algorithm with no `mode` key in params. The
  Savitzky-Golay derivative is the established convention; the
  naive `np.gradient` alternative was rejected as a footgun
  (noise amplification). Mode-discriminator extension would be
  added if a wavelet-based derivative or a Tikhonov-regularised
  derivative ever lands.
* **NodeType.SECOND_DERIVATIVE vs SMOOTHED-with-metadata
  decision.** Resolved in favour of a new NodeType variant.
  Reusing SMOOTHED with a `derivative_order` metadata flag would
  have collided with the smoothing-as-curve-cleanup interpretation
  (the d² of a spectrum is a different scientific object) and
  would have surfaced derivatives in `_spectrum_nodes` as if they
  were smoothing outputs, breaking the parent-type checks in the
  locked panels.
* **Mean-spacing scaling for non-uniform grids.** `compute()`
  divides by `np.mean(np.abs(np.diff(wl)))` to give the caller
  physical units (A/nm² rather than A/sample²). For the typical
  UV/Vis grid (uniform within < 0.1%) this is exact; for an
  upstream resampling that produces a non-uniform grid the
  scaling is approximate. Tracked in BACKLOG Phase 4i friction
  #4. A more rigorous alternative would re-interpolate the parent
  to a uniform grid before differentiating; deferred until a user
  loads a non-uniform spectrum.
* **Default colour picked from the same palette.** A
  SECOND_DERIVATIVE node's default colour is `_PALETTE[(n_uvvis +
  n_baseline + n_normalised + n_smoothed + n_second_deriv) %
  len(_PALETTE)]` so the derivative curve is visually distinct
  from the parent. Phase 4g / 4h friction already flagged the
  duplicated index expression + duplicated `_PALETTE`; Phase 4i
  adds the sixth copy. The `_pick_default_color(graph)` extraction
  would now touch four locked modules — deferred for a polish
  session that bundles it with the left-pane density redesign
  (BACKLOG Phase 4i friction #1 + #2).
* **Reuses `node_styles.default_spectrum_style`.** All eight
  universal style keys are meaningful for a curve, so the
  scatter-vs-line distinction that surfaced in CS-19 does not
  apply — the renderer reads every key the dialog can write.

---

## CS-21: Collapsible left-pane sections + shared palette helper

**Files:** `collapsible_section.py`, `node_styles.py` (extended)
**Depends on:** CS-01 (`ProjectGraph.nodes_of_type`), CS-02 (`NodeType`),
CS-07 (UV/Vis left panel layout)
**Depended on by:** CS-15 (`uvvis_tab._apply_baseline` + `_load_uvvis_scan`),
CS-16 (`NormalisationPanel._apply`), CS-18 (`SmoothingPanel._apply`),
CS-19 (`PeakPickingPanel._apply`), CS-20 (`SecondDerivativePanel._apply`)

### Responsibility

Two small reusable pieces extracted in Phase 4j to absorb two
long-running duplications that the prior phases (4c, 4e, 4g, 4h, 4i)
flagged but couldn't resolve without touching multiple locked
modules in one phase:

* **`pick_default_color(graph) -> str`** — single source of truth
  for "next default colour" picking. Walks every spectrum-shaped
  NodeType in one go and indexes into the shared palette.
* **`CollapsibleSection(parent, title, *, expanded=False)`** —
  reusable show/hide wrapper widget for an arbitrary block of
  Tk widgets. Header is a clickable strip with `▶ Title`
  (collapsed) / `▼ Title` (expanded); body is a `tk.Frame` exposed
  via the `body` property.

### `node_styles.SPECTRUM_PALETTE` + `pick_default_color`

`SPECTRUM_PALETTE` is a 10-entry tuple of hex colour strings (the
matplotlib default Set1-ish palette: `#1f77b4`, `#d62728`, …
`#17becf`). Pre-4j this literal was duplicated in six modules
(`uvvis_tab` plus the four operation modules
`uvvis_normalise` / `uvvis_smoothing` / `uvvis_peak_picking` /
`uvvis_second_derivative`); CS-21 lifts it into `node_styles` and
replaces every copy with an import.

`SPECTRUM_PALETTE_NODE_TYPES` is the tuple of NodeTypes whose
existence consumes a palette slot:

```
SPECTRUM_PALETTE_NODE_TYPES = (
    NodeType.UVVIS,
    NodeType.BASELINE,
    NodeType.NORMALISED,
    NodeType.SMOOTHED,
    NodeType.SECOND_DERIVATIVE,
    NodeType.PEAK_LIST,
)
```

`pick_default_color(graph)` sums `len(graph.nodes_of_type(t,
state=None))` over every type in `SPECTRUM_PALETTE_NODE_TYPES` and
returns `SPECTRUM_PALETTE[total % len(SPECTRUM_PALETTE)]`. State
is intentionally `None` (count provisional + committed +
discarded) so colours stay sticky across an undo/redo round trip
and across project save/load.

Behaviour change vs pre-4j: peak_picking and second_derivative now
see each other's nodes in the counter (pre-4j they each rolled
their own palette-index expression that was mutually palette-
invisible). Locked at the Phase 4j brief as the "order-independent"
unified rule. xas_analysis_tab and exafs_analysis_tab keep their
own local `_PALETTE` literals — Phase 0 / pre-redesign code, out
of scope.

### `CollapsibleSection`

```
collapsible_section.py
  CollapsibleSection(parent, title, *, expanded=False,
                     body_padx=0, body_pady=0)
    .body              # tk.Frame — caller's content goes here
    .title             # str
    .is_expanded() -> bool
    .expand()
    .collapse()
    .toggle()
```

* **Header strip** is a single full-width `tk.Label` with bold
  font, `cursor="hand2"`, and a `<Button-1>` binding that calls
  `toggle()`. Click anywhere on the strip toggles — no double-click
  required, no separate expand button.
* **Chevron glyph** sits at the start of the header text:
  `▶ Title` when collapsed, `▼ Title` when expanded.
* **Body** is a `tk.Frame`. When collapsed the body is
  `pack_forget()`-en off the section; when expanded it is
  re-`pack`-ed with `after=self._header` so siblings packed after
  the section keep their position. Children of the body stay
  packed inside it across collapse → expand cycles, so layout is
  preserved exactly.
* **State storage** — internal `tk.BooleanVar`. Not persisted to
  project files this phase (Phase 8 concern by design).

### Test coverage

* `test_node_styles.py` (new, 16 tests) — `SPECTRUM_PALETTE`
  shape, `SPECTRUM_PALETTE_NODE_TYPES` order, empty graph,
  single-type counts, palette-length wrap, six-NodeType walk,
  PEAK_LIST + SECOND_DERIVATIVE inclusion, state independence,
  order independence across NodeType mixes.
* `test_collapsible_section.py` (new, 13 tests) — default-collapsed
  state, `expanded=True` at construction, expand / collapse /
  toggle / is_expanded, idempotent expand-while-expanded, chevron
  glyph swap, `.body` returns a `tk.Frame`, `<Button-1>` binding
  registered, handler-direct toggle, body children survive a
  collapse → expand round trip.
* `test_uvvis_tab.TestCollapsibleLeftPaneSections` (new, 11
  integration tests) — five `tab._{name}_section` attributes
  exist, every section starts collapsed, collapsed bodies are
  not packed, each operation panel lives inside its host
  section's body, baseline section's inline widgets pack into
  the section body, expand / collapse cycle on sections, header
  click handler reachable through the tab.

### Migration sites

Every spectrum-creating call site in the UV/Vis path now reads
the helper:

| Site | Pre-4j | Post-4j |
|---|---|---|
| `uvvis_tab._load_uvvis_scan` | `_PALETTE[n_uvvis % len(_PALETTE)]` | `pick_default_color(self._graph)` |
| `uvvis_tab._apply_baseline` | `_PALETTE[(n_uvvis + n_baseline) % len(_PALETTE)]` | `pick_default_color(self._graph)` |
| `NormalisationPanel._apply` | three-term sum into local `_PALETTE` | `pick_default_color(self._graph)` |
| `SmoothingPanel._apply` | four-term sum into local `_PALETTE` | `pick_default_color(self._graph)` |
| `PeakPickingPanel._apply` | five-term sum into local `_PALETTE` | `pick_default_color(self._graph)` |
| `SecondDerivativePanel._apply` | five-term sum (no PEAK_LIST) into local `_PALETTE` | `pick_default_color(self._graph)` |

### `_build_left_panel` integration

`uvvis_tab._build_left_panel` now constructs five `CollapsibleSection`
instances stored on the tab as
`self._baseline_section` / `self._normalisation_section` /
`self._smoothing_section` / `self._peak_picking_section` /
`self._second_derivative_section`. Each is created with
`expanded=False` (locked default state at end of Phase 4i). The
Baseline section's inline widgets (subject combobox, mode combobox,
parameter rows, Apply button) pack into `self._baseline_section.body`;
the four operation panels (`NormalisationPanel`, `SmoothingPanel`,
`PeakPickingPanel`, `SecondDerivativePanel`) are constructed with
`section.body` as parent. The four `ttk.Separator` strips between
sections are gone — each section's bold-font header is the
divider.

### Defence-in-depth fix (commit 6)

`scan_tree_widget._begin_label_edit` previously constructed
`tk.StringVar(value=current)` with no explicit `master`. That
fell back to `tkinter._default_root`, which is mutable: a fifth
`tk.Tk()`-using test module loaded before `test_scan_tree_widget`
shifted it and silently broke the rename Entry's textvariable
binding (Entry rendered empty). Phase 4j passes `master=row_frame`
explicitly. Same risk would have surfaced for any future plugin
tab / workspace window that spawns its own Tk root, so this is a
forward-defence fix as well as a test-stability fix.

---

## CS-22: Shared subject combobox + per-panel set_subject contract

**Files:** `uvvis_tab.py` (extended), `uvvis_normalise.py` (extended),
`uvvis_smoothing.py` (extended), `uvvis_peak_picking.py` (extended),
`uvvis_second_derivative.py` (extended)
**Depends on:** CS-01 (`ProjectGraph.subscribe`), CS-02 (`NodeType`),
CS-07 (UV/Vis left panel layout), CS-15 / CS-16 / CS-18 / CS-19 / CS-20
(the four operation panels' `_apply` shape), CS-21 (`CollapsibleSection`
— the shared combobox sits *above* every section)
**Depended on by:** future Phase 4 register entries that touch the
left pane (Commit / discard reachable from the left pane after Apply,
Per-variant gestures on sweep-group rows, Plot Settings dialog Save
& Close)

### Responsibility

Lift the per-panel "Spectrum:" combobox out of the four operation
panels and the inline baseline section, replacing them with one
shared combobox at the top of the left pane (always visible, above
every CollapsibleSection). USER-FLAGGED at end of Phase 4j: each of
the five operation panels owning its own subject combobox felt
redundant — picking the spectrum once and then expanding the
section for whichever operation the user wants is the correct
shape.

CS-22 is purely a UI / integration refactor. No new pure module,
no new NodeType, no new OperationType, no new arrays schema. The
four pure-compute layers under `uvvis_*.py` are untouched.

### `UVVisTab` — shared subject plumbing

```
self._shared_subject       : tk.StringVar           # display text
self._shared_subject_map   : dict[str, str]         # display → node id
self._shared_subject_cb    : ttk.Combobox           # the widget
```

The combobox is packed directly into the left-pane parent frame
(NOT inside any `CollapsibleSection`), between the "Processing"
header label and the Baseline section.

```
self._baseline_subject_id  : Optional[str]                       # resolved id
self._BASELINE_ACCEPTED_PARENT_TYPES = (NodeType.UVVIS, NodeType.BASELINE)
```

Inline baseline section's parent-type tuple is held on the tab
because the inline section has no panel class to attach a
`ACCEPTED_PARENT_TYPES` constant to. Naming-inconsistency carry-
forward documented in the Phase 4k friction list.

### Hand-off contract — `set_subject(node_id)`

Each of the four operation panels now exposes:

```
class <Panel>(tk.Frame):
    ACCEPTED_PARENT_TYPES: tuple[NodeType, ...]   # class constant
    def set_subject(self, node_id: Optional[str]) -> None: ...
```

`set_subject` stores the id internally as `self._subject_id` and
re-evaluates the Apply button state via `_refresh_apply_state`:
the button is enabled iff `node_id is not None` AND the resolved
node's type is in `ACCEPTED_PARENT_TYPES`. The `_apply()` body
resolves the parent via `self._subject_id` rather than reading
from a combobox.

`ACCEPTED_PARENT_TYPES` per panel — locked, do not widen without
coming back to this section:

| Panel | Accepted parent types |
|---|---|
| `NormalisationPanel` | UVVIS, BASELINE, NORMALISED |
| `SmoothingPanel` | UVVIS, BASELINE, NORMALISED, SMOOTHED |
| `PeakPickingPanel` | UVVIS, BASELINE, NORMALISED, SMOOTHED |
| `SecondDerivativePanel` | UVVIS, BASELINE, NORMALISED, SMOOTHED |
| (inline baseline on tab) | UVVIS, BASELINE |

The shared combobox lists the *union* of acceptable parents
(`_spectrum_nodes` walks UVVIS / BASELINE / NORMALISED / SMOOTHED).
PEAK_LIST and SECOND_DERIVATIVE remain excluded from the list —
chained derivatives / chained peak picks stay out of scope.

### Fan-out — `_on_shared_subject_changed`

A `trace_add("write", ...)` on `_shared_subject` calls
`_on_shared_subject_changed`, which:

1. Resolves the display text → node id via `_shared_subject_map`.
2. Stores it on the tab as `_baseline_subject_id`.
3. Calls `set_subject(node_id)` on each of the four panels.
4. Calls `_refresh_baseline_apply_state` (mirrors the panels'
   `_refresh_apply_state` shape, but on the tab because the
   inline baseline section has no panel class).

Every Apply button on the left pane therefore re-evaluates its
gate exactly once per shared-subject change.

### Repopulation — `_refresh_shared_subjects`

Driven by `_on_graph_event` on every `NODE_ADDED` / `DISCARDED` /
`ACTIVE_CHANGED` / `LABEL_CHANGED` / `GRAPH_LOADED` /
`GRAPH_CLEARED`. Walks `_spectrum_nodes`, rebuilds
`_shared_subject_map`, and either preserves the user's selection
(if its display text still exists) or auto-falls-back to the
first available item. The trace fans the change out either way,
so panel gates always reflect the current selection.

### Defence-in-depth at Apply time

The messagebox-bearing checks in each `_apply()` are retained
even though the gate normally prevents Apply from being clicked:

```
subject_id = self._subject_id
if not subject_id:
    messagebox.showinfo(...)
    return None
try:
    parent_node = self._graph.get_node(subject_id)
except KeyError:
    messagebox.showerror(...)
    return None
if parent_node.type not in self.ACCEPTED_PARENT_TYPES:
    messagebox.showerror(...)
    return None
```

These survive the refactor because (a) a programmatic invocation
(test code, future plugin) can call `_apply()` directly without
going through the gate, and (b) graph events that fire between
`set_subject` and the user's click could in principle invalidate
the subject; the defensive check turns an exception into a
user-readable messagebox.

### Test coverage

* `test_uvvis_normalise.py`, `test_uvvis_smoothing.py`,
  `test_uvvis_peak_picking.py`, `test_uvvis_second_derivative.py`
  — six new panel-level tests each: `test_apply_disabled_when_no_subject`,
  `test_set_subject_with_uvvis_enables_apply`,
  `test_set_subject_none_disables_apply`,
  `test_set_subject_unknown_id_disables_apply`,
  `test_set_subject_<unaccepted>_disables_apply` (panel-specific
  example), `test_accepted_parent_types_constant` (guards against
  silent widening). Existing apply-path tests reworked to use
  `set_subject` instead of poking the dropped `_subject_var` /
  `_subject_cb`.
* `test_uvvis_tab.TestUVVisTabSharedSubject` (new, 11 tests) —
  end-to-end: combobox empty / auto-select / SMOOTHED appears /
  PEAK_LIST and SECOND_DERIVATIVE excluded, hide-selected falls
  back, label-edit preserves resolved id, UVVIS enables every
  panel's Apply, SMOOTHED disables normalise + baseline only,
  empty graph disables every Apply, four panels share one
  combobox widget (no `_subject_cb` attribute).
* `test_uvvis_tab.test_left_panel_exists` — extended to assert
  `_shared_subject_cb` and `_shared_subject` are present and
  `_baseline_subject_cb` is *absent*.
* `test_uvvis_tab.test_shared_subject_combobox_lives_outside_collapsible_sections`
  + `test_baseline_section_body_has_no_subject_combobox` — pin
  the structural invariant: the shared combobox is OUTSIDE every
  CollapsibleSection body, and the baseline section body holds
  exactly one Combobox descendant (the mode combobox).

### Migration sites

| Site | Pre-4k | Post-4k |
|---|---|---|
| `NormalisationPanel.__init__` | `(parent, graph, spectrum_nodes_fn=...)` + inline subject combobox | `(parent, graph, status_cb=None)` — no subject widget |
| `SmoothingPanel.__init__` | same shape | same change |
| `PeakPickingPanel.__init__` | same shape | same change |
| `SecondDerivativePanel.__init__` | same shape | same change |
| `uvvis_tab._build_left_panel` | inline `_baseline_subject_cb` + per-panel subject combos | one `_shared_subject_cb` at top of pane |
| `uvvis_tab._refresh_baseline_subjects` | refreshed inline baseline combobox | renamed to `_refresh_shared_subjects`, drives the shared widget |
| `uvvis_tab._apply_baseline` | resolved via `_baseline_subject_map[_baseline_subject.get()]` | resolved via `self._baseline_subject_id` |

The four panels' `_subject_var` / `_subject_map` / `_subject_cb`
ivars + `refresh_subjects` public API + per-panel
`self._graph.subscribe(self._on_graph_event)` + `<Destroy>`
unsubscribe are all gone.

### Unresolved (deferred to subsequent Phase 4 sessions)

Five Phase 4k friction items above are not addressed by CS-22:

* **Three USER-FLAGGED carry-forwards** — each has its own register
  entry: Commit / discard reachable from the left pane after Apply,
  Per-variant gestures on sweep-group rows (elevated from Phase 2
  carry-forward), Plot Settings dialog Save & Close.
* **Auto-fall-back uses graph-insertion order.** When the selected
  subject vanishes, fall-back is `items[0]` — first UVVIS in the
  graph's insertion order. "Previous in list" / "freshly-added"
  policies may feel less surprising; lock-worthy debate.
* **Apply-disabled state has no inline explanation.** The
  per-panel gate disables the button silently; a small inline
  caption inside each panel explaining "Selected node is not a
  valid parent for this op" would teach the user the per-op
  acceptance set.
* **`_baseline_subject_id` lives on the tab; `_subject_id` lives on
  each panel.** Resolved when the inline baseline section is
  extracted into a `BaselinePanel` widget — at that point
  `_BASELINE_ACCEPTED_PARENT_TYPES` should join the public
  `ACCEPTED_PARENT_TYPES` API the four operation panels already
  expose.

---

## CS-04 implementation notes (Phase 4c)

* **B-001 fix — inline history expansion.** `_render_history`
  now packs the sub-frame with `after=row` so the provenance
  chain renders directly below the clicked row. Toggling history
  on a different row collapses any previously expanded pane —
  one history pane open at a time across the widget.
* **B-004 fix — Rename context-menu entry routing.** The Rename
  menu entry was present since Phase 2 but `_begin_label_edit`
  raised `TclError` because it passed `before=label_widget` to
  `entry.pack` after `label_widget.pack_forget()`. Fixed by
  packing the Entry with `side="left"`/`expand=True` only — the
  row's left/right pack split guarantees the Entry fills the
  vacated slot. Both rename gestures (double-click and the
  Rename menu entry) share `_begin_label_edit` per the original
  spec.

## CS-04 implementation notes (Phase 4f)

* **Export… row context-menu entry.** A new entry sits between
  ``Rename`` and ``Show history`` in the right-click menu (CS-04
  §"Context menu"). Enabled only when the row is committed *and*
  the host wired ``export_cb``; provisional rows render the entry
  disabled (not absent), mirroring the Discard convention so the
  user can see the affordance and learn the commit-or-discard
  rule. Invocation calls ``export_cb(node_id)`` — the widget never
  imports ``filedialog`` or ``node_export``; the host owns the
  dialog flow (CS-17).
* **New constructor kwarg ``export_cb``.** Optional callable
  ``(node_id: str) -> None``; defaults to ``None``. Tabs that wish
  to support export pass a bound method; the widget checks for
  ``None`` before enabling the menu entry.

## CS-04 implementation notes (Phase 4d)

* **B-002 fix — responsive row collapse.** `_apply_responsive_layout`
  hides the optional row controls (swatch, legend toggle, linestyle
  canvas, history button) when the row's `winfo_width()` is below
  `_RESPONSIVE_COLLAPSE_PX` (currently 280 px). The minimum
  always-visible set (state, `[☑]` visibility, label, `[⚙]` gear,
  `[✕]`) survives every width. `<Configure>` on each row frame
  drives the helper.
* **Per-row optional widgets dict.** `_optional_row_widgets[node_id]`
  maps `"swatch" / "leg" / "ls_canvas" / "hist"` to the widgets
  the responsive helper hides, plus `"vis_cb"` as the swatch's
  re-pack anchor (needed because `pack(side="left")` without
  `before=vis_cb` would land the swatch after the label, which
  has `fill="x", expand=True` and consumes the remaining left
  space).
* **Restore order matches the original build order** for the
  right-side widgets (`hist` → `ls_canvas` → `leg`) so each new
  `side="right"` pack lands to the left of the previously packed
  right-side controls — preserving the visual sequence
  `leg ls_canvas hist gear x`.
* **Optional-widgets dict cleared on rebuild and on row repopulate**
  so a NODE_STYLE_CHANGED → `_refresh_row` cycle does not leak
  stale widget references into the responsive layout.
* **Tests stub `winfo_width`** to force a deterministic row width;
  they do not depend on the host's real geometry. Tests also call
  `update_idletasks()` between layout calls because
  `winfo_ismapped()` reflects the result of Tk's geometry pass,
  not the most recent `pack` / `pack_forget`. Phase 4n note: this
  guidance is incomplete — see CS-04 implementation notes (Phase
  4n, CS-26) for the `_root.update()` requirement on a withdrawn
  root.

## CS-25 — Duplicate panel-title deletion (Phase 4n, task C)

**Files:** `uvvis_normalise.py`, `uvvis_smoothing.py`,
`uvvis_peak_picking.py`, `uvvis_second_derivative.py`
**Depends on:** CS-21 (`CollapsibleSection`)

The four `CollapsibleSection`-wrapped operation panels each
rendered a stale `tk.Label(self, text="<Title>", …)` directly
below the chevron header — a visual duplicate of the title that
the chevron-header (CS-21) already shows. The label was a
leftover from before CS-21 wrapped each panel's body; the
chevron-header's title made it redundant.

CS-25 is a pure deletion: the inline `tk.Label` line is removed
from each of the four panel modules. Baseline Correction was
unaffected (the inline section in `uvvis_tab.py` never had its
own title label). Each panel test file gains a
`test_no_inline_title_label_inside_panel_body` regression
assertion that walks the panel's widget tree recursively and
fails if any `tk.Label` carries the section title text — future
refactors that re-introduce the duplicate (or move it inside a
sub-frame) will trip the guard.

## CS-04 implementation notes (Phase 4n, CS-26 — graduated reveal)

Phase 4d's B-002 closed the responsive collapse with a single
280 px threshold over four optional cells (swatch, legend
toggle, linestyle canvas, history button). Phase 4n CS-26 makes
two coupled changes:

* **`hist` (⌥n provenance count) is promoted out of the optional
  set into the always-visible minimum.** The new minimum is
  seven cells: `state · [☑] · label · ⌥n · [⚙] · [→] · [✕]`.
  (`[→]` is added by CS-27 in the same phase.) The old optional
  set shrinks to three cells: swatch, leg, ls\_canvas. `hist`
  is no longer present in `_optional_row_widgets[node_id]` —
  the dict is the responsive-helper's working set, not a
  generic "all widgets in the row" registry.

* **Single 280 px threshold replaced by three priority-ordered
  thresholds** in `_RESPONSIVE_THRESHOLDS_PX`:

  | Priority | Cell        | Threshold |
  |----------|-------------|-----------|
  | 1        | `swatch`    | 240 px    |
  | 2        | `leg`       | 280 px    |
  | 3        | `ls_canvas` | 320 px    |

  Below 240 px no optional cells are shown; the always-visible
  minimum keeps the row usable. As the row widens past each
  threshold, the corresponding cell maps. The smallest threshold
  (240 px) is exposed as `_RESPONSIVE_COLLAPSE_PX` for callers /
  tests that want a single "is the row narrow?" sentinel.

The fourth-priority "line width entry" cell from the Phase 4l
USER-FLAGGED brief is deferred (no per-row line-width control
exists today; the universal section of `StyleDialog` (CS-05)
is the canonical reach point).

**Helper invariants under Tk overflow.** `_apply_responsive_layout`
unconditionally `pack_forget`s + repacks every optional cell on
every call rather than tracking last-applied state. The reason
is subtle: Tk auto-unmaps a packed widget that doesn't fit in a
narrow parent — leaving it in the pack list at its old position
even though `winfo_ismapped()` returns False. A `winfo_ismapped`-
based "have" check would intermittently disagree with the pack
list (visible in tests where the host frame is at its default
1 px size before geometry runs), and a guarded `pack_forget`
would skip the call. The subsequent `pack(side="right")` would
be a no-op (widget already in the list at its old position),
breaking the canonical visual order `leg ls_canvas hist gear →
x`. The unconditional reflow pays a few pack-list updates per
Configure event but is correct under every overflow regime.

The right-side optional cells are reflowed **together**: when
the desired set of `(want_leg, want_ls)` differs from the
actual set, both widgets are `pack_forget`ed and then re-packed
in the order `ls_canvas → leg`. Each `side="right"` pack lands
to the left of the previously packed widget, so this order
yields the visual `leg | ls_canvas | hist | …`. Re-packing only
one (when the other is already mapped) would break the order
because `pack` on a widget that is already in the pack list
just updates options at its existing position rather than
moving it.

The threshold-band caching optimisation (skip the reflow when
the new width falls in the same band as the previous call) is
deferred — see Phase 4n friction #4 / "Threshold-band caching
for responsive helper".

**Test convention update.** `update_idletasks()` flushes idle
handlers but does NOT trigger Tk's geometry pass on a withdrawn
root; `winfo_ismapped()` lags reality until the next event
cycle. The pre-CS-26 helper packed less aggressively and the
tests got away with `update_idletasks` alone. CS-26 tests use
`_root.update()` after layout-changing operations, plus a host
frame pinned to 800 × 400 with `pack_propagate(False)` and the
widget packed `fill="both", expand=True`. Otherwise the host's
natural width is 1 px, Tk auto-unmaps overflowed widgets, and
`winfo_ismapped` reports False even for widgets that ARE in the
pack list — masquerading as a helper bug. The convention is
captured as Phase 4n friction #2 (test convention) for any
future widget tests that read mapped state.

## CS-04 implementation notes (Phase 4n, CS-27 — per-row → Send-to-Compare)

The legacy "+ Add to TDDFT Overlay" top-bar bulk button is
retired. Each `ScanTreeWidget` row now carries a `→` button
between `[⚙]` and `[✕]`, in the always-visible minimum (CS-26).

* **Disabled-state convention** mirrors Export… (CS-17): the
  button is rendered in `state="disabled"` when no
  `send_to_compare_cb` is wired (deferred-tab convention) OR
  when the row's node is not `COMMITTED`. The button is always
  *present* (the affordance is visible) so users can see the
  available gesture and learn the commit-or-discard discipline.

* **Defensive re-check on click.** The button's disabled state
  is set at row build time. A row's state can change between
  build and click without a row rebuild firing (rare today but
  possible if a future feature mutates state without invalidating
  the rendered row). The handler `_on_send_to_compare_clicked`
  re-validates `node.state == NodeState.COMMITTED` and the
  callback's existence before invoking the callback. Stale ids
  (row destroyed between build and click) are swallowed via the
  `KeyError` branch.

* **UVVisTab integration.** The tab wires
  `send_to_compare_cb=self._send_node_to_compare` in
  `_build_sidebar`. `_send_node_to_compare(node_id)` is a
  single-node refactor of the old `_add_selected_to_overlay`
  bulk method — same energy-conversion path
  (`wavelength_nm` → eV via `_HC_NM_EV / wl`) and same
  `ExperimentalScan` shape, but reads one node by id instead of
  walking `_uvvis_nodes()` and filtering by `style.visible`.
  The "no Compare host connected" messagebox is preserved; it
  fires when `_add_scan_fn is None`, matching the legacy
  button's gate.

* **Status-bar message** changes from the legacy
  `"Added N spectra to TDDFT overlay."` to
  `"Sent <label> to TDDFT overlay."` — single-node semantics
  surface in the user-visible feedback.

* **Right-click context-menu "Send to Compare"** entry remains
  in place as the canonical fallback. It hands off to the same
  `send_to_compare_cb` so per-row icon and menu entry agree on
  the destination.

CS-27 keeps the routing layer unchanged: the widget never
imports the Compare tab and never knows about
`ExperimentalScan` — `send_to_compare_cb` is a host-supplied
function that takes a `node_id` and converts it however the
destination tab needs. When Phase 7 lands the actual Compare
tab, only `UVVisTab._send_node_to_compare` and the host glue
(`binah.py`) change; the widget side stays put.

---

## CS-28 — `_redraw` defensive guard for malformed DataNodes (Phase 4o)

`uvvis_tab._redraw` walks every `DataNode` returned by
`_spectrum_nodes()` and `_second_derivative_nodes()` and reads
the canonical `arrays["wavelength_nm"]` / `["absorbance"]`
pair for each one. Every NodeType in those filter lists
(`UVVIS`, `BASELINE`, `NORMALISED`, `SMOOTHED`, `SECOND_DERIVATIVE`)
is *meant* to carry that pair, but a malformed entry (test
scaffolding, partial project file, future NodeType added to the
filter without renderer support) used to raise
`KeyError` from inside the Tk graph-event handler — the trace
escaped to stderr but the user saw nothing.

CS-28 adds a positive guard at the top of the per-node loop body:

```python
for node in live:
    if ("wavelength_nm" not in node.arrays
            or "absorbance" not in node.arrays):
        continue
    ...
```

The same guard is mirrored on the `unit == "nm"` axis-limit
comprehension so a half-formed `live` list cannot blow up the
`min(...)` / `max(...)` either:

```python
if unit == "nm":
    wl_nodes = [n for n in live if "wavelength_nm" in n.arrays]
    if wl_nodes:
        lo_nm = min(float(np.min(n.arrays["wavelength_nm"]))
                    for n in wl_nodes)
        ...
```

The skip is silent — there is no log line, no messagebox, no
status-bar entry. The diagnostic-console register entry (still
⏳ as of Phase 4o) is the natural surface for "renderer skipped
node X because of Y"; until that lands, `_redraw` simply ignores
the malformed entry and keeps drawing the rest of the live list.

Test class `TestUVVisTabRedrawGuard` in `test_uvvis_tab.py`
covers three cases: malformed BASELINE alone (was the original
crash path), malformed BASELINE alongside a valid UVVIS (the
valid spectrum still renders), and malformed BASELINE missing
`wavelength_nm` entirely (the xlim mirror keeps the axis-limit
computation alive). CS-28 also enabled simplifying
`test_send_node_to_compare_skips_non_uvvis_nodes`, which used to
stub `graph.get_node` with a one-off lambda specifically to keep
the malformed BASELINE out of `_redraw`'s path.

---

## CS-29 — Baseline-curve overlay (Phase 4o)

After the user applies a baseline (any mode in CS-15 / CS-24)
the resulting `BASELINE` `DataNode` shows the *corrected*
spectrum but the *fitted baseline curve itself* is not drawn.
Reviewing the fit quality before committing required toggling
the parent's visibility on/off and eyeballing the difference.

CS-29 adds an opt-in dashed overlay. New top-bar
`tk.Checkbutton` "Baseline curves" (immediately after the
existing `λ(nm) axis` button), wired to a new
`self._show_baseline_curves` Tk `BooleanVar` (default `False` —
opt-in so existing flows render unchanged). When on, `_redraw`
walks every visible `BASELINE` node and overlays its fitted
baseline as a dashed line in the BASELINE node's colour.

The pure helper that recovers the baseline lives in
`uvvis_baseline.py` next to the `compute_*` family:

```python
def compute_baseline_curve(graph, baseline_node):
    """Recover parent_absorbance - baseline_node.absorbance.

    Returns (wavelength_nm, baseline_curve) on success or None
    on every failure path (wrong type, missing arrays, no
    parent, shape mismatch). Never raises.
    """
```

Implementation walks one hop in the graph:

* `parents_of(baseline_node.id)` → expects exactly one
  `OperationNode` (the `BASELINE` op that produced this node)
* `op.input_ids[0]` → the parent `DataNode` (typically `UVVIS`,
  but `BASELINE` works too — chained corrections are a valid
  shape)
* baseline curve = `parent.arrays["absorbance"] - baseline_node.arrays["absorbance"]`

Every failure mode returns `None` rather than raising, so the
caller's render loop simply skips and continues — a malformed
graph cannot crash the renderer through this branch.

In `_redraw`, the overlay loop is placed after the main spectrum
loop and before the PEAK_LIST scatter loop, so the dashed line
sits visually on top of its parent curve while peaks remain
topmost. Style attributes:

| Attribute  | Value                              |
|---|---|
| `linestyle` | `"--"` (always dashed)            |
| `color`     | inherited from BASELINE node      |
| `linewidth` | inherited from BASELINE node      |
| `alpha`     | hard-coded 0.7 (deliberate; a faded BASELINE shouldn't make the overlay invisible) |
| `label`     | `f"{node.label} (baseline)"` if `style["in_legend"]` is true, else `None` |

The overlay respects the BASELINE node's own visibility — a
hidden BASELINE node has no overlay.

Test classes:

* `TestComputeBaselineCurve` (in `test_uvvis_baseline.py`,
  six cases): success path; chained baseline parent;
  non-BASELINE input; missing arrays; orphan node (no graph
  parent); parent / child shape mismatch
* `TestUVVisTabBaselineCurveOverlay` (in `test_uvvis_tab.py`,
  six cases): default-off; toggle off renders no dashed line;
  toggle on adds exactly one dashed line whose y-data matches
  the fitted baseline; invisible BASELINE node has no overlay;
  overlay inherits the BASELINE node's colour; orphan BASELINE
  is skipped without crashing

CS-29's deliberate scope limit: the toggle is global. Per-node
gating, legend density mitigation, and a per-node
`style["show_baseline_curve"]` style key were all considered
during decision lock and deferred — the global toggle is the
minimum viable review aid; per-node control is registered as a
USER-FLAGGED Phase 4o follow-up. The CS-24 lock is preserved:
`compute_baseline_curve` is an additive helper alongside
`compute_*` and `_DISPATCH`; no existing mode signatures were
touched.

---

## CS-30 — Canvas-driven responsive layout (Phase 4p)

The Phase 4d / 4n responsive layout (B-002 + CS-26) had correct
threshold logic but was wired to the wrong width signal. Two
production failures motivated the rewrite:

- **Single-node sidebar stayed collapsed at any width.** With
  one row, the inner `_rows_frame`'s natural width was the
  label width (~150 px), well below every threshold, so
  `row.winfo_width()` returned that small number even at 800 px
  sidebar width. Optional cells (swatch, leg, ls_canvas) never
  appeared.
- **Narrowing the sidebar did not recollapse expanded rows.**
  The row's own width never changed because content didn't
  change, so the per-row `<Configure>` binding never re-fired.

CS-30 changes the helper's contract:

```python
def _apply_responsive_layout(
    self, node_id: str, row: tk.Frame,
    width: int | None = None,
) -> None:
    ...
```

When `width` is `None` (the default), the helper reads
`self._scroll_canvas.winfo_width()` rather than
`row.winfo_width()`. The canvas's width is the actual sidebar
width — independent of row content — so threshold decisions
now reflect available space instead of label length.

The reflow trigger also changes. The per-row `<Configure>`
binding is removed (it raced with explicit helper calls under
`update_idletasks` and read the wrong width). A new
canvas-`<Configure>` binding fires the helper for every row in
`_optional_row_widgets` whenever the sidebar resizes:

```python
def _on_canvas_configure(_event):
    for nid, frm in list(self._row_frames.items()):
        if nid in self._optional_row_widgets:
            self._apply_responsive_layout(nid, frm)
```

The handler does **not** pass `_event.width` — it lets the
helper read `_scroll_canvas.winfo_width()` itself. That matters
for tests: stubbing `canvas.winfo_width()` flows through both
the binding and direct calls, but stubbing has no effect on
`event.width` (which is Tk's actual reported size).

Initial calibration of newly-built rows happens at the end of
`_populate_node_row` with a single `_apply_responsive_layout(
node.id, row)` call. New rows added after the canvas is
realised collapse straight away if the canvas is below threshold;
new rows added before the canvas is realised get calibrated
when the canvas's first `<Configure>` event fires.

Inner `_rows_frame` width is **not** bound to canvas width.
Binding it via `itemconfig(_rows_window, width=event.width)`
was the first attempt and broke under Tk's auto-unmap rule —
narrow canvases caused Tk to silently unmap overflow widgets
in tests that had stubbed only the row's `winfo_width`. The
canvas-driven helper sidesteps that entirely: rows stay
content-driven for their natural width, the helper just
controls *which* widgets are packed.

A direct consequence: every row in the sidebar reflows
uniformly on a canvas resize. They share column structure
because they share the same width signal — confirming the user-
flagged invariant that "all rows must have the same column
widths."

Test mechanics. Tests that stubbed `row.winfo_width` via
`_force_width(row, N)` keep working because `_force_width`
also stubs the owning `_scroll_canvas.winfo_width`. The
existing helper-test patterns (force a width, call the helper,
assert pack state) continue without rewrite. Six new tests in
`TestScanTreeWidgetCanvasDrivenLayout` (in
`test_scan_tree_widget.py`) pin the new contract:

* default-width path reads canvas (`winfo_width` stubbed wide → all packed)
* default-width path collapses on narrow canvas
* explicit `width=` kwarg overrides canvas default
* canvas-`<Configure>` event walks every row in both directions
* initial calibration runs inside `_populate_node_row`
* no per-row `<Configure>` binding remains (regression guard
  against accidental restore)

Plus the Phase 4n `test_each_row_collapses_independently` test
was rewritten to drive each row's width via the explicit
`width=` kwarg — under the new contract rows share a canvas, so
"per-row independence" only survives when the caller drives it
directly. The architectural invariant (all rows reflow together
under a real resize) is the new default.

Locks held: `_RESPONSIVE_THRESHOLDS_PX` priority order is
unchanged (swatch 240 / leg 280 / ls_canvas 320); the always-
visible seven-cell minimum (state, ☑, label, ⌥n, ⚙, →, ✕) is
unchanged; the optional widgets dict layout in
`_optional_row_widgets` is unchanged. CS-26 + CS-27 invariants
are preserved.

---

## CS-31 — Suppress identical re-applies (Phase 4p)

> **⚠️ Reverted in Phase 4ac (CS-54).** This section documents the
> historical CS-31 contract; the implementation was removed in
> Phase 4ac after the user flagged its dedup gate as workflow-
> blocking. `ProjectGraph.find_provisional_op_with_params` no
> longer exists; every UV/Vis apply site now creates a fresh node
> on identical-param re-applies. See CS-54 below for the removal
> rationale + the carry-forward Phase 4ad intent (user-driven
> `NodeType.NODE_GROUP` container).

Architecturally, the right-side ScanTreeWidget collapses two or
more PROVISIONAL DataNode siblings sharing one parent into a
single sweep-group leader row (CS-04 §6.3). The
`_compute_sweep_groups` rule keys on `(parent_id, op_type,
state == PROVISIONAL)` — it does *not* check whether params
differ. Result: clicking Apply twice with identical parameters
produced two PROVISIONAL siblings, which collapsed into a
"sweep (2 variants)" row even though no parameter actually
swept. The user lost access to the just-created node behind a
bulk-discard `✕all` gesture.

Per `ARCHITECTURE.md` §5.4, a sweep is "an operation across a
parameter range." Identical params should not qualify. CS-31
adds a duplicate-apply detector and threads it through every
UV/Vis apply site so identical re-clicks become a no-op with a
status message.

The detector lives on `ProjectGraph` so it is a pure graph
query (no Tk dependency, easily testable in isolation):

```python
def find_provisional_op_with_params(
    self,
    parent_id: str,
    op_type: OperationType,
    params: dict,
) -> str | None:
    """Return the id of an existing PROVISIONAL OperationNode
    of the given type whose input is parent_id and whose params
    equal `params`. Returns None when no such op exists.
    """
```

Match contract:

| Attribute | Required value |
|---|---|
| `node.type` | `op_type` |
| `node.state` | `NodeState.PROVISIONAL` |
| `parent_id in node.input_ids` | `True` |
| `node.params == params` | `True` (full dict equality) |

Returns the first match in graph insertion order so callers
surface a deterministic id in status messages. Returns `None`
when no match — the apply path then proceeds normally.

Architecturally, this is the inverse of
`scan_tree_widget._compute_sweep_groups`: that helper *groups*
2+ PROVISIONAL siblings; CS-31 detects the case where the
proposed second sibling would be a *duplicate* of an existing
one, so the apply path can refuse before creating it.

Integrated at every UV/Vis apply site:

* `uvvis_tab._apply_baseline` (UVVisTab, ``OperationType.BASELINE``)
* `uvvis_normalise.NormalisationPanel._apply` (`OperationType.NORMALISE`)
* `uvvis_smoothing.SmoothingPanel._apply` (`OperationType.SMOOTH`)
* `uvvis_peak_picking.PeakPickingPanel._apply` (`OperationType.PEAK_PICK`)
* `uvvis_second_derivative.SecondDerivativePanel._apply`
  (`OperationType.SECOND_DERIVATIVE`)

The check fires after parameter validation and **before**
`compute()` runs — the dedup decision must not depend on the
(deterministic) numerical output. On hit:

* No graph mutation. The existing PROVISIONAL OperationNode
  stays.
* Status message: *"<op> (<mode>) with these parameters already
  applied to <parent label> — no new node created."* The four
  panels report via `self._status_cb`; the baseline path on
  UVVisTab reports via `self._status_lbl.config(text=...,
  fg="#7a4a00")`.
* Apply returns `None`.

Real parameter sweeps (different params on each click) still
flow into the sweep-grouping detector unchanged — that path is
exercised by the new "different params creates new node" tests
in each panel's test file, which assert that two calls with one
tweaked param create two distinct PROVISIONAL siblings.

Test classes:

* `TestFindProvisionalOpWithParams` (in `test_graph.py`, 10
  cases): match returns id; no match → None when no op exists,
  params differ, op is committed, op is discarded, op type
  differs, parent differs; first-match-wins ordering;
  dict-key-order-independent equality; list-param element-wise
  equality (covers PEAK_PICK manual mode)
* Five panel-side integration test pairs (suppress + different-
  params), one per apply site — `test_uvvis_tab.py`,
  `test_uvvis_normalise.py`, `test_uvvis_smoothing.py`,
  `test_uvvis_peak_picking.py`, `test_uvvis_second_derivative.py`

CS-31's deliberate scope limit: the gate is exact dict equality.
Floating-point parameters (anchor windows, prominence) are
compared with `==`, not tolerance — the panels populate params
from string-parsed Tk Entry values, so re-typing the same
number reproduces the same float bit-for-bit. A future
floating-point tolerance comparison would be a separable
extension; today's implementation matches user expectation
because the user is hitting Apply twice without changing any
field.

CS-32 (per-variant gestures on sweep-group rows) was scoped
into Phase 4p at decision lock but split out to Phase 4q after
CS-30 took longer than expected. The Phase 4 register entry
remains ⏳ as the obvious primary intent for the next phase.

---

## CS-32 — Sweep group inline expansion (Phase 4q)

> **⚠️ Reverted in Phase 4ac (CS-54).** This section documents the
> historical CS-32 contract; the implementation was removed in
> Phase 4ac alongside CS-31. The auto-grouping rule ("≥2
> PROVISIONAL siblings sharing one DataNode parent") collapsed
> nodes the user wanted to act on; CS-54 drops it entirely so
> identical re-applies render as standalone full-chrome rows.
> The replacement — user-driven `NodeType.NODE_GROUP` containers
> + a "Combine selected → Group" gesture — is the carry-forward
> Phase 4ad intent. CS-35's `_SWEEP_MEMBER_INDENT_PX` constant +
> `_build_node_row(indent_px=0)` kwarg signature survive Phase 4ac
> for Phase 4ad reuse.

CS-04 §6.3 sketched "Expanding shows all variants ranked by
fit metric" but the Phase 2 implementation only delivered the
collapsed leader row with a single `✕all` gesture. Two or more
PROVISIONAL DataNode siblings sharing one parent (a sweep
group) hid every per-variant action — commit, discard, restyle —
behind a "Show hidden" toggle plus right-click context menus
on individual variants, which in practice meant the user
could see the variants but not act on them. CS-31 (Phase 4p)
made this register entry actually useful by ensuring sweeps
only fire on real parameter differences; CS-32 makes them
editable.

CS-32 adds an inline-expansion model to the leader row:

```python
self._expanded_sweep_groups: set[str] = set()  # parent_id keys
```

The set parallels `_expanded_history` and persists across
every `_rebuild`. Membership in the set is the source of truth
for whether a group's members render inline.

The leader row's leading `⋯` Label is replaced with a chevron
`tk.Button`:

* `▸` when the parent_id is NOT in `_expanded_sweep_groups`
* `▾` when it IS

Click invokes `_toggle_sweep_group(parent_id)`, which flips
the parent_id's membership in the set and triggers a full
`_rebuild`. Routing through `_rebuild` rather than an in-place
edit keeps member-row construction in one place — the initial
render and every subsequent toggle take exactly the same path:

```python
self._build_sweep_row(group_key)
if group_key in self._expanded_sweep_groups:
    for member_id in self._sweep_groups.get(group_key, []):
        member_node = self._graph.get_node(member_id)
        if isinstance(member_node, DataNode):
            self._build_node_row(member_node)
```

Members iterate in the deterministic sorted order
`_compute_sweep_groups` already imposes. Each member routes
through `_build_node_row` → `_populate_node_row`, so it
inherits the full row chrome — state · swatch · ☑ · label ·
⌥n · ⚙ · → · 🔒 · ✕ — including CS-34's commit button. No
member-only branch exists in `_populate_node_row`; the
provisional-row 🔒 falls out of the `node.state ==
PROVISIONAL` check that's already there.

Group dissolution is automatic. `_compute_sweep_groups` only
returns groups with ≥2 visible PROVISIONAL members, so
committing or discarding a member down to 1 makes the
parent_id absent from `_sweep_groups` on the next rebuild.
The chevron + leader row + remaining inline members all
disappear — the surviving member renders as a normal
standalone row. Stale entries in `_expanded_sweep_groups` for
dissolved groups become harmless no-ops; no explicit cleanup
is required. The chevron only renders inside `_build_sweep_row`,
which only runs when the group exists.

Test mechanics. The chevron is found by walking
`_rows_frame.winfo_children()` rather than indexing
`_row_frames[leader_id]`, because expansion overwrites
`_row_frames[leader_id]` with the member row of the same id
(the leader id is, by definition, also a member id).
`_row_frames[leader_id]` resolves to the leader row when
collapsed and to the member row when expanded — the only
caller that actually reads it (`_refresh_row`) handles both
cases by falling back to `_rebuild` whenever the id is part
of a sweep group.

Six new tests in `TestSweepGroupInlineExpansion`
(`test_scan_tree_widget.py`):

* collapsed leader row renders `▸`; only leader id keyed in `_row_frames`
* `chevron.invoke()` flips to `▾`, populates `_expanded_sweep_groups`, both members keyed
* second toggle collapses cleanly
* expansion state survives a manual `_rebuild()`
* each expanded member row carries exactly one 🔒 commit button (CS-34)
* committing one member dissolves the group (chevron + leader row gone)

Plus `TestExpandedSweepGroupsField` (1 test) pins the field
type and initial-empty-set contract.

Locks held: the leader row's `✕all` bulk-discard gesture is
unchanged; sweep grouping criteria (≥2 PROVISIONAL siblings
sharing one DataNode parent) are unchanged; lex-smallest id
remains the leader.

---

## CS-33 — Label truncation with hover tooltip (Phase 4q)

CS-30 (Phase 4p) made the responsive helper key on canvas
width rather than row natural width — so all rows uniformly
show the same column structure regardless of any individual
row's content (the user-flagged "all rows must share column
widths" invariant). But the row's *natural* width can still
exceed the canvas width when the label cell plus all packed
right-cluster widgets together don't fit, causing horizontal
overflow on long chained-op labels. UV/Vis chains accumulate
suffixes (`NiAqua · baseline (linear) · norm (peak)` is ~40
chars; three or four chained ops reach 60–80).

CS-33 adds a uniform character cap on the painted label text:

```python
_LABEL_MAX_CHARS: int = 32

def _truncate_label(text: str, max_chars: int = _LABEL_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1] + "…"
```

The helper is pure (no Tk dependency) so its tests run in any
environment. Returns text unchanged when short; otherwise
returns text cut at `max_chars - 1` characters with `…`
appended, so the displayed length is exactly `max_chars`.
Chosen over the alternative shapes (wrap to two lines, fixed-
width column with fade gradient, reserve minimum widths per
cell): truncation matches typical desktop conventions and
keeps every row at the same height.

`_populate_node_row` paints the truncated text and attaches a
`_Tooltip` only when truncation actually cut text:

```python
display_text = _truncate_label(node.label)
label = tk.Label(row, text=display_text, anchor="w")
if display_text != node.label:
    _Tooltip(label, node.label)
```

`_build_sweep_row` applies the same treatment to the parent
label inside the leader text (`{parent_label} · sweep (N
variants)`).

`_Tooltip` is a small Toplevel-based hover tooltip (600 ms
delay):

* `<Enter>` schedules `_show` via `widget.after`
* `<Leave>` and `<ButtonPress>` cancel any pending schedule and destroy the Toplevel
* `update_text(new_text)` rotates the text in place after a label rename without rebuilding the row
* TclError catches keep it cheap during widget-teardown races

The Toplevel uses `wm_overrideredirect(True)` for borderless
chrome and a pale-yellow `bg="#FFFFE0"` for the conventional
"hover hint" colour.

Rename source-of-truth fix. `_begin_label_edit` now reads the
canonical full label from the graph rather than the painted
(potentially truncated) widget text, so editing a truncated
row starts with the untruncated text:

```python
try:
    node = self._graph.get_node(node_id)
    current = (node.label
               if isinstance(node, DataNode)
               else label_widget.cget("text"))
except KeyError:
    current = label_widget.cget("text")
```

Falls back to the widget text only if the graph lookup raises
(defensive: stale id mid-click). Every existing rename test
continues to pass without change.

Test coverage. Five pure-helper tests in `TestTruncateLabel`
(`test_scan_tree_widget.py`): short text passthrough, exact-
cap passthrough, long-text truncation with ellipsis at the
exact target length, `max_chars` override, `_LABEL_MAX_CHARS`
type/sign. Three Tooltip tests in `TestTooltip` cover
construction, `update_text`, and idempotent `_hide` —
construction-only because the Toplevel-rendering path is
timing-dependent (600 ms `after`) and the test suite doesn't
drive the event loop, so verifying the tooltip surface itself
is left to manual smoke. Three widget-side tests in
`TestLabelTruncationInRow` cover short-label verbatim, long-
label truncation with the graph-side label intact, and the
rename-from-full-label invariant.

Follow-ups (BACKLOG entries 🟢): cap-from-canvas-width-and-
font-metrics (CS-33 follow-up), promote `_Tooltip` to shared
utility module on first cross-module re-use.

Locks held: `_LABEL_MAX_CHARS = 32` is a module-level
constant, not a parameter on the class — shared by every
caller in the module so all rows truncate uniformly.

---

## CS-34 — 🔒 commit gesture on provisional rows (Phase 4q)

Phase 4k friction #1 (USER-FLAGGED) flagged that the only
"accept this provisional node" path after Apply was the
right-click context menu on the right-side ScanTreeWidget
row. Each Apply makes a provisional node, and the user wants
confirm-as-they-go without traversing to the right sidebar
and right-clicking. The original register entry called for a
left-pane "Accept last / Discard last" button-pair. CS-34
addresses the right-sidebar half: every PROVISIONAL row now
carries a per-row 🔒 commit gesture as a single-click twin of
the existing ✕.

```python
if node.state == NodeState.PROVISIONAL:
    commit_btn = tk.Button(
        row, text="🔒", relief=tk.FLAT, cursor="hand2",
        command=lambda nid=node.id: self._safely(
            self._graph.commit_node, nid),
    )
    commit_btn.pack(side="right", padx=(2, 0))
```

Order in the right cluster (left→right): `[⌥n] [⚙] [→] [🔒]
[✕]` provisional, `[⌥n] [⚙] [→] [✕]` committed.

Decisions worth pinning:

* **Omitted entirely on committed rows**, not disabled. The
  leftmost-cell 🔒 state indicator already signals committed
  state; a disabled 🔒 button next to ✕ would put two 🔒
  glyphs on the same row, which is more confusing than the
  omission. The state column says "this row is committed";
  the right cluster says "what can you do next" — and on a
  committed row the answer no longer includes commit.

* **NOT in the responsive-optional set.** 🔒 is the commit
  twin of ✕ (also always-visible) and a commit gesture is
  too important to hide on narrow widths. The optional set
  in `_RESPONSIVE_THRESHOLDS_PX` (swatch / leg / ls_canvas)
  is unchanged.

* **`_safely` wrapper.** Routes through the same
  `try/except (KeyError, ValueError, TypeError)` shim the
  context-menu Commit entry uses, so the on-row gesture and
  the menu gesture stay behaviourally identical on stale or
  invalid ids.

Same widget appears on sweep-group MEMBER rows when expanded
via CS-32, since member rows route through
`_populate_node_row`. So once a sweep group is expanded,
committing a single variant is one click on its 🔒 button —
which makes the group dissolve naturally if it drops below
the 2-member threshold.

Three integration tests in `TestProvisionalRowCommitButton`
(`test_scan_tree_widget.py`):

* provisional row has the 🔒 button
* committed row OMITS the button (omitted, not disabled)
* `btn.invoke()` commits the node via `commit_node`; the
  button disappears on the post-commit re-render

The original Phase 4k friction #1 register entry "Commit /
discard reachable from the left pane after Apply (USER-
FLAGGED)" stays ⏳ at 🟡 (dropped from 🔴 because CS-34
satisfies the spirit of the original USER-FLAG — single-click
commit without the right-click context menu — and the left-
pane Accept-last button-pair becomes a convenience-layer
follow-up rather than a hard requirement).

Locks held: the right-click context menu's Commit entry is
unchanged; `_safely` is unchanged.

---

## CS-35 — Sweep group member visual nesting (Phase 4r)

CS-32 (Phase 4q) gave sweep groups inline expansion: clicking the
chevron on the leader row turns each member into a full-chrome
row rendered below. The members and the leader were packed at the
same left padding (`padx=2`), so visually the relationship between
the leader and its members read as "siblings" rather than "parent
and indented children". CS-35 adds one indent step on the member
rows so the grouping is visible at a glance.

Mechanic
--------

Module-level constant:

::

    _SWEEP_MEMBER_INDENT_PX: int = 16

`_build_node_row` grows an `indent_px: int = 0` keyword. Default 0
preserves every existing call site (every standalone-row caller
threads the default). The sweep-expansion branch in `_rebuild`
calls:

::

    self._build_node_row(member_node, indent_px=_SWEEP_MEMBER_INDENT_PX)

The row frame is packed via:

::

    row.pack(side="top", fill="x", padx=(2 + indent_px, 2), pady=1)

Tk normalises an equal-sided `padx=(2, 2)` to the scalar `2` when
read back via `pack_info()`, so the standalone case round-trips
identically; only indented rows show as a tuple.

Why a pack-arg pass-through (and not a wrapper frame)
-----------------------------------------------------

Considered alternative: wrap each expanded member row in an outer
`tk.Frame` packed with extra left padding, leaving the member row
itself unchanged. Rejected because:

* The member row's own internal layout (state · swatch · ☑ · ~ ·
  label · …) already has its own `padx` budget. Wrapping in a
  parent frame would have to manage the wrapper's lifecycle on
  collapse, doubling the dictionary tracking that
  `_row_frames[member_id]` does today.
* The pack-arg path is one literal change at one call site. The
  wrapper-frame path adds a `_member_frames` dict + collapse
  cleanup + tests for the cleanup. Wasted complexity for a 16 px
  visual hint.

CS-32 contract preserved
------------------------

CS-35 does not touch:

* `_expanded_sweep_groups: set[str]` field shape or initial-empty
  contract.
* `_toggle_sweep_group(parent_id)` flip-and-rebuild model.
* `_compute_sweep_groups`'s ≥2-member dissolution rule.
* The deterministic `sorted(...)` member iteration order.

CS-35's lock surface is `_SWEEP_MEMBER_INDENT_PX` itself, the
`indent_px` kwarg signature, and the call-site delivery of that
kwarg from `_rebuild`. Everything else is downstream.

Tests
-----

`TestSweepMemberIndentConstant` (pure, no Tk) — constant is a
positive int and its exact value is pinned to 16 so a future
restyle is a deliberate change.

`TestSweepGroupNestedIndent` (5 integration tests, Tk-required)
— standalone row uses `padx=2` (Tk's scalar-collapse form),
expanded member uses `padx=(2 + _SWEEP_MEMBER_INDENT_PX, 2)`,
left padding derives from the constant (not a literal), collapse
removes the indented member row, re-expand re-applies the indent.

---

## CS-36 — Per-node baseline-curve toggle (Phase 4r)

CS-29 (Phase 4o) added a global "Baseline curves" checkbox on the
top bar that, when on, rendered the dashed baseline overlay for
every visible BASELINE node. The user reported that with three or
more BASELINE nodes the plot crowded; the canonical fix was a
per-node opt-out so individual baselines can be hidden while the
global toggle stays on. CS-36 lands that as a per-row gesture on
ScanTreeWidget rows.

Mechanic
--------

New style key with a default-on convention: `style["show_baseline_curve"]`,
default `True`. The default-on convention parallels `visible` and
`in_legend` and means:

* Existing graphs (no key in the saved style) round-trip
  unchanged — every BASELINE node remains visible under the
  global toggle.
* New BASELINE nodes start visible; user opts out per node.

`uvvis_tab._redraw`'s CS-29 overlay loop adds one filter line:

::

    if self._show_baseline_curves.get():
        for bn in self._spectrum_nodes():
            if bn.type != NodeType.BASELINE:
                continue
            if not bool(bn.style.get("visible", True)):
                continue
            if not bool(bn.style.get("show_baseline_curve", True)):  # NEW
                continue
            pair = uvvis_baseline.compute_baseline_curve(...)
            ...

The global toggle stays as the master switch (CS-29 lock holds);
the per-node key is a downstream filter. Both must be on for an
overlay to render.

Per-row gesture
---------------

`_populate_node_row` adds a `tk.Button` between `[☑]` and the
label, packed `side="left", padx=(2, 0)`, **only when**
`node.type == NodeType.BASELINE`. Glyph vocabulary parallels the
legend toggle:

* `~` (foreground `#444444`) when on.
* `–` (foreground `#999999`) when off.

Click flips the style key via `self._graph.set_style(nid,
{"show_baseline_curve": new})`, which fires
`GraphEvent.NODE_STYLE_CHANGED` → uvvis_tab subscribes →
`_redraw` re-evaluates the per-node gate. Same wiring path the
visibility checkbox and legend toggle use.

Why BASELINE-only and not a placeholder on every row
----------------------------------------------------

Considered alternative: pack a disabled placeholder on UVVIS /
NORMALISED / SMOOTHED / PEAK_LIST rows so every row has the same
column structure. Rejected:

* No utility — these node types have no baseline curve to
  toggle. A disabled button is a noise pixel on every non-
  baseline row.
* The CS-26 lock specifies a seven-cell always-visible minimum.
  CS-36 conditionally adds an 8th cell on BASELINE rows; the
  seven-cell floor for non-baseline rows is preserved.

The per-row toggle is also NOT in the responsive-optional set
(`_optional_row_widgets`). It is always-visible on BASELINE rows
regardless of canvas width — the same convention that applies to
the chevron on sweep-group leader rows and the 🔒 commit button
on provisional rows.

Why the StyleDialog universal section is NOT touched
----------------------------------------------------

Phase 4r's decision lock weighed a parallel CS-36 path: surface
`style["show_baseline_curve"]` as a row in the StyleDialog
universal section. Deferred. Reasons:

* The universal section is a Phase 4d / 4f deliberate-lock
  surface (see "Do not touch ... StyleDialog universal section"
  in the lock list). Relaxation requires explicit user
  authorisation; the right-sidebar gesture covers the workflow
  the user described without needing it.
* The new per-row gesture is more discoverable: the user is
  already looking at the BASELINE row when deciding whether to
  hide its overlay; opening a modal for a single-checkbox toggle
  is friction.
* The style key remains accessible programmatically and via
  `set_style`, so a future dialog row is purely additive.

CS-29 contract preserved
------------------------

CS-29's two locked surfaces — `uvvis_tab._redraw`'s defensive guard
and `uvvis_baseline.compute_baseline_curve` — are untouched. The
global `_show_baseline_curves` Tk `BooleanVar` is unchanged. CS-36
is exclusively additive.

Tests
-----

`TestShowBaselineCurveStyleKeyDefault` (pure, no Tk) — locks the
default-True convention and `set_style`'s key-merge semantics so
sibling keys (visible / in_legend) are not silently clobbered when
the new key is toggled.

`TestPerNodeBaselineCurveToggle` (7 integration tests) — button
present on BASELINE rows, absent on UVVIS + NORMALISED rows,
default-on glyph (`~`), off glyph (`–`) when the key is
pre-populated False, click flips both the style key and the glyph
through the graph-event rebuild path, round-trip back to on.

---

## CS-37 — Floor-zero baseline as fit-time constraint (Phase 4s + Phase 4t)

The user's framing: corrected absorbance (`parent − B`) should be
≥ 0 across the entire range when the user explicitly asks for it.
Post-fit shifting only translates the baseline globally; the
*shape* is still optimised for unconstrained residual minimisation.
For scattering at high energies the unconstrained fit rises too
steeply and shifting it doesn't fix the shape mismatch — the
constraint must be enforced at *fit time*.

CS-37's roadmap shipped in two phases:

* **Phase 4s** — universal "Floor at zero" toggle plus the
  constrained-fit code path for scattering, scattering+offset
  (CS-38), and rubberband (3 of 6 modes).
* **Phase 4t** — the remaining three modes: linear, polynomial,
  spline. ``BASELINE_MODES`` is now fully covered; no mode raises
  on ``floor_zero=True``.

UI surface
----------

`UVVisTab._init_left_pane` adds a single Tk var:

::

    self._baseline_floor_zero = tk.BooleanVar(value=False)

…and a `tk.Checkbutton` packed in `bl_body` between the mode
combobox `mode_frame` and the per-mode parameter rows
`_baseline_params_frame`:

::

    floor_frame = tk.Frame(bl_body)
    floor_frame.pack(fill=tk.X, padx=4, pady=(2, 0))
    self._baseline_floor_zero_cb = tk.Checkbutton(
        floor_frame, text="Floor at zero",
        variable=self._baseline_floor_zero, font=F9,
    )
    self._baseline_floor_zero_cb.pack(anchor="w")

Always visible regardless of mode. Phase 4t adds the disabled-
state machinery (CS-43) that greys the toggle out when the active
mode isn't in ``_FLOOR_ZERO_SUPPORTED_MODES``; today the supported
set covers every mode in ``BASELINE_MODES``, so the disabled
branch never fires — it's defensive scaffolding for a future
mode added without floor-zero coverage.

Params round-trip
-----------------

`_collect_baseline_params(mode)` injects `"floor_zero":
bool(self._baseline_floor_zero.get())` into **every** mode's
returned dict (linear / polynomial / spline / rubberband /
scattering / scattering+offset). The toggle state is therefore
recorded on every BASELINE OperationNode, regardless of whether
the constrained-fit code path is implemented for that mode yet —
so when the linear / polynomial / spline branches ship in a later
session, prior projects round-trip cleanly.

Pure-module helpers
-------------------

`uvvis_baseline._floor_zero(params)` reads the flag from a
possibly-None mapping (`compute_rubberband` accepts `params=None`
for API symmetry).

Per-mode implementation:

* **scattering** (Phase 4s) — closed-form: under the model
  `B = c · λ^(-n)`, the constraint `c · λ_i^(-n) ≤ a_i`
  everywhere reduces to `c ≤ min_i(a_i · λ_i^n)`. The
  unconstrained least-squares `c*` is computed exactly as before;
  if `c* > c_max`, clamp to `c_max`. With `n="fit"`, a 1-D
  `scipy.optimize.minimize_scalar` bounded scan over `n ∈
  n_bounds` (CS-41) carries the closed-form constrained-c step
  inside as the residual function.

* **scattering+offset** (Phase 4s, CS-38) — convex QP via
  `scipy.optimize.minimize(method="SLSQP")` with linear
  inequality `a_param + c · λ_i^(-n) ≤ a_i` at every full-range
  sample (encoded via `LinearConstraint`). Initial guess: project
  the unconstrained 2-D linear LSQ down by the maximum overage.
  Failure surfaces as `ValueError("scattering+offset floor-zero
  fit did not converge: …")`.

* **rubberband** (Phase 4s) — no-op + invariant assert. The
  convex-hull lower envelope is ≤ data by construction; the
  guard raises if numerical drift takes the corrected curve
  below `-1e-9`.

* **linear** (Phase 4t) — `_linear_floor_zero_fit` runs SLSQP on
  the two-anchor pair `(a_lo, a_hi)`. Objective minimises L2
  distance from the unconstrained sampled values so the result
  matches the unconstrained line when the constraint isn't
  binding. ``LinearConstraint`` rows are
  `(1 - weight_i) · a_lo + weight_i · a_hi ≤ a_i` at every
  full-range sample, where `weight_i = (wl_i - lo) / (hi - lo)`
  is the linear-interpolation coefficient. Initial guess shifts
  the unconstrained pair down by the maximum overage so SLSQP
  starts feasible.

* **polynomial** (Phase 4t) — `_polynomial_floor_zero_fit` runs
  SLSQP on the polynomial coefficients. The solve runs in a
  normalized variable `z = (wl − center) / half_range` so the
  Vandermonde columns stay within ~1 order of magnitude
  regardless of polynomial order; without the normalization the
  raw `wl ∈ [200, 800]` Vandermonde columns span 6 orders of
  magnitude for order ≥ 2 and SLSQP fails with "Inequality
  constraints incompatible" before the line search moves. The
  fitted z-space polynomial is converted back to wl-space
  ``np.polyfit`` ordering by evaluating at every wl sample and
  re-fitting — robust round-trip with no manual basis transforms.

* **spline** (Phase 4t) — `_spline_floor_zero_fit` runs SLSQP on
  the per-anchor absorbance vector. The constraint function is
  expressed via ``NonlinearConstraint`` even though the
  underlying problem is linear in `anchor_a` (the
  CubicSpline / polynomial-fallback solve is a linear map from
  point-values to evaluated-values). The single ``_spline_evaluate``
  helper is shared between the unconstrained and constrained
  paths so all three branches (4-anchor cubic spline, 3-anchor
  quadratic, 2-anchor linear) propagate the constraint
  consistently.

All five SLSQP-based paths surface convergence failure as
``ValueError("<mode> floor-zero fit did not converge: …")``;
the apply site catches `(ValueError, KeyError)` and shows the
message via `messagebox.showerror`. No silent fall-through.

Lock surface
------------

CS-37 is the universal toggle's surface plus all six modes'
constrained-fit code paths (Phase 4s shipped 3/6, Phase 4t
shipped the remaining 3/6 plus the disabled-state machinery).
The lock relaxes only when:

* a future new ``BASELINE_MODES`` entry needs its own
  constrained-fit branch — see CS-43 for how it slots into
  ``_FLOOR_ZERO_SUPPORTED_MODES``;
* the apply site grows a "fit-once" refactor that returns the
  resolved baseline + fit-info from a single ``compute_*`` call
  instead of re-running ``fit_*`` for diagnostics (Phase 4s
  friction #4 — process note, no register entry today).

Tests
-----

`TestRubberbandFloorZero` (2 pure tests) — invariant guard
passes through; output matches unconstrained within fp tolerance.

`TestScatteringFloorZero` (3 pure tests) — pure power-law
unchanged when constraint doesn't bind; constrained `c` clamps
to `min_i(a_i · λ_i^n)` when it does; n="fit" + floor_zero
returns non-negative corrected output.

Phase 4t replaced the deferral-raise contract with three new
behavioural classes (the old `TestFloorZeroNotYetImplemented` was
removed):

* `TestLinearFloorZero` (3 pure tests) — inactive matches
  unconstrained on a positive-bg Gaussian; clamp-on-overshoot via
  a negative-dip spectrum; anchor-ordering invariance under the
  constraint.
* `TestPolynomialFloorZero` (3 pure tests) — inactive matches on
  a pure linear bg with order-1; clamp-on-overshoot with order-2
  on the dip spectrum (exercises the z-space conditioning path);
  order-0 constant degenerate path.
* `TestSplineFloorZero` (4 pure tests) — inactive matches via
  4-anchor cubic spline; clamp-on-overshoot on a 4-anchor spline
  tracing the dip; 2-anchor linear-fallback and 3-anchor
  quadratic-fallback paths so the constraint propagation is
  verified across all three branches of `_spline_evaluate`.

Integration tests:

* `test_baseline_floor_zero_toggle_exists_and_defaults_off`,
  `test_apply_baseline_writes_floor_zero_into_params` (Phase 4s)
  — Tk var + Checkbutton present and default-off; params round-trip.
* `test_apply_baseline_linear_with_floor_zero_creates_baseline_node`
  (Phase 4t — replaces the Phase 4s "_surfaces_error" test) +
  `test_apply_baseline_polynomial_with_floor_zero_creates_baseline_node`
  + `test_apply_baseline_spline_with_floor_zero_creates_baseline_node`
  — apply-site coverage of the new constrained-fit paths;
  confirms result is non-None, op + BASELINE data nodes are
  created, op records `floor_zero=True`.

---

## CS-38 — Composite scattering+offset baseline mode (Phase 4s)

`B(λ) = a + c · λ^(-n)` for samples that carry both a Rayleigh /
Mie scattering tail AND an instrument or solvent offset. Same
parameter schema as the existing scattering mode — `n` (numeric
or "fit"), `fit_lo_nm`, `fit_hi_nm`, optional `floor_zero`. The
additive constant `a` is always fitted.

Mode registration
-----------------

`BASELINE_MODES` grows from 5 to 6:

::

    BASELINE_MODES = (
        "linear", "polynomial", "spline", "rubberband",
        "scattering", "scattering+offset",
    )

`_DISPATCH` adds the new entry:

::

    "scattering+offset": compute_scattering_offset,

The combobox auto-pulls the new entry via
`values=list(uvvis_baseline.BASELINE_MODES)`.

Pure-module helpers
-------------------

`compute_scattering_offset(wl, a, params)` mirrors
`compute_scattering` but with the additional fitted constant.
Internally:

* `_scattering_window(wl, a, params, label="scattering+offset")`
  shared with `compute_scattering` — single source of truth for
  fit-window validation + nm-range error widening (CS-40).
* `_scattering_offset_fit(wl, a, wl_w, a_w, lo, hi, n_in,
  floor_zero)` does the actual fit. For fixed `n`: 2-D linear
  LSQ via `np.linalg.lstsq` on design columns
  `[1, λ^(-n)]`. For `n="fit"`: 1-D bounded scan over `n ∈
  [0.1, 8.0]` with `scipy.optimize.minimize_scalar`, calling the
  2-D solve inside as the residual. Under `floor_zero=True`, the
  2-D solve becomes a convex QP (see CS-37).

UI sharing with scattering
--------------------------

The user's mental model is "scattering with an offset", so CS-38
shares the existing scattering Tk vars:

* `_baseline_scattering_n: tk.StringVar(value="4")`
* `_baseline_scattering_fit_n: tk.BooleanVar(value=False)`
* `_baseline_scattering_fit_lo: tk.StringVar(value="")`
* `_baseline_scattering_fit_hi: tk.StringVar(value="")`

`_refresh_baseline_param_rows` extends the scattering branch:

::

    elif mode in ("scattering", "scattering+offset"):
        # Same row layout — n entry + Fit n checkbox + fit lo/hi.
        ...

`_collect_baseline_params` extends the same way — the only
difference is the `mode` field on the OperationNode's params
dict, which the dispatcher uses to pick the right `compute_*`.

The tight coupling is deliberate: a follow-up register entry
(USER-FLAGGED Phase 4s) will collapse the two modes into a
single `scattering` mode with an "Add offset" Checkbutton. The
shared Tk vars + shared parameter row layout in CS-38 are
already the right factoring for that consolidation.

Lock surface
------------

CS-38 owns the new mode's `compute_*` + the parameter row
sharing with scattering. The composite mode shape (additive
offset always fitted; no separate "fit a" toggle) is locked.

Tests
-----

`TestScatteringOffsetMode` (7 pure tests) — recovers the unit
peak height for fixed n / n="fit" / `floor_zero=True`; subtracts
a pure `a + c·λ^(-n)` background to ~zero; rejects negative
`n`, non-numeric/non-"fit" `n`, and missing param keys.

`TestDispatcherWithScatteringOffset` (2 pure tests) — `compute(
"scattering+offset", …)` routes correctly and `BASELINE_MODES`
length grows to 6.

`test_scattering_offset_mode_swaps_parameter_rows` and
`test_apply_scattering_offset_creates_baseline_node` (2
integration tests) — the new mode reuses scattering's 3-row
layout and materialises a BASELINE OperationNode with mode
discriminator `"scattering+offset"`.

---

## CS-39 — Fit-helper persistence on OperationNode (Phase 4s)

Phase 4m friction #2 noted that scattering with `n="fit"` loses
the resolved numeric `n` in `op.params` — the param dict carries
the literal string `"fit"`, so a downstream consumer has to
re-run the operation to recover the value. CS-39 closes this by
persisting the fit's resolved parameters as sibling keys on the
OperationNode.

Public helpers
--------------

`uvvis_baseline.fit_scattering(wl, a, params) -> dict` returns
`{"c_fitted": float, "n_fitted": float}`. Same param schema as
`compute_scattering`. Internally calls the same
`_scattering_fit` helper that `compute_scattering` uses, so the
returned values are guaranteed identical to what the compute
path produced.

`uvvis_baseline.fit_scattering_offset(wl, a, params) -> dict`
returns `{"a_fitted": float, "c_fitted": float, "n_fitted":
float}` — three keys, all always populated (`a` and `c` are
always fitted; `n_fitted` equals `params["n"]` when fixed or the
recovered value when `n="fit"`).

Apply-site integration
----------------------

`UVVisTab._apply_baseline` calls the matching helper after
`compute()` returns successfully:

::

    if mode == "scattering":
        try:
            info = uvvis_baseline.fit_scattering(wl, absorb, params)
            op_params["c_fitted"] = info["c_fitted"]
            if str(params.get("n", "")).lower() == "fit":
                op_params["n_fitted"] = info["n_fitted"]
        except (ValueError, KeyError):
            pass
    elif mode == "scattering+offset":
        try:
            info = uvvis_baseline.fit_scattering_offset(wl, absorb, params)
            op_params["a_fitted"] = info["a_fitted"]
            op_params["c_fitted"] = info["c_fitted"]
            if str(params.get("n", "")).lower() == "fit":
                op_params["n_fitted"] = info["n_fitted"]
        except (ValueError, KeyError):
            pass

Failure here is non-fatal — the corrected spectrum already
exists; we silently skip the diagnostic keys. This guards
against a future refactor where the fit helper diverges from
the compute path; the apply node still lands.

Why the helpers re-run the fit
------------------------------

`compute_scattering` and `compute_scattering_offset` could
return a `(corrected, info)` tuple instead, avoiding the
re-run. The current shape (helpers re-run the fit) was chosen
because:

* Existing 12 unit tests for scattering compute call the
  array-only signature directly. Threading info through
  every call site for a feature that's mostly diagnostic
  doesn't pay back the test churn.
* The fit cost on UV/Vis spectra (~600 points, closed-form
  linear LSQ or 1-D `minimize_scalar`) is microseconds.
* Future ops with genuinely expensive fits (e.g. a global
  nonlinear solver) would prefer the tuple-return shape.
  The CS-39 register entry's friction note flags the
  re-run for that future case.

Surface coverage
----------------

CS-39 records the values; surfacing them in the
ScanTreeWidget tooltip / export header / a future
diagnostic console folds into the open Diagnostic console
register entry (USER-FLAGGED Phase 4n).

Tests
-----

`TestFitScatteringHelper` (3 pure tests) — fixed n returns
`n_fitted == n`; n="fit" recovers ~4 for a Rayleigh
background; floor_zero shrinks `c_fitted` when the constraint
binds.

`TestFitScatteringOffsetHelper` (2 pure tests) — returns all
three keys; recovers the additive offset and exponent for a
synthetic spectrum.

`test_scattering_n_fit_persists_n_fitted_and_c_fitted`,
`test_scattering_fixed_n_persists_c_fitted_only`,
`test_scattering_offset_persists_a_fitted` (3 integration
tests) — the apply path writes the resolved keys onto
`OperationNode.params` exactly when expected (n_fitted only
under n="fit"; a_fitted always for the composite mode).

---

## CS-40 — Fit-window error messages widen to data range (Phase 4s)

Phase 4m friction #4: a user typing a fit window outside the
spectrum's range sees only the requested window in the error
message, with no hint of where the data actually is. Trivial
fix; CS-40 ships it across every fit-window error path in the
UV/Vis pure modules.

Touched messages
----------------

`uvvis_baseline.compute_polynomial`:

::

    raise ValueError(
        f"polynomial order {order_n} requires > {order_n} points in "
        f"the fit window [{lo}, {hi}]; found {n_in}; "
        f"data spans [{float(wl.min()):.1f}, {float(wl.max()):.1f}] nm"
    )

`uvvis_baseline._scattering_window` (shared by scattering and
scattering+offset):

::

    raise ValueError(
        f"{label} baseline needs ≥ 2 points in fit window "
        f"[{lo}, {hi}]; found {n_in}; "
        f"data spans [{float(wl.min()):.1f}, {float(wl.max()):.1f}] nm"
    )

`uvvis_normalise._window_mask` (shared by peak / area):

::

    raise ValueError(
        f"normalisation window [{lo}, {hi}] contains no samples; "
        f"data spans [{float(wl.min()):.1f}, {float(wl.max()):.1f}] nm"
    )

Format choice
-------------

One-decimal precision (`:.1f`) is the right resolution for
nm-scale spectra: the user reads the messagebox alongside the
plot's axis ticks, which are typically marked at 50 nm or 100 nm
intervals. Sub-nm precision adds noise; integer precision loses
information when the spectrum starts at e.g. 199.5 nm.

Lock surface
------------

CS-40 is the message-content append. The Phase 4o friction #1
"diagnostic-console intent" register entry will eventually
reformat these messages to also flow through a structured log
pane; the pure-module ValueError raise stays as the
authoritative source of truth.

Tests
-----

`TestErrorMessageDataRange` (3 pure tests in test_uvvis_baseline)
— polynomial / scattering / scattering+offset error messages
include "data spans", and the actual nm range substring.

`TestErrorMessageDataRange` (2 pure tests in test_uvvis_normalise)
— peak and area window messages include "data spans" and the
data range.

---

## CS-41 — Configurable n="fit" scan bounds (Phase 4t)

Phase 4s friction #3: the n="fit" branch in `_scattering_fit` and
`_scattering_offset_fit` called `scipy.optimize.minimize_scalar(
..., bounds=(0.1, 8.0), method="bounded")`. The default range
covers Rayleigh (n=4), large-particle Mie (n≈2), and dust-tail
(n≈1) comfortably, but a sub-Rayleigh tail (n ≈ 0.5) or an
unusual fit could pin at the bound silently. CS-41 makes the
range a per-fit parameter without changing the default.

Hook surface
------------

`uvvis_baseline._DEFAULT_N_BOUNDS: tuple[float, float] = (0.1, 8.0)`
captures the historical default. `_resolve_n_bounds(params)` reads
the optional override and validates `(lo, hi)`:

* must be a 2-tuple (TypeError / IndexError on shape mismatch);
* both entries ≥ 0;
* `lo < hi` strictly.

The validated tuple threads through `_scattering_fit` and
`_scattering_offset_fit` as a kwarg defaulting to
`_DEFAULT_N_BOUNDS`, then reaches the
`minimize_scalar(..., bounds=n_bounds, method="bounded")` call.

Branch asymmetry (read carefully)
---------------------------------

`_scattering_fit`'s n="fit" path has TWO branches:

* `floor_zero=True` — bounded scan via `minimize_scalar`; n_bounds
  applies.
* `floor_zero=False` — closed-form log–log linear regression
  (`np.polyfit(log(wl_w), log(a_w), 1)`); n_bounds is read +
  validated for symmetry but does not constrain the fit (the
  log–log path has no bounds).

`_scattering_offset_fit`'s n="fit" path always uses the bounded
scan (its 2-D closed-form `(a, c)` step requires fixed n), so
n_bounds always applies for that helper.

UI surface
----------

None today — the hook is API-only this session. The matching Tk
row (two extra Entries surfaced when "Fit n" is checked, with
default-prefill from `_DEFAULT_N_BOUNDS`) is deferred per the
register entry.

Lock surface
------------

The default value `(0.1, 8.0)` and the validation contract
(`0 ≤ lo < hi`) are locked. The lock relaxes when the matching
UI row ships — adding the Tk vars + the default-prefill +
threading from `_collect_baseline_params` into `params["n_bounds"]`
keeps the helper signatures unchanged.

Tests
-----

`TestNFitBoundsConfigurable` (8 pure tests) — default bounds
recover truth; custom bounds bracketing truth recover it on both
helpers under the appropriate branch (floor_zero=True for
`_scattering_fit`, always for `_scattering_offset_fit`); narrow
bounds pin n at the upper edge on both; three validation tests
(`lo >= hi`, negative entry, non-pair); one no-effect test
confirming n_bounds is read+validated but doesn't alter output
when n is fixed numerically.

---

## CS-42 — Tooltip module promotion (Phase 4t)

Phase 4q (CS-33) introduced `_Tooltip` as a private class inside
`scan_tree_widget.py`. Phase 4r friction #1 noted that the new
per-row `[~]/[–]` baseline-curve toggle (CS-36) needed a tooltip
of its own but the helper was private; the canonical follow-up
(Phase 4q friction #3 in the BACKLOG friction section) was to
extract `_Tooltip` to its own module on first cross-module
re-use. CS-42 ships that extraction together with the second
and third consumers.

Module layout
-------------

`tooltip.py` — new module; only stdlib `tkinter` import. Public
class `Tooltip` (no leading underscore — public API now).
Behaviour unchanged from CS-33: 600 ms hover delay,
borderless `tk.Toplevel`, light-yellow `bg="#FFFFE0"`,
`<Enter>` / `<Leave>` / `<ButtonPress>` binding triple via
`add="+"` so widget-owner bindings are not displaced.
``update_text`` rotates the tooltip text in place; `_show` bails
silently when text is the empty string, so an "empty-string
sentinel" pattern works for tooltips that should be silent under
some states (used by CS-43 for the floor-zero toggle).

Consumers
---------

* `scan_tree_widget.py` — drops the local class, adds
  `from tooltip import Tooltip`, renames the two existing
  call sites (truncated label + sweep-leader truncated label),
  and adds a third call site:
  `Tooltip(bc_btn, "Show / hide baseline curve overlay")` on
  the per-row `[~]/[–]` toggle so the gesture is no longer
  discoverable only by experimentation. Resolves Phase 4r
  friction #1.
* `uvvis_tab.py` — `from tooltip import Tooltip`, attaches a
  Tooltip to `_baseline_floor_zero_cb` at panel build time and
  stores it as `_baseline_floor_zero_tooltip` so CS-43's refresh
  method can rotate the text in place.

Test promotion
--------------

`test_scan_tree_widget.py` `TestTooltip` updates its imports
from `from scan_tree_widget import _Tooltip` to
`from tooltip import Tooltip` (renaming the symbol); the three
existing tests (construction, update_text, hide-idempotency)
pass unchanged. New test
`TestPerNodeBaselineCurveToggle.test_baseline_curve_button_has_tooltip`
asserts the `<Enter>` binding is present on the [~] toggle and
that a fresh `Tooltip(btn, …)` constructs cleanly with the
canonical hint text.

Lock surface
------------

CS-42 is the module split + the empty-string-sentinel contract.
The lock relaxes when a tooltip-elsewhere-in-the-app needs a
new behaviour (e.g. multi-line tooltip wrapping, programmatic
positioning); the helper grows additively on the consumer's
demand. No app-wide tooltip styling layer until at least three
consumers want different defaults.

---

## CS-43 — Floor-zero toggle disabled-state machinery (Phase 4t)

Phase 4s friction #1 (USER-FLAGGED): the universal "Floor at
zero" Checkbutton stayed clickable for every mode regardless of
whether `compute_*` had its constrained-fit branch. Linear /
polynomial / spline raised a `ValueError` from the apply path
under `floor_zero=True`, but the user only learned the mode was
unsupported by triggering the messagebox. CS-43 ships the
disabled-state mechanism that surfaces "unsupported" at the
toggle.

Module-level constants
----------------------

`uvvis_tab.py` adds two module-level constants:

::

    _FLOOR_ZERO_SUPPORTED_MODES: frozenset[str] = frozenset(
        uvvis_baseline.BASELINE_MODES
    )
    _FLOOR_ZERO_DISABLED_TOOLTIP: str = (
        "Floor-zero is not supported for this baseline mode."
    )

The supported set is initialised to every entry in
``BASELINE_MODES`` because Phase 4t shipped floor-zero for all
six modes (E from the session intent). Today the disabled branch
never fires; the constant remains as defensive scaffolding so a
future new mode added to ``BASELINE_MODES`` without floor-zero
coverage greys the toggle out automatically.

Refresh method
--------------

::

    def _refresh_floor_zero_state(self) -> None:
        if not hasattr(self, "_baseline_floor_zero_cb"):
            return
        mode = self._baseline_mode.get()
        if mode in _FLOOR_ZERO_SUPPORTED_MODES:
            self._baseline_floor_zero_cb.config(state="normal")
            self._baseline_floor_zero_tooltip.update_text("")
        else:
            self._baseline_floor_zero_cb.config(state="disabled")
            self._baseline_floor_zero_tooltip.update_text(
                _FLOOR_ZERO_DISABLED_TOOLTIP,
            )

Wired to the `_baseline_mode` Tk var trace alongside
`_refresh_baseline_param_rows` (callbacks are independent;
ordering doesn't matter — neither reads the other's state) and
called once at init time so the toggle starts in the correct
state.

Design lock — the BooleanVar value is preserved across
enable/disable transitions. A user who toggles floor-zero ON
under scattering, flips to a (hypothetically) unsupported mode,
then flips back to scattering finds the toggle still ON. This
matches the persistence-umbrella's preferred carry-forward shape.

Tooltip via the empty-string sentinel
-------------------------------------

The tooltip is constructed once at panel-build time with empty
text:

::

    self._baseline_floor_zero_tooltip = Tooltip(
        self._baseline_floor_zero_cb, "",
    )

`_refresh_floor_zero_state` rotates the text via `update_text`
between the empty string (supported mode — `Tooltip._show` bails
silently) and `_FLOOR_ZERO_DISABLED_TOOLTIP` (unsupported mode —
the hover hint paints). One Tooltip instance, no per-mode
construction churn.

Lock surface
------------

CS-43 is the constant + the refresh method + the tooltip rotation
contract. The lock relaxes only when `_FLOOR_ZERO_SUPPORTED_MODES`
needs to change shape (e.g. growing a per-mode opt-out reason
that the tooltip could surface); today it's a flat `frozenset`
keyed by mode name and the tooltip text is mode-agnostic.

Tests
-----

`TestUVVisTabBaseline.test_floor_zero_checkbutton_is_enabled_for_supported_modes`
walks every entry in `BASELINE_MODES` and asserts state="normal"
+ tooltip empty. Pins the Phase 4t invariant
`_FLOOR_ZERO_SUPPORTED_MODES == frozenset(BASELINE_MODES)`.

`TestUVVisTabBaseline.test_floor_zero_checkbutton_disables_for_unsupported_mode`
monkey-patches the constant to `frozenset()`, calls the refresh,
and asserts state="disabled" + tooltip text rotates to
`_FLOOR_ZERO_DISABLED_TOOLTIP`. Restores the constant in finally
so isolation holds.

`TestUVVisTabBaseline.test_floor_zero_disabled_state_preserves_var_value`
pins the carry-forward design lock by setting the BooleanVar
True, monkey-patching the constant to empty, calling the refresh,
and asserting the BooleanVar is still True afterwards.

`TestUVVisTabBaseline.test_floor_zero_tooltip_constructed_at_panel_build`
asserts the tooltip is a `Tooltip` instance bound to
`_baseline_floor_zero_cb`.

---

## CS-44 — Multi-axis plot routing (Phase 4u)

Phase 4u (`uvvis_tab.py` + `test_uvvis_tab.py`) introduces a
NodeType-keyed axis routing system that resolves the Phase 4t
friction #2 USER-FLAGGED concern about SECOND_DERIVATIVE values
collapsing the primary y-axis. The user expanded the original
"right axis for the second derivative" scope at session start to
"we may need to build in other secondary axes for other processes
and might even need to add a third y-axis somehow in some cases",
so the implementation generalises to a three-role axis vocabulary
with lazy creation, per-NodeType defaults, and a deferred per-style
override hook.

**Module-level constants and tables.**

- `_AXIS_ROLES: tuple[str, ...] = ("primary", "secondary", "tertiary")`
  fixes the role vocabulary in deterministic order. `_redraw` walks
  this tuple to build the role → Axes map.
- `_DEFAULT_Y_AXIS_BY_NODETYPE: dict[NodeType, str]` is the per-
  NodeType default mapping. Today: UVVIS / BASELINE / NORMALISED /
  SMOOTHED / PEAK_LIST → `"primary"`; SECOND_DERIVATIVE →
  `"secondary"`. NodeTypes absent from the table fall through to
  `"primary"` via the lookup default in `_resolve_y_axis_role`.
  Future NodeType additions (Beer-Lambert concentration; difference
  spectra; MCR component profiles when chemometrics lands) are a
  one-line table edit.
- `_NON_PRIMARY_Y_LABEL: dict[tuple[NodeType, str], str]` is the
  x-unit-aware label table for non-primary roles. Today populated
  for `(SECOND_DERIVATIVE, "nm") → "d²A/dλ²"`,
  `(SECOND_DERIVATIVE, "cm-1") → "d²A/d(cm⁻¹)²"`, and
  `(SECOND_DERIVATIVE, "eV") → "d²A/dE²"`. The x-unit awareness is
  a Q3 user decision: the label is physically meaningful, not
  cosmetic, so it must stay correct as the user toggles the x-axis
  unit. Pairs absent from the table return `None` and the role
  goes unlabelled.
- `_TERTIARY_AXIS_OFFSET_FRAC: float = 1.12` is the matplotlib axes-
  coordinate position for the tertiary axis's right spine. Tunable
  later via a Plot Settings field per Q2 user decision; module-level
  today so the helper signatures stay stable across the eventual
  promotion. The 1.10–1.15 range is the typical convention for
  3-axis stacks.

**Pure helpers.**

- `_resolve_y_axis_role(node_type: NodeType) -> str` returns the
  per-NodeType default. Phase 4u Decision 1 ships per-NodeType only;
  the future per-style override (`node.style.get("y_axis")`) lands
  at the front of this function as an additive change without
  breaking the call sites.
- `_resolve_non_primary_y_label(node_type: NodeType, x_unit: str)
  -> Optional[str]` returns the registered label for a given
  `(NodeType, x_unit)` pair, or `None` for unregistered pairs.

**Lazy axis-creation flow inside `_redraw`.**

After `self._fig.clear()` + re-creating primary, the rewrite
instantiates `self._axes_by_role: dict[str, Axes] = {"primary": ax}`
and a local `first_node_type_per_role: dict[str, NodeType]` tracker.
An inner closure `get_axis(role)` returns the existing axis for a
role or creates it on first request:

- `"secondary"` → `ax.twinx()`.
- `"tertiary"` → second `ax.twinx()` with
  `spines["right"].set_position(("axes", _TERTIARY_AXIS_OFFSET_FRAC))`.
- Unknown role → falls back to primary (defensive — the future
  per-style override could surface a malformed value).

Newly-created non-primary axes inherit the primary's tick direction
and tick label size at creation time (`tick_params(direction=…,
labelsize=…)`).

The per-node loop body now resolves the role via
`_resolve_y_axis_role(node.type)`, calls `get_axis(role)` for the
target Axes, records the first NodeType to land on each non-primary
role (so labelling is order-deterministic), and dispatches `plot()`
+ `fill_between()` onto the resolved target. CS-29 baseline-curve
overlay and CS-19 peak-list scatter route through the same resolver
for consistency, even though both currently resolve to `"primary"`
— the indirection lets a future routing change land as a single
table edit.

**Y-label propagation.**

After the per-node loops, `_redraw` walks
`first_node_type_per_role.items()` and calls
`_axes_by_role[role].set_ylabel(label, ...)` for each populated
non-primary role whose first NodeType has a registered label.
Roles whose first NodeType is unregistered go unlabelled rather
than showing a guess.

**Legend merge.**

`ax.get_legend_handles_labels()` only collects artists on its own
Axes, so without an explicit merge a SECOND_DERIVATIVE node on the
right axis would silently drop out of the legend. The rewrite walks
every populated `_axes_by_role` axis, concatenates handles + labels,
and calls `ax.legend(handles, labels, …)` once on primary so the
user sees a single unified legend.

**Y-limit handling.**

The existing `_ylim_lo` / `_ylim_hi` Tk vars apply to primary only
this phase (Decision 4 in the Phase 4u step-2 design lock). Per-role
y-limit Tk vars are explicitly out of scope; the friction note is
carried forward for the next phase that needs to clamp the
secondary derivative trace.

**Empty-state hygiene.**

`_draw_empty` was changed to call `self._fig.clear()` instead of
`self._ax.cla()` — without the full clear, stale twin axes from a
prior populated draw would linger as floating spines on the empty-
state placeholder. The role map is reseeded to `{"primary": self._ax}`
so the next populated redraw starts from a clean slate.

**Related but separate: cm⁻¹ → λ(nm) top axis.**

The existing `secondary_xaxis("top", functions=(_fwd, _fwd))` axis
that appears under `unit == "cm-1"` is an x-axis sibling on the
*top* spine of primary, not a y-axis role. It uses matplotlib's
linked-transform-pair mechanism (different from the y-axis
`twinx()` machinery above) and stays anchored to primary regardless
of which y-axis roles are populated. Documented here so future
readers do not conflate the two.

**Tertiary axis is wired but unused today.**

No NodeType defaults to `"tertiary"` in the production table.
`TestUVVisTabTertiaryAxisPath.test_tertiary_axis_lazily_created_with_offset_spine`
proves the offset-spine path works end-to-end by monkey-patching
`_resolve_y_axis_role` to route a NORMALISED node to `"tertiary"`,
then asserting (a) the third Axes is created in `_axes_by_role`, (b)
its right spine sits at `_TERTIARY_AXIS_OFFSET_FRAC` (read from the
live constant so a future Plot Settings promotion that changes the
value does not silently break the assertion), and (c) the routed
curve lands on the tertiary axis while primary keeps the parent.

**Test coverage.**

- `TestMultiAxisRoutingHelpers` (9 pure-module tests, no Tk
  dependency) — pin the role-tuple shape, the per-NodeType default
  table coverage, every renderer NodeType's resolved role, the
  unknown-NodeType fallback, the value-subset-of-roles drift guard,
  the x-unit-aware non-primary label round-trip across nm / cm-1 /
  eV, the unregistered-pair `None` return, and the tertiary-offset
  constant in the typical matplotlib range.
- `TestUVVisTabSecondDerivativeIntegration` — three existing tests
  updated to the post-CS-44 "primary has 1, secondary has 1" line
  shape (was: "primary has 2"); four new tests (`test_secondary_axis_label_is_x_unit_aware`,
  `test_legend_merges_handles_across_primary_and_secondary`,
  `test_no_secondary_axis_when_only_primary_nodes_visible`,
  `test_empty_state_resets_role_map_to_primary_only`).
- `TestUVVisTabTertiaryAxisPath` — one new test
  (`test_tertiary_axis_lazily_created_with_offset_spine`).

**Locked invariants.**

- `_AXIS_ROLES` shape, order, and length are pinned by tests.
  Shrinking back to two roles or reordering would surface as a CI
  failure.
- `_DEFAULT_Y_AXIS_BY_NODETYPE` must contain every renderer
  NodeType (UVVIS / BASELINE / NORMALISED / SMOOTHED / PEAK_LIST /
  SECOND_DERIVATIVE) explicitly. Adding a new renderer NodeType
  requires adding a row.
- The `_resolve_y_axis_role` signature is `(node_type: NodeType)
  -> str`. The future per-style override extends to `(node_type,
  style: Mapping | None = None) -> str` — additive only.
- Y-limit Tk vars apply to primary. Per-role limits are deferred.
- `_TERTIARY_AXIS_OFFSET_FRAC` is module-level; promote to a Plot
  Settings field when a real tertiary-axis NodeType lands.
- `_draw_empty` must `_fig.clear()` (not `cla()`) and reseed
  `_axes_by_role` to primary-only. Skipping the reseed leaks twin
  axes across populated → empty transitions.

---

## CS-45 — Per-OperationType implementation hash registry (Phase 4v)

**Source files.** `operation_hash.py` (new module).

**Purpose.** A per-OperationType registry maps each op to the bundle
of `compute_*` + shared helpers that constitute its implementation.
`compute_implementation_hash(op_type)` returns the SHA-256 of the
sorted-by-qualname concatenation of `inspect.getsource()` bytes for
every registered callable, domain-separated by op name. Apply sites
stamp the result into `OperationNode.metadata["implementation_hash"]`;
project load (CS-46) recomputes the hash and surfaces drift via
`LoadedProject.implementation_warnings`.

**Why automatic source-hash (Q1.a lock) and not manual semver.**
- Zero developer overhead — no string to bump on every conditioning
  tweak; auto-detected the Phase 4t polynomial conditioning swap that
  motivated the umbrella entry.
- Manual semver gets forgotten; the failure mode (silent drift) is
  exactly what the entry was raised to prevent.
- False positives from whitespace-only edits are the right behaviour
  on the precautionary-principle side: re-run is one click in the
  load-time mismatch dialog, and a stable formatter (e.g. `black`)
  keeps run-to-run noise out.

**Data model additions.**

`OperationNode` (in `nodes.py`) gains two new fields with defaults
that preserve every existing construction site:

- `metadata: dict[str, Any] = field(default_factory=dict)` — apply
  sites stamp `metadata["implementation_hash"]` here.
- `deterministic: bool = True` — persistence Phase A may skip the
  array sidecar for deterministic ops (re-derived on load); always
  stores arrays for non-deterministic ops. Every op shipped today is
  deterministic; the field exists for the future Monte Carlo /
  MCR-ALS / bootstrap entries.

**Module surface.**

```
_HASH_REGISTRY: dict[OperationType, tuple[Callable, ...]]   # private
_HASH_CACHE: dict[OperationType, str]                       # private
SENTINEL_PREFIX = "unregistered:"                           # public

register_implementation(op_type, *callables) -> None
clear_registry() -> None
is_registered(op_type) -> bool
registered_op_types() -> tuple[OperationType, ...]
compute_implementation_hash(op_type) -> str
register_default_implementations() -> None
```

**Hash algorithm.**

```
h = SHA256()
h.update(b"op_type:" + op_name.encode() + b"\n")
for fn in sorted(bundle, key=qualname):
    h.update(b"fn:" + qualname(fn).encode() + b"\n")
    h.update(getsource(fn).encode() + b"\n")
return h.hexdigest()
```

Domain separation by op name prevents the registry from accidentally
colliding hashes between two ops with the same callables. Sorting by
qualname ensures bundle-order independence. Cache invalidates on
`register_implementation` so test re-registration produces fresh
hashes.

**Default registrations (production).**

`register_default_implementations()` is called from
`OrcaTDDFTApp.__init__` before any apply runs:

| OperationType | Bundle |
|---|---|
| `BASELINE` | six `compute_*` (linear / polynomial / spline / rubberband / scattering / scattering_offset) + four shared helpers (`_floor_zero`, `_resolve_n_bounds`, `_spline_evaluate`, `_spline_floor_zero_fit`) + three scattering helpers (`_scattering_window`, `_scattering_fit`, `_scattering_offset_fit`) |
| `NORMALISE` | `compute_peak`, `compute_area`, `_coerce`, `_window_mask` |
| `SMOOTH` | `compute_savgol`, `compute_moving_avg`, `_coerce` |
| `PEAK_PICK` | `compute_prominence`, `compute_manual`, `_coerce` |
| `SECOND_DERIVATIVE` | `compute`, `_coerce` |
| `LOAD` | `parse_uvvis_file` |

Unregistered ops (DEGLITCH / SHIFT_ENERGY / AVERAGE / DIFFERENCE /
FEFF_RUN / BXAS_FIT) return `"unregistered:<OperationType.name>"`
sentinels. Manifest diffs of sentinel-vs-sentinel are no-ops; sentinel-
vs-real-hash is treated as a structural change worth surfacing.

**Apply sites that stamp.**

| Site | OperationType |
|---|---|
| `uvvis_tab._apply_baseline` | `BASELINE` |
| `uvvis_tab._on_uvvis_loaded` | `LOAD` |
| `uvvis_normalise.NormalisationPanel._apply` | `NORMALISE` |
| `uvvis_smoothing.SmoothingPanel._apply` | `SMOOTH` |
| `uvvis_peak_picking.PeakPickingPanel._apply` | `PEAK_PICK` |
| `uvvis_second_derivative.SecondDerivativePanel._apply` | `SECOND_DERIVATIVE` |

Each adds `metadata={"implementation_hash":
compute_implementation_hash(OperationType.X)}` to the
`OperationNode(...)` constructor call.

**Test coverage.**

- `test_operation_hash.TestUnregisteredSentinel` (2)
- `test_operation_hash.TestRegistration` (3)
- `test_operation_hash.TestHashDeterminism` (3)
- `test_operation_hash.TestDomainSeparation` (1)
- `test_operation_hash.TestHashCache` (1)
- `test_operation_hash.TestDefaultRegistrations` (3)
- `test_operation_hash.TestSourceHashSensitivity` (2)
- `test_nodes_metadata_field` (8 tests on the new
  OperationNode fields)
- `test_persistence_phase_a.TestApplySiteStampsImplementationHash`
  (5 — one per stamping site)
- `test_persistence_phase_a.TestImplementationMismatchSurface`
  (2 — load drift detection + clean-load no-warnings)

**Locked invariants.**

- The hash domain-separates by `OperationType.name` — two registry
  entries with the same callables but different op names produce
  different hashes.
- The registry is a single source of truth: helpers shared between
  modes (e.g. `_floor_zero` across the six BASELINE branches) MUST
  appear once in the BASELINE bundle. Adding a helper without
  registering it is the silent-drift failure mode the entry was
  raised to prevent.
- The unregistered sentinel is `"unregistered:<name>"` with the
  exact `SENTINEL_PREFIX` constant — change this and every drift
  detector breaks.

---

## CS-46 — Persistence Phase A: manifest + sidecar (Phase 4v)

**Source files.** `project_io.py` (full rewrite — replaced four
`NotImplementedError` stubs with the manifest+sidecar
implementation).

**Architecture (locked Phase 4r, shipped Phase 4v).**

- Content-addressed manifest JSON + sidecar HDF5 files.
- Sidecars carry every raw array (DataNode arrays). Sidecar
  filenames are the SHA-256 of the canonical (sorted-by-key) byte
  serialisation of the arrays dict, so two DataNodes with identical
  payloads share a single sidecar.
- Single `protected: bool` header flag gates verification on load.
  Phase A always writes `protected: false`; Phase C flips it to
  `true` once Merkle/signed verification lands.
- Whole-app save: one manifest, one set of sidecars. Top-level
  `plot_defaults` mirrors `plot_settings_dialog._USER_DEFAULTS`;
  per-tab `tabs[<name>].plot_config` carries each tab's local
  overrides; per-tab `tabs[<name>].graph` carries the full
  ProjectGraph (data nodes + op nodes + edges + active overrides).

**On-disk layout.**

```
myproject.ptmg/
+-- manifest.json
+-- sidecars/
    +-- <hash>.h5         # one HDF5 per unique arrays bundle
    +-- ...
```

**Manifest schema (top-level).**

```json
{
  "ptarmigan_format": "ptmg",
  "ptarmigan_format_version": 1,
  "ptarmigan_version": "0.X.Y",
  "python_version": "3.12.x",
  "name": "...",
  "created_at": "ISO 8601",
  "modified_at": "ISO 8601",
  "protected": false,
  "plot_defaults": { ... },
  "tabs": {
    "uvvis": {
      "plot_config": { ... },
      "graph": {
        "data_nodes": [
          {"id": "...", "type": "UVVIS", "label": "...", "state": "PROVISIONAL",
           "created_at": "...", "active": true, "style": {...}, "metadata": {...},
           "arrays_hash": "abc123..."},
          ...
        ],
        "op_nodes": [
          {"id": "...", "type": "BASELINE", "engine": "internal",
           "engine_version": "0.X.Y", "params": {...},
           "input_ids": [...], "output_ids": [...],
           "timestamp": "...", "duration_ms": 0, "status": "SUCCESS",
           "log": "", "state": "PROVISIONAL",
           "metadata": {"implementation_hash": "..."},
           "deterministic": true},
          ...
        ],
        "edges": [["parent_id", "child_id"], ...],
        "active_overrides": {"dataset_id": "override_id", ...}
      }
    }
  }
}
```

**Public API.**

```
save_project(path, *, name, plot_defaults, tabs) -> Path
load_project(path) -> LoadedProject
verify_project(path) -> {"array_warnings": [...], "implementation_warnings": [...]}

@dataclass class TabPayload:
    plot_config: dict[str, Any]
    graph: ProjectGraph

@dataclass class LoadedProject:
    name: str
    created_at: str
    modified_at: str
    ptarmigan_version: str
    plot_defaults: dict[str, Any]
    tabs: dict[str, TabPayload]
    implementation_warnings: list[str]

# Retained from pre-Phase-A project_io
hash_file(path) -> str        # SHA-256 of file contents
copy_project(src, dst) -> Path  # Save As helper
```

**Sidecar HDF5 round-trip.**

- `_hash_arrays(arrays)` — SHA-256 over a canonical encoding (per
  array, in sorted-key order, encoded as
  `"k:" + key + "\nd:" + dtype + "\ns:" + shape + "\nb:" + bytes + "\n"`).
- `_write_arrays_sidecar(path, arrays)` — `h5py.File("w")` with
  `compression="gzip"`, `compression_opts=4`. ~3-5 KB per typical
  601-sample UV/Vis absorbance pair.
- `_read_arrays_sidecar(path)` — round-trip back into a
  `dict[str, np.ndarray]`.

**Implementation hash verification at load.**

For every OperationNode whose `metadata["implementation_hash"]` is a
real hash (not the unregistered sentinel), `_deserialise_graph`
recomputes the registry hash and appends per-op drift to
`implementation_warnings`. Two distinct mismatch shapes:

- "implementation changed since save" — both sides have a real hash
  but they differ.
- "no implementation is registered in this build" — the manifest
  has a real hash but the current registry returns a sentinel.

The host (`binah.py`) wraps the warnings in a "Implementation
Changed Since Save" dialog with two buttons today: Keep cached +
Show details. Re-run all changed is deferred (see the new register
entry; needs a workflow-replay mechanism).

**Workflow restoration (`_restore_workflow_payload`).**

`UVVisTab._restore_workflow_payload(payload: TabPayload)` swaps
graph contents in place: clears the existing graph, re-adds every
node + edge from `payload.graph`, restores `_active_overrides`,
fires a single GRAPH_LOADED notification so subscribers refresh
once. Subwidgets keep their reference to `self._graph` so the
post-restore plot+sidebar refresh uses the same code path as a
normal apply.

XAS / EXAFS / TDDFT tabs do not yet ship a `_restore_workflow_payload`;
when they migrate to ProjectGraphs (Phase 5+), each gains a parallel
method (see the new register entry).

**Workflow menu wiring (binah.py).**

```
File:
  Save Workflow            (Ctrl+Alt+S)
  Save Workflow As…
  Open Workflow…           (Ctrl+Alt+O)
  Recent Workflows  >
```

These coexist with the existing TDDFT-only `.otproj` save/load
gestures (left intact per Phase A scope; unification is a future
phase). `tk.filedialog.askdirectory` picks a directory; the chosen
path gets a `.ptmg` suffix appended if absent. Recent workflows
persist to the same `~/.binah_config.json` under
`"recent_workflows"`.

**Phase A explicit deferrals (each is a new register entry).**

- `.ptmg` zip-archive form (directory only this phase).
- Original instrument file persistence (DataNode arrays round-trip;
  the source instrument file does not yet).
- Phases B (subgraph export), C (signed Merkle manifest), D
  (OpenTimestamps anchoring).
- Migration of legacy `.ptproj` / `.otproj` files (per user lock:
  "compatibility with existing project files is NOT a goal").
- Sidecar garbage collection across saves.
- Re-run all changed ops at load.

**Test coverage.**

- `test_project_io.TestEmptySaveLoad` (3)
- `test_project_io.TestRoundTrip` (4)
- `test_project_io.TestSidecarDedup` (2)
- `test_project_io.TestVerifyMismatch` (6)
- `test_project_io.TestErrorPaths` (4)
- `test_project_io.TestCreatedAtPersistsAcrossSaves` (1)
- `test_project_io.TestJsonifyHelpers` (1)
- `test_project_io.TestUnregisteredOpRoundTrip` (1)
- `test_persistence_phase_a.TestSaveLoadRoundTrip` (2)
- `test_persistence_phase_a.TestRestoreWorkflowPayload` (2)
- `test_persistence_phase_a.TestImplementationMismatchSurface` (2)

**Locked invariants.**

- `PTMG_FORMAT = "ptmg"` and `PTMG_FORMAT_VERSION = 1` constants
  pin the manifest's `ptarmigan_format` / `ptarmigan_format_version`
  keys. A future schema change bumps the version and adds
  back-compat handling.
- Sidecar filenames are exactly `<arrays_hash>.h5` (no prefix). The
  raw-instrument-file follow-up uses `raw_<file_hash>.<ext>` to keep
  the namespaces separate.
- `_hash_arrays` MUST sort keys (canonical encoding); otherwise
  insertion-order-dependent hashes break dedup.
- `LoadedProject.implementation_warnings` is exactly the list of
  drift warnings — empty list ⇒ no drift; never `None`.
- The manifest carries `protected: false` in Phase A; Phase C ships
  the verification path that flips it to `true`.

---

## CS-47 — Adjustable sidebar measurement vocabulary + dynamic label cap (Phase 4w)

**Source files.** `scan_tree_widget.py` (per-cell vocabulary, sidebar
floor, dynamic-cap helper, widest-label measurement, re-truncation
in `_apply_responsive_layout`); `uvvis_tab.py` (PanedWindow `minsize`
reads the pinned constant; `_calibrate_sidebar_width` runs once via
`after_idle`).

**Purpose.** Auto-bump the right-pane PanedWindow sash on first paint
to fit the widest current label cell, with the truncation cap
adapting to the actual sidebar width via font metrics. The user
re-flagged the manual sash drag during Phase 4v as still-broken-and-
blocking-work; CS-47 is the auto-width path and the dynamic-cap
companion. Pairs with CS-48's column-alignment work for a
cohesive sidebar visual-quality phase.

**Module-level constants (locked Phase 4w step 2).**
- `_CELL_MIN_PX: dict[str, int]` — documented per-cell minimum
  natural widths covering every cell in a sidebar row: `state` (18),
  `swatch` (24), `vis_cb` (22), `row_toggle` (22 — CS-48 slot),
  `label` (56 floor), `leg` (22), `ls_canvas` (38), `hist` (28),
  `gear` (22), `compare` (22), `commit` (22), `x` (22). Single
  source of truth; future row-cell additions list themselves here.
- `_SIDEBAR_MIN_WIDTH_PX: int = _RESPONSIVE_COLLAPSE_PX` — pinned
  floor matching the smallest threshold from CS-26's
  `_RESPONSIVE_THRESHOLDS_PX` (240). `UVVisTab` reads this when
  configuring `body.add(sidebar_pane, minsize=…)` so the responsive
  helper and the geometry manager stay in lock-step.
- `_LABEL_CHAR_FLOOR: int = 8`, `_LABEL_CHAR_CEIL: int = 64` —
  clamps for the dynamic label cap. The floor keeps at least eight
  characters visible at the narrowest realised sidebar; the ceil
  prevents a 1500-px sidebar from disabling truncation entirely.
  `_LABEL_MAX_CHARS = 32` retained as the static fallback when
  geometry / font metrics are unavailable (CS-33 invariant
  preserved).

**Pure helper.**
```
_label_char_capacity(canvas_width_px, avg_char_px, overhead_px) → int
```
Returns `clamp((canvas_width_px - overhead_px) // avg_char_px,
[_LABEL_CHAR_FLOOR, _LABEL_CHAR_CEIL])`. Falls back to
`_LABEL_MAX_CHARS` when `canvas_width_px ≤ 1` (unrealised),
`avg_char_px ≤ 0` (font metrics unavailable), or
`overhead_px ≥ canvas_width_px` (no room for the label cell).

**Widget instance methods.**
- `_label_font()` — looks up `tkfont.nametofont("TkDefaultFont")`
  (the font `_populate_node_row` constructs the label with).
  Returns `None` when the lookup fails.
- `_avg_char_px()` — measures `font.measure("ABCDEFGHIJabcdefghij") //
  20`, more representative for proportional fonts than `measure("M")`.
  Returns `0` when font metrics fail; the helper falls back.
- `_label_overhead_px()` — sum of `_CELL_MIN_PX[c]` for each
  always-visible cell (state, vis_cb, row_toggle, hist, gear,
  compare, x) + 30 px padding slack. Optional cells excluded —
  at each responsive threshold the sidebar gains roughly
  cell-width + small padding, so the label cell's share stays
  approximately constant across thresholds.
- `_current_label_cap()` — instance shortcut wrapping
  `_label_char_capacity(_scroll_canvas.winfo_width(),
  _avg_char_px(), _label_overhead_px())`.
- `widest_label_pixel_width(font=None) → int` — public method,
  walks `_candidate_nodes()` and returns
  `max(font.measure(node.label))`. Returns 0 when the candidate
  list is empty or font metrics fail. Used by
  `UVVisTab._calibrate_sidebar_width` to size the sash.

**Re-truncation on resize.** `_apply_responsive_layout` runs from
the canvas-`<Configure>` binding (CS-30) on every sash drag.
After the optional-cell reflow it now also computes
`new_cap = _current_label_cap()`, re-truncates the label widget's
text via `_truncate_label(node.label, max_chars=new_cap)`, and
rotates the always-attached label tooltip's text using its
empty-string sentinel (`Tooltip.update_text("")` makes `_show`
silently bail). No tooltip create/destroy churn; one Tooltip per
row for the lifetime of the row.

**`UVVisTab._calibrate_sidebar_width`.** One-shot, scheduled via
`self.after_idle(self._calibrate_sidebar_width)` after
`_build_chrome` completes. Idempotent — `_sidebar_calibrated: bool`
flips True after the first successful call so manual sash drags
persist across rebuilds. Computes:
```
target = clamp(
    widest_label_pixel_width() + _label_overhead_px(),
    [_SIDEBAR_MIN_WIDTH_PX, _SIDEBAR_MAX_CALIBRATED_PX = 480],
)
sash_x = max(0, paned_width - target)
body.sash_place(2, sash_x, 0)
```
Sash 2 is the rightmost (between plot pane and sidebar pane).
Bails silently when the PanedWindow's geometry isn't realised
yet (`paned.winfo_width() <= 1`), retrying via
`self.after(50, ...)` so the calibration eventually succeeds
once the tab is mapped.

**Locks.**
- `_LABEL_MAX_CHARS = 32` constant value, `_truncate_label`
  signature, and the `text[:max-1] + "…"` shape all preserved
  (CS-33 invariants).
- `_RESPONSIVE_THRESHOLDS_PX` integer values + tuple shape +
  priority order all preserved (CS-26 invariants).
- `_apply_responsive_layout(node_id, row, width=None)` signature
  preserved (CS-30 invariant).
- `_optional_row_widgets[node_id]` inner type relaxed from
  `dict[str, tk.Widget]` to `dict[str, Any]` to host the
  Tooltip handle. Pre-existing keys (swatch, leg, ls_canvas,
  vis_cb) still hold tk.Widget; `label` holds the label widget;
  `label_tooltip` holds `Tooltip | None`.

**What changes when this lock relaxes.** New row cells must list
themselves in `_CELL_MIN_PX`; new responsive-threshold tiers
must keep ascending integer order so the existing
`test_*_revealed_at_*_threshold` tests pass. Bumping
`_SIDEBAR_MIN_WIDTH_PX` higher than `_RESPONSIVE_COLLAPSE_PX`
would either widen the threshold tuple in lock-step or break
TestResponsiveCollapse — keep them equal.

**Implementation notes.**
- Calibration uses `after_idle` not synchronous because tab
  construction completes before geometry settles. Without the
  defer, `paned.winfo_width()` returns 1 every time.
- The `_SIDEBAR_MAX_CALIBRATED_PX = 480` cap is intentional: a
  60-char label at ~7 px / char + ~190 px overhead = ~610 px,
  past 480 the plot pane gets squeezed below comfort; manual
  sash-drag remains the escape valve.
- Tooltip rotation via empty-string sentinel rather than
  create/destroy: Tooltip has no `destroy()` method, only
  `update_text(...)`. `_show` bails silently on empty text.
- The dynamic label cap uses the canvas width, not the row
  width — the row's natural width is content-driven and would
  shrink-the-cap-shrinks-the-row in a feedback loop. The
  canvas width is the available sidebar space, the
  source-of-truth.

---

## CS-48 — Row-toggle column slot (Phase 4w)

**Source files.** `scan_tree_widget.py` (`_populate_node_row`
adds the always-packed `row_toggle` Frame slot; the BASELINE-only
bc_btn is parented inside it).

**Purpose.** Make the sidebar row-toggle column align across every
node type so labels start at the same x-coordinate regardless of
whether the row owns the `[~]` baseline-curve toggle. Phase 4t
friction #1 — the user-flagged misalignment that the original
proposal would have fixed by packing a disabled `state="disabled"`
Button on every row. Phase 4w design rejected the disabled-button
shape in favour of a fixed-width Frame placeholder: cheaper (no
Button + tooltip per non-BASELINE row) and avoids the "what does a
disabled `[~]` mean?" UX confusion.

**Layout contract.**
```
row_toggle = tk.Frame(row, width=_CELL_MIN_PX["row_toggle"])  # = 22
row_toggle.pack(side="left", padx=(2, 0), fill="y")
row_toggle.pack_propagate(False)  # keep width even with no children

if node.type == NodeType.BASELINE:
    bc_btn = tk.Button(row_toggle, …)  # parent is row_toggle, NOT row
    bc_btn.pack(fill="both", expand=True)
    Tooltip(bc_btn, "Show / hide baseline curve overlay")
# else: row_toggle is an empty placeholder
```

The slot is packed `fill="y"` so its height matches the row's
height regardless of children; `pack_propagate(False)` keeps the
22 px width even when the slot contains the bc_btn (whose natural
width may differ slightly).

**Locks.**
- `_CELL_MIN_PX["row_toggle"] = 22` is the slot's width. Changing
  it is a CS-47 / CS-48 joint lock (the cell vocabulary stays
  consistent).
- The slot is packed unconditionally on every row at the
  position previously occupied only by `bc_btn` on BASELINE
  rows. Changing the position would break test
  `TestRowToggleColumnAlignment.test_slots_have_identical_width_
  across_row_types`.
- CS-36's behaviour preserved verbatim: `[~]` button fires the
  same `set_style({"show_baseline_curve": …})` → graph event
  → `_redraw` chain. Only the parent widget moved.

**What changes when this lock relaxes.** Adding more row-toggle
buttons (e.g. a per-NORMALISED row "show normalisation curve"
overlay) means parenting them to the same slot — but the slot's
fixed-width contract means only one button can be visible at a
time without restructuring. A future "two-toggle row" would
require either widening the slot or stacking buttons via grid.

**Implementation notes.**
- Test helper `_bc_button_in` was updated to recurse one level
  into Frame children when looking for the bc_btn — the button
  is no longer a direct child of `row`. The recursion stops at
  the first matching Button to keep the helper cheap.
- Non-BASELINE rows pay the cost of one extra Tk widget per row
  (the placeholder Frame). At dozens of rows the cost is
  negligible; at hundreds it would still be ~22 KB of Tk
  bookkeeping — within budget.

---

## CS-49 — Cross-type panel parent acceptance widening (Phase 4x)

**Source files.** `uvvis_smoothing.py` (`SmoothingPanel.ACCEPTED_PARENT_TYPES`
gains `SECOND_DERIVATIVE`); `uvvis_tab.py` (`_BASELINE_ACCEPTED_PARENT_TYPES`
gains `SMOOTHED`; `_refresh_shared_subjects` walks both spectrum-shaped
and derivative helpers; `_second_derivative_nodes` docstring rewritten
to reflect the new contract).

**Purpose.** Close the user-flagged Phase 4w friction #1
("Cannot do baseline correction from a smoothed spectrum.
Cannot smooth derivative plots."). Both gaps were panel-side
parent-type rejection only; the math in each case is
type-agnostic — every accepted parent carries
`arrays["wavelength_nm"]` + `arrays["absorbance"]` and the
solver feeds those arrays in regardless of which op produced
them. Companion polish: surface SECOND_DERIVATIVE rows in the
shared subject combobox so the SmoothingPanel widening is
actually reachable from the UI.

**Tuple widening.**
| Tuple | Before | After |
|---|---|---|
| `UVVisTab._BASELINE_ACCEPTED_PARENT_TYPES` | `(UVVIS, BASELINE)` | `(UVVIS, BASELINE, SMOOTHED)` |
| `SmoothingPanel.ACCEPTED_PARENT_TYPES` | `(UVVIS, BASELINE, NORMALISED, SMOOTHED)` | `(UVVIS, BASELINE, NORMALISED, SMOOTHED, SECOND_DERIVATIVE)` |
| `NormalisationPanel.ACCEPTED_PARENT_TYPES` | `(UVVIS, BASELINE, NORMALISED)` | UNCHANGED (audit decision held) |
| `PeakPickingPanel.ACCEPTED_PARENT_TYPES` | `(UVVIS, BASELINE, NORMALISED, SMOOTHED)` | UNCHANGED (audit decision held) |
| `SecondDerivativePanel.ACCEPTED_PARENT_TYPES` | `(UVVIS, BASELINE, NORMALISED, SMOOTHED)` | UNCHANGED (audit decision held) |

**Audit decisions held (intentionally NOT widened).**
- **NormalisationPanel** keeps SMOOTHED + SECOND_DERIVATIVE
  excluded — existing comment documents "normalisation should
  run on raw or baseline-corrected curves, before smoothing,
  so the smooth window matches the canonical amplitude scale."
  Normalising a derivative would divide by a zero-crossing.
- **PeakPickingPanel** keeps SECOND_DERIVATIVE excluded — picking
  peaks of d²A/dλ² conflates absorbance maxima with derivative
  zero-crossings; PEAK_LIST excluded by output-shape mismatch
  (`peak_wavelengths_nm` / `peak_absorbances` vs the curve
  schema).
- **SecondDerivativePanel** keeps SECOND_DERIVATIVE itself
  excluded — chained derivatives rarely useful + amplifies
  noise. PEAK_LIST excluded by shape.

Each unchanged tuple's `test_accepted_parent_types_constant`
gained an audit-time comment block + remains a hard pin so a
future widening must update the rationale comment in
lock-step.

**Combobox surfacing.** `_refresh_shared_subjects` now walks
`_spectrum_nodes() + _second_derivative_nodes()` (in that
order: spectrum nodes first, derivatives appended). Order
pinned by `test_shared_combobox_orders_spectrum_then_derivative`
in the new `TestUVVisTabPhase4xCrossTypeAcceptance` class.

`_spectrum_nodes` itself is **not** touched. The renderer
(`_redraw`) iterates the two helpers separately because
`_DEFAULT_Y_AXIS_BY_NODETYPE[SECOND_DERIVATIVE] == "secondary"`
under CS-44; concatenating them into `_spectrum_nodes` would
double-render every derivative.

The `_second_derivative_nodes` docstring was rewritten:
the historical "panels do not surface SECOND_DERIVATIVE"
rationale (true pre-Phase 4x) is preserved as a history note
alongside the still-true "renderer-side double-iteration
avoidance" reason.

**Decision lock taken (Phase 4x step 2).**
- (i) **Explicit type-list gate kept.** Rejected the looser
  "any DataNode with `arrays['wavelength_nm']` +
  `arrays['absorbance']`" alternative — explicit lists let
  each panel encode deliberate exclusions (NormalisationPanel's
  "before smoothing" rationale stays expressible; future
  per-type behavioural exclusions stay possible).
- (ii) **y-axis routing of cross-typed outputs deferred to
  CS-44 by-NodeType routing.** Smoothed-of-derivative output
  carries `NodeType.SMOOTHED` → routes to "primary" axis
  (visually misleading for d²A values); the fix lives in the
  open Phase 4u friction #10 / per-style `y_axis` override
  hook (carry-forward T), not in this phase. CS-49 adds no
  parent-aware routing logic.
- (iii) **Audit pass concluded with two widenings + three
  held decisions** (per the table above).

**Locks.**
- `_BASELINE_ACCEPTED_PARENT_TYPES` shape now `(UVVIS,
  BASELINE, SMOOTHED)` — adding NORMALISED would re-shift the
  amplitude scale on a normalised parent; deferred until the
  user requests it.
- `SmoothingPanel.ACCEPTED_PARENT_TYPES` includes
  SECOND_DERIVATIVE; PEAK_LIST stays excluded (incompatible
  array shape).
- The three audit-held tuples (`NormalisationPanel`,
  `PeakPickingPanel`, `SecondDerivativePanel`) are pinned by
  their `test_accepted_parent_types_constant` and the
  rationale comments — both must move in lock-step on a
  future widening.
- `_refresh_shared_subjects` walks `_spectrum_nodes +
  _second_derivative_nodes` in that order. Both
  `test_second_derivative_appears_in_shared_subject_list` and
  `test_shared_combobox_orders_spectrum_then_derivative` pin
  the contract.
- The `compute_baseline_curve` helper is type-agnostic and
  unchanged; it walks `parent.absorbance - child.absorbance`
  without inspecting NodeType. CS-49 only made a SMOOTHED
  parent newly reachable; the helper handles it transparently
  (pinned by
  `test_baseline_dashed_overlay_recovers_baseline_curve_from_smoothed_parent`).

**What changes when this lock relaxes.** A future widening of
NormalisationPanel / PeakPickingPanel / SecondDerivativePanel
must (a) update both the constant and the rationale comment
on the panel, (b) update the audit-stability test, and (c)
likely add a new positive-flow test in
`TestUVVisTabPhase4xCrossTypeAcceptance` documenting the new
allowed combination. Adding a panel that accepts PEAK_LIST as
a parent would also need a new render-helper iteration, since
PEAK_LIST has the `peak_wavelengths_nm` / `peak_absorbances`
schema that isn't in the curve helper.

**Implementation notes.**
- The defence-in-depth check inside each panel's `_apply`
  (e.g. `if parent_node.type not in self.ACCEPTED_PARENT_TYPES:`)
  automatically widens with the constant — no additional
  code changes needed in the apply paths.
- Three pre-existing contract tests in `test_uvvis_tab.py`
  were rewritten to invert the old "SECOND_DERIVATIVE not in
  combobox" assertions (the old contract was deliberately
  pessimistic; CS-49 makes it permissive). Renames:
  `test_second_derivative_does_not_appear_in_shared_subject_list`
  → `test_second_derivative_appears_in_shared_subject_list`;
  `test_second_derivative_node_does_not_appear_in_shared_combobox`
  → `test_second_derivative_node_appears_in_shared_combobox`;
  `test_smoothed_subject_disables_normalise_and_baseline_apply`
  → `test_smoothed_subject_disables_normalise_only` (split:
  baseline now ENABLES on SMOOTHED, normalise still
  disables).
- `_BASELINE_ACCEPTED_PARENT_TYPES` is the only acceptance
  tuple still living on `UVVisTab` rather than its panel —
  the inline baseline section was never extracted into a
  `BaselinePanel` widget. Phase 4k friction #6 documents this
  drift; Phase 4x reinforces it but doesn't fix it (cheap-
  correct in-place widening). Resolution belongs to whichever
  phase extracts the inline section.

---

## CS-50 — Per-style `y_axis` override hook (Phase 4y)

**Source files.** `node_styles.py` (`default_spectrum_style` adds the
new key); `uvvis_tab.py` (`_resolve_y_axis_role` signature widens;
three call sites in `_redraw` thread `node.style`;
`_on_uvvis_apply_to_all` special-cases the key);
`style_dialog.py` (universal-section Combobox row +
`_Y_AXIS_OPTIONS` / round-trip helpers + `_UNIVERSAL_DEFAULTS`
update); `uvvis_smoothing.py` (cross-typed-Apply inheritance
block in `SmoothingPanel._apply`).

**Purpose.** Close the carry-forward T from Phase 4u Decision 1
(USER-LOCKED "Default only for now is okay"; the deferral was
the canonical Phase 4u friction #10 register entry) and Phase 4x
friction #6 (smoothed-of-derivative misroute, USER-NOTED) in
one phase. CS-44's per-NodeType routing table covers the
typical case but cannot express "send THIS specific node to a
non-default axis" — for example a small-magnitude
SECOND_DERIVATIVE that shares the parent's amplitude scale
should land on primary, not secondary. CS-50 adds the per-node
override on top of CS-44 without changing any of CS-44's locked
constants.

**Style key.** `style["y_axis"]: str | None`. Default `None`
means "follow my NodeType default in
``_DEFAULT_Y_AXIS_BY_NODETYPE``." A non-`None` value (one of
`_AXIS_ROLES = ("primary", "secondary", "tertiary")`) overrides
the routing per-node. The key was anticipated in CS-44's
docstring; Phase 4y ships it. ``DEFAULT_SPECTRUM_STYLE_KEYS``
widens in lockstep so callers asserting against the schema pin
catch the addition. Persistence (CS-46) auto-rides — the key
sits in the existing style-dict round-trip; no manifest schema
change needed.

**Helper signature (additive widening).**

`_resolve_y_axis_role(node_type: NodeType, style: Mapping |
None = None) -> str`. The `style` parameter is optional and
defaults to `None` so every pre-CS-50 caller (overlay-axis
resolvers that pass only a NodeType) keeps byte-identical
behaviour. Resolution order:

1. **Per-style override.** If `style is not None` and
   `style.get("y_axis")` is one of `_AXIS_ROLES`, return it.
2. **Per-NodeType default.** Look up
   `_DEFAULT_Y_AXIS_BY_NODETYPE.get(node_type, "primary")`.

Malformed override values (non-string, unknown string, empty
string, missing key) fall through to the table — the helper
never returns a value outside `_AXIS_ROLES`.

**Renderer threading.** Three call sites in `_redraw` thread
the per-node style:

- **Per-node main loop:** `_resolve_y_axis_role(node.type,
  node.style)`. Default-`None` style preserves pre-CS-50
  routing.
- **BASELINE-curve dashed overlay (CS-29):** the resolver call
  moved INSIDE the per-bn loop body, parameterised by
  `(bn.type, bn.style)`. Without this move a BASELINE node
  with a non-default `y_axis` override would render its main
  curve on the override axis but its dashed overlay on the
  default — visually broken.
- **PEAK_LIST scatter loop (CS-19):** the resolver call moved
  INSIDE the per-peak-node loop, parameterised by
  `(peak_node.type, peak_node.style)`. Same reason.

The `_axes_by_role` lazy creation closure `get_axis(role)`
remains unchanged — only its callers' arguments grew.

**StyleDialog Combobox row.** A new row in the universal
section, between "In legend" and the bottom button row. Layout
mirrors the surrounding 4-column grid (label · control · spacer
· ∀). `ttk.Combobox` with `state="readonly"` so the user cannot
type a malformed role; `<<ComboboxSelected>>` fires the write.
Options:

```
("(default)", "primary", "secondary", "tertiary")
```

with two pure-helper round-trip translators:

- `_y_axis_display_to_value(display: str) -> str | None` —
  "(default)" → `None`; valid role → role; anything else → `None`
  (defensive: a malformed Combobox state never lands a bogus
  role string in a graph node).
- `_y_axis_value_to_display(value: str | None) -> str` —
  symmetrical.

`_UNIVERSAL_DEFAULTS["y_axis"] = None` keeps the section
fallback in sync with `node_styles.default_spectrum_style`.
`_read_universal_values` includes `"y_axis"` so Apply / Save
round-trip the override; Cancel reverts to the snapshot.

**Decision lock taken (Phase 4y step 2).**

- (i) **Cross-typed Apply auto-inherits y_axis IFF defaults
  differ.** When a panel `_apply` would create an output whose
  NodeType-default differs from the parent's *effective*
  y_axis (post-override), the new node's `style["y_axis"]` is
  set to the parent's effective role. Else it is left `None`.
  Today this fires only inside `SmoothingPanel._apply` (the
  only widened cross-type panel under CS-49); a SMOOTHED
  output of a SECOND_DERIVATIVE parent ends up with
  `style["y_axis"] = "secondary"`. Closes Phase 4x friction #6.
- (ii) **`(default)` Combobox label = literal `None`.** Selecting
  "(default)" writes `None` ("follow my NodeType default").
  Inheritance from parent (Decision (i)) is a separate apply-
  time mechanism that writes a literal role string into style.
  The two are orthogonal.
- (iii) **`y_axis` excluded from `_BULK_UNIVERSAL_KEYS`.**
  Bottom ∀ Apply-to-All does not fan it (parallel to Phase 4d's
  `visible` / `in_legend` carve-out — collapsing every
  derivative onto primary in one click is a footgun). Per-row
  ∀ button writes the chosen role to **every renderable node**
  (UVVIS / BASELINE / NORMALISED / SMOOTHED / SECOND_DERIVATIVE
  / PEAK_LIST), implemented by special-casing `param ==
  "y_axis"` in `UVVisTab._on_uvvis_apply_to_all` to walk the
  union; other keys preserve the existing `_spectrum_nodes()`
  scope so a linewidth ∀ does not silently rewrite annotation
  overlays.

**Test coverage.**

- `test_node_styles.TestDefaultSpectrumStyle` — 2 new tests
  (`test_y_axis_default_is_none`,
  `test_y_axis_key_is_in_default_keys_tuple`); the existing
  `test_factory_defaults_are_stable` asserts the new
  `style["y_axis"] is None` default.
- `test_uvvis_tab.TestResolveYAxisRoleStyleOverride` — 7 pure
  tests covering the override short-circuit (string role beats
  default, tertiary reachable, derivative-to-primary, None
  fall-through, missing-key fall-through, malformed value
  fall-through, signature backwards compatibility).
- `test_style_dialog.TestStyleDialogYAxisOverride` — 16
  integration tests covering Combobox initial state, write-
  through, Apply / Save / Cancel round-trip, per-row ∀ delegate,
  external sync, bulk-fan-out exclusion, module-level defaults,
  the option-list ↔ `_AXIS_ROLES` drift guard, and the round-
  trip helpers' total-domain behaviour.
- `test_uvvis_tab.TestUVVisTabPhase4yYAxisOverride` — 4
  integration tests covering UVVIS-on-secondary,
  default-preserves-pre-CS-50,
  SECOND_DERIVATIVE-back-to-primary, BASELINE-overlay-follows-
  override.
- `test_uvvis_tab.TestUVVisTabPhase4yCrossTypedInheritance` — 3
  integration tests covering the auto-inheritance fire-when-
  defaults-differ rule, the same-default no-fire rule, and the
  parent's *effective* role (not just NodeType default) driving
  the decision.
- `test_uvvis_tab.TestUVVisTabPhase4yApplyToAllScope` — 3
  integration tests covering the y_axis-fans-to-derivative,
  y_axis-fans-to-peak-list, and other-keys-preserve-spectrum-
  only-scope rules.

**Locked invariants.**

- `_resolve_y_axis_role` signature is `(node_type: NodeType,
  style: Mapping | None = None) -> str`. The `style=None`
  default keeps pre-CS-50 callers byte-identical. Removing the
  parameter or making it required would break the overlay
  call sites that pass only a NodeType.
- `style["y_axis"]: None` (default) MUST preserve pre-CS-50
  routing exactly — pinned by
  `test_uvvis_with_default_renders_on_primary_unchanged`.
- `_Y_AXIS_OPTIONS` shape MUST equal
  `("(default)",) + _AXIS_ROLES` — pinned by
  `test_y_axis_options_match_axis_roles`. If `_AXIS_ROLES` ever
  grows or shrinks, the Combobox option list must move in
  lockstep.
- `_BULK_UNIVERSAL_KEYS` MUST NOT include `y_axis` — pinned by
  `test_bulk_universal_keys_excludes_y_axis`. Decision (iii)
  is durable; widening it would land in a fresh phase.
- `_on_uvvis_apply_to_all` MUST widen its scope when `param ==
  "y_axis"` — pinned by `test_y_axis_fans_out_to_second_derivative_too`
  and `test_y_axis_fans_out_to_peak_list_too`.
- The `SmoothingPanel._apply` inheritance block MUST set
  `style["y_axis"]` IFF the parent's effective role differs
  from `_DEFAULT_Y_AXIS_BY_NODETYPE[NodeType.SMOOTHED]` —
  pinned by the three
  `TestUVVisTabPhase4yCrossTypedInheritance` tests.

**What changes when this lock relaxes.** The CS-50 lock relaxes
when (a) a second cross-typed-Apply panel lands (NormalisationPanel
on SECOND_DERIVATIVE; SecondDerivativePanel on a non-spectrum
NodeType; etc.) — at that point the inheritance block in
`SmoothingPanel._apply` should be promoted into a shared helper
in `node_styles.py` (open carry-forward register entry from
Phase 4y); (b) the multi-axis routing lifts to `plot_widget.py`
(open carry-forward) — at that point the `y_axis` Combobox row
in the StyleDialog universal section becomes meaningful for
every tab, closing the open Phase 4y friction #1
("Y-axis Combobox row appears on non-UVVis StyleDialog
instances"); (c) `_NON_PRIMARY_Y_LABEL` widens to cover non-
default routings (open Phase 4y register entry on the per-
NodeType primary y-label gap).

**Implementation notes.**

- The local `from uvvis_tab import _resolve_y_axis_role,
  _DEFAULT_Y_AXIS_BY_NODETYPE` inside `SmoothingPanel._apply`
  is intentional: `uvvis_tab` imports `uvvis_smoothing` at
  module load (`import uvvis_smoothing`), so a top-level
  reverse import would create a cycle. The deferred import
  fires only at button-click time — well after module loading.
- The CS-44 docstring's anticipated signature widening
  ("`(node_type, style: Mapping | None = None) -> str` —
  additive only") is now realised. The CS-44 lock note that
  "the future per-style override could surface a malformed
  value" is honoured by the helper itself rejecting malformed
  values rather than echoing them; the `get_axis` defensive
  fallback for unknown roles also remains in place as a
  belt-and-braces second guard.
- Phase 4u friction #9 (`_absorbance_to_y` corrupts d²A on
  %T) is now newly reachable from the UI: pre-CS-50 a user had
  to hand-edit a project file's style dict to land a
  SECOND_DERIVATIVE on primary; post-CS-50 the StyleDialog
  Combobox makes it a single click. The bug is documented in
  Phase 4u friction #9; Phase 4y added a priority-bump note
  inline.

---

## CS-51 — Width-aware label-cell overhead helper (Phase 4z)

**Source files.** `scan_tree_widget.py` (two new pure module-level
helpers, lifted constants, width-kwarg on the `_label_overhead_px`
instance method, one-line wire change in `_current_label_cap`).

**Purpose.** Close Phase 4x friction #1 (USER-FLAGGED): at the
swatch reveal threshold (240 px) the swatch column reappears per
CS-26's `_RESPONSIVE_THRESHOLDS_PX`, but Phase 4w's
`_label_overhead_px` was a static estimate that didn't account for
the swatch's 24 px width. The dynamic label cap stayed sized for
the swatch-absent state, the label widget refused to shrink, and
the right-side cells (incl. the `✕`) fell off the row's right
edge — the user could no longer remove a node that just gained a
colour swatch. Closes Phase 4w friction #6 (measure actual row
overhead) for the optional-cell visibility axis (the dominant
source of overhead drift).

**Module-level constants (locked Phase 4z step 2).**
- `_ALWAYS_VISIBLE_CELLS: tuple[str, ...]` — `("state", "vis_cb",
  "row_toggle", "hist", "gear", "compare", "x")`. Lifted from the
  Phase 4w `_label_overhead_px` body so the pure helpers below
  can share it. Order is informative only; the sum is order-
  independent. Pinned by
  `test_always_visible_cells_match_phase_4w_set` so a future cell
  promotion is intentional and forces a CS-26 audit.
- `_OVERHEAD_SLACK_PX: int = 30` — per-row pixel slack added on
  top of the per-cell minimums, covering inter-cell padding
  (`pack(padx=2)` etc.). Lifted from the Phase 4w `+ 30` literal.
  Pinned by `test_baseline_decomposition_matches_cell_vocabulary`
  so the no-args overhead path stays byte-equivalent to Phase 4w
  (186 px = sum of the seven always-visible cell mins + 30).

**Pure helpers.**
```
_compute_label_overhead_px(visible_optional_cells: Iterable[str] = ()) -> int
_visible_optional_cells_for_width(width_px: int) -> tuple[str, ...]
```

`_compute_label_overhead_px` returns
`sum(_CELL_MIN_PX[c] for c in _ALWAYS_VISIBLE_CELLS) +
sum(_CELL_MIN_PX[c] for c in visible_optional_cells) +
_OVERHEAD_SLACK_PX`. No-args path returns 186 px (byte-equivalent
to Phase 4w). Unknown cell names raise `KeyError` so call-site
typos fail loudly.

`_visible_optional_cells_for_width` walks
`_RESPONSIVE_THRESHOLDS_PX` (ascending by threshold by
construction) and returns the cell names whose thresholds are
`<= width_px`. Mirrors `_apply_responsive_layout`'s reveal
predicate exactly (`want_<cell> = width >= thresholds[<cell>]`),
so the label cap and the optional-cell layout cannot drift —
pinned by
`test_helper_matches_apply_responsive_layout_reveal_predicate`.

**Widget instance method.** `_label_overhead_px(self, width:
int | None = None) -> int` — the Phase 4w method gains a `width`
kwarg. When `width` is given, the method returns
`_compute_label_overhead_px(_visible_optional_cells_for_width(width))`,
i.e. always-visible plus the optional cells revealed at that
width. When `width` is `None`, the method returns
`_compute_label_overhead_px()` — the no-args baseline, byte-
equivalent to Phase 4w. The signature change is the CS-47 lock
relaxation specifically scoped for this intent.

**Wire change.** `_current_label_cap` reads the canvas width via
`self._scroll_canvas.winfo_width()` (unchanged from Phase 4w) and
now forwards it as `self._label_overhead_px(width=canvas_width)`
into the cap calculation. The dynamic label cap therefore shrinks
the moment any optional cell reappears at its CS-26 threshold —
the per-row overhead the cap divides by grows by exactly the
revealed cell's `_CELL_MIN_PX` contribution, and the available-
pixel budget for the label cell drops accordingly.

**`_calibrate_sidebar_width` is unchanged.** The one-shot sash
calibration still calls `self._label_overhead_px()` with no
args, so its target width is byte-equivalent to Phase 4w. Phase
4z friction #1 (Claude-surfaced) flags this as a future
opportunity — the calibration target may undershoot by up to
84 px (the sum of all three optional cell mins) — but the
`_SIDEBAR_MAX_CALIBRATED_PX = 480` cap usually swallows the
shortfall, so it's a deferred polish.

**Locks.**
- `_ALWAYS_VISIBLE_CELLS` content. Adding or removing an entry
  requires a CS-26 threshold audit (the optional-cell threshold
  set assumes which cells are always-visible). Pinned by
  `test_always_visible_cells_match_phase_4w_set`.
- `_OVERHEAD_SLACK_PX = 30` integer value. Phase 4w byte-
  equivalence depends on this constant matching the Phase 4w
  `+ 30` literal. Pinned by
  `test_baseline_decomposition_matches_cell_vocabulary`.
- `_compute_label_overhead_px` and `_visible_optional_cells_for_width`
  signatures. The width-aware path of `_label_overhead_px`
  delegates directly to these; signature change requires
  updating the delegation.
- `_label_overhead_px(self, width: int | None = None)` signature.
  The `width=None` default is byte-required by
  `_calibrate_sidebar_width`'s no-args call. The two existing
  Phase 4w call sites (`_calibrate_sidebar_width` no-args,
  `_current_label_cap` width-forward) are pinned by their
  respective integration tests.
- `_RESPONSIVE_THRESHOLDS_PX` integer values + tuple shape +
  priority order all preserved (CS-26 invariants —
  `_visible_optional_cells_for_width` reads them, never
  modifies).
- `_label_char_capacity` signature, `_LABEL_MAX_CHARS = 32`
  fallback, `_LABEL_CHAR_FLOOR = 8` / `_LABEL_CHAR_CEIL = 64`
  clamps all preserved (CS-47 invariants).

**What changes when this lock relaxes.** Tightening
`_OVERHEAD_SLACK_PX` to a measured value (Phase 4z friction #3)
will require a one-line constant change + update to the
byte-equivalence test's expected baseline. Adding a fourth
optional cell to `_RESPONSIVE_THRESHOLDS_PX` automatically widens
`_visible_optional_cells_for_width`'s return tuple — no helper
change needed, but the new threshold value should follow the
ascending-order convention.

**Implementation notes.**
- The pure-helper / instance-method split mirrors Phase 4w's
  `_label_char_capacity` pure helper + `_current_label_cap`
  instance shortcut split — the helpers don't touch any widget
  state and can be tested without a Tk root (19 of the 24 new
  tests are pure).
- Architecture (a) was chosen over (c) (post-pack
  `winfo_reqwidth()` measurement) because (a) computes overhead
  from the same `_CELL_MIN_PX` source of truth that drives
  `_RESPONSIVE_THRESHOLDS_PX`, eliminating drift between the cap
  and the reveal predicate by construction. (c) would have
  required a packed row to measure, which the cap helper runs
  before the row is necessarily realised in geometry.
- Architecture (b) (bump the swatch reveal threshold higher) was
  rejected: it would have changed CS-26's locked threshold
  values, regressing the existing
  `test_swatch_revealed_first_at_smallest_threshold` /
  `test_leg_revealed_at_middle_threshold` /
  `test_ls_canvas_revealed_at_largest_threshold` invariants and
  pushing the optional cells out further than user manual sash-
  drag testing has validated.
- Below the smallest reveal threshold (239 px) and at very narrow
  thresholds (240 px specifically), `_label_char_capacity`
  clamps the cap to `_LABEL_CHAR_FLOOR = 8`. The bug fix is
  effective (the right-side cells no longer get clipped because
  the cap calculation correctly accounts for the swatch's
  overhead in the dynamic path) but the *visible* label-
  truncation cue between 239 and 240 px is masked by the floor
  — see Phase 4z friction #2.

---

## CS-52 — StyleDialog y-axis visibility predicate + label-rename Entry (Phase 4aa)

**Source files.** `style_dialog.py` (one new module-private
constant, one gated call site, one new universal-section row, two
new helpers, one new graph-event branch).

**Purpose.** Two visible deliverables that share the StyleDialog
universal section:

1. **Y-axis Combobox visibility predicate** — closes Phase 4y
   friction #1 (Claude-surfaced). The CS-50 "Y axis:" Combobox
   row landed in the *universal* section so it appeared for every
   NodeType. Only `uvvis_tab._redraw` reads the override through
   `_resolve_y_axis_role`, so on TDDFT / FEFF_PATHS / XANES /
   EXAFS / DEGLITCHED / AVERAGED / BXAS_RESULT the Combobox was a
   misleading affordance — changing it persisted `style["y_axis"]`
   harmlessly but the user's tab's renderer never consulted the
   key. CS-52 wraps the row builder in a NodeType visibility
   predicate so the affordance only renders where it functions.
2. **Label-rename Entry** — closes the "first concrete add" half
   of Phase 4x friction #2 (USER-FLAGGED). Today the only path to
   rename a node lives in the sidebar's CS-33 `_begin_label_edit`
   double-click. CS-52 surfaces the rename gesture inside the
   gear-icon dialog so the user can mutate every node-table
   parameter from one place. The "tighten organisation for
   scale" half (LabelFrame groupings, tabbed shape) is deferred —
   see the Phase 4aa friction section's #1.

**Module-level constant (locked Phase 4aa step 2).**
- `_Y_AXIS_VISIBLE_NODETYPES: frozenset[NodeType]` — pinned to
  `frozenset({UVVIS, BASELINE, NORMALISED, SMOOTHED, PEAK_LIST,
  SECOND_DERIVATIVE})`. The drift test
  `test_y_axis_visible_node_types_match_routing_table` pins it
  against `uvvis_tab._DEFAULT_Y_AXIS_BY_NODETYPE.keys()` exactly,
  so a future widening of the routing table forces the StyleDialog
  Combobox to surface for the new NodeType (and a future shrinking
  suppresses it).

**Wire change — y-axis row gate.** The `_build_universal_section`
call site that builds the Combobox now reads:
```
if self._node_type in _Y_AXIS_VISIBLE_NODETYPES:
    self._build_y_axis_row(sec, row)
    row += 1
```
When the gate is False, no Combobox is constructed,
`_control_vars` does not gain a `y_axis` key, and
`_read_universal_values` skips `y_axis` automatically (the
existing `var = self._control_vars.get(key); if var is None:
continue` pattern). Save / Apply / per-row ∀ / bottom ∀ Apply-to-
All paths all stay self-consistent without further changes.

**New universal-section row — "Label:" Entry.** Built by the new
`_build_label_row` method, inserted at the **top** of the
universal grid (row 0; existing rows shift down by 1 grid row,
relative order preserved per the lock-relaxation reading "rows +
their order stay verbatim"). The Entry binds to a `tk.StringVar`
master-bound to the dialog (Phase 4j friction #1 defence-in-depth)
whose `trace_add('write')` callback commits each keystroke through
the new `_write_label_partial` helper. The label row carries no
∀ button — fanning one label across siblings would collapse them
onto a single display name (parallel to but stronger than the
y-axis bottom-button carve-out).

**New helper — `_write_label_partial(new_label: str) -> None`.**
Companion to `_write_partial`, but routes via `graph.set_label`
(label is a top-level `DataNode` slot, not a style key — does NOT
travel through `set_style`). Shares the `_suspend_writes`
re-entrancy guard with `_write_partial` so a label keystroke and
a style write cannot loop into each other. `set_label` is a no-op
when the value already matches (`graph.set_label`'s early return),
so idempotent refreshes don't fire spurious events.

**Snapshot extension.** `__init__` now snapshots both
`node.style` (`self._snapshot`) and `node.label`
(`self._snapshot_label`). `_do_cancel` re-emits the snapshot
label first (via `_write_label_partial`) and then the snapshot
style (via `_write_partial`) so a mid-session rename reverts in
the same gesture as a mid-session style change.

**Graph-event branch — `NODE_LABEL_CHANGED`.** `_on_graph_event`
gains a second event-type branch alongside the existing
`NODE_STYLE_CHANGED` path. When a sibling rename gesture (the
sidebar's CS-33 `_begin_label_edit`, the rename context-menu
entry, or another open StyleDialog on the same node) fires
`NODE_LABEL_CHANGED`, the dialog's `_refresh_label` helper:
1. Pushes the new label into the Entry's `StringVar` via the
   `label` refresh closure (under `_suspend_writes=True` so the
   refresh cannot loop through `set_label`).
2. Updates the dialog title via `self.title(f"Style — {new_label}")`
   so the "Style — <label>" header stays truthful mid-session.

**Locks.**
- `_Y_AXIS_VISIBLE_NODETYPES` content — frozenset value pinned by
  `test_y_axis_visible_node_types_match_routing_table`. Adding or
  removing a NodeType requires a corresponding routing-table edit
  in the same commit; the drift test makes a one-sided change
  fail.
- `_Y_AXIS_VISIBLE_NODETYPES` type — frozenset (vs set / tuple /
  list) pinned by `test_y_axis_visible_node_types_is_frozen`.
- `_build_y_axis_row` call site — `if self._node_type in
  _Y_AXIS_VISIBLE_NODETYPES:` predicate. Pinned by the
  `TestStyleDialogYAxisVisibility` matrix (six routing-NodeType
  "present" cases + seven non-routing "absent" cases).
- `_build_label_row` placement at the top of the universal grid
  (row 0). Pinned indirectly by the lock-relaxation reading "rows
  + their order stay verbatim" — the tests don't pin row indices,
  but moving "Label:" elsewhere would require a deliberate
  decision to break the universal section's relative ordering
  invariant established in Phase 4d / 4y.
- `_write_label_partial` signature `(self, new_label: str) ->
  None`. The integration test
  `test_external_rename_refreshes_entry` pins the
  re-entrancy-guard contract (no recursive `set_label` invocation
  during refresh).
- `_snapshot_label: str` field exists on every constructed
  StyleDialog. Pinned by `test_cancel_restores_snapshot_label`.
- `_on_graph_event`'s two-branch structure — `NODE_STYLE_CHANGED`
  routes to `_refresh_widgets`; `NODE_LABEL_CHANGED` routes to
  `_refresh_label`. Pinned by
  `test_external_rename_refreshes_entry` and
  `test_external_rename_updates_title`.

**What changes when this lock relaxes.** Adding a new universal-
section row that needs a NodeType-aware visibility gate follows
the same pattern: declare a `_<ROW>_VISIBLE_NODETYPES` frozenset
near the top, pin it with a drift test if it must mirror an
existing routing/registry table, and gate the row builder's call
site. The "tighten organisation for scale" follow-up (Phase 4aa
friction #1) will at minimum group the universal rows under
`tk.LabelFrame` widgets — that re-org touches every existing row's
parent argument but should preserve the gate predicate
unchanged. If the dialog grows a `ttk.Notebook` shape (the open
lock decision (i) on Phase 4x friction #2's canonical register
entry), the universal rows move into Tab 1 "Style" and the
Combobox gate moves with them; the predicate signature does not
change.

**Implementation notes.**
- The label-rename Entry uses live-write semantics (every
  keystroke commits) to match the slider/Combobox convention used
  by every other universal row and to avoid the "type a label,
  forget to press Enter, close the dialog, no save" footgun. The
  CS-33 sidebar gesture commits on Enter / FocusOut instead;
  consistency between the two rename paths is at the
  routes-through-`graph.set_label`-with-no-validation layer, not
  at the keystroke-vs-Enter trigger layer. See Phase 4aa friction
  #2 for revisit triggers.
- The label row is unconditional (it appears on every NodeType
  the dialog accepts), unlike the gated y-axis row. Every
  `DataNode` carries a `label` slot, so the rename gesture is
  meaningful for every NodeType — there is no "this NodeType
  doesn't display labels" case the way there is for y-axis
  routing.
- Validation on the Entry is intentionally absent (lock decision
  (ii) taken Phase 4aa step 2). Empty strings and duplicate
  labels are accepted — `graph.set_label` itself enforces
  nothing, and matching that behaviour keeps the dialog Entry and
  the sidebar gesture consistent. A future "tighten
  organisation" pass could surface a non-blocking warning
  (duplicate-label cross-fade or similar) without changing the
  underlying `set_label` contract.
- Cancel always re-emits the snapshot label, even when the user
  never renamed — `set_label` early-returns when old == new so
  the call is a no-op, but it costs a function dispatch. See
  Phase 4aa friction #6 for the cosmetic gate-by-inequality
  follow-up.

---

## CS-53 — StyleDialog Notebook restructure + Provenance tab (Phase 4ab)

**Source files.** `style_dialog.py` (one module-level frozenset of
graph-event types, one constants tuple for tab titles, one new
state-display dict, three new pure helpers, one restructured body
builder, one new tab builder, one new render helper, one new
refresh method, one extended graph-event handler).

**Purpose.** Two visible deliverables that share the StyleDialog
shell and close the user-flagged Phase 4x friction #3 in full plus
the "tabbed shape" lock decision (i) of Phase 4x friction #2:

1. **`ttk.Notebook` body** — closes the Phase 4x friction #2 lock
   decision (i). The single-pane vs tabbed-shape question has been
   open since Phase 4aa shipped the label-rename Entry; CS-53
   commits to **tabbed**. Tab 1 "Style" hosts the existing
   universal + conditional sections verbatim (rows + relative
   ordering preserved per the CS-52 lock relaxation; only the
   parent widget changed). Tab 2 "Provenance" is the read-only
   ancestor walk. The bottom Apply / ∀ / Save / Cancel row stays
   outside the Notebook so it's visible regardless of which tab is
   active. Phase 4x friction #2's "tighten organisation for scale"
   half (LabelFrame groupings) stays carry-forward — it's
   independent of the Notebook restructure and pairs naturally
   with future per-type sections.
2. **Provenance tab** — closes Phase 4x friction #3 (USER-FLAGGED)
   in full. The right-sidebar's per-row history dropdown (the `▿`
   chevron) is intentionally compact; CS-53 surfaces a more
   detailed view inside the gear-icon dialog: ancestor walk back
   to the RAW_FILE / multi-input source, pretty-printed op params,
   engine + version, implementation hash (CS-45 with sentinel
   marker preserved through truncation), state badge with
   per-state foreground colour. Read-only this phase — the "Add to
   graph" gesture (Phase 4x friction #4) is a separate register
   entry that depends on this one.

**Module-level constants (locked Phase 4ab step 2).**
- `_NOTEBOOK_TAB_TITLES: tuple[str, ...] = ("Style", "Provenance")`.
  Tab order is Style first (default-active on dialog open,
  preserves the pre-CS-53 UX) and Provenance second. Reordering
  would change the default tab on dialog open. Pinned by
  `test_notebook_tab_titles_shape` + `test_notebook_tab_titles_is_tuple`.
- `_PROVENANCE_STATE_DISPLAY: dict[NodeState, tuple[str, str]]`.
  Maps each NodeState to `(display_text, foreground_colour)` —
  PROVISIONAL `("provisional", "#444444")`, COMMITTED
  `("committed", "#004400")`, DISCARDED `("discarded", "#888888")`.
  DISCARDED renders dimmed grey per Phase 4ab Decision (iv); the
  table covers every NodeState variant (pinned by
  `test_state_display_table_covers_every_state` so adding a new
  state forces a matching display entry).
- `_PROVENANCE_REFRESHING_EVENTS: frozenset` — the five graph
  event types that mutate the displayed ancestor walk
  (`NODE_LABEL_CHANGED`, `NODE_DISCARDED`, `NODE_COMMITTED`,
  `NODE_ADDED`, `EDGE_ADDED`). Membership pinned by
  `test_provenance_refreshing_events_membership` so a future
  expansion (e.g. the dialog grows to display style on ancestors)
  must explicitly grow the set rather than silently widening
  through `_on_graph_event`.

**Pure helpers (Tk-free, fully unit-tested).**
- `_provenance_state_display(state) -> (display_text, fg_colour)` —
  defensive wrapper around `_PROVENANCE_STATE_DISPLAY`. Falls
  back to `(state.name.lower(), "#444444")` for any state the
  table does not know about (forward-compat against future
  NodeState variants).
- `_format_provenance_op_params(params) -> str` — sorted-by-key
  multi-line `key: repr(value)` pretty-printer. Empty / None
  returns blank string so the caller can render an "(no params)"
  placeholder. Stable output across runs (sorted keys) makes both
  the test pin and reproducible screenshots trivial.
- `_format_provenance_node_summary(node) -> dict[str, str]` —
  reduces a DataNode or OperationNode to a flat dict of display
  strings. Op-node summaries fold `params["mode"]` discriminator
  into `type_text` (so `BASELINE` becomes `BASELINE / linear` for
  the linear-mode variant); implementation hash gets a 12-char
  prefix + ellipsis for display, with explicit "(unregistered)"
  suffix when the hash is the operation_hash sentinel. Defensive
  fallback for non-{DataNode, OperationNode} input — never fires
  in practice (only those two classes live in `ProjectGraph`) but
  keeps the dialog resilient against stale caches.

**Body restructure — `_build_body`.** The body Frame now hosts a
`ttk.Notebook` instead of the universal + conditional sections
directly. Tab 1 "Style" (a `tk.Frame` with `padx=12, pady=8`)
hosts the universal + conditional sections; Tab 2 "Provenance"
(a `tk.Frame`) hosts the Canvas + Scrollbar pair. The Notebook
calls `notebook.select(style_tab)` explicitly so the default-
active tab is pinned even if a future "add a tab in front of
Style" refactor reorders the children.

**New attributes on the dialog instance.**
- `self._notebook: ttk.Notebook` — the tab host.
- `self._style_tab: tk.Frame` — Tab 1 content frame.
- `self._provenance_tab: tk.Frame` — Tab 2 content frame.
- `self._provenance_canvas: tk.Canvas` — vertical scrolling host.
- `self._provenance_inner: tk.Frame` — child of the canvas; the
  per-ancestor blocks live here.
- `self._body` (existing) — now points at the Frame containing
  the Notebook (was the Frame containing the sections directly).
  No external code reads `self._body`, so the meaning shift is
  internal-only.

**Provenance tab build — `_build_provenance_tab(parent)`.** Eager
construction at `__init__` (Decision (ii)). Creates a Canvas +
Scrollbar pair packed onto the tab frame; an inner Frame is
embedded via `canvas.create_window((0, 0), …, anchor="nw")`. The
inner Frame's `<Configure>` event refreshes the canvas's
`scrollregion` so vertical scrolling works as content height
changes. Then delegates to `_render_provenance_blocks(inner)`.

**Provenance content render — `_render_provenance_blocks(container)`.**
Walks `graph.provenance_chain(self._node_id)` (existing helper —
no `graph.py` change needed; the original register entry's
proposed `ancestors_of` would return the same list). For each
ancestor in topological order:
- A `tk.Frame` block with `padx=12, pady=6` packed `fill=X`.
- Header row: bold label · type tag (DataNodes only) · separator
  + state badge. Foreground colour comes from
  `_provenance_state_display(node.state)`; DISCARDED ancestors
  render dimmed.
- Body block (OperationNodes only): pretty-printed params
  (`(no params)` placeholder when empty), engine + version line,
  truncated implementation hash. Body uses `font=("Courier", 8)`
  for params alignment.
- A `ttk.Separator` between blocks (not after the last).
- Empty chain: shows `(no ancestors)` placeholder.

**Refresh — `_refresh_provenance()`.** Destroys the inner Frame's
children and re-renders from scratch. Cheap: ancestor walk is
bounded by graph size; widget tree is small. Idempotent — runs
on a destroyed inner Frame as a no-op (try/except around the
destroy + render). Defends against partial construction (the
attribute may not exist yet during the call — no-op).

**Graph-event extension — `_on_graph_event`.** Restructured to
run Provenance refresh BEFORE the existing same-node early
return, but AFTER the `_suspend_writes` guard:
```
if self._suspend_writes:
    return
if event.type in _PROVENANCE_REFRESHING_EVENTS:
    self._refresh_provenance()
if event.node_id != self._node_id:
    return
# existing branches: NODE_STYLE_CHANGED, NODE_LABEL_CHANGED
```
The Provenance rebuild fires on any node's qualifying event (any
ancestor in any chain might be affected); the style + label
refresh paths still gate on the dialog's own node id. The
`_suspend_writes` gate covers both — the dialog's own keystroke-
driven label rename does NOT rebuild Provenance per keystroke
(deliberate perf trade-off; bottom-of-chain block is briefly
stale during a typing session, refreshes on the next external
event or a dialog re-open).

**Locks.**
- `_NOTEBOOK_TAB_TITLES` content + tuple type. Reordering would
  change the default-active tab on dialog open. Pinned by
  `test_notebook_tab_titles_shape` + `test_notebook_tab_titles_is_tuple`.
- `_PROVENANCE_STATE_DISPLAY` covers every `NodeState` variant
  with the documented `(text, colour)` pairs. Pinned by
  `test_state_display_table_covers_every_state` +
  `test_state_display_provisional` +
  `test_state_display_committed` +
  `test_state_display_discarded_is_dimmed`.
- `_PROVENANCE_REFRESHING_EVENTS` membership = exact five-element
  frozenset above. Drift would silently widen or narrow which
  graph mutations refresh the Provenance tab. Pinned by
  `test_provenance_refreshing_events_membership`.
- `_format_provenance_op_params` sorted-by-key contract. Pinned
  by `test_format_op_params_sorted_by_key`.
- `_format_provenance_node_summary` flat-dict keys (`kind`, `id`,
  `label`, `type_text`, `state_text`, `state_colour`,
  `params_text`, `hash_text`, `engine_text`). Implementation
  hash 12-char prefix + ellipsis pinned by
  `test_summary_op_node_implementation_hash_truncated`. The
  unregistered: sentinel survives truncation as a 24-char prefix
  + " (unregistered)" suffix, pinned by
  `test_summary_op_node_unregistered_hash_keeps_marker`.
- `_build_provenance_tab` creates the Canvas + Frame pair as
  named attributes. Pinned by
  `test_provenance_tab_canvas_exists`.
- `_render_provenance_blocks` topological order (root → self).
  Pinned by `test_chain_renders_in_topological_order`.
- DISCARDED ancestors render with foreground `#888888`. Pinned
  by `test_discarded_ancestor_renders_dimmed`.
- Bottom button row stays outside the Notebook (visible
  regardless of active tab). Pinned by
  `test_button_row_outside_notebook`.
- `notebook.select(style_tab)` — Style is the default-active tab
  on dialog open. Pinned by `test_style_tab_is_default_active`.
- The graph-event handler's three-stage structure
  (`_suspend_writes` early-return → Provenance refresh →
  same-node early-return → style/label branches) is pinned by
  the contrast pair
  `test_self_keystroke_rename_skips_provenance_rebuild` (gates on
  guard) +
  `test_external_rename_does_rebuild_provenance` (refreshes when
  guard is False) — both halves of the perf trade-off stay
  honoured.

**What changes when this lock relaxes.** The "tighten organisation
for scale" half of Phase 4x friction #2 (LabelFrame groupings or
per-type sub-tabs inside Tab 1 "Style") is the natural next
relaxation: the universal section's existing rows + the new
"Label:" row + the gated "Y axis:" row keep their relative
ordering, only the parent widget changes (matching the CS-52 lock
relaxation pattern). The "Add to graph" gesture (Phase 4x
friction #4) extends the Provenance tab with a per-ancestor
button that materialises a discarded ancestor as a live node;
this would add a write path inside the Provenance tab and
require revisiting Decision (v) ("Provenance is read-only this
phase") explicitly.

**Implementation notes.**
- `graph.provenance_chain` was reused rather than introducing a
  new `ProjectGraph.ancestors_of` helper as the original register
  entry suggested. The two return the same topological-sorted
  list (ancestors + self in order); reusing the existing helper
  avoids a `graph.py` change and keeps the test surface narrow.
- Self-keystroke rename leaves the Provenance bottom-of-chain
  block stale until the next external event or dialog re-open.
  The cost of a per-keystroke Provenance rebuild was deemed
  higher than the cost of stale display during typing. See
  Phase 4ab friction list for the revisit-trigger.
- Mouse-wheel scrolling is NOT bound to the Provenance Canvas
  this phase. Standard tkinter Canvas+Scrollbar pattern — wheel
  events do not auto-route. The user has to drag the scrollbar
  manually for long ancestor chains. See Phase 4ab friction list
  for the cheap fix.
- The Provenance refresh fires for graph events on any node, not
  just ancestors of the dialog's own node. Wasted work for graphs
  with many disjoint chains; the per-rebuild cost is small enough
  (BFS bounded by graph size) that this hasn't been observed as a
  problem. Cheap optimisation for a future session: cache the
  ancestor set at construction; gate the refresh on
  `event.node_id in ancestor_set`.

---

## CS-54 — Drop CS-31 dedup + CS-32 sweep auto-grouping (Phase 4ac)

**Source files.** `graph.py` (one method removed); `scan_tree_widget.py`
(one module-level helper removed, three fields removed from
`__init__`, one method body simplified, six methods removed, one
guard removed from `_refresh_row`); `uvvis_tab.py` +
`uvvis_normalise.py` + `uvvis_smoothing.py` + `uvvis_peak_picking.py` +
`uvvis_second_derivative.py` (one short-circuit + one status-message
branch removed per file).

**Purpose.** Closes parts (a) + (b) of the USER-FLAGGED Phase 4v
friction #1 register entry — *"Drop CS-31 'no duplicate apply'
check + introduce user-driven node groups"*. The user flagged the
existing behaviour as workflow-blocking: CS-31's dedup gate
(Phase 4p) silently refused to create a new node when the user
re-applied the same operation with the same parameters, and
CS-32's sweep auto-grouping (Phase 4q) collapsed every PROVISIONAL
sibling sharing one (parent, op_type) into a single leader row
with a chevron expand toggle. Together, the two contracts hid
nodes the user wanted to act on. CS-54 removes both. Part (c) of
the original architecture — the user-driven `NodeType.NODE_GROUP`
container — is the carry-forward Phase 4ad intent.

**Architecture.** Two orthogonal removals, both data-shape changes:

1. **`graph.py`.** `ProjectGraph.find_provisional_op_with_params`
   — the inverse of `_compute_sweep_groups`'s grouping rule —
   removed. The five UV/Vis apply sites (`uvvis_tab._apply_baseline`,
   `NormalisationPanel._apply`, `SmoothingPanel._apply`,
   `PeakPickingPanel._apply`, `SecondDerivativePanel._apply`) lose
   the `existing = self._graph.find_provisional_op_with_params(...)`
   short-circuit + the matching `if existing is not None:` branch
   that wrote a status message and returned `None`. Apply now
   always proceeds to `compute()` and creates a fresh
   OperationNode + child DataNode regardless of param-equality.
   The companion error/validation paths (parameter parse errors,
   parent-node sanity checks, post-compute messageboxes) stay
   unchanged — only the dedup gate moves.
2. **`scan_tree_widget.py`.** Removed: the module-level helper
   `_datanode_parents`; the fields `_expanded_sweep_groups: set[str]`,
   `_sweep_groups: dict[str, list[str]]`, `_sweep_leaders: set[str]`
   from `__init__`; the methods `_compute_sweep_groups`,
   `_group_key_of`, `_build_sweep_row`, `_toggle_sweep_group`,
   `_discard_many` (the bulk-discard helper that only the sweep-
   leader row's `✕all` button called); the `if any(node_id in
   members for members in self._sweep_groups.values()):` guard in
   `_refresh_row`. `_rebuild` simplifies to a straight iteration
   over `_candidate_nodes()` → `_build_node_row(node)` for every
   candidate. Identical PROVISIONAL siblings sharing one DataNode
   parent now render as N standalone full-chrome rows.

**CS-35 lock survives.** The module-level constant
`_SWEEP_MEMBER_INDENT_PX = 16` and the `indent_px: int = 0` kwarg
on `_build_node_row` are deliberately preserved — Phase 4ad's
user-driven `NODE_GROUP` container will reuse them for group-
member visual nesting. The single call site that passed
`indent_px=_SWEEP_MEMBER_INDENT_PX` (in the now-removed expanded-
sweep render branch of `_rebuild`) goes away; the kwarg's default-
zero use stays correct for every standalone row.

**Decision lock taken.** Mechanical removal rather than stub.
Rationale: Phase 4ad's group container will be a different data
shape (an explicit `NodeType.NODE_GROUP` DataNode with member ids,
not a synthetic parent_id leader row). Keeping CS-32's `_sweep_*`
machinery dormant would be lock-list weight without future-fit —
none of the dormant fields would shape Phase 4ad's data model.
The constant + kwarg survive on a different bet (the indent
*shape* — pack-arg pass-through with a fixed pixel offset — is
likely to be reused even if the container data model is fresh).

**Lock relaxations recorded by this section.**

* **CS-31 lock relaxes.** `find_provisional_op_with_params` removed;
  the canonical CS-31 register entry above is now struck through
  (✅→reverted). The match contract (full dict equality on params
  + first-match-wins ordering + `state == PROVISIONAL` filter) is
  no longer pinned anywhere — Phase 4ad's group implementation is
  free to introduce its own equivalence rules (or none) without
  the CS-31 contract carrying through.
* **CS-32 lock relaxes.** `_expanded_sweep_groups`, `_sweep_groups`,
  `_sweep_leaders`, `_compute_sweep_groups`, `_build_sweep_row`,
  `_toggle_sweep_group` all removed. The "≥2 PROVISIONAL siblings
  sharing one DataNode parent" auto-grouping rule is gone — Phase
  4ad's group construction is user-driven, not auto-detected. The
  chevron `▸/▾` glyph + the leader-row `✕all` bulk-discard gesture
  + the `_group_key_of` lookup are also gone; Phase 4ad's group
  row will introduce its own expansion glyph, its own bulk
  gesture (likely "Ungroup" rather than "Discard all"), and its
  own membership lookup keyed by group-node id rather than
  parent-node id.
* **CS-35 lock partially survives.** The constant +
  `_build_node_row(indent_px=0)` kwarg signature stay verbatim;
  the call site that passed the constant goes away. Phase 4ad's
  group-member render branch is the next planned consumer.

**Tests pinning the removal.**

* Pure-module: `TestFindProvisionalOpWithParamsRemoved` (1 test,
  in `test_graph.py`) — `hasattr(g, "find_provisional_op_with_params")`
  is False on a fresh `ProjectGraph`.
* Pure-module: `TestSweepGroupRemovalPhase4ac` (4 tests, in
  `test_scan_tree_widget.py`) — each provisional sibling owns its
  own row; no chevron glyphs anywhere; the four removed fields
  + five removed methods all return False from `hasattr`.
* Pure-module: `TestStandaloneRowDefaultPaddingPhase4ac` (2 tests)
  — standalone rows pack at default `padx=2`; two-variant graphs
  no longer indent any row.
* Pure-module: `TestSweepMemberIndentConstant` extended (3 tests
  total) — constant survives at 16; `_build_node_row(indent_px=0)`
  kwarg signature pinned via `inspect.signature`.
* Per-panel integration tests (5 files, 1 test per file)
  — `test_apply_*_identical_re_apply_creates_new_sibling`: identical
  re-apply creates two ops + two data nodes; no "already applied"
  status spam fires.
* The 5 `test_apply_*_with_different_params_creates_new_node`
  tests stay verbatim — the "different params" path was always
  the same (create a new node), so no inversion is needed there.

**Net delta on the test suite.** 864 tests (down from 878 — 14
removed, 9 new pin tests added). The removal:

* `TestFindProvisionalOpWithParams` — 12 tests removed, 1 added
* `TestSweepGroupInlineExpansion` — 6 tests removed, 4 added
* `TestExpandedSweepGroupsField` — 1 test removed, 0 added
* `TestSweepGroupNestedIndent` — 5 tests removed, 2 added
* `TestSweepMemberIndentConstant` — 0 tests removed, 1 added
* Per-panel suppress tests (5 files) — inverted in place; no count
  change

**Carry-forward.** Phase 4ad — `NodeType.NODE_GROUP` (or
`USER_GROUP`) + the user-driven "Combine selected → Group"
gesture. Lock decisions still pending: gesture style (context-
menu / left-pane button / drag-and-drop), nested groups, where
the "Ungroup" gesture lives, and whether Phase 4ad reuses
`_SWEEP_MEMBER_INDENT_PX` or picks a fresh indent. The Phase 4v
friction #1 canonical register entry in BACKLOG.md (now ✅ for
parts a + b, ⏳ for part c) is the home for those decisions.

---

## CS-55 — Role-agnostic y-axis label resolution (Phase 4ad)

Phase 4ad (`uvvis_tab.py` + `test_uvvis_tab.py`) fixes the Phase
4ac friction #1 USER-FLAGGED 🔴 bug where the renderer's primary
y-axis label was hard-coded from y-unit only, leaving Absorbance-
on-secondary unlabelled and SECOND_DERIVATIVE-on-primary labelled
"Absorbance" (wrong for d²A values) once the CS-50 per-style
`y_axis` override hook landed. The fix is structural: label
dimensionality varies by NodeType class, not by axis role.

**New module-level constants (additive only — CS-44 untouched).**

- `_ABSORBANCE_SPACE_NODETYPES: frozenset[NodeType]` — the five
  NodeTypes whose y-values are in absorbance / transmittance
  space and therefore share the y-unit-derived label: UVVIS /
  BASELINE / NORMALISED / SMOOTHED / PEAK_LIST. Pinned by the
  drift test `test_absorbance_space_matches_primary_default_routing`
  against `_DEFAULT_Y_AXIS_BY_NODETYPE`'s primary-by-default
  subset — any future renderer NodeType that lands on `"primary"`
  by default but is NOT absorbance-shaped (e.g. a hypothetical
  concentration-space NodeType) must be added to the routing
  table without being added here.
- `_ABSORBANCE_Y_LABEL: dict[str, str]` — `{"A": "Absorbance",
  "%T": "Transmittance (%)"}`. Lifted from the previously inline
  `auto_ylabels` dict inside `_redraw`. Unknown y-units return
  `None` from the helper rather than guessing.

**New pure helper.**

- `_resolve_y_axis_label(node_type: NodeType, x_unit: str, y_unit:
  str) -> Optional[str]` — returns the label for a node of
  `node_type` rendered against the current `(x_unit, y_unit)`
  context, regardless of which axis role the node lives on.
  Resolution:
  1. If `node_type in _ABSORBANCE_SPACE_NODETYPES`, return
     `_ABSORBANCE_Y_LABEL.get(y_unit)` (or `None` for unknown
     y-units).
  2. Otherwise fall through to `_NON_PRIMARY_Y_LABEL.get(
     (node_type, x_unit))` — the existing CS-44 derivative-space
     label table, byte-identical to its pre-CS-55 state.
  3. Else `None`.

  The helper is consulted for every populated axis role in the
  Phase 4ad renderer pass; the role is intentionally NOT part of
  the key, because label text depends on the NodeType's nature,
  not on which side of the figure it ended up on.

**Renderer changes in `_redraw`.**

- `first_node_type_per_role.setdefault(role, node.type)` is now
  unconditional (the `if role != "primary":` guard from CS-44 is
  dropped). The map now records the first NodeType to land on
  every populated role, including primary.
- The pre-CS-55 unconditional primary `ax.set_ylabel(...)` block
  (`auto_ylabels[self._y_unit.get()]` inline lookup) is replaced
  by a role-walking pass. `ylabel_mode == "custom"` is the
  primary-only user-text affordance: when set, primary's label
  comes from `cfg["ylabel_text"]` and the auto loop skips
  primary. Otherwise every populated role's label flows through
  `_resolve_y_axis_label`. `None` returns leave the axis
  unlabelled rather than picking a guess (strictly better than
  pre-CS-55, which hard-coded "Absorbance" on an empty primary).

**Why option (b) over (a) and (c).**

The Phase 4ac friction #1 register entry surveyed three
architecture options:

- (a) Add a `_PRIMARY_Y_LABEL` companion table mirroring
  `_NON_PRIMARY_Y_LABEL`'s `(NodeType, x_unit) → label` shape.
- (b) Collapse into a single role-keyed lookup.
- (c) Widen `_NON_PRIMARY_Y_LABEL` to cover every renderer
  NodeType + parallel primary-side widening.

(c) was rejected — two parallel tables would drift on every
NodeType addition. (a) was rejected because absorbance-space
NodeTypes' labels depend on **y-unit** while derivative-space
NodeTypes' depend on **x-unit**: forcing UVVIS / BASELINE /
NORMALISED / SMOOTHED / PEAK_LIST entries into the
`(NodeType, x_unit)`-keyed shape would contradict the key's
semantics. (b)'s helper-based collapse correctly captures that
the dimension of variability is NodeType class, not role.

**Test coverage.**

- `TestYAxisLabelResolution` (9 pure-module tests, no Tk
  dependency) — frozenset membership of
  `_ABSORBANCE_SPACE_NODETYPES`; drift guard against
  `_DEFAULT_Y_AXIS_BY_NODETYPE`; `_ABSORBANCE_Y_LABEL` dict
  shape; absorbance-space y-unit invariance across every x-unit
  for all five member NodeTypes; SECOND_DERIVATIVE x-unit
  invariance across every y-unit; three `None`-return cases
  (unknown y-unit on absorbance-space, unknown x-unit on
  derivative, unrouted NodeType); backward-compatibility check
  that the new helper agrees with `_resolve_non_primary_y_label`
  for SECOND_DERIVATIVE.
- `TestYAxisLabelRoleSwap` (9 integration tests) — default
  routing UVVIS-only keeps primary's "Absorbance" label;
  y-unit flip to "%T" drives primary's label to
  "Transmittance (%)"; UVVIS routed to secondary labels
  secondary "Absorbance" (case A of the user-reported bug);
  same scenario with `y_unit = "%T"` labels secondary
  "Transmittance (%)"; SECOND_DERIVATIVE routed to primary
  alongside default-routed UVVIS labels primary by the first
  node (UVVIS); SECOND_DERIVATIVE alone on primary (parent
  hidden) labels primary "d²A/dλ²" (case B); full user-reported
  scenario (UVVIS on secondary + d²A on primary) labels both
  correctly; `ylabel_mode = "custom"` wins for primary
  regardless of routing while secondary stays auto; CS-44
  x-unit-aware secondary derivative label invariant preserved
  through the new helper for nm / cm-1 / eV.

**Locked invariants.**

- `_ABSORBANCE_SPACE_NODETYPES` content + frozenset type pinned
  by `test_absorbance_space_nodetypes_membership`.
- `_ABSORBANCE_Y_LABEL` content pinned by
  `test_absorbance_y_label_dict_shape`.
- `_resolve_y_axis_label` signature `(node_type: NodeType,
  x_unit: str, y_unit: str) -> Optional[str]`. Future widenings
  (e.g. a third role parameter) would need a deliberate signature
  change.
- The renderer's role-walking pass MUST consult the helper for
  every populated role, with `ylabel_mode == "custom"` skipping
  primary only.
- CS-44 invariants ALL preserved: `_NON_PRIMARY_Y_LABEL` content,
  `_resolve_non_primary_y_label` signature, `_AXIS_ROLES` shape,
  `_DEFAULT_Y_AXIS_BY_NODETYPE` content, `_TERTIARY_AXIS_OFFSET_FRAC`,
  `_resolve_y_axis_role` signature — all byte-identical pre-CS-55
  → post-CS-55. The new helper layers on top; it does not
  replace any CS-44 surface.

**Carry-forward.**

- 🟢 First-node-on-primary wins the label when multiple NodeType
  classes coexist on primary — under-informative when primary
  hosts both a default-routed UVVIS and an override-routed
  derivative. Polish-level; defer until reported.
- 🟢 `_NON_PRIMARY_Y_LABEL` is now misnamed (post-CS-55 it feeds
  primary too). Rename to `_DERIVATIVE_Y_LABEL` or
  `_Y_LABEL_BY_NODETYPE_AND_X_UNIT` requires a CS-44 lock-name
  relaxation. Cheap rename; defer.
- 🟢 Empty primary is silently unlabelled (strict improvement
  over pre-CS-55's wrong "Absorbance"). A future polish could
  surface "(no data)".
- Phase 4u friction #9 — `_absorbance_to_y` value-corruption on
  %T for d²A — stays open. CS-55 fixes label routing; the value-
  routing half is independent. Natural co-pickup with the next
  session that touches the per-node redraw loop's y-unit branch.

---

## CS-56 — Plot Settings → Appearance: grid colour + tertiary offset + inward-tick default (Phase 4ae)

**Origin**: Phase 4ac friction #2 + #3 (both USER-FLAGGED 🟡) and
the promote-to-Plot-Settings half of the Phase 4u Decision 7 /
CS-44 follow-up register entry. User had asked for a per-plot
grid-colour picker (today the grid renders at matplotlib's default
light grey with no control) and an inward-tick factory default
(the matplotlib default `"out"` clashes with their visual
preference). The CS-44 follow-up to promote
`_TERTIARY_AXIS_OFFSET_FRAC` to a tunable Plot Settings row paired
naturally — same Plot Settings → Appearance section, same factory-
dict + dialog-row + renderer-read code path. Phase 4ae bundled the
three into one phase to close two USER-FLAGGED items and a 🟢
CS-44 follow-up at the same time, on a single coherent surface.

### Architecture

Three new / changed entries in `plot_settings_dialog._FACTORY_DEFAULTS`:

    "grid_color":           "#b0b0b0",   # NEW (CS-56)
    "tick_direction":       "in",        # was "out"
    "tertiary_axis_offset": 1.12,        # NEW (CS-56)

`_UNIVERSAL_DEFAULTS = dict(_FACTORY_DEFAULTS)` inherits both new
keys at module import (shallow copy contract per the existing
module docstring). The CS-44 module constant
`uvvis_tab._TERTIARY_AXIS_OFFSET_FRAC = 1.12` stays in place as
the canonical fallback value the renderer reads when the cfg key
is missing; a drift-pin test asserts the two stay equal.

Two new rows in `_build_section_appearance`:

    row=0  Grid               (checkbox)        existing
    row=1  Grid colour        (swatch)          NEW
    row=2  Background         (swatch)          existing (was row=1)
    row=3  Tick direction     (radio)           existing (was row=2)
    row=4  Tertiary axis offset (float Spinbox) NEW

Grid colour reuses the existing `_make_colour_swatch` helper.
Tertiary offset uses an inline `tk.Spinbox` bound to a new
`_on_float_var_write` helper — analogue of `_on_int_var_write`;
skips the write on mid-edit `TclError`/`ValueError` rather than
crashing the trace, so the working dict keeps its last good value
until the spinbox re-stabilises. Spinbox bounds `1.00`–`1.50`,
increment `0.01`, format `"%.2f"`; bounds are a Claude pick (the
user confirmed both "change in plot settings" and "change the
default" paths are reachable today, no specific bounds locked).

Three apply sites in `uvvis_tab._redraw`:

1. Tick-direction fallback flip:
   `cfg.get("tick_direction", "out")` → `cfg.get("tick_direction", "in")`.
   Matches the factory-default flip; existing user configs that
   explicitly pin `"out"` still win.

2. Tertiary spine offset reads through a new local:
   `tertiary_offset = float(cfg.get("tertiary_axis_offset",
   _TERTIARY_AXIS_OFFSET_FRAC))`. The `get_axis(role)` closure
   uses `tertiary_offset` instead of the bare module constant
   when offsetting the right spine of the tertiary axis. The
   constant remains defined at module scope as the canonical
   fallback.

3. `ax.grid(...)` gains a `color=cfg.get("grid_color", "#b0b0b0")`
   kwarg. The `"#b0b0b0"` fallback matches matplotlib's default
   visual so existing user configs render identically until the
   new key is set.

### Lock decisions

**Grid colour:**
- (i) **app-global** in `_USER_DEFAULTS`. Consistent with every
  other Plot Settings key today. Per-tab is the future "project-
  specific plot defaults" register entry's job (BACKLOG line ~1648).
- (ii) **one colour** covers both major + minor grids.
  `ax.grid(color=...)` applies to both; two pickers is gold-plating.
- (iii) **plot-wide only.** No per-style override; the StyleDialog
  re-org register entry handles that if it ever surfaces.

**Inward-tick flip:**
- (i) **factory-default-only flip.** No migration code path.
  Existing `_USER_DEFAULTS["tick_direction"] = "out"` entries are
  left alone — explicit user choice wins. New users + users with
  no explicit setting get `"in"`. Cheapest, safest.
- (ii) **defer cross-tab.** `_FACTORY_DEFAULTS` is module-level;
  XANES / EXAFS / TDDFT inherit when they wire Plot Settings.
- (iii) **no-op for `plot_widget._tick_direction`.** Already
  defaults to `"in"` at [plot_widget.py:250](plot_widget.py#L250);
  question collapsed.

**Tertiary offset row:**
- **Surface-as-row only.** The larger CS-44 follow-up lift to
  `plot_widget.py` (or a new `plot_axes.py`) stays carry-forward
  on the original register entry. The new `tertiary_axis_offset`
  cfg-key read site lifts naturally alongside when the rest does.

### CS-44 lock relaxations

`_TERTIARY_AXIS_OFFSET_FRAC` is no longer the sole source of truth
for the tertiary spine offset — the Plot Settings cfg key takes
precedence; the constant is the fallback. The other CS-44 locks
stay byte-identical: `_AXIS_ROLES`, `_DEFAULT_Y_AXIS_BY_NODETYPE`,
`_NON_PRIMARY_Y_LABEL`, `_resolve_y_axis_role`,
`_resolve_non_primary_y_label`, the `get_axis(role)` lazy-creation
closure structure.

### Invariants (drift pins)

- `_FACTORY_DEFAULTS["tertiary_axis_offset"] ==
  uvvis_tab._TERTIARY_AXIS_OFFSET_FRAC`
  Pinned by `TestUVVisTabAppearancePhase4ae.
  test_factory_default_mirrors_tertiary_offset_constant`. Drift
  would surface as a visual jump on Factory Reset for any user
  who hasn't manually adjusted the offset.
- `_FACTORY_DEFAULTS["grid_color"] == "#b0b0b0"`. Pinned by
  `TestAppearanceSectionPhase4ae.
  test_grid_color_in_factory_defaults`. The hex value matches
  matplotlib's default so a fresh user config renders identically
  to a pre-CS-56 default.
- `_FACTORY_DEFAULTS["tick_direction"] == "in"`. Pinned by
  `TestAppearanceSectionPhase4ae.
  test_tick_direction_factory_default_is_in`.

### Test footprint

- 10 pure-module tests in `test_plot_settings_dialog.
  TestAppearanceSectionPhase4ae` — factory dict shape, dialog
  widget construction (swatch registry + DoubleVar registry),
  write-through paths, Factory Reset, config pre-population.
- 7 integration tests in `test_uvvis_tab.
  TestUVVisTabAppearancePhase4ae` — drift pin, `plot_config`
  inherits the inward-tick default, `ax.grid` colour for default
  + custom + off-then-on round-trip, tertiary-offset spine
  position for default fallback + custom cfg value (reusing the
  monkey-patch trick `TestUVVisTabTertiaryAxisPath` uses to route
  NORMALISED to "tertiary").

Total: 882 → 899 (+17 new tests, all green).

### Carry-forward (per the original CS-44 follow-up register entry)

- The full lift of `_AXIS_ROLES`, `_DEFAULT_Y_AXIS_BY_NODETYPE`,
  `_NON_PRIMARY_Y_LABEL`, `_resolve_y_axis_role`,
  `_resolve_non_primary_y_label`, and the `get_axis(role)`
  closure from `uvvis_tab._redraw` into `plot_widget.py` (or
  a new `plot_axes.py`) stays ⏳. Trigger: when a second tab
  (XANES / EXAFS) needs multi-axis routing. Single consumer
  today; no abstraction tax warranted. The new
  `tertiary_axis_offset` cfg-key read site lifts naturally
  alongside when the rest does.

### Friction surfaced at step 5 (Claude-surfaced; no register entries)

- 🟢 `_make_colour_swatch` has no `trace_add` on its `StringVar` —
  writes to `_working` only fire via the colorchooser's `_pick`
  callback explicitly calling `_on_var_write`. Same gap exists
  for the existing `background_color` swatch. One-line fix; own
  phase to avoid drive-by behaviour change.
- 🟢 No targeted persistence round-trip test for the new keys
  through `project_io`. Likely works (CS-46 round-trips arbitrary
  `plot_defaults` content) but unproven.
- 🟢 The `tick_direction` factory-default flip is observable to
  existing users with no `_USER_DEFAULTS["tick_direction"]`. Per
  the decision lock this is intentional, but worth surfacing in
  a future release-note flow.
- 🟢 Spinbox bounds `1.00`–`1.50` are a Claude pick, not a user
  lock. `tk.Spinbox` lets the user type values outside the
  bounds (arrows clamp, typed input does not), so the band is a
  soft suggestion.
- 🟢 Dialog row order in `_build_section_appearance` is a
  cluster-by-concept choice (Grid + Grid colour together) over
  cluster-by-widget (both colour swatches adjacent). If the
  planned LabelFrame re-org pass reshapes the section, re-sort
  then.

---

## CS-57 — User-driven NODE_GROUP container + Combine/Ungroup gesture (Phase 4af)

**Status:** ✅ implemented.

The scientific question
-----------------------

After Phase 4ac (CS-54) dropped the CS-31 dedup gate + the CS-32
auto-sweep-grouping, identical re-applies render as N separate
sibling rows. Users wanted to *organise* those siblings (and any
other set of related DataNodes — kinetic series across a parameter
sweep, a-vs-b comparison pair, baseline candidates) into a
collapsible container without losing the per-node identity that
CS-54 deliberately preserved. The architecture question: how do we
add a view-layer aggregation without re-introducing CS-32's
auto-grouping pitfalls?

The Phase 4af answer (CS-57)
----------------------------

A new `NodeType.NODE_GROUP` DataNode that carries no scientific
data (`arrays={}`), holds an ordered list of member ids in
`metadata["member_ids"]: list[str]`, and renders in the scan tree
as a chevron-toggleable container row above its members. Creation
and dissolution are USER-DRIVEN through two surfaces — a footer
"Group selected" button and a right-click "Group selected (N)"
context-menu entry — never automatic. Members keep their original
parent edges untouched; the group is a sibling, not a reparenting,
so every consumer of `parent_id` (provenance walks, baseline
lookups, send-to-compare wiring) needs zero awareness of grouping.

Design invariants
-----------------

Locked at the graph layer (`graph.py`):

1. **Flat-only — no nested groups.** `create_group` rejects any
   member that is itself a NODE_GROUP. Relaxing this later is
   additive (the chevron expansion becomes a tree walk); tightening
   from nested to flat would be a breaking change, so flat-only is
   the safe default.
2. **Single-membership.** A node belongs to at most one active
   NODE_GROUP. `create_group` rejects already-grouped members;
   `group_of(node_id)` walks active groups and returns the first
   (canonical) match.
3. **No scientific arrays.** A NODE_GROUP MUST have `arrays={}`.
   The renderer (`uvvis_tab._redraw`) does not iterate NODE_GROUPs
   at all — they're a sidebar-only construct.
4. **Always PROVISIONAL.** Groups have no scientific value to
   commit; the only state transition is PROVISIONAL → DISCARDED
   via `dissolve_group`, which routes through `discard_node` and
   emits NODE_DISCARDED.
5. **Auto-dissolve cascade.** When the discarded node is a group
   member and the group falls below two active members,
   `discard_node` recursively discards the group. Threshold matches
   `create_group`'s ≥2 minimum so a group never lingers with one
   or zero active members. The flat-only invariant bounds the
   recursion at one level (groups never nest, so a group's own
   discard never re-cascades).

Locked at the UI layer (`scan_tree_widget.py`):

6. **Two surfaces for the create gesture (decision lock i).**
   Right-click context-menu "Group selected (N)" on a data row
   AND footer "Group selected" button. Both are gated by
   `_can_group_selection()`, which mirrors `create_group`'s
   validation so the UI never offers a gesture that would raise.
7. **Two surfaces for the dissolve gesture (decision lock iii).**
   Right-click context-menu "Ungroup" on a group row AND inline
   ✕ on the group row's right edge. Both call
   `ProjectGraph.dissolve_group`.
8. **`<ButtonRelease-1>` selection toggle, not `<Button-1>`.**
   A double-click rename gesture fires Release twice
   (Button → ButtonRelease → Double-Button → ButtonRelease), so
   binding selection to Release nets out to zero toggle on
   double-click while still toggling on single-click. The
   alternative (deferred-resolution via `after(300, ...)`) is
   complex; the Release approach is one line per binding.
9. **Member indent reuses `_SWEEP_MEMBER_INDENT_PX = 16` (decision
   lock iv).** CS-35's dormant constant + `_build_node_row(indent_
   px=0)` kwarg signature, preserved verbatim across Phase 4ac
   on the bet of Phase 4ad's NODE_GROUP arrival, are now LIVE in
   Phase 4af. The CS-35 lock survives into Phase 4af's lock list.

Module layer
------------

The Phase 4af machinery is concentrated in three modules + two
new lifecycle helpers:

* `nodes.py` — `NodeType.NODE_GROUP` enum variant. Docstring
  records the lock invariants (no arrays, member_ids in metadata,
  always PROVISIONAL, flat-only, single-membership, view-layer
  aggregation).
* `graph.py` —
  * `create_group(member_ids: list[str], label: str | None = None)
    -> str` — validates and creates; emits NODE_ADDED via
    `add_node`. Default label `"Group N"` where N counts existing
    NODE_GROUPs (active or discarded).
  * `dissolve_group(group_id: str) -> None` — type-checks then
    delegates to `discard_node` so NODE_DISCARDED fires normally.
  * `group_of(node_id: str) -> str | None` — never raises; walks
    active groups and matches against `metadata["member_ids"]`.
  * `discard_node` — auto-dissolve cascade hook (see invariant 5).
* `scan_tree_widget.py` — new view state (`_selected_node_ids`,
  `_expanded_groups`), new footer button + group-row pipeline
  (`_build_group_row`, `_toggle_group_expansion`,
  `_toggle_row_selection`, `_apply_row_selection_visual`,
  `_refresh_group_button_state`, `_can_group_selection`,
  `_group_selected`, `_show_group_context_menu`). `_candidate_
  nodes` excludes grouped members; `_rebuild` branches on
  NODE_GROUP and renders members below with the CS-35 indent.

Persistence
-----------

A NODE_GROUP DataNode survives `project_io.save_project` →
`load_project` with NO schema changes (CS-46 already round-trips
arbitrary DataNode shapes; arrays={} produces an empty savez
archive, `member_ids` in metadata is JSON-serialisable). Pinned by
`test_node_group_round_trips_through_save_load` in
`test_persistence_phase_a.TestSaveLoadRoundTrip`.

Test pins (50 new tests across four files)
------------------------------------------

* `test_nodes.TestNodeTypeEnum` — `NODE_GROUP` is a distinct
  variant (not an alias of `AVERAGED` / `DIFFERENCE`).
* `test_graph.TestNodeGroupOps` (27 tests) — create/dissolve/
  group_of happy paths + all eight validation paths + auto-
  dissolve cascade behaviour (fires at threshold, doesn't fire
  above, walks through sequential discards, emits ordered events,
  bounded at one level).
* `test_scan_tree_widget.TestScanTreeWidgetNodeGroupsPhase4af`
  (21 tests) — selection model, visual highlight, footer button
  predicate (zero / one / two / already-grouped / NODE_GROUP-as-
  selection), `_group_selected` clears selection + member-order
  deterministic, group row chrome + count badge, members hidden
  from top-level when collapsed + indent when expanded, chevron
  toggle, dissolve restores members at top-level, auto-dissolve
  prunes group row + expanded-groups set, rebuild prunes stale
  selection ids, context-menu dispatch branch.
* `test_persistence_phase_a.TestSaveLoadRoundTrip` (1 test) —
  full `.ptmg` save → load round-trip with a NODE_GROUP holding
  two UVVIS members; type, label, member_ids, arrays, and
  `group_of` all survive.

Lock relaxations
----------------

This CS section LOCKS the following identifiers — changing any of
them requires a deliberate CS-N relaxation in a future phase that
re-litigates the contract:

* `NodeType.NODE_GROUP` enum variant existence + name.
* `metadata["member_ids"]: list[str]` convention.
* `ProjectGraph.create_group(member_ids, label=None) -> str` /
  `dissolve_group(group_id)` / `group_of(node_id) -> Optional[str]`
  signatures + raise semantics.
* `discard_node` auto-dissolve cascade — threshold (<2 active
  members), guard (skip on NODE_GROUP self-discard), one-level
  recursion bound.
* `_selected_node_ids: set[str]` + `_expanded_groups: set[str]`
  attribute names on ScanTreeWidget.
* `_SELECTION_BG = "#cce4ff"` (the row-selection highlight colour).
* The footer button's existence + `_group_btn` attribute name +
  `text="Group selected"` initial label (the count-aware label
  is a future polish — Phase 4af friction #6).
* The `<ButtonRelease-1>` selection toggle binding contract
  (decision lock 8 — net-zero on double-click is the invariant
  the binding shape encodes).
* The simplified group context menu's three entries: Rename,
  Expand-or-Collapse, Ungroup.
* The `<Button-3>` data-row context-menu's new "Group selected
  (N)" entry's existence + predicate (`_can_group_selection() AND
  node_id in _selected_node_ids`).
* `_SWEEP_MEMBER_INDENT_PX = 16` value + `_build_node_row(indent_
  px=0)` kwarg signature — CS-35 lock survives.

Lock relaxations that explicitly DO NOT require a CS-N bump:

* The "(N members)" label suffix shape (Phase 4af friction #4
  flags this for polish; rewording is free).
* `_show_hidden`'s behaviour on group rows (untested edge — Phase
  4af friction #5).
* The selection-visual paint helper's implementation detail
  (currently writes `bg` on the row's `anchor="w"` label widget;
  any equivalent visual treatment is fine).
* Auto-name `f"Group {N}"` template (user can rename freely;
  template change is free).

Friction points carried forward
-------------------------------

See "Friction points carried forward from Phase 4af" in
BACKLOG.md. Highest-pain items the next session may want to fold
in:

- 🟡 USER-FLAGGED Keyboard shortcuts — whole-interface
  evaluation pass (new register entry, multi-phase design pass).
- 🟡 USER-FLAGGED "Add to existing group" gesture (new register
  entry, Phase 4ag candidate — the natural v2 extend path).
  ✅ Resolved in Phase 4ag (CS-58).

---

## CS-58 — Extend + Remove gestures for NODE_GROUP (Phase 4ag)

**Status:** ✅ implemented.

The scientific question
-----------------------

Phase 4af (CS-57) shipped the v1 create + dissolve gestures for
user-driven NODE_GROUPs. Once a group existed, the ONLY way to
add new members was dissolve + reselect + recreate — destroying
the user-edited label, the per-group state, and the ordering
context the user had built. The architecture question for the
v2 extend path: how do we surface "add to existing group" + the
symmetric "remove single member" without re-introducing CS-32's
auto-grouping pitfalls and without breaking CS-57's invariants?

The Phase 4ag answer (CS-58)
----------------------------

Two new graph-layer methods that mirror CS-57's contract:
`ProjectGraph.extend_group(group_id, member_ids)` appends to an
existing group's roster, and `ProjectGraph.remove_from_group(
node_id)` detaches a single node. The new
`GraphEventType.NODE_GROUP_MEMBERS_CHANGED` event carries the
delta (`{"group_id", "added", "removed"}`). Three new
ScanTreeWidget surfaces consume the API: the footer
`_group_btn` switches its text + click-target based on
selection classification, the group-row context menu grows a
fourth entry "Add selected to this group", and the data-row
context menu grows two siblings ("Add selected to <group
label>" + per-row "Remove from group").

Design invariants
-----------------

Locked at the graph layer (`graph.py`):

1. **List shape is canonical, mutability grows.** CS-57's
   `metadata["member_ids"]: list[str]` convention stays. CS-58
   relaxes the IMMUTABILITY of the list (extend / remove now
   mutate in place). The shape — flat list of node ids in
   roster order — is unchanged. A future tightening to e.g.
   a frozen tuple would be a breaking change.
2. **Validation mirrors `create_group`.** `extend_group`
   re-runs every check (unique within call, no already-in-
   roster, no already-grouped-elsewhere, no nested group, no
   discarded, no operation node). The user-facing gestures
   converge to a single set of rules — what fails on create
   also fails on extend.
3. **Append ordering.** New members are appended to the
   existing roster, preserving caller order. Pre-existing
   members keep their position. Re-ordering is out of scope
   (no register entry; not surfaced as friction).
4. **Auto-dissolve threshold reused.** `remove_from_group`
   routes through `discard_node` when the post-removal active
   member count drops below 2. CS-57's cascade logic fires
   identically — `remove_from_group` does not duplicate the
   walk; it just removes the id and lets `discard_node` decide.
5. **Event suppression on cascade.** When `remove_from_group`
   triggers the auto-dissolve, `NODE_GROUP_MEMBERS_CHANGED` is
   NOT emitted — the cascading `NODE_DISCARDED` on the now-
   defunct group is the authoritative signal. Subscribers see
   exactly one terminal event for that group instance.

Locked at the UI layer (`scan_tree_widget.py`):

6. **Structural event routing.** `NODE_GROUP_MEMBERS_CHANGED`
   joins `NODE_ADDED / NODE_COMMITTED / NODE_DISCARDED /
   EDGE_ADDED / GRAPH_LOADED / GRAPH_CLEARED` in `_on_graph_
   event`'s full-rebuild branch. Member changes are
   structural (rows move between top-level and group-nested
   rendering); a targeted `_refresh_row` cannot reshuffle
   the membership boundary. CS-57's choice of
   `NODE_LABEL_CHANGED → targeted refresh` is preserved; the
   new event lands in the existing structural list because
   that branch already handles the rebuild correctly.
7. **Single selection-classification analysis.** New helper
   `_classify_selection() -> dict` returns one of:
   - `{"mode": "none"}` — empty selection.
   - `{"mode": "group", "members": [ids in graph order]}` —
     ≥2 ungroupable nodes, no groups, none already grouped:
     `create_group` is legal.
   - `{"mode": "extend", "group_id": str,
     "members": [ungrouped ids in graph order]}` — exactly
     one NODE_GROUP + ≥1 ungrouped, none already grouped:
     `extend_group` is legal.
   - `{"mode": "invalid"}` — non-empty but doesn't fit
     either gesture.
   Footer button refresh + both context-menu builders read
   from this canonical analysis. Avoids the duplicated walk
   adding per-surface predicates would have produced.
8. **CS-57 button-text lock relaxed.** The footer button now
   mutates its text per `_classify_selection`'s verdict:
   `"Group selected (N)"` in group mode, `"Add to <truncated
   group label>"` in extend mode, baseline `"Group selected"`
   disabled otherwise. The relaxation trigger (Phase 4af
   friction #6 "static button label") was always anticipated
   in CS-57's lock list. `_group_btn` attribute name and the
   button's existence + position are preserved.
9. **Right-click-target / selection-payload convention.**
   The group-row context menu's fourth entry ("Add selected
   to this group") and the data-row "Add selected to <group
   label>" sibling both follow the same shape: the
   right-clicked row identifies the target / scope; the
   current selection identifies the payload. The group-row
   entry is intentionally insensitive to whether the
   right-clicked group is itself in the selection — the
   right-click IS the selection in that branch. The
   data-row "Add selected to <group>" entry is gated on the
   clicked row being in the selection, mirroring CS-57's
   "Group selected" entry's predicate.
10. **Per-row Remove preserves selection.** The data-row
    context menu's "Remove from group" entry is a per-row
    gesture (target identified by right-click only — the
    selection is irrelevant). It does NOT clear
    `_selected_node_ids`. Only multi-target gestures
    (`_group_selected`, `_extend_into_group`) reset the
    selection.

Module layer
------------

CS-58 is concentrated in two modules:

* `graph.py` —
  * New `GraphEventType.NODE_GROUP_MEMBERS_CHANGED` enum
    variant; payload convention documented on `GraphEvent`.
  * `extend_group(group_id, member_ids) -> None` — validation
    mirrors `create_group`; mutates `metadata["member_ids"]`
    in place; emits `NODE_GROUP_MEMBERS_CHANGED` with
    `{"added": [...], "removed": []}`.
  * `remove_from_group(node_id) -> None` — raises
    `ValueError` if not in any active group; mutates
    `metadata["member_ids"]` in place; routes through
    `discard_node` for the auto-dissolve cascade when the
    active member count drops below 2; otherwise emits
    `NODE_GROUP_MEMBERS_CHANGED` with `{"removed": [node_id],
    "added": []}`.
* `scan_tree_widget.py` —
  * `_on_graph_event` — `NODE_GROUP_MEMBERS_CHANGED` joins
    the structural-rebuild branch.
  * `_classify_selection() -> dict` — canonical selection
    analysis (see lock 7).
  * `_can_extend_existing_group() -> tuple[str, list[str]]
    | None` — thin wrapper that returns the extend pair or
    None; used by context-menu predicates.
  * `_refresh_group_button_state` — now sets BOTH text and
    state (CS-58 button-text lock relaxation).
  * `_group_selected` — branches on classification:
    `create_group` for group mode, `extend_group` for
    extend mode, no-op for invalid / none.
  * `_extend_into_group(group_id)` — context-menu action.
    Walks the selection, filters to only ungroupable data
    nodes, calls `extend_group`, clears selection.
  * `_remove_from_group_via_menu(node_id)` — per-row
    gesture. Wraps `graph.remove_from_group` in `_safely`;
    preserves selection.
  * `_show_group_context_menu` — grows a fourth entry
    "Add selected to this group (N)".
  * `_show_context_menu` (data row) — grows two sibling
    entries: "Add selected to <group label> (N)" and per-row
    "Remove from group".
  * `_can_group_selection` — preserved verbatim as a thin
    alias of `_classify_selection()["mode"] == "group"`;
    referenced by an existing Phase 4af test and the
    data-row "Group selected (N)" predicate. Duplication
    deferred (Phase 4ag friction #4).

Test pins (53 new tests across three files)
-------------------------------------------

* `test_graph.TestNodeGroupExtendRemoveOps` (27 tests):
  - extend happy path + caller-order preservation;
  - every validation raise: unknown group, non-group target,
    op-node target, discarded group, empty list, intra-call
    duplicates, already-in-this-group, unknown member, op-node
    member, nested group, discarded member, member in another
    group;
  - event shape: emits exactly `NODE_GROUP_MEMBERS_CHANGED`
    with the added list; payload list is an independent copy;
  - atomic validation (partial mutation never survives a raise);
  - `group_of` consistency after extend;
  - remove happy path + member-attribute preservation;
  - auto-dissolve threshold (<2 active members) routes to
    `NODE_DISCARDED`, suppressing `MEMBERS_CHANGED`;
  - remove → extend round-trip.
* `test_scan_tree_widget.TestScanTreeWidgetNodeGroupsPhase4ag`
  (24 tests): structural rebuild on extend AND remove;
  `_classify_selection` covers all five branches; footer
  button text + state for each classification; footer click
  dispatch; `_extend_into_group` selection filtering;
  `_remove_from_group_via_menu` preserves selection; group
  context menu fourth entry; data-row context menu siblings.
  Uses an enriched spy-menu pattern (captures every
  `add_command` keyword dict).
* `test_persistence_phase_a.TestSaveLoadRoundTrip` (2 tests):
  - full mutation sequence (create → extend → remove) round-
    trips through save/load with `group_of()` mapping intact;
  - auto-dissolved group survives save/load as DISCARDED with
    `group_of()` returning None for formerly-grouped members.

Lock relaxations
----------------

This CS section LOCKS the following identifiers — changing any of
them requires a deliberate CS-N relaxation in a future phase:

* `GraphEventType.NODE_GROUP_MEMBERS_CHANGED` enum variant + its
  payload convention (`{"group_id", "added", "removed"}`).
* `ProjectGraph.extend_group(group_id, member_ids) -> None` /
  `remove_from_group(node_id) -> None` signatures + raise
  semantics.
* The auto-dissolve event-suppression contract on remove
  (cascading `NODE_DISCARDED` is the authoritative signal;
  `NODE_GROUP_MEMBERS_CHANGED` is NOT emitted in that branch).
* `_classify_selection`'s four return shapes (none / group /
  extend / invalid) + the field names (`mode`, `members`,
  `group_id`).
* `_extend_into_group(group_id)` + `_remove_from_group_via_menu(
  node_id)` method names.
* The footer button's three text variants (`"Group selected
  (N)"`, `"Add to <label>"`, baseline `"Group selected"`).
* The group-row context menu's growth from three entries to
  four (Rename, Expand/Collapse, Ungroup, "Add selected to
  this group (N)").

Lock relaxations to CS-57 made by CS-58 (explicitly recorded):

* CS-57 invariant 6 (`_can_group_selection` is the single
  predicate gating the footer button + data-row entry) is
  narrowed — `_can_group_selection` now covers ONLY the
  create_group gesture; the extend gesture is gated by
  `_can_extend_existing_group` (returns Some / None).
* CS-57 button-text lock (`text="Group selected"` initial label)
  is broadened — the button now mutates its text per
  selection classification.
* CS-57 narrow "any NODE_GROUP in selection → button disabled"
  semantics is broadened — `1 group + ≥1 ungrouped` now
  routes to the extend gesture.

Lock relaxations that explicitly DO NOT require a CS-N bump:

* The "Add to <group label>" 24-char truncation cap (Phase 4ag
  friction #6 polish — derive from footer width if needed).
* The group "(N members)" suffix's location inside the main
  label widget (Phase 4af friction #4 carry-over — moving to
  a separate widget cell is free).
* The `_classify_selection` "invalid" branch's grouping of
  sub-cases (mixed groups / orphan member / single group
  alone are all "invalid"; future refactors can split into
  distinct verdicts if a surface needs to differentiate).

Friction points carried forward
-------------------------------

See "Friction points carried forward from Phase 4ag" in
BACKLOG.md. Three new USER-FLAGGED 🟡 register entries from
step 5: grid z-order bug, axis double-click dialog, "Show
hidden" disable-gating. Four Claude-surfaced 🟢 polish notes.

## CS-59 — Show-hidden disable-gating + `_absorbance_to_y` NodeType gate (Phase 4ah)

**Status:** ✅ implemented.

The scientific question
-----------------------

Phase 4ah is a polish bundle resolving four register entries
of different sizes. CS-59 anchors the two changes that
introduce new locks the next session must respect — a new
Checkbutton state-aware refresh pattern (in `scan_tree_widget.
py`) and a signature widening on the renderer's y-axis
conversion helper (in `uvvis_tab.py`). The other two
Phase 4ah commits (grid `zorder=0`; relocation of Open File /
Reload from app top-bar into the TDDFT sidebar) are bug-fix
/ UI relocation changes that don't introduce architectural
locks — they're documented in the doc-version footer entry
1.34 below.

The Phase 4ah answer (CS-59)
----------------------------

Two architectural threads:

**Thread A — Show-hidden disable-gating.** The "Show hidden"
footer Checkbutton, on a fresh workflow where no rows have
`active=False`, reads as responsive but produces no visible
change on click — a false affordance the user explicitly
flagged ("if it's not relevant, then it should be greyed out
when it's not relevant"). The Checkbutton is now stored as
`self._show_hidden_btn`, and a new `_refresh_show_hidden_
button_state()` method (called from `_rebuild`'s tail
alongside `_refresh_group_button_state`) reads the new
`_has_hidden_rows()` predicate and flips the button between
`"normal"` and `"disabled"`. The pattern generalises: future
state-aware footer controls follow the same shape — store
the widget as an attribute, recompute on `_rebuild` end via
a `_refresh_<name>_button_state` method whose name pattern
makes the cluster discoverable.

**Thread B — `_absorbance_to_y` NodeType gate.** The
renderer's per-node y-conversion helper used to apply
`100 · 10^(-A)` to every node's `arrays["absorbance"]` field
when `_y_unit == "%T"`, regardless of NodeType. This
corrupted SECOND_DERIVATIVE values (whose `arrays["absorbance"]`
field actually holds d²A/dλ² values by legacy naming). The
helper now takes a third positional `node_type: NodeType`
argument and short-circuits to a pass-through when
`node_type not in _ABSORBANCE_SPACE_NODETYPES` (the CS-55
frozenset). Centralised gate keeps the three `_redraw`
call sites symmetric — the helper owns the rule.

Design invariants
-----------------

Locked at the widget layer (`scan_tree_widget.py`):

1. **`_show_hidden_btn` attribute identity.** The "Show
   hidden" Checkbutton is the `self._show_hidden_btn`
   attribute on `ScanTreeWidget`. Future state-aware
   manipulations (count badge, tooltip) attach to this
   attribute. Renaming would break the refresh method's
   `getattr(self, "_show_hidden_btn", None)` defensive lookup
   that protects against in-flight `__init__` calls.
2. **`_has_hidden_rows() -> bool` semantics.** Returns True
   iff ≥1 non-DISCARDED DataNode with `active=False` passes
   the tab predicate (or is itself a NODE_GROUP — which
   always passes per CS-57's visual-layer invariant).
   Includes hidden group members regardless of whether their
   parent group is expanded. Rationale: if a member is
   currently hidden, the toggle becomes relevant the moment
   the user expands its group, so the toggle's enabled state
   should not whiplash as the user expands/collapses groups.
3. **`_refresh_show_hidden_button_state()` signature + call
   site.** No arguments; called at the end of every
   `_rebuild` immediately after `_refresh_group_button_state`.
   The order matters only for predictability — the two
   refresh methods are independent.
4. **Cascade contract: never silently flip `_show_hidden`.**
   If the toggle is currently ON and the last hidden row
   disappears (discarded or un-hidden), `_show_hidden` STAYS
   True and `_show_hidden_btn` becomes `disabled`. The
   disabled state is itself the affordance; mutating
   `_show_hidden` would change view state behind the user's
   back.
5. **Disable-only — no tooltip, no count badge.** The
   register entry asked whether to surface a count badge
   ("Show hidden (3)") or a tooltip on the disabled state.
   Phase 4ah picked the minimal scope: disable-gate only.
   Adding either is a future polish trigger, not a hidden
   constraint.

Locked at the renderer layer (`uvvis_tab.py`):

6. **`_absorbance_to_y(absorbance, y_unit, node_type) ->
   np.ndarray`.** Three positional args; the third is a
   `NodeType` enum value. Future signature changes (e.g.
   widening to accept the full node for style-aware
   conversion) require a CS-N relaxation.
7. **The CS-55 frozenset is the canonical gate.**
   `_absorbance_to_y` reads `_ABSORBANCE_SPACE_NODETYPES`
   directly. Adding SECOND_DERIVATIVE (or any future
   derivative-space NodeType) to that frozenset would
   re-introduce the Phase 4u friction #9 bug — pinned by
   `test_absorbance_space_node_types_pin`.
8. **Pass-through, not error.** Non-absorbance-space
   NodeTypes return the input array unchanged. The helper
   never raises on an unknown NodeType — additive
   compatibility is the contract so a future NodeType lands
   as a single `_DEFAULT_Y_AXIS_BY_NODETYPE` table edit
   (CS-44 / CS-55 follow-up) without needing to touch
   `_absorbance_to_y`.

Module layer
------------

CS-59 is concentrated in two modules:

* `scan_tree_widget.py` —
  * `self._show_hidden_btn` — Checkbutton reference now
    stored as an attribute (was anonymous in Phase 4af).
  * `_has_hidden_rows() -> bool` — new pure predicate.
  * `_refresh_show_hidden_button_state()` — new no-arg
    refresh method; called from `_rebuild`'s tail.
* `uvvis_tab.py` —
  * `_absorbance_to_y(absorbance, y_unit, node_type)` —
    signature widened; gates `%T` conversion on the CS-55
    `_ABSORBANCE_SPACE_NODETYPES` frozenset.
  * Three call sites in `_redraw` pass `node.type` /
    `bn.type` / `peak_node.type` respectively.

Test pins (20 new tests across two files)
-----------------------------------------

* `test_uvvis_tab.TestUVVisTabGridZOrderPhase4ah` (2 tests,
  commit 1 / not CS-59 strictly but Phase 4ah anchor):
  - relational invariant (every gridline zorder < every
    data-line zorder);
  - literal value (`get_zorder() == 0`).
* `test_scan_tree_widget.TestShowHiddenButtonGatingPhase4ah`
  (11 tests, commit 2 / Thread A):
  - 6 pure-helper coverage (empty graph, all-active, one
    hidden, discarded-ignored, predicate-excluded-ignored,
    NODE_GROUP-counts);
  - 5 button-state coverage (fresh-disabled, becomes-hidden,
    un-hidden-redisables, cascade discard preserves
    `_show_hidden` ON, hidden group member counts).
* `test_uvvis_tab.TestAbsorbanceToYNodeTypeGatePhase4ah`
  (7 tests, commit 4 / Thread B):
  - 1 frozenset-membership pin (drift guard);
  - 4 pure-helper coverage (d²A passthrough on A AND %T;
    UVVIS conversion preserved; clip preserved on absorbance-
    space; A passthrough across all absorbance-space
    NodeTypes);
  - 2 integration coverage (d²A values reach matplotlib
    unchanged on %T flip; UVVIS values STILL convert on %T
    flip).

Lock relaxations
----------------

This CS section LOCKS the following identifiers — changing
any of them requires a deliberate CS-N relaxation in a
future phase:

* `_show_hidden_btn` attribute identity on `ScanTreeWidget`.
* `_has_hidden_rows() -> bool` signature + the predicate it
  evaluates (lock 2).
* `_refresh_show_hidden_button_state()` signature + the
  `_rebuild`-tail call site.
* Cascade contract: `_show_hidden` is never silently flipped
  by the refresh method.
* `_absorbance_to_y(absorbance, y_unit, node_type)` three-
  positional signature.
* The CS-55 frozenset `_ABSORBANCE_SPACE_NODETYPES` remains
  the canonical gate (CS-55 invariant 1 is RE-LOCKED here,
  not relaxed — adding SECOND_DERIVATIVE to it would
  regress Phase 4u friction #9).

Lock relaxations to prior CS sections made by CS-59:

* None. CS-55, CS-57, and CS-58 invariants are all preserved
  byte-identical. CS-59 layers on top of CS-55 (uses its
  frozenset as the gate) and on top of CS-57 (uses its
  `_rebuild`-tail refresh pattern as the call-site
  convention).

Lock relaxations that explicitly DO NOT require a CS-N bump:

* The disable-only / no-tooltip / no-count-badge choice
  (lock 5). Adding either UI affordance is additive and
  doesn't break the existing predicate.
* The "what counts as a hidden row" predicate's group-member
  branch (lock 2 final paragraph). If the user later flags
  that the whiplash-avoidance behaviour is wrong, narrowing
  to "only count members of expanded groups" is a contained
  edit inside `_has_hidden_rows()`.

Friction points carried forward
-------------------------------

See "Friction points carried forward from Phase 4ah" in
BACKLOG.md. One new 🟢 register entry from step 5 (USER-
CONFIRMED): sidebar `«` toggle + "TDDFT Section:" combobox
should follow Open File / Reload into TDDFT-only chrome in a
future phase. Two open Phase 4ag carry-forwards remain (🟡
axis double-click dialog; 🟢 `_can_group_selection` thin-
alias cleanup). Phase 4af friction #4 ("(N members)" suffix
relocation) still open.

## CS-60 — Unified PlotConfigDialog Notebook + cross-tab pending-edit state model (Phase 4ai)

**Status:** ✅ foundation implemented; per-axis settings continue Phase 4aj+.

The scientific question
-----------------------

CS-23 shipped a single-modal Plot Settings dialog with one
section stack (Fonts / Appearance / Legend / Title-labels) and
an Apply / Save / Cancel button row. As Phase 4ai
double-clicking on a plot axis is meant to open a dedicated
axis-properties dialog — but launching a SECOND modal per axis
fragments the user's mental model (where do you go to change
fonts vs primary-y label vs tertiary tick direction?) and
duplicates plumbing (snapshot, working copy, modal contract).

The user's design call: **one unified configuration dialog**
with Notebook tabs — one Global tab matching today's
PlotSettings, plus one tab per axis role (primary X / secondary
X / primary Y / secondary Y / tertiary Y) reachable both via
the ⚙ button (Global) and via double-clicking the axis region
(that axis's tab). Cross-tab pending edits persist across tab
switches; tab modified state is surfaced as a bullet suffix in
the tab title; the dialog-level button row owns the commit
gestures.

The Phase 4ai answer (CS-60)
----------------------------

Five architectural threads, landed across five commits ahead of
per-axis settings:

**1. Axis-region double-click hit-test (`plot_axis_hit_test.py`).**

Pure module — duck-types the matplotlib MouseEvent so the
classifier is test-friendly without standing up a Figure. The
single public surface is:

```python
@dataclass(frozen=True)
class AxisHit:
    role: str       # "primary_x" | "secondary_x" | "primary_y"
                    # | "secondary_y" | "tertiary_y"
    hit_kind: str   # "spine" | "tick_labels" | "axis_label"

def classify_axis_double_click(
    event,
    axes_by_role,   # dict keyed by CS-44 names: "primary",
                    # "secondary", "tertiary"
    tertiary_offset_frac: float = 1.12,
) -> Optional[AxisHit]
```

Five-band bbox-relative classification (rejects non-double-
clicks, no primary axes, missing/malformed event coords,
degenerate bbox, plot interior, far-outside clicks). Tertiary
band tested first so secondary-y's envelope on the right side
gets clipped at the tertiary spine. When no twinx exists,
right-side clicks classify as primary_y.

Module-level constants:
- `AXIS_ROLES` — five-tuple: `("primary_x", "secondary_x",
  "primary_y", "secondary_y", "tertiary_y")`.
- `HIT_KINDS` — three-tuple: `("spine", "tick_labels",
  "axis_label")`.
- `_TOTAL_BAND_PX = 40` — envelope width around each spine.
- `_SPINE_BAND_PX = 6` — inner sub-band.
- `_TICK_BAND_PX = 18` — middle sub-band.
- `_TERTIARY_BAND_PX = 24` — tertiary spine half-width.

37 pure tests in `TestAxisHitContract`,
`TestRejectPaths`, `TestPrimaryX`, `TestSecondaryX`,
`TestPrimaryY`, `TestPrimaryYRightSpine`, `TestSecondaryY`,
`TestTertiaryY`, `TestSecondaryClippedByTertiary`,
`TestBoundaryConditions`.

**2. PlotConfigDialog Notebook + 6 tab frames.**

`plot_settings_dialog.PlotConfigDialog` (renamed from
`PlotSettingsDialog`; factory renamed
`open_plot_settings_dialog` → `open_plot_config_dialog`).
The module name `plot_settings_dialog.py` and the module-level
dicts `_USER_DEFAULTS` / `_FACTORY_DEFAULTS` /
`_UNIVERSAL_DEFAULTS` are preserved at the same name so
`binah.py`, `project_io.py`, and `test_persistence_phase_a.py`
keep their existing imports.

New module-level constants:
- `_TAB_KEYS` — canonical Notebook pack order: `("global",
  "primary_x", "secondary_x", "primary_y", "secondary_y",
  "tertiary_y")`.
- `_TAB_TITLES` — human-readable tab labels.
- `_AXIS_TAB_PLACEHOLDER_BADGE` — initial italic badge text
  per axis role (Phase 4ak swaps in live "(used by N nodes)"
  / "(unused)" / "(derived)" markers from the host's
  `_axes_by_role` + graph nodes).

The dialog body is now a `ttk.Notebook` parented to a single
outer Frame; six `tk.Frame` tab frames are stored in
`self._tab_frames: dict[str, tk.Frame]`. The Global tab hosts
the legacy four section LabelFrames unchanged (delegated to
`_build_global_tab`); each axis tab hosts a placeholder shell
(`_build_axis_tab_shell`) with bold "Axis: <Title>" header,
italic placeholder badge, "Plots on this axis" LabelFrame
("(populated in Phase 4ak)" hint), separator, "Settings"
LabelFrame ("Per-axis settings land in Phase 4aj+" hint).

API additions on PlotConfigDialog:
- `__init__(..., tab="global")` — pre-select the active tab.
  Unknown keys fall back to `"global"`.
- `select_tab(key)` — runtime tab navigation. Used by the
  factory's "raise existing" path so a second double-click on
  a different axis switches the already-open dialog.
- `current_tab_key() -> str` — for tests and the button row.

19 tests in `TestPlotConfigDialogNotebookPhase4ai`.

**3. CS-60 cross-tab pending-edit state model.**

Per-tab modified marker: `_TAB_TITLES[tab] + " •"` while any
setting on that tab carries uncommitted edits. The bullet
(`_MODIFIED_TAB_SUFFIX = " •"`, IntelliJ-style) is the visual
signal; `_modified_tabs: set[str]` is the source of truth.

Module-level routing map:
- `_KEY_TO_TAB: dict[str, str]` — every working-copy key
  resolves to a Notebook tab. Empty in Phase 4ai (every
  factory key defaults to `"global"` via `_key_to_tab(key)`);
  Phase 4aj+ populates entries as per-axis settings move out
  of the Global tab.

PlotConfigDialog state-management methods:
- `_mark_tab_modified(tab_key)` / `_clear_tab_modified(tab_key)`
  / `_clear_all_modified_tabs()` — per-tab marker mutators.
- `_refresh_tab_title(tab_key)` — drives the Notebook
  tab-text update.
- `_has_uncommitted_changes() -> bool` — True iff Cancel
  would discard something. Two paths: pending edits in
  `_modified_tabs`, or intermediate-Applied edits where
  `config != snapshot` (the CS-23 Cancel-still-reverts
  contract).

Writer wiring: `_on_var_write` / `_on_int_var_write` /
`_on_float_var_write` each call
`self._mark_tab_modified(_key_to_tab(key))` after a successful
write (mid-edit garbage in spinboxes still skips the mark by
returning before tagging).

25 tests in `TestPlotConfigDialogStateModelPhase4ai` +
`TestPlotConfigDialogButtonRowPhase4ai`.

**4. CS-60 four-button row.**

Replaces the CS-23 Apply / Save / Cancel row with
**Save · Apply · Apply to All Tabs · Cancel** — right-aligned
at the Toplevel bottom (outside the Notebook so it applies
dialog-wide). Per CS-23 the Save-as-Default / Reset Defaults /
Factory Reset row inside the Fonts section stays in place;
those buttons affect the working copy only.

- **Save** — `_commit_working_copy` + destroy. Same wording as
  CS-23, cross-tab scope is new.
- **Apply** — `_commit_working_copy`; stay open.
- **Apply to All Tabs** — `_commit_working_copy` first (so the
  host's replication callback reads the new config), then
  invoke `on_apply_all_tabs` if wired. Disabled when callback
  is None. Errors in the callback are logged, not raised.
- **Cancel** — if `_has_uncommitted_changes()`, prompt
  `messagebox.askokcancel("Discard changes?")`; only proceed
  when the user confirms. `_test_silence` returns True so the
  existing CS-23 always-close-on-Cancel test contract holds
  unchanged. Reverts config to snapshot, clears markers,
  destroys.

Constructor extension: `__init__(..., on_apply_all_tabs:
Callable[[], None] | None = None)`. Factory propagates it.

**5. UV/Vis integration — figure double-click → dialog tab.**

`UVVisTab._on_mpl_axis_double_click` is bound to
`button_press_event` in `_build_plot` alongside the existing
`button_release_event` / `scroll_event` wirings. It passes
`event` and `self._axes_by_role` (CS-44 keys) to
`plot_axis_hit_test.classify_axis_double_click` with
`tertiary_offset_frac=_TERTIARY_AXIS_OFFSET_FRAC`. On `None`
it returns silently (interior / single-click). Otherwise it
dispatches:

```python
plot_settings_dialog.open_plot_config_dialog(
    self, self._plot_config,
    on_apply=self._on_plot_config_changed,
    tab=hit.role,
)
```

— same `on_apply` callback, same per-host registry, same modal
contract as the existing ⚙ button. The factory's
raise-existing path uses `select_tab` to switch the active tab
when the dialog is already open. The ⚙ button continues to
open on Global.

10 integration tests in `TestUVVisTabAxisDoubleClickPhase4ai`.

Locks (do not relax without a follow-up CS-N)
---------------------------------------------

1. **`PlotConfigDialog` class name + `open_plot_config_dialog`
   factory.** Module file name `plot_settings_dialog.py`
   preserved; module-level dicts `_USER_DEFAULTS` /
   `_FACTORY_DEFAULTS` / `_UNIVERSAL_DEFAULTS` preserved at the
   same name. The legacy `PlotSettingsDialog` class identifier
   is gone — call sites use the new name. CS-23 subsumed.

2. **`_TAB_KEYS` six-tuple and canonical order.** The Notebook
   pack order matches this tuple. Tests rely on it.

3. **`_TAB_TITLES` content.** Renaming a tab string is a UX
   change with no schema impact, but the tests (and the
   marker logic via `_refresh_tab_title`) pin the exact
   strings. Update tests in lock-step if titles change.

4. **`_KEY_TO_TAB` defaults to `"global"`.** Adding a key
   means the dialog marks a different tab dirty on edit. The
   marker is the source of truth for "what does Cancel
   discard"; mis-mapping a key would mis-attribute a dirty
   tab. Phase 4aj+ adds entries deliberately as per-axis
   settings land.

5. **`_MODIFIED_TAB_SUFFIX = " •"`.** Tests check the literal.
   Replacing the bullet is a deliberate UX choice; do it once,
   in coordination with the test pinning it.

6. **`AxisHit` dataclass shape: `(role, hit_kind)`, frozen.**
   `role` ∈ `AXIS_ROLES`, `hit_kind` ∈ `HIT_KINDS`. Adding a
   field is a non-breaking append; renaming or removing
   breaks every call site.

7. **`classify_axis_double_click` signature:**
   `(event, axes_by_role, tertiary_offset_frac=1.12)`.
   `axes_by_role` keys use CS-44 names (`"primary"`,
   `"secondary"`, `"tertiary"` — all referring to y-axes
   today). The returned `role` uses dialog tab keys
   (`primary_y`, etc.). The asymmetry is intentional —
   classifier translates from figure topology to dialog
   topology.

8. **Five-band hit-test envelope: `_TOTAL_BAND_PX = 40`,
   `_SPINE_BAND_PX = 6`, `_TICK_BAND_PX = 18`,
   `_TERTIARY_BAND_PX = 24`.** Tuning candidates if the
   matplotlib layout ever changes (e.g. wider tick label
   regions on some platforms). Tests are tolerant of small
   shifts (use the constants symbolically) but the values
   themselves are a UX call.

9. **Tertiary spine band tested first** in the classifier.
   Secondary band gets clipped on the right at
   `tertiary_spine_x - _TERTIARY_BAND_PX`. Reversing the order
   would cause secondary-y to swallow the tertiary region.

10. **Button row order: Save / Apply / Apply to All Tabs /
    Cancel, right-aligned.** Right-side alignment matches
    OS-convention modal dialogs. Apply-to-All-Tabs sits
    between Apply and Cancel so it reads as a peer of the
    other commit gestures, not as a destructive action.

11. **Apply to All Tabs commits locally FIRST**, then invokes
    `on_apply_all_tabs`. The host's replication callback
    reads `self._config` to discover what to copy, so the
    ordering matters. Errors from the callback are logged,
    not raised — the local commit must complete.

12. **Cancel-with-pending shows
    `messagebox.askokcancel("Discard changes?")`.** True
    proceeds (default in `_test_silence`); False keeps the
    dialog open. `_has_uncommitted_changes` is the predicate.

13. **UV/Vis double-click integration** is wired in
    `UVVisTab._build_plot` via
    `self._canvas.mpl_connect("button_press_event",
    self._on_mpl_axis_double_click)`. The handler passes
    `self._axes_by_role` directly and uses the module constant
    `_TERTIARY_AXIS_OFFSET_FRAC`. Other tabs (XANES / EXAFS /
    TDDFT / Compare) wire equivalently when they adopt the
    renderer architecture; they're not wired today.

14. **`PlotConfigDialog` is tab-type-agnostic** by design —
    the host owns `on_apply` and `on_apply_all_tabs` semantics.
    XANES / EXAFS will each construct the dialog with their
    own `_plot_config` dict and their own callbacks. Cross-
    tab-type replication is NOT a thing today; "Apply to All
    Tabs" replicates only to same-tab-type siblings (e.g.
    other UV/Vis tabs in the notebook).

Lock relaxations
----------------

- **CS-23 → CS-60.** CS-23's `_do_save` / `_do_apply` /
  `_do_cancel` / `_on_close_requested` / `_build_button_row`
  locks no longer apply — the methods are renamed/restructured
  on `PlotConfigDialog`. The button-row vocabulary (Apply /
  Save / Cancel) is broadened to (Save / Apply / Apply to All
  Tabs / Cancel); the locked "Apply commits and stays open,
  Save commits and closes, Cancel reverts to snapshot"
  semantics persists.

Carry-forward
-------------

- Per-axis settings (label override, range / autoscale, tick
  spacing, scale linear/log, per-axis tick direction) land in
  Phase 4aj+.
- Live "(used by N nodes)" / "(unused)" / "(derived)" axis-tab
  badge replaces `_AXIS_TAB_PLACEHOLDER_BADGE` in Phase 4ak.
- "Plots on this axis" list (read-only) populates in 4ak;
  Move-to picker writes `y_axis` style key in 4al.
- `_USER_DEFAULTS` tab-type split (universal vs per-tab-type
  axis-label keys) lands when the dialog wires into a second
  tab type. Carry-forward register entry added in BACKLOG.
- Twin-X full wiring (matplotlib `twinx()` with wavelength↔
  energy transform, bidirectional range coupling) is a
  separate, larger feature register entry. Today the Notebook
  has a Secondary X tab and double-clicking the top spine
  opens it; the tab content is shell-only.
- `hit_kind` from the classifier is recorded on `AxisHit` but
  ignored at the dialog level — every band of the same axis
  opens the same tab. Future phases can branch on it (e.g.
  tick-label click jumps to the Ticks section once that
  lands).
- "Apply to All Tabs" callback is unwired today — Binah needs
  the notebook-iterator logic before this button does anything.
  Polish-phase register entry.

Tests
-----

- 37 pure tests in `test_plot_axis_hit_test`.
- 19 tests in
  `test_plot_settings_dialog.TestPlotConfigDialogNotebookPhase4ai`.
- 25 tests in
  `test_plot_settings_dialog.TestPlotConfigDialogStateModelPhase4ai` +
  `TestPlotConfigDialogButtonRowPhase4ai`.
- 10 integration tests in
  `test_uvvis_tab.TestUVVisTabAxisDoubleClickPhase4ai`.

Total: 91 new tests; full suite 1113 (was 1022).

See "Friction points carried forward from Phase 4ai" in
BACKLOG.md. Two new register entries from step 5:
`_USER_DEFAULTS` tab-type split (USER-FLAGGED — surfaced by
the user during step 5 of Phase 4ai); Twin-X full feature
(USER-FLAGGED — same step). Five Claude-surfaced
notes: Apply-to-All-Tabs unwired; live axis-tab badges
deferred to 4ak; `hit_kind` ignored at dialog level; tertiary
x-axis is not classifiable today; band-size tuning if
matplotlib layout changes.

---

## CS-61 — tick_direction relocation to per-axis tabs + `_KEY_TO_TAB` dirty-pin pattern (Phase 4aj)

**Status:** ✅ implemented; first slice of the multi-phase
per-axis settings ladder (Phase 4aj→4an).

The scientific question
-----------------------

CS-60 (Phase 4ai) shipped the unified `PlotConfigDialog`
Notebook with a Global tab and five per-axis shells, but the
shells carried only a static "(populated in Phase 4ak)" plot
list and a "Per-axis settings land in Phase 4aj+." placeholder
label. The user had explicitly requested that per-axis
settings start landing one slice at a time, smallest-first, so
the ladder pattern that ships in 4aj propagates cleanly
through 4ak/4al/4am/4an without committing to schema-invention
decisions early.

The Phase 4aj answer (CS-61)
----------------------------

**Pick the smallest possible real relocation:** the existing
`tick_direction` Radiobutton row from the Plot Settings →
Appearance section (CS-56). Single setting, three values
("in" / "out" / "inout"), no schema change (still uses the
flat `_USER_DEFAULTS["tick_direction"]` slot), and the widget
is mirrored across all five per-axis tabs so the user sees
the same control wherever they hover.

**Mirrored-widget / shared-var / dirty-pin pattern.** Three
architectural locks land together:

1. **The widget exists once per per-axis tab.** Each non-
   Global Notebook tab's "Settings" `LabelFrame` builds a
   "Tick direction:" `Label` + a three-`Radiobutton` row
   (In / Out / Both) via the new
   `_build_axis_tab_settings(parent, role)` helper called
   from `_build_axis_tab_shell`.

2. **All five tabs share ONE Tk var.** The first axis tab
   built (canonical pack order: `primary_x`) creates the
   `tk.StringVar`, registers the trace callback + refresh
   closure, and stashes it as
   `self._control_vars["tick_direction"]`. Each subsequent
   axis tab calls `self._control_vars.get("tick_direction")`
   and reuses the same var. Result: editing the radio on
   one tab visually updates the radios on the other four
   tabs in real time. The schema stays flat — a single
   working-copy key `tick_direction`.

3. **The dirty marker pins to one tab.** A new module-level
   `_KEY_TO_TAB` dict carries the first explicit entry —
   `"tick_direction": "primary_x"`. The `_key_to_tab(key)`
   helper resolves the dirty tab for any working-copy key;
   keys not in the dict default to `"global"` per CS-60.
   The pin is independent of the user's currently visible
   tab: editing tick_direction on Primary Y still marks
   Primary X dirty, and only Primary X (no five-bullet
   flood).

**Plot Settings → Appearance section changes.** The Tick
direction `Label` + radio frame at row 3 is removed cleanly;
`tertiary_axis_offset` slides from row 4 → row 3 to keep the
section dense. `grid_color` and `tertiary_axis_offset` stay
in Appearance — the rest of CS-56 is unchanged. The factory
default key `_FACTORY_DEFAULTS["tick_direction"] = "in"` is
NOT modified; CS-56's Phase 4ae factory-default flip stays
locked.

**Default lookup routes through `_FACTORY_DEFAULTS`.** The
new helper falls back to `_FACTORY_DEFAULTS["tick_direction"]`
rather than a hard-coded `"in"` literal so a future schema
flip cannot drift between the Appearance and per-axis
builders. Same idiom as `_make_int_spinbox` /
`_make_bool_checkbox` / `_make_colour_swatch` already use.

Locks (CS-61)
-------------

These invariants are pinned by
`TestPlotConfigDialogTickDirectionRelocationPhase4aj` and the
updated Phase 4ai test classes:

1. **`_KEY_TO_TAB` is a `dict[str, str]`** carrying at least
   the entry `{"tick_direction": "primary_x"}`. Future
   per-axis relocations extend the dict; the default branch
   of `_key_to_tab(key)` still returns `"global"` for any
   unmapped key. Phase 4aj is the canonical relaxation of
   CS-60 lock 4 (the routing map was empty in 4ai).

2. **`tick_direction` widget exists on every per-axis tab.**
   Each of the five non-Global tabs builds a Tick direction
   Radiobutton row in its "Settings" `LabelFrame`. The Global
   tab does NOT carry the widget (it lived in
   `_build_section_appearance` pre-4aj). The pre-4aj
   placeholder Label ("Per-axis settings land in Phase
   4aj+.") is gone.

3. **All five radios share one Tk var.** Exactly one entry
   in `self._control_vars` is registered for
   `"tick_direction"` (a `tk.StringVar`). Every Radiobutton
   across every per-axis tab references the same var name
   (matplotlib backend identity check via
   `str(radio.cget("variable"))`). Schema stays flat:
   `_USER_DEFAULTS["tick_direction"]` is a single string,
   not a per-role dict.

4. **Edit on any tab marks ONLY Primary X dirty.** Calling
   `dlg.select_tab("primary_y")` and then
   `dlg._control_vars["tick_direction"].set("out")` results
   in `dlg._modified_tabs == {"primary_x"}`. Not Primary Y;
   not the full set of five.

5. **`_build_axis_tab_settings(parent, role)` is the per-axis
   tab body builder.** Lifted out of `_build_axis_tab_shell`;
   called once per non-Global role. Future per-axis ladder
   phases extend this helper with additional widgets (axis
   label override, range/autoscale, tick spacing, etc.).

6. **`_build_section_appearance` no longer grids
   `tick_direction`.** Row 3 (label + radio frame) is gone.
   `tertiary_axis_offset` is now row 3 (was row 4). The
   relaxed CS-56 invariant is: `_build_section_appearance`
   builds Grid + Grid colour + Background + Tertiary axis
   offset, in that grid-row order.

7. **`_FACTORY_DEFAULTS["tick_direction"]` value is
   unchanged.** Still `"in"`. The relocated widget reads
   from `_FACTORY_DEFAULTS["tick_direction"]` (not a literal)
   so a future schema flip would propagate without code edit
   in the per-axis builder.

8. **Apply / Factory Reset preserve the relocated widget's
   binding.** `_do_apply` commits `self._working["tick_direction"]`
   into `self._config` and clears `_modified_tabs`.
   `_do_factory_reset` restores `"in"` via
   `_refresh_widgets_from_working` → the registered
   `_control_refresh["tick_direction"]` closure → the shared
   var → every per-axis tab's radio reflects the reset value.

Lock relaxations (anticipated for Phase 4ak)
--------------------------------------------

- **Shared-var goes away.** Phase 4ak invents nested
  `_USER_DEFAULTS["axes"][role]["tick_direction"]` (or
  equivalent) and each tab gets its own per-axis Tk var.
  Editing on Primary Y stops updating Primary X visually.
- **Dirty-pin generalises.** With per-axis vars,
  `_KEY_TO_TAB["tick_direction"]` either drops out
  altogether (each radio writes through its tab-scoped
  helper, marking its own tab dirty) or becomes
  `_KEY_TO_TAB[("tick_direction", role)] = role` (per-key
  per-axis routing). The Phase 4aj "edit on Y marks X"
  friction clears in this step.
- **Flat schema relaxes.** `_USER_DEFAULTS` grows the
  `"axes"` sub-dict; the manifest's `plot_defaults` key
  (CS-46) accordingly evolves. Migration shim translates
  legacy flat `tick_direction` to `axes.{role}.tick_direction`
  on load.

Friction points carried forward
-------------------------------

- **Shared-var UX is dishonest by design (Claude-surfaced).**
  Editing on Primary Y updates the radio on Primary X (and
  the other three). Acknowledged trade-off; the brief
  authorized it for 4aj.
- **Dirty pin is counterintuitive (Claude-surfaced).** "I
  edited on Primary Y but the bullet appeared on Primary
  X" — first-time-user confusion. Folds into the Phase 4ak
  per-axis schema invention.
- **`TestAppearanceSectionPhase4ae` class name drift (USER-
  FLAGGED 🟢).** The class still contains
  `test_tick_direction_factory_default_is_in` +
  `test_factory_reset_restores_new_appearance_keys` even
  though tick_direction no longer lives in Appearance.
  Tests stay correct (factory-default schema invariants);
  the class name is the lie. Rename when a future refactor
  naturally touches the class. No register entry.
- **`_build_axis_tab_settings` is single-purpose today.**
  Tick direction is the only widget. Phase 4ak generalises
  the helper when it adds the second per-axis widget (axis
  label override mirror).

Tests
-----

- 13 new tests in
  `test_plot_settings_dialog.TestPlotConfigDialogTickDirectionRelocationPhase4aj`.
- 2 pre-existing Phase 4ai tests updated in place
  (`test_axis_tab_shell_carries_phase_4aj_placeholder`
  renamed to
  `test_axis_tab_shell_carries_real_settings_widget_post_phase_4aj`
  with inverted assertion; `test_key_to_tab_defaults_to_global`
  narrowed to skip keys in `_KEY_TO_TAB`).

Total: +13 new; full suite 1126 (was 1113).

See "Friction points carried forward from Phase 4aj" in
BACKLOG.md. One new USER-FLAGGED register entry from step 5:
external-output plot style presets (J. Am. Chem. Soc. /
PowerPoint / etc.) with reference Jupyter notebook code the
user offered to lift from. One USER-FLAGGED 🟢 friction note:
`TestAppearanceSectionPhase4ae` class-name drift.

---

## CS-62 — Per-axis schema invention + axis_label_override + plots_by_role inventory (Phase 4ak)

**Status:** ✅ implemented; second slice of the multi-phase
per-axis settings ladder (Phase 4aj→4an), the schema-
invention pivot point.

The scientific question
-----------------------

Phase 4aj (CS-61) shipped the smallest possible per-axis
relocation by keeping the schema flat: one Tk var shared
across all five tabs, dirty marker pinned to Primary X, the
working-copy key `tick_direction` still a single string. Two
acknowledged frictions resulted: (a) editing the radio on
Primary Y visually flipped the Primary X radio (shared-var
UX dishonesty); (b) the dirty bullet showed on Primary X
even when the user edited Primary Y (dirty-pin
counterintuitive). Both were authorised for 4aj and queued
for 4ak's schema-invention resolution. The per-axis ladder
also needed: (c) the read-only "Plots on this axis" list
inside each per-axis tab populated from the host's live
graph, (d) a new per-axis `axis_label_override` key for
fine-grained label customisation, and (e) a Global-tab
mirror surface for the axis-label overrides so the user can
edit all five from one place.

The Phase 4ak answer (CS-62)
----------------------------

**Nested schema in `_FACTORY_DEFAULTS["axes"][role][key]`.**
The factory dict grows a new `"axes"` sub-dict with one
entry per per-axis role (`primary_x` / `secondary_x` /
`primary_y` / `secondary_y` / `tertiary_y`); each per-role
dict carries `tick_direction` (default `"in"`) AND the new
`axis_label_override` (default `""`). The top-level flat
`_FACTORY_DEFAULTS["tick_direction"]` is REMOVED. The per-
axis-key registry `_AXIS_KEYS = ("tick_direction",
"axis_label_override")` documents the schema growth path
for future phases.

**Idempotent migration shim.** A new module-level
`migrate_plot_config(config: dict) -> dict` (returns the
same dict for chaining) translates legacy flat
`config["tick_direction"]` into the nested
`config["axes"][role]["tick_direction"]` slot for every
role, then deletes the legacy key. Each per-role sub-dict
missing keys gets backfilled from
`_FACTORY_DEFAULTS["axes"][role]`. **Idempotency invariant:**
a non-`None` legacy flat `tick_direction` wins over any
per-role slot already present (the factory pre-seed always
populates the slot, but the user's legacy intent must
override the factory default). Other per-axis keys take the
existing slot when present.

**Migration runs at dialog construction time + Reset paths.**
The dialog's `__init__` deep-copies `_FACTORY_DEFAULTS`,
updates from the caller's config, then calls
`migrate_plot_config(self._working)`. `_load_into_working`
(Reset Defaults / Factory Reset) also runs the shim so a
legacy `_USER_DEFAULTS` saved by an older session migrates
on every reset gesture. The renderer reads through helpers
that fall back gracefully — a pre-migration `_plot_config`
still renders identically because `_per_axis_tick_direction`
prefers nested > legacy flat > factory default.

**Per-axis Tk vars in `_axis_control_vars[(role, key)]`.**
The dialog's pre-CS-62 flat `_control_vars` dict gains a
sibling `_axis_control_vars: dict[tuple[str, str],
tk.Variable]` keyed by `(role, key)` pairs. Each per-axis
tab's widget builder calls
`self._make_axis_string_var(role, key)` which is **idempotent
on the `(role, key)` pair** — first call builds the var +
trace + refresh closure; subsequent calls with the same pair
return the cached var. The Global "Per-axis label
overrides" mirror section reuses this idempotency to share
Tk vars with the per-axis tab Entries: when the Global
section runs first (canonical Notebook pack order, Global is
tab[0]), the per-axis tab Entries reuse the var the mirror
section already built.

**Per-axis writer `_on_axis_var_write(role, key, value)`.**
New writer analogue of `_on_var_write` that carries the
role directly and marks `self._mark_tab_modified(role)`
without going through `_key_to_tab`. The `_suspend_writes`
re-entrancy guard works identically. `_KEY_TO_TAB`'s
`tick_direction` entry from CS-61 is REMOVED (the dict is
now empty); per-axis keys never route through `_key_to_tab`.

**New `_build_axis_tab_settings` body — two widgets, inline.**
The CS-61 helper signature `(parent, role)` is preserved
(canonical lock relaxation: "the helper either grows
additional widget builders inline or splits into per-widget
helpers"). It now builds: (a) Tick direction Radiobutton row
(unchanged shape, but bound to per-axis var); (b) Axis
label override Entry with a "(empty = auto)" trailing label.
Both use `_make_axis_string_var` for the per-axis var.

**New `_build_section_axis_labels` Global section.** Five
rows, one per `_TAB_KEYS` role (minus `"global"`). Each row:
bold `"<Tab Title>:"` Label + Entry whose `textvariable`
shares a Tk var with the per-axis tab's Entry via
`_make_axis_string_var`'s idempotency. `_DEFAULT_SECTIONS`
extends to include `"axis_labels"` (appended; canonical
order is fonts → appearance → legend → title_labels →
axis_labels). `_SECTION_TITLES["axis_labels"]` =
`"Per-axis label overrides"`.

**`plots_by_role` constructor kwarg + Listbox rendering.**
The dialog constructor + `open_plot_config_dialog` factory
both gain a `plots_by_role: dict[str, tuple[str, ...]] |
None = None` parameter. None means the host didn't compute
the inventory; the per-axis tabs fall back to the italic
`"(no plots on this axis)"` placeholder. Roles whose tuple
is empty get the same placeholder. For populated roles, a
read-only `tk.Listbox` (height capped at `min(6, n)`,
`state="disabled"`) renders the plot labels.

**Renderer wiring in `uvvis_tab._redraw` (visible-effect
features).** New module-level helpers in `uvvis_tab.py`:

- `_axis_label_override(cfg, tab_role) -> str` returns the
  per-axis override defensively (handles missing `axes`
  sub-dict, missing role, missing key). Empty string is
  the factory default meaning "defer to existing label
  resolution".
- `_per_axis_tick_direction(cfg, tab_role) -> str` resolves
  with nested → legacy flat → factory fallback chain so a
  pre-migration `_plot_config` keeps rendering.
- `_enumerate_plots_by_role(spectrum_nodes,
  second_derivative_nodes, peak_list_nodes, *,
  secondary_x_active) -> dict[str, tuple[str, ...]]` walks
  visible plottable nodes, routes Y axes via
  `_resolve_y_axis_role` (honouring per-style `y_axis`
  overrides from CS-50), and mirrors primary_x onto
  secondary_x when the wavelength↔energy twin is active.
- `_Y_AXIS_ROLE_TO_TAB` translates `_AXIS_ROLES` keys
  (`primary` / `secondary` / `tertiary`) into the dialog's
  per-axis tab keys (`primary_y` / `secondary_y` /
  `tertiary_y`).

Renderer changes at the label-setting points:
- Primary X label: non-empty `axis_label_override` wins
  over the legacy `xlabel_mode` auto/custom path.
- Primary Y label: non-empty override wins over both
  `ylabel_mode == "custom"` and the auto resolution; the
  role iteration loop short-circuits primary when an
  override is active.
- Secondary X (wavelength↔energy twin): non-empty
  override replaces the hardcoded `"λ (nm)"` string.
- Secondary Y / tertiary Y: non-empty override replaces
  the `_resolve_y_axis_label` result.

Tick direction reads through
`_per_axis_tick_direction(cfg, "primary_x")` and applies
uniformly to every axis — **per-axis tick rendering is
explicitly deferred to Phase 4al** per the decision lock.
The schema STORES per-axis values but the renderer doesn't
yet APPLY them per-axis. The user observed this directly
("Editing the Secondary X tick direction radio moves the
Primary X axis ticks, not the Secondary X axis"); this is
honest-but-incomplete and queued for the next ladder slice.

**Host integration on UVVisTab.** New `_compute_plots_by_role`
method builds the inventory at dialog open time via the
three live-node helpers + the `_show_nm_axis` +
`_x_unit.get()` state. Both dialog open paths
(`_open_plot_settings` for the ⚙ button + `_on_mpl_axis_double_click`
for the CS-60 double-click hit-test) pass `plots_by_role=`
into `open_plot_config_dialog`.

**`_UNIVERSAL_DEFAULTS` upgrades from shallow to deep copy.**
Pre-CS-62 used `dict(_FACTORY_DEFAULTS)`; CS-62 uses
`copy.deepcopy(_FACTORY_DEFAULTS)` because the new `axes`
sub-dict is mutable. A shallow copy would let mutations on
one leak into the other. Test `test_universal_defaults_is_deep_copy_of_factory`
pins this — every per-role sub-dict is a distinct object.

Locks (CS-62)
-------------

These invariants are pinned by
`TestPlotConfigDialogPerAxisSchemaPhase4ak` (new),
`TestPlotConfigDialogTickDirectionRelocationPhase4aj`
(inverted from the CS-61 shape),
`TestEnumeratePlotsByRolePhase4ak` (new, unit tests on
the enumerator), and `TestUVVisTabPerAxisSchemaPhase4ak`
(new, host integration):

1. **`_FACTORY_DEFAULTS["axes"]` is a `dict[str, dict[str,
   Any]]`** keyed by the five per-axis roles (`primary_x`,
   `secondary_x`, `primary_y`, `secondary_y`,
   `tertiary_y`). Each role's sub-dict carries exactly the
   keys in `_AXIS_KEYS`: `tick_direction` (default `"in"`)
   and `axis_label_override` (default `""`).

2. **Top-level `_FACTORY_DEFAULTS["tick_direction"]` is
   absent.** The CS-61 schema lock relaxed; the flat key
   is gone (canonical CS-61 relaxation per its lock-
   relaxations block). `_UNIVERSAL_DEFAULTS` mirrors this
   absence.

3. **`_AXIS_KEYS = ("tick_direction", "axis_label_override")`.**
   The canonical per-axis-key registry. Future phases
   extend this tuple (range / autoscale / scale type /
   tick spacing keys land here).

4. **`_UNIVERSAL_DEFAULTS` is a deep copy of
   `_FACTORY_DEFAULTS`.** Test pins `u is not f`, `u["axes"]
   is not f["axes"]`, AND `u["axes"][role] is not
   f["axes"][role]` for every role.

5. **`migrate_plot_config(config)` is idempotent.** Tests:
   running on a fully-migrated config is a no-op; running
   on an empty config populates the full nested form;
   running on a legacy-flat config moves the value into
   every per-role slot AND deletes the legacy key. A
   non-`None` legacy `tick_direction` wins over factory-
   default per-role slots (the factory pre-seed is the
   bootstrap shape, not the final user state). Test
   `test_migrate_partial_nested_fills_gaps` pins that
   nested values present in the input are preserved while
   missing keys get backfilled.

6. **`_KEY_TO_TAB` dict is empty.** CS-61's
   `{"tick_direction": "primary_x"}` entry removed.
   `_key_to_tab(key)` returns `"global"` for every key
   that resolves through it. Per-axis dirty marking
   bypasses this map entirely via `_on_axis_var_write`.

7. **Per-axis Tk vars live in `_axis_control_vars[(role,
   key)]`.** Each per-axis tab owns its own var per key;
   no shared var. Five distinct `(role, "tick_direction")`
   var names + five distinct `(role, "axis_label_override")`
   var names. `self._control_vars` carries no
   `"tick_direction"` entry post-CS-62.

8. **`_make_axis_string_var(role, key)` is idempotent on
   the `(role, key)` pair.** Cached lookup returns the
   existing var. The Global "axis_labels" mirror section
   reuses this to share Tk vars with the per-axis tab
   Entries.

9. **`_on_axis_var_write(role, key, value)` marks the
   role's tab dirty.** Not Global; not Primary X; the
   role itself. Test
   `test_edit_marks_role_specific_tab_dirty` and
   `test_axis_label_override_edit_marks_role_tab_dirty`
   pin both keys.

10. **`_DEFAULT_SECTIONS` ends with `"axis_labels"`.** The
    new Global section sits at the bottom of the Global
    tab below Title and labels. `_SECTION_TITLES["axis_labels"]
    = "Per-axis label overrides"`.

11. **Global "Per-axis label overrides" section has five
    Entry widgets** — one per role (excluding Global) in
    `_TAB_KEYS` canonical order. Each Entry's
    `textvariable` matches the corresponding per-axis tab
    Entry's `textvariable` (shared var, idempotency).

12. **`plots_by_role` constructor kwarg accepts `None` or
    `dict[str, tuple[str, ...]]`.** `None` and any
    role-missing-or-empty render the italic
    `"(no plots on this axis)"` placeholder Label.
    Populated tuples render a `tk.Listbox` with
    `state="disabled"`, `height=min(6, n)`.

13. **Renderer reads `_axis_label_override(cfg, tab_role)`
    at every axis label setter** (primary_x, primary_y,
    secondary_x, secondary_y, tertiary_y). A non-empty
    string wins over the existing auto/custom resolution.

14. **`_enumerate_plots_by_role` invariants:** primary_x
    lists every visible plot; secondary_x mirrors
    primary_x when `secondary_x_active=True`, empty
    otherwise; Y axes route via `_resolve_y_axis_role`;
    invisible nodes are skipped silently. Returned dict
    always has all 5 keys (even if empty tuples).

Lock relaxations (anticipated for Phase 4al onward)
---------------------------------------------------

- **Per-axis tick rendering.** The renderer reads
  `_per_axis_tick_direction(cfg, "primary_x")` and applies
  uniformly today. 4al's canonical relaxation: split
  `ax.tick_params(direction=...)` into per-axis-role calls
  reading `axes[<role>]["tick_direction"]` per axis. The
  hardcoded `sec.tick_params(axis="x", direction="in",
  labelsize=8)` for the wavelength twin also reads through
  the helper.
- **`_AXIS_KEYS` grows.** Phase 4al adds the "Move to ▾"
  picker for `y_axis` style routing (CS-50 follow-up; may
  or may not live in `_AXIS_KEYS` depending on whether it
  becomes a per-axis-tab Plot Settings key or stays a
  per-style key); Phase 4am adds range / autoscale / scale-
  type keys; Phase 4an adds tick spacing + per-axis grid +
  per-axis colour pickers.
- **Listbox interactivity.** Phase 4ak ships read-only
  (`state="disabled"`). A future enhancement could enable
  single-click selection to jump-scroll the sidebar
  ScanTreeWidget to the corresponding node.
- **`plots_by_role` freshness.** Today the dialog stores
  the inventory at construction time. Reactivity is queued
  with the live-preview register entry (CS-06 / CS-23 /
  CS-60 working-copy semantics).

Friction points carried forward
-------------------------------

- 🟠 **USER-FLAGGED bug: Secondary X tick direction
  changes Primary X, not Secondary X.** Resolution lands
  in Phase 4al's per-axis tick rendering wire-up. Folds
  into the canonical per-axis ladder above.
- 🟡 **USER-FLAGGED Live-preview vs Apply button.** New
  canonical register entry; meta-UX question across the
  dialog ecosystem.
- 🟡 **USER-FLAGGED Apply-to-all icon on per-axis tabs.**
  New canonical register entry; UI consistency with the
  ScanTreeWidget per-row send-to-compare icon.
- 🟡 **USER-FLAGGED Axis nomenclature rename.** New
  canonical register entry; massive cross-codebase rename
  (CS-44 / CS-50 / CS-60 / CS-61 / CS-62 locks affected).
- 🟡 **USER-FLAGGED Rich-text axis labels (mathtext).**
  New canonical register entry; small enabling phase.
- 🟢 **Dual-surface primary X / Y label
  (Claude-surfaced).** `axis_label_override` + the legacy
  Title-and-labels section's X/Y label rows are two
  surfaces editing the same label. Override wins via
  precedence.
- 🟢 **`plots_by_role` frozen at open time
  (Claude-surfaced).** Folds into the live-preview
  register entry above.
- 🟢 **Listbox `state="disabled"` (Claude-surfaced).**
  Read-only today; jump-to-node click is a future
  enhancement.
- 🟢 **`TestAppearanceSectionPhase4ae` class-name drift
  (USER-FLAGGED 🟢, Phase 4aj carry-over).** Two tests
  inside got updated in Phase 4ak for the nested
  schema — the class stays correct in content, but the
  name still misleads. Rename when a future Appearance
  section refactor naturally touches the class.

Tests
-----

- New `TestPlotConfigDialogPerAxisSchemaPhase4ak` class:
  26 tests covering nested factory shape, migration shim
  semantics, per-axis vars, axis_label_override widget,
  Global mirror section, plots_by_role rendering, and
  end-to-end Apply / Reset Defaults paths.
- New `TestEnumeratePlotsByRolePhase4ak` class: 7 unit
  tests against the module-level `_enumerate_plots_by_role`
  helper (no Tk needed).
- New `TestUVVisTabPerAxisSchemaPhase4ak` class: 10
  integration tests on the host — `_compute_plots_by_role`,
  the two dialog open paths threading the inventory, and
  the renderer's axis_label_override application on all
  five axes.
- `TestPlotConfigDialogTickDirectionRelocationPhase4aj`
  (CS-61) inverted in place: shared-var assertions flipped
  to per-axis-var, dirty-pin-to-primary-x flipped to
  dirty-mark-the-edited-role, write-to-flat flipped to
  write-to-nested. Static layout tests (label absent from
  Appearance, label + 3 radios on every per-axis Settings
  frame) stay AS-IS.
- `TestAppearanceSectionPhase4ae`: two tests updated for
  the nested schema (`test_tick_direction_factory_default_is_in`
  + `test_factory_reset_restores_new_appearance_keys`).
- `test_plot_config_inherits_inward_tick_default` in
  `test_uvvis_tab.py` updated to read the nested form.

Total: +39 new across the four new test classes plus
inversions. Full suite 1165 (was 1126).

See "Friction points carried forward from Phase 4ak" in
BACKLOG.md. **Five new USER-FLAGGED register entries from
step 5:** live-preview vs Apply (meta-UX); apply-to-all
icon on per-axis tabs (UI consistency); axis nomenclature
rename to position-based names; rich-text axis labels
(mathtext); plus ONE user-surfaced bug folded into the
canonical per-axis ladder (Secondary X tick direction
mis-applied — resolution lands in Phase 4al per the
deferred per-axis tick rendering scope).

---

## CS-63 — Per-axis tick rendering + Move-to picker on Y-axis tabs (Phase 4al)

### Responsibility

Second slice of the per-axis settings ladder (CS-60 → CS-61 →
CS-62 → CS-63 → CS-64 → CS-65). Wires the renderer to consume
the per-axis `tick_direction` slots CS-62 invented, AND adds the
Plot Settings dialog's Y-axis-tab Move-to Combobox that mutates
the CS-50 `style["y_axis"]` value via the host's
`graph.set_style`. Resolves the Phase 4ak step-5 USER-FLAGGED
"Secondary X tick direction changes Primary X" bug.

### Renderer changes — `uvvis_tab._redraw`

The single uniform `tick_dir = _per_axis_tick_direction(cfg,
"primary_x")` read (CS-62 transitional behaviour) splits into
five per-axis-role reads at the call sites:

| Call site | Reads slot | Applies to |
|---|---|---|
| `ax.tick_params(axis="x", ...)` | `primary_x` | Primary x-axis ticks |
| `ax.tick_params(axis="y", ...)` | `primary_y` | Primary y-axis ticks |
| `ax_new.tick_params(axis="y", ...)` in `get_axis` for secondary twin | `secondary_y` | Right-side secondary y-axis |
| `ax_new.tick_params(axis="y", ...)` in `get_axis` for tertiary twin | `tertiary_y` | Offset right-side tertiary y-axis |
| `sec.tick_params(axis="x", ...)` for the wavelength↔energy sibling | `secondary_x` | Top secondary x-axis (was hardcoded `"in"`) |

The `tick_label_font_size` (a Global key) still applies
uniformly to every tick_params call as `labelsize`. The
secondary_x sibling axis keeps its 8pt labelsize (separate from
the Global `tick_label_font_size` per the existing CS-29 / CS-62
convention).

### Dialog changes — `plot_settings_dialog`

* New module constants:
  * `_Y_AXIS_TAB_KEYS: frozenset[str]` = `{"primary_y", "secondary_y", "tertiary_y"}`.
  * `_MOVE_TO_OPTIONS: tuple[tuple[str, Optional[str]], ...]`
    — four `(label, tab_role_key | None)` pairs: `"Default
    (by NodeType)"` → `None`; `"Primary Y"` → `"primary_y"`;
    `"Secondary Y"` → `"secondary_y"`; `"Tertiary Y"` →
    `"tertiary_y"`.
  * `_MOVE_TO_LABELS: tuple[str, ...]` + `_MOVE_TO_VALUE_BY_LABEL:
    dict[str, Optional[str]]` derived helpers.
* `_build_axis_tab_plots` walks `_Y_AXIS_TAB_KEYS` to decide
  Listbox `state`: Y-axis tabs use `tk.NORMAL` (selectable
  rows); X-axis tabs keep `tk.DISABLED` (CS-62 lock preserved
  for the X tabs).
* New helper `_build_move_to_picker(parent, role, listbox)`
  renders a `"Move selected to:"` Label + `ttk.Combobox` row
  below the Listbox on the three Y-axis tabs. The Combobox is
  `state="readonly"` listing the four `_MOVE_TO_LABELS` entries.
* New method `_on_move_to_choose(role, listbox, var)` extracted
  from the closure so tests can drive the routing path directly
  without relying on Tk's `<<ComboboxSelected>>` virtual event
  dispatch (the dispatch turned out to be flaky in suite mode —
  fired synchronously in isolation but intermittently dropped
  when many Toplevels lived in the same root). The bind on
  `<<ComboboxSelected>>` invokes the method via a one-line
  trampoline.
* Constructor + module factory `open_plot_config_dialog` gain
  `on_route_plot: Callable[[str, str, Optional[str]], None] | None`
  kwarg. Signature: `(source_tab_role, label, target_tab_role)`.
  Both role arguments live in the dialog's tab-role-key space
  throughout; the host owns the translation into the CS-50
  `style["y_axis"]` value when it writes.

### Host wiring — `uvvis_tab`

* Both `_open_plot_settings` (⚙ button) and
  `_on_mpl_axis_double_click` (axis double-click hit-test)
  thread `on_route_plot=self._on_route_plot_from_dialog` through
  `open_plot_config_dialog`.
* New host method `_on_route_plot_from_dialog(source_tab_role,
  label, target_tab_role)`:
  * Translates `target_tab_role` ∈ {`"primary_y"`, `"secondary_y"`,
    `"tertiary_y"`, `None`} into the CS-50 style value
    (`"primary"`, `"secondary"`, `"tertiary"`, `None`) via the
    inverse of `_Y_AXIS_ROLE_TO_TAB`.
  * Walks visible spectrum + second-derivative + peak-list
    nodes; finds the first match whose `node.label == label` AND
    whose `_resolve_y_axis_role(node.type, node.style) ==
    source_style` (source disambiguates label collisions across
    axes).
  * Writes `style["y_axis"] = target_style` via `graph.set_style`.
  * Defensive silent no-ops on: unknown source role, no matching
    visible node, invisible node match.
* `set_style` fires `NODE_STYLE_CHANGED` which the tab's
  subscription consumes → `_redraw`. No manual redraw call.

### Locks taken (Phase 4al)

* Renderer signature of `_per_axis_tick_direction(cfg,
  tab_role)` unchanged (CS-62 lock preserved); only call-site
  ROLE arguments change.
* `get_axis(role)` signature + lazy-twin creation order
  unchanged. The new per-role tick read is internal to the
  closure body.
* Module factory `open_plot_config_dialog` signature gains an
  ADDITIVE kwarg; existing call sites stay backward-compatible
  (default `None`).
* `PlotConfigDialog.__init__` signature gains an ADDITIVE kwarg.
* `_AXIS_KEYS` stays `("tick_direction", "axis_label_override")`
  — the Move-to picker writes a per-NODE style key, NOT a
  per-axis schema slot.
* `_MOVE_TO_OPTIONS` tuple shape + four-entry value set
  (`None`, `"primary_y"`, `"secondary_y"`, `"tertiary_y"`).
* `_Y_AXIS_TAB_KEYS` frozen set of three keys (the three
  CS-44 Y-axis roles mapped through `_Y_AXIS_ROLE_TO_TAB`).
* Callback signature `on_route_plot(source_tab_role, label,
  target_tab_role)` — three positional, tab-role-key space
  throughout, `None` only valid for `target_tab_role`.
* `_on_move_to_choose(role, listbox, var)` method signature on
  `PlotConfigDialog` — tests rely on calling it directly.

### Locks relaxed (canonical from CS-62 for Phase 4al only)

* The CS-62 Listbox `state="disabled"` lock relaxes on the
  three Y-axis tabs (now `state="normal"` so rows are
  selectable). X-axis tabs preserve `state="disabled"`.
* The "single uniform `_per_axis_tick_direction(cfg, 'primary_x')`
  read" transitional behaviour is replaced by per-axis-role
  reads at every call site (CS-62 deferred per-axis tick
  rendering ✅).
* The previously-hardcoded `sec.tick_params(axis="x",
  direction="in", labelsize=8)` for the wavelength twin now
  reads `direction=_per_axis_tick_direction(cfg, "secondary_x")`.

### Locks held (no canonical relaxation)

Every CS-60 / CS-61 / CS-62 lock the relaxations above didn't
touch: `PlotConfigDialog` class identity + `open_plot_config_dialog`
factory name; `_TAB_KEYS` six-tuple + canonical order;
`_TAB_TITLES` content; `_MODIFIED_TAB_SUFFIX = " •"`; `AxisHit`
dataclass; `classify_axis_double_click` signature + hit-test
band constants; button row order; Apply-to-All-Tabs commits-
locally-first contract; Cancel-with-pending confirm dialog;
`_axis_control_vars[(role, key)]` registry idempotency on the
`(role, key)` pair; `_on_axis_var_write(role, key, value)`
signature; `_build_section_axis_labels` mirror section's
five-row shape; `_DEFAULT_SECTIONS` ending with `"axis_labels"`;
`plots_by_role` kwarg's `dict[str, tuple[str, ...]] | None`
type; the `(no plots on this axis)` placeholder text; Listbox
height ≤ 6 cap.

All CS-44 + CS-50 invariants unchanged. CS-46 manifest schema
unchanged — Phase 4al touches no persistence schema (the
NODE_STYLE_CHANGED gesture rides the existing graph round-trip).

### Decision lock taken (Phase 4al)

(i) **Move-to picker UX**: Combobox below Listbox on Y-axis
tabs only (X-axis tabs get no picker — every visible plot
necessarily sits on primary_x); auto-applies on
`<<ComboboxSelected>>` (with the dispatch-bypass refactor noted
above); resets to empty placeholder after every choose so the
user can route another plot without first clearing the dropdown.
(ii) **Tab-role-key space throughout the dialog**: both the
combobox values and the callback parameters use tab keys
(`"primary_y"` etc.) rather than CS-50 style values (`"primary"`
etc.); the host owns the translation. Keeps the dialog in one
namespace; future axis-nomenclature-rename (USER-FLAGGED
register entry) touches one space, not two. (iii) **Source role
disambiguates label collisions**: the picker fires
`(source_tab_role, label, target_tab_role)` — the host filters
to nodes currently routed to `source_tab_role`. First match
wins (rare-case tie-breaker documented in BACKLOG.md friction
#11). (iv) **Picker fires immediately, NOT on dialog Apply**:
per-node style edits commit on pick (consistent with CS-50
Style-dialog behaviour). Bypasses Plot Settings' working-copy
Cancel semantics for these edits — asymmetry intentional;
documented in BACKLOG.md friction #9 as a candidate for the
USER-FLAGGED Live-preview register entry to address. (v) **Bind
trampoline + extracted method** rather than inline closure: the
flaky-in-suite Tk virtual-event dispatch motivated the refactor;
the method-direct test pattern bypasses event_generate
entirely.

### Tests

* New `TestUVVisTabPerAxisTickRenderingPhase4al` (7 tests):
  mock-patched `_per_axis_tick_direction` captures the role
  argument at each renderer call site; end-to-end "distinct
  per-axis values land on distinct matplotlib axis tick params"
  via `Axis.get_tick_params`; the explicit "Secondary X
  distinct from Primary X" case the Phase 4ak user-flagged bug
  demanded.
* New `TestPlotConfigDialogMoveToPickerPhase4al` (16 tests):
  module constants; Combobox presence on Y-axis tabs / absence
  on X-axis tabs / absence when no plots; four-option list;
  readonly state; Y-axis listbox state="normal"; callback firing
  with row + combobox; no-fire without row; Default→None target;
  source role from tab not row; combobox reset after choose;
  silent no-op when callback unset; bind registration.
* New `TestUVVisTabMoveToPickerPhase4al` (9 tests): both
  dialog-open paths thread `on_route_plot`;
  `_on_route_plot_from_dialog` writes `style["y_axis"]` via
  `graph.set_style`; Default option clears the override;
  source-role disambiguates label collisions across axes;
  unknown label / invisible node / unknown source tab are
  silent no-ops; routing-induced NODE_STYLE_CHANGED event drives
  `_redraw` which re-resolves the role correctly.
* The CS-62 test `test_plots_listbox_is_read_only` renamed to
  `test_plots_listbox_is_disabled_on_x_axis_tabs` and pivoted
  onto an X-axis tab (where the `state="disabled"` lock
  survives Phase 4al's canonical relaxation).

Total: +32 new across the three new test classes plus the
rename. Full suite 1197 (was 1165).

See "Friction points carried forward from Phase 4al" in
BACKLOG.md. **Three new USER-FLAGGED register entries from
step 5:** accessibility features umbrella; modeless dialogs
(drop `grab_set` from Plot Settings to match CS-05 StyleDialog
modeless precedent); retire the global "Baseline curves"
top-bar checkbox now that the per-node CS-36 toggle has
subsumed it. Four Claude-surfaced 🟢 polish notes documented
inline (cancel-with-pending asymmetry on routing edits;
silent-no-op without listbox row; label-collision first-match
tie-breaker; Combobox virtual-event dispatch flakiness fixed
by the extract-to-method refactor).

---

## CS-64 — Per-axis range / autoscale / scale (linear/log) (Phase 4am)

The third slice of the per-axis settings ladder (after CS-62's
schema invention and CS-63's per-axis tick rendering + Move-to
picker). Adds four new keys per axis role, the matching widgets
on every per-axis tab, and the renderer wiring that reads them.

### Schema growth

`_AXIS_KEYS` grew from `("tick_direction", "axis_label_override")`
to `("tick_direction", "axis_label_override", "range_lo",
"range_hi", "autoscale", "scale")` — a 6-tuple. Every role's
sub-dict in `_FACTORY_DEFAULTS["axes"]` gained four new entries:

| Key | Type | Default | Semantics |
|---|---|---|---|
| `range_lo` | `str` | `""` | Empty = no bound on this end. StringVar-backed (`_make_axis_string_var`). |
| `range_hi` | `str` | `""` | Empty = no bound on this end. |
| `autoscale` | `bool` | `True` | When `True`, renderer ignores schema range; when `False`, schema range_lo / range_hi clamp where non-empty. |
| `scale` | `str` | `"linear"` | One of `{"linear", "log"}`. Applied via `set_xscale` / `set_yscale` at the per-role site. |

New module-level `_AXIS_SCALE_OPTIONS = ("linear", "log")`
canonicalises the Scale Combobox value set; tests pin this tuple
so future extensions (symlog, function) declare themselves
explicitly.

### `_FACTORY_DEFAULTS` shape

```python
"axes": {
    "primary_x":   {"tick_direction": "in", "axis_label_override": "",
                    "range_lo": "", "range_hi": "",
                    "autoscale": True, "scale": "linear"},
    "secondary_x": {"tick_direction": "in", ...},
    "primary_y":   {"tick_direction": "in", ...},
    "secondary_y": {"tick_direction": "in", ...},
    "tertiary_y":  {"tick_direction": "in", ...},
}
```

### Migration shim

`migrate_plot_config(config)` (CS-62) required NO code change for
the schema growth — the existing per-role per-key fill loop walks
`_FACTORY_DEFAULTS["axes"][role].items()` and back-fills missing
keys from factory defaults. Legacy configs (pre-Phase-4am)
gain the four new keys per role transparently on first dialog
open. The shim remains idempotent.

### Widgets per per-axis tab

`_build_axis_tab_settings(parent, role)` was extended with three
new rows below the existing tick-direction + axis-label-override
rows, on ALL FIVE per-axis tabs (primary_x, secondary_x,
primary_y, secondary_y, tertiary_y) — uniform schema, uniform
surface:

* **Range row**: two `tk.Entry` widgets with `width=8`, separated
  by a "to" label and tailed with an italic "(empty = no bound)"
  hint. Both Entries bind to per-axis StringVars (`range_lo`,
  `range_hi`).
* **Autoscale row**: `tk.Checkbutton` bound to a per-axis
  BooleanVar (`autoscale`), label "Autoscale", with an inline
  italic "(off = use Range bounds above)" hint.
* **Scale row**: readonly `ttk.Combobox` bound to a per-axis
  StringVar (`scale`), values from `_AXIS_SCALE_OPTIONS`.

### `_make_axis_bool_var(role, key)`

Parallel to CS-62's `_make_axis_string_var`. Same idempotency
contract on the `(role, key)` pair; same registration in
`_axis_control_vars` (cross-typed registry) and
`_axis_control_refresh`; same trace handler routing through
`_on_axis_var_write(role, key, value)`. The refresh closure
coerces via `bool(value)` so a stored "True" / "False" / 0 / 1
round-trips correctly through Load Defaults / Factory Reset /
Cancel revert paths.

`_on_axis_var_write`'s `value: Any` signature accepts the bool
without change.

### Renderer wiring

Four new module-level helpers in `uvvis_tab.py`:

```python
_per_axis_range(cfg, tab_role, key) -> str       # "" if missing
_per_axis_autoscale(cfg, tab_role) -> bool       # True if missing
_per_axis_scale(cfg, tab_role) -> str            # "linear" if missing/unknown
_parse_lim_str(text) -> Optional[float]          # None for empty/garbage
```

All four are defensive against malformed configs (pre-Phase-4am
shapes that lack the nested `axes` sub-dict) and against unknown
values (`_per_axis_scale` clamps to `{"linear", "log"}`,
defaulting to `"linear"` otherwise).

The renderer (`UVVisTab._redraw`) reads each axis's own
`cfg["axes"][role][...]` slot at its limit-application site:

* **Primary X** (`ax.set_xscale` / `ax.set_xlim`): scale always
  applied; when `autoscale=True` (default), the legacy top-bar
  `_xlim_lo` / `_xlim_hi` Tk vars provide the fallback bound;
  when `autoscale=False`, the schema range_lo / range_hi win.
* **Primary Y** (`ax.set_yscale` / `ax.set_ylim`): same pattern
  via `_ylim_lo` / `_ylim_hi`.
* **Twin Y-axes** (secondary_y, tertiary_y): iterate
  `_axes_by_role` + `_Y_AXIS_ROLE_TO_TAB`; `set_yscale` always,
  `set_ylim` only when `autoscale=False` and at least one bound
  is set. No legacy Tk-var fallback — twins are schema-only.
* **Secondary X** (wavelength-nm sibling, when active):
  `set_xscale` always; `set_xlim` only when `autoscale=False`
  and at least one bound is set.

Scale applies BEFORE range so log + clamp lands in log space.

### Backward compatibility

The legacy top-bar `_xlim_lo` / `_xlim_hi` / `_ylim_lo` /
`_ylim_hi` Tk vars remain the renderer's fallback for primary_x
and primary_y when `autoscale=True` (default). This is a
deliberate decision (D7 in the Phase 4am decision lock): adding
a sync trace from the top-bar Entries into
`cfg["axes"]["primary_x"]["range_lo"]` would have doubled the
write surface for no user-visible benefit. The user can type in
either surface and see correct behaviour as long as the schema's
autoscale flag stays True. `autoscale=False` makes the schema
the only source of truth.

### Locks

* **`_AXIS_KEYS` is a 6-tuple** in the canonical order shown
  above. Future per-axis ladder phases extend it; the migration
  shim handles legacy configs without code change.
* **`_FACTORY_DEFAULTS["axes"][role]` carries exactly these six
  keys** for all five roles. Adding a new key requires extending
  `_AXIS_KEYS` AND every role's sub-dict in lock-step.
* **`_AXIS_SCALE_OPTIONS = ("linear", "log")`** — the renderer
  rejects unknown values defensively.
* **`_make_axis_bool_var(role, key)`** signature + idempotency
  contract; mirrors `_make_axis_string_var`. The cached var lives
  in the shared `_axis_control_vars` registry (cross-typed).
* **`_per_axis_range` / `_per_axis_autoscale` / `_per_axis_scale`
  / `_parse_lim_str`** module-level helpers' signatures and
  default-return semantics. The renderer's per-call-site reads
  go through these — a future schema relaxation that changes
  defaults updates the helpers in one place.
* **`_Y_AXIS_ROLE_TO_TAB` iteration order** at the twin-Y range
  application site is deterministic via the dict's insertion
  order (Python 3.7+). The renderer applies secondary_y BEFORE
  tertiary_y.
* **Legacy top-bar Tk vars (`_xlim_lo` / `_xlim_hi` /
  `_ylim_lo` / `_ylim_hi`)** remain the renderer's
  primary-axis fallback when `autoscale=True`. This is an
  intentional decision — see "Backward compatibility" above.
* **Apply scale BEFORE range** at every per-role limit-
  application site so log + clamp interact correctly.

### Lock relaxations vs CS-62 / CS-63

* `_AXIS_KEYS` grew from `("tick_direction",
  "axis_label_override")` to a 6-tuple. CS-62 explicitly named
  this as the canonical relaxation target for the per-axis
  ladder.
* `_FACTORY_DEFAULTS["axes"][role]` shape grew additively.
  CS-62's "shape is `dict[str, dict[str, Any]]` keyed by the
  five per-axis roles" invariant remains; the inner dict gained
  four entries.
* CS-62's "fully migrated dict… leaves the existing values alone"
  invariant still holds — the migration shim doesn't overwrite
  user-set values; it only fills missing keys.

### Decision lock (Phase 4am)

D1. New `_AXIS_KEYS` entries are `range_lo` (str) / `range_hi`
(str) / `autoscale` (bool) / `scale` (str ∈ `{"linear",
"log"}`). Order is canonical; tests pin the tuple shape.

D2. Factory defaults: empty range, autoscale=True, scale=linear
for all five roles. Rationale: matches matplotlib's default
behaviour exactly, so a fresh config and a config with all
factory-default per-axis slots render identically.

D3. Widgets land on ALL FIVE per-axis tabs, not just Y. Schema
is uniformly per-role per CS-62; consistent surface; X-axis
range control is genuinely useful (e.g. wavelength axis clamp
on a Compare tab).

D4. Renderer reads per-role at the axis's own limit-application
site. Twin Y-axes are applied AFTER the primary plot loop via
`_axes_by_role` iteration; secondary X is applied inline inside
the `unit == "cm-1" and self._show_nm_axis.get()` block.

D5. Autoscale-True is the renderer-ignore semantic — pure
matplotlib autoscale, matches the empty-Entry pre-Phase-4am
default. Autoscale-False makes schema range_lo / range_hi clamp
where non-empty; empty bound = "no bound on this end".

D6. Scale applies via `set_xscale` / `set_yscale` BEFORE the
range clamp so log + clamp interact correctly (log-scale axis
clamped to (0.01, 100) is meaningful; clamp-then-scale could
hit non-positive values).

D7. Legacy top-bar `_xlim_lo` / `_xlim_hi` / `_ylim_lo` /
`_ylim_hi` Tk vars remain the renderer's primary-axis fallback
when `autoscale=True`. Schema autoscale=False overrides.
Decision: NO sync trace from top-bar to schema this phase —
adds surface area for no user-visible win.

### Tests added

* `TestPlotConfigDialogPerAxisRangeScaleSchemaPhase4am` (6
  tests): registry tuple growth, `_AXIS_SCALE_OPTIONS` enum,
  migration fill of missing keys, migration preservation of
  user-set values, idempotency on Phase 4am keys,
  `_UNIVERSAL_DEFAULTS` round-trip.
* `TestPlotConfigDialogPerAxisRangeScaleWidgetsPhase4am` (13
  tests): var-registry coverage per key per role (StringVar for
  range / scale, BooleanVar for autoscale), make-bool-var
  idempotency, write-through to `_working["axes"][role][...]`,
  widget surface (Range label / Autoscale Checkbutton / Scale
  Combobox per tab), Apply round-trip to `config`,
  legacy-config fill-on-load.
* `TestUVVisTabPerAxisRangeScalePhase4am` (20 tests): helper
  read paths (defaults, garbage rejection, unknown-scale
  rejection), primary_y autoscale-on vs autoscale-off
  semantics, legacy top-bar fallback when autoscale=True,
  primary_x / primary_y scale=log, twin Y-axis range + scale
  application, only-one-bound clamp semantics, missing-axes
  defensive guard.
* 2 Phase 4ak tests updated in place
  (`test_factory_defaults_carries_nested_axes` and
  `test_axis_keys_registry_matches_factory` to assert the new
  6-tuple shape and the new per-role default values).

Net suite count after Phase 4am: 1236 (up from 1197).

### Step 5 elicitation (Phase 4am)

User had nothing to add. Four Claude-surfaced 🟢 polish notes
documented in BACKLOG's "Friction points carried forward from
Phase 4am" section: (θ) Range Entry edits don't trigger immediate
`_redraw` (working-copy model — folds into the USER-FLAGGED
live-preview register entry); (ι) top-bar legacy Tk vars and
schema range bounds can drift silently when the user toggles
autoscale after editing the top-bar (folds into per-axis ladder
— tooltip suggested); (κ) Secondary X range Entries silent-no-op
without active wavelength↔energy twin (folds into the USER-FLAGGED
Twin-X register entry); (l) `_do_apply` vs `_apply` naming
discoverability cliff for tests (polish; surface if it bites
again).

## CS-65 — Per-axis tick spacing + per-axis grid + per-axis axis colour (Phase 4an)

The **fifth and final canonical slice** of the per-axis settings
ladder (after CS-61 / CS-62 / CS-63 / CS-64). Adds four polish
keys per axis role, the matching widgets on every per-axis tab,
and the renderer wiring that reads them. With this phase the
ladder is complete: every plot-level setting that mattered for
per-axis precision in Phase 4ai's original USER-FLAGGED scope
now lives in the per-axis schema.

### Schema growth

`_AXIS_KEYS` grew from the 6-tuple of Phase 4am to a 10-tuple:

```python
("tick_direction", "axis_label_override",
 "range_lo", "range_hi", "autoscale", "scale",
 "tick_major", "tick_minor", "grid_show", "axis_color")
```

Every role's sub-dict in `_FACTORY_DEFAULTS["axes"]` gained four
new entries:

| Key | Type | Default | Semantics |
|---|---|---|---|
| `tick_major` | `str` | `""` | Empty = matplotlib auto-locator. Non-empty positive float = `MultipleLocator(value)`. Negative / zero / `inf` / `nan` / garbage silently rejected → auto-locator. |
| `tick_minor` | `str` | `""` | Same rules as `tick_major`. |
| `grid_show` | `bool` | `True` for `primary_x` / `primary_y`, `False` for the three non-primary roles | Renderer reads this only for `primary_x` / `primary_y` (twin axes share the primary grid). Per-role default differs from every other key so the Plot Settings checkbox starts visually consistent with what the renderer paints. |
| `axis_color` | `str` | `"#000000"` | Hex colour string. Applied to the per-role spine + tick params (colour) + axis-label colour. Non-string values fall back to `"#000000"` defensively. |

### `_FACTORY_DEFAULTS` shape

```python
"axes": {
    "primary_x":   {"tick_direction": "in", "axis_label_override": "",
                    "range_lo": "", "range_hi": "",
                    "autoscale": True, "scale": "linear",
                    "tick_major": "", "tick_minor": "",
                    "grid_show": True, "axis_color": "#000000"},
    "secondary_x": {... "grid_show": False, ...},
    "primary_y":   {... "grid_show": True, ...},
    "secondary_y": {... "grid_show": False, ...},
    "tertiary_y":  {... "grid_show": False, ...},
}
```

### Migration shim

`migrate_plot_config(config)` required NO code change — the
existing per-role per-key fill loop walks
`_FACTORY_DEFAULTS["axes"][role].items()` and back-fills missing
keys from factory defaults. Pre-Phase-4an configs gain the four
new keys per role transparently on first dialog open. The shim
remains idempotent and preserves user-set values.

### Widgets per per-axis tab

`_build_section_axis_settings(parent, role)` was extended with
four new rows below the Phase 4am Scale Combobox row, on ALL
FIVE per-axis tabs:

* **Tick spacing row**: two side-by-side Entries (major / minor),
  `width=6`, StringVar-backed. Italic "(empty = auto)" hint
  trails. No validate logic — the renderer's `_parse_tick_str`
  silently rejects garbage / non-positive / inf / nan, matching
  the Phase 4am Range Entry convention.
* **Show gridlines row**: Checkbutton bound to a per-axis
  BooleanVar (`grid_show`). On non-primary tabs an italic
  "(twin axes share the primary grid)" hint trails the box,
  indicating the checkbox is schema-only there.
* **Axis colour row**: a `tk.Frame` swatch (22×14 px, `bd=1`,
  `relief="solid"`, `bg=current_hex`) + a `tk.Button("Choose…")`
  that opens `tkinter.colorchooser.askcolor(parent=...,
  title=...)` seeded with the current value. The Button writes
  any successful pick back into the StringVar; a per-widget
  trace updates the swatch's `bg` whenever the var changes (Tk
  colour-string errors are swallowed so the trace can't blow
  up the dialog).

Tk var wiring uses the existing `_make_axis_string_var` (tick
+ colour keys) and `_make_axis_bool_var` (`grid_show`) helpers
from earlier phases — no new registry machinery; idempotency
on `(role, key)` pairs continues to hold.

### Renderer wiring

Five new module-level helpers in `uvvis_tab.py`:

```python
_parse_tick_str(text) -> Optional[float]            # positive-float-only; None for empty / garbage / non-positive / inf / nan
_per_axis_tick_major(cfg, tab_role) -> Optional[float]
_per_axis_tick_minor(cfg, tab_role) -> Optional[float]
_per_axis_grid(cfg, tab_role) -> bool               # role-default split: True for primaries, False otherwise
_per_axis_color(cfg, tab_role) -> str               # "#000000" default; non-string returns the default
```

`UVVisTab._redraw` adds a per-axis polish application block AFTER
the Phase 4am scale/range block, applied at five call sites:

* **Primary X** (`ax.xaxis`): `set_major_locator` /
  `set_minor_locator` from MultipleLocator when helper returns
  non-None; `spines["bottom"].set_color`; `tick_params(axis="x",
  colors=...)`; `xaxis.label.set_color`.
* **Primary Y** (`ax.yaxis`): same as primary X but for the y
  axis, spine `"left"`.
* **Twin Y-axes** (secondary_y, tertiary_y): iterate
  `_Y_AXIS_ROLE_TO_TAB`; locator on `twin_ax.yaxis`; spine
  `"right"` (guarded with try/except for malformed twins);
  matching tick params + axis label colour.
* **Secondary X** (wavelength-nm sibling, when active): locator
  on `sec.xaxis`; tick params + axis label colour. NO spine
  adjustment — `secondary_xaxis` manages its own spine.

Order matters: colour application happens AFTER `set_xscale` /
`set_yscale` at every site so the scale change doesn't reset
the colour. Tick spacing uses `matplotlib.ticker.MultipleLocator`
(new top-level import).

The existing global `ax.grid(...)` block was rewritten to honour
`_per_axis_grid(cfg, "primary_x")` and `_per_axis_grid(cfg,
"primary_y")` independently on the X / Y axes:

```python
if cfg.get("grid", True):
    grid_color = cfg.get("grid_color", "#b0b0b0")
    if _per_axis_grid(cfg, "primary_x"):
        ax.grid(True, axis="x", linestyle=":", alpha=0.4,
                color=grid_color, zorder=0)
    else:
        ax.grid(False, axis="x")
    if _per_axis_grid(cfg, "primary_y"):
        ax.grid(True, axis="y", linestyle=":", alpha=0.4,
                color=grid_color, zorder=0)
    else:
        ax.grid(False, axis="y")
else:
    ax.grid(False)
```

Two important invariants here:

1. **`cfg["grid"]` master switch wins**: `False` disables
   everything regardless of per-axis values.
2. **CS-28 `zorder=0` invariant preserved**: every `visible=True`
   call passes `zorder=0` so gridlines paint BEHIND data lines.

**matplotlib quirk discovered (Phase 4an commit 5 integration
tests)**: passing styling kwargs (`linestyle` / `alpha` / `color`)
alongside `visible=False` ENABLES the grid because matplotlib
interprets the styling presence as "you must have meant
visible=True", overriding the explicit `False`. The disable
branch above calls `ax.grid(False, axis=...)` with NO styling
kwargs to dodge this trap. Documented inline in the renderer.

### `grid_show` precedence rules

* `cfg["grid"] = False` → no grid anywhere; per-axis `grid_show`
  values are ignored.
* `cfg["grid"] = True` AND `grid_show=True` on primary_x → x-grid
  painted.
* `cfg["grid"] = True` AND `grid_show=False` on primary_x → x-grid
  hidden, y-grid follows its own per-axis setting.
* `grid_show` on non-primary roles is schema-only — the renderer
  doesn't consult it because matplotlib paints gridlines only on
  the host axes (twin axes share the primary's grid).

### Locks

* **`_AXIS_KEYS` is a 10-tuple** in the canonical order shown
  above. The migration shim handles legacy configs without code
  change.
* **`_FACTORY_DEFAULTS["axes"][role]` carries exactly these ten
  keys** for all five roles with the canonical default values
  (note `grid_show`'s per-role split).
* **`_parse_tick_str(text) -> Optional[float]`** signature +
  positive-float-only contract (rejects empty / garbage /
  non-positive / non-finite). Renderer's
  `MultipleLocator(value)` call site depends on this; a future
  relaxation to permit zero/negative would also need to update
  the locator strategy.
* **`_per_axis_tick_major` / `_per_axis_tick_minor` /
  `_per_axis_grid` / `_per_axis_color`** module-level helpers'
  signatures and default-return semantics. The renderer's per-
  call-site reads go through these.
* **`_per_axis_grid` default split** (`True` for `primary_x` /
  `primary_y`; `False` otherwise) when the schema slot is
  missing — keeps the Plot Settings checkbox visually
  consistent with what the renderer actually paints.
* **`_per_axis_color` defensive defaults** — non-string slot
  values return `"#000000"` so a malformed config (e.g. an
  integer 0xff8800 instead of `"#ff8800"`) can't propagate a
  bad value into matplotlib.
* **Apply order at every per-role site**: scale → range → tick
  spacing → grid → colour. Colour last so spine recreation /
  scale changes don't reset the chosen colour.
* **CS-28 `ax.grid(..., zorder=0)` invariant preserved** on
  every `visible=True` per-axis grid call.
* **Global `cfg["grid"]` remains the master switch** — per-axis
  `grid_show` cannot enable gridlines if the global key is
  `False`.

### Lock relaxations vs CS-64

* `_AXIS_KEYS` grew from 6 → 10. CS-64 explicitly named this as
  the canonical relaxation target for Phase 4an.
* `_FACTORY_DEFAULTS["axes"][role]` shape grew additively. CS-62
  / CS-64 "shape is `dict[str, dict[str, Any]]` keyed by the
  five per-axis roles" invariant remains; the inner dict gained
  four entries.
* The Phase 4ah global `ax.grid(...)` call was rewritten into the
  four-branch shape above, preserving the CS-28 `zorder=0`
  invariant. The `linestyle=":"`, `alpha=0.4`, and `grid_color`
  fallback all carry forward unchanged on the `visible=True`
  branches.

### Decision lock (Phase 4an)

D1. Four new `_AXIS_KEYS` entries: `tick_major` (str) /
`tick_minor` (str) / `grid_show` (bool) / `axis_color` (str hex).
Order is canonical; tests pin the 10-tuple shape.

D2. `grid_show` defaults split per role: `True` for the two
primaries, `False` for the three non-primary roles. Rationale:
the renderer only consults `grid_show` for the primaries, so a
non-primary default of `True` would lie to the user about what
the Checkbutton state means. The split keeps the Plot Settings
surface visually honest.

D3. Widgets land on ALL FIVE per-axis tabs, not just primaries.
Schema is uniformly per-role per CS-62 / CS-64; consistent
surface; consistent reasoning. The non-primary `grid_show`
checkbox is rendered with an inline "(twin axes share the
primary grid)" hint label to signal the schema-only status.

D4. Colour picker uses `tkinter.colorchooser.askcolor` — the
stdlib choice; no third-party dependency. Hex string round-
trips trivially through `_jsonify` for CS-46 persistence (no
project_io changes needed).

D5. Apply order: scale → range → tick spacing → grid → colour
at every per-role site. Colour last because spine recreation or
`set_yscale` calls reset spine styling on some matplotlib paths;
colour at the tail of the chain is the safe place. Tests in
`test_scale_then_colour_order_preserves_colour` pin this
ordering.

D6. Tick-spacing parser rejects non-positive and non-finite
values silently. `MultipleLocator(0)` raises; `MultipleLocator
(-1)` produces incoherent ticks; `MultipleLocator(inf)` and
`MultipleLocator(nan)` produce nothing useful. Silent rejection
in `_parse_tick_str` keeps the renderer free of try/except
clutter and matches the Phase 4am Range Entry "empty = no
override" convention.

### Tests added

* `TestPlotConfigDialogPerAxisPolishSchemaPhase4an` (6 tests):
  registry tuple growth to 10, factory-default values per role
  (with the `grid_show` per-role split), universal-defaults
  round-trip, migration fill, migration preservation of user-set
  values, idempotency on Phase 4an keys.
* `TestUVVisTabPerAxisPolishHelpersPhase4an` (11 tests):
  `_parse_tick_str` accepts positive floats, rejects empty /
  garbage / non-positive / inf / nan; `_per_axis_tick_major` /
  `_per_axis_tick_minor` read nested slot + default None;
  `_per_axis_grid` per-role default split + explicit override;
  `_per_axis_color` reads nested slot + defaults black + rejects
  non-string defensively.
* `TestPlotConfigDialogPerAxisPolishWidgetsPhase4an` (10 tests):
  var-registry coverage per key per role (StringVar for tick +
  colour, BooleanVar for grid_show), `grid_show` default-split
  per role, default colour `"#000000"`, write-through to
  `_working["axes"][role][...]`, working-copy seeding from
  existing values, Factory Reset round-trip, dialog opens on
  every per-axis tab without raising.
* `TestUVVisTabPerAxisPolishPhase4an` (16 tests): tick spacing
  applies as MultipleLocator with expected step, twin Y picks up
  per-role spacing, empty / garbage / non-positive keep the
  auto-locator; primary X / Y grid_show False disables the
  respective grid axis, independence of x- and y-grid toggles,
  global `cfg["grid"]=False` master switch wins; axis_color
  sets bottom / left / right spines correctly, axis label
  colour follows the hex; scale-then-colour ordering
  preservation; defensive empty-config / missing-keys.
* 2 pre-existing tests updated in place
  (`test_axis_keys_grew_to_six` relaxed `==` to `>=`,
  `test_axis_keys_registry_matches_factory` expected tuple
  extended).

Net suite count after Phase 4an: 1279 (up from 1236).

### Step 5 elicitation (Phase 4an)

User had nothing to add. Five Claude-surfaced notes carried
forward into the BACKLOG "Friction points carried forward from
Phase 4an" section: (μ) matplotlib grid-styling override quirk
(renderer-bug-fix surfaced by integration tests, already fixed
in commit 5); (ν) `grid_show` on non-primary tabs is schema-
only (hint label in place; defer until reported); (ο)
`tick_minor` doesn't force minor ticks to render (folds into
future tick-rendering polish or accessibility visibility audit);
(π) `_AXIS_KEYS` readability cliff approaching at 10 entries
(consider nested sub-dicts when adding more keys; pairs with
`_USER_DEFAULTS` tab-type split); (ρ) Colour swatch is a
`tk.Frame`, not a ttk widget (cross-platform feedback pending).

---

## CS-66 — Modeless Plot Settings dialog (Phase 4ao)

Phase 4ao relaxes the original CS-06 modal contract: the unified
`PlotConfigDialog` (CS-60) drops `grab_set()` so the main window
stays interactive while the dialog is open. `transient(parent)`
is retained — the dialog stays grouped above its parent in the
window manager's Z-order, but no grab is held. The user can
select scan-tree rows, pan the canvas, double-click a node to
open a StyleDialog, or commit a panel-driven operation while
Plot Settings remains open.

### Lock relaxations vs CS-06 / CS-60

The single behavioural change is in `PlotConfigDialog.__init__`:
the `self.grab_set()` line is removed. The surrounding
`self.transient(parent.winfo_toplevel())` block is unchanged.
The module docstring's "Behavioural model" section flips from
"**Modal.**" to "**Modeless.**"; the class docstring flips from
"Modal per-tab plot-settings editor" to "Modeless per-tab plot-
settings editor".

CS-06's one-per-host uniqueness invariant is unaffected: the
`_open_dialogs` registry still enforces "exactly one Plot
Settings dialog open at a time per host", and a second open
request still focuses the existing window rather than creating
a duplicate. CS-23's Apply / Save / Cancel button row + working-
copy + `_snapshot` semantics survive unchanged.

### CS-05 StyleDialog precedent

`StyleDialog` (CS-05) was already modeless before Phase 4ao; it
drops BOTH `transient` and `grab_set` because multiple style
dialogs coexist (one per node). Plot Settings keeps `transient`
because it is one-per-host — keeping the dialog grouped above
its parent is the right default. The two modeless dialogs in
the app now have slightly different `transient` policies driven
by their cardinality.

### Renderer + integration consequences

None. The dialog mutates a working-copy dict on edits; Apply /
Save commits the working copy into the host's `_plot_config`
and fires `_redraw`. With or without a grab, the working-copy
semantics and the Apply / Save / Cancel button row are
unchanged. The host doesn't observe the grab status; only the
user does (the main window is no longer un-clickable).

### Implementation notes

* `wm_transient()` (called without arguments) returns the
  master path name — non-empty when transient is set. The
  `test_transient_is_preserved` test pins this.
* `grab_status()` on a dialog with no grab returns `None` on
  the Phase 4ao Tk build (`""` on some other builds). Tests
  use `assertFalse(status)` to accept either.
* The `test_source_does_not_call_grab_set` sentinel uses
  `inspect.getsource(PlotConfigDialog.__init__)` and asserts
  the literal `"self.grab_set()"` is absent. Re-introducing
  the grab requires a deliberate edit.
* The new `TestPlotConfigDialogModelessPhase4ao` test class
  (four tests) pins the modeless contract independently of
  the shell suite for ease of phase tagging.

### Locks held (Phase 4ao)

1. `PlotConfigDialog.__init__` does NOT call `self.grab_set()`.
2. `PlotConfigDialog.__init__` DOES call
   `self.transient(parent.winfo_toplevel())` inside a
   `try/except (AttributeError, tk.TclError)` block. Removing
   the try/except is a separate lock relaxation; the
   `transient` call itself is the load-bearing part of CS-66.
3. CS-06's per-host singleton survives: `_open_dialogs`
   continues to focus an existing dialog instead of creating
   a second.
4. CS-23's Apply / Save / Cancel + working-copy + `_snapshot`
   semantics survive.
5. Module docstring + class docstring describe the dialog as
   modeless and cross-reference CS-05.
6. `test_no_grab_set_on_visible_window` and
   `test_transient_is_preserved` (in `TestPlotConfigDialogShell`)
   AND the four tests in `TestPlotConfigDialogModelessPhase4ao`
   pin the contract.

### Decision lock taken (Phase 4ao / CS-66)

* (DM1) Scope: Plot Settings only. Other CS-23 modals
  (project-load mismatch dialog, Save As confirmations) stay
  modal because they represent acknowledgement gates.
* (DM2) `transient(parent)` retained — the dialog is grouped
  above the parent in the WM Z-order. The grab was the only
  modality-bearing piece dropped.
* (DM3) `_plots_by_role` remains frozen at open time per
  CS-62. Mid-edit graph mutations are reflected on dialog
  re-open. A future live-preview / refresh-on-graph-event
  phase may revisit.
* (DM4) Cancel semantics unchanged — reverts the working copy
  to `_snapshot` per CS-23.

### Carry-forwards

(σ) Modeless + per-row-baseline-toggle integration surface is
uncovered (no test drives that flow today — was impossible
under the modal contract; folds into the live-preview phase).
(τ) `_plots_by_role` staleness more reachable now (CS-62
frozen-at-open carry-forward from Phase 4ak (ε) becomes more
visible). (υ) `grab_status()` build-variation gotcha
documented inline.

---

## CS-67 — Retire global "Baseline curves" top-bar Checkbutton (Phase 4ao)

Phase 4ao retires the global `_show_baseline_curves` BooleanVar
and its top-bar Checkbutton ("Baseline curves") on UVVisTab.
The renderer's outer guard
`if self._show_baseline_curves.get(): …` is removed from the
`_redraw` baseline-overlay loop. CS-36's per-node
`style["show_baseline_curve"]` (default True), surfaced as the
per-row `~` toggle in ScanTreeWidget, is now the **single
source of truth** for dashed-overlay visibility.

### Default flip

CS-29 (Phase 4o) introduced the global toggle as **off by
default** — overlays were an opt-in review aid. After Phase
4r added the per-node CS-36 gate, the renderer required BOTH
toggles to be on (the global checkbox AND the per-node style)
before drawing an overlay. With CS-67 the global toggle is
gone and CS-36 (default True) wins: **baseline overlays now
render by default** the moment a BASELINE node is committed.

This is the documented intent of the canonical register entry
(Phase 4al elicitation) and was explicitly confirmed at the
Phase 4ao decision lock. Existing `.ptmg` projects saved before
CS-36 will display overlays they didn't previously — expected.

### Lock relaxations vs CS-29 / CS-36

CS-29's "global gate exists" invariant is **retired**. CS-36's
"per-node gate default True" invariant becomes the single
source of truth. The renderer's overlay-loop body is unchanged
apart from the outer guard removal; the per-node filter
`if not bool(bn.style.get("show_baseline_curve", True)): continue`
remains inside the loop as the only gate.

### Sites changed

1. `uvvis_tab.py` line ~611 (BooleanVar init): deleted +
   replaced with a Phase 4ao retirement comment.
2. `uvvis_tab.py` lines ~847–856 (Checkbutton + `pack`):
   deleted + replaced with a one-line retirement comment.
3. `uvvis_tab.py` line ~2393 (outer `if` guard in `_redraw`):
   deleted; the `for bn in self._spectrum_nodes():` loop now
   runs unconditionally and the per-node CS-36 filter inside
   the loop is the sole gate.

### Test consequences

* `test_default_toggle_is_off` (the CS-29 default-off pin) is
  renamed to `test_no_global_baseline_var_after_phase_4ao` and
  inverted into a `hasattr` sentinel — the BooleanVar and the
  Checkbutton attribute must NOT exist on `UVVisTab`.
* `test_toggle_off_renders_no_overlay` is replaced by
  `test_per_node_show_false_hides_overlay`, which drives
  CS-36's per-node gate via `graph.set_style`.
* A new `test_per_node_default_renders_overlay` pins the
  default-flip: a fresh BASELINE node renders without any
  toggling.
* Four other tests in `TestUVVisTabBaselineCurveOverlay` had
  redundant `self.tab._show_baseline_curves.set(True)` setup
  lines; those are dropped because the default flow already
  renders. One test in a different class
  (`TestUVVisTabPhase4yCrossTypedInheritance`) at the
  secondary-axis routing case dropped its `set(True)` too.

### Locks held (Phase 4ao)

1. `UVVisTab` has no `_show_baseline_curves` attribute.
2. `UVVisTab` has no `_baseline_curves_cb` attribute.
3. The `_redraw` baseline-overlay loop has no outer global
   guard; the per-node `style["show_baseline_curve"]` filter
   inside the loop is the only gate.
4. CS-36's default-True invariant for
   `style["show_baseline_curve"]` is preserved.
5. CS-28 zorder=0 invariant on `ax.grid(...)` calls is
   preserved (unrelated, but the `_redraw` rewrite did not
   disturb it).
6. CS-46 manifest schema is unaffected — the global checkbox
   was tab-private UI state, never in `_plot_config` or the
   graph. No round-trip surface to update.

### Decision lock taken (Phase 4ao / CS-67)

* (DR1) Default flip accepted — overlays now render by
  default. User must explicitly hide via the per-row `~`
  toggle.
* (DR2) Tests update in place; no new test class needed
  beyond the renamed + new tests inside the existing
  `TestUVVisTabBaselineCurveOverlay`.
* (DR3) Manifest schema untouched (no persisted state for
  the retired global var).
* (DR4) CS-29 invariant text in COMPONENTS.md left as the
  historical record; this CS-67 entry is the canonical
  retirement note.

### Carry-forwards

(φ) `scan_tree_widget.py:822` comment still references the
CS-29 "Baseline curves" global Checkbutton. Cosmetic; folds
into the next session that touches the surrounding block.
(χ) Default-flip first-reload smoke check on legacy `.ptmg`
projects is a manual verification step the user may want to
run on first reopen of a pre-CS-36 file.

---

*Document version: 1.41 — May 2026*
*1.1: CS-13 implementation notes added in Phase 4a.*
*1.2: CS-14 Plot Settings Dialog added in Phase 4b.*
*1.3: CS-15 UV/Vis Baseline Correction + CS-04 implementation
notes (Phase 4c B-001 / B-004 fixes) added in Phase 4c.*
*1.4: CS-04 §6.1 responsive collapse rules + CS-05 universal
section `visible` / `in_legend` rows + CS-04 / CS-05
implementation notes added in Phase 4d (B-002 fix).*
*1.5: CS-16 UV/Vis Normalisation added in Phase 4e
(normalisation-as-operation; resolves Phase 4a friction #2).
CS-03 enum comment notes the BASELINE / NORMALISE mode-
discriminator convention.*
*1.6: CS-17 Single-node export added in Phase 4f. CS-04
gains the ``Export…`` row context-menu entry + the
``export_cb`` constructor kwarg. CS-13 gains a forward-compat
note tying the export header shape to the future project-save
serialiser.*
*1.7: CS-18 UV/Vis Smoothing added in Phase 4g (Savitzky-Golay
+ moving average; mode-discriminated SMOOTH OperationType
mirroring CS-15 / CS-16). `node_styles.default_spectrum_style`
extracted as the four-caller threshold for the spectrum-
producing default-style dict; `uvvis_tab` and `uvvis_normalise`
migrated to it alongside the new `uvvis_smoothing`.*
*1.8: CS-19 UV/Vis Peak Picking added in Phase 4h (prominence +
manual; mode-discriminated PEAK_PICK OperationType mirroring
CS-15 / CS-16 / CS-18). First non-curve DataNode (`PEAK_LIST`)
in the UV/Vis path: separate `_peak_list_nodes()` helper +
separate scatter render branch in `uvvis_tab._redraw`, with the
sidebar filter widened to include PEAK_LIST.*
*1.9: CS-20 UV/Vis Second Derivative added in Phase 4i (single
Savitzky-Golay algorithm, no `mode` discriminator — first
operation that breaks the CS-15 / CS-16 / CS-18 / CS-19
mode-discriminator pattern). New `NodeType.SECOND_DERIVATIVE`
that reuses the `wavelength_nm` / `absorbance` schema so the
existing curve render path handles it; lives in its own
`_second_derivative_nodes()` iteration outside `_spectrum_nodes`
because chained derivatives are out of scope and the locked
operation panels' parent-type checks would refuse it. Sidebar
filter widened to include SECOND_DERIVATIVE.*
*1.10: CS-21 Collapsible left-pane sections + shared palette helper
added in Phase 4j. `node_styles.pick_default_color(graph)` unifies
the six pre-4j palette-index expressions; `node_styles.SPECTRUM_PALETTE`
becomes the single source of truth for the ten-entry default colour
palette. `collapsible_section.py` adds a reusable show/hide widget
used to wrap each of the five UV/Vis operation sections. CS-07 §"UV/Vis
left panel" updated to show the collapsed-by-default header strips.
Defence-in-depth production fix in `scan_tree_widget._begin_label_edit`
(StringVar bound to explicit master) shipped alongside.*
*1.11: CS-22 Shared subject combobox + per-panel set_subject
contract added in Phase 4k. The five per-panel `_subject_cb`
widgets are gone; one shared `_shared_subject_cb` at the top of
the left pane drives every panel + the inline baseline section
via `set_subject(node_id)` + `ACCEPTED_PARENT_TYPES`. Apply
buttons gate-disable when the shared selection isn't a valid
parent for the panel's op. Resolves Phase 4j friction #5
(USER-FLAGGED). Phase 4k logged six new friction items including
three new USER-FLAGGED follow-ups (Commit / discard reachable
from the left pane after Apply, Per-variant gestures on
sweep-group rows, Plot Settings dialog Save & Close).*
*1.12: CS-23 Plot Settings dialog Save button added in Phase 4l.
The dialog's button row now reads `Apply · Save · Cancel`,
matching CS-05 StyleDialog vocabulary (the `∀ Apply to All`
slot is dropped — Plot Settings has no node-bulk concept).
Save = `_do_apply()` + `destroy()`. Resolves Phase 4k friction
#3 (USER-FLAGGED). Phase 4l logged nine new friction items
including five USER-FLAGGED follow-ups: Audit dialog button-row
vocabulary across the app, Plot config + plot defaults
persistence to project.json, Remove duplicate section title
from operation panels, Right-sidebar responsive layout
extension, Scattering-functional baseline mode.*
*1.13: CS-24 Scattering baseline mode added in Phase 4m as the
fifth `OperationType.BASELINE` mode. Pure helper
`uvvis_baseline.compute_scattering` fits `B(λ) = c · λ^(-n)`
over a peak-free window and subtracts the result across the
full input range; `params["n"]` is either numeric (closed-form
fit for `c` only) or the string `"fit"` (log–log linear
regression for both `c` and `n`). UI gains a fifth combobox
entry + parameter row (`n:` Entry, `Fit n` Checkbutton, fit
window endpoints). Renderer / sidebar / `_spectrum_nodes` need
no changes — the new mode reuses the CS-15 BASELINE node shape
end-to-end. Resolves Phase 4l friction #9 (USER-FLAGGED). Phase
4m logged five new friction items, all observed-during-session
(no new USER-FLAGGED elevations): Fit-n state-rebuild brittleness,
n-fit diagnostic loss, scattering+offset composite mode, fit
window error message gap, missing checkbox-disables-entry
integration test.*
*1.14: CS-25 + CS-26 + CS-27 added in Phase 4n. CS-25 deletes
the duplicate `tk.Label` from each of the four
`CollapsibleSection`-wrapped operation panels (USER-FLAGGED
Phase 4l #6). CS-26 extends CS-04 §6.1: ⌥n provenance count
promoted into the always-visible minimum, single 280 px
threshold replaced by three priority-ordered thresholds
(swatch @ 240, leg @ 280, ls\_canvas @ 320); helper now reflows
right-side optional cells together to preserve canonical
visual order under Tk's overflow auto-unmap (USER-FLAGGED
Phase 4l #8). CS-27 retires the top-bar `+ Add to TDDFT
Overlay` button in favour of a per-row → icon between `[⚙]`
and `[✕]`; UVVisTab refactors the bulk overlay handler to a
single-node `_send_node_to_compare(node_id)` (USER-FLAGGED
Phase 4l #7). Phase 4n logged five new friction items, three
USER-FLAGGED: `_redraw` KeyError on non-UVVIS DataNodes
(observed-during-session), responsive helper does redundant
work on every Configure (technical debt), `⌥n` digit overflow
for long provenance chains. Plus four register-elevated
USER-FLAGGED feature requests: Show baseline function on the
plot, Scattering floor-zero shift (CS-24 follow-up),
Diagnostic console / fitted-parameter panel, Difference
spectra elevation.*
*1.15: CS-28 + CS-29 added in Phase 4o. CS-28 wraps the
`uvvis_tab._redraw` per-node loop in a positive guard
(`"wavelength_nm" in arrays and "absorbance" in arrays`) and
mirrors the guard on the `unit == "nm"` xlim min/max
comprehension; resolves Phase 4n friction #1 (USER-FLAGGED).
CS-29 lands the dashed baseline-curve overlay: new top-bar
"Baseline curves" toggle + new pure helper
`uvvis_baseline.compute_baseline_curve(graph, baseline_node)`
that walks one hop in the graph to recover
`parent.absorbance - baseline_node.absorbance` and returns
`None` on every failure path; renderer plots it dashed in the
BASELINE node's colour after the main spectrum loop. Resolves
Phase 4n register entry "Show baseline function on the plot"
(USER-FLAGGED). Phase 4o logged three new friction items
(per-node baseline-curve gate USER-FLAGGED, overlay legend
density, friction-note schema accuracy as a process note); two
new register entries: 🔴 Per-node baseline-curve toggle
(USER-FLAGGED), 🟡 Baseline-curve overlay legend density. The
`test_send_node_to_compare_skips_non_uvvis_nodes` get_node
stub workaround was simplified to use the new CS-28 guard
rather than the lambda override.*
*1.16: CS-30 + CS-31 added in Phase 4p (CS-32 split out to
Phase 4q). CS-30 rewrites the responsive helper to read
`_scroll_canvas.winfo_width()` instead of `row.winfo_width()`
and replaces the per-row `<Configure>` binding with a canvas-
`<Configure>` binding that walks every row. Single-node
sidebars now collapse / expand correctly at any width, and
narrowing the sidebar recollapses expanded rows. The helper
gains a `width: int | None = None` kwarg so explicit per-call
widths can override the canvas default — used by tests and
preserved by `_force_width(row, N)` extending its stub to the
owning canvas's `winfo_width`. CS-31 adds
`ProjectGraph.find_provisional_op_with_params`, a pure graph
query that locates an existing PROVISIONAL OperationNode of a
given type with full dict-equality on params; threaded through
every UV/Vis apply site so identical re-clicks return None +
status message instead of creating bogus PROVISIONAL siblings
that would collapse into a misleading sweep-group leader row.
Three new register entries logged up front: CS-30 + CS-31 (now
✅), CS-32 (⏳, deferred to 4q). Phase 4p logged four new
friction items (test-fragility process note, status-message
discoverability that pairs with the open Diagnostic console
intent, long-label overflow under uniform-row-width invariant,
CS-32 deferred). 540 tests, all green.*
*1.17: CS-32 + CS-33 + CS-34 added in Phase 4q. CS-32
adds inline expansion to sweep groups: chevron `▸/▾` on the
leader row toggles `parent_id` membership in
`self._expanded_sweep_groups: set[str]` (parallels
`_expanded_history`); routes through `_rebuild` so member
rendering happens in one place; members render with full
chrome via `_populate_node_row`, picking up CS-34's 🔒
commit button along with everything else; group dissolves
naturally when members drop below 2 (no explicit cleanup
needed). CS-33 caps painted label text at module-level
`_LABEL_MAX_CHARS = 32` characters with `…` truncation;
attaches a `_Tooltip` (Toplevel, 600 ms hover, pale yellow)
only when truncation actually cut text; `_begin_label_edit`
reads the canonical full label from the graph rather than
the painted widget text so rename starts with the
untruncated value. CS-34 packs a per-row `tk.Button("🔒")`
between → and ✕ on every PROVISIONAL row, click invokes
`_safely(commit_node, nid)`; committed rows OMIT the button
entirely (the leftmost-cell state indicator already signals
committed state); not in the responsive-optional set —
always-visible commit twin of ✕. Three Phase 4 register
entries marked ✅ (CS-32 + CS-33 + new CS-34 entry "🔒
commit gesture on provisional ScanTreeWidget rows"); the
existing Phase 4k friction #1 register entry "Commit /
discard reachable from the left pane after Apply" drops
from 🔴 to 🟡 (CS-34 satisfies the spirit of the USER-FLAG;
left-pane button-pair stays as a convenience-layer follow-
up). Three new 🟢 register entries logged: cap-from-canvas-
width-and-font-metrics follow-up to CS-33, promote
`_Tooltip` to shared utility module on first cross-module
re-use, indent expanded sub-frames inside sweep groups
(visual nesting). 561 tests, all green (540 + 21 new).*
*1.18: CS-35 + CS-36 added in Phase 4r. CS-35 adds visual
nesting for sweep-group expanded members: module-level
constant `_SWEEP_MEMBER_INDENT_PX = 16`, `_build_node_row`
grows an `indent_px: int = 0` kwarg threaded into
`row.pack(padx=(2 + indent_px, 2), pady=1)`, the sweep-
expansion branch in `_rebuild` passes the constant. Pack-
arg pass-through chosen over wrapper-frame to avoid a
parallel `_member_frames` dict + collapse cleanup. CS-32
contracts (`_expanded_sweep_groups` set type, `_toggle_
sweep_group` flip-and-rebuild, `_compute_sweep_groups` ≥2-
member dissolution) preserved verbatim. CS-36 adds a per-
node baseline-curve toggle: new `style["show_baseline_
curve"]` key with default-True convention parallels
`visible`/`in_legend`; per-row `tk.Button("~"/"–")` packed
between `[☑]` and the label on BASELINE rows ONLY (no
placeholder on non-baseline rows); click routes through
`set_style` so `NODE_STYLE_CHANGED` triggers the existing
`uvvis_tab._redraw` path. `_redraw`'s CS-29 overlay loop
adds one filter line: `if not bool(bn.style.get("show_
baseline_curve", True)): continue`. Master-switch contract
of CS-29 unchanged. StyleDialog universal-section path
deferred (Phase 4d / 4f lock held). Two Phase 4 register
entries marked ✅ (existing "Per-node baseline-curve toggle
(USER-FLAGGED)" → CS-36; existing "Indent expanded sub-
frames inside sweep groups (visual nesting)" → CS-35).
Phase 4r logged five new friction items: tooltip on the
new `[~]` toggle (defer until CS-33's `_Tooltip` is
promoted, Phase 4q friction #3), `~` glyph choice (test
pins literal so future restyle is deliberate), persistence
coverage of the new style key (cross-ref the new persistence
umbrella), legend toggle and baseline toggle both use `–`
when off (disambiguated by row position), tested-by-
integration smoke pattern (process note). Two new 🔴
USER-FLAGGED register entries logged: Project + per-node
persistence with manifest+sidecar+optional-blockchain-anchor
architecture (subsumes the existing Plot config persistence
entry as one phase of a four-phase ladder), Floor-zero
baseline as fit-time constraint per mode (supersedes the
post-shift framing in the existing Scattering baseline
floor-zero shift entry — that entry stays open as the
scattering-specific fitted-offset variant). 579 tests, all
green (561 + 18 new: 6 pure-module + 12 integration).*
*1.19: CS-37 + CS-38 + CS-39 + CS-40 added in Phase 4s. CS-37
ships the universal "Floor at zero" panel toggle and the
constrained-fit code path for 3 of 6 baseline modes
(scattering: closed-form constrained `c`; scattering+offset:
SLSQP convex QP; rubberband: no-op + invariant assert);
linear / polynomial / spline raise a clear ValueError per the
per-mode roadmap. CS-38 adds the new `BASELINE_MODES` entry
`"scattering+offset"` (`B(λ) = a + c · λ^(-n)`), sharing
scattering's Tk vars and parameter row layout. CS-39 adds
`fit_scattering` / `fit_scattering_offset` public helpers
that return the resolved fit parameters; the apply site
records `c_fitted` (always for scattering modes), `a_fitted`
(always for scattering+offset), and `n_fitted` (only when
`n="fit"`) on the OperationNode. CS-40 widens fit-window
error messages in `compute_polynomial`, the shared
`_scattering_window` helper (covers scattering and
scattering+offset), and `uvvis_normalise._window_mask` to
include `"; data spans [<min>, <max>] nm"`. Two register
entries marked ✅ (Scattering baseline fitted-offset →
CS-38; Floor-zero baseline partial 3/6 modes → CS-37).
Phase 4m friction #2 / #3 / #4 struck through (resolved by
CS-39 / CS-38 / CS-40). Phase 4r friction #6 partial-strike.
Four new register entries (1 🔴, 2 🟡, 1 🟢) including
two USER-FLAGGED elevations (Floor-zero toggle disabled
state for unsupported modes; Consolidate scattering+offset
into scattering with optional offset toggle) and one new
🔴 USER-FLAGGED feature (OLIS .ols / .asc UV/Vis file
format support). 615 tests, all green (579 + 36 new: 28
pure-module in test_uvvis_baseline + test_uvvis_normalise;
8 integration in TestUVVisTabBaseline).*
*1.20: Phase 4t — completes the floor-zero per-mode roadmap
(CS-37 expansion to all 6 modes) plus CS-41 + CS-42 + CS-43.
CS-37 ships the constrained-fit code paths for the remaining
three modes: linear (SLSQP on the (a_lo, a_hi) anchor pair),
polynomial (SLSQP on the polynomial coefficients with z-space
conditioning so the Vandermonde stays well-scaled for arbitrary
order), spline (SLSQP on the per-anchor absorbance vector via
NonlinearConstraint that re-uses the shared `_spline_evaluate`
helper for all three branches — 4-anchor cubic, 3-anchor
quadratic, 2-anchor linear). CS-41 adds `params["n_bounds"]:
tuple[float, float]` (default `(0.1, 8.0)`) overriding the
n="fit" bounded-scan range in scattering / scattering+offset;
API-only this session, UI deferred. CS-42 promotes `_Tooltip`
from `scan_tree_widget` to its own `tooltip.py` module (public
class `Tooltip`); the per-row `[~]/[–]` baseline-curve toggle
gains a hover hint and `uvvis_tab` becomes the second consumer
via the floor-zero checkbutton. CS-43 ships the disabled-state
machinery for the universal "Floor at zero" toggle:
`_FLOOR_ZERO_SUPPORTED_MODES` (defensive scaffolding —
currently `frozenset(BASELINE_MODES)`) +
`_refresh_floor_zero_state()` wired to the mode trace + tooltip
rotation via the empty-string sentinel pattern. Three register
entries marked ✅ (Floor-zero per-mode → CS-37; Floor-zero
disabled state → CS-43; the Phase 4q friction #3 / Phase 4r
friction #1 paired entry → CS-42). The "Scattering n-fit scan
bounds configurable via params" register entry stays ⏳ as
"API ✅ / UI ⏳". Three new register entries from step 5
USER-FLAGGED elicitation: per-row `[~]` toggle column
alignment across all node types; second-derivative plot on
separate right y-axis; top-bar Open File / Reload buttons
belong to TDDFT only (not the app top level). Phase 4q
friction #3 + Phase 4r friction #1 struck through (resolved
by CS-42). 637 tests, all green (615 + 22 net new: 19
pure-module in test_uvvis_baseline; 7 integration in
test_uvvis_tab + test_scan_tree_widget; 1 replaced; 4
removed from `TestFloorZeroNotYetImplemented`).*
*1.21: Phase 4u — multi-axis plot routing lands (CS-44).
SECOND_DERIVATIVE renders on a lazily-created right y-axis
via the new `_AXIS_ROLES` / `_DEFAULT_Y_AXIS_BY_NODETYPE` /
`_NON_PRIMARY_Y_LABEL` / `_TERTIARY_AXIS_OFFSET_FRAC`
constants + the `_resolve_y_axis_role` /
`_resolve_non_primary_y_label` helpers in `uvvis_tab.py`.
Per-NodeType default keys SECOND_DERIVATIVE → `"secondary"`
and every existing renderer NodeType → `"primary"`; tertiary
infrastructure ships wired-but-unused for a future NodeType
that needs a third stacked axis (validated end-to-end via a
monkey-patched routing test). `_redraw` builds
`_axes_by_role` lazily; CS-29 baseline-curve overlay and
CS-19 peak-list scatter route through the same resolver for
consistency. Legend handles + labels are merged across every
populated role before being drawn on primary so the
SECOND_DERIVATIVE label still appears in the unified legend.
The x-unit-aware secondary y-label table covers nm /
cm-1 / eV. `_draw_empty` switched from `cla()` to
`_fig.clear()` + role-map reseed so populated → empty
transitions don't leak twin axes. Per-style
`node.style["y_axis"]` override and per-role y-limit Tk vars
deferred per Decisions 1 + 4 in the Phase 4u step-2 design
lock. Three existing SECOND_DERIVATIVE assertions updated to
the new "primary has 1, secondary has 1" line shape. 651
tests, all green (637 + 14 net new: 9 pure-helper in
TestMultiAxisRoutingHelpers + 5 integration in
TestUVVisTabSecondDerivativeIntegration /
TestUVVisTabTertiaryAxisPath).*
*1.22: Phase 4v — per-OperationType implementation hash (CS-45)
+ persistence Phase A manifest+sidecar round-trip (CS-46).
`operation_hash.py` (new module) registers a per-op bundle of
`compute_*` + shared helpers and computes a SHA-256 over the
sorted-by-qualname `inspect.getsource()` bytes; `OperationNode`
gains `metadata: dict` + `deterministic: bool` fields; six apply
sites stamp `metadata["implementation_hash"]` at apply time.
`project_io.py` (full rewrite) replaces the prior
`NotImplementedError` stubs with the manifest+sidecar
implementation: content-addressed HDF5 sidecars (one per unique
arrays bundle, gzip-compressed), whole-app manifest covering
`plot_defaults` + per-tab `plot_config` + per-tab `graph` (data
nodes + op nodes + edges + active overrides). `binah.py` adds
Save Workflow / Save Workflow As… / Open Workflow… / Recent
Workflows menu items routing to the new format and surfaces
`LoadedProject.implementation_warnings` via a "Implementation
Changed Since Save" dialog (Keep cached + Show details; Re-run
deferred). UVVisTab gains `_restore_workflow_payload` for
in-place graph swap on load. Phase A explicit deferrals: .ptmg
zip-archive form, original instrument file persistence, sidecar
GC, re-run-all-changed action, Phases B/C/D. Test infrastructure
addition: `_test_silence` module silences modal Tk messageboxes
during test runs (wired into `run_tests.py` and
`test_persistence_phase_a.py`). 708 tests, all green (651 + 45
new pure-module + 12 new integration).*
*1.23: Phase 4w — adjustable-sidebar UX work (CS-47 + CS-48).
CS-47 ships per-cell minimum-width vocabulary (`_CELL_MIN_PX`
covering every row cell), pinned `_SIDEBAR_MIN_WIDTH_PX = 240`
(matching the smallest CS-26 threshold so the responsive helper
and the PanedWindow `minsize` stay in lock-step), pure helper
`_label_char_capacity(canvas_width_px, avg_char_px, overhead_px)`
clamped to `[_LABEL_CHAR_FLOOR=8, _LABEL_CHAR_CEIL=64]` with
fallback to `_LABEL_MAX_CHARS=32`, widget-instance methods
`_label_font` / `_avg_char_px` / `_label_overhead_px` /
`_current_label_cap` / `widest_label_pixel_width`, and the
`_apply_responsive_layout` re-truncation pass that rotates
the always-attached label tooltip's text via the empty-string
sentinel (no Tooltip create/destroy churn).
`UVVisTab._calibrate_sidebar_width` runs once via `after_idle`
after construction, computes `target = clamp(widest_label_px +
overhead_px, [240, 480])` and calls `body.sash_place(2,
paned_width - target, 0)`. Idempotent — the
`_sidebar_calibrated` flag flips True after the first
successful run so manual sash drags persist. CS-48 ships the
fixed-width `row_toggle` Frame slot at
`_CELL_MIN_PX["row_toggle"] = 22` packed on every row
regardless of node type so labels start at the same x;
BASELINE rows host the `[~]` toggle inside the slot, every
other type leaves it empty. The original Phase 4t friction #1
proposal (disabled-button on every row) was rejected as more
expensive and UX-confusing. Existing `TestPerNodeBaselineCurve
Toggle._bc_button_in` test helper updated to recurse one level
into the slot. CS-33 invariants (`_LABEL_MAX_CHARS = 32`,
`_truncate_label` signature, `text[:max-1] + "…"` shape),
CS-26 invariants (`_RESPONSIVE_THRESHOLDS_PX` values + tuple
shape + priority order), CS-30's responsive-helper signature,
CS-35's indent_px kwarg, and CS-36's per-row-toggle
behavioural contract all preserved. 738 tests, all green
(708 + 30 new: 12 pure-module across TestCellMinPxVocabulary
+ TestSidebarMinWidth + TestLabelCharCapacity; 18 integration
across TestRowToggleColumnAlignment + TestDynamicLabelCap
Wiring + TestWidestLabelPixelWidth +
TestUVVisTabSidebarCalibration).*
*1.24: Phase 4x — cross-type panel parent acceptance widening
(CS-49). Resolves Phase 4w friction #1 (USER-FLAGGED 🔴 —
"Cannot do baseline correction from a smoothed spectrum.
Cannot smooth derivative plots."). Two tuples widened:
`UVVisTab._BASELINE_ACCEPTED_PARENT_TYPES` adds `SMOOTHED`;
`SmoothingPanel.ACCEPTED_PARENT_TYPES` adds
`SECOND_DERIVATIVE`. `_refresh_shared_subjects` now walks
both `_spectrum_nodes` and `_second_derivative_nodes` so the
combobox surfaces derivative rows; `_spectrum_nodes` itself
untouched (renderer iterates the two helpers separately for
axis-role routing under CS-44). Audit pass result:
NormalisationPanel / PeakPickingPanel / SecondDerivativePanel
intentionally NOT widened — existing exclusions are
deliberate per panel-side comments; user has not flagged.
Each unchanged tuple is now pinned by an audit-stability
`test_accepted_parent_types_constant` whose comment must move
in lock-step with any future widening. Decisions taken: (i)
explicit type-list gate kept (vs "any DataNode with arrays"
— preserves per-panel exclusion expressivity); (ii) y-axis
routing of cross-typed outputs deferred to existing CS-44 —
smoothed-of-derivative output carries SMOOTHED → routes to
"primary"; the misroute fix lives in carry-forward T
(per-style `y_axis` override hook), not Phase 4x. Three
pre-existing contract tests rewritten to invert old "no
SECOND_DERIVATIVE in combobox" assertions + split the old
"SMOOTHED disables both normalise and baseline" into the new
"normalise-only-disabled" form. Compute helpers
(`uvvis_baseline.compute`, `uvvis_baseline.compute_baseline_curve`,
`uvvis_smoothing.compute`) are all type-agnostic and required
no changes — the CS-49 widening only made new parent-types
reachable; the math handles them transparently. CS-22 +
CS-26 + CS-29 + CS-30 + CS-33 + CS-44 + CS-45 + CS-47 +
CS-48 invariants all preserved. Phase 4k friction #6
reinforced (the inline baseline tuple still lives on
UVVisTab — extraction belongs to whichever phase factors
out a `BaselinePanel` widget). 746 tests, all green
(738 + 8 new: 3 in TestSmoothingPanel for
SECOND_DERIVATIVE acceptance + 5 in new
TestUVVisTabPhase4xCrossTypeAcceptance for end-to-end flows
+ audit stability + combobox order).*
*1.25: Phase 4y — per-style `y_axis` override hook + StyleDialog
Combobox row (CS-50). Closes the carry-forward T from Phase 4u
Decision 1 (USER-LOCKED "Default only for now is okay"; the
deferral was the canonical Phase 4u friction #10 register entry,
now ✅) and Phase 4x friction #6 (smoothed-of-derivative
misroute, USER-NOTED) in one phase. `node_styles.default_spectrum_style`
adds `style["y_axis"]: str | None` (default `None` = follow
NodeType default; non-`None` = literal CS-44 axis role overrides
per-node); `uvvis_tab._resolve_y_axis_role` grows an optional
`style: Mapping | None = None` argument with a one-line short-
circuit at the front. Renderer threads `node.style` at three
call sites in `_redraw` (per-node main loop; BASELINE-curve
dashed overlay moved INSIDE per-bn body so main + overlay land
on the same axis; PEAK_LIST scatter moved INSIDE per-peak loop).
StyleDialog universal section gains a read-only `ttk.Combobox`
row labelled "Y axis:" with options `["(default)", "primary",
"secondary", "tertiary"]`; "(default)" round-trips to `None`.
`_BULK_UNIVERSAL_KEYS` intentionally NOT extended (parallel to
Phase 4d's `visible` / `in_legend` carve-out); per-row ∀ button
widens its scope to every renderable node via
`_on_uvvis_apply_to_all`'s special-case for the key.
`SmoothingPanel._apply` writes `style["y_axis"] = parent_effective_role`
on cross-typed outputs (today: smoothed-of-derivative →
"secondary") IFF NodeType-defaults differ. Decision lock taken:
(i) cross-typed-Apply auto-inheritance fires IFF NodeType-
defaults differ; (ii) "(default)" = literal `None` semantics,
inheritance is a separate apply-time mechanism; (iii) y_axis
bulk-fan-out scope = renderable nodes only. CS-44 locks all
preserved (`_AXIS_ROLES` / `_DEFAULT_Y_AXIS_BY_NODETYPE` /
`_NON_PRIMARY_Y_LABEL` / `_TERTIARY_AXIS_OFFSET_FRAC` /
`_resolve_non_primary_y_label` byte-identical;
`_resolve_y_axis_role` signature widened additively per the
docstring's anticipated extension). CS-46 manifest schema
unchanged (the new key auto-rides the existing style-dict
round-trip). 781 tests, all green (746 + 35 new: 7 pure-helper
in TestResolveYAxisRoleStyleOverride + 2 in
TestDefaultSpectrumStyle + 16 in TestStyleDialogYAxisOverride
+ 4 in TestUVVisTabPhase4yYAxisOverride + 3 in
TestUVVisTabPhase4yCrossTypedInheritance + 3 in
TestUVVisTabPhase4yApplyToAllScope).*
*1.26: Phase 4z — width-aware label-cell overhead helper (CS-51).
Closes Phase 4x friction #1 (USER-FLAGGED, swatch-reveal label-
cap drift) and Phase 4w friction #6 (measure actual row overhead)
for the optional-cell visibility axis. `scan_tree_widget` lifts
the previously inline cell-vocabulary into module-level constants
`_ALWAYS_VISIBLE_CELLS` (the seven Phase 4w always-visible cells)
and `_OVERHEAD_SLACK_PX = 30` (the inter-cell padding slack), and
adds two pure helpers — `_compute_label_overhead_px(visible_optional_cells)`
sums the always-visible cells + the named optional cells +
slack; `_visible_optional_cells_for_width(width_px)` walks
`_RESPONSIVE_THRESHOLDS_PX` and returns the optional cells
revealed at the given width (mirrors `_apply_responsive_layout`'s
reveal predicate exactly so cap and layout cannot drift). The
`_label_overhead_px(self, width: int | None = None)` widget
method gains a `width` kwarg; `width=None` returns the no-args
baseline (byte-equivalent to Phase 4w) for `_calibrate_sidebar_width`'s
unchanged use, and `_current_label_cap` forwards the canvas width
so the dynamic cap shrinks the moment any optional cell reappears
at its CS-26 threshold. CS-26 + CS-47 + CS-48 invariants all
preserved. 805 tests, all green (781 + 24 new: 19 pure-helper
+ 5 integration). Phase 4z friction list: three 🟢 Claude-
surfaced polish notes, none promoted to register entries (user-
accepted at step 5).*
*1.27: Phase 4aa — StyleDialog y-axis visibility predicate +
label-rename Entry (CS-52). Closes Phase 4y friction #1 in full
(Claude-surfaced "Y-axis Combobox row appears on non-UVVis
StyleDialog instances"; path (a) NodeType-gate landed) and the
"first concrete add" half of Phase 4x friction #2 (USER-FLAGGED
"StyleDialog must surface ALL node-table parameters incl. label
rename"; the LabelFrame re-org + tabs question stays open).
`style_dialog` adds module-private `_Y_AXIS_VISIBLE_NODETYPES:
frozenset[NodeType]` mirroring `uvvis_tab._DEFAULT_Y_AXIS_BY_NODETYPE.keys()`
exactly (UVVIS / BASELINE / NORMALISED / SMOOTHED / PEAK_LIST /
SECOND_DERIVATIVE), pinned by the drift test
`test_y_axis_visible_node_types_match_routing_table`.
`_build_universal_section` wraps the `_build_y_axis_row` call in
`if self._node_type in _Y_AXIS_VISIBLE_NODETYPES`; on the seven
non-routing NodeTypes the Combobox is suppressed,
`_read_universal_values` skips the key automatically, and Save /
Apply / ∀ paths stay self-consistent. New `_build_label_row`
inserts a "Label:" Entry at the top of the universal grid (row
0; existing rows shift down by 1, relative order preserved per
the lock-relaxation reading); a `trace_add('write')` callback
commits each keystroke through the new `_write_label_partial`
helper, which routes via `graph.set_label` (label is a top-level
DataNode slot, not a style key) under the same `_suspend_writes`
re-entrancy guard `_write_partial` uses. `__init__` snapshots
`node.label` alongside `node.style`; `_do_cancel` reverts both.
`_on_graph_event` gains a `NODE_LABEL_CHANGED` branch that
refreshes the Entry + the dialog title in place. Lock decisions
taken Phase 4aa step 2: (i) **defer** the LabelFrame re-org +
tabbed-shape question — single-pane with Label at top this
phase, the re-org pairs with Phase 4x friction #3 + #4
(Provenance tab + "Add to graph") in a future combined intent;
(ii) **no inline validation** — match CS-33's sidebar gesture
behaviour; (iii) **no widget lifts** — universal rows preserve
relative order. CS-50 + CS-44 invariants all preserved
(`_DEFAULT_Y_AXIS_BY_NODETYPE` / `_resolve_y_axis_role` / `_AXIS_ROLES`
byte-identical; the gate is purely additive). CS-46 manifest
unchanged (the visibility predicate lives entirely on the dialog
side; no new persisted state). 832 tests, all green (805 + 27
new: 2 pure-module drift in TestStyleDialogPhase4aaConstants + 15
visibility-matrix in TestStyleDialogYAxisVisibility + 10 label-
rename in TestStyleDialogLabelRename). Phase 4aa friction list:
six 🟢 Claude-surfaced polish notes, none promoted to register
entries (user-accepted at step 5).*
*1.29: Phase 4ac — drop CS-31 dedup gate + drop CS-32 sweep auto-
grouping (CS-54). Closes parts (a) + (b) of the USER-FLAGGED
Phase 4v friction #1 register entry; defers part (c)
(NodeType.NODE_GROUP + user-driven "Combine selected → Group"
gesture) to Phase 4ad. `find_provisional_op_with_params` removed
from `graph.py`; the dedup short-circuit removed from all five
UV/Vis apply sites; `_compute_sweep_groups`, `_build_sweep_row`,
`_toggle_sweep_group`, `_expanded_sweep_groups`, `_sweep_groups`,
`_sweep_leaders`, `_group_key_of`, `_discard_many`,
`_datanode_parents` all removed from `scan_tree_widget.py`.
Identical re-applies now create fresh standalone PROVISIONAL
siblings. CS-31 + CS-32 register entries above are now struck
through (✅→reverted). CS-35 lock survives (the
`_SWEEP_MEMBER_INDENT_PX = 16` constant + the
`_build_node_row(indent_px=0)` kwarg signature stay verbatim for
Phase 4ad reuse). 864 tests, all green (878 − 14 removed + 9 new
pin tests added; per-panel suppress-tests inverted in place).
Phase 4ac friction list: six items (1 USER-FLAGGED y-axis label
routing bug bumped 🟢 → 🔴 from Phase 4y friction #2; 2
USER-FLAGGED Plot Settings additions — configurable grid colour
+ default-inward ticks; 3 Claude-surfaced 🟢 polish notes covering
Phase 4ad's NODE_GROUP carry-forward, the dormant
`_SWEEP_MEMBER_INDENT_PX` constant, and the no-cue-for-N-identical-
siblings polish).*
*1.28: Phase 4ab — StyleDialog Notebook restructure + Provenance
tab (CS-53). Closes Phase 4x friction #3 (USER-FLAGGED "Per-node
parameter window: add a Provenance tab") in full plus the
"tabbed shape" lock decision (i) of Phase 4x friction #2
(USER-FLAGGED "StyleDialog must surface ALL node-table
parameters … + tighten organisation for scale"). The dialog body
becomes a `ttk.Notebook` with Tab 1 "Style" hosting the existing
universal + conditional sections verbatim (rows + relative
ordering preserved per the CS-52 lock relaxation; only the parent
widget changes) and Tab 2 "Provenance" hosting the read-only
ancestor walk. Bottom Apply / ∀ Apply to All / Save / Cancel row
stays outside the Notebook so it's visible regardless of which
tab is active. New module-level constants: `_NOTEBOOK_TAB_TITLES`
(tuple, locks tab order); `_PROVENANCE_STATE_DISPLAY` (NodeState →
display text + foreground colour, with DISCARDED dimmed grey
#888888); `_PROVENANCE_REFRESHING_EVENTS` (the five graph-event
types that mutate the displayed walk —
NODE_LABEL_CHANGED / NODE_DISCARDED / NODE_COMMITTED /
NODE_ADDED / EDGE_ADDED). Three new pure helpers
(`_provenance_state_display`, `_format_provenance_op_params`,
`_format_provenance_node_summary`) reduce graph nodes to display
strings — Tk-free, fully unit-tested. The Provenance tab uses a
Canvas + Scrollbar pair with an inner Frame for the per-ancestor
blocks; eager construction at `__init__` (Decision (ii)). Each
block carries a header (label · type · state badge) plus, for
OperationNodes, a Courier body block with pretty-printed params,
engine + version, and a 12-char-prefix truncated implementation
hash. The "(unregistered)" sentinel from `operation_hash` survives
truncation as an explicit suffix marker. DISCARDED ancestors
render unfiltered with the dimmed foreground colour (Decision
(iv)). `_on_graph_event` restructured to run a Provenance rebuild
before the existing same-node early-return; the
`_suspend_writes` guard still gates BOTH halves so the dialog's
own keystroke-driven label rename does NOT rebuild Provenance per
keystroke (perf trade-off accepted in Phase 4ab; bottom-of-chain
block is briefly stale during typing). `graph.provenance_chain`
reused as the ancestor walk source; no `graph.py` change needed.
CS-52 invariants all preserved (`_Y_AXIS_VISIBLE_NODETYPES`,
`_build_label_row`, `_write_label_partial`, `_snapshot_label`,
`_do_cancel` revert order — all byte-identical). CS-50 + CS-44 +
CS-46 unaffected. 878 tests, all green (832 + 46 new: 22
pure-module helpers in `TestStyleDialogPhase4abHelpers` + 9
Notebook structure in `TestStyleDialogPhase4abNotebook` + 15
Provenance tab in `TestStyleDialogPhase4abProvenanceTab`).
Phase 4ab friction list: TBD — populated by step 5 + step 6 of
the bookkeeping commit.*
*1.30: Phase 4ad — role-agnostic y-axis label resolution (CS-55).
Closes Phase 4ac friction #1 (USER-FLAGGED 🔴) in full plus the
Phase 4y friction #2 and Phase 4aa friction #5 cross-refs to the
same root issue. The user reproduced the bug end-to-end at end
of Phase 4ac: placing Absorbance on the secondary axis and a
derivative on the primary axis used to leave "Absorbance" on the
empty left axis and the right side unlabelled. CS-55's fix
recognises that label dimensionality varies by NodeType class,
not by axis role. New `_ABSORBANCE_SPACE_NODETYPES: frozenset`
covering UVVIS / BASELINE / NORMALISED / SMOOTHED / PEAK_LIST +
`_ABSORBANCE_Y_LABEL` y-unit → label dict, both module-level in
`uvvis_tab`. New pure helper `_resolve_y_axis_label(node_type,
x_unit, y_unit) -> Optional[str]`: absorbance-space NodeTypes
label by y-unit (independent of x-unit and role); derivative-
space NodeTypes fall through to the existing CS-44
`_NON_PRIMARY_Y_LABEL` table (which now feeds both primary and
non-primary roles). Renderer in `_redraw` widens
`first_node_type_per_role.setdefault` to record primary too,
drops the hardcoded primary-ylabel inline lookup, and walks
every populated role through the helper. `ylabel_mode = "custom"`
still wins for primary (user-text affordance remains primary-
only); non-primary always auto. Default routing (UVVIS-only) is
byte-identical pre/post — the common case is unchanged. **Lock
decision taken:** option (b) variant of the three architecture
options surveyed — single helper keyed on NodeType class rather
than two parallel tables, because the dimensionality of
variability is NodeType nature (absorbance-space vs derivative-
space), not axis role. CS-44 invariants ALL preserved
(`_NON_PRIMARY_Y_LABEL` content + `_resolve_non_primary_y_label`
signature byte-identical; the new helper layers on top). CS-50
+ CS-52 + CS-53 + CS-54 unaffected. Five Claude-surfaced 🟢
friction items at step 5 without new register entries (user
accepted no new items): first-node-on-primary wins label policy;
`_NON_PRIMARY_Y_LABEL` misnamed post-CS-55; empty-primary
silently unlabelled; Phase 4u friction #9 cross-ref to value-
corruption half; BACKLOG.md changelog gap for Phase 4ac. 882
tests, all green (864 + 9 pure-module in
`TestYAxisLabelResolution` + 9 integration in
`TestYAxisLabelRoleSwap`).*
*1.31: Phase 4ae — Plot Settings → Appearance gains three new
controls (CS-56). Closes the two USER-FLAGGED 🟡 Phase 4ac
friction items in full ("Configurable plot grid colour" +
"Default to inward-facing axis ticks") plus the promote-to-Plot-
Settings half of the CS-44 follow-up register entry (the larger
`plot_widget.py` lift stays carry-forward). Three new entries in
`plot_settings_dialog._FACTORY_DEFAULTS`: `"grid_color"` =
`"#b0b0b0"` (matplotlib's standard light grey, preserves existing
visual), `"tertiary_axis_offset"` = `1.12` (drift-pinned against
`uvvis_tab._TERTIARY_AXIS_OFFSET_FRAC`), and `"tick_direction"`
flipped `"out"` → `"in"`. Two new rows in
`_build_section_appearance`: colour swatch for `grid_color` at
row=1 (existing Background + Tick direction rows shift down by
one), inline `tk.Spinbox` for `tertiary_axis_offset` at row=4
bound to a new `_on_float_var_write` helper. Three new renderer
reads in `uvvis_tab._redraw`: `ax.grid(color=...)`, the inward-
tick fallback flip, and `tertiary_offset` local that replaces the
bare `_TERTIARY_AXIS_OFFSET_FRAC` consumer in the `get_axis(role)`
closure. **Lock decisions taken:** grid colour is app-global /
single-colour / plot-wide; tick flip is factory-default-only / no
migration; tertiary offset is row-only (plot_widget.py lift stays
carry-forward). Retroactive `*1.28: Phase 4ac…*` BACKLOG entry
inserted (the changelog gap that Phase 4ad surfaced). 899 tests,
all green (882 + 17 new: 10 pure-module in
`TestAppearanceSectionPhase4ae` + 7 integration in
`TestUVVisTabAppearancePhase4ae`).*
*1.32: Phase 4af — user-driven `NodeType.NODE_GROUP` container +
"Combine selected → Group" gesture (CS-57). FULLY resolves the
canonical Phase 4v friction #1 "Drop CS-31 + introduce user-
driven node groups" register entry (USER-FLAGGED 🔴) — Phase 4ac
shipped parts (a) + (b), Phase 4af ships part (c). Also closes
Phase 4ac friction #4 (Phase 4ad → 4af carry-forward; intent
slipped two phases) + Phase 4ac friction #5 (the dormant
`_SWEEP_MEMBER_INDENT_PX` + `_build_node_row(indent_px=0)` kwarg
— now LIVE). Graph layer: new `NodeType.NODE_GROUP` enum variant
(arrays={}, `metadata["member_ids"]: list[str]`); new
`ProjectGraph.create_group(member_ids, label=None) -> str` +
`dissolve_group(group_id)` + `group_of(node_id) -> Optional[str]`;
`discard_node` grew an auto-dissolve cascade (recursively
discards a group when fewer than two active members remain;
bounded at one level by flat-only). UI layer: ScanTreeWidget
gained click-toggle selection (`_selected_node_ids` set,
`<ButtonRelease-1>` so double-click rename nets zero toggle),
footer "Group selected" button (predicate mirrors `create_
group`), group-row pipeline (`_build_group_row` with chevron
▾/▸ + "(N members)" badge + inline ✕), chevron `_expanded_
groups` set, simplified group context menu via
`_show_group_context_menu` (Rename / Expand-or-Collapse /
Ungroup). Top-level rendering excludes grouped members;
expanded groups render members below with `padx=(2 +
_SWEEP_MEMBER_INDENT_PX, 2)`. Right-click on data rows grew
"Group selected (N)" entry. **Lock decisions taken:** (i)
context-menu + left-pane footer button (both surfaces); (ii)
flat only, no nesting; (iii) Ungroup via context-menu + inline
✕ on group rows; (iv) reuse `_SWEEP_MEMBER_INDENT_PX = 16`
(CS-35 lock survives, purpose realised). Additional Claude-side
locks: default label `"Group N"`; members keep their parent
edges; single-membership enforced; NODE_ADDED on create +
NODE_DISCARDED on dissolve; renderer-skip invariant; groups
always PROVISIONAL; `project_io` round-trips through existing
DataNode schema. Two new USER-FLAGGED register entries surfaced
at step 5: 🟡 Keyboard shortcuts — whole-interface evaluation
pass (multi-phase); 🟡 "Add to existing group" gesture (Phase
4ag candidate). Recorded design constraint: no info bleed
between tabs unless explicit (USER-CONFIRMED). Four Claude-
surfaced 🟢 polish notes in Phase 4af friction (group "(N
members)" suffix on user-renamed groups; "Show hidden" toggle
opacity; static footer button label; menu-introspection
monkey-patch). 949 tests, all green (899 + 50 new across four
files).*
*1.33: Phase 4ag — Extend + Remove gestures for NODE_GROUP
(CS-58). Fully resolves the canonical Phase 4af follow-up
"'Add to existing group' gesture" register entry (USER-FLAGGED
🟡). Also closes Phase 4af friction #6 (static button label)
by relaxing CS-57's `text="Group selected"` initial-label
lock. Graph layer: new `ProjectGraph.extend_group(group_id,
member_ids)` + `remove_from_group(node_id)` methods + new
`GraphEventType.NODE_GROUP_MEMBERS_CHANGED` event (payload
`{"group_id", "added", "removed"}`); `remove_from_group`
routes through `discard_node` for auto-dissolve when active
member count drops below 2 (re-using CS-57's cascade
threshold), suppressing `MEMBERS_CHANGED` in that branch so
subscribers see exactly one terminal event. UI layer: new
`_classify_selection` helper returns one of `"none"` /
`"group"` / `"extend"` / `"invalid"` so the footer button +
both context menus share a canonical analysis; footer button
mutates text per classification (`"Group selected (N)"` /
`"Add to <group label>"` / baseline disabled); group-row
context menu grows a fourth entry "Add selected to this
group (N)"; data-row context menu grows two siblings
("Add selected to <group label> (N)" + per-row "Remove from
group"). **Lock decisions taken:** (i) both surfaces —
context menu AND footer button; (ii) append (preserve caller
order); (iii) new `NODE_GROUP_MEMBERS_CHANGED` event type
(rejected NODE_LABEL_CHANGED — scan tree routes label-changed
to targeted refresh, but member changes are structural);
(iv) yes — symmetric `remove_from_group` ships in the same
phase. **Lock relaxations to CS-57:** narrow "any group in
selection → button disabled" semantics broadened (1 group +
≥1 ungrouped now routes to extend); `text="Group selected"`
initial-label lock broadened (mutates per classification).
Three new USER-FLAGGED 🟡 register entries surfaced at step
5: grid renders in front of data lines (one-line fix, high
bundling potential); axis double-click → axis-properties
dialog (multi-phase, new dialog shell); "Show hidden" toggle
should disable when no hidden rows exist (upgraded from
Phase 4af friction #5 🟢 by user flag during verification).
Four Claude-surfaced 🟢 polish notes: `_can_group_selection`
preserved as thin alias of `_classify_selection`; spy-menu
pattern duplicated between Phase 4af + 4ag tests; "Add to
<group>" 24-char truncation cap hand-tuned (not responsive);
right-click-target / selection-payload convention
undocumented in CS-04. Phase 4af friction #4 ("(N members)"
suffix relocation) stays carry-forward — Phase 4ag explicitly
scoped it out because the existing inline rendering
refreshes correctly on the new structural-rebuild path.
1002 tests, all green (949 + 53 new across three files: 27
in `test_graph.TestNodeGroupExtendRemoveOps` + 24 in
`test_scan_tree_widget.TestScanTreeWidgetNodeGroupsPhase4ag`
+ 2 in `test_persistence_phase_a.TestSaveLoadRoundTrip` for
the extend+remove and auto-dissolve cascade round-trips).*
*1.34: Phase 4ah — polish bundle (A.1 + A.2 + F + G).
Resolves four BACKLOG register entries in one phase, each
scoped narrowly: (A.1) USER-FLAGGED Phase 4ag friction #1 —
grid renders in front of data lines: `ax.grid(...)` in
`uvvis_tab._redraw` now takes `zorder=0` so gridlines paint
behind data; (A.2 — CS-59 Thread A) USER-FLAGGED Phase 4ag
friction #3 / Phase 4af friction #5 chain — "Show hidden"
Checkbutton disable-gating: new `_has_hidden_rows()` predicate
+ `_refresh_show_hidden_button_state()` companion to
`_refresh_group_button_state`, called from `_rebuild`'s tail;
Checkbutton is now `self._show_hidden_btn`; cascade contract
locked (never silently flip `_show_hidden`). (F) USER-FLAGGED
Phase 4t friction #3 — Open File / Reload relocate from the
app-level top bar into the TDDFT tab's left sidebar (path (a)
from the register entry — each tab owns its file ingestion;
the flanking ttk.Separator is removed too). (G — CS-59
Thread B) Phase 4u friction #9 — `_absorbance_to_y(absorbance,
y_unit, node_type)` signature widened with a NodeType gate
keyed on CS-55's `_ABSORBANCE_SPACE_NODETYPES` frozenset;
SECOND_DERIVATIVE values pass through unchanged on `%T`,
fixing the d²A/dλ² corruption bug. **Lock decisions taken
(Phase 4ah):** (i) hard-code `zorder=0`, no Plot Settings key
(no plausible user wants grid in front of data lines, this
is render correctness); (ii) UV/Vis tab only this phase
(other tabs migrate on renderer adoption); (iii) disable-only
on the Show hidden gate — no count badge or tooltip; (iv)
cascade preserves `_show_hidden` ON when the last hidden row
disappears (disabled state is the affordance); (v) member-of-
collapsed-group counts as hidden (avoids whiplash on
expand/collapse); (vi) path (a) for TDDFT chrome — re-render
in the tab, not tab-context-aware top-bar; (vii) sidebar `«`
toggle + "TDDFT Section:" combobox + file label stay in the
top bar this phase (USER-CONFIRMED for the `«` + combobox
follow-up as a new 🟢 BACKLOG entry); (viii) global Ctrl+O
keybinding stays bound to `_open_file` (keyboard-shortcut
scope-by-tab is its own future phase); (ix)
`_absorbance_to_y` extends signature rather than branching at
the three call sites (helper owns the rule). **Lock
relaxations:** none to CS-55, CS-57, CS-58, CS-44 — all
preserved byte-identical; CS-55 invariant 1 explicitly
RE-LOCKED here (adding SECOND_DERIVATIVE to
`_ABSORBANCE_SPACE_NODETYPES` would regress this phase's
fix). The user noted a multi-axis-defaults design question at
step 5 (what counts as a tertiary-y-axis default per tab —
UV/Vis derivative→secondary is clear, but tertiary candidates
are tab-specific); recorded as a new 🟢 BACKLOG entry for a
dedicated future phase rather than bundled. 1022 tests, all
green (1002 + 20 new across two files: 2 in
`test_uvvis_tab.TestUVVisTabGridZOrderPhase4ah` + 11 in
`test_scan_tree_widget.TestShowHiddenButtonGatingPhase4ah` +
7 in `test_uvvis_tab.TestAbsorbanceToYNodeTypeGatePhase4ah`).
No test added for the TDDFT button relocation — Lock 13
explicitly accepted manual smoke for a one-button-parent
move on a module that has no existing test coverage.*
*1.35: Phase 4ai — unified PlotConfigDialog Notebook + cross-tab
pending-edit state model (CS-60). Foundation for the
USER-FLAGGED axis double-click feature register entry from
Phase 4ag: instead of a separate axis-properties dialog, CS-60
ships a single PlotConfigDialog with a ttk.Notebook hosting six
tabs — Global (today's PlotSettings content unchanged) plus
Primary X / Secondary X / Primary Y / Secondary Y / Tertiary Y
shells. The ⚙ button opens on Global; double-clicking on a
plot axis region opens on that axis's tab. New
`plot_axis_hit_test.py` module classifies bbox-relative
matplotlib events into five axis roles × three hit kinds.
Cross-tab pending-edit state model: per-tab `" •"` modified
marker, `_modified_tabs: set[str]` source of truth,
`_KEY_TO_TAB` routing map (empty today, every key resolves to
Global). New four-button row Save / Apply / Apply to All Tabs /
Cancel — Apply to All Tabs disabled unless host wires
`on_apply_all_tabs`; Cancel-with-pending shows askokcancel
"Discard changes?" confirm (silenced True preserves CS-23
test contract). UV/Vis double-click integration:
`UVVisTab._on_mpl_axis_double_click` binds button_press_event
and dispatches to `open_plot_config_dialog(..., tab=hit.role)`.
**Lock decisions taken (Phase 4ai):** (i) one unified dialog
with axis-tab selector via Notebook, not one dialog per axis
clicked; (ii) module file name stays `plot_settings_dialog.py`
(minimises import churn across binah / project_io / persistence
tests); (iii) cross-tab pending edits persist across tab
switches (navigation gesture, not commit boundary); (iv)
modified marker is " •" bullet, IntelliJ-style; (v) Apply to
All Tabs replicates to same-tab-type siblings only, host-
defined (cross-tab-type plot-setting replication is not a
thing); (vi) Cancel-confirm uses `askokcancel` (not
`askyesno`) so silenced-test default True matches existing
"Cancel always closes" contract; (vii) hit-test bands
`_TOTAL_BAND_PX=40` / `_SPINE_BAND_PX=6` / `_TICK_BAND_PX=18`
/ `_TERTIARY_BAND_PX=24`; (viii) tertiary band tested first
so secondary-y gets clipped at the offset spine; (ix)
right-side click with no twinx maps to primary_y (the right
spine of the primary axes); (x) axis tabs are shells in
Phase 4ai — placeholder header / badge / "Plots on this axis"
LabelFrame / "Settings" LabelFrame — real per-axis settings
start landing Phase 4aj+. **Lock relaxations:** CS-23
subsumed into CS-60 (class name, factory name, button row
vocabulary all evolve; the locked semantics persist:
"Apply commits and stays open, Save commits and closes,
Cancel reverts to snapshot"). Two new USER-FLAGGED register
entries from step 5: `_USER_DEFAULTS` tab-type split when the
dialog wires into a second tab type (XANES axis labels
≠ UV/Vis); Twin-X full wiring (matplotlib `twinx()` +
wavelength↔energy transform + bidirectional range coupling).
Five Claude-surfaced 🟢 polish notes: Apply-to-All-Tabs
unwired today; live axis-tab badges deferred to 4ak;
`hit_kind` ignored at dialog level; tertiary x-axis not
classifiable today (no twin-x machinery yet); band-size
tuning if matplotlib layout changes. 1113 tests, all green
(1022 + 91 new across four files: 37 in
`test_plot_axis_hit_test` + 44 in
`test_plot_settings_dialog` Phase 4ai classes + 10 in
`test_uvvis_tab.TestUVVisTabAxisDoubleClickPhase4ai`).*
*1.36: Phase 4aj — tick_direction widget relocation to per-axis
tabs (CS-61). First slice of the per-axis settings ladder
(Phase 4aj→4an). The widget moves out of Plot Settings →
Appearance (row 3 vanishes; tertiary_axis_offset slides from
row 4 → row 3) and into a new "Settings" LabelFrame on each of
the five per-axis Notebook tabs. All five tabs share one Tk var
(`_control_vars["tick_direction"]`) so editing on one tab
visually reflects on the other four. The single flat working-
copy key `tick_direction` is preserved — Phase 4ak invents the
per-axis nested schema; Phase 4aj is the smallest possible real
relocation, no schema change. New `_KEY_TO_TAB` routing map
(empty in 4ai) gets its first explicit entry —
`{"tick_direction": "primary_x"}` — so editing the radio on
ANY per-axis tab marks ONLY Primary X dirty (not the full
five-tab set). New `_build_axis_tab_settings(parent, role)`
helper, called from `_build_axis_tab_shell` for each non-Global
role, is the body builder future per-axis ladder phases extend.
The fallback in the helper reads from
`_FACTORY_DEFAULTS["tick_direction"]` not a hard-coded "in"
literal so a future schema flip can't drift. **Lock relaxations
(Phase 4aj):** CS-60 lock 4 (`_KEY_TO_TAB` was empty) — the map
now carries one entry, intentional growth not a lock break.
CS-56 invariant — `_build_section_appearance` no longer grids
tick_direction. **Locks held:** every CS-56 / CS-60 lock except
the two relaxations above; `_FACTORY_DEFAULTS["tick_direction"]
= "in"` schema invariant; `_USER_DEFAULTS` flat shape; all CS-44
+ CS-49 + CS-50 + CS-55 + CS-57 + CS-58 + CS-59 invariants
unchanged. Four code commits across the phase: (1) widget
relocation + routing map entry + Appearance section renumber +
docstring updates; (2) `TestPlotConfigDialogTickDirectionRelocation
Phase4aj` with 13 invariants; (3) two pre-existing Phase 4ai
tests updated for the relocation (`test_axis_tab_shell_carries_
phase_4aj_placeholder` renamed and inverted;
`test_key_to_tab_defaults_to_global` narrowed); (4) hard-coded
"in" fallback in `_build_axis_tab_settings` routed through
`_FACTORY_DEFAULTS["tick_direction"]`. **Decision lock taken
(Phase 4aj):** (i) widget mirrors across ALL FIVE per-axis tabs
sharing one Tk var (not Global tab; not one arbitrary axis tab
in isolation; not five independent vars — that's 4ak's job);
(ii) `_KEY_TO_TAB["tick_direction"] = "primary_x"` because tick
direction is most visually associated with bottom X-axis ticks
in a UV/Vis plot; (iii) Appearance section row 3 (tick
direction) deletes cleanly; tertiary_axis_offset moves up to row
3; grid_color and tertiary_axis_offset stay in Appearance. One
new USER-FLAGGED 🟡 register entry surfaced at step 5: external-
output plot style presets (J. Am. Chem. Soc., two-column
PowerPoint, etc.) — per plot type setting, user has reference
Jupyter notebook code to lift from. One USER-FLAGGED 🟢
friction note: `TestAppearanceSectionPhase4ae` class-name drift
(class still contains tick_direction tests even though the
widget no longer lives in Appearance). 1126 tests, all green
(1113 + 13 new in `TestPlotConfigDialogTickDirectionRelocation
Phase4aj`).*
*1.37: CS-62 — per-axis schema invention + axis_label_override
+ plots_by_role inventory added in Phase 4ak. Schema-invention
slice of the multi-phase per-axis settings ladder (Phase
4aj→4an); the CS-61 dirty-pin pattern from 4aj inverts to per-
axis Tk vars + per-role dirty marking. **Lock relaxations
taken:** (1) `_FACTORY_DEFAULTS` gains a nested `"axes"` sub-
dict (one entry per `_TAB_KEYS` axis role), each carrying
`tick_direction` + the new `axis_label_override` (CS-61 schema
invariant relaxed — top-level flat `tick_direction` REMOVED;
CS-23 / CS-60 lock 4 / `_USER_DEFAULTS` shape extended);
(2) `_UNIVERSAL_DEFAULTS` upgrades from `dict(...)` shallow
copy to `copy.deepcopy(...)` so the new mutable `axes` sub-
dict isolation holds; (3) `_KEY_TO_TAB`'s `tick_direction`
entry removed (canonical CS-61 relaxation; dict is now empty);
(4) `_build_axis_tab_settings(parent, role)` grows inline
(canonical CS-61 relaxation: two widget builders inline —
tick_direction Radiobutton row + axis_label_override Entry);
(5) `_DEFAULT_SECTIONS` extends to include `"axis_labels"` —
the new Global "Per-axis label overrides" mirror section;
(6) `open_plot_config_dialog` + `PlotConfigDialog.__init__`
gain `plots_by_role: dict[str, tuple[str, ...]] | None` kwarg.
**New module surface:** `migrate_plot_config(config)`
idempotent legacy-flat-to-nested shim; `_make_axis_string_var(role,
key)` idempotent per-axis-var factory; `_on_axis_var_write(role,
key, value)` per-axis writer routing dirty marking through
the role argument directly; `_build_section_axis_labels`
Global mirror section builder; `_build_axis_tab_plots` per-
axis Listbox renderer; `_axis_label_override(cfg, tab_role)` +
`_per_axis_tick_direction(cfg, tab_role)` renderer helpers in
`uvvis_tab.py`; `_enumerate_plots_by_role` module-level
enumerator + `UVVisTab._compute_plots_by_role` host method;
`_Y_AXIS_ROLE_TO_TAB` mapping from CS-44 Y-axis role keys to
dialog per-axis tab keys. **Renderer wiring:** `axis_label_override`
applied per axis for primary_x, primary_y, secondary_x,
secondary_y, tertiary_y. Per-axis tick_direction RENDERING
deferred to Phase 4al (the schema STORES per-axis values but
the renderer applies primary_x's value uniformly — the user-
surfaced "Secondary X tick changes Primary X axis" bug is
honest-but-incomplete and resolved in 4al). **Locks held:**
every CS-60 / CS-61 lock the canonical relaxations didn't
touch (`PlotConfigDialog` identity, `_TAB_KEYS` six-tuple +
order, `_TAB_TITLES`, `_MODIFIED_TAB_SUFFIX = " •"`, `AxisHit`
dataclass, `classify_axis_double_click` signature, hit-test
bands, button row order, Apply-to-All semantics); all CS-44 +
CS-46 + CS-49 + CS-50 + CS-55 + CS-56 + CS-57 + CS-58 + CS-59
invariants unchanged (project_io's `plot_defaults` manifest
key serialises the nested form transparently via `_jsonify` —
no schema code change in `project_io.py`). **Decision lock
taken (Phase 4ak):** (i) nested `_FACTORY_DEFAULTS["axes"][role][key]`
shape with `tick_direction` + `axis_label_override` for all
five roles; (ii) migration shim runs at dialog `__init__` on
working copy + Reset Defaults / Factory Reset paths;
(iii) `_KEY_TO_TAB` drops the entry entirely (cleaner than
generalising to `dict[tuple[str, str], str]`); (iv) per-axis
Tk vars stored separately from flat-key vars in
`_axis_control_vars[(role, key)]`; (v) Global mirror section
appended last in `_DEFAULT_SECTIONS`; (vi) per-axis tick
rendering deferred to Phase 4al — schema stores per-axis,
renderer applies primary_x uniformly with helper-based
fallback chain. **Five new USER-FLAGGED register entries
surfaced at step 5:** live-preview vs Apply button (meta-UX),
apply-to-all icon on per-axis tabs (UI consistency with
data-node settings), axis nomenclature rename to position-
based names (bottom/top/left/right with `*` suffix for
offset), rich-text axis labels (matplotlib mathtext
subscript/superscript/equations), plus the Secondary X tick
direction bug folded into the canonical per-axis ladder
register entry (resolution in 4al). Three Claude-surfaced 🟢
friction notes (dual-surface primary X/Y label, plots_by_role
frozen at open, Listbox disabled). One USER-FLAGGED 🟢
friction note carries forward unresolved from Phase 4aj
(`TestAppearanceSectionPhase4ae` class-name drift — two tests
inside got updated this phase, but the class name still
misleads). 1165 tests, all green (1126 + 39 new across
`TestPlotConfigDialogPerAxisSchemaPhase4ak`,
`TestEnumeratePlotsByRolePhase4ak`,
`TestUVVisTabPerAxisSchemaPhase4ak`, plus inversions in
`TestPlotConfigDialogTickDirectionRelocationPhase4aj`).*
*1.38: CS-63 — per-axis tick rendering + Move-to picker on
Y-axis tabs added in Phase 4al. Second slice of the per-axis
settings ladder; consumes the CS-62 schema slots invented in
Phase 4ak. **Lock relaxations taken:** (1) the CS-62 single
uniform `_per_axis_tick_direction(cfg, "primary_x")` read in
`uvvis_tab._redraw` splits into five per-axis-role reads at the
five tick_params call sites (primary x / primary y / secondary
twin / tertiary twin / wavelength-twin sibling); (2) the
previously-hardcoded `sec.tick_params(axis="x",
direction="in", labelsize=8)` for the wavelength↔energy
sibling axis now reads `direction=_per_axis_tick_direction(cfg,
"secondary_x")`; (3) the CS-62 Listbox `state="disabled"` lock
relaxes on the three Y-axis tabs to `state="normal"` so rows are
selectable (X-axis tabs keep `state="disabled"` — no picker
there); (4) `open_plot_config_dialog` + `PlotConfigDialog.__init__`
gain `on_route_plot: Callable[[str, str, Optional[str]], None]
| None` kwarg (additive). **New module surface:**
`_Y_AXIS_TAB_KEYS` frozenset; `_MOVE_TO_OPTIONS`/`_MOVE_TO_LABELS`/
`_MOVE_TO_VALUE_BY_LABEL` Combobox vocabularies;
`_build_move_to_picker(parent, role, listbox)` Combobox row
renderer; `PlotConfigDialog._on_move_to_choose(role, listbox,
var)` extracted from the closure so tests bypass the flaky
`<<ComboboxSelected>>` virtual-event dispatch in suite mode;
`UVVisTab._on_route_plot_from_dialog(source_tab_role, label,
target_tab_role)` host handler that walks visible plot nodes,
disambiguates label collisions by source role, and writes
`style["y_axis"]` via `graph.set_style`. **Renderer wiring:**
`primary_x` / `primary_y` reads at `ax.tick_params(axis="x"/"y")`;
`secondary_y` / `tertiary_y` reads at twin-creation time inside
`get_axis`; `secondary_x` read at the wavelength-sibling
`sec.tick_params` site. Resolves Phase 4ak USER-FLAGGED bug:
editing Secondary X tick direction no longer reroutes through
Primary X. **Locks held:** CS-62 `_AXIS_KEYS` =
`("tick_direction", "axis_label_override")` unchanged (Move-to
picker writes per-NODE `style["y_axis"]`, NOT per-axis-tab
schema); `_per_axis_tick_direction(cfg, tab_role)` signature
unchanged; `get_axis(role)` signature + lazy-creation order
unchanged; every CS-60 / CS-61 / CS-62 / CS-44 / CS-50
invariant the relaxations didn't touch. **Decision lock taken
(Phase 4al):** (i) Move-to picker UX = Combobox below Listbox
on Y-axis tabs only; auto-applies on choose; resets after
choose; (ii) tab-role-key namespace throughout the dialog —
host owns the translation to CS-50 style values; (iii) source
role disambiguates label collisions (first-match-wins, rare-
case documented); (iv) picker fires immediately, bypassing
the Plot Settings working-copy Cancel semantics — consistent
with CS-50 Style-dialog precedent; (v) bind trampoline +
extracted method instead of inline closure (testing
determinism). **Three new USER-FLAGGED register entries from
step 5:** accessibility features umbrella (open-ended;
keyboard shortcuts + colour-blind palette + Escape audit +
font scaling as first batch); modeless dialogs (drop
`grab_set` from Plot Settings to match CS-05 StyleDialog
modeless precedent); retire the global "Baseline curves"
top-bar checkbox (per-node CS-36 toggle in the data panel
has subsumed it). Four Claude-surfaced 🟢 polish notes
folded into existing register entries. Phase 4ak's "Secondary
X tick direction" user-flagged bug ✅ resolved; Phase 4ai
friction #1 "per-axis ladder continues" cross-referenced into
the new Phase 4al friction section. 1197 tests, all green
(1165 + 32 new across `TestPlotConfigDialogMoveToPickerPhase4al`,
`TestUVVisTabPerAxisTickRenderingPhase4al`,
`TestUVVisTabMoveToPickerPhase4al`, plus the rename of
`TestPlotConfigDialogPerAxisSchemaPhase4ak.test_plots_listbox_is_read_only`
→ `…_is_disabled_on_x_axis_tabs`).*
*1.40: CS-65 — per-axis tick spacing + per-axis grid + per-axis
axis colour added in Phase 4an. **Fifth and final canonical
slice** of the per-axis settings ladder (after CS-61 / CS-62 /
CS-63 / CS-64); the ladder is now complete. **Lock relaxations
taken:** (1) `_AXIS_KEYS` grew from the 6-tuple of CS-64 to a
10-tuple with `tick_major` / `tick_minor` / `grid_show` /
`axis_color`; (2) `_FACTORY_DEFAULTS["axes"][role]` carries the
four new keys per role with `grid_show` defaulting True for the
two primaries and False for the three non-primary roles; (3) the
Phase 4ah global `ax.grid(...)` call rewrote into a four-branch
shape honouring `_per_axis_grid` on `primary_x` and `primary_y`
independently while preserving the CS-28 `zorder=0` invariant on
every `visible=True` call. **New module surface:**
`matplotlib.ticker.MultipleLocator` import in `uvvis_tab.py`;
five new module-level helpers (`_parse_tick_str`,
`_per_axis_tick_major`, `_per_axis_tick_minor`, `_per_axis_grid`,
`_per_axis_color`); four new widget rows per per-axis tab in
`_build_section_axis_settings` (tick-spacing Entry pair, Show
gridlines Checkbutton, Axis colour swatch + `tkinter.colorchooser`
picker Button). **Renderer wiring:** per-axis polish block
applied at five call sites (primary X, primary Y, both twin Y
axes, secondary X wavelength sibling) after the Phase 4am scale
+ range block; tick locators via `MultipleLocator(value)` when
helper returns non-None; colour applied to per-role spine + tick
params + axis label; per-axis grid override applied to the
existing global grid call. **Bugfix surfaced by integration
tests:** matplotlib enables the grid when styling kwargs are
passed alongside `visible=False`; per-axis-disable branch now
calls `ax.grid(False, axis=...)` with no styling kwargs.
**Locks held:** every CS-62 / CS-63 / CS-64 invariant unchanged;
CS-28 `zorder=0` grid invariant preserved; CS-46 manifest
round-trip works without project_io edits (`_jsonify` already
handles the nested per-axis dict shape). **Decision lock taken
(Phase 4an):** (D1) four new keys with the canonical order
above; (D2) `grid_show` default split per role; (D3) widgets
on ALL FIVE per-axis tabs with hint label on non-primary tabs;
(D4) `tkinter.colorchooser.askcolor` stdlib choice; (D5) apply
order at every site is scale → range → tick spacing → grid →
colour (colour last so spine recreation doesn't reset it); (D6)
`_parse_tick_str` silently rejects non-positive / non-finite.
User had nothing to add at step 5. Five Claude-surfaced notes
documented in BACKLOG's "Friction points carried forward from
Phase 4an" section: matplotlib grid-styling override quirk
(fixed); `grid_show` schema-only on non-primaries (hint label in
place); `tick_minor` doesn't force minor ticks on (defer); 10-key
`_AXIS_KEYS` readability cliff (consider nested sub-dicts);
swatch is `tk.Frame` not ttk (cross-platform polish). 1279 tests,
all green (1236 + 43 new across
`TestPlotConfigDialogPerAxisPolishSchemaPhase4an`,
`TestUVVisTabPerAxisPolishHelpersPhase4an`,
`TestPlotConfigDialogPerAxisPolishWidgetsPhase4an`,
`TestUVVisTabPerAxisPolishPhase4an`, plus two pre-existing
test sweeps for the registry growth).*
*1.41: CS-66 + CS-67 — modeless Plot Settings + retire global
"Baseline curves" Checkbutton, Phase 4ao. **Dual-target small
phase** bundling two USER-FLAGGED carry-forwards. CS-66:
`PlotConfigDialog` drops `grab_set()` — main window stays
interactive while dialog is open; `transient(parent)` retained
for WM Z-order grouping; CS-06 one-per-host singleton unchanged;
CS-23 Apply/Save/Cancel + working-copy + `_snapshot` semantics
unchanged. CS-67: `_show_baseline_curves` BooleanVar + top-bar
Checkbutton + `_redraw` outer guard all retired — CS-36's
per-node `style["show_baseline_curve"]` (default True) is single
source of truth; default-flip means baseline overlays now render
by default. **Lock relaxations:** CS-06 modal contract relaxed
to modeless (CS-66); CS-29 global-gate invariant retired (CS-67).
**Locks held:** CS-06 singleton, CS-23 button-row + working-copy,
CS-36 default-True per-node, CS-28 zorder=0 grid, CS-46 manifest
schema, CS-60 cross-tab pending-edit state model + Notebook tab
shape, CS-61 / CS-62 / CS-63 / CS-64 / CS-65 per-axis ladder
invariants. **Decision lock taken (Phase 4ao):** (DM1) scope
Plot Settings only — other CS-23 acknowledgement modals stay
modal; (DM2) `transient(parent)` retained; (DM3) `_plots_by_role`
remains frozen at open time per CS-62; (DM4) Cancel semantics
preserved. (DR1) Default flip accepted — overlays render by
default; (DR2) tests rename/replace in place; (DR3) manifest
untouched; (DR4) CS-29 historical text preserved, CS-67 is
canonical retirement note. User had nothing to add at step 5.
Five Claude-surfaced notes documented in BACKLOG's "Friction
points carried forward from Phase 4ao" section: (σ) modeless
+ per-row baseline-toggle integration surface uncovered (folds
into live-preview); (τ) `_plots_by_role` staleness more
reachable now; (υ) `grab_status()` build-variation gotcha;
(φ) scan_tree_widget.py:822 stale comment reference; (χ)
default-flip first-reload manual smoke check on legacy projects.
1285 tests, all green (1279 + 6 net new across
`TestPlotConfigDialogModelessPhase4ao` ×4, the inverted/added
`TestPlotConfigDialogShell` ×2, the two new + one renamed
tests inside `TestUVVisTabBaselineCurveOverlay`, with three
redundant `set(True)` setup lines pruned).*
*To be updated as Open Questions are resolved and new components
are specified.*
