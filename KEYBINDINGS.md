# Keyboard shortcuts

Registered-shortcut table for SpecTRACE. The source of truth at
runtime is `accessibility.SHORTCUT_REGISTRY`, populated by every
`accessibility.bind_shortcut(...)` call at widget construction
time. This document mirrors that registry and is updated in the
bookkeeping commit of every Phase 4 sub-batch that adds keyboard
gestures (CS-75 sub-axis C, introduced Phase 4az).

Discoverability path:

* In-app — the **Plot Settings → Accessibility** tab's "Keyboard
  shortcuts" LabelFrame renders the same table at runtime
  (CS-75 D1 + D6, Phase 4az).
* Per-widget hover — shortcut-bearing widgets (buttons,
  comboboxes) wire `accessibility.attach_shortcut_tooltip` so a
  hover hint also surfaces the binding (CS-75 D6, Phase 4ax
  `NodeStylesDialog` precedent). Container widgets without a
  natural hover surface (tree-level shortcuts in
  `ScanTreeWidget`) rely on the Accessibility-tab table only.

## Scan tree

| Key            | Action                              | Component lock |
| -------------- | ----------------------------------- | -------------- |
| F2             | Rename selected node                | CS-78 (Phase 4az), routes through CS-33 `_begin_label_edit` via `_begin_rename_via_menu` |
| Delete         | Discard selected provisional nodes  | CS-78 (Phase 4az), graph.discard_node — commit-or-discard discipline (committed nodes skipped) |
| Ctrl+G         | Group selected nodes                | CS-78 (Phase 4az), routes through CS-57 `_group_selected` |
| Ctrl+Shift+G   | Ungroup selected group              | CS-78 (Phase 4az), graph.dissolve_group (CS-58) |

### Selection model

`ScanTreeWidget._selected_node_ids` is the read by every gesture.
Click a row to toggle its membership; the widget calls
`self.focus_set()` after each toggle so the next keystroke reaches
the registered bindings (Frames do not accept focus by default —
`takefocus=1` + the post-toggle focus call together make the
shortcuts reachable from the keyboard).

Each handler is selection-shape strict: F2 fires only on a single
selection; Ctrl+Shift+G fires only when the single selected node
is a `NODE_GROUP`; Delete operates on every provisional DataNode
in the selection and clears the selection on completion.

---

*Document version: 1.0 — Phase 4az (May 2026)*
