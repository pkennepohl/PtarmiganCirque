# Ptarmigan — Architecture Document

> **Status:** Authoritative. Do not re-litigate decisions recorded here
> within a Code session. If a decision needs revisiting, do so in a
> Design session first and update this document before implementing.

---

## 1. Application Identity

Ptarmigan is a **computational spectroscopy workbench** for inorganic and
physical chemistry. Its core value proposition is:

> A scientist can go from raw beamline or instrument data to a
> publication-quality comparison figure — with full provenance — without
> leaving the application.

It brokers between external computational engines (Larch, FEFF, bXAS) and
a unified comparison and presentation surface. It does not duplicate what
those engines do; it manages data flow into and out of them, and provides
the presentation layer that none of them supply.

---

## 2. Tab Structure

Five tabs. This list is definitive.

| Tab | Role | Primary engine(s) |
|---|---|---|
| **XANES** | Load and process X-ray absorption near-edge data | Larch (inline) · bXAS (workspace window) |
| **EXAFS** | Extract and display extended fine structure | Larch (inline) |
| **UV/Vis** | Load and process UV/Visible/NIR spectra | Internal only |
| **Simulate** | Set up and run ab initio simulations | FEFF (workspace window) |
| **Compare** | Overlay any combination of datasets for interpretation and figure generation | Internal only |

**What is not a tab:**
- TDDFT is not a tab. TDDFT calculation files are a type of calculated
  data that loads into the Compare tab.
- BlueprintXAS (bXAS) is not a tab. It is an engine option selectable
  within the XANES tab (and potentially UV/Vis in future).
- FEFF fitting/inspection is not embedded in the EXAFS tab. It is a
  dedicated workspace window launched from the Simulate tab.

---

## 3. Layout Grammar

Every tab follows the same three-zone layout. This rule has no exceptions.

```
┌─────────────────────────────────────────────────────────────────┐
│  TOP BAR  — plot-level controls + primary action                │
├──────────────────┬──────────────────────────┬───────────────────┤
│                  │                          │                   │
│   LEFT PANEL     │       CENTRE             │   RIGHT SIDEBAR   │
│                  │       (matplotlib        │                   │
│  Engine selector │        figure)           │  ScanTreeWidget   │
│  +               │                          │                   │
│  Engine params   │                          │  (all datasets    │
│                  │                          │   for this tab)   │
│  [absent on      │                          │                   │
│   Compare tab]   │                          │                   │
│                  │                          │                   │
├──────────────────┴──────────────────────────┴───────────────────┤
│  BOTTOM  — log / provenance explorer (collapsible)              │
├─────────────────────────────────────────────────────────────────┤
│  STATUS BAR — last operation · project status · autosave        │
└─────────────────────────────────────────────────────────────────┘
```

**Top bar** holds only:
- Axis units and limits (where applicable)
- Y-axis quantity selector (where applicable)
- Primary action button (Run / Fit / Send to Compare)
- Normalisation mode (where applicable)
- Export / Pop Out / Save Figure actions

Everything else (fonts, grid, background colour, legend position,
tick direction, title/label text) belongs in a **Plot Settings dialog**
accessible from the top bar via a single ⚙ button.

**Left panel** holds:
- Engine selector (radio buttons: e.g. Larch / bXAS)
- Engine-specific parameter controls (conditional on engine selection)
- Run / Fit button at the bottom of the parameter section
- Absent entirely on the Compare tab (no engine, no parameters)

**Right sidebar** is always the ScanTreeWidget (see Section 6).

**Bottom panel** is the provenance log explorer, collapsible to a single
status line.

---

## 4. Core Data Model — The Provenance DAG

The fundamental architectural commitment of Ptarmigan is that **all data
is stored as a directed acyclic graph (DAG) of immutable nodes**. This is
the non-negotiable foundation on which every other feature is built.

### 4.1 Node types

**DataNode** — represents a dataset at a specific point in its processing
history:

```python
@dataclass
class DataNode:
    id: str                  # unique, permanent, never reused
    type: NodeType           # RAW_FILE | XANES | EXAFS | UVVIS |
                             # FEFF_PATHS | BXAS_RESULT | TDDFT |
                             # AVERAGED | DIFFERENCE | ...
    arrays: dict             # the actual data arrays
    metadata: dict           # technique-specific metadata
    label: str               # user-editable display name
    created_at: datetime
    state: NodeState         # PROVISIONAL | COMMITTED | DISCARDED
    active: bool             # False = hidden from default views
```

**OperationNode** — represents a processing step that produced one or
more DataNodes from one or more parent DataNodes:

```python
@dataclass
class OperationNode:
    id: str
    type: OperationType      # LOAD | DEGLITCH | NORMALISE | AVERAGE |
                             # DIFFERENCE | SMOOTH | SHIFT_ENERGY |
                             # FEFF_RUN | BXAS_FIT | BASELINE | ...
    engine: str              # "internal" | "larch" | "feff" | "bxas"
    engine_version: str      # exact version string
    params: dict             # complete parameter snapshot at time of run
    input_ids: list[str]     # parent DataNode ids
    output_ids: list[str]    # child DataNode ids produced
    timestamp: datetime
    duration_ms: int
    status: str              # SUCCESS | FAILED | PARTIAL
    log: str                 # engine output, warnings, errors
    state: NodeState         # PROVISIONAL | COMMITTED | DISCARDED
```

### 4.2 The graph

```python
class ProjectGraph:
    nodes: dict[str, DataNode | OperationNode]
    edges: list[tuple[str, str]]   # (parent_id, child_id)
    # ... query, traversal, and persistence methods
```

The graph is the project. Everything else in the application is a view
of, or an operation on, the graph.

### 4.3 Immutability rule

Once a node's state is set to COMMITTED, its arrays, metadata, and
operation parameters are never modified. Operations do not modify data;
they produce new nodes. This rule has no exceptions.

---

## 5. Provisional / Committed / Discarded Model

Every result produced by any operation starts as PROVISIONAL and stays
that way until the user explicitly commits it.

### 5.1 State definitions

| State | Meaning | In sidebar | In log |
|---|---|---|---|
| **PROVISIONAL** | Being explored; not yet locked | Italic label, dashed swatch border | Not written |
| **COMMITTED** | Permanent; part of the scientific record | Normal label, solid swatch | Written to log.jsonl |
| **DISCARDED** | Explicitly abandoned | Hidden by default | Not written |

### 5.2 The five verbs

These are the only operations that change node state. They are the
user's complete interaction vocabulary with the provenance system:

| Verb | Gesture | Effect |
|---|---|---|
| **Explore** | Adjust parameters, click Run | Creates PROVISIONAL operation + output nodes |
| **Commit** | Click lock icon / Ctrl+Return | Promotes PROVISIONAL → COMMITTED; writes to log |
| **Discard** | Click ✕ on provisional / Escape | Promotes PROVISIONAL → DISCARDED; removed from view |
| **Send** | "Send to Compare" button / Ctrl+Shift+C | Makes COMMITTED node available in Compare tab |
| **Compare** | Node appears in Compare right sidebar | Node is rendered on Compare figure |

### 5.3 Raw data is always the first committed node

Loading a file always produces exactly one COMMITTED DataNode of type
RAW_FILE. This node is the immutable anchor of every provenance chain.
No analysis runs automatically on load. The user initiates the first
operation explicitly.

### 5.4 Parameter sweeps

Running an operation across a parameter range (e.g. ten E0 values)
produces a **sweep group**: a set of PROVISIONAL output nodes sharing
a common parent, displayed in the sidebar as a single collapsed row with
a summary indicator. The user inspects, selects keeper(s), commits
those, and discards the rest. Only committed nodes enter the log.

---

## 6. ScanTreeWidget

The right sidebar component. Appears on every tab. Same widget,
contents vary by tab context.

### 6.1 Default appearance (flat)

Displays only the currently active node for each loaded dataset — one
row per "thing the user is working with." Derivation history is not
visible by default.

Each row contains (left to right):
- State indicator (lock icon = committed; dashed = provisional)
- Colour swatch (click → colour picker)
- Visibility checkbox
- Label (editable in-place on double-click)
- Legend toggle (✓ / –)
- Linestyle canvas (click to cycle)
- History indicator (small branch icon + count; click to expand)
- ⚙ (open unified style dialog for this node)
- ✕ (discard this node)

### 6.2 History expansion

Clicking the history indicator expands the row inline to show the
provenance chain for that dataset:

```
[●] scan1 TEY normalised  ──────────────── [⚙][⌥3][✕]
    ↳ normalise [larch 0.9.80] at 14:35 · E0=2470.3 ...
    ↳ deglitch [internal] at 14:32 · interp at 2471.3
    ↳ source: scan1.dat [sha256: abc123]
```

Each history entry is clickable — clicking navigates to that node
and displays it on the plot.

### 6.3 Sweep group appearance

```
[~] scan1 TEY · E0 sweep (10 variants)  ──── [compare][✕]
    best: E0 = 2470.3  (χ² = 0.0023)
```

Expanding shows all variants ranked by fit metric. The user selects
keeper(s) and uses commit/discard actions to resolve the sweep.

### 6.4 Tab-specific contents

| Tab | ScanTreeWidget shows |
|---|---|
| XANES | All XANES DataNodes (RAW_FILE and derived) |
| EXAFS | All EXAFS DataNodes |
| UV/Vis | All UV/Vis DataNodes |
| Simulate | FEFF session results available for Compare |
| Compare | All COMMITTED nodes sent to Compare, any type |

The Compare tab sidebar is heterogeneous — it lists TDDFT calculated
data, FEFF results, bXAS fit results, and experimental datasets from
any technique, grouped by type.

### 6.5 Reference implementation

The existing UV/Vis sidebar in uvvis_tab.py is the reference
implementation for the ScanTreeWidget row. Its per-row controls
(colour swatch, visibility, legend toggle, linestyle canvas, linewidth
entry, fill checkbox, ⚙, ✕) are carried forward directly. The
ScanTreeWidget adds: state indicator, history indicator, in-place
label editing, sweep group representation.

---

## 7. Unified Style Dialog

One dialog, called from the ⚙ button on any ScanTreeWidget row,
regardless of tab or dataset type.

- **Modeless** — stays open while the plot updates live
- **Conditional sections** — sections shown depend on the type of the
  selected node
- **∀ buttons** — each parameter row has a per-parameter apply-to-all
  button, following the existing UV/Vis style dialog pattern
- **Bottom buttons:** Apply · ∀ Apply to All · Save · Cancel

Conditional sections by node type:

| Section | Shown for |
|---|---|
| Line style / width / opacity / colour / fill | All types |
| Markers (shape, size) | XANES, EXAFS scan types |
| Broadening (Gaussian/Lorentzian, FWHM) | TDDFT, bXAS calculated types |
| Energy shift (ΔE) and scale factor | TDDFT, bXAS, FEFF types |
| Envelope display (line width, fill, opacity) | TDDFT, bXAS types |
| Stick display (width, opacity, tip markers) | TDDFT types |
| Uncertainty band (colour, opacity) | bXAS result types |
| Component visibility (D², m², Q²) | TDDFT types |

---

## 8. Engine Model

Engines are selectable within tabs, not separate tabs. Engine selection
lives in the left panel.

### 8.1 Inline engines

Run within the main window. Results appear in the centre plot. Fast
enough for interactive use.

| Engine | Tab | Type |
|---|---|---|
| Larch | XANES, EXAFS | External library (in-process) |
| Internal | UV/Vis | Pure Python, in-process |

### 8.2 Workspace-window engines

Too complex for the left panel. Launched as a dedicated non-blocking
window. The main window and workspace window communicate through the
shared ProjectGraph.

| Engine | Launched from | Window type |
|---|---|---|
| bXAS | XANES tab (engine selector) | bXAS Workspace |
| FEFF | Simulate tab | FEFF Workspace |

The main window shows a thin session manager for workspace engines:
- Active sessions list (name, dataset, status, fit quality)
- ↗ Open [Engine] Workspace button
- Last result summary (if committed result exists)
- Send to Compare button

### 8.3 Engine parameter display

When an inline engine is selected, its parameters appear in the left
panel below the engine selector. The parameter panel is conditional:
switching engine replaces the parameter section entirely.

When a workspace engine is selected, the left panel shows the session
manager (above) rather than a parameter panel.

---

## 9. Project File Format

A project is a directory, not a single file. The directory is named
`projectname.ptproj/` and can be zipped for sharing.

```
projectname.ptproj/
├── project.json          # project metadata, graph index, app state
├── graph/
│   ├── committed/        # immutable committed nodes (never modified)
│   │   ├── ds_001.json   # DataNode metadata
│   │   ├── ds_001.npz    # DataNode arrays (numpy format)
│   │   ├── op_001.json   # OperationNode record
│   │   └── ...
│   └── provisional/      # ephemeral; cleared or offered for recovery
│       └── ...
├── raw/                  # copies of all original input files
│   ├── scan1.dat         # copied at load time
│   └── cumnt.out
├── sessions/             # dedicated workspace window session states
│   ├── feff_001/
│   └── bxas_001/
└── log.jsonl             # append-only; committed operations only
```

**Key properties:**
- Raw input files are copied into the project at load time. The project
  is self-contained — no dependency on original file paths.
- Each raw file is stored with its SHA-256 hash for integrity
  verification.
- log.jsonl is append-only. It records only committed operations.
  Provisional exploration does not appear in the log.
- Provisional nodes in graph/provisional/ are offered for recovery on
  next open (like crash recovery in a word processor). User chooses to
  restore or discard.
- The committed/ directory is never modified after a node is written.

---

## 10. Provenance Log Panel

A collapsible panel at the bottom of the main window, above the status
bar. Always accessible regardless of active tab.

**Collapsed state:** single line showing the last committed operation.

**Expanded state:** scrollable list of committed operations across all
datasets, filterable by dataset, operation type, engine, and time range.
Each entry is clickable — clicking navigates to the corresponding node
in the active tab's ScanTreeWidget.

**What appears in the log:** only COMMITTED operations.

**What does not appear:** provisional exploration, discarded branches,
parameter adjustments that were not committed.

---

## 11. Cross-Tab Actions

### Send to Compare

The primary cross-tab action. Available from:
- Any ScanTreeWidget row (right-click context menu)
- Keyboard shortcut: Ctrl+Shift+C
- "Send to Compare" button in the top bar of each analysis tab

Only COMMITTED nodes can be sent to Compare. Attempting to send a
provisional node prompts commit-first.

### Commit

- Lock icon on ScanTreeWidget row
- Keyboard shortcut: Ctrl+Return
- Right-click context menu on any provisional node

### Discard

- ✕ button on ScanTreeWidget row (provisional nodes only)
- Keyboard shortcut: Escape (when provisional node is selected)
- Right-click context menu

---

## 12. Dedicated Workspace Windows

### Properties common to both

- **Non-blocking** — the main window remains fully interactive while
  a workspace window is open.
- **Non-modal** — the user can switch between main window and workspace
  window freely.
- **Persistent** — workspace windows survive tab switches in the main
  window. Closing a workspace window suspends (does not destroy) the
  session.
- **Communicate via ProjectGraph** — workspace windows read and write
  to the shared graph. Results committed in a workspace window
  immediately appear as available nodes in the main window.

### FEFF Workspace

Launched from: Simulate tab.
Contains: structure input, XYZ/CIF loader, FEFF parameter configuration,
path treeview with per-path controls and amplitude preview, FEFF
execution log, path selection and grouping tools, model comparison view.

### bXAS Workspace

Launched from: XANES tab (when bXAS engine selected).
Contains: background model builder, spectral model composer, fit
execution, residuals panel, correlation matrix display, parameter table
with uncertainties, parameter evolution across a scan series, model
comparison view, uncertainty band visualisation.

---

## 13. Reproducibility

### Reproducibility report

Accessible via File menu → Export Reproducibility Report.
Generates a human-readable methods-section-style summary of every
committed operation applied to every dataset currently visible in the
Compare tab. Intended for inclusion in publications or supplementary
materials.

### Project archive

Accessible via File menu → Export Project Archive.
Produces a zip of the .ptproj/ directory. Contains all raw input files,
all committed nodes, all session states, and the audit log. A recipient
with Ptarmigan can reproduce every result from scratch.

---

## 14. Design Decisions

These record non-obvious choices and the alternatives that were
considered and rejected. New Code sessions should read this section
before proposing changes to fundamental behaviour.

---

**Decision: Five tabs, not four or six**

TDDFT is not a tab — it is a dataset type that loads into Compare.
BlueprintXAS is not a tab — it is an engine option within XANES.
FEFF is not embedded in EXAFS — it has a dedicated Simulate tab
and workspace window.

*Rejected: tab-per-engine model.* Organising by tool rather than by
data type and scientific question is a less intuitive structure for
users who think "I have a XANES dataset" not "I want to use Larch."

---

**Decision: Raw file load always produces a COMMITTED node**

The raw DataNode is the immutable anchor of every provenance chain.
No processing runs automatically on load. The user initiates every
operation explicitly.

*Rejected: auto-run on load.* Auto-running produces results without
user intent, blurs the provisional/committed boundary, and makes the
provenance chain ambiguous about what was deliberate.

---

**Decision: Provisional nodes never appear in log.jsonl**

The audit log records only the committed scientific record. Exploratory
work that is discarded is not logged.

*Rejected: log everything including provisional.* Makes the log noisy
and harder to use as a methods record. The graph/provisional/ directory
preserves session state for recovery purposes.

---

**Decision: ScanTreeWidget is flat by default**

The default view shows only the currently active node per dataset.
The provenance tree is accessible via the history indicator but not
shown by default.

*Rejected: always-visible tree.* For users working with 5–10 datasets,
a fully expanded tree creates visual noise that obscures the current
working state. Progressive disclosure is more appropriate.

---

**Decision: Workspace windows for complex engines (FEFF, bXAS)**

Engines with multi-step iterative workflows (model building, comparison,
statistics inspection) use dedicated non-blocking windows rather than
left-panel parameter sections.

*Rejected: embedding complex engine UI in the left panel.* The FEFF
and bXAS workflows require simultaneous visibility of multiple plot
panels, model comparison, and statistical outputs that cannot be
accommodated in a sidebar panel.

---

**Decision: Internal storage as absorbance + nm (UV/Vis)**

Carried forward from existing implementation. UVVisScan stores
wavelength_nm and absorbance internally; all other representations
(%T, cm⁻¹, eV) are computed properties.

---

**Decision: Sticky axis limits stored as StringVar entries**

Carried forward from existing implementation. Empty string = auto.
Unit conversion normalises through nm. This implementation detail
is correct and should not be changed without specific reason.

---

## 15. Open Questions

These require resolution before implementation of the affected
component. Do not implement workarounds — bring these back to a
design session.

---

**OQ-001: Link groups**

The TDDFT tab (plot_widget.py) contains a "link groups" feature for
experimental scans. Its purpose and implementation are not documented.

*Action for Code session:* Read the link groups implementation in
plot_widget.py. Determine: (a) what it does, (b) whether it is used,
(c) whether the new architecture solves the same problem natively,
(d) whether it should be carried forward into the Compare tab.
Report findings before implementing anything.

---

**OQ-002: bXAS uncertainty bands in Compare**

bXAS fits produce uncertainty bands (shaded regions). The Compare tab
style system needs to support rendering them. The exact representation
(how bands are stored in the DataNode, how they are styled) is not yet
specified.

*Action:* Design the uncertainty band DataNode schema and style dialog
section before implementing the bXAS engine or the Compare tab
uncertainty display.

---

**OQ-003: bXAS compound result grouping**

A bXAS fit result is a compound object: fitted model curve +
uncertainty band + residuals. How this is represented in the
ScanTreeWidget (one row? three rows? expandable group?) and how
the component parts are individually styled needs explicit design
before implementation.

---

**OQ-004: Multi-input operation nodes in UI**

Some operations take multiple input DataNodes (Average, Difference,
OLIS integrating sphere correction). The UI gesture for constructing
a multi-input operation — selecting which nodes are inputs before
running — is not yet designed.

---

**OQ-005: "Replace-or-Add" for TDDFT files**

The existing binah.py has a dialog that asks whether a newly loaded
ORCA file should replace the existing TDDFT data or be added as an
overlay. In the new architecture, TDDFT files always load as new
DataNodes in the Compare tab graph. Whether a "replace" concept still
makes sense needs a decision.

---

*Document version: 1.0 — April 2026*
*Supersedes: the About and Design Decisions sections of BACKLOG.md*
