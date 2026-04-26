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

### Reactivity

The graph uses an observer pattern. UI components subscribe to graph
events. When a node is added, committed, or discarded, the graph
notifies all subscribers. This eliminates the need for "Refresh"
buttons anywhere in the UI.

GraphEvent types:
- NODE\_ADDED(node\_id)
- NODE\_COMMITTED(node\_id)
- NODE\_DISCARDED(node\_id)
- NODE\_LABEL\_CHANGED(node\_id, new\_label)
- GRAPH\_LOADED
- GRAPH\_CLEARED

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
    created_at: datetime = field(default_factory=datetime.utcnow)
    active: bool = True              # False = hidden from default views
    style: dict = field(            # display style; not scientific data
        default_factory=dict)
```

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
    BASELINE      = auto()
    AVERAGE       = auto()
    DIFFERENCE    = auto()
    FEFF_RUN      = auto()
    BXAS_FIT      = auto()
    # Add further types as new operations are implemented

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
    timestamp: datetime = field(default_factory=datetime.utcnow)
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

Each parameter row has a ∀ button (rightmost) that applies that
parameter to all visible nodes of the same type in the current tab.
This carries forward the existing UV/Vis \_push\_to\_all pattern.

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

---

*Document version: 1.0 — April 2026*
*To be updated as Open Questions are resolved and new components
are specified.*
