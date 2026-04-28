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

```
Processing
  Baseline:  [combobox: none/linear/poly/spline/rubberband]
  Order n:   [spinbox]  (shown for poly)
  [Apply Baseline]
─────────────────────────────
  Normalisation: already in top bar combobox
─────────────────────────────
  [Apply Smoothing…]
  [Shift Energy…]
  [Difference Spectra…]
```

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
[ Apply ]  [ Cancel ]
```

- **Apply** — copy the working copy into the caller's config dict
  (in place), invoke `on_apply`, dialog stays open for further edits
- **Cancel** — revert config to the snapshot taken at `__init__`,
  invoke `on_apply` if anything had to be reverted, destroy

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

*Document version: 1.5 — April 2026*
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
*To be updated as Open Questions are resolved and new components
are specified.*
