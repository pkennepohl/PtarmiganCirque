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

### Four modes (single OperationType, params discriminated by mode)

A single `OperationType.BASELINE` covers all four. The
discriminator is `params["mode"]`; the remaining keys are the
mode-specific sub-schema.

| Mode | Required `params` keys | Algorithm |
|---|---|---|
| `linear`     | `anchor_lo_nm`, `anchor_hi_nm`              | Two-point baseline through the absorbance values at the two anchor wavelengths (linearly interpolated from neighbouring data points). |
| `polynomial` | `order` (int), `fit_lo_nm`, `fit_hi_nm`     | Polynomial of given order fit (`np.polyfit`) to the data inside the wavelength window; evaluated across the full input range. |
| `spline`     | `anchors` (list of nm)                      | Cubic interpolating spline (`scipy.interpolate.CubicSpline`) through `(anchor, sampled_absorbance)` points. Falls back to quadratic / linear when `len(anchors) < 4`. |
| `rubberband` | (none)                                       | Lower convex hull (Andrew's monotone chain) of the `(wavelength, absorbance)` point set, linearly interpolated onto the input grid. |

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
  `spline` / `rubberband`. On change, the parameter row frame
  rebuilds.
* **Conditional parameter rows** —
  * linear: two anchor entries (nm).
  * polynomial: order spinbox + two fit-window entries (nm).
  * spline: comma-separated anchor entry (nm).
  * rubberband: a single "(parameter-free convex hull)" label.
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
  not the most recent `pack` / `pack_forget`.

---

*Document version: 1.12 — May 2026*
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
*To be updated as Open Questions are resolved and new components
are specified.*
