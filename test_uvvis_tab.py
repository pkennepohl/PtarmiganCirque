"""Tests for uvvis_tab.py.

Mirrors the structure of ``test_scan_tree_widget.py`` and
``test_style_dialog.py``: construct a real ``tk.Tk`` root and a real
``ProjectGraph``, then drive the tab and observe the resulting graph
state. Headless environments where ``tk.Tk()`` cannot be constructed
are skipped via ``unittest.skipUnless``.

Phase 4a (Part A) coverage:

* loading a fixture file produces the expected node structure
  (1 LOAD op, 1 RAW_FILE, 1 UVVIS, edges wired)
* default colour from the loader palette is set on the UVVIS node
* ``_redraw`` no longer references ``_entries`` and walks the graph

Run with the project venv:

    venv/Scripts/python run_tests.py
"""

from __future__ import annotations

import os
import tempfile
import textwrap
import unittest

import numpy as np

# Try to construct a Tk root once at module import time. If it fails
# (no display, missing tcl/tk), every test in the file is skipped.
try:
    import tkinter as tk
    _root = tk.Tk()
    _root.withdraw()
    _HAS_DISPLAY = True
except Exception:  # pragma: no cover — only hit on headless CI
    _root = None
    _HAS_DISPLAY = False


from graph import ProjectGraph
from nodes import DataNode, NodeState, NodeType, OperationNode, OperationType


# ---- helpers --------------------------------------------------------

def _write_csv_fixture(path: str) -> None:
    """Write a tiny generic two-column UV/Vis CSV (nm, absorbance)."""
    rows = ["# generic UV/Vis fixture"]
    for nm, a in [(200.0, 0.10), (300.0, 0.45),
                  (400.0, 0.70), (500.0, 0.30),
                  (600.0, 0.05)]:
        rows.append(f"{nm},{a}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(rows))


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabLoaderMigration(unittest.TestCase):
    """Phase 4a Part A — loader builds the right graph structure."""

    @classmethod
    def setUpClass(cls):
        # CS-21 (Phase 4j) lifted the palette into node_styles. The
        # tab still produces colours from the same ten-entry tuple
        # via node_styles.pick_default_color; existing assertions
        # against ``cls._PALETTE`` keep working transparently.
        from uvvis_tab import UVVisTab
        from node_styles import SPECTRUM_PALETTE
        cls.UVVisTab = UVVisTab
        cls._PALETTE = SPECTRUM_PALETTE

    def setUp(self):
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)
        self._tmpdir = tempfile.mkdtemp(prefix="uvvis_tab_test_")

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass
        # Best-effort cleanup of the fixture file(s).
        for name in os.listdir(self._tmpdir):
            try:
                os.remove(os.path.join(self._tmpdir, name))
            except OSError:
                pass
        try:
            os.rmdir(self._tmpdir)
        except OSError:
            pass

    # ----------- construction -----------

    def test_constructs_with_external_graph(self):
        # The tab honours the graph argument and routes through it.
        self.assertIs(self.tab._graph, self.graph)
        # No UVVIS nodes yet.
        self.assertEqual(
            self.graph.nodes_of_type(NodeType.UVVIS, state=None), [],
        )

    def test_constructs_with_default_graph(self):
        # When no graph is given the tab fabricates its own; the tab
        # still works end-to-end without binah.py integration.
        host = tk.Frame(_root)
        try:
            tab = self.UVVisTab(host)
            self.assertIsInstance(tab._graph, ProjectGraph)
        finally:
            host.destroy()

    def test_no_entries_attribute(self):
        # Phase 4a Part A drops self._entries entirely.
        self.assertFalse(hasattr(self.tab, "_entries"))

    # ----------- loader produces the right graph structure -----------

    def test_load_creates_raw_load_uvvis_with_edges(self):
        path = os.path.join(self._tmpdir, "fixture.csv")
        _write_csv_fixture(path)

        from uvvis_parser import parse_uvvis_file
        scans = parse_uvvis_file(path)
        self.assertEqual(len(scans), 1, "fixture should parse to 1 scan")

        raw_id, op_id, uvvis_id = self.tab._load_uvvis_scan(path, scans[0])

        # Node identities and types.
        raw   = self.graph.get_node(raw_id)
        op    = self.graph.get_node(op_id)
        uvvis = self.graph.get_node(uvvis_id)

        self.assertIsInstance(raw, DataNode)
        self.assertEqual(raw.type, NodeType.RAW_FILE)
        self.assertEqual(raw.state, NodeState.COMMITTED)

        self.assertIsInstance(op, OperationNode)
        self.assertEqual(op.type, OperationType.LOAD)
        self.assertEqual(op.engine, "internal")
        self.assertEqual(op.input_ids, [raw_id])
        self.assertEqual(op.output_ids, [uvvis_id])
        self.assertEqual(op.state, NodeState.COMMITTED)

        self.assertIsInstance(uvvis, DataNode)
        self.assertEqual(uvvis.type, NodeType.UVVIS)
        self.assertEqual(uvvis.state, NodeState.COMMITTED)
        self.assertIn("wavelength_nm", uvvis.arrays)
        self.assertIn("absorbance",    uvvis.arrays)
        self.assertEqual(
            uvvis.arrays["wavelength_nm"].shape,
            uvvis.arrays["absorbance"].shape,
        )

        # Edges wired raw → op → uvvis.
        self.assertIn(op_id,    self.graph.children_of(raw_id))
        self.assertIn(uvvis_id, self.graph.children_of(op_id))
        self.assertEqual(self.graph.parents_of(uvvis_id), [op_id])
        self.assertEqual(self.graph.parents_of(op_id),    [raw_id])

    def test_uvvis_metadata_follows_cs02_conventions(self):
        path = os.path.join(self._tmpdir, "meta.csv")
        _write_csv_fixture(path)
        from uvvis_parser import parse_uvvis_file
        scan = parse_uvvis_file(path)[0]

        _, _, uvvis_id = self.tab._load_uvvis_scan(path, scan)
        uvvis = self.graph.get_node(uvvis_id)

        # CS-02 UVVIS metadata convention: x_unit, y_unit, instrument.
        self.assertEqual(uvvis.metadata.get("x_unit"),  "nm")
        self.assertEqual(uvvis.metadata.get("y_unit"),  "absorbance")
        self.assertIn("instrument", uvvis.metadata)
        self.assertEqual(uvvis.metadata.get("source_file"), path)

    # ----------- default colour at node creation -----------

    def test_default_colour_assigned_from_palette(self):
        path = os.path.join(self._tmpdir, "color.csv")
        _write_csv_fixture(path)
        from uvvis_parser import parse_uvvis_file
        scan = parse_uvvis_file(path)[0]

        _, _, uvvis_id = self.tab._load_uvvis_scan(path, scan)
        node = self.graph.get_node(uvvis_id)
        self.assertEqual(node.style.get("color"), self._PALETTE[0])

    def test_default_colour_cycles_through_palette(self):
        from uvvis_parser import parse_uvvis_file
        ids: list[str] = []
        for i in range(len(self._PALETTE) + 2):
            path = os.path.join(self._tmpdir, f"row{i}.csv")
            _write_csv_fixture(path)
            scan = parse_uvvis_file(path)[0]
            scan.label = f"row{i}"  # avoid duplicate-detection
            _, _, uvvis_id = self.tab._load_uvvis_scan(path, scan)
            ids.append(uvvis_id)

        # Index N wraps modulo the palette length.
        for i, nid in enumerate(ids):
            self.assertEqual(
                self.graph.get_node(nid).style["color"],
                self._PALETTE[i % len(self._PALETTE)],
                f"node #{i} should pick palette[{i % len(self._PALETTE)}]",
            )

    # ----------- _redraw walks the graph (not _entries) -----------

    def test_redraw_walks_graph(self):
        # Inject a UVVIS node directly so we can verify _redraw uses
        # it without going through the loader path.
        wl = np.linspace(300, 600, 50)
        absorb = np.exp(-((wl - 450) ** 2) / 50.0)
        node = DataNode(
            id="manual",
            type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"x_unit": "nm", "y_unit": "absorbance",
                      "instrument": "manual",
                      "source_file": "synthetic"},
            label="manual",
            state=NodeState.COMMITTED,
            style={"color": "#123456", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        )
        self.graph.add_node(node)
        # _redraw does not raise; the figure ends up with one Line2D.
        self.tab._redraw()
        ax = self.tab._ax
        self.assertEqual(len(ax.get_lines()), 1)
        line = ax.get_lines()[0]
        self.assertEqual(line.get_label(), "manual")
        self.assertEqual(line.get_color(), "#123456")

    def test_redraw_skips_invisible_nodes(self):
        wl = np.linspace(300, 600, 20)
        absorb = np.linspace(0.1, 0.9, 20)
        self.graph.add_node(DataNode(
            id="hidden",
            type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label="hidden",
            state=NodeState.COMMITTED,
            style={"color": "#abcdef", "visible": False},
        ))
        self.tab._redraw()
        # When every UVVIS is invisible the empty-state placeholder
        # renders — no Line2D entries.
        self.assertEqual(self.tab._ax.get_lines(), [])

    def test_redraw_skips_discarded_and_inactive_nodes(self):
        wl = np.linspace(300, 600, 20)
        absorb = np.linspace(0.1, 0.9, 20)
        self.graph.add_node(DataNode(
            id="discarded",
            type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label="discarded",
            state=NodeState.PROVISIONAL,
            style={"color": "#aaaaaa", "visible": True},
        ))
        self.graph.discard_node("discarded")

        self.graph.add_node(DataNode(
            id="inactive",
            type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label="inactive",
            state=NodeState.COMMITTED,
            active=False,
            style={"color": "#bbbbbb", "visible": True},
        ))

        self.tab._redraw()
        self.assertEqual(self.tab._ax.get_lines(), [])

    # ----------- duplicate detection -----------

    def test_duplicate_load_is_skipped(self):
        path = os.path.join(self._tmpdir, "dup.csv")
        _write_csv_fixture(path)
        from uvvis_parser import parse_uvvis_file
        scan = parse_uvvis_file(path)[0]

        self.tab._load_uvvis_scan(path, scan)
        # Same source_file + label combination → duplicate.
        self.assertTrue(
            self.tab._has_existing_load(scan.source_file, scan.label),
        )


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabSidebar(unittest.TestCase):
    """Phase 4a Part B — sidebar is a ScanTreeWidget, gear opens dialog."""

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        from scan_tree_widget import ScanTreeWidget
        import style_dialog
        cls.UVVisTab = UVVisTab
        cls.ScanTreeWidget = ScanTreeWidget
        cls.style_dialog = style_dialog

    def setUp(self):
        # Reset the per-node dialog registry between tests so a leaked
        # entry from one test cannot poison the next.
        self.style_dialog._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)
        self._tmpdir = tempfile.mkdtemp(prefix="uvvis_sidebar_test_")

    def tearDown(self):
        for dlg in list(self.style_dialog._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.style_dialog._open_dialogs.clear()
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass
        for name in os.listdir(self._tmpdir):
            try:
                os.remove(os.path.join(self._tmpdir, name))
            except OSError:
                pass
        try:
            os.rmdir(self._tmpdir)
        except OSError:
            pass

    # ----------- sidebar identity -----------

    def test_sidebar_contains_a_scan_tree_widget(self):
        self.assertIsInstance(self.tab._scan_tree, self.ScanTreeWidget)

    def test_legacy_table_widgets_are_gone(self):
        # The Phase 2 friction "monolithic _rebuild_table" is resolved.
        self.assertFalse(hasattr(self.tab, "_tbl_canvas"))
        self.assertFalse(hasattr(self.tab, "_tbl_inner"))
        self.assertFalse(hasattr(self.tab, "_rebuild_table"))
        self.assertFalse(hasattr(self.tab, "_remove_entry"))
        self.assertFalse(hasattr(self.tab, "_make_leg_btn"))
        self.assertFalse(hasattr(self.tab, "_make_ls_canvas"))
        self.assertFalse(hasattr(self.tab, "_make_lw_entry"))

    # ----------- sidebar lists exactly the loaded UVVIS nodes -----------

    def test_sidebar_lists_loaded_uvvis_nodes(self):
        from uvvis_parser import parse_uvvis_file
        ids: list[str] = []
        for i in range(3):
            path = os.path.join(self._tmpdir, f"row{i}.csv")
            _write_csv_fixture(path)
            scan = parse_uvvis_file(path)[0]
            scan.label = f"row{i}"
            _, _, uvvis_id = self.tab._load_uvvis_scan(path, scan)
            ids.append(uvvis_id)
        self.tab._scan_tree.update_idletasks()

        # ScanTreeWidget rebuilds reactively on NODE_ADDED — every
        # loaded UVVIS id must own a row.
        self.assertEqual(
            set(self.tab._scan_tree._row_frames.keys()),
            set(ids),
        )

    def test_sidebar_excludes_non_uvvis_nodes(self):
        # Add a XANES node directly; it is filtered out by the
        # node_filter list.
        wl = np.linspace(300, 600, 5)
        xanes = DataNode(
            id="xanes_id",
            type=NodeType.XANES,
            arrays={"energy": wl, "mu": np.zeros_like(wl)},
            metadata={},
            label="xanes",
            state=NodeState.COMMITTED,
        )
        self.graph.add_node(xanes)
        self.tab._scan_tree.update_idletasks()
        self.assertNotIn("xanes_id", self.tab._scan_tree._row_frames)

    # ----------- gear button opens unified StyleDialog -----------

    def test_gear_click_opens_style_dialog(self):
        # Add a UVVIS directly so we control the id deterministically.
        wl = np.linspace(300, 600, 10)
        absorb = np.linspace(0.1, 0.9, 10)
        self.graph.add_node(DataNode(
            id="uvvis_target",
            type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label="target",
            state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linewidth": 1.5},
        ))
        self.tab._scan_tree.update_idletasks()

        # Locate the gear button in the row and invoke it.
        row = self.tab._scan_tree._row_frames["uvvis_target"]
        gear = [
            w for w in row.winfo_children()
            if isinstance(w, tk.Button) and w.cget("text") == "⚙"
        ]
        self.assertEqual(len(gear), 1)
        gear[0].invoke()

        # The unified factory registers the live dialog under its id.
        dlg = self.style_dialog._open_dialogs.get("uvvis_target")
        self.assertIsNotNone(dlg)
        self.assertIsInstance(dlg, self.style_dialog.StyleDialog)

    # ----------- ∀ apply-to-all fans out via graph.set_style -----------

    def test_on_uvvis_apply_to_all_writes_each_visible_spectrum_node(self):
        # Two UVVIS + one BASELINE + one XANES so we can confirm:
        #   * UVVIS rows receive the fan-out
        #   * BASELINE rows also receive the fan-out (Phase 4d widened
        #     the scope from UVVIS-only to UVVIS+BASELINE so the new
        #     visible / in_legend toggles cover every sidebar row)
        #   * non-spectrum rows (XANES) are still excluded
        for nid, ntype in [("u1", NodeType.UVVIS),
                           ("u2", NodeType.UVVIS),
                           ("b1", NodeType.BASELINE),
                           ("x1", NodeType.XANES)]:
            wl = np.linspace(300, 600, 4)
            self.graph.add_node(DataNode(
                id=nid, type=ntype,
                arrays={"wavelength_nm": wl, "absorbance": wl * 0,
                        "energy": wl, "mu": wl * 0},
                metadata={}, label=nid,
                state=NodeState.COMMITTED,
                style={"linewidth": 1.5},
            ))

        self.tab._on_uvvis_apply_to_all("linewidth", 3.5)

        self.assertAlmostEqual(self.graph.get_node("u1").style["linewidth"], 3.5)
        self.assertAlmostEqual(self.graph.get_node("u2").style["linewidth"], 3.5)
        # BASELINE included after Phase 4d widening.
        self.assertAlmostEqual(self.graph.get_node("b1").style["linewidth"], 3.5)
        # XANES untouched — fan-out is sidebar-scoped, not all spectra.
        self.assertAlmostEqual(self.graph.get_node("x1").style["linewidth"], 1.5)

    # ----------- graph subscription drives plot redraws -----------

    def test_graph_event_triggers_redraw(self):
        wl = np.linspace(300, 600, 10)
        absorb = np.linspace(0.1, 0.9, 10)
        self.graph.add_node(DataNode(
            id="redraw_target",
            type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label="r",
            state=NodeState.COMMITTED,
            style={"color": "#aabbcc", "visible": True},
        ))

        # First confirm it draws once.
        self.assertEqual(len(self.tab._ax.get_lines()), 1)

        # External style mutation should re-render.
        self.graph.set_style("redraw_target", {"color": "#112233"})
        self.tab.update_idletasks()
        self.assertEqual(self.tab._ax.get_lines()[0].get_color(), "#112233")


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabSidebarCalibration(unittest.TestCase):
    """Phase 4w (CS-47) — first-paint sash auto-bump.

    The tab schedules ``_calibrate_sidebar_width`` via
    ``after_idle`` after construction; it computes a target
    sidebar width from the widest current label plus the always-
    visible row overhead and moves the rightmost sash there.
    Idempotent + one-shot — ``_sidebar_calibrated`` flips True
    after the first successful run so manual sash drags persist.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        from scan_tree_widget import _SIDEBAR_MIN_WIDTH_PX
        cls.UVVisTab = UVVisTab
        cls.SIDEBAR_MIN_PX = _SIDEBAR_MIN_WIDTH_PX

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack(fill="both", expand=True)
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)
        self.tab.pack(fill="both", expand=True)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_paned_window_minsize_uses_sidebar_constant(self):
        # Drill into the PanedWindow's pane configuration. The
        # sidebar pane is the third (index 2) child of body_paned;
        # its minsize must equal the pinned constant so the helper
        # and the geometry manager stay in lock-step.
        paned = self.tab._body_paned
        sidebar_pane = self.tab._sidebar_pane
        # Tk reports paneconfigure values via paneconfigure().
        cfg = paned.paneconfigure(sidebar_pane)
        # The minsize entry comes back as a 5-tuple
        # (option, dbName, dbClass, default, current).
        minsize = int(cfg["minsize"][-1])
        self.assertEqual(minsize, self.SIDEBAR_MIN_PX)

    def test_calibration_flag_starts_false(self):
        self.assertFalse(self.tab._sidebar_calibrated)

    def test_calibration_bails_when_paned_window_unrealised(self):
        # Stub the paned-window width to an unrealised value (1).
        # The flag must stay False so a later attempt can succeed
        # once the geometry settles.
        self.tab._body_paned.winfo_width = lambda: 1  # type: ignore
        self.tab._calibrate_sidebar_width()
        self.assertFalse(self.tab._sidebar_calibrated)

    def test_calibration_sets_flag_and_places_sash_when_realised(self):
        # Stub the geometry queries: paned 1000 px wide, sidebar
        # 240 px target (no labels yet → widest_label = 0 → target
        # clamps up to the sidebar floor). Sash 2 should land at
        # 1000 - 240 = 760.
        self.tab._body_paned.winfo_width = lambda: 1000  # type: ignore
        captured: dict[str, tuple] = {}

        def _fake_sash_place(idx, x, y):
            captured["args"] = (idx, x, y)
        self.tab._body_paned.sash_place = _fake_sash_place  # type: ignore

        self.tab._calibrate_sidebar_width()
        self.assertTrue(self.tab._sidebar_calibrated)
        self.assertEqual(captured["args"][0], 2)
        # Sash x = paned_width - target_sidebar_width.
        # target floor is _SIDEBAR_MIN_WIDTH_PX (240).
        self.assertEqual(captured["args"][1],
                         1000 - self.SIDEBAR_MIN_PX)

    def test_calibration_is_idempotent_after_first_success(self):
        # Once flag flips True, subsequent calls must not place the
        # sash again — preserves manual drags.
        self.tab._body_paned.winfo_width = lambda: 1000  # type: ignore
        calls = []

        def _fake_sash_place(idx, x, y):
            calls.append((idx, x, y))
        self.tab._body_paned.sash_place = _fake_sash_place  # type: ignore

        self.tab._calibrate_sidebar_width()
        self.tab._calibrate_sidebar_width()
        self.tab._calibrate_sidebar_width()
        self.assertEqual(len(calls), 1)

    def test_calibration_caps_at_max_calibrated_px(self):
        # Inject a fake widest_label_pixel_width so the target would
        # exceed the cap. The sash must clamp to the max so the plot
        # pane keeps room.
        self.tab._scan_tree.widest_label_pixel_width = (  # type: ignore
            lambda font=None: 5000
        )
        self.tab._body_paned.winfo_width = lambda: 1200  # type: ignore
        captured = {}
        self.tab._body_paned.sash_place = (  # type: ignore
            lambda idx, x, y: captured.setdefault("x", x)
        )
        self.tab._calibrate_sidebar_width()
        # Target capped at _SIDEBAR_MAX_CALIBRATED_PX (480).
        self.assertEqual(
            captured["x"],
            1200 - self.tab._SIDEBAR_MAX_CALIBRATED_PX,
        )


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabStyleDialogIntegration(unittest.TestCase):
    """Phase 4a Part C — inline dialog gone, unified StyleDialog wired."""

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        import style_dialog
        cls.UVVisTab = UVVisTab
        cls.style_dialog = style_dialog

    def setUp(self):
        self.style_dialog._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        for dlg in list(self.style_dialog._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.style_dialog._open_dialogs.clear()
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    # ----------- the inline dialog has been deleted -----------

    def test_inline_open_style_dialog_method_is_gone(self):
        # Part C deletes _open_style_dialog (~175 lines). The
        # tab keeps only _open_style_dialog_for_node, the gear
        # hand-off to the unified factory.
        self.assertFalse(hasattr(self.tab, "_open_style_dialog"))
        self.assertTrue(hasattr(self.tab, "_open_style_dialog_for_node"))

    # ----------- gear callback opens the unified StyleDialog -----------

    def _add_uvvis(self, nid: str, style: dict | None = None):
        wl = np.linspace(300, 600, 10)
        absorb = np.linspace(0.1, 0.9, 10)
        node = DataNode(
            id=nid,
            type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label=nid,
            state=NodeState.COMMITTED,
            style=dict(style) if style else {"color": "#1f77b4",
                                             "linewidth": 1.5},
        )
        self.graph.add_node(node)
        return node

    def test_gear_callback_registers_unified_style_dialog(self):
        self._add_uvvis("a")
        self.tab._scan_tree.update_idletasks()

        # Trigger the gear hand-off the same way the widget would.
        self.tab._open_style_dialog_for_node("a")

        dlg = self.style_dialog._open_dialogs.get("a")
        self.assertIsNotNone(dlg)
        self.assertIsInstance(dlg, self.style_dialog.StyleDialog)

    def test_slider_change_in_dialog_writes_to_node_style(self):
        self._add_uvvis("a", style={"color": "#1f77b4", "linewidth": 1.5})
        self.tab._open_style_dialog_for_node("a")
        dlg = self.style_dialog._open_dialogs["a"]
        dlg.update_idletasks()

        # Simulating the user dragging the line-width slider drives
        # the bound DoubleVar; the dialog routes it through
        # graph.set_style under the hood.
        dlg._control_vars["linewidth"].set(3.7)
        dlg.update_idletasks()

        self.assertAlmostEqual(self.graph.get_node("a").style["linewidth"], 3.7)

    def test_apply_to_all_fans_out_to_sibling_uvvis_nodes(self):
        # Three UVVIS nodes; opening the dialog on one and using its
        # ∀ fan-out must update the sibling UVVIS nodes via the
        # tab's on_apply_to_all callback.
        self._add_uvvis("a", style={"linewidth": 1.5})
        self._add_uvvis("b", style={"linewidth": 1.5})
        self._add_uvvis("c", style={"linewidth": 1.5})

        self.tab._open_style_dialog_for_node("a")
        dlg = self.style_dialog._open_dialogs["a"]
        dlg.update_idletasks()

        # Set a value, then trigger ∀ fan-out on linewidth via the
        # dialog's per-row delegate (matches the user clicking ∀).
        dlg._control_vars["linewidth"].set(4.2)
        dlg.update_idletasks()
        dlg._delegate_apply_one("linewidth", 4.2)

        for nid in ("a", "b", "c"):
            self.assertAlmostEqual(
                self.graph.get_node(nid).style["linewidth"], 4.2,
                f"node {nid} should have received fan-out",
            )


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabPlotSettingsIntegration(unittest.TestCase):
    """Phase 4b — ⚙ Plot Settings button + dialog hand-off."""

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        import plot_settings_dialog
        cls.UVVisTab = UVVisTab
        cls.psd = plot_settings_dialog

    def setUp(self):
        # Reset registries / module-level user defaults.
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str = "u1") -> None:
        """Drop one UVVIS node onto the tab so _redraw produces a Line2D."""
        wl = np.linspace(300, 600, 10)
        absorb = np.linspace(0.1, 0.9, 10)
        self.graph.add_node(DataNode(
            id=nid,
            type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label=nid,
            state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))

    # ----------- ⚙ button is in the toolbar -----------

    def test_plot_settings_button_exists_in_toolbar(self):
        # Phase 4n CS-27 retired the top-bar "+ Add to TDDFT Overlay"
        # button (replaced by the per-row → icon on each
        # ScanTreeWidget row), so the Plot Settings button now sits
        # in the slot freed by that removal — between the separator
        # and the status label.
        self.assertTrue(hasattr(self.tab, "_plot_settings_btn"))
        btn = self.tab._plot_settings_btn
        self.assertIsInstance(btn, tk.Button)
        self.assertIn("Plot Settings", btn.cget("text"))

    def test_plot_config_initialised_from_factory_defaults(self):
        # No user defaults saved yet → plot_config mirrors factory.
        self.assertEqual(
            self.tab._plot_config["title_font_size"],
            self.psd._FACTORY_DEFAULTS["title_font_size"],
        )
        self.assertEqual(
            self.tab._plot_config["grid"],
            self.psd._FACTORY_DEFAULTS["grid"],
        )

    # ----------- ⚙ click opens dialog and registers it -----------

    def test_button_invocation_opens_and_registers_dialog(self):
        self.tab._plot_settings_btn.invoke()
        dlg = self.psd._open_dialogs.get(id(self.tab))
        self.assertIsNotNone(dlg, "dialog must register under the tab id")
        self.assertIsInstance(dlg, self.psd.PlotConfigDialog)

    def test_open_then_apply_calls_back_into_tab(self):
        # The dialog factory enforces one-per-tab; sanity-check that
        # the on_apply callback is wired and triggers _redraw.
        self.tab._open_plot_settings()
        dlg = self.psd._open_dialogs[id(self.tab)]
        dlg.update_idletasks()

        self._add_uvvis()
        # Pre-Apply: factory default tick label size is 9.
        self.tab._redraw()
        labels_pre = self.tab._ax.get_xticklabels()
        size_pre = labels_pre[0].get_fontsize() if labels_pre else None

        # CS-68 (Phase 4ap): live-preview seam — the var.set fires
        # _on_var_write → _apply_changes_live → tab._redraw via the
        # registered on_apply callback. No explicit Apply step.
        dlg._control_vars["tick_label_font_size"].set(16)
        dlg.update_idletasks()

        labels_post = self.tab._ax.get_xticklabels()
        # The tick params API stores labelsize on each tick label.
        # After redraw with the new config, every visible tick label
        # carries the new size.
        if labels_post:
            self.assertAlmostEqual(labels_post[0].get_fontsize(), 16.0)
        # Config dict was mutated in place.
        self.assertEqual(self.tab._plot_config["tick_label_font_size"], 16)

    # ----------- font size change reaches matplotlib -----------

    def test_apply_font_size_change_reflects_in_axes(self):
        self._add_uvvis()
        self.tab._open_plot_settings()
        dlg = self.psd._open_dialogs[id(self.tab)]
        dlg.update_idletasks()

        # Bump the X-axis label font size from default (10) to 18.
        # CS-68: live commit fires on var.set; no Apply step.
        dlg._control_vars["xlabel_font_size"].set(18)
        dlg.update_idletasks()

        # _redraw has been called via the live on_apply path; the
        # matplotlib X-label carries the new font size.
        self.assertAlmostEqual(
            self.tab._ax.xaxis.label.get_fontsize(), 18.0,
        )

    # ----------- grid toggle removes the gridlines -----------

    def test_apply_grid_off_removes_gridlines(self):
        self._add_uvvis()
        # Default factory: grid=True. Confirm gridlines exist.
        self.tab._redraw()
        x_grid_pre = self.tab._ax.xaxis.get_gridlines()
        # At least one gridline visible by default.
        self.assertTrue(any(g.get_visible() for g in x_grid_pre))

        # CS-68: open dialog, flip grid off — live commit fires on
        # var.set, no Apply gesture.
        self.tab._open_plot_settings()
        dlg = self.psd._open_dialogs[id(self.tab)]
        dlg.update_idletasks()
        dlg._control_vars["grid"].set(False)
        dlg.update_idletasks()

        x_grid_post = self.tab._ax.xaxis.get_gridlines()
        # Gridlines either gone or all marked invisible.
        self.assertFalse(any(g.get_visible() for g in x_grid_post))
        self.assertEqual(self.tab._plot_config["grid"], False)


# =====================================================================
# CS-60 Phase 4ai: double-click on a plot axis opens the dialog tab
# =====================================================================


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabAxisDoubleClickPhase4ai(unittest.TestCase):
    """CS-60 integration: matplotlib double-click on an axis region
    opens the Plot Config dialog pre-selected to that axis's tab.

    The hit-test classifier is exercised in test_plot_axis_hit_test
    against a stub axes; this suite drives a real :class:`UVVisTab`
    with one UVVIS node so the figure is fully laid out and the
    classifier sees real bbox pixels.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        import plot_settings_dialog
        cls.UVVisTab = UVVisTab
        cls.psd = plot_settings_dialog

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)
        self._populate_plot()

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _populate_plot(self) -> None:
        """Add a UVVIS node and force a redraw so the primary axes
        gets a populated window extent."""
        wl = np.linspace(300, 600, 10)
        absorb = np.linspace(0.1, 0.9, 10)
        self.graph.add_node(DataNode(
            id="u1",
            type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label="u1",
            state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))
        self.tab._redraw()
        self.tab._fig.canvas.draw()

    def _event_at_axes_bbox_edge(self, side: str, dblclick: bool = True):
        """Build a MouseEvent-like stub at the requested bbox edge.

        ``side`` is one of "bottom" / "top" / "left" / "right",
        chosen to land in the matching axis-region band that
        ``classify_axis_double_click`` recognises.
        """
        from types import SimpleNamespace
        bbox = self.tab._ax.get_window_extent()
        cx = (bbox.x0 + bbox.x1) / 2.0
        cy = (bbox.y0 + bbox.y1) / 2.0
        if side == "bottom":
            ex, ey = cx, bbox.y0 - 2.0
        elif side == "top":
            ex, ey = cx, bbox.y1 + 2.0
        elif side == "left":
            ex, ey = bbox.x0 - 2.0, cy
        elif side == "right":
            ex, ey = bbox.x1 + 2.0, cy
        elif side == "interior":
            ex, ey = cx, cy
        else:
            raise ValueError(f"unknown side {side!r}")
        return SimpleNamespace(x=ex, y=ey, dblclick=dblclick)

    # ----- canvas wiring -----

    def test_button_press_event_is_bound(self):
        # The canvas exposes mpl_connect's registry as
        # canvas.callbacks; checking the bind via a real
        # mpl_connect roundtrip is sufficient to confirm the wiring.
        # We just smoke-test that the handler exists on the tab.
        self.assertTrue(hasattr(self.tab, "_on_mpl_axis_double_click"))
        self.assertTrue(callable(self.tab._on_mpl_axis_double_click))

    # ----- double-clicks open the dialog on the right tab -----

    def test_double_click_bottom_opens_primary_x_tab(self):
        ev = self._event_at_axes_bbox_edge("bottom", dblclick=True)
        self.tab._on_mpl_axis_double_click(ev)
        dlg = self.psd._open_dialogs.get(id(self.tab))
        self.assertIsNotNone(dlg, "axis double-click must open the dialog")
        self.assertEqual(dlg.current_tab_key(), "primary_x")

    def test_double_click_top_opens_secondary_x_tab(self):
        ev = self._event_at_axes_bbox_edge("top", dblclick=True)
        self.tab._on_mpl_axis_double_click(ev)
        dlg = self.psd._open_dialogs.get(id(self.tab))
        self.assertIsNotNone(dlg)
        self.assertEqual(dlg.current_tab_key(), "secondary_x")

    def test_double_click_left_opens_primary_y_tab(self):
        ev = self._event_at_axes_bbox_edge("left", dblclick=True)
        self.tab._on_mpl_axis_double_click(ev)
        dlg = self.psd._open_dialogs.get(id(self.tab))
        self.assertIsNotNone(dlg)
        self.assertEqual(dlg.current_tab_key(), "primary_y")

    def test_double_click_right_with_no_twin_opens_primary_y_tab(self):
        # No SECOND_DERIVATIVE / non-primary node, so no secondary y
        # axis exists. Right-side click maps to primary_y per the
        # hit-test classifier's no-twin contract.
        ev = self._event_at_axes_bbox_edge("right", dblclick=True)
        self.tab._on_mpl_axis_double_click(ev)
        dlg = self.psd._open_dialogs.get(id(self.tab))
        self.assertIsNotNone(dlg)
        self.assertEqual(dlg.current_tab_key(), "primary_y")

    # ----- non-axis clicks do NOT open the dialog -----

    def test_single_click_does_not_open_dialog(self):
        ev = self._event_at_axes_bbox_edge("bottom", dblclick=False)
        self.tab._on_mpl_axis_double_click(ev)
        self.assertNotIn(id(self.tab), self.psd._open_dialogs)

    def test_double_click_interior_does_not_open_dialog(self):
        ev = self._event_at_axes_bbox_edge("interior", dblclick=True)
        self.tab._on_mpl_axis_double_click(ev)
        self.assertNotIn(id(self.tab), self.psd._open_dialogs)

    # ----- the gear button still opens on Global -----

    def test_gear_button_still_opens_on_global_tab(self):
        # Sanity check that the CS-23 entry point hasn't drifted —
        # the ⚙ button continues to open the Global tab.
        self.tab._open_plot_settings()
        dlg = self.psd._open_dialogs[id(self.tab)]
        dlg.update_idletasks()
        self.assertEqual(dlg.current_tab_key(), "global")

    # ----- second double-click on a different axis switches tab -----

    def test_double_click_switches_tab_of_existing_dialog(self):
        # Open on primary_x via a bottom click.
        ev_bottom = self._event_at_axes_bbox_edge("bottom", dblclick=True)
        self.tab._on_mpl_axis_double_click(ev_bottom)
        dlg = self.psd._open_dialogs[id(self.tab)]
        self.assertEqual(dlg.current_tab_key(), "primary_x")
        # Second double-click on the left side — the dialog must
        # switch to primary_y rather than create a duplicate.
        ev_left = self._event_at_axes_bbox_edge("left", dblclick=True)
        self.tab._on_mpl_axis_double_click(ev_left)
        # Same dialog still registered.
        self.assertIs(self.psd._open_dialogs[id(self.tab)], dlg)
        self.assertEqual(dlg.current_tab_key(), "primary_y")

    # ----- on_apply still wires through ------------------------------

    def test_double_click_dialog_apply_triggers_redraw(self):
        ev = self._event_at_axes_bbox_edge("bottom", dblclick=True)
        self.tab._on_mpl_axis_double_click(ev)
        dlg = self.psd._open_dialogs[id(self.tab)]
        dlg.update_idletasks()
        # CS-68: edit a global setting — the live-preview path
        # drives _redraw because the host's on_apply callback IS
        # the tab's _redraw.
        dlg._control_vars["xlabel_font_size"].set(18)
        dlg.update_idletasks()
        self.assertAlmostEqual(
            self.tab._ax.xaxis.label.get_fontsize(), 18.0,
        )


# =====================================================================
# CS-62 Phase 4ak: per-axis schema host wiring (axis_label_override
# rendering + plots_by_role enumeration)
# =====================================================================


class TestEnumeratePlotsByRolePhase4ak(unittest.TestCase):
    """Unit tests for the module-level :func:`_enumerate_plots_by_role`.

    No Tk display needed — these are pure-Python tests against
    DataNode stubs. The test ensures every plottable node category
    feeds the right axis-tab bucket.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import _enumerate_plots_by_role
        cls.enumerate_plots_by_role = staticmethod(_enumerate_plots_by_role)

    def _node(
        self,
        node_type: "NodeType",
        label: str,
        y_axis_override: "str | None" = None,
        visible: bool = True,
    ) -> "DataNode":
        style: dict = {"visible": visible}
        if y_axis_override is not None:
            style["y_axis"] = y_axis_override
        return DataNode(
            id=label, type=node_type,
            arrays={"wavelength_nm": np.array([300., 400.]),
                    "absorbance": np.array([0.1, 0.2])},
            metadata={"source_file": "synthetic"},
            label=label,
            state=NodeState.COMMITTED,
            style=style,
        )

    def test_empty_inputs_return_five_empty_tuples(self):
        result = self.enumerate_plots_by_role(
            [], [], [], secondary_x_active=False,
        )
        self.assertEqual(set(result.keys()), {
            "primary_x", "secondary_x",
            "primary_y", "secondary_y", "tertiary_y",
        })
        for tup in result.values():
            self.assertEqual(tup, ())

    def test_uvvis_node_lands_on_primary_x_and_primary_y(self):
        uv = self._node(NodeType.UVVIS, "scan-a")
        result = self.enumerate_plots_by_role(
            [uv], [], [], secondary_x_active=False,
        )
        self.assertEqual(result["primary_x"], ("scan-a",))
        self.assertEqual(result["primary_y"], ("scan-a",))
        self.assertEqual(result["secondary_y"], ())
        self.assertEqual(result["tertiary_y"], ())

    def test_second_derivative_lands_on_secondary_y_by_default(self):
        d2 = self._node(NodeType.SECOND_DERIVATIVE, "d2-a")
        result = self.enumerate_plots_by_role(
            [], [d2], [], secondary_x_active=False,
        )
        self.assertEqual(result["primary_x"], ("d2-a",))
        self.assertEqual(result["primary_y"], ())
        self.assertEqual(result["secondary_y"], ("d2-a",))

    def test_per_style_y_axis_override_routes_to_tertiary(self):
        node = self._node(
            NodeType.UVVIS, "scan-tert", y_axis_override="tertiary",
        )
        result = self.enumerate_plots_by_role(
            [node], [], [], secondary_x_active=False,
        )
        self.assertEqual(result["primary_y"], ())
        self.assertEqual(result["tertiary_y"], ("scan-tert",))

    def test_invisible_nodes_are_skipped(self):
        visible = self._node(NodeType.UVVIS, "shown")
        hidden = self._node(NodeType.UVVIS, "hidden", visible=False)
        result = self.enumerate_plots_by_role(
            [visible, hidden], [], [], secondary_x_active=False,
        )
        self.assertEqual(result["primary_x"], ("shown",))
        self.assertEqual(result["primary_y"], ("shown",))

    def test_secondary_x_mirrors_primary_x_when_active(self):
        uv = self._node(NodeType.UVVIS, "scan-x")
        d2 = self._node(NodeType.SECOND_DERIVATIVE, "deriv-x")
        result_active = self.enumerate_plots_by_role(
            [uv], [d2], [], secondary_x_active=True,
        )
        result_inactive = self.enumerate_plots_by_role(
            [uv], [d2], [], secondary_x_active=False,
        )
        self.assertEqual(
            result_active["secondary_x"], result_active["primary_x"],
        )
        self.assertEqual(result_inactive["secondary_x"], ())

    def test_peak_list_nodes_are_listed(self):
        peak = DataNode(
            id="pk", type=NodeType.PEAK_LIST,
            arrays={"peak_wavelengths_nm": np.array([350.0]),
                    "peak_absorbances": np.array([0.5])},
            metadata={}, label="peaks",
            state=NodeState.COMMITTED, style={"visible": True},
        )
        result = self.enumerate_plots_by_role(
            [], [], [peak], secondary_x_active=False,
        )
        self.assertEqual(result["primary_x"], ("peaks",))
        self.assertEqual(result["primary_y"], ("peaks",))


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabPerAxisSchemaPhase4ak(unittest.TestCase):
    """CS-62 host wiring: axis_label_override renders on every
    populated axis; ``plots_by_role`` threads through the dialog
    open calls; the legacy flat ``cfg["tick_direction"]`` keeps
    working through the renderer's fallback chain.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        import plot_settings_dialog
        cls.UVVisTab = UVVisTab
        cls.psd = plot_settings_dialog

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str = "u1") -> DataNode:
        wl = np.linspace(300, 600, 10)
        absorb = np.linspace(0.1, 0.9, 10)
        node = DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label=nid,
            state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        )
        self.graph.add_node(node)
        return node

    # ---- _compute_plots_by_role wiring on the tab ----

    def test_compute_plots_by_role_reflects_live_graph(self):
        self._add_uvvis("alpha")
        self._add_uvvis("beta")
        result = self.tab._compute_plots_by_role()
        self.assertEqual(set(result["primary_x"]), {"alpha", "beta"})
        self.assertEqual(set(result["primary_y"]), {"alpha", "beta"})
        self.assertEqual(result["secondary_y"], ())
        self.assertEqual(result["tertiary_y"], ())

    def test_open_plot_settings_threads_plots_by_role(self):
        self._add_uvvis("gamma")
        self.tab._open_plot_settings()
        dlg = self.psd._open_dialogs[id(self.tab)]
        dlg.update_idletasks()
        # The dialog stored the snapshot under self._plots_by_role.
        self.assertEqual(dlg._plots_by_role["primary_x"], ("gamma",))
        self.assertEqual(dlg._plots_by_role["primary_y"], ("gamma",))

    def test_double_click_threads_plots_by_role(self):
        self._add_uvvis("delta")
        self.tab._redraw()
        self.tab._fig.canvas.draw()
        from types import SimpleNamespace
        bbox = self.tab._ax.get_window_extent()
        cx = (bbox.x0 + bbox.x1) / 2.0
        ev = SimpleNamespace(x=cx, y=bbox.y0 - 2.0, dblclick=True)
        self.tab._on_mpl_axis_double_click(ev)
        dlg = self.psd._open_dialogs[id(self.tab)]
        dlg.update_idletasks()
        self.assertEqual(dlg._plots_by_role["primary_x"], ("delta",))

    # ---- axis_label_override rendering ----

    def test_primary_x_override_wins_over_auto_label(self):
        self._add_uvvis()
        self.tab._plot_config["axes"] = {
            "primary_x": {"axis_label_override": "Custom X label"},
        }
        self.tab._redraw()
        self.assertEqual(self.tab._ax.get_xlabel(), "Custom X label")

    def test_empty_override_falls_through_to_auto_label(self):
        self._add_uvvis()
        # No override → "Wavelength (nm)" auto label for nm unit.
        self.tab._redraw()
        self.assertEqual(self.tab._ax.get_xlabel(), "Wavelength (nm)")

    def test_primary_y_override_wins_over_resolved_label(self):
        self._add_uvvis()
        self.tab._plot_config["axes"] = {
            "primary_y": {"axis_label_override": "Custom Y label"},
        }
        self.tab._redraw()
        self.assertEqual(self.tab._ax.get_ylabel(), "Custom Y label")

    def test_secondary_x_override_replaces_wavelength_label(self):
        # The secondary X axis is the wavelength↔energy twin —
        # active only when x_unit == "cm-1" and the toggle is on.
        # matplotlib's ``Axes.secondary_xaxis`` attaches the new
        # axis under ``ax.child_axes`` rather than ``fig.axes``.
        self._add_uvvis()
        self.tab._x_unit.set("cm-1")
        self.tab._show_nm_axis.set(True)
        self.tab._plot_config["axes"] = {
            "secondary_x": {"axis_label_override": "Wavelength axis"},
        }
        self.tab._redraw()
        child_xlabels = [
            ca.get_xlabel() for ca in self.tab._ax.child_axes
        ]
        self.assertIn("Wavelength axis", child_xlabels)
        self.assertNotIn("λ (nm)", child_xlabels)

    def test_secondary_y_override_wins_over_resolved_label(self):
        # SECOND_DERIVATIVE defaults to the secondary y axis.
        wl = np.linspace(300, 600, 10)
        absorb = np.linspace(-0.01, 0.01, 10)
        self.graph.add_node(DataNode(
            id="d2", type=NodeType.SECOND_DERIVATIVE,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label="d2",
            state=NodeState.COMMITTED,
            style={"color": "#ff7f0e", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))
        self.tab._plot_config["axes"] = {
            "secondary_y": {"axis_label_override": "Derivative axis"},
        }
        self.tab._redraw()
        self.assertIn("secondary", self.tab._axes_by_role)
        self.assertEqual(
            self.tab._axes_by_role["secondary"].get_ylabel(),
            "Derivative axis",
        )

    # ---- tick_direction fallback chain ----

    def test_legacy_flat_tick_direction_still_renders(self):
        # A pre-Phase-4ak _plot_config carries flat "tick_direction"
        # and no "axes" sub-dict. The renderer's
        # _per_axis_tick_direction helper falls back through to the
        # flat key and the matplotlib state reflects it.
        self._add_uvvis()
        self.tab._plot_config.pop("axes", None)
        self.tab._plot_config["tick_direction"] = "out"
        self.tab._redraw()
        # matplotlib stores tick_params under axes via the rcParams /
        # major tick attributes. Reading back the direction is awkward;
        # instead, assert the tick label tickdir attribute through
        # the major ticks.
        primary_ticks = self.tab._ax.get_xticklines()
        # Each tick line carries the marker style — for direction
        # "out", the marker is on the spine; for "in", it's reversed.
        # An end-to-end check is impractical with matplotlib's
        # internals, so verify the helper directly.
        from uvvis_tab import _per_axis_tick_direction
        self.assertEqual(
            _per_axis_tick_direction(self.tab._plot_config, "primary_x"),
            "out",
        )

    def test_nested_tick_direction_reads_primary_x_slot(self):
        # After migration, the renderer reads primary_x's slot. Other
        # roles' values still store but aren't yet applied (deferred
        # to Phase 4al). The single uniform read is the Phase 4ak
        # transitional behaviour.
        cfg = {
            "axes": {
                "primary_x":   {"tick_direction": "out"},
                "primary_y":   {"tick_direction": "inout"},
                "secondary_x": {"tick_direction": "in"},
                "secondary_y": {"tick_direction": "in"},
                "tertiary_y":  {"tick_direction": "in"},
            },
        }
        from uvvis_tab import _per_axis_tick_direction
        self.assertEqual(
            _per_axis_tick_direction(cfg, "primary_x"), "out",
        )
        # And the per-axis reads are honest about the stored values.
        self.assertEqual(
            _per_axis_tick_direction(cfg, "primary_y"), "inout",
        )


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabPerAxisTickRenderingPhase4al(unittest.TestCase):
    """Phase 4al — per-axis tick direction wiring in ``_redraw``.

    Phase 4ak (CS-62) invented ``cfg["axes"][<role>]["tick_direction"]``
    but the renderer read primary_x's slot uniformly. This phase
    splits the reads: each tick_params call site reads its own
    axis-role. Tests patch ``_per_axis_tick_direction`` to capture
    the role argument the renderer passes at each call site, plus an
    end-to-end check that distinct values land on distinct matplotlib
    Axis tick params.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str = "u1") -> DataNode:
        wl = np.linspace(300, 600, 10)
        absorb = np.linspace(0.1, 0.9, 10)
        node = DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label=nid,
            state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        )
        self.graph.add_node(node)
        return node

    def _add_second_derivative(self, nid: str = "d1") -> DataNode:
        wl = np.linspace(300, 600, 10)
        absorb = np.linspace(-0.01, 0.01, 10)
        node = DataNode(
            id=nid, type=NodeType.SECOND_DERIVATIVE,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label=nid,
            state=NodeState.COMMITTED,
            style={"color": "#ff7f0e", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        )
        self.graph.add_node(node)
        return node

    # ---- per-call-site role argument ----

    def test_renderer_reads_primary_x_for_x_ticks(self):
        from unittest import mock
        self._add_uvvis()
        with mock.patch(
            "uvvis_tab._per_axis_tick_direction", return_value="in",
        ) as m:
            self.tab._redraw()
        roles = [call.args[1] for call in m.call_args_list]
        self.assertIn("primary_x", roles)

    def test_renderer_reads_primary_y_for_y_ticks(self):
        from unittest import mock
        self._add_uvvis()
        with mock.patch(
            "uvvis_tab._per_axis_tick_direction", return_value="in",
        ) as m:
            self.tab._redraw()
        roles = [call.args[1] for call in m.call_args_list]
        self.assertIn("primary_y", roles)

    def test_renderer_reads_secondary_y_when_twin_active(self):
        # SECOND_DERIVATIVE defaults to the secondary axis (CS-44), so
        # adding one materialises the twinx() and triggers the
        # secondary_y read inside get_axis.
        from unittest import mock
        self._add_uvvis()
        self._add_second_derivative()
        with mock.patch(
            "uvvis_tab._per_axis_tick_direction", return_value="in",
        ) as m:
            self.tab._redraw()
        roles = [call.args[1] for call in m.call_args_list]
        self.assertIn("secondary_y", roles)

    def test_renderer_reads_tertiary_y_when_twin_active(self):
        # Force a tertiary twin by setting style["y_axis"]="tertiary"
        # on a visible UVVIS node (CS-50 override).
        from unittest import mock
        node = self._add_uvvis()
        node.style["y_axis"] = "tertiary"
        with mock.patch(
            "uvvis_tab._per_axis_tick_direction", return_value="in",
        ) as m:
            self.tab._redraw()
        roles = [call.args[1] for call in m.call_args_list]
        self.assertIn("tertiary_y", roles)

    def test_renderer_reads_secondary_x_when_wavelength_twin_active(self):
        # Activating cm-1 + nm-axis toggle creates the secondary_xaxis
        # sibling that hosts the wavelength↔energy twin. Phase 4al
        # rewired its tick_params direction from the hardcoded "in"
        # to a per-axis read on the secondary_x role.
        from unittest import mock
        self._add_uvvis()
        self.tab._x_unit.set("cm-1")
        self.tab._show_nm_axis.set(True)
        with mock.patch(
            "uvvis_tab._per_axis_tick_direction", return_value="in",
        ) as m:
            self.tab._redraw()
        roles = [call.args[1] for call in m.call_args_list]
        self.assertIn("secondary_x", roles)

    # ---- end-to-end: distinct per-axis values land on distinct axes ----

    def test_distinct_directions_per_axis_land_on_matplotlib(self):
        # Set different directions per role, redraw, and read back via
        # matplotlib's public Axis.get_tick_params API.
        self._add_uvvis()
        self.tab._plot_config["axes"] = {
            "primary_x":   {"tick_direction": "out",   "axis_label_override": ""},
            "primary_y":   {"tick_direction": "inout", "axis_label_override": ""},
            "secondary_x": {"tick_direction": "in",    "axis_label_override": ""},
            "secondary_y": {"tick_direction": "in",    "axis_label_override": ""},
            "tertiary_y":  {"tick_direction": "in",    "axis_label_override": ""},
        }
        self.tab._redraw()
        x_params = self.tab._ax.xaxis.get_tick_params(which="major")
        y_params = self.tab._ax.yaxis.get_tick_params(which="major")
        self.assertEqual(x_params.get("direction"), "out")
        self.assertEqual(y_params.get("direction"), "inout")

    def test_secondary_x_distinct_from_primary_x(self):
        # The hardcoded direction="in" on the wavelength twin is gone.
        # If Secondary X's slot says "out", the wavelength twin should
        # render with "out" ticks regardless of Primary X's "in".
        self._add_uvvis()
        self.tab._x_unit.set("cm-1")
        self.tab._show_nm_axis.set(True)
        self.tab._plot_config["axes"] = {
            "primary_x":   {"tick_direction": "in",  "axis_label_override": ""},
            "primary_y":   {"tick_direction": "in",  "axis_label_override": ""},
            "secondary_x": {"tick_direction": "out", "axis_label_override": ""},
            "secondary_y": {"tick_direction": "in",  "axis_label_override": ""},
            "tertiary_y":  {"tick_direction": "in",  "axis_label_override": ""},
        }
        self.tab._redraw()
        # The secondary_xaxis sibling lives under ax.child_axes.
        self.assertTrue(self.tab._ax.child_axes)
        sec = self.tab._ax.child_axes[0]
        sec_params = sec.xaxis.get_tick_params(which="major")
        self.assertEqual(sec_params.get("direction"), "out")
        # And primary_x still reads "in".
        x_params = self.tab._ax.xaxis.get_tick_params(which="major")
        self.assertEqual(x_params.get("direction"), "in")


class TestCustomTicksParsePhase4aq(unittest.TestCase):
    """Phase 4aq (CS-69) — ``_parse_custom_ticks_str`` policy.

    Pure-helper coverage matching :func:`uvvis_tab._parse_tick_str`'s
    "silent-drop invalid, ``None`` for empty / all-invalid" contract.
    No Tk display needed.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import _parse_custom_ticks_str
        cls._parse = staticmethod(_parse_custom_ticks_str)

    def test_empty_string_returns_none(self):
        self.assertIsNone(self._parse(""))

    def test_whitespace_only_returns_none(self):
        self.assertIsNone(self._parse("   "))
        self.assertIsNone(self._parse("\t\n"))

    def test_non_string_input_returns_none(self):
        # Migration shim writes ``""`` for missing slots, but a
        # malformed config might carry a non-string value through; the
        # helper must not crash.
        self.assertIsNone(self._parse(None))  # type: ignore[arg-type]
        self.assertIsNone(self._parse(123))   # type: ignore[arg-type]

    def test_valid_csv_returns_tuple(self):
        result = self._parse("300, 400, 500, 700, 900")
        self.assertEqual(result, (300.0, 400.0, 500.0, 700.0, 900.0))

    def test_mixed_silently_drops_invalid_tokens(self):
        # "abc" is not a float; the helper silently drops it and
        # returns the parseable subset.
        self.assertEqual(self._parse("300, abc, 500"), (300.0, 500.0))

    def test_all_invalid_returns_none(self):
        # No salvageable tokens → None, matching empty input.
        self.assertIsNone(self._parse("abc, xyz, ?"))

    def test_extra_commas_skipped(self):
        # Double comma yields an empty token in the middle — silently
        # dropped.
        self.assertEqual(self._parse("300,,400"), (300.0, 400.0))
        self.assertEqual(self._parse(", 300, ,400, "), (300.0, 400.0))

    def test_negative_values_kept(self):
        # Unlike ``_parse_tick_str`` (CS-65) which rejects non-positive
        # for ``MultipleLocator``, ``_parse_custom_ticks_str`` accepts
        # negative tick positions — ``FixedLocator`` handles them.
        self.assertEqual(self._parse("-1, 0, 2"), (-1.0, 0.0, 2.0))

    def test_non_finite_silently_dropped(self):
        # ``np.isfinite`` rejects inf / nan; the helper drops them.
        result = self._parse("300, inf, 500, nan, 700")
        self.assertEqual(result, (300.0, 500.0, 700.0))

    def test_single_value_returns_one_element_tuple(self):
        self.assertEqual(self._parse("500"), (500.0,))

    def test_float_values_preserved(self):
        result = self._parse("300.5, 400.25, 500.125")
        self.assertEqual(result, (300.5, 400.25, 500.125))


class TestPerAxisCustomTicksAccessorPhase4aq(unittest.TestCase):
    """Phase 4aq (CS-69) — ``_per_axis_custom_ticks`` reader."""

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import _per_axis_custom_ticks
        cls._read = staticmethod(_per_axis_custom_ticks)

    def test_missing_axes_returns_empty(self):
        # Pre-Phase-4aq config / blank config → "" (no override).
        self.assertEqual(self._read({}, "secondary_x"), "")

    def test_missing_role_returns_empty(self):
        self.assertEqual(self._read({"axes": {}}, "secondary_x"), "")

    def test_missing_custom_ticks_key_returns_empty(self):
        cfg = {"axes": {"secondary_x": {"tick_major": "100"}}}
        self.assertEqual(self._read(cfg, "secondary_x"), "")

    def test_non_string_value_returns_empty(self):
        # Defensive: stored value is not a string (e.g., None from a
        # malformed config) — return "" so the renderer falls through
        # to ``tick_major`` cleanly.
        cfg = {"axes": {"secondary_x": {"custom_ticks": None}}}
        self.assertEqual(self._read(cfg, "secondary_x"), "")

    def test_string_value_returned_verbatim(self):
        cfg = {"axes": {"secondary_x":
                        {"custom_ticks": "300, 400, 500"}}}
        self.assertEqual(self._read(cfg, "secondary_x"), "300, 400, 500")


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestSecondaryXAxisLinkPhase4aq(unittest.TestCase):
    """Phase 4aq (CS-69) — B-005 linked secondary X axis contract.

    Pins three invariants:

    1. With cm⁻¹ + toggle ON, the secondary X axis is matplotlib-
       linked via ``secondary_xaxis(functions=(_fwd, _fwd))``;
       ``sec.get_xlim()`` tracks ``_fwd(ax.get_xlim())`` by
       construction.
    2. Same for ``unit == "eV"`` (D8 lock relaxation: the wavelength
       toggle activates the linked secondary for both cm⁻¹ and eV).
    3. The renderer does NOT call ``sec.set_xlim`` even when the
       schema's ``secondary_x.autoscale=False`` with non-empty
       ``range_lo`` / ``range_hi``. Calling ``sec.set_xlim`` on a
       linked secondary axis would back-propagate through the inverse
       of ``_fwd`` and CORRUPT the primary axis's xlim — the bug at
       the root of B-005. Stale legacy ``range_lo`` / ``range_hi`` /
       ``autoscale`` / ``scale`` values are therefore inert.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab, _HC_NM_EV
        cls.UVVisTab = UVVisTab
        cls._HC_NM_EV = _HC_NM_EV

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str = "u1") -> None:
        wl = np.linspace(300, 600, 10)
        absorb = np.linspace(0.1, 0.9, 10)
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label=nid,
            state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))

    # ---- link invariants ----

    def test_cm1_secondary_x_axis_tracks_primary_via_fwd(self):
        # _fwd(x) = 1e7 / x for cm-1; both forward AND inverse slots of
        # secondary_xaxis(...) receive the same callable (it's self-
        # inverse). After redraw, sec.get_xlim() must equal _fwd of
        # ax.get_xlim().
        self._add_uvvis()
        self.tab._x_unit.set("cm-1")
        self.tab._show_nm_axis.set(True)
        self.tab._redraw()
        self.assertTrue(self.tab._ax.child_axes,
                        "Secondary X axis must exist for cm-1 + toggle ON")
        sec = self.tab._ax.child_axes[0]
        ax_lo, ax_hi = self.tab._ax.get_xlim()
        sec_lo, sec_hi = sec.get_xlim()
        # The link is via 1e7 / x. Ordered by sec's natural orientation
        # (matplotlib may invert), so we compare the SET of transformed
        # endpoints rather than positional order.
        expected = {1e7 / ax_lo, 1e7 / ax_hi}
        actual = {sec_lo, sec_hi}
        for e in expected:
            self.assertTrue(
                any(abs(a - e) < 1e-6 for a in actual),
                f"Secondary xlim {actual} should contain 1e7/{ax_lo or ax_hi}"
                f" ≈ {e}",
            )

    def test_eV_secondary_x_axis_tracks_primary_via_fwd(self):
        # D8 lock relaxation: same link contract for unit == "eV"
        # via _HC_NM_EV / x. Tests that toggling x_unit to eV + the
        # nm-axis toggle creates the linked sibling.
        self._add_uvvis()
        self.tab._x_unit.set("eV")
        self.tab._show_nm_axis.set(True)
        self.tab._redraw()
        self.assertTrue(self.tab._ax.child_axes,
                        "Secondary X axis must exist for eV + toggle ON")
        sec = self.tab._ax.child_axes[0]
        ax_lo, ax_hi = self.tab._ax.get_xlim()
        sec_lo, sec_hi = sec.get_xlim()
        expected = {self._HC_NM_EV / ax_lo, self._HC_NM_EV / ax_hi}
        actual = {sec_lo, sec_hi}
        for e in expected:
            self.assertTrue(
                any(abs(a - e) < 1e-6 for a in actual),
                f"Secondary xlim {actual} should contain _HC_NM_EV/"
                f"{ax_lo or ax_hi} ≈ {e}",
            )

    def test_nm_unit_does_not_create_secondary_x(self):
        # The wavelength toggle is gated on unit ∈ {cm-1, eV}; nm is
        # already wavelength so no linked sibling makes sense. Confirm
        # the secondary axis is NOT created in nm mode regardless of
        # the toggle's value.
        self._add_uvvis()
        self.tab._x_unit.set("nm")
        self.tab._show_nm_axis.set(True)
        self.tab._redraw()
        self.assertFalse(self.tab._ax.child_axes,
                         "Secondary X must not be created in nm mode")

    def test_renderer_does_not_corrupt_primary_xlim_via_range_lo_hi(self):
        # B-005 root cause: the buggy renderer called
        # ``sec.set_xlim(lo, hi)`` whenever secondary_x.autoscale=False
        # with non-empty range_lo / range_hi. On a linked secondary
        # axis matplotlib back-propagates through the inverse of _fwd
        # and CORRUPTS the primary axis. The CS-69 fix never calls
        # sec.set_xlim, so the primary xlim is preserved across the
        # autoscale-False schema.
        self._add_uvvis()
        self.tab._x_unit.set("cm-1")
        self.tab._show_nm_axis.set(True)
        # Capture the primary xlim with autoscale=True (default).
        self.tab._redraw()
        baseline_lo, baseline_hi = self.tab._ax.get_xlim()
        # Now populate the stale secondary_x range that the buggy code
        # would have pushed through ``sec.set_xlim``.
        self.tab._plot_config["axes"] = {
            "secondary_x": {
                "autoscale": False,
                "range_lo": "300",
                "range_hi": "500",
                "scale": "linear",
            },
        }
        self.tab._redraw()
        # The primary xlim must match the autoscale-derived baseline;
        # if the buggy code path runs, ax.set_xlim was hit via the
        # back-propagation through _fwd at the secondary's set_xlim
        # call and the baseline diverges.
        post_lo, post_hi = self.tab._ax.get_xlim()
        self.assertAlmostEqual(post_lo, baseline_lo, places=4)
        self.assertAlmostEqual(post_hi, baseline_hi, places=4)

    def test_renderer_does_not_corrupt_primary_xscale_via_secondary_log(self):
        # Companion to the range case: secondary_x.scale="log" once
        # called ``sec.set_xscale("log")`` which on a linked secondary
        # could propagate to the primary. The CS-69 fix never calls
        # sec.set_xscale; the primary stays linear regardless of the
        # secondary_x.scale value.
        self._add_uvvis()
        self.tab._x_unit.set("cm-1")
        self.tab._show_nm_axis.set(True)
        self.tab._plot_config["axes"] = {
            "secondary_x": {"scale": "log"},
        }
        self.tab._redraw()
        # Primary x scale must still be linear.
        self.assertEqual(self.tab._ax.get_xscale(), "linear")


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabLiveLinkStatePhase4ar(unittest.TestCase):
    """Phase 4ar (CS-70) — host-side live link-state plumbing.

    Pins the three new UVVisTab methods and their wiring:

    * ``_update_nm_cb_state`` — disables ``_nm_cb`` when
      ``_x_unit == "nm"`` and forces ``_show_nm_axis`` False.
      Enabled (NORMAL) when unit ∈ {"cm-1", "eV"}.

    * ``_on_nm_cb_toggle`` — bound as ``_nm_cb``'s command;
      invokes ``_redraw`` and ``_notify_axis_link_state_change``.

    * ``_notify_axis_link_state_change`` — looks up the per-host
      dialog in ``plot_settings_dialog._open_dialogs[id(self)]``
      (CS-66) and calls ``refresh_axis_link_state`` with the freshly
      computed link bool. No-op when no dialog is open.

    Wiring sentinels: ``_on_unit_change`` chains the gate update +
    notification before ``_redraw``; the dialog's ``_secondary_x_linked``
    snapshot tracks live host changes.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        import plot_settings_dialog as psd
        cls.UVVisTab = UVVisTab
        cls.psd = psd

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    # ---- _update_nm_cb_state ----

    def test_nm_cb_disabled_at_construction_default_unit_nm(self):
        # Default ``_x_unit`` is "nm" → _update_nm_cb_state should have
        # fired once after _nm_cb was built and left it DISABLED.
        self.assertEqual(self.tab._x_unit.get(), "nm")
        self.assertEqual(
            str(self.tab._nm_cb.cget("state")), "disabled",
            "nm_cb should be DISABLED when default unit is nm",
        )

    def test_nm_cb_enabled_after_switch_to_cm1(self):
        self.tab._x_unit.set("cm-1")
        self.tab._update_nm_cb_state()
        self.assertEqual(
            str(self.tab._nm_cb.cget("state")), "normal",
            "nm_cb should be NORMAL when unit is cm-1",
        )

    def test_nm_cb_enabled_after_switch_to_eV(self):
        # D8 lock relaxation: eV is also a non-nm unit that allows the
        # wavelength secondary axis.
        self.tab._x_unit.set("eV")
        self.tab._update_nm_cb_state()
        self.assertEqual(
            str(self.tab._nm_cb.cget("state")), "normal",
            "nm_cb should be NORMAL when unit is eV",
        )

    def test_nm_cb_disabled_after_switch_back_to_nm(self):
        self.tab._x_unit.set("cm-1")
        self.tab._update_nm_cb_state()
        self.tab._x_unit.set("nm")
        self.tab._update_nm_cb_state()
        self.assertEqual(
            str(self.tab._nm_cb.cget("state")), "disabled",
        )

    def test_update_forces_show_nm_axis_false_when_unit_nm(self):
        # User had toggle ON in cm⁻¹ mode; switching to nm should
        # force the BooleanVar to False (toggle has no effect in nm
        # mode anyway, but leaving it stale-truthy is misleading UX).
        self.tab._x_unit.set("cm-1")
        self.tab._show_nm_axis.set(True)
        self.tab._x_unit.set("nm")
        self.tab._update_nm_cb_state()
        self.assertFalse(self.tab._show_nm_axis.get())

    def test_update_does_not_flip_show_nm_axis_when_unit_non_nm(self):
        # When unit ∈ {cm-1, eV}, the gate enables the Checkbutton but
        # must NOT touch the BooleanVar's current value (the user's
        # choice is preserved across switches between cm-1 and eV).
        self.tab._x_unit.set("cm-1")
        self.tab._show_nm_axis.set(True)
        self.tab._update_nm_cb_state()
        self.assertTrue(self.tab._show_nm_axis.get())
        self.tab._x_unit.set("eV")
        self.tab._update_nm_cb_state()
        self.assertTrue(self.tab._show_nm_axis.get())

    def test_update_safe_when_nm_cb_attribute_missing(self):
        # Defensive guard: calling _update_nm_cb_state before _nm_cb
        # exists (or after it's been destroyed) is a no-op, not an
        # AttributeError.
        del self.tab._nm_cb
        # Must not raise.
        self.tab._update_nm_cb_state()

    # ---- _on_nm_cb_toggle ----

    def test_nm_cb_command_routes_through_on_nm_cb_toggle(self):
        # Wiring sentinel: the Checkbutton's command must route through
        # _on_nm_cb_toggle, NOT the pre-CS-70 direct _redraw binding.
        # We can't monkey-patch _on_nm_cb_toggle after the fact (Tk's
        # command callback closes over the original method object at
        # build time), so we spy on the two side effects
        # (_redraw + _notify_axis_link_state_change) and invoke the
        # widget. If both fire on a single ``.invoke()`` call, the
        # command MUST be _on_nm_cb_toggle — the pre-CS-70 binding only
        # fired _redraw.
        # Switch to cm-1 first so _nm_cb is NOT disabled (Tk widgets
        # in state=disabled don't fire commands on invoke).
        self.tab._x_unit.set("cm-1")
        self.tab._update_nm_cb_state()
        redraw_calls = [0]
        notify_calls = [0]
        original_redraw = self.tab._redraw
        original_notify = self.tab._notify_axis_link_state_change

        def _redraw_spy(*a, **kw):
            redraw_calls[0] += 1
            return original_redraw(*a, **kw)

        def _notify_spy(*a, **kw):
            notify_calls[0] += 1
            return original_notify(*a, **kw)
        self.tab._redraw = _redraw_spy  # type: ignore[method-assign]
        self.tab._notify_axis_link_state_change = _notify_spy  # type: ignore[method-assign]
        self.tab._nm_cb.invoke()
        self.assertEqual(
            redraw_calls[0], 1,
            "_nm_cb.invoke() must fire _redraw via _on_nm_cb_toggle",
        )
        self.assertEqual(
            notify_calls[0], 1,
            "_nm_cb.invoke() must fire _notify via _on_nm_cb_toggle "
            "(absent in the pre-CS-70 direct-redraw binding)",
        )

    def test_on_nm_cb_toggle_calls_redraw_and_notify(self):
        # Both side effects must fire. Spy on both.
        redraw_calls = [0]
        notify_calls = [0]
        original_redraw = self.tab._redraw
        original_notify = self.tab._notify_axis_link_state_change

        def _redraw_spy(*a, **kw):
            redraw_calls[0] += 1
            return original_redraw(*a, **kw)

        def _notify_spy(*a, **kw):
            notify_calls[0] += 1
            return original_notify(*a, **kw)
        self.tab._redraw = _redraw_spy  # type: ignore[method-assign]
        self.tab._notify_axis_link_state_change = _notify_spy  # type: ignore[method-assign]
        self.tab._on_nm_cb_toggle()
        self.assertEqual(redraw_calls[0], 1)
        self.assertEqual(notify_calls[0], 1)

    # ---- _notify_axis_link_state_change ----

    def test_notify_is_noop_when_no_dialog_open(self):
        # No dialog in _open_dialogs → call must be a silent no-op.
        self.psd._open_dialogs.clear()
        # Must not raise.
        self.tab._notify_axis_link_state_change()

    def test_notify_calls_refresh_on_open_dialog(self):
        # Open a real dialog and verify that the notification routes
        # to its refresh_axis_link_state method.
        dlg = self.psd.open_plot_config_dialog(
            self.tab, {}, secondary_x_linked=False,
        )
        try:
            calls = []
            original = dlg.refresh_axis_link_state

            def _spy(linked):
                calls.append(linked)
                return original(linked)
            dlg.refresh_axis_link_state = _spy  # type: ignore[method-assign]
            # Flip host into the linked state and notify.
            self.tab._x_unit.set("cm-1")
            self.tab._show_nm_axis.set(True)
            self.tab._notify_axis_link_state_change()
            self.assertEqual(calls, [True])
            # Flip back and notify again.
            self.tab._show_nm_axis.set(False)
            self.tab._notify_axis_link_state_change()
            self.assertEqual(calls, [True, False])
        finally:
            try:
                dlg.destroy()
            except Exception:
                pass

    def test_notify_uses_id_self_lookup(self):
        # The dialog registry is keyed by id(parent). Confirm the
        # notification only fires for the dialog whose parent IS this
        # tab — a dialog for an unrelated host must be left alone.
        other_host = tk.Frame(_root)
        other_host.pack()
        try:
            other_tab = self.UVVisTab(other_host, graph=ProjectGraph())
            try:
                self_dlg = self.psd.open_plot_config_dialog(
                    self.tab, {}, secondary_x_linked=False,
                )
                other_dlg = self.psd.open_plot_config_dialog(
                    other_tab, {}, secondary_x_linked=False,
                )
                self_calls = []
                other_calls = []
                original_self = self_dlg.refresh_axis_link_state
                original_other = other_dlg.refresh_axis_link_state

                def _spy_self(linked):
                    self_calls.append(linked)
                    return original_self(linked)

                def _spy_other(linked):
                    other_calls.append(linked)
                    return original_other(linked)
                self_dlg.refresh_axis_link_state = _spy_self  # type: ignore[method-assign]
                other_dlg.refresh_axis_link_state = _spy_other  # type: ignore[method-assign]
                # Flip this tab into linked, notify — only self_dlg fires.
                self.tab._x_unit.set("cm-1")
                self.tab._show_nm_axis.set(True)
                self.tab._notify_axis_link_state_change()
                self.assertEqual(self_calls, [True])
                self.assertEqual(other_calls, [])
            finally:
                try:
                    other_tab.destroy()
                except Exception:
                    pass
        finally:
            try:
                other_host.destroy()
            except Exception:
                pass

    # ---- end-to-end via _on_unit_change ----

    def test_on_unit_change_refreshes_dialog_greying(self):
        # Start in cm-1 + nm-axis ON (linked); open dialog → greyed.
        self.tab._x_unit.set("cm-1")
        self.tab._x_unit_prev = "cm-1"
        self.tab._show_nm_axis.set(True)
        dlg = self.psd.open_plot_config_dialog(
            self.tab, {},
            secondary_x_linked=self.tab._secondary_x_linked(),
        )
        try:
            dlg.update_idletasks()
            self.assertIs(dlg._secondary_x_linked, True)
            # Flip unit to nm via the toolbar Radiobutton path's
            # callback. _on_unit_change updates the gate (forces
            # _show_nm_axis False) then notifies the dialog.
            self.tab._x_unit.set("nm")
            self.tab._on_unit_change()
            dlg.update_idletasks()
            self.assertIs(dlg._secondary_x_linked, False)
            # Secondary X widgets should be un-greyed now.
            for key in ("range_lo", "range_hi", "autoscale"):
                w = dlg._axis_control_widgets[("secondary_x", key)]
                self.assertEqual(
                    str(w.cget("state")), "normal",
                    f"({key}) should be normal after unit→nm refresh",
                )
        finally:
            try:
                dlg.destroy()
            except Exception:
                pass

    def test_on_nm_cb_toggle_refreshes_dialog_greying(self):
        # Start in cm-1 + nm-axis OFF; open dialog (not linked, not
        # greyed). Toggle nm-axis ON via the Checkbutton command path
        # → dialog should flip into greyed state.
        self.tab._x_unit.set("cm-1")
        self.tab._x_unit_prev = "cm-1"
        self.tab._show_nm_axis.set(False)
        dlg = self.psd.open_plot_config_dialog(
            self.tab, {},
            secondary_x_linked=self.tab._secondary_x_linked(),
        )
        try:
            dlg.update_idletasks()
            self.assertIs(dlg._secondary_x_linked, False)
            # Toggle nm-axis ON and fire the command. (Setting the var
            # alone does NOT fire the command in Tk, so we call the
            # command directly — mirrors what tk would do on a user
            # click.)
            self.tab._show_nm_axis.set(True)
            self.tab._on_nm_cb_toggle()
            dlg.update_idletasks()
            self.assertIs(dlg._secondary_x_linked, True)
            for key in ("range_lo", "range_hi", "autoscale", "scale"):
                w = dlg._axis_control_widgets[("secondary_x", key)]
                self.assertEqual(
                    str(w.cget("state")), "disabled",
                    f"({key}) should be disabled after nm_cb toggle ON",
                )
        finally:
            try:
                dlg.destroy()
            except Exception:
                pass

    def test_on_unit_change_chains_update_then_notify_then_redraw(self):
        # Call order matters: gate update first (may flip
        # _show_nm_axis), then notify (so the dialog sees the freshly
        # computed link state), then redraw. Verify order via a single
        # event list.
        events = []
        original_update = self.tab._update_nm_cb_state
        original_notify = self.tab._notify_axis_link_state_change
        original_redraw = self.tab._redraw

        def _upd(*a, **kw):
            events.append("update")
            return original_update(*a, **kw)

        def _not(*a, **kw):
            events.append("notify")
            return original_notify(*a, **kw)

        def _red(*a, **kw):
            events.append("redraw")
            return original_redraw(*a, **kw)
        self.tab._update_nm_cb_state = _upd  # type: ignore[method-assign]
        self.tab._notify_axis_link_state_change = _not  # type: ignore[method-assign]
        self.tab._redraw = _red  # type: ignore[method-assign]
        self.tab._x_unit_prev = self.tab._x_unit.get()
        self.tab._on_unit_change()
        self.assertEqual(events, ["update", "notify", "redraw"])


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestCustomTicksRendererPhase4aq(unittest.TestCase):
    """Phase 4aq (CS-69) — ``custom_ticks`` renderer wiring.

    Non-empty ``cfg["axes"][<role>]["custom_ticks"]`` wins outright over
    ``tick_major`` on every per-axis role, applied as
    :class:`matplotlib.ticker.FixedLocator`. Empty / all-invalid falls
    through to ``tick_major`` :class:`MultipleLocator` (CS-65) or, if
    that's also empty, matplotlib's auto-locator. ``tick_minor`` is
    untouched by ``custom_ticks``.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str = "u1") -> None:
        wl = np.linspace(300, 600, 10)
        absorb = np.linspace(0.1, 0.9, 10)
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label=nid,
            state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))

    def test_custom_ticks_paint_fixed_locator_on_secondary_x(self):
        from matplotlib.ticker import FixedLocator
        self._add_uvvis()
        self.tab._x_unit.set("cm-1")
        self.tab._show_nm_axis.set(True)
        self.tab._plot_config["axes"] = {
            "secondary_x": {"custom_ticks": "300, 400, 500, 700, 900"},
        }
        self.tab._redraw()
        sec = self.tab._ax.child_axes[0]
        locator = sec.xaxis.get_major_locator()
        self.assertIsInstance(locator, FixedLocator)
        self.assertEqual(
            list(locator.tick_values(0, 0)),
            [300.0, 400.0, 500.0, 700.0, 900.0],
        )

    def test_custom_ticks_override_tick_major_on_secondary_x(self):
        # Both keys set: custom_ticks must win.
        from matplotlib.ticker import FixedLocator
        self._add_uvvis()
        self.tab._x_unit.set("cm-1")
        self.tab._show_nm_axis.set(True)
        self.tab._plot_config["axes"] = {
            "secondary_x": {
                "tick_major": "100",
                "custom_ticks": "300, 600",
            },
        }
        self.tab._redraw()
        sec = self.tab._ax.child_axes[0]
        locator = sec.xaxis.get_major_locator()
        self.assertIsInstance(locator, FixedLocator)
        self.assertEqual(list(locator.tick_values(0, 0)), [300.0, 600.0])

    def test_empty_custom_ticks_falls_through_to_tick_major(self):
        from matplotlib.ticker import MultipleLocator
        self._add_uvvis()
        self.tab._x_unit.set("cm-1")
        self.tab._show_nm_axis.set(True)
        self.tab._plot_config["axes"] = {
            "secondary_x": {"tick_major": "100", "custom_ticks": ""},
        }
        self.tab._redraw()
        sec = self.tab._ax.child_axes[0]
        locator = sec.xaxis.get_major_locator()
        self.assertIsInstance(locator, MultipleLocator)
        self.assertEqual(locator.view_limits(0, 100), (0.0, 100.0))

    def test_minor_locator_unaffected_by_custom_ticks(self):
        from matplotlib.ticker import FixedLocator, MultipleLocator
        self._add_uvvis()
        self.tab._x_unit.set("cm-1")
        self.tab._show_nm_axis.set(True)
        self.tab._plot_config["axes"] = {
            "secondary_x": {
                "custom_ticks": "300, 400, 500",
                "tick_minor": "10",
            },
        }
        self.tab._redraw()
        sec = self.tab._ax.child_axes[0]
        major = sec.xaxis.get_major_locator()
        minor = sec.xaxis.get_minor_locator()
        self.assertIsInstance(major, FixedLocator)
        self.assertIsInstance(minor, MultipleLocator)

    def test_custom_ticks_uniform_across_primary_x(self):
        # D6b lock: the schema key is uniform — non-empty custom_ticks
        # on primary_x also paints FixedLocator. The user only stated
        # the secondary X use case, but uniform contract makes future
        # use free.
        from matplotlib.ticker import FixedLocator
        self._add_uvvis()
        self.tab._plot_config["axes"] = {
            "primary_x": {"custom_ticks": "350, 450, 550"},
        }
        self.tab._redraw()
        locator = self.tab._ax.xaxis.get_major_locator()
        self.assertIsInstance(locator, FixedLocator)
        self.assertEqual(
            list(locator.tick_values(0, 0)),
            [350.0, 450.0, 550.0],
        )

    def test_all_invalid_custom_ticks_falls_through_to_auto(self):
        # All-invalid custom_ticks + empty tick_major → auto-locator.
        self._add_uvvis()
        self.tab._x_unit.set("cm-1")
        self.tab._show_nm_axis.set(True)
        self.tab._plot_config["axes"] = {
            "secondary_x": {
                "custom_ticks": "abc, xyz",
                "tick_major": "",
            },
        }
        # Just confirm no crash; renderer falls through to matplotlib's
        # default. The locator type is matplotlib-version-dependent
        # (AutoLocator on 3.x).
        self.tab._redraw()
        sec = self.tab._ax.child_axes[0]
        # Must NOT be FixedLocator or our user-specified MultipleLocator
        # (no tick_major to consume).
        from matplotlib.ticker import FixedLocator, MultipleLocator
        locator = sec.xaxis.get_major_locator()
        self.assertNotIsInstance(locator, FixedLocator)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabMoveToPickerPhase4al(unittest.TestCase):
    """Phase 4al — host wiring for the Plot Settings Move-to picker.

    The dialog passes ``(source_tab_role, label, target_tab_role)`` to
    the host; the host translates into the CS-50
    ``style["y_axis"]`` value and writes via ``graph.set_style``.
    Source role disambiguates label collisions across axes.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        import plot_settings_dialog
        cls.UVVisTab = UVVisTab
        cls.psd = plot_settings_dialog

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str, label: str, y_axis=None) -> DataNode:
        wl = np.linspace(300, 600, 10)
        absorb = np.linspace(0.1, 0.9, 10)
        style = {
            "color": "#1f77b4", "linestyle": "solid", "linewidth": 1.5,
            "alpha": 0.9, "visible": True, "in_legend": True,
            "fill": False, "fill_alpha": 0.08,
        }
        if y_axis is not None:
            style["y_axis"] = y_axis
        node = DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label=label,
            state=NodeState.COMMITTED,
            style=style,
        )
        self.graph.add_node(node)
        return node

    # ---- dialog threading ----

    def test_open_plot_settings_threads_on_route_plot_callback(self):
        self._add_uvvis("u1", "alpha")
        self.tab._open_plot_settings()
        dlg = self.psd._open_dialogs[id(self.tab)]
        dlg.update_idletasks()
        # The callback stored on the dialog must be the host's bound method.
        self.assertEqual(
            dlg._on_route_plot, self.tab._on_route_plot_from_dialog,
        )

    def test_double_click_threads_on_route_plot_callback(self):
        self._add_uvvis("u1", "alpha")
        self.tab._redraw()
        self.tab._fig.canvas.draw()
        from types import SimpleNamespace
        bbox = self.tab._ax.get_window_extent()
        cx = (bbox.x0 + bbox.x1) / 2.0
        ev = SimpleNamespace(x=cx, y=bbox.y0 - 2.0, dblclick=True)
        self.tab._on_mpl_axis_double_click(ev)
        dlg = self.psd._open_dialogs[id(self.tab)]
        dlg.update_idletasks()
        self.assertEqual(
            dlg._on_route_plot, self.tab._on_route_plot_from_dialog,
        )

    # ---- routing writes style["y_axis"] ----

    def test_route_writes_y_axis_style_via_set_style(self):
        self._add_uvvis("u1", "alpha")
        self.tab._on_route_plot_from_dialog(
            "primary_y", "alpha", "secondary_y",
        )
        node = self.graph.get_node("u1")
        self.assertEqual(node.style.get("y_axis"), "secondary")

    def test_route_to_default_clears_y_axis_override(self):
        # Start with an override; routing to Default (None) should
        # write style["y_axis"]=None so _resolve_y_axis_role falls
        # back to the per-NodeType default.
        self._add_uvvis("u1", "alpha", y_axis="tertiary")
        self.tab._on_route_plot_from_dialog(
            "tertiary_y", "alpha", None,
        )
        node = self.graph.get_node("u1")
        self.assertIsNone(node.style.get("y_axis"))

    def test_route_disambiguates_by_source_role(self):
        # Two visible nodes share label "twin": one on primary_y (UVVIS
        # default), one on secondary_y (style override). Picker on
        # primary_y → only the primary_y-routed node moves.
        self._add_uvvis("u_prim", "twin")  # primary_y by default
        self._add_uvvis("u_sec",  "twin", y_axis="secondary")
        self.tab._on_route_plot_from_dialog(
            "primary_y", "twin", "tertiary_y",
        )
        prim = self.graph.get_node("u_prim")
        sec = self.graph.get_node("u_sec")
        self.assertEqual(prim.style.get("y_axis"), "tertiary")
        self.assertEqual(sec.style.get("y_axis"), "secondary")

    def test_route_unknown_label_is_silent_noop(self):
        self._add_uvvis("u1", "alpha")
        # No exception; no style change on the existing node.
        self.tab._on_route_plot_from_dialog(
            "primary_y", "no_such_label", "secondary_y",
        )
        node = self.graph.get_node("u1")
        self.assertIsNone(node.style.get("y_axis"))

    def test_route_skips_invisible_nodes(self):
        # An invisible node with a matching label must not be routed —
        # the picker's listbox only shows visible plots, so the host
        # must filter consistently.
        node = self._add_uvvis("u1", "alpha")
        node.style["visible"] = False
        self.tab._on_route_plot_from_dialog(
            "primary_y", "alpha", "secondary_y",
        )
        self.assertIsNone(node.style.get("y_axis"))

    def test_route_unknown_source_tab_is_silent_noop(self):
        # Defensive guard: a malformed source_tab_role (not in
        # _Y_AXIS_ROLE_TO_TAB's values) is ignored.
        self._add_uvvis("u1", "alpha")
        self.tab._on_route_plot_from_dialog(
            "global", "alpha", "secondary_y",
        )
        node = self.graph.get_node("u1")
        self.assertIsNone(node.style.get("y_axis"))

    # ---- end-to-end through the renderer ----

    def test_route_triggers_redraw_via_graph_event(self):
        # set_style fires NODE_STYLE_CHANGED; the tab's subscription
        # consumes it and calls _redraw. After routing, the resolver
        # should report the new role.
        from uvvis_tab import _resolve_y_axis_role
        node = self._add_uvvis("u1", "alpha")
        # Sanity: default routing is primary for UVVIS.
        self.assertEqual(
            _resolve_y_axis_role(node.type, node.style), "primary",
        )
        self.tab._on_route_plot_from_dialog(
            "primary_y", "alpha", "secondary_y",
        )
        # Re-fetch the node — set_style returns a NEW DataNode (CS-04
        # immutability), so the local ``node`` reference is stale.
        fresh = self.graph.get_node("u1")
        self.assertEqual(
            _resolve_y_axis_role(fresh.type, fresh.style), "secondary",
        )


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabBaseline(unittest.TestCase):
    """Phase 4c — UV/Vis baseline correction (CS-15).

    Covers the left-panel chrome and the Apply gesture's
    materialisation of a provisional ``BASELINE`` OperationNode +
    DataNode pair. The ScanTreeWidget integration (provisional
    indicator, commit, discard) is exercised through the existing
    public API.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str = "u1") -> str:
        wl = np.linspace(200.0, 800.0, 601)
        peak = np.exp(-((wl - 500.0) / 25.5) ** 2)
        bg = 0.10 + 0.0005 * wl
        absorb = peak + bg
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"x_unit": "nm", "y_unit": "absorbance",
                      "instrument": "synthetic",
                      "source_file": f"syn_{nid}"},
            label=nid, state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))
        return nid

    # ---- left panel chrome -----------------------------------------

    def test_left_panel_exists(self):
        self.assertTrue(hasattr(self.tab, "_baseline_mode"))
        self.assertTrue(hasattr(self.tab, "_baseline_mode_cb"))
        # Phase 4k (CS-22): a single shared subject combobox at the
        # top of the left pane replaces the per-section "Spectrum:"
        # rows. ``_baseline_subject_cb`` is gone.
        self.assertTrue(hasattr(self.tab, "_shared_subject_cb"))
        self.assertTrue(hasattr(self.tab, "_shared_subject"))
        self.assertFalse(hasattr(self.tab, "_baseline_subject_cb"))
        self.assertTrue(hasattr(self.tab, "_apply_baseline_btn"))
        # All six modes are exposed on the combobox (CS-38 added
        # ``scattering+offset``).
        values = self.tab._baseline_mode_cb.cget("values")
        # Tk returns either a tuple or a string of space-separated names.
        if isinstance(values, str):
            values = tuple(values.split())
        self.assertEqual(
            tuple(values),
            ("linear", "polynomial", "spline", "rubberband",
             "scattering", "scattering+offset"),
        )
        # CS-24 (Phase 4m) scattering mode Tk vars exist on the tab.
        self.assertTrue(hasattr(self.tab, "_baseline_scattering_n"))
        self.assertTrue(hasattr(self.tab, "_baseline_scattering_fit_n"))
        self.assertTrue(hasattr(self.tab, "_baseline_scattering_fit_lo"))
        self.assertTrue(hasattr(self.tab, "_baseline_scattering_fit_hi"))
        # Default n is "4" (Rayleigh); fit-n checkbox starts unchecked.
        self.assertEqual(self.tab._baseline_scattering_n.get(), "4")
        self.assertFalse(self.tab._baseline_scattering_fit_n.get())

    def test_mode_change_swaps_parameter_rows(self):
        # Linear mode → 2 anchor entries; polynomial mode → spinbox +
        # 2 fit-window entries (3 rows); spline mode → 1 entry;
        # rubberband mode → "no parameters" label only.
        self.tab._baseline_mode.set("linear")
        self.tab.update_idletasks()
        linear_count = len(self.tab._baseline_params_frame.winfo_children())

        self.tab._baseline_mode.set("polynomial")
        self.tab.update_idletasks()
        poly_count = len(self.tab._baseline_params_frame.winfo_children())

        self.tab._baseline_mode.set("spline")
        self.tab.update_idletasks()
        spline_count = len(self.tab._baseline_params_frame.winfo_children())

        self.tab._baseline_mode.set("rubberband")
        self.tab.update_idletasks()
        rb_count = len(self.tab._baseline_params_frame.winfo_children())

        self.tab._baseline_mode.set("scattering")
        self.tab.update_idletasks()
        scatter_count = len(self.tab._baseline_params_frame.winfo_children())

        # Each mode rebuilds the frame; counts differ between modes.
        self.assertGreater(linear_count, 0)
        self.assertGreater(poly_count, linear_count,
                           "polynomial has more rows than linear")
        self.assertGreater(spline_count, 0)
        self.assertEqual(rb_count, 1,
                         "rubberband shows only the 'no parameters' label")
        # Scattering: 3 rows (n+checkbox / fit lo / fit hi).
        self.assertEqual(scatter_count, 3,
                         "scattering shows n+fit-n + fit lo + fit hi rows")

    # ---- Apply materialises provisional pair -----------------------

    def test_apply_creates_provisional_op_and_data_node(self):
        self._add_uvvis("u1")
        # Pick the freshly-loaded subject in the combobox.
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertTrue(len(items) >= 1, "subject combobox should list u1")
        self.tab._shared_subject.set(items[0])

        self.tab._baseline_mode.set("linear")
        self.tab._baseline_anchor_lo.set("200")
        self.tab._baseline_anchor_hi.set("800")

        n_before = len(self.graph.nodes)
        op_id, out_id = self.tab._apply_baseline()
        n_after = len(self.graph.nodes)
        self.assertEqual(n_after - n_before, 2,
                         "Apply must add exactly one op + one data node")

        op = self.graph.get_node(op_id)
        out = self.graph.get_node(out_id)
        self.assertIsInstance(op, OperationNode)
        self.assertEqual(op.type, OperationType.BASELINE)
        self.assertEqual(op.engine, "internal")
        self.assertEqual(op.state, NodeState.PROVISIONAL)
        # Params completeness — mode + sub-schema for linear.
        self.assertEqual(op.params["mode"], "linear")
        self.assertAlmostEqual(op.params["anchor_lo_nm"], 200.0)
        self.assertAlmostEqual(op.params["anchor_hi_nm"], 800.0)

        self.assertIsInstance(out, DataNode)
        self.assertEqual(out.type, NodeType.BASELINE)
        self.assertEqual(out.state, NodeState.PROVISIONAL)
        self.assertIn("wavelength_nm", out.arrays)
        self.assertIn("absorbance", out.arrays)
        # Edges parent → op → out.
        self.assertEqual(self.graph.parents_of(op_id), ["u1"])
        self.assertEqual(self.graph.children_of(op_id), [out_id])

    def test_apply_corrected_data_recovers_unit_peak_height(self):
        # End-to-end sanity: with anchors at the spectrum extremes,
        # the corrected absorbance peak ≈ 1.0 (the synthetic Gaussian
        # height) within tolerance.
        self._add_uvvis("u1")
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._shared_subject.set(items[0])
        self.tab._baseline_mode.set("linear")
        self.tab._baseline_anchor_lo.set("200")
        self.tab._baseline_anchor_hi.set("800")

        _, out_id = self.tab._apply_baseline()
        out = self.graph.get_node(out_id)
        self.assertAlmostEqual(float(out.arrays["absorbance"].max()),
                               1.0, places=4)

    def _add_uvvis_scattering_bg(self, nid: str = "us1") -> str:
        """UVVIS spectrum with a Rayleigh-like (c·λ^-4) background."""
        wl = np.linspace(200.0, 800.0, 601)
        peak = np.exp(-((wl - 500.0) / 25.5) ** 2)
        bg = 1e8 * wl ** (-4)
        absorb = peak + bg
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"x_unit": "nm", "y_unit": "absorbance",
                      "instrument": "synthetic-scattering",
                      "source_file": f"syn_{nid}"},
            label=nid, state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))
        return nid

    def test_apply_scattering_fixed_n_recovers_unit_peak(self):
        # CS-24: scattering mode with n=4 (Rayleigh) over a peak-free
        # window subtracts the c·λ^-4 background almost exactly.
        self._add_uvvis_scattering_bg("us1")
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._shared_subject.set(items[0])
        self.tab._baseline_mode.set("scattering")
        self.tab._baseline_scattering_n.set("4")
        self.tab._baseline_scattering_fit_n.set(False)
        self.tab._baseline_scattering_fit_lo.set("200")
        self.tab._baseline_scattering_fit_hi.set("350")

        op_id, out_id = self.tab._apply_baseline()
        op = self.graph.get_node(op_id)
        out = self.graph.get_node(out_id)
        self.assertEqual(op.type, OperationType.BASELINE)
        self.assertEqual(op.params["mode"], "scattering")
        # Numeric n flows through as a float (CS-03 verbatim capture).
        self.assertAlmostEqual(op.params["n"], 4.0)
        self.assertAlmostEqual(op.params["fit_lo_nm"], 200.0)
        self.assertAlmostEqual(op.params["fit_hi_nm"], 350.0)
        self.assertEqual(out.type, NodeType.BASELINE)
        self.assertAlmostEqual(float(out.arrays["absorbance"].max()),
                               1.0, places=4)

    def test_apply_scattering_fit_n_records_string_in_params(self):
        # CS-24: when "Fit n" is checked, params["n"] is the string
        # "fit" — the helper recovers n alongside c.
        self._add_uvvis_scattering_bg("us1")
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._shared_subject.set(items[0])
        self.tab._baseline_mode.set("scattering")
        self.tab._baseline_scattering_fit_n.set(True)
        self.tab._baseline_scattering_fit_lo.set("200")
        self.tab._baseline_scattering_fit_hi.set("350")

        op_id, out_id = self.tab._apply_baseline()
        op = self.graph.get_node(op_id)
        # The discriminator (n="fit") is preserved verbatim per CS-03,
        # so a re-run from the captured params reproduces the result.
        self.assertEqual(op.params["mode"], "scattering")
        self.assertEqual(op.params["n"], "fit")
        out = self.graph.get_node(out_id)
        self.assertAlmostEqual(float(out.arrays["absorbance"].max()),
                               1.0, places=3)

    # ---- ScanTreeWidget integration --------------------------------

    def test_provisional_baseline_appears_in_sidebar(self):
        self._add_uvvis("u1")
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._shared_subject.set(items[0])
        self.tab._baseline_mode.set("rubberband")
        _, out_id = self.tab._apply_baseline()
        self.tab._scan_tree.update_idletasks()

        # The new BASELINE node owns a row in the right sidebar.
        self.assertIn(out_id, self.tab._scan_tree._row_frames)

        # That row's leftmost label is the provisional indicator (⋯).
        row = self.tab._scan_tree._row_frames[out_id]
        first_label = next(
            (w for w in row.winfo_children() if isinstance(w, tk.Label)),
            None,
        )
        self.assertIsNotNone(first_label)
        self.assertEqual(first_label.cget("text"), "⋯")

    def test_commit_promotes_baseline_state(self):
        self._add_uvvis("u1")
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._shared_subject.set(items[0])
        self.tab._baseline_mode.set("rubberband")
        _, out_id = self.tab._apply_baseline()

        # Commit through the public graph API (the widget's
        # right-click menu also calls graph.commit_node).
        self.graph.commit_node(out_id)
        self.assertEqual(self.graph.get_node(out_id).state,
                         NodeState.COMMITTED)
        self.tab._scan_tree.update_idletasks()
        # State indicator now shows committed.
        row = self.tab._scan_tree._row_frames[out_id]
        first_label = next(
            (w for w in row.winfo_children() if isinstance(w, tk.Label)),
            None,
        )
        self.assertIsNotNone(first_label)
        self.assertEqual(first_label.cget("text"), "🔒")

    def test_discard_removes_baseline_from_plot(self):
        self._add_uvvis("u1")
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._shared_subject.set(items[0])
        self.tab._baseline_mode.set("rubberband")
        _, out_id = self.tab._apply_baseline()
        self.tab.update_idletasks()

        # Two lines: the parent UVVIS + the new provisional BASELINE.
        self.assertEqual(len(self.tab._ax.get_lines()), 2)

        self.graph.discard_node(out_id)
        self.tab.update_idletasks()
        # Only the parent UVVIS remains.
        lines = self.tab._ax.get_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].get_label(), "u1")

    def test_subject_combobox_updates_when_baseline_added(self):
        # After Apply, the new BASELINE node is a candidate subject
        # itself (chained baseline correction is allowed).
        self._add_uvvis("u1")
        items_before = self.tab._shared_subject_cb.cget("values")
        if isinstance(items_before, str):
            items_before = tuple(items_before.split())
        self.assertEqual(len(items_before), 1)

        self.tab._shared_subject.set(items_before[0])
        self.tab._baseline_mode.set("rubberband")
        self.tab._apply_baseline()
        self.tab.update_idletasks()

        items_after = self.tab._shared_subject_cb.cget("values")
        if isinstance(items_after, str):
            items_after = tuple(items_after.split())
        self.assertEqual(len(items_after), 2,
                         "subject list should now include the BASELINE node")

    # ---- Phase 4ac (CS-54): identical re-apply creates a new sibling ----

    def test_apply_baseline_identical_re_apply_creates_new_sibling(self):
        # Phase 4ac (CS-54) dropped CS-31's dedup gate. Two clicks
        # with identical params now produce TWO PROVISIONAL BASELINE
        # OperationNodes, each owning a fresh DataNode child. This
        # is the workflow the user flagged: re-applying a process
        # you tweaked once must not be silently blocked.
        self._add_uvvis("u1")
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._shared_subject.set(items[0])
        self.tab._baseline_mode.set("linear")
        self.tab._baseline_anchor_lo.set("200")
        self.tab._baseline_anchor_hi.set("800")

        first = self.tab._apply_baseline()
        self.assertIsNotNone(first)
        n_after_first = len(self.graph.nodes)

        second = self.tab._apply_baseline()
        self.assertIsNotNone(
            second, "identical re-apply must NOT be blocked",
        )
        self.assertEqual(
            len(self.graph.nodes), n_after_first + 2,
            "identical re-apply must add one op + one data node",
        )
        # No "already applied" status spam — the dedup status branch
        # is gone with the gate.
        self.assertNotIn(
            "already", str(self.tab._status_lbl.cget("text")),
        )

    def test_apply_baseline_with_different_params_creates_new_node(self):
        self._add_uvvis("u1")
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._shared_subject.set(items[0])
        self.tab._baseline_mode.set("linear")
        self.tab._baseline_anchor_lo.set("200")
        self.tab._baseline_anchor_hi.set("800")
        self.assertIsNotNone(self.tab._apply_baseline())
        n_after_first = len(self.graph.nodes)

        # Tweak anchor_lo and re-apply — different params, so a real
        # second BASELINE node IS created.
        self.tab._baseline_anchor_lo.set("220")
        self.assertIsNotNone(self.tab._apply_baseline())
        self.assertEqual(len(self.graph.nodes), n_after_first + 2)

    # ---- Phase 4s — floor-zero, scattering+offset, fit persistence ----

    def test_baseline_floor_zero_toggle_exists_and_defaults_off(self):
        # CS-37 — universal "Floor at zero" Checkbutton at the top of
        # the baseline section, bound to a ``tk.BooleanVar`` that
        # defaults to False.
        self.assertTrue(hasattr(self.tab, "_baseline_floor_zero"))
        self.assertTrue(hasattr(self.tab, "_baseline_floor_zero_cb"))
        self.assertFalse(self.tab._baseline_floor_zero.get())
        self.assertEqual(self.tab._baseline_floor_zero_cb.cget("text"),
                         "Floor at zero")

    def test_apply_baseline_writes_floor_zero_into_params(self):
        # CS-37 — every mode's apply path round-trips the toggle state
        # into ``params["floor_zero"]`` on the OperationNode.
        self._add_uvvis("u1")
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._shared_subject.set(items[0])
        self.tab._baseline_mode.set("linear")
        self.tab._baseline_anchor_lo.set("200")
        self.tab._baseline_anchor_hi.set("800")

        # Default (False) → params records False.
        op_id, _ = self.tab._apply_baseline()
        op = self.graph.get_node(op_id)
        self.assertIn("floor_zero", op.params)
        self.assertFalse(op.params["floor_zero"])

    def test_apply_baseline_linear_with_floor_zero_creates_baseline_node(self):
        # Phase 4t (CS-37 expansion) — linear floor-zero ships in this
        # phase. Replaces the Phase 4s "raises a clear ValueError"
        # contract with the new "constrained-fit succeeds and the op
        # records floor_zero=True" contract.
        self._add_uvvis("u1")
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._shared_subject.set(items[0])
        self.tab._baseline_mode.set("linear")
        self.tab._baseline_anchor_lo.set("200")
        self.tab._baseline_anchor_hi.set("800")
        self.tab._baseline_floor_zero.set(True)

        n_before = len(self.graph.nodes)
        result = self.tab._apply_baseline()
        self.assertIsNotNone(result, "linear floor-zero apply must succeed now")
        self.assertEqual(len(self.graph.nodes), n_before + 2,
                         "apply creates op + BASELINE data node")
        # The op records floor_zero=True for the persistence-umbrella
        # round-trip.
        op_ids = [
            nid for nid, n in self.graph.nodes.items()
            if isinstance(n, OperationNode)
            and n.params.get("mode") == "linear"
        ]
        self.assertEqual(len(op_ids), 1)
        op = self.graph.nodes[op_ids[0]]
        self.assertTrue(op.params["floor_zero"])

    def test_apply_baseline_polynomial_with_floor_zero_creates_baseline_node(self):
        # Phase 4t (CS-37 expansion) — polynomial floor-zero ships.
        # Mirror coverage of the linear test on the polynomial mode so
        # the SLSQP-with-z-space-conditioning path is exercised at the
        # apply integration site.
        self._add_uvvis("u1")
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._shared_subject.set(items[0])
        self.tab._baseline_mode.set("polynomial")
        self.tab._baseline_poly_order.set(2)
        self.tab._baseline_fit_lo.set("200")
        self.tab._baseline_fit_hi.set("800")
        self.tab._baseline_floor_zero.set(True)

        n_before = len(self.graph.nodes)
        result = self.tab._apply_baseline()
        self.assertIsNotNone(result, "polynomial floor-zero apply must succeed")
        self.assertEqual(len(self.graph.nodes), n_before + 2)
        op_ids = [
            nid for nid, n in self.graph.nodes.items()
            if isinstance(n, OperationNode)
            and n.params.get("mode") == "polynomial"
        ]
        self.assertEqual(len(op_ids), 1)
        self.assertTrue(self.graph.nodes[op_ids[0]].params["floor_zero"])

    def test_apply_baseline_spline_with_floor_zero_creates_baseline_node(self):
        # Phase 4t (CS-37 expansion) — spline floor-zero ships.
        # Anchors in the wings of the synthetic Gaussian peak.
        self._add_uvvis("u1")
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._shared_subject.set(items[0])
        self.tab._baseline_mode.set("spline")
        self.tab._baseline_spline_anchors.set("220, 280, 720, 780")
        self.tab._baseline_floor_zero.set(True)

        n_before = len(self.graph.nodes)
        result = self.tab._apply_baseline()
        self.assertIsNotNone(result, "spline floor-zero apply must succeed")
        self.assertEqual(len(self.graph.nodes), n_before + 2)
        op_ids = [
            nid for nid, n in self.graph.nodes.items()
            if isinstance(n, OperationNode)
            and n.params.get("mode") == "spline"
        ]
        self.assertEqual(len(op_ids), 1)
        self.assertTrue(self.graph.nodes[op_ids[0]].params["floor_zero"])

    def test_floor_zero_checkbutton_is_enabled_for_supported_modes(self):
        # CS-43 — every mode in BASELINE_MODES is in
        # _FLOOR_ZERO_SUPPORTED_MODES this session, so flipping through
        # all six modes leaves the checkbutton state="normal" each
        # time and the tooltip text empty.
        import uvvis_tab as _ut
        import uvvis_baseline as _ub
        self.assertSetEqual(
            set(_ut._FLOOR_ZERO_SUPPORTED_MODES),
            set(_ub.BASELINE_MODES),
        )
        for mode in _ub.BASELINE_MODES:
            self.tab._baseline_mode.set(mode)
            self.tab.update_idletasks()
            self.assertEqual(
                str(self.tab._baseline_floor_zero_cb.cget("state")),
                "normal",
                f"floor-zero toggle should be enabled for mode {mode!r}",
            )
            self.assertEqual(
                self.tab._baseline_floor_zero_tooltip._text, "",
                f"tooltip text should be empty for mode {mode!r}",
            )

    def test_floor_zero_checkbutton_disables_for_unsupported_mode(self):
        # CS-43 — the disabled-state branch is defensive scaffolding
        # since today every BASELINE_MODES entry is supported. Force
        # the supported set to exclude the current mode and confirm
        # _refresh_floor_zero_state flips the Checkbutton state and
        # rotates the tooltip text. Using monkey-patch rather than
        # editing the module-level constant keeps the test isolated.
        import uvvis_tab as _ut
        original = _ut._FLOOR_ZERO_SUPPORTED_MODES
        try:
            _ut._FLOOR_ZERO_SUPPORTED_MODES = frozenset()
            self.tab._refresh_floor_zero_state()
            self.assertEqual(
                str(self.tab._baseline_floor_zero_cb.cget("state")),
                "disabled",
            )
            self.assertEqual(
                self.tab._baseline_floor_zero_tooltip._text,
                _ut._FLOOR_ZERO_DISABLED_TOOLTIP,
            )
        finally:
            _ut._FLOOR_ZERO_SUPPORTED_MODES = original
            self.tab._refresh_floor_zero_state()

    def test_floor_zero_disabled_state_preserves_var_value(self):
        # CS-43 design lock — disabling the checkbutton must NOT clear
        # the BooleanVar (the persistence-umbrella round-trip carries
        # the user's choice forward across mode flips).
        import uvvis_tab as _ut
        self.tab._baseline_floor_zero.set(True)
        original = _ut._FLOOR_ZERO_SUPPORTED_MODES
        try:
            _ut._FLOOR_ZERO_SUPPORTED_MODES = frozenset()
            self.tab._refresh_floor_zero_state()
            self.assertTrue(self.tab._baseline_floor_zero.get())
        finally:
            _ut._FLOOR_ZERO_SUPPORTED_MODES = original
            self.tab._refresh_floor_zero_state()

    def test_floor_zero_tooltip_constructed_at_panel_build(self):
        # CS-42 — the Tooltip on _baseline_floor_zero_cb is built at
        # init time and stored on the tab so _refresh_floor_zero_state
        # can rotate the text in place. Simple existence + binding
        # presence assertion (the actual Toplevel display is timing-
        # dependent and outside the scope of this test).
        from tooltip import Tooltip
        self.assertIsInstance(
            self.tab._baseline_floor_zero_tooltip, Tooltip,
        )
        self.assertIs(
            self.tab._baseline_floor_zero_tooltip._widget,
            self.tab._baseline_floor_zero_cb,
        )

    def test_scattering_offset_mode_swaps_parameter_rows(self):
        # CS-38 — selecting scattering+offset reuses scattering's row
        # layout (3 rows: n+fit-n / fit lo / fit hi).
        self.tab._baseline_mode.set("scattering+offset")
        self.tab.update_idletasks()
        count = len(self.tab._baseline_params_frame.winfo_children())
        self.assertEqual(count, 3,
                         "scattering+offset shows the same 3 rows as scattering")

    def test_apply_scattering_offset_creates_baseline_node(self):
        # CS-38 — applying scattering+offset materialises the same op +
        # data pair shape as scattering, with mode discriminator
        # ``"scattering+offset"``.
        self._add_uvvis("u1")
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._shared_subject.set(items[0])
        self.tab._baseline_mode.set("scattering+offset")
        self.tab._baseline_scattering_n.set("4")
        self.tab._baseline_scattering_fit_lo.set("200")
        self.tab._baseline_scattering_fit_hi.set("350")

        op_id, out_id = self.tab._apply_baseline()
        op = self.graph.get_node(op_id)
        out = self.graph.get_node(out_id)
        self.assertEqual(op.params["mode"], "scattering+offset")
        self.assertEqual(out.type, NodeType.BASELINE)

    def test_scattering_n_fit_persists_n_fitted_and_c_fitted(self):
        # CS-39 — applying scattering with n="fit" writes c_fitted +
        # n_fitted into params on the OperationNode.
        self._add_uvvis("u1")
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._shared_subject.set(items[0])
        self.tab._baseline_mode.set("scattering")
        self.tab._baseline_scattering_fit_n.set(True)
        self.tab._baseline_scattering_fit_lo.set("200")
        self.tab._baseline_scattering_fit_hi.set("350")

        op_id, _ = self.tab._apply_baseline()
        op = self.graph.get_node(op_id)
        self.assertEqual(op.params["n"], "fit")
        self.assertIn("c_fitted", op.params)
        self.assertIn("n_fitted", op.params)
        self.assertIsInstance(op.params["c_fitted"], float)
        self.assertIsInstance(op.params["n_fitted"], float)

    def test_scattering_fixed_n_persists_c_fitted_only(self):
        # CS-39 — fixed n: ``n_fitted`` is NOT recorded (the
        # diagnostic is meaningful only when the fit recovered n).
        self._add_uvvis("u1")
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._shared_subject.set(items[0])
        self.tab._baseline_mode.set("scattering")
        self.tab._baseline_scattering_fit_n.set(False)
        self.tab._baseline_scattering_n.set("4")
        self.tab._baseline_scattering_fit_lo.set("200")
        self.tab._baseline_scattering_fit_hi.set("350")

        op_id, _ = self.tab._apply_baseline()
        op = self.graph.get_node(op_id)
        self.assertIn("c_fitted", op.params)
        self.assertNotIn("n_fitted", op.params)

    def test_scattering_offset_persists_a_fitted(self):
        # CS-39 — scattering+offset always records a_fitted +
        # c_fitted (additive offset is always fitted).
        self._add_uvvis("u1")
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._shared_subject.set(items[0])
        self.tab._baseline_mode.set("scattering+offset")
        self.tab._baseline_scattering_fit_n.set(False)
        self.tab._baseline_scattering_n.set("4")
        self.tab._baseline_scattering_fit_lo.set("200")
        self.tab._baseline_scattering_fit_hi.set("350")

        op_id, _ = self.tab._apply_baseline()
        op = self.graph.get_node(op_id)
        self.assertIn("a_fitted", op.params)
        self.assertIn("c_fitted", op.params)
        self.assertNotIn("n_fitted", op.params)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabNormalisationIntegration(unittest.TestCase):
    """Phase 4e — NORMALISED nodes are first-class spectra in the tab.

    Replaces TestUVVisTabBugB003 (the legacy Norm: combobox is gone;
    its draw-time ``_y_with_norm`` transform retired with it). The
    Phase 4c regressions it pinned (np.trapz / descending-nm sign
    flip) live on as unit tests against ``uvvis_normalise.compute_*``
    in test_uvvis_normalise.py — the integration concern here is
    that NORMALISED nodes flow through the tab's render path and
    sidebar like UVVIS / BASELINE.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str = "u1") -> None:
        wl = np.linspace(200.0, 800.0, 601)
        absorb = np.exp(-((wl - 500.0) / 50.0) ** 2) + 0.05
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "syn"},
            label=nid, state=NodeState.COMMITTED,
            style={"color": "#111", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))

    def _select_first_norm_subject(self):
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertGreaterEqual(len(items), 1)
        self.tab._shared_subject.set(items[0])

    def test_panel_present_and_unit_selector_has_no_norm_combobox(self):
        # The legacy ``_norm_mode`` Tk var and ``_y_with_norm`` method
        # are retired; the new panel is wired into the left pane.
        self.assertFalse(hasattr(self.tab, "_norm_mode"))
        self.assertFalse(hasattr(self.tab, "_y_with_norm"))
        self.assertTrue(hasattr(self.tab, "_normalisation_panel"))

    def test_normalised_node_renders_in_redraw(self):
        # Apply normalisation through the panel; the resulting
        # NORMALISED node must show up as a second matplotlib line on
        # the next redraw (parent UVVIS + child NORMALISED).
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_norm_subject()
        self.tab._normalisation_panel._mode_var.set("peak")
        self.tab._normalisation_panel._window_lo.set("200")
        self.tab._normalisation_panel._window_hi.set("800")
        self.tab._normalisation_panel._apply()
        self.tab.update_idletasks()
        self.assertEqual(len(self.tab._ax.get_lines()), 2)

    def test_xlim_entries_apply_with_normalised_node_present(self):
        # The legacy B-003 regression was about ``_y_with_norm``
        # raising inside the ``<Return>`` callback so X-limit entries
        # silently failed to apply. The transform is gone, but the
        # equivalent integration check — X-limit entries land
        # correctly when a NORMALISED node is in the graph — is
        # worth pinning.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_norm_subject()
        self.tab._normalisation_panel._mode_var.set("area")
        self.tab._normalisation_panel._window_lo.set("200")
        self.tab._normalisation_panel._window_hi.set("800")
        self.tab._normalisation_panel._apply()
        self.tab._xlim_lo.set("300")
        self.tab._xlim_hi.set("700")
        self.tab._redraw()
        # nm axis is rendered descending, so x-limits land as (hi, lo).
        x0, x1 = self.tab._ax.get_xlim()
        self.assertAlmostEqual(x0, 700.0)
        self.assertAlmostEqual(x1, 300.0)

    def test_normalised_node_has_sidebar_row(self):
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_norm_subject()
        self.tab._normalisation_panel._mode_var.set("peak")
        self.tab._normalisation_panel._window_lo.set("200")
        self.tab._normalisation_panel._window_hi.set("800")
        _, out_id = self.tab._normalisation_panel._apply()
        self.tab._scan_tree.update_idletasks()
        # The new NORMALISED node owns a row in the right sidebar
        # (the sidebar filter widened from [UVVIS, BASELINE] to
        # [UVVIS, BASELINE, NORMALISED] in Phase 4e Part E).
        self.assertIn(out_id, self.tab._scan_tree._row_frames)

    def test_discard_removes_normalised_from_plot(self):
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_norm_subject()
        self.tab._normalisation_panel._mode_var.set("peak")
        self.tab._normalisation_panel._window_lo.set("200")
        self.tab._normalisation_panel._window_hi.set("800")
        _, out_id = self.tab._normalisation_panel._apply()
        self.tab.update_idletasks()
        self.assertEqual(len(self.tab._ax.get_lines()), 2)
        self.graph.discard_node(out_id)
        self.tab.update_idletasks()
        lines = self.tab._ax.get_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].get_label(), "u1")


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabSmoothingIntegration(unittest.TestCase):
    """Phase 4g — SMOOTHED nodes are first-class spectra in the tab.

    Mirrors TestUVVisTabNormalisationIntegration (Phase 4e). The pure
    SmoothingPanel mechanics are pinned in test_uvvis_smoothing.py;
    here we only check that the panel is wired into the tab and that
    SMOOTHED nodes flow through the render path and the right
    sidebar like UVVIS / BASELINE / NORMALISED.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str = "u1") -> None:
        wl = np.linspace(200.0, 800.0, 601)
        absorb = np.exp(-((wl - 500.0) / 50.0) ** 2) + 0.05
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "syn"},
            label=nid, state=NodeState.COMMITTED,
            style={"color": "#111", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))

    def _select_first_smooth_subject(self):
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertGreaterEqual(len(items), 1)
        self.tab._shared_subject.set(items[0])

    def test_panel_present_in_left_pane(self):
        self.assertTrue(hasattr(self.tab, "_smoothing_panel"))

    def test_smoothed_node_renders_in_redraw(self):
        # Apply smoothing through the panel; the resulting SMOOTHED
        # node must show up as a second matplotlib line on the next
        # redraw (parent UVVIS + child SMOOTHED).
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_smooth_subject()
        self.tab._smoothing_panel._mode_var.set("savgol")
        self.tab._smoothing_panel._window_length.set(11)
        self.tab._smoothing_panel._polyorder.set(2)
        self.tab._smoothing_panel._apply()
        self.tab.update_idletasks()
        self.assertEqual(len(self.tab._ax.get_lines()), 2)

    def test_smoothed_node_has_sidebar_row(self):
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_smooth_subject()
        self.tab._smoothing_panel._mode_var.set("moving_avg")
        self.tab._smoothing_panel._window_length.set(7)
        _, out_id = self.tab._smoothing_panel._apply()
        self.tab._scan_tree.update_idletasks()
        # The new SMOOTHED node owns a row in the right sidebar (the
        # sidebar filter widened from [UVVIS, BASELINE, NORMALISED]
        # to [UVVIS, BASELINE, NORMALISED, SMOOTHED] in Phase 4g).
        self.assertIn(out_id, self.tab._scan_tree._row_frames)

    def test_discard_removes_smoothed_from_plot(self):
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_smooth_subject()
        self.tab._smoothing_panel._mode_var.set("savgol")
        self.tab._smoothing_panel._window_length.set(5)
        self.tab._smoothing_panel._polyorder.set(2)
        _, out_id = self.tab._smoothing_panel._apply()
        self.tab.update_idletasks()
        self.assertEqual(len(self.tab._ax.get_lines()), 2)
        self.graph.discard_node(out_id)
        self.tab.update_idletasks()
        lines = self.tab._ax.get_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].get_label(), "u1")

    def test_smoothed_appears_in_shared_subject_list(self):
        # The shared subject combobox (CS-22, Phase 4k) iterates
        # _spectrum_nodes — UVVIS / BASELINE / NORMALISED / SMOOTHED
        # — so a freshly-Applied SMOOTHED node is itself a candidate
        # subject for downstream ops.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_smooth_subject()
        self.tab._smoothing_panel._mode_var.set("savgol")
        self.tab._smoothing_panel._window_length.set(5)
        self.tab._smoothing_panel._polyorder.set(2)
        self.tab._smoothing_panel._apply()
        self.tab.update_idletasks()
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertEqual(len(items), 2,
                         "shared subject list should contain the parent "
                         "UVVIS plus the new SMOOTHED node")

    def test_smoothing_status_message_routed_to_toolbar(self):
        # The panel's status_cb is wired to the tab's
        # _set_status_message helper (same hand-off as the
        # NormalisationPanel). A successful Apply must update the
        # toolbar status label.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_smooth_subject()
        self.tab._smoothing_panel._mode_var.set("moving_avg")
        self.tab._smoothing_panel._window_length.set(5)
        before = self.tab._status_lbl.cget("text")
        self.tab._smoothing_panel._apply()
        self.tab.update_idletasks()
        after = self.tab._status_lbl.cget("text")
        self.assertNotEqual(before, after)
        self.assertIn("smooth", after.lower())


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabPeakPickingIntegration(unittest.TestCase):
    """Phase 4h — PEAK_LIST nodes are first-class scatter overlays.

    Mirrors TestUVVisTabSmoothingIntegration (Phase 4g). The pure
    PeakPickingPanel mechanics are pinned in test_uvvis_peak_picking.py;
    here we only check that the panel is wired into the tab, that
    PEAK_LIST nodes flow through the render path as scatter (not lines)
    and through the right sidebar like UVVIS / BASELINE / NORMALISED /
    SMOOTHED, and that PEAK_LIST nodes do NOT appear in the baseline /
    normalisation / smoothing subject lists (chained peak picking is
    undefined per CS-19).
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str = "u1") -> None:
        wl = np.linspace(200.0, 800.0, 601)
        absorb = (np.exp(-((wl - 350.0) / 30.0) ** 2)
                  + 0.5 * np.exp(-((wl - 600.0) / 25.0) ** 2)
                  + 0.05)
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "syn"},
            label=nid, state=NodeState.COMMITTED,
            style={"color": "#111", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))

    def _select_first_peak_subject(self):
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertGreaterEqual(len(items), 1)
        self.tab._shared_subject.set(items[0])

    def test_panel_present_in_left_pane(self):
        self.assertTrue(hasattr(self.tab, "_peak_picking_panel"))

    def test_peak_list_node_renders_as_scatter_not_line(self):
        # Apply peak picking through the panel; the resulting PEAK_LIST
        # node must show up as a matplotlib scatter (PathCollection),
        # NOT a Line2D — keeping the line count at 1 (the parent UVVIS).
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_peak_subject()
        self.tab._peak_picking_panel._mode_var.set("prominence")
        self.tab._peak_picking_panel._prominence.set("0.1")
        self.tab._peak_picking_panel._distance.set(1)
        self.tab._peak_picking_panel._apply()
        self.tab.update_idletasks()
        # Scatter is a PathCollection on ax.collections, not a Line2D.
        self.assertEqual(len(self.tab._ax.get_lines()), 1,
                         "peak markers must not show up as lines")
        self.assertEqual(len(self.tab._ax.collections), 1,
                         "exactly one scatter overlay for the peak list")

    def test_peak_list_node_has_sidebar_row(self):
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_peak_subject()
        self.tab._peak_picking_panel._mode_var.set("manual")
        self.tab._peak_picking_panel._manual_wavelengths.set("350, 600")
        _, out_id = self.tab._peak_picking_panel._apply()
        self.tab._scan_tree.update_idletasks()
        # The new PEAK_LIST node owns a row in the right sidebar (the
        # sidebar filter widened from
        # [UVVIS, BASELINE, NORMALISED, SMOOTHED] to include PEAK_LIST
        # in Phase 4h).
        self.assertIn(out_id, self.tab._scan_tree._row_frames)

    def test_discard_removes_peak_list_from_plot(self):
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_peak_subject()
        self.tab._peak_picking_panel._mode_var.set("prominence")
        self.tab._peak_picking_panel._prominence.set("0.1")
        _, out_id = self.tab._peak_picking_panel._apply()
        self.tab.update_idletasks()
        self.assertEqual(len(self.tab._ax.collections), 1)
        self.graph.discard_node(out_id)
        self.tab.update_idletasks()
        self.assertEqual(len(self.tab._ax.collections), 0)

    def test_peak_list_does_not_appear_in_shared_subject_list(self):
        # PEAK_LIST is intentionally excluded from _spectrum_nodes
        # (CS-19): chained peak picking is undefined, and the shared
        # subject combobox (CS-22, Phase 4k) reads that helper.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_peak_subject()
        self.tab._peak_picking_panel._mode_var.set("prominence")
        self.tab._peak_picking_panel._prominence.set("0.1")
        self.tab._peak_picking_panel._apply()
        self.tab.update_idletasks()

        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertEqual(len(items), 1,
                         "shared subject list should still list only the "
                         "parent UVVIS — the new PEAK_LIST is not a curve")

    def test_peak_picking_status_message_routed_to_toolbar(self):
        # The panel's status_cb is wired to the tab's
        # _set_status_message helper (same hand-off as the
        # NormalisationPanel / SmoothingPanel). A successful Apply
        # must update the toolbar status label.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_peak_subject()
        self.tab._peak_picking_panel._mode_var.set("prominence")
        self.tab._peak_picking_panel._prominence.set("0.1")
        before = self.tab._status_lbl.cget("text")
        self.tab._peak_picking_panel._apply()
        self.tab.update_idletasks()
        after = self.tab._status_lbl.cget("text")
        self.assertNotEqual(before, after)
        self.assertIn("peak", after.lower())

    def test_empty_peak_list_renders_no_scatter(self):
        # A high prominence threshold filters every peak; the PEAK_LIST
        # node still gets created (the operation ran) but has no
        # samples, so the renderer skips drawing for it.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_peak_subject()
        self.tab._peak_picking_panel._mode_var.set("prominence")
        self.tab._peak_picking_panel._prominence.set("100.0")
        self.tab._peak_picking_panel._apply()
        self.tab.update_idletasks()
        self.assertEqual(len(self.tab._ax.collections), 0,
                         "empty peak lists must not draw a scatter")


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabSecondDerivativeIntegration(unittest.TestCase):
    """Phase 4i — SECOND_DERIVATIVE nodes are first-class curve overlays.

    Mirrors TestUVVisTabSmoothingIntegration (Phase 4g). The pure
    SecondDerivativePanel mechanics are pinned in
    test_uvvis_second_derivative.py; here we only check that the
    panel is wired into the tab, that SECOND_DERIVATIVE nodes flow
    through the render path as a curve (not scatter) and through the
    right sidebar like UVVIS / BASELINE / NORMALISED / SMOOTHED, and
    that SECOND_DERIVATIVE nodes do NOT appear in the baseline /
    normalisation / smoothing / peak-picking subject lists (chained
    derivatives are out of scope per CS-20).
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str = "u1") -> None:
        wl = np.linspace(200.0, 800.0, 601)
        absorb = np.exp(-((wl - 500.0) / 50.0) ** 2) + 0.05
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "syn"},
            label=nid, state=NodeState.COMMITTED,
            style={"color": "#111", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))

    def _select_first_d2_subject(self):
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertGreaterEqual(len(items), 1)
        self.tab._shared_subject.set(items[0])

    def test_panel_present_in_left_pane(self):
        self.assertTrue(hasattr(self.tab, "_second_derivative_panel"))

    def test_second_derivative_node_renders_as_line_not_scatter(self):
        # Apply second derivative through the panel; the resulting
        # SECOND_DERIVATIVE node must show up as a Line2D on the
        # secondary y-axis (Phase 4u CS-44 routes
        # NodeType.SECOND_DERIVATIVE to "secondary"). Parent UVVIS
        # stays on primary. NOT scatter on either axis.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_d2_subject()
        self.tab._second_derivative_panel._window_length.set(11)
        self.tab._second_derivative_panel._polyorder.set(3)
        self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()
        # Phase 4u (CS-44): parent on primary, derivative on secondary.
        self.assertEqual(len(self.tab._ax.get_lines()), 1,
                         "primary axis carries only the parent UVVIS")
        self.assertIn("secondary", self.tab._axes_by_role,
                      "SECOND_DERIVATIVE must lazily create the "
                      "secondary twin axis")
        self.assertEqual(
            len(self.tab._axes_by_role["secondary"].get_lines()), 1,
            "derivative must render as a Line2D on secondary, not scatter")
        self.assertEqual(len(self.tab._ax.collections), 0,
                         "no scatter overlay on primary")
        self.assertEqual(
            len(self.tab._axes_by_role["secondary"].collections), 0,
            "no scatter overlay on secondary")

    def test_second_derivative_node_has_sidebar_row(self):
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_d2_subject()
        _, out_id = self.tab._second_derivative_panel._apply()
        self.tab._scan_tree.update_idletasks()
        # The new SECOND_DERIVATIVE node owns a row in the right
        # sidebar (the sidebar filter widened from
        # [UVVIS, BASELINE, NORMALISED, SMOOTHED, PEAK_LIST] to
        # include SECOND_DERIVATIVE in Phase 4i).
        self.assertIn(out_id, self.tab._scan_tree._row_frames)

    def test_discard_removes_second_derivative_from_plot(self):
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_d2_subject()
        _, out_id = self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()
        # Phase 4u (CS-44): pre-discard the primary axis carries
        # the parent UVVIS and the secondary twin carries the
        # derivative.
        self.assertEqual(len(self.tab._ax.get_lines()), 1)
        self.assertEqual(
            len(self.tab._axes_by_role["secondary"].get_lines()), 1)
        self.graph.discard_node(out_id)
        self.tab.update_idletasks()
        # After the discard there are no SECOND_DERIVATIVE nodes on
        # the live list; the lazy axis-creation path skips
        # "secondary" entirely, so the role map shrinks back to
        # primary-only.
        lines = self.tab._ax.get_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].get_label(), "u1")
        self.assertNotIn("secondary", self.tab._axes_by_role,
                         "secondary axis must not be created when no "
                         "node routes to it")

    def test_second_derivative_appears_in_shared_subject_list(self):
        # Phase 4x (CS-49): SECOND_DERIVATIVE now appears in the
        # shared subject combobox so SmoothingPanel can accept a
        # derivative as a parent (closes the user-flagged Phase 4w
        # friction #1 — "Cannot smooth derivative plots").
        # ``_refresh_shared_subjects`` unions ``_spectrum_nodes()``
        # and ``_second_derivative_nodes()``; the renderer keeps the
        # two helpers separate so axis routing stays correct.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_d2_subject()
        self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()

        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertEqual(len(items), 2,
                         "shared subject list should list the parent UVVIS "
                         "AND the new SECOND_DERIVATIVE — Phase 4x widened "
                         "SmoothingPanel.ACCEPTED_PARENT_TYPES so the "
                         "derivative is now a valid parent for smoothing")

    def test_second_derivative_status_message_routed_to_toolbar(self):
        # The panel's status_cb is wired to the tab's
        # _set_status_message helper (same hand-off as the
        # NormalisationPanel / SmoothingPanel / PeakPickingPanel).
        # A successful Apply must update the toolbar status label.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_d2_subject()
        before = self.tab._status_lbl.cget("text")
        self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()
        after = self.tab._status_lbl.cget("text")
        self.assertNotEqual(before, after)
        self.assertIn("derivative", after.lower())

    def test_visibility_toggle_hides_derivative_curve(self):
        # The derivative node carries the universal style schema
        # (default_spectrum_style); flipping style.visible to False
        # must drop its curve from the plot on the next redraw,
        # matching how the existing UVVIS / BASELINE / NORMALISED /
        # SMOOTHED rows behave.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_d2_subject()
        _, out_id = self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()
        # Phase 4u (CS-44): parent on primary, derivative on secondary.
        self.assertEqual(len(self.tab._ax.get_lines()), 1)
        self.assertEqual(
            len(self.tab._axes_by_role["secondary"].get_lines()), 1)
        self.graph.set_style(out_id, {"visible": False})
        self.tab.update_idletasks()
        # Hidden derivative falls out of the live list, so the
        # secondary axis is no longer created on this redraw.
        self.assertEqual(len(self.tab._ax.get_lines()), 1)
        self.assertNotIn("secondary", self.tab._axes_by_role)

    def test_secondary_axis_label_is_x_unit_aware(self):
        # Phase 4u (CS-44): the secondary y-axis label switches with
        # the displayed x-unit because d²A/dλ² is only correct when
        # the x grid is wavelength. Cycle through nm / cm-1 / eV
        # and pin each label.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_d2_subject()
        self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()

        for unit, expected in (("nm", "d²A/dλ²"),
                               ("cm-1", "d²A/d(cm⁻¹)²"),
                               ("eV", "d²A/dE²")):
            self.tab._x_unit.set(unit)
            self.tab._on_unit_change()
            self.tab.update_idletasks()
            self.assertIn("secondary", self.tab._axes_by_role,
                          f"secondary axis missing after switching to {unit}")
            self.assertEqual(
                self.tab._axes_by_role["secondary"].get_ylabel(),
                expected,
                f"secondary y-label wrong for x-unit={unit}")

    def test_legend_merges_handles_across_primary_and_secondary(self):
        # Phase 4u (CS-44): a single legend lives on primary but
        # collects handles from every populated role. Without the
        # merge, a SECOND_DERIVATIVE node on the right axis would
        # silently drop out of the legend.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_d2_subject()
        _, out_id = self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()

        legend = self.tab._ax.get_legend()
        self.assertIsNotNone(legend, "primary axis must own the legend")
        labels = [t.get_text() for t in legend.get_texts()]
        self.assertIn("u1", labels,
                      "parent UVVIS label must be in the legend")
        d2_label = self.graph.get_node(out_id).label
        self.assertIn(d2_label, labels,
                      "SECOND_DERIVATIVE label must be merged into the "
                      "legend even though it lives on the secondary axis")

    def test_no_secondary_axis_when_only_primary_nodes_visible(self):
        # Phase 4u (CS-44): twin axes are lazy. A graph with only
        # primary-mapped node types renders identically to the
        # pre-CS-44 single-axis layout — `_axes_by_role` carries
        # exactly one entry.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self.assertEqual(len(self.tab._axes_by_role), 1,
                         "primary-only graph must not create twin axes")
        self.assertIn("primary", self.tab._axes_by_role)

    def test_empty_state_resets_role_map_to_primary_only(self):
        # _draw_empty must `_fig.clear()` and rebuild the role map
        # so a populated draw → empty transition does not leak twin
        # axes (orphaned spines from a hidden secondary derivative).
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_d2_subject()
        _, out_id = self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()
        self.assertIn("secondary", self.tab._axes_by_role)
        # Hide every live node — the next redraw flips into the
        # empty placeholder branch.
        for nid in (
                [n.id for n in self.graph.nodes_of_type(NodeType.UVVIS,
                                                        state=None)]
                + [out_id]):
            self.graph.set_style(nid, {"visible": False})
        self.tab.update_idletasks()
        self.assertEqual(self.tab._axes_by_role, {"primary": self.tab._ax},
                         "_draw_empty must reseed _axes_by_role to "
                         "primary-only")


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestAbsorbanceToYNodeTypeGatePhase4ah(unittest.TestCase):
    """Phase 4ah — `_absorbance_to_y` is a no-op for derivative-space NodeTypes.

    Phase 4u friction #9 fix. The helper used to apply the
    absorbance→%T conversion (``100 · 10^(-A)``) on every node's
    values regardless of NodeType — which corrupted d²A/dλ²
    values (stored in the legacy ``arrays["absorbance"]`` field
    on SECOND_DERIVATIVE nodes for historical reasons). The fix
    gates the conversion on CS-55's ``_ABSORBANCE_SPACE_NODETYPES``
    frozenset; non-absorbance-space NodeTypes pass through
    unchanged.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import (
            UVVisTab,
            _absorbance_to_y,
            _ABSORBANCE_SPACE_NODETYPES,
        )
        cls.UVVisTab = UVVisTab
        cls._absorbance_to_y = staticmethod(_absorbance_to_y)
        cls._ABSORBANCE_SPACE_NODETYPES = _ABSORBANCE_SPACE_NODETYPES

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    # ---- pure-helper coverage ----

    def test_absorbance_space_node_types_pin(self):
        # The five NodeTypes whose ``arrays["absorbance"]`` field
        # genuinely holds absorbance values. Add to this set with
        # care — adding SECOND_DERIVATIVE here would re-introduce
        # the Phase 4u friction #9 bug.
        self.assertEqual(
            self._ABSORBANCE_SPACE_NODETYPES,
            frozenset({
                NodeType.UVVIS,
                NodeType.BASELINE,
                NodeType.NORMALISED,
                NodeType.SMOOTHED,
                NodeType.PEAK_LIST,
            }),
        )

    def test_helper_noop_on_second_derivative_regardless_of_y_unit(self):
        # The headline regression: d²A values pass through unchanged
        # on "A" AND on "%T".
        d2 = np.array([-0.005, -0.001, 0.0, 0.001, 0.005])
        for y_unit in ("A", "%T"):
            with self.subTest(y_unit=y_unit):
                out = self._absorbance_to_y(
                    d2.copy(), y_unit, NodeType.SECOND_DERIVATIVE,
                )
                np.testing.assert_array_equal(out, d2)

    def test_helper_applies_pct_t_on_uvvis(self):
        # Backwards-compat: absorbance-space NodeTypes still get the
        # conversion. The clip + 100·10^(-A) maths is unchanged.
        a = np.array([0.0, 0.5, 1.0, 2.0])
        out = self._absorbance_to_y(a, "%T", NodeType.UVVIS)
        np.testing.assert_allclose(
            out, 100.0 * np.power(10.0, -a),
        )

    def test_helper_clip_preserved_on_absorbance_space(self):
        # The defensive clip on absorbance values must still hold
        # for absorbance-space NodeTypes — a 100 dB value would
        # otherwise underflow to 0 and lose information.
        a = np.array([-100.0, 100.0])
        out = self._absorbance_to_y(a, "%T", NodeType.UVVIS)
        # clip to [-10, 10] then 100·10^(-A)
        np.testing.assert_allclose(
            out,
            100.0 * np.power(10.0, -np.array([-10.0, 10.0])),
        )

    def test_helper_passthrough_on_absorbance_unit_for_absorbance_space(self):
        # "A" branch is byte-identical pre/post fix — pass-through.
        a = np.array([0.1, 0.5, 0.9])
        for ntype in self._ABSORBANCE_SPACE_NODETYPES:
            with self.subTest(node_type=ntype):
                out = self._absorbance_to_y(a.copy(), "A", ntype)
                np.testing.assert_array_equal(out, a)

    # ---- integration coverage: d²A values reach matplotlib unchanged ----

    def _add_uvvis(self, nid: str = "u1") -> str:
        wl = np.linspace(200.0, 800.0, 601)
        absorb = np.exp(-((wl - 500.0) / 50.0) ** 2) + 0.05
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "syn"},
            label=nid, state=NodeState.COMMITTED,
            style={"color": "#111", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))
        return nid

    def test_second_derivative_values_unchanged_by_percent_t_y_unit(self):
        # Phase 4u friction #9 end-to-end. Render a UVVIS parent +
        # SECOND_DERIVATIVE child + flip _y_unit to "%T" + assert
        # the rendered y-data on secondary equals the raw d²A values
        # (which live in the SECOND_DERIVATIVE node's
        # ``arrays["absorbance"]`` field by legacy naming).
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        # Apply second derivative via the panel to get a real
        # SECOND_DERIVATIVE node in the graph.
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._shared_subject.set(items[0])
        self.tab._second_derivative_panel._window_length.set(11)
        self.tab._second_derivative_panel._polyorder.set(3)
        _, d2_id = self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()

        d2_node = self.graph.get_node(d2_id)
        raw_d2 = np.asarray(d2_node.arrays["absorbance"], dtype=float)
        wl = np.asarray(d2_node.arrays["wavelength_nm"], dtype=float)
        # The renderer sorts by x; mirror the sort so our expected
        # array matches the line's data order.
        order = np.argsort(wl)
        expected = raw_d2[order]

        # Now flip y-unit to "%T" and force a fresh redraw.
        self.tab._y_unit.set("%T")
        self.tab._redraw()
        self.tab.update_idletasks()

        secondary = self.tab._axes_by_role["secondary"]
        lines = secondary.get_lines()
        self.assertEqual(len(lines), 1,
                         "expected exactly one Line2D on secondary "
                         "(the SECOND_DERIVATIVE curve)")
        rendered_y = lines[0].get_ydata()
        np.testing.assert_allclose(
            rendered_y, expected,
            err_msg="SECOND_DERIVATIVE values must NOT be transformed "
                    "by the _y_unit='%T' toggle — they are not "
                    "absorbance-space values.",
        )

    def test_uvvis_values_still_transformed_by_percent_t_y_unit(self):
        # Backwards-compat for absorbance-space: UVVIS values on
        # primary must STILL convert to %T when the toggle flips.
        # This pins that the gate hasn't accidentally broken the
        # original conversion path.
        self._add_uvvis("u1")
        self.tab._y_unit.set("%T")
        self.tab._redraw()
        self.tab.update_idletasks()
        lines = self.tab._ax.get_lines()
        self.assertEqual(len(lines), 1)
        rendered_y = lines[0].get_ydata()
        # The peak of the UVVIS Gaussian is around A≈1 → %T≈10. If
        # we accidentally skipped the conversion the peak would
        # still be ≈1, not 10ish. Use the minimum y value as a
        # robust proxy (it corresponds to the peak A).
        self.assertLess(
            float(np.min(rendered_y)), 50.0,
            "UVVIS on primary with y_unit='%T' must still apply the "
            "absorbance→%T conversion; minimum should be in %T units "
            "(near 10), not the raw absorbance (near 1).",
        )


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestYAxisLabelRoleSwap(unittest.TestCase):
    """Phase 4ad (CS-55) — y-axis label tracks NodeType, not axis side.

    Reproduces the Phase 4ac friction #1 USER-FLAGGED bug end-to-end:
    placing Absorbance (UVVIS) on the secondary axis via the CS-50
    ``style["y_axis"]`` override used to leave Absorbance unlabelled
    on the right side AND keep "Absorbance" hard-coded on the empty
    primary; placing SECOND_DERIVATIVE on primary used to label
    primary "Absorbance" even though the values plotted were d²A.
    CS-55's role-agnostic ``_resolve_y_axis_label`` fixes both.

    Default routing (no overrides) must still produce the pre-Phase-
    4ad labels — the bug fix is strictly a widening, not a behavioural
    flip for the common case.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str = "u1") -> None:
        wl = np.linspace(200.0, 800.0, 601)
        absorb = np.exp(-((wl - 500.0) / 50.0) ** 2) + 0.05
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "syn"},
            label=nid, state=NodeState.COMMITTED,
            style={"color": "#111", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))

    def _select_first_d2_subject(self):
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertGreaterEqual(len(items), 1)
        self.tab._shared_subject.set(items[0])

    def test_default_routing_uvvis_only_keeps_primary_absorbance_label(self):
        # Pre-Phase-4ad behaviour preservation: a default-routed UVVIS
        # node lands on primary with the "Absorbance" label (or
        # "Transmittance (%)" if y-unit is "%T"). The fix must NOT
        # regress the common case.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self.assertEqual(self.tab._ax.get_ylabel(), "Absorbance")

    def test_default_routing_y_unit_flip_to_transmittance(self):
        # The y-unit toggle still drives primary's auto label for
        # absorbance-space NodeTypes; the helper reads y-unit.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self.tab._y_unit.set("%T")
        self.tab._redraw()
        self.tab.update_idletasks()
        self.assertEqual(self.tab._ax.get_ylabel(), "Transmittance (%)")

    def test_uvvis_on_secondary_labels_secondary_absorbance(self):
        # Phase 4ac friction #1 case A: route Absorbance (UVVIS) to
        # secondary via CS-50 override. Secondary's label must be
        # "Absorbance"; primary is empty so it stays unlabelled.
        self._add_uvvis("u1")
        self.graph.set_style("u1", {"y_axis": "secondary"})
        self.tab.update_idletasks()
        self.assertIn("secondary", self.tab._axes_by_role)
        self.assertEqual(
            self.tab._axes_by_role["secondary"].get_ylabel(),
            "Absorbance",
            "Absorbance routed to secondary must label the secondary axis",
        )
        # Primary holds no nodes after the override; the helper does
        # not invent a label for an empty axis.
        self.assertEqual(self.tab._ax.get_ylabel(), "")

    def test_uvvis_on_secondary_with_y_unit_percent_t_labels_transmittance(self):
        # Y-unit toggle still drives the label when UVVIS is on the
        # secondary side — the dimension is NodeType class, not role.
        self._add_uvvis("u1")
        self.graph.set_style("u1", {"y_axis": "secondary"})
        self.tab._y_unit.set("%T")
        self.tab._redraw()
        self.tab.update_idletasks()
        self.assertEqual(
            self.tab._axes_by_role["secondary"].get_ylabel(),
            "Transmittance (%)",
        )

    def test_second_derivative_on_primary_labels_primary_with_derivative(self):
        # Phase 4ac friction #1 case B: route SECOND_DERIVATIVE to
        # primary via CS-50 override. Primary's label must be
        # "d²A/dλ²" (not "Absorbance"), because the helper now reads
        # the NodeType — not a hard-coded y-unit lookup.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_d2_subject()
        _, d2_id = self.tab._second_derivative_panel._apply()
        self.graph.set_style(d2_id, {"y_axis": "primary"})
        self.tab.update_idletasks()
        # The override flipped the derivative onto primary, so
        # secondary should not be created at all (parent UVVIS is
        # also on primary by default).
        self.assertNotIn("secondary", self.tab._axes_by_role)
        # Primary's first node (the UVVIS, added first) wins the
        # label — the bug isn't fully symmetric. Confirm the UVVIS
        # case stays correct under default y-unit, then test the
        # all-derivatives-on-primary case in a separate test.
        # Here we expect "Absorbance" (UVVIS is the first node).
        self.assertEqual(self.tab._ax.get_ylabel(), "Absorbance")

    def test_second_derivative_alone_on_primary_labels_derivative(self):
        # Bug repro: only a SECOND_DERIVATIVE node, routed to primary
        # via override, on the figure → primary's label is the
        # derivative label, not "Absorbance". The parent UVVIS is
        # hidden so primary's first (and only) node is the derivative.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_d2_subject()
        _, d2_id = self.tab._second_derivative_panel._apply()
        self.graph.set_style(d2_id, {"y_axis": "primary"})
        # Hide the parent so only the derivative renders.
        self.graph.set_style("u1", {"visible": False})
        self.tab.update_idletasks()
        self.assertEqual(self.tab._ax.get_ylabel(), "d²A/dλ²",
                         "primary axis with only a SECOND_DERIVATIVE "
                         "node must be labelled by the derivative, "
                         "NOT by the hard-coded absorbance label")

    def test_uvvis_on_secondary_and_derivative_on_primary_labels_both_correctly(self):
        # The full Phase 4ac friction #1 user-reported scenario:
        # Absorbance routed to secondary AND derivative routed to
        # primary. Pre-CS-55 the user saw "Absorbance" on the LEFT
        # (wrong; primary now holds a derivative) and nothing on the
        # right (wrong; secondary holds the absorbance). CS-55 fixes
        # both: primary → "d²A/dλ²", secondary → "Absorbance".
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_d2_subject()
        _, d2_id = self.tab._second_derivative_panel._apply()
        self.graph.set_style("u1", {"y_axis": "secondary"})
        self.graph.set_style(d2_id, {"y_axis": "primary"})
        self.tab.update_idletasks()
        self.assertIn("secondary", self.tab._axes_by_role)
        self.assertEqual(
            self.tab._ax.get_ylabel(), "d²A/dλ²",
            "primary holds the derivative — label must follow")
        self.assertEqual(
            self.tab._axes_by_role["secondary"].get_ylabel(),
            "Absorbance",
            "secondary holds the absorbance — label must follow")

    def test_custom_ylabel_mode_wins_for_primary_regardless_of_routing(self):
        # ylabel_mode = "custom" is the user-text affordance and is
        # primary-only. When set, primary shows the user's text
        # regardless of what NodeType lands there. Non-primary axes
        # always auto.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_d2_subject()
        _, d2_id = self.tab._second_derivative_panel._apply()
        self.graph.set_style("u1", {"y_axis": "secondary"})
        self.graph.set_style(d2_id, {"y_axis": "primary"})
        # Mutate the plot config the way the Plot Settings dialog
        # would after Save / Apply.
        self.tab._plot_config["ylabel_mode"] = "custom"
        self.tab._plot_config["ylabel_text"] = "My custom label"
        self.tab._redraw()
        self.tab.update_idletasks()
        self.assertEqual(self.tab._ax.get_ylabel(), "My custom label")
        # Non-primary still gets the auto label.
        self.assertEqual(
            self.tab._axes_by_role["secondary"].get_ylabel(),
            "Absorbance",
        )

    def test_secondary_label_x_unit_aware_for_derivative_default_routing(self):
        # CS-44 contract preserved: default routing puts d²A on
        # secondary, and the secondary label tracks x-unit (nm /
        # cm-1 / eV). Mirrors
        # TestUVVisTabSecondDerivativeIntegration.
        # test_secondary_axis_label_is_x_unit_aware — same invariant,
        # different surface (the new helper is wired in but its
        # SECOND_DERIVATIVE branch must keep its CS-44 behaviour).
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_d2_subject()
        self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()
        for unit, expected in (("nm", "d²A/dλ²"),
                               ("cm-1", "d²A/d(cm⁻¹)²"),
                               ("eV", "d²A/dE²")):
            self.tab._x_unit.set(unit)
            self.tab._on_unit_change()
            self.tab.update_idletasks()
            self.assertEqual(
                self.tab._axes_by_role["secondary"].get_ylabel(),
                expected,
                f"secondary label wrong for x-unit={unit} via CS-55 helper")


class TestUVVisTabTertiaryAxisPath(unittest.TestCase):
    """Phase 4u (CS-44) — tertiary axis path coverage.

    No NodeType defaults to "tertiary" today, so the offset-spine
    machinery has no production exercise. To prove the code path,
    monkey-patch ``uvvis_tab._resolve_y_axis_role`` to route a
    spectrum NodeType to "tertiary" and check that the third Axes
    is created with its right spine offset to
    ``_TERTIARY_AXIS_OFFSET_FRAC``. This is the user-flagged
    "possibly a 3rd y-axis somehow in some cases" requirement —
    the table edit lands as a one-line change once a real third-
    axis NodeType (Beer-Lambert concentration, difference spectra
    against a reference, etc.) shows up.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_tertiary_axis_lazily_created_with_offset_spine(self):
        import uvvis_tab as ut

        wl = np.linspace(200.0, 800.0, 601)
        absorb = np.exp(-((wl - 500.0) / 50.0) ** 2) + 0.05
        # Two nodes: parent UVVIS on primary (default), a NORMALISED
        # node which we route to "tertiary" via monkey-patch so the
        # offset-spine path lights up.
        self.graph.add_node(DataNode(
            id="u1", type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "syn"},
            label="u1", state=NodeState.COMMITTED,
            style={"color": "#111", "visible": True, "in_legend": True},
        ))
        self.graph.add_node(DataNode(
            id="n1", type=NodeType.NORMALISED,
            arrays={"wavelength_nm": wl, "absorbance": absorb * 2.0},
            metadata={"source_file": "syn"},
            label="n1", state=NodeState.COMMITTED,
            style={"color": "#222", "visible": True, "in_legend": True},
        ))

        original_resolver = ut._resolve_y_axis_role

        def routed_to_tertiary(node_type, style=None):
            # Phase 4y (CS-50) widened the helper signature to accept
            # an optional ``style`` for the per-style override hook;
            # the test's monkey-patch widens in lockstep so the
            # renderer's per-node call ``_resolve_y_axis_role(
            # node.type, node.style)`` reaches the patched function
            # without a TypeError.
            if node_type == NodeType.NORMALISED:
                return "tertiary"
            return original_resolver(node_type, style)

        ut._resolve_y_axis_role = routed_to_tertiary
        try:
            self.tab._redraw()
            self.tab.update_idletasks()
            self.assertIn("tertiary", self.tab._axes_by_role,
                          "tertiary axis must be created when at least "
                          "one node routes to it")
            tert = self.tab._axes_by_role["tertiary"]
            # The right spine of the tertiary axis is offset to the
            # tunable module constant. Match within float tolerance
            # against the live constant so a future Plot Settings
            # promotion that changes the value does not silently
            # break this assertion.
            position = tert.spines["right"].get_position()
            self.assertEqual(position[0], "axes")
            self.assertAlmostEqual(position[1],
                                   ut._TERTIARY_AXIS_OFFSET_FRAC,
                                   places=4)
            self.assertEqual(len(tert.get_lines()), 1,
                             "the routed NORMALISED curve must land on "
                             "the tertiary axis")
            self.assertEqual(len(self.tab._ax.get_lines()), 1,
                             "primary axis must keep its single UVVIS line")
        finally:
            ut._resolve_y_axis_role = original_resolver


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabAppearancePhase4ae(unittest.TestCase):
    """Phase 4ae (CS-56) — renderer reads the new Appearance keys.

    Integration coverage for the three Plot Settings → Appearance
    additions in commits 1–3:
      - cfg["grid_color"] reaches ax.grid(color=...).
      - cfg["tertiary_axis_offset"] reaches the tertiary-axis right
        spine position when a node routes to "tertiary".
      - The factory-default tick direction flipped to "in"; a fresh
        UVVisTab's plot_config inherits it.
      - Drift pin: _FACTORY_DEFAULTS["tertiary_axis_offset"] mirrors
        the uvvis_tab._TERTIARY_AXIS_OFFSET_FRAC constant.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab
        import plot_settings_dialog
        cls.psd = plot_settings_dialog

    def setUp(self):
        self.psd._USER_DEFAULTS.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass
        self.psd._USER_DEFAULTS.clear()

    def _add_uvvis(self, nid: str = "u1") -> str:
        wl = np.linspace(200.0, 800.0, 601)
        absorb = np.exp(-((wl - 500.0) / 50.0) ** 2) + 0.05
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "syn"},
            label=nid, state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))
        return nid

    # ---- drift pin: dict default mirrors the module constant ----

    def test_factory_default_mirrors_tertiary_offset_constant(self):
        # CS-56 invariant. The Plot Settings dict default and the
        # CS-44 module-level constant must stay equal — the constant
        # is the canonical fallback the renderer reads when cfg lacks
        # the key, and Factory Reset writes the dict default into
        # cfg. Drift here would surface as a visual jump on Factory
        # Reset for any user who hasn't manually adjusted the slider.
        import uvvis_tab as ut
        self.assertEqual(
            self.psd._FACTORY_DEFAULTS["tertiary_axis_offset"],
            ut._TERTIARY_AXIS_OFFSET_FRAC,
        )

    # ---- tick direction factory default reaches the tab ----

    def test_plot_config_inherits_inward_tick_default(self):
        # No user-defaults, no explicit config — the fresh tab's
        # plot_config copies the factory default "in" per axis role.
        # Phase 4ak (CS-62) moved the key into the nested
        # ``axes[<role>]`` schema, so the read reaches into the
        # sub-dict. Every per-axis role starts at the factory "in".
        self.assertNotIn("tick_direction", self.tab._plot_config)
        for role in self.psd._FACTORY_DEFAULTS["axes"]:
            self.assertEqual(
                self.tab._plot_config["axes"][role]["tick_direction"],
                "in",
            )

    # ---- grid colour reaches matplotlib ----

    def test_default_grid_colour_applied(self):
        self._add_uvvis()
        self.tab._redraw()
        lines = self.tab._ax.get_xgridlines()
        self.assertTrue(lines)
        # matplotlib expands the hex string to an RGBA tuple in
        # Line2D.get_color(); compare via to_rgba for tolerance.
        from matplotlib.colors import to_rgba
        self.assertEqual(
            to_rgba(lines[0].get_color()),
            to_rgba("#b0b0b0"),
        )

    def test_custom_grid_colour_applied(self):
        self._add_uvvis()
        self.tab._plot_config["grid_color"] = "#ff0000"
        self.tab._redraw()
        lines = self.tab._ax.get_xgridlines()
        self.assertTrue(lines)
        from matplotlib.colors import to_rgba
        self.assertEqual(
            to_rgba(lines[0].get_color()),
            to_rgba("#ff0000"),
        )

    def test_grid_off_then_on_with_custom_colour_round_trip(self):
        # Flip grid off then back on with a custom colour. The colour
        # must apply on the second draw (i.e. cfg["grid_color"] isn't
        # cached from the off path).
        self._add_uvvis()
        self.tab._plot_config["grid"] = False
        self.tab._redraw()
        self.tab._plot_config["grid"] = True
        self.tab._plot_config["grid_color"] = "#00ff00"
        self.tab._redraw()
        from matplotlib.colors import to_rgba
        lines = self.tab._ax.get_xgridlines()
        self.assertTrue(any(g.get_visible() for g in lines))
        self.assertEqual(
            to_rgba(lines[0].get_color()),
            to_rgba("#00ff00"),
        )

    # ---- tertiary axis offset reaches matplotlib ----

    def test_tertiary_offset_default_reaches_spine(self):
        # Same monkey-patch trick TestUVVisTabTertiaryAxisPath uses
        # above — route NORMALISED to "tertiary" so the offset-spine
        # path lights up — but here we omit any cfg override, so the
        # fallback to the module constant is the path under test.
        import uvvis_tab as ut

        self._add_uvvis()
        wl = np.linspace(200.0, 800.0, 601)
        absorb = np.exp(-((wl - 500.0) / 50.0) ** 2) + 0.05
        self.graph.add_node(DataNode(
            id="n1", type=NodeType.NORMALISED,
            arrays={"wavelength_nm": wl, "absorbance": absorb * 2.0},
            metadata={"source_file": "syn"},
            label="n1", state=NodeState.COMMITTED,
            style={"color": "#222", "visible": True, "in_legend": True},
        ))

        original_resolver = ut._resolve_y_axis_role

        def routed_to_tertiary(node_type, style=None):
            if node_type == NodeType.NORMALISED:
                return "tertiary"
            return original_resolver(node_type, style)

        ut._resolve_y_axis_role = routed_to_tertiary
        try:
            self.tab._redraw()
            tert = self.tab._axes_by_role["tertiary"]
            position = tert.spines["right"].get_position()
            self.assertEqual(position[0], "axes")
            self.assertAlmostEqual(
                position[1], ut._TERTIARY_AXIS_OFFSET_FRAC, places=4,
            )
        finally:
            ut._resolve_y_axis_role = original_resolver

    def test_tertiary_offset_custom_reaches_spine(self):
        # Custom cfg value (1.30) overrides the constant fallback and
        # reaches the spine.
        import uvvis_tab as ut

        self._add_uvvis()
        wl = np.linspace(200.0, 800.0, 601)
        absorb = np.exp(-((wl - 500.0) / 50.0) ** 2) + 0.05
        self.graph.add_node(DataNode(
            id="n1", type=NodeType.NORMALISED,
            arrays={"wavelength_nm": wl, "absorbance": absorb * 2.0},
            metadata={"source_file": "syn"},
            label="n1", state=NodeState.COMMITTED,
            style={"color": "#222", "visible": True, "in_legend": True},
        ))

        self.tab._plot_config["tertiary_axis_offset"] = 1.30

        original_resolver = ut._resolve_y_axis_role

        def routed_to_tertiary(node_type, style=None):
            if node_type == NodeType.NORMALISED:
                return "tertiary"
            return original_resolver(node_type, style)

        ut._resolve_y_axis_role = routed_to_tertiary
        try:
            self.tab._redraw()
            tert = self.tab._axes_by_role["tertiary"]
            position = tert.spines["right"].get_position()
            self.assertEqual(position[0], "axes")
            self.assertAlmostEqual(position[1], 1.30, places=4)
        finally:
            ut._resolve_y_axis_role = original_resolver


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabGridZOrderPhase4ah(unittest.TestCase):
    """Phase 4ah — grid renders BEHIND data lines, not in front.

    matplotlib's default grid zorder (2.5) sits above the default line
    zorder (2.0), so without an explicit override the dotted gridlines
    cross-hatch the rendered spectra. ``uvvis_tab._redraw`` now passes
    ``zorder=0`` on the ``ax.grid(...)`` call. Pin the invariant via
    the rendered Line2D objects so a future re-arrangement of the
    grid call (e.g. relocating to a per-axis loop) cannot silently
    regress.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str = "u1") -> str:
        wl = np.linspace(200.0, 800.0, 601)
        absorb = np.exp(-((wl - 500.0) / 50.0) ** 2) + 0.05
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "syn"},
            label=nid, state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))
        return nid

    def test_grid_renders_behind_data_lines(self):
        # Render a single spectrum and confirm every gridline's zorder
        # is strictly less than every data-line zorder. This is the
        # render-correctness invariant Phase 4ah locked.
        self._add_uvvis()
        self.tab._redraw()
        ax = self.tab._ax
        grid_lines = ax.get_xgridlines() + ax.get_ygridlines()
        data_lines = ax.get_lines()
        self.assertTrue(grid_lines, "expected gridlines on primary axis")
        self.assertTrue(data_lines, "expected at least one data line")
        max_grid_z = max(g.get_zorder() for g in grid_lines)
        min_data_z = min(d.get_zorder() for d in data_lines)
        self.assertLess(
            max_grid_z, min_data_z,
            f"grid zorder {max_grid_z} not below data zorder {min_data_z}",
        )

    def test_grid_zorder_is_zero(self):
        # Anchor on the literal value the renderer passes. Decoupled
        # from matplotlib's default-zorder choices in case those shift
        # in a future release.
        self._add_uvvis()
        self.tab._redraw()
        ax = self.tab._ax
        grid_lines = ax.get_xgridlines() + ax.get_ygridlines()
        self.assertTrue(grid_lines)
        for g in grid_lines:
            self.assertEqual(g.get_zorder(), 0)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabExportIntegration(unittest.TestCase):
    """Phase 4f, CS-17 — Export… dialog flow.

    The widget side of Export… is exercised in
    ``test_scan_tree_widget.py``; here we pin that the tab wires
    ``export_cb`` to its own handler, that the handler invokes the
    file dialog and writes via ``node_export``, and that an empty
    dialog return cancels the gesture.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)
        self._tmpdir = tempfile.mkdtemp(prefix="uvvis_export_test_")

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass
        for name in os.listdir(self._tmpdir):
            try:
                os.remove(os.path.join(self._tmpdir, name))
            except OSError:
                pass
        try:
            os.rmdir(self._tmpdir)
        except OSError:
            pass

    def _add_committed_uvvis(self, nid: str = "uvX0123456789",
                              label: str = "exportable") -> None:
        wl = np.linspace(200.0, 700.0, 6)
        ab = np.linspace(0.05, 0.95, 6)
        node = DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": ab},
            metadata={}, label=label,
            state=NodeState.COMMITTED,
        )
        self.graph.add_node(node)

    def test_scan_tree_export_cb_routes_to_tab_handler(self):
        # The tab must hand its ``_on_export_node`` method to the
        # widget. Bound methods are unique per access in Python (``is``
        # comparison fails even when both reference the same
        # underlying function), so we compare ``__func__`` / ``__self__``
        # to pin the wiring.
        cb = self.tab._scan_tree._export_cb
        self.assertIsNotNone(cb)
        self.assertIs(cb.__self__, self.tab)
        self.assertIs(
            cb.__func__, self.UVVisTab._on_export_node,
        )

    def test_export_node_writes_file_at_chosen_path(self):
        # Stub the file dialog so the flow runs end-to-end without UI.
        self._add_committed_uvvis()
        target = os.path.join(self._tmpdir, "out.csv")

        from uvvis_tab import filedialog as _fd
        original = _fd.asksaveasfilename
        try:
            _fd.asksaveasfilename = lambda **kw: target
            self.tab._on_export_node("uvX0123456789")
        finally:
            _fd.asksaveasfilename = original

        self.assertTrue(os.path.exists(target))
        with open(target, encoding="utf-8") as fh:
            text = fh.read()
        # File carries the expected header + data block.
        self.assertIn("# ptarmigan_version=", text)
        self.assertIn("wavelength_nm,absorbance", text)

    def test_export_cancel_writes_no_file(self):
        # An empty path return from the dialog is the cancellation
        # convention — the handler must not call out to node_export.
        self._add_committed_uvvis()

        from uvvis_tab import filedialog as _fd
        original = _fd.asksaveasfilename
        try:
            _fd.asksaveasfilename = lambda **kw: ""
            self.tab._on_export_node("uvX0123456789")
        finally:
            _fd.asksaveasfilename = original

        # No files in the tmpdir — the cancel path is silent.
        self.assertEqual(os.listdir(self._tmpdir), [])

    def test_export_default_basename_is_label_sanitised(self):
        # The dialog's ``initialfile`` must be the node's label with
        # filesystem-hostile characters replaced. We capture the kwargs
        # the tab passes to ``asksaveasfilename`` rather than driving
        # the real dialog.
        self._add_committed_uvvis(
            nid="lblsanitisetest", label='ugly/name?:"',
        )
        captured: dict = {}

        from uvvis_tab import filedialog as _fd
        original = _fd.asksaveasfilename

        def _capture(**kwargs):
            captured.update(kwargs)
            return ""  # cancel

        try:
            _fd.asksaveasfilename = _capture
            self.tab._on_export_node("lblsanitisetest")
        finally:
            _fd.asksaveasfilename = original

        initialfile = captured.get("initialfile", "")
        # No bad characters survived.
        for ch in '<>:"/\\|?*':
            self.assertNotIn(ch, initialfile)
        # And it didn't collapse to empty.
        self.assertTrue(initialfile)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestCollapsibleLeftPaneSections(unittest.TestCase):
    """Phase 4j (CS-21) — collapsible left-pane integration."""

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        from collapsible_section import CollapsibleSection
        cls.UVVisTab = UVVisTab
        cls.CollapsibleSection = CollapsibleSection

    def setUp(self):
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)
        self.tab.update_idletasks()

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    # ---- five sections present + named -----------------------------

    def test_all_five_sections_attached_to_tab(self):
        # Each section must be reachable as ``self.tab._{name}_section``
        # so future "expand all" gestures and project-state restore can
        # drive them. Pinned per the Phase 4j brief.
        for attr in (
            "_baseline_section",
            "_normalisation_section",
            "_smoothing_section",
            "_peak_picking_section",
            "_second_derivative_section",
        ):
            section = getattr(self.tab, attr, None)
            self.assertIsInstance(
                section, self.CollapsibleSection,
                f"{attr} should be a CollapsibleSection")

    # ---- default-collapsed state -----------------------------------

    def test_all_five_sections_start_collapsed(self):
        # Locked decision at end of Phase 4i — every section is
        # collapsed by default. Pin every one of the five so the
        # default-collapsed contract is loud if anything regresses.
        for attr in (
            "_baseline_section",
            "_normalisation_section",
            "_smoothing_section",
            "_peak_picking_section",
            "_second_derivative_section",
        ):
            section = getattr(self.tab, attr)
            self.assertFalse(
                section.is_expanded(),
                f"{attr} should start collapsed")

    def test_collapsed_section_bodies_are_not_packed(self):
        # The body's pack visibility is the perceptual contract — when
        # collapsed, the panel should not occupy vertical space on the
        # left pane.
        for attr in (
            "_baseline_section",
            "_normalisation_section",
            "_smoothing_section",
            "_peak_picking_section",
            "_second_derivative_section",
        ):
            section = getattr(self.tab, attr)
            self.assertNotIn(
                section.body, section.pack_slaves(),
                f"{attr}.body should be unpacked while collapsed")

    # ---- panels live inside their section's body -------------------

    def test_normalisation_panel_lives_in_section_body(self):
        # The panel is constructed with ``section.body`` as parent so
        # it inherits the section's pack visibility.
        self.assertIs(
            self.tab._normalisation_panel.master,
            self.tab._normalisation_section.body)

    def test_smoothing_panel_lives_in_section_body(self):
        self.assertIs(
            self.tab._smoothing_panel.master,
            self.tab._smoothing_section.body)

    def test_peak_picking_panel_lives_in_section_body(self):
        self.assertIs(
            self.tab._peak_picking_panel.master,
            self.tab._peak_picking_section.body)

    def test_second_derivative_panel_lives_in_section_body(self):
        self.assertIs(
            self.tab._second_derivative_panel.master,
            self.tab._second_derivative_section.body)

    def test_shared_subject_combobox_lives_outside_collapsible_sections(self):
        # Phase 4k (CS-22): the shared "Spectrum:" combobox sits at
        # the top of the left pane, ABOVE every CollapsibleSection,
        # so it is always visible regardless of which sections are
        # expanded. Walk up the master chain and assert no
        # CollapsibleSection body appears before we reach the left
        # pane root.
        master = self.tab._shared_subject_cb.master
        forbidden_bodies = {
            self.tab._baseline_section.body,
            self.tab._normalisation_section.body,
            self.tab._smoothing_section.body,
            self.tab._peak_picking_section.body,
            self.tab._second_derivative_section.body,
        }
        cur = master
        depth = 0
        while cur is not None and depth < 8:
            self.assertNotIn(
                cur, forbidden_bodies,
                "shared subject combobox must not be inside a "
                "CollapsibleSection body",
            )
            cur = cur.master
            depth += 1

    def test_baseline_section_body_has_no_subject_combobox(self):
        # The inline baseline subject row was removed in Phase 4k —
        # the section body no longer hosts any ttk.Combobox whose
        # textvariable points at a baseline-subject Tk var (the only
        # combobox left inside the body is the baseline-MODE combobox).
        bl = self.tab._baseline_section
        # The mode combobox is the only Combobox-typed descendant.
        n_combos = 0
        stack = list(bl.body.winfo_children())
        while stack:
            child = stack.pop()
            stack.extend(child.winfo_children())
            if child.winfo_class() == "TCombobox":
                n_combos += 1
        self.assertEqual(n_combos, 1,
                         "baseline section body should contain only the "
                         "mode combobox, not a subject combobox")

    # ---- expanding makes the panel visible -------------------------

    def test_expand_smoothing_section_packs_its_body(self):
        section = self.tab._smoothing_section
        self.assertNotIn(section.body, section.pack_slaves())
        section.expand()
        self.tab.update_idletasks()
        self.assertIn(section.body, section.pack_slaves())
        self.assertTrue(section.is_expanded())

    def test_expand_then_collapse_restores_unpacked_state(self):
        section = self.tab._peak_picking_section
        section.expand()
        self.tab.update_idletasks()
        section.collapse()
        self.tab.update_idletasks()
        self.assertNotIn(section.body, section.pack_slaves())
        self.assertFalse(section.is_expanded())

    # ---- header click integration ----------------------------------

    def test_header_click_toggles_section_via_handler(self):
        # The CollapsibleSection unit tests already pin the bound
        # handler path; this test pins that the integration into the
        # tab leaves the handler reachable (no rebinding mishap).
        section = self.tab._second_derivative_section
        self.assertFalse(section.is_expanded())
        section._on_header_click(None)
        self.tab.update_idletasks()
        self.assertTrue(section.is_expanded())


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabSharedSubject(unittest.TestCase):
    """Phase 4k (CS-22) — shared subject combobox hand-off.

    The four operation panels (NormalisationPanel, SmoothingPanel,
    PeakPickingPanel, SecondDerivativePanel) and the inline baseline
    section all read the same source of truth for "which node is the
    user operating on": ``UVVisTab._shared_subject`` + the trace-
    driven ``_on_shared_subject_changed`` fan-out. These tests pin
    the end-to-end behaviour: combobox membership, selection
    persistence across graph events, and per-panel Apply-gate
    interactions when the shared selection isn't a valid parent for
    the panel's op.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)
        self.tab.pack(fill=tk.BOTH, expand=True)
        self.tab.update_idletasks()

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    # ---- helpers ----------------------------------------------------

    def _add_uvvis(self, nid: str = "u1") -> str:
        wl = np.linspace(200.0, 800.0, 601)
        absorb = np.exp(-((wl - 500.0) ** 2) / (2.0 * 25.5 ** 2)) + 0.05
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"_load_id": f"L_{nid}", "source_file": f"syn_{nid}"},
            label=nid, state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))
        return nid

    def _select_shared(self, node_id: str) -> None:
        # Translate node id → display key, then set the shared
        # StringVar (mirrors what the user does by picking from the
        # combobox dropdown). The trace fans the change out.
        for key, nid in self.tab._shared_subject_map.items():
            if nid == node_id:
                self.tab._shared_subject.set(key)
                self.tab.update_idletasks()
                return
        self.fail(f"node {node_id!r} not in shared subject map")

    # ---- combobox membership ---------------------------------------

    def test_shared_combobox_starts_empty_with_no_nodes(self):
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertEqual(len(items), 0)
        self.assertEqual(self.tab._shared_subject.get(), "")

    def test_adding_uvvis_node_populates_combobox_and_auto_selects(self):
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertEqual(len(items), 1)
        # Auto-pick the only available node.
        self.assertNotEqual(self.tab._shared_subject.get(), "")
        self.assertEqual(self.tab._resolve_shared_subject_id(), "u1")

    def test_smoothed_node_appears_in_shared_combobox_after_apply(self):
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        # Smoothing panel adopts the shared subject u1; Apply
        # creates a SMOOTHED child.
        self.tab._smoothing_panel._mode_var.set("savgol")
        self.tab._smoothing_panel._window_length.set(5)
        self.tab._smoothing_panel._polyorder.set(2)
        self.tab._smoothing_panel._apply()
        self.tab.update_idletasks()
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertEqual(len(items), 2,
                         "shared list should now include parent + SMOOTHED")

    def test_peak_list_node_does_not_appear_in_shared_combobox(self):
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        # Peak picking on u1 produces a PEAK_LIST — not a candidate
        # subject for further curve operations.
        self.tab._peak_picking_panel._mode_var.set("prominence")
        self.tab._peak_picking_panel._prominence.set("0.1")
        self.tab._peak_picking_panel._apply()
        self.tab.update_idletasks()
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertEqual(len(items), 1,
                         "PEAK_LIST must not appear in the shared list")

    def test_second_derivative_node_appears_in_shared_combobox(self):
        # Phase 4x (CS-49): SECOND_DERIVATIVE joins the shared
        # combobox so SmoothingPanel can accept it as a parent.
        # See companion test
        # TestUVVisTabSecondDerivativeIntegration.test_second_derivative_appears_in_shared_subject_list
        # for the rationale block. Mirrors the prior PEAK_LIST
        # test: that one stays at len==1 (PEAK_LIST is not in any
        # panel's ACCEPTED_PARENT_TYPES, deliberately — it's an
        # output annotation, not a parent).
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertEqual(len(items), 2,
                         "SECOND_DERIVATIVE must appear in the shared list "
                         "(Phase 4x widening for SmoothingPanel)")

    def test_hiding_selected_node_moves_selection(self):
        # Two committed UVVIS nodes; pick u2; flip u2's active flag
        # off (the equivalent of "remove from list" for committed
        # rows in the right sidebar). _spectrum_nodes filters
        # inactive nodes, so the shared combobox repopulates with
        # only u1 and the selection auto-falls back.
        self._add_uvvis("u1")
        self._add_uvvis("u2")
        self.tab.update_idletasks()
        self._select_shared("u2")
        self.assertEqual(self.tab._resolve_shared_subject_id(), "u2")
        self.graph.set_active("u2", False)
        self.tab.update_idletasks()
        self.assertEqual(self.tab._resolve_shared_subject_id(), "u1")

    # ---- fan-out to panels -----------------------------------------

    def test_selecting_uvvis_enables_every_panel_apply_button(self):
        # Sanity: with a UVVIS subject selected, every panel + the
        # inline baseline Apply button is enabled (UVVIS is in every
        # panel's ACCEPTED_PARENT_TYPES).
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_shared("u1")
        self.assertEqual(
            str(self.tab._normalisation_panel._apply_btn.cget("state")),
            "normal")
        self.assertEqual(
            str(self.tab._smoothing_panel._apply_btn.cget("state")),
            "normal")
        self.assertEqual(
            str(self.tab._peak_picking_panel._apply_btn.cget("state")),
            "normal")
        self.assertEqual(
            str(self.tab._second_derivative_panel._apply_btn.cget("state")),
            "normal")
        self.assertEqual(
            str(self.tab._apply_baseline_btn.cget("state")),
            "normal")

    def test_smoothed_subject_disables_normalise_only(self):
        # Phase 4x (CS-49) split — SMOOTHED is *not* in
        # NormalisationPanel.ACCEPTED_PARENT_TYPES (peak/area
        # normalise should run on raw / baseline-corrected /
        # already-normalised curves, before smoothing). The inline
        # baseline section was widened to include SMOOTHED in
        # Phase 4x, closing the user-flagged Phase 4w friction #1
        # ("Cannot do baseline correction from a smoothed
        # spectrum"). Selecting a SMOOTHED subject must therefore
        # disable normalise's Apply but ENABLE baseline's Apply
        # (along with smoothing / peak-picking / 2nd-derivative).
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        # Materialise a SMOOTHED child of u1 via the smoothing panel.
        self.tab._smoothing_panel._mode_var.set("savgol")
        self.tab._smoothing_panel._window_length.set(5)
        self.tab._smoothing_panel._polyorder.set(2)
        _, smoothed_id = self.tab._smoothing_panel._apply()
        self.tab.update_idletasks()
        # Now flip the shared subject to the SMOOTHED child.
        self._select_shared(smoothed_id)

        self.assertEqual(
            str(self.tab._normalisation_panel._apply_btn.cget("state")),
            "disabled",
            "normalisation does not accept SMOOTHED parents (audit-time "
            "decision held in Phase 4x — see test_accepted_parent_types_constant "
            "in test_uvvis_normalise.py)")

        # Phase 4x widening: baseline now accepts SMOOTHED.
        self.assertEqual(
            str(self.tab._apply_baseline_btn.cget("state")),
            "normal",
            "Phase 4x (CS-49): inline baseline section now accepts "
            "SMOOTHED parents — closes Phase 4w friction #1")

        # The other three still accept SMOOTHED.
        self.assertEqual(
            str(self.tab._smoothing_panel._apply_btn.cget("state")),
            "normal")
        self.assertEqual(
            str(self.tab._peak_picking_panel._apply_btn.cget("state")),
            "normal")
        self.assertEqual(
            str(self.tab._second_derivative_panel._apply_btn.cget("state")),
            "normal")

    def test_no_subject_disables_every_apply_button(self):
        # Empty graph → no shared subject → every Apply is disabled.
        self.assertEqual(
            str(self.tab._normalisation_panel._apply_btn.cget("state")),
            "disabled")
        self.assertEqual(
            str(self.tab._smoothing_panel._apply_btn.cget("state")),
            "disabled")
        self.assertEqual(
            str(self.tab._peak_picking_panel._apply_btn.cget("state")),
            "disabled")
        self.assertEqual(
            str(self.tab._second_derivative_panel._apply_btn.cget("state")),
            "disabled")
        self.assertEqual(
            str(self.tab._apply_baseline_btn.cget("state")),
            "disabled")

    def test_label_edit_preserves_selection(self):
        # Editing the selected node's label fires NODE_LABEL_CHANGED;
        # the shared combobox repopulates its display strings, but
        # the resolved id underneath the selection must be unchanged.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_shared("u1")
        self.graph.set_label("u1", "u1-renamed")
        self.tab.update_idletasks()
        self.assertEqual(self.tab._resolve_shared_subject_id(), "u1")

    def test_panels_share_one_combobox_widget(self):
        # CS-22 invariant: every panel reads the SAME widget instance,
        # not a per-panel copy. The four panels no longer hold a
        # ``_subject_cb`` attribute at all — that's what allowed the
        # subject row to disappear from each section's body.
        self.assertFalse(
            hasattr(self.tab._normalisation_panel, "_subject_cb"))
        self.assertFalse(
            hasattr(self.tab._smoothing_panel, "_subject_cb"))
        self.assertFalse(
            hasattr(self.tab._peak_picking_panel, "_subject_cb"))
        self.assertFalse(
            hasattr(self.tab._second_derivative_panel, "_subject_cb"))


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabSendToCompareIntegration(unittest.TestCase):
    """Phase 4n CS-27 — per-row → Send-to-Compare wiring.

    The legacy top-bar "+ Add to TDDFT Overlay" button is gone;
    each ScanTreeWidget row carries a → icon that calls
    ``UVVisTab._send_node_to_compare(node_id)``. Tests cover both
    halves: (a) the tab no longer builds the bulk button, (b) the
    single-node helper does the right energy conversion and pushes
    a single ExperimentalScan into the host's add_scan_fn.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)
        # Capture every ExperimentalScan the tab tries to push.
        self.pushed: list = []
        self.tab._add_scan_fn = self.pushed.append

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str, label: str | None = None) -> DataNode:
        wl = np.linspace(300, 600, 10)
        absorb = np.linspace(0.1, 0.9, 10)
        node = DataNode(
            id=nid,
            type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label=label or nid,
            state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True},
        )
        self.graph.add_node(node)
        return node

    # ----------- top-bar button is gone -----------

    def test_top_bar_no_longer_has_overlay_button(self):
        # Walk every Button in the top toolbar and confirm none
        # carries the legacy "+ Add to TDDFT Overlay" text — the
        # affordance moved to the per-row → icon (CS-27).
        bar = self.tab._plot_settings_btn.master  # the toolbar frame
        for child in bar.winfo_children():
            if isinstance(child, tk.Button):
                self.assertNotIn(
                    "TDDFT Overlay", child.cget("text"),
                    "top bar must not carry a bulk overlay button "
                    "after CS-27",
                )

    def test_legacy_bulk_method_is_gone(self):
        # ``_add_selected_to_overlay`` is replaced by
        # ``_send_node_to_compare(node_id)`` — pin the rename so
        # external callers (binah host glue) catch the API change.
        self.assertFalse(hasattr(self.tab, "_add_selected_to_overlay"))
        self.assertTrue(hasattr(self.tab, "_send_node_to_compare"))

    # ----------- ScanTreeWidget receives the callback -----------

    def test_scan_tree_widget_has_send_to_compare_callback_wired(self):
        # The widget's ``_send_to_compare_cb`` must route through the
        # tab's single-node helper after CS-27 — confirms the
        # _build_sidebar wiring rather than asserting a None default.
        # Bound methods compare unequal across accesses, so verify by
        # behaviour: invoking the wired callback for a UVVIS node
        # produces an ExperimentalScan in the tab's add_scan_fn sink.
        self._add_uvvis("u1", label="wired-check")
        self.assertIsNotNone(self.tab._scan_tree._send_to_compare_cb)
        self.tab._scan_tree._send_to_compare_cb("u1")
        self.assertEqual(len(self.pushed), 1)
        self.assertEqual(self.pushed[0].label, "wired-check")

    # ----------- single-node helper pushes one ExperimentalScan ------

    def test_send_node_to_compare_pushes_one_scan(self):
        # A committed node, an ``_add_scan_fn`` host wired —
        # invoking the helper produces one ExperimentalScan with the
        # right label and uvvis_source metadata.
        self._add_uvvis("u1", label="my-spectrum")
        self.tab._send_node_to_compare("u1")

        self.assertEqual(len(self.pushed), 1)
        scan = self.pushed[0]
        self.assertEqual(scan.label, "my-spectrum")
        self.assertEqual(scan.scan_type, "UV/Vis absorbance")
        self.assertEqual(
            scan.metadata.get("uvvis_source"), "synthetic",
        )
        # Energy axis populated and strictly increasing.
        self.assertGreater(len(scan.energy_ev), 0)
        self.assertTrue(np.all(np.diff(scan.energy_ev) > 0))

    def test_send_node_to_compare_status_message_names_node(self):
        # Status bar message changes from the legacy "Added N
        # spectra to TDDFT overlay." (bulk) to "Sent <label> to
        # TDDFT overlay." (single).
        self._add_uvvis("u1", label="alpha")
        self.tab._send_node_to_compare("u1")
        self.tab.update_idletasks()
        status_text = self.tab._status_lbl.cget("text")
        self.assertIn("alpha", status_text)
        self.assertIn("TDDFT", status_text)

    def test_send_node_to_compare_no_host_shows_messagebox(self):
        # No ``_add_scan_fn`` wired ⇒ helper bails with a messagebox
        # before any push. Stub the messagebox so the test is silent.
        self._add_uvvis("u1")
        self.tab._add_scan_fn = None
        from unittest import mock
        with mock.patch("uvvis_tab.messagebox.showinfo") as mb:
            self.tab._send_node_to_compare("u1")
        self.assertEqual(self.pushed, [])
        self.assertEqual(mb.call_count, 1)

    def test_send_node_to_compare_unknown_id_is_silent(self):
        # Stale ids (row destroyed between click and dispatch)
        # must not raise out of the click path.
        self.tab._send_node_to_compare("ghost")
        self.assertEqual(self.pushed, [])

    def test_send_node_to_compare_skips_non_uvvis_nodes(self):
        # The helper guards on ``node.type == NodeType.UVVIS`` —
        # downstream NodeTypes (BASELINE, NORMALISED, etc.) are
        # routed through the same ScanTreeWidget filter, but
        # ExperimentalScan.energy_ev expects UVVIS-shaped
        # ``wavelength_nm`` / ``absorbance`` arrays. Out-of-shape
        # nodes are dropped silently.
        #
        # Phase 4o (CS-28): the previous get_node stub workaround
        # is no longer needed — _redraw's defensive guard skips
        # malformed DataNodes silently, so a BASELINE node with a
        # non-canonical array key can live in the graph without
        # crashing the renderer.
        bad_baseline = DataNode(
            id="b1",
            type=NodeType.BASELINE,
            arrays={"wavelength_nm": np.linspace(300, 600, 5),
                    "baseline":      np.zeros(5)},
            metadata={"source_file": "synthetic"},
            label="b1",
            state=NodeState.COMMITTED,
        )
        self.graph.add_node(bad_baseline)
        self.tab._send_node_to_compare("b1")
        self.assertEqual(self.pushed, [])


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabBaselineCurveOverlay(unittest.TestCase):
    """Phase 4o (CS-29) / Phase 4ao (CS-67) — dashed baseline-curve
    overlay in _redraw.

    Phase 4ao retired the global ``_show_baseline_curves`` BooleanVar
    and its top-bar Checkbutton; CS-36's per-node
    ``style["show_baseline_curve"]`` (default True) is now the
    single source of truth. The renderer no longer carries an outer
    global guard. Each visible BASELINE node gets a dashed overlay
    of its fitted baseline (recovered via
    ``uvvis_baseline.compute_baseline_curve``) UNLESS the per-node
    style explicitly opts out.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        from nodes import OperationNode, OperationType
        self.OperationNode = OperationNode
        self.OperationType = OperationType
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _build_parent_and_baseline(self):
        wl = np.linspace(300.0, 600.0, 6)
        parent_abs = np.array([1.0, 1.5, 2.0, 1.8, 1.4, 0.9])
        baseline_function = np.array([0.4, 0.5, 0.6, 0.55, 0.45, 0.3])
        child_abs = parent_abs - baseline_function
        parent = DataNode(
            id="p1", type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": parent_abs},
            metadata={"source_file": "synthetic"}, label="parent-spec",
            state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True},
        )
        op = self.OperationNode(
            id="op1", type=self.OperationType.BASELINE,
            engine="internal", engine_version="test",
            params={"mode": "linear"},
            input_ids=["p1"], output_ids=["c1"],
            status="SUCCESS", state=NodeState.COMMITTED,
        )
        child = DataNode(
            id="c1", type=NodeType.BASELINE,
            arrays={"wavelength_nm": wl, "absorbance": child_abs},
            metadata={}, label="parent · baseline (linear)",
            state=NodeState.COMMITTED,
            style={"color": "#ff7f0e", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True},
        )
        self.graph.add_node(parent)
        self.graph.add_node(op)
        self.graph.add_node(child)
        self.graph.add_edge("p1", "op1")
        self.graph.add_edge("op1", "c1")
        return wl, parent_abs, baseline_function

    def test_no_global_baseline_var_after_phase_4ao(self):
        # Phase 4ao (CS-67) retired the global BooleanVar. The
        # attribute must no longer exist on UVVisTab so that a
        # future copy-paste of "self.tab._show_baseline_curves" in
        # a test or in app code fails loudly.
        self.assertFalse(
            hasattr(self.tab, "_show_baseline_curves"),
            "Phase 4ao: global _show_baseline_curves BooleanVar removed",
        )
        self.assertFalse(
            hasattr(self.tab, "_baseline_curves_cb"),
            "Phase 4ao: global Baseline curves Checkbutton removed",
        )

    def test_per_node_default_renders_overlay(self):
        # CS-36 default for ``style["show_baseline_curve"]`` is True;
        # Phase 4ao removed the global outer guard. Result: a freshly
        # committed BASELINE node renders its dashed overlay without
        # the user touching any toggle.
        self._build_parent_and_baseline()
        self.tab._x_unit.set("nm")
        self.tab._redraw()
        labels = [ln.get_label() for ln in self.tab._ax.get_lines()]
        self.assertIn(
            "parent · baseline (linear) (baseline)", labels,
            "overlay must render by default (no global gate anymore)",
        )

    def test_per_node_show_false_hides_overlay(self):
        # CS-36's per-node gate is now the single source of truth.
        # Setting ``style["show_baseline_curve"]`` to False on the
        # BASELINE child must hide its dashed overlay.
        self._build_parent_and_baseline()
        self.graph.set_style("c1", {"show_baseline_curve": False})
        self.tab._redraw()
        for ln in self.tab._ax.get_lines():
            self.assertNotEqual(
                ln.get_linestyle(), "--",
                "per-node show_baseline_curve=False must hide overlay",
            )

    def test_toggle_on_adds_dashed_baseline_curve(self):
        wl, parent_abs, baseline_function = (
            self._build_parent_and_baseline()
        )
        # Stay in nm so x-axis ordering matches input ordering.
        self.tab._x_unit.set("nm")
        self.tab._redraw()

        labels = [ln.get_label() for ln in self.tab._ax.get_lines()]
        self.assertIn("parent · baseline (linear) (baseline)", labels,
                      "overlay must appear in legend when toggle on")
        # Find the dashed line and verify y-data matches the baseline
        # function (sorted by x).
        dashed = [ln for ln in self.tab._ax.get_lines()
                  if ln.get_linestyle() == "--"]
        self.assertEqual(len(dashed), 1,
                         "exactly one dashed overlay expected")
        # y-data is in display order (sorted by x). In nm units the
        # x is just wl, so display order matches input order.
        y_drawn = np.asarray(dashed[0].get_ydata(), dtype=float)
        np.testing.assert_array_almost_equal(y_drawn, baseline_function)

    def test_invisible_baseline_node_has_no_overlay(self):
        # Hiding the BASELINE node hides its baseline-curve overlay
        # too — the overlay follows the node's visibility.
        self._build_parent_and_baseline()
        # Hide the BASELINE node via style.
        self.graph.set_style("c1", {"visible": False})
        self.tab._redraw()
        for ln in self.tab._ax.get_lines():
            self.assertNotEqual(
                ln.get_linestyle(), "--",
                "dashed overlay must not render for an invisible node",
            )

    def test_overlay_uses_baseline_node_color(self):
        # The dashed overlay inherits the BASELINE node's colour so
        # the user can match the dashed line to the corrected curve
        # at a glance.
        self._build_parent_and_baseline()
        self.tab._redraw()
        dashed = [ln for ln in self.tab._ax.get_lines()
                  if ln.get_linestyle() == "--"]
        self.assertEqual(len(dashed), 1)
        # Compare matplotlib's normalised RGBA against the BASELINE
        # node's hex colour.
        from matplotlib.colors import to_rgba
        self.assertEqual(
            to_rgba(dashed[0].get_color()),
            to_rgba("#ff7f0e"),
        )

    def test_orphan_baseline_node_skipped_without_crash(self):
        # A BASELINE node added to the graph without an upstream
        # operation: the helper returns None, the loop skips, no
        # crash. (Pairs with CS-28 guard but exercises the overlay
        # branch specifically.)
        bad = DataNode(
            id="b1", type=NodeType.BASELINE,
            arrays={"wavelength_nm": np.linspace(300, 600, 4),
                    "absorbance":    np.zeros(4)},
            metadata={}, label="orphan",
            state=NodeState.COMMITTED,
            style={"color": "#000", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True},
        )
        self.graph.add_node(bad)
        self.tab._redraw()  # must not raise
        for ln in self.tab._ax.get_lines():
            self.assertNotEqual(ln.get_linestyle(), "--")


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabRedrawGuard(unittest.TestCase):
    """Phase 4o (CS-28) — _redraw silently skips malformed DataNodes.

    Every NodeType in ``_spectrum_nodes()`` / ``_second_derivative_nodes()``
    is *meant* to carry a ``wavelength_nm`` + ``absorbance`` array
    pair, but a half-formed DataNode (test scaffolding, partial
    project file, future NodeType added to the filter list without
    renderer support) used to raise KeyError from inside the Tk
    graph-event handler. The guard skips the bad node and lets the
    rest of the live list render.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str, label: str = "u") -> DataNode:
        node = DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": np.linspace(300.0, 600.0, 5),
                    "absorbance":    np.linspace(0.1, 0.5, 5)},
            metadata={"source_file": "synthetic"}, label=label,
            state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True},
        )
        self.graph.add_node(node)
        return node

    def _add_malformed_baseline(self, nid: str = "b1") -> DataNode:
        # Deliberately wrong array key — exercises the guard.
        node = DataNode(
            id=nid, type=NodeType.BASELINE,
            arrays={"wavelength_nm": np.linspace(300.0, 600.0, 5),
                    "baseline":      np.zeros(5)},
            metadata={"source_file": "synthetic"}, label="malformed",
            state=NodeState.COMMITTED,
            style={"color": "#ff7f0e", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True},
        )
        self.graph.add_node(node)
        return node

    def test_redraw_does_not_raise_on_malformed_baseline_alone(self):
        # Only a malformed BASELINE in the graph: pre-CS-28 this
        # raised KeyError("absorbance") from the Tk handler.
        self._add_malformed_baseline()
        self.tab._redraw()  # must not raise
        # No spectrum line was drawn from the malformed node.
        ax_lines = self.tab._ax.get_lines() if self.tab._ax else []
        # Either the axis went into the empty-state placeholder or
        # it contains zero spectrum lines from the malformed node.
        # Both outcomes are acceptable; the assertion is "no crash".
        self.assertTrue(True, "guard kept _redraw alive")

    def test_redraw_skips_malformed_node_alongside_valid_one(self):
        # A valid UVVIS + a malformed BASELINE coexist; the valid
        # one renders, the malformed one is silently dropped.
        self._add_uvvis("u1", label="real")
        self._add_malformed_baseline("b1")
        self.tab._redraw()
        labels = [ln.get_label() for ln in self.tab._ax.get_lines()]
        self.assertIn("real", labels,
                      "valid UVVIS line must still render")
        self.assertNotIn("malformed", labels,
                         "malformed BASELINE must be skipped")

    def test_redraw_nm_axis_xlim_ignores_malformed_node(self):
        # The unit == "nm" min/max comprehension also reads
        # node.arrays["wavelength_nm"]; the guard mirror keeps it
        # alive when one entry of `live` lacks the key.
        self._add_uvvis("u1")
        # Construct a malformed node missing wavelength_nm too.
        bad = DataNode(
            id="b2", type=NodeType.BASELINE,
            arrays={"absorbance": np.zeros(3)},  # no wavelength_nm
            metadata={}, label="missing-wl",
            state=NodeState.COMMITTED,
            style={"color": "#000", "visible": True, "in_legend": True},
        )
        self.graph.add_node(bad)
        self.tab._x_unit.set("nm")
        self.tab._redraw()  # must not raise


class TestMultiAxisRoutingHelpers(unittest.TestCase):
    """Phase 4u (CS-44) — pure-helper coverage for the multi-axis routing.

    The constants and helpers under test are module-level in
    ``uvvis_tab`` and have no Tk dependency, so this class does not
    construct a display. Integration coverage (twin-axis lifecycle in
    ``_redraw``) lives in ``TestUVVisTabSecondDerivativeIntegration``
    + the per-role smoke tests later in this file.
    """

    def test_axis_roles_tuple_shape_and_order(self):
        # The role tuple is a fixed three-entry vocabulary: primary
        # is the user-facing left axis, secondary the first twinx,
        # tertiary the offset-spine third axis. Order matters because
        # `_redraw` walks it to build the role → Axes map in
        # deterministic order. Tests pin the shape so a future
        # signature change (e.g. shrinking back to two roles) shows
        # up as a CI failure rather than a silent UI surprise.
        from uvvis_tab import _AXIS_ROLES
        self.assertEqual(_AXIS_ROLES, ("primary", "secondary", "tertiary"))

    def test_default_y_axis_table_covers_every_renderer_nodetype(self):
        # Every NodeType that flows through `_spectrum_nodes`,
        # `_second_derivative_nodes`, or `_peak_list_nodes` must
        # have an entry in the default table — the lookup falls back
        # to "primary" for unknowns, but routing decisions for these
        # NodeTypes should be explicit, not implicit, so a future
        # NodeType addition cannot silently land on the wrong axis.
        from uvvis_tab import _DEFAULT_Y_AXIS_BY_NODETYPE
        for ntype in (NodeType.UVVIS, NodeType.BASELINE,
                      NodeType.NORMALISED, NodeType.SMOOTHED,
                      NodeType.PEAK_LIST, NodeType.SECOND_DERIVATIVE):
            self.assertIn(ntype, _DEFAULT_Y_AXIS_BY_NODETYPE,
                          f"{ntype} missing from _DEFAULT_Y_AXIS_BY_NODETYPE")

    def test_resolve_y_axis_role_routes_second_derivative_to_secondary(self):
        from uvvis_tab import _resolve_y_axis_role
        self.assertEqual(_resolve_y_axis_role(NodeType.SECOND_DERIVATIVE),
                         "secondary")

    def test_resolve_y_axis_role_routes_other_renderer_types_to_primary(self):
        # All five non-derivative renderer NodeTypes share the
        # absorbance y-axis (primary).
        from uvvis_tab import _resolve_y_axis_role
        for ntype in (NodeType.UVVIS, NodeType.BASELINE,
                      NodeType.NORMALISED, NodeType.SMOOTHED,
                      NodeType.PEAK_LIST):
            self.assertEqual(_resolve_y_axis_role(ntype), "primary",
                             f"{ntype} must default to 'primary'")

    def test_resolve_y_axis_role_falls_back_to_primary_for_unknown_type(self):
        # NodeTypes outside the renderer set (RAW_FILE, ANALYSIS,
        # XANES, etc.) never reach `_redraw`'s plot loop, but the
        # helper is total over NodeType — an unknown type defaults
        # to "primary" so a future renderer extension that forgets
        # to register its NodeType lands safely on the left axis.
        from uvvis_tab import _resolve_y_axis_role
        self.assertEqual(_resolve_y_axis_role(NodeType.RAW_FILE), "primary")

    def test_default_role_values_are_subset_of_axis_roles(self):
        # Every value in the per-NodeType table must be one of the
        # three known roles — drift here is a contract bug.
        from uvvis_tab import _AXIS_ROLES, _DEFAULT_Y_AXIS_BY_NODETYPE
        for ntype, role in _DEFAULT_Y_AXIS_BY_NODETYPE.items():
            self.assertIn(role, _AXIS_ROLES,
                          f"{ntype} maps to {role!r} which is not in "
                          f"_AXIS_ROLES")

    def test_resolve_non_primary_y_label_is_x_unit_aware(self):
        # SECOND_DERIVATIVE's label changes with the displayed x
        # unit — d²A/dλ² when nm, d²A/d(cm⁻¹)² when cm-1, d²A/dE²
        # when eV. The label is physically meaningful, not
        # cosmetic, so the helper must round-trip every supported
        # unit.
        from uvvis_tab import _resolve_non_primary_y_label
        self.assertEqual(
            _resolve_non_primary_y_label(NodeType.SECOND_DERIVATIVE, "nm"),
            "d²A/dλ²",
        )
        self.assertEqual(
            _resolve_non_primary_y_label(NodeType.SECOND_DERIVATIVE, "cm-1"),
            "d²A/d(cm⁻¹)²",
        )
        self.assertEqual(
            _resolve_non_primary_y_label(NodeType.SECOND_DERIVATIVE, "eV"),
            "d²A/dE²",
        )

    def test_resolve_non_primary_y_label_returns_none_for_unregistered(self):
        # A (NodeType, x_unit) pair without a registered label
        # returns None — the role goes unlabelled rather than
        # picking a guess. UVVIS on any unit and SECOND_DERIVATIVE
        # on a hypothetical future unit both fall through.
        from uvvis_tab import _resolve_non_primary_y_label
        self.assertIsNone(
            _resolve_non_primary_y_label(NodeType.UVVIS, "nm"))
        self.assertIsNone(
            _resolve_non_primary_y_label(NodeType.UVVIS, "cm-1"))
        self.assertIsNone(
            _resolve_non_primary_y_label(NodeType.SECOND_DERIVATIVE,
                                         "future-unit"))

    def test_tertiary_axis_offset_constant_in_typical_range(self):
        # 1.10–1.15 is the typical matplotlib convention for a
        # 3rd-axis stacked spine. Pinned as a sanity check; the
        # constant is intentionally module-level so a future Plot
        # Settings field can promote it without changing any helper
        # signatures.
        from uvvis_tab import _TERTIARY_AXIS_OFFSET_FRAC
        self.assertGreater(_TERTIARY_AXIS_OFFSET_FRAC, 1.0)
        self.assertLess(_TERTIARY_AXIS_OFFSET_FRAC, 1.30)


class TestYAxisLabelResolution(unittest.TestCase):
    """Phase 4ad (CS-55) — role-agnostic y-axis label helper.

    CS-44 + CS-50 introduced multi-axis routing and a per-style
    override; the resulting Phase 4ac friction #1 USER-FLAGGED bug
    was that the renderer hard-coded primary's ylabel from y-unit
    only, leaving Absorbance-on-secondary unlabelled and
    SECOND_DERIVATIVE-on-primary labelled "Absorbance". The fix is
    structural: ``_resolve_y_axis_label(node_type, x_unit, y_unit)``
    returns the right label regardless of which axis the node lives
    on. Absorbance-space NodeTypes label from y-unit; derivative-
    space NodeTypes label from x-unit via the existing CS-44 table.
    """

    def test_absorbance_space_nodetypes_membership(self):
        # The frozenset must cover exactly the NodeTypes that share
        # the absorbance-or-transmittance y-unit semantics. Drift
        # against this set would silently break the bug fix — e.g.
        # adding a derivative NodeType here would route its label
        # through the y-unit path, not the x-unit path.
        from uvvis_tab import _ABSORBANCE_SPACE_NODETYPES
        self.assertIsInstance(_ABSORBANCE_SPACE_NODETYPES, frozenset)
        self.assertEqual(
            _ABSORBANCE_SPACE_NODETYPES,
            frozenset({
                NodeType.UVVIS,
                NodeType.BASELINE,
                NodeType.NORMALISED,
                NodeType.SMOOTHED,
                NodeType.PEAK_LIST,
            }),
        )

    def test_absorbance_space_matches_primary_default_routing(self):
        # Sanity drift guard: every absorbance-space NodeType also
        # defaults to "primary" in the CS-44 routing table. If a
        # future NodeType lands on "primary" by default but its
        # values are NOT absorbance-shaped, it must NOT be added to
        # _ABSORBANCE_SPACE_NODETYPES — and the test would force a
        # deliberate split here.
        from uvvis_tab import (
            _ABSORBANCE_SPACE_NODETYPES,
            _DEFAULT_Y_AXIS_BY_NODETYPE,
        )
        for ntype in _ABSORBANCE_SPACE_NODETYPES:
            self.assertEqual(
                _DEFAULT_Y_AXIS_BY_NODETYPE.get(ntype),
                "primary",
                f"{ntype} is in absorbance-space set but does not "
                f"default to primary",
            )

    def test_absorbance_y_label_dict_shape(self):
        from uvvis_tab import _ABSORBANCE_Y_LABEL
        self.assertEqual(
            _ABSORBANCE_Y_LABEL,
            {"A": "Absorbance", "%T": "Transmittance (%)"},
        )

    def test_resolve_label_for_absorbance_space_uses_y_unit(self):
        # Every absorbance-space NodeType returns the y-unit-derived
        # label regardless of x-unit. This is the core invariant
        # that fixes Absorbance-on-secondary.
        from uvvis_tab import _resolve_y_axis_label
        for ntype in (NodeType.UVVIS, NodeType.BASELINE,
                      NodeType.NORMALISED, NodeType.SMOOTHED,
                      NodeType.PEAK_LIST):
            for x_unit in ("nm", "cm-1", "eV"):
                self.assertEqual(
                    _resolve_y_axis_label(ntype, x_unit, "A"),
                    "Absorbance",
                    f"{ntype} on x={x_unit} y=A",
                )
                self.assertEqual(
                    _resolve_y_axis_label(ntype, x_unit, "%T"),
                    "Transmittance (%)",
                    f"{ntype} on x={x_unit} y=%T",
                )

    def test_resolve_label_for_second_derivative_uses_x_unit(self):
        # SECOND_DERIVATIVE labels by x-unit (independent of y-unit).
        # This is the existing CS-44 contract — preserved end-to-end.
        from uvvis_tab import _resolve_y_axis_label
        cases = {
            "nm":   "d²A/dλ²",
            "cm-1": "d²A/d(cm⁻¹)²",
            "eV":   "d²A/dE²",
        }
        for x_unit, expected in cases.items():
            for y_unit in ("A", "%T"):
                self.assertEqual(
                    _resolve_y_axis_label(
                        NodeType.SECOND_DERIVATIVE, x_unit, y_unit),
                    expected,
                    f"d²A on x={x_unit} y={y_unit}",
                )

    def test_resolve_label_returns_none_for_absorbance_space_unknown_y_unit(self):
        # Unknown y-unit on an absorbance-space NodeType returns None
        # rather than guessing.
        from uvvis_tab import _resolve_y_axis_label
        self.assertIsNone(
            _resolve_y_axis_label(NodeType.UVVIS, "nm", "future-y-unit"))

    def test_resolve_label_returns_none_for_derivative_unknown_x_unit(self):
        # Unknown x-unit on a non-absorbance NodeType falls through
        # to the existing _NON_PRIMARY_Y_LABEL lookup and returns
        # None.
        from uvvis_tab import _resolve_y_axis_label
        self.assertIsNone(
            _resolve_y_axis_label(
                NodeType.SECOND_DERIVATIVE, "future-x-unit", "A"))

    def test_resolve_label_returns_none_for_unrouted_nodetype(self):
        # A NodeType that's neither absorbance-space nor present in
        # the CS-44 derivative-label table returns None (e.g.
        # RAW_FILE, TDDFT — not rendered on the UV/Vis tab).
        from uvvis_tab import _resolve_y_axis_label
        self.assertIsNone(
            _resolve_y_axis_label(NodeType.RAW_FILE, "nm", "A"))
        self.assertIsNone(
            _resolve_y_axis_label(NodeType.TDDFT, "nm", "A"))

    def test_resolve_label_agrees_with_legacy_non_primary_helper(self):
        # Backward-compat check: for the SECOND_DERIVATIVE NodeType,
        # the new helper returns exactly what the CS-44-locked
        # _resolve_non_primary_y_label returns. The new helper is a
        # widening, not a replacement; CS-44's contract stands.
        from uvvis_tab import (
            _resolve_y_axis_label,
            _resolve_non_primary_y_label,
        )
        for x_unit in ("nm", "cm-1", "eV"):
            self.assertEqual(
                _resolve_y_axis_label(
                    NodeType.SECOND_DERIVATIVE, x_unit, "A"),
                _resolve_non_primary_y_label(
                    NodeType.SECOND_DERIVATIVE, x_unit),
            )


class TestResolveYAxisRoleStyleOverride(unittest.TestCase):
    """Phase 4y (CS-50) — per-style ``y_axis`` override hook.

    Pure-helper coverage for the ``style`` short-circuit prepended
    to ``_resolve_y_axis_role`` in Phase 4y. The override is the
    foundation for the CS-50 carry-forward T register entry — a
    StyleDialog Combobox lets the user pin a node to a specific axis
    role independently of its NodeType default. The pre-CS-50
    callers that pass only ``node_type`` (overlay-axis resolvers in
    ``_redraw``) keep their byte-identical behaviour because
    ``style`` defaults to ``None``.
    """

    def test_string_role_override_beats_nodetype_default(self):
        # The canonical override path: a UVVIS node with
        # ``style["y_axis"] = "secondary"`` lands on the secondary
        # axis even though UVVIS defaults to "primary".
        from uvvis_tab import _resolve_y_axis_role
        self.assertEqual(
            _resolve_y_axis_role(NodeType.UVVIS, {"y_axis": "secondary"}),
            "secondary",
        )

    def test_override_can_route_uvvis_to_tertiary(self):
        # Tertiary is wired but unpopulated by the default table
        # (CS-44 lock). A user-facing override is the first
        # production path that lands a node there. Pinned so a
        # future renderer change cannot silently refuse the role.
        from uvvis_tab import _resolve_y_axis_role
        self.assertEqual(
            _resolve_y_axis_role(NodeType.UVVIS, {"y_axis": "tertiary"}),
            "tertiary",
        )

    def test_override_can_send_second_derivative_back_to_primary(self):
        # The "small-magnitude derivative shares parent's scale" case
        # called out in the carry-forward T register entry — a
        # SECOND_DERIVATIVE node with ``style["y_axis"] = "primary"``
        # routes to primary even though the NodeType-default is
        # "secondary".
        from uvvis_tab import _resolve_y_axis_role
        self.assertEqual(
            _resolve_y_axis_role(
                NodeType.SECOND_DERIVATIVE, {"y_axis": "primary"},
            ),
            "primary",
        )

    def test_none_override_falls_through_to_nodetype_default(self):
        # ``None`` is the literal "(default)" Combobox value: a
        # freshly-created node carries ``style["y_axis"] = None``
        # and must route by NodeType default.
        from uvvis_tab import _resolve_y_axis_role
        self.assertEqual(
            _resolve_y_axis_role(NodeType.UVVIS, {"y_axis": None}),
            "primary",
        )
        self.assertEqual(
            _resolve_y_axis_role(
                NodeType.SECOND_DERIVATIVE, {"y_axis": None},
            ),
            "secondary",
        )

    def test_missing_y_axis_key_falls_through(self):
        # An empty style dict (or one that pre-dates CS-50 and lacks
        # the new key) must behave exactly as the no-style path.
        from uvvis_tab import _resolve_y_axis_role
        self.assertEqual(
            _resolve_y_axis_role(NodeType.UVVIS, {}),
            _resolve_y_axis_role(NodeType.UVVIS),
        )
        self.assertEqual(
            _resolve_y_axis_role(NodeType.SECOND_DERIVATIVE, {"color": "#abc"}),
            _resolve_y_axis_role(NodeType.SECOND_DERIVATIVE),
        )

    def test_malformed_override_falls_through(self):
        # A non-string or unknown-string value (saved by a future
        # bug or hand-edited project file) must NOT crash the
        # renderer — the helper falls back to the per-NodeType
        # default. The CS-44 docstring's "future per-style override
        # could surface a malformed value" guard lives in
        # ``get_axis``'s defensive branch, but the helper itself
        # also rejects malformed values rather than echoing them.
        from uvvis_tab import _resolve_y_axis_role
        self.assertEqual(
            _resolve_y_axis_role(NodeType.UVVIS, {"y_axis": "bogus"}),
            "primary",
        )
        self.assertEqual(
            _resolve_y_axis_role(NodeType.UVVIS, {"y_axis": 17}),
            "primary",
        )
        self.assertEqual(
            _resolve_y_axis_role(NodeType.UVVIS, {"y_axis": ""}),
            "primary",
        )

    def test_signature_remains_backwards_compatible(self):
        # The pre-Phase-4y call sites (overlay-axis resolvers in
        # ``_redraw``) pass only the NodeType. The signature
        # extension is additive: every NodeType still resolves
        # without a ``style`` argument.
        from uvvis_tab import _resolve_y_axis_role
        for ntype in (NodeType.UVVIS, NodeType.BASELINE,
                      NodeType.NORMALISED, NodeType.SMOOTHED,
                      NodeType.PEAK_LIST, NodeType.SECOND_DERIVATIVE):
            # No-style call returns a string in _AXIS_ROLES — not
            # an exception — for every renderer NodeType.
            from uvvis_tab import _AXIS_ROLES
            self.assertIn(_resolve_y_axis_role(ntype), _AXIS_ROLES)


# ---------------------------------------------------------------------------
# Phase 4x (CS-49) — cross-type parent acceptance, end-to-end
# ---------------------------------------------------------------------------


@unittest.skipUnless(_HAS_DISPLAY, "Tk display required")
class TestUVVisTabPhase4xCrossTypeAcceptance(unittest.TestCase):
    """End-to-end coverage of the Phase 4x panel-parent widening.

    Closes the user-flagged Phase 4w friction #1 ("Cannot do
    baseline correction from a smoothed spectrum. Cannot smooth
    derivative plots."). Two new workflows must work end-to-end via
    the shared subject combobox:

    1. Smooth → baseline-correct: load UVVIS, smooth it
       (SMOOTHED child), flip the shared subject to the SMOOTHED
       child, click the inline baseline Apply, get a BASELINE child
       parented on the SMOOTHED node.
    2. Second-derivative → smooth: load UVVIS, second-derivative it
       (SECOND_DERIVATIVE child), flip the shared subject to the
       derivative (now visible in the combobox), click the smoothing
       Apply, get a SMOOTHED child parented on the SECOND_DERIVATIVE
       node.

    Plus three audit-stability checks: a SECOND_DERIVATIVE subject
    enables ONLY SmoothingPanel (the other three panels + inline
    baseline stay disabled — those tuples were intentionally NOT
    widened in Phase 4x).
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)
        self.tab.pack(fill=tk.BOTH, expand=True)
        self.tab.update_idletasks()

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    # ---- helpers ----------------------------------------------------

    def _add_uvvis(self, nid: str = "u1") -> str:
        wl = np.linspace(200.0, 800.0, 601)
        absorb = np.exp(-((wl - 500.0) ** 2) / (2.0 * 25.5 ** 2)) + 0.05
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"_load_id": f"L_{nid}", "source_file": f"syn_{nid}"},
            label=nid, state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))
        return nid

    def _select_shared(self, node_id: str) -> None:
        for key, nid in self.tab._shared_subject_map.items():
            if nid == node_id:
                self.tab._shared_subject.set(key)
                self.tab.update_idletasks()
                return
        self.fail(f"node {node_id!r} not in shared subject map")

    # ---- workflow 1: smooth → baseline-correct -------------------

    def test_baseline_apply_on_smoothed_subject_creates_baseline_child(self):
        # Load UVVIS, smooth it via the smoothing panel, flip the
        # shared subject to the SMOOTHED child, configure the
        # baseline section for linear mode with explicit anchors,
        # click Apply.
        from nodes import OperationType
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self.tab._smoothing_panel._mode_var.set("savgol")
        self.tab._smoothing_panel._window_length.set(5)
        self.tab._smoothing_panel._polyorder.set(2)
        _, smoothed_id = self.tab._smoothing_panel._apply()
        self.tab.update_idletasks()
        self._select_shared(smoothed_id)

        # Apply button now enabled (covered by the rewritten
        # test_smoothed_subject_disables_normalise_only above);
        # configure linear mode + go.
        self.tab._baseline_mode.set("linear")
        self.tab._baseline_anchor_lo.set("250")
        self.tab._baseline_anchor_hi.set("750")
        self.tab._refresh_baseline_param_rows()

        n_before = len(self.graph.nodes)
        self.tab._apply_baseline()
        self.tab.update_idletasks()
        n_after = len(self.graph.nodes)
        # Apply produces one OperationNode + one DataNode.
        self.assertEqual(n_after - n_before, 2)

        # Find the new BASELINE node and confirm it is parented on
        # the SMOOTHED node via a single BASELINE op.
        baseline_nodes = [
            n for n in self.graph.nodes_of_type(NodeType.BASELINE,
                                                 state=None)
            if n.metadata.get("baseline_parent_id") == smoothed_id
        ]
        self.assertEqual(len(baseline_nodes), 1,
                         "exactly one BASELINE child of the SMOOTHED "
                         "node must exist after Apply")
        baseline = baseline_nodes[0]
        self.assertEqual(baseline.state, NodeState.PROVISIONAL)
        # Walk the graph: BASELINE DataNode → BASELINE OperationNode → SMOOTHED parent.
        op_parents = self.graph.parents_of(baseline.id)
        self.assertEqual(len(op_parents), 1)
        op = self.graph.get_node(op_parents[0])
        self.assertEqual(op.type, OperationType.BASELINE)
        self.assertEqual(op.input_ids, [smoothed_id])
        # Output type stays BASELINE (the op-natural NodeType).
        self.assertEqual(baseline.type, NodeType.BASELINE)
        # Arrays carry the canonical curve schema.
        self.assertIn("wavelength_nm", baseline.arrays)
        self.assertIn("absorbance", baseline.arrays)

    def test_baseline_dashed_overlay_recovers_baseline_curve_from_smoothed_parent(self):
        # CS-29 dashed overlay walks BASELINE.absorbance =
        # parent.absorbance - baseline_curve. The helper
        # (uvvis_baseline.compute_baseline_curve) is type-agnostic
        # but Phase 4x is the first phase where a SMOOTHED parent
        # is reachable; pin that the helper still returns a (wl,
        # curve) tuple — not None — when the parent is SMOOTHED.
        from uvvis_baseline import compute_baseline_curve
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self.tab._smoothing_panel._mode_var.set("savgol")
        self.tab._smoothing_panel._window_length.set(5)
        self.tab._smoothing_panel._polyorder.set(2)
        _, smoothed_id = self.tab._smoothing_panel._apply()
        self.tab.update_idletasks()
        self._select_shared(smoothed_id)
        self.tab._baseline_mode.set("linear")
        self.tab._baseline_anchor_lo.set("250")
        self.tab._baseline_anchor_hi.set("750")
        self.tab._refresh_baseline_param_rows()
        self.tab._apply_baseline()
        self.tab.update_idletasks()

        baseline = next(
            n for n in self.graph.nodes_of_type(NodeType.BASELINE,
                                                 state=None)
            if n.metadata.get("baseline_parent_id") == smoothed_id
        )
        result = compute_baseline_curve(self.graph, baseline)
        self.assertIsNotNone(result,
                             "compute_baseline_curve must succeed "
                             "with a SMOOTHED parent (Phase 4x)")
        wl, curve = result
        self.assertEqual(wl.shape, curve.shape)

    # ---- workflow 2: second-derivative → smooth -------------------

    def test_smoothing_apply_on_second_derivative_subject_creates_smoothed_child(self):
        # Load UVVIS, derive it, flip the shared subject to the
        # SECOND_DERIVATIVE child (now in the combobox), click
        # smoothing Apply.
        from nodes import OperationType
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        # Apply second-derivative via its panel — the panel is
        # already wired to the shared subject (defaulting to u1).
        _, d2_id = self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()
        # Flip the shared subject to the new derivative.
        self._select_shared(d2_id)
        # SmoothingPanel's Apply button must now be enabled.
        self.assertEqual(
            str(self.tab._smoothing_panel._apply_btn.cget("state")),
            "normal",
            "SmoothingPanel must accept a SECOND_DERIVATIVE subject "
            "after the Phase 4x widening")

        self.tab._smoothing_panel._mode_var.set("savgol")
        self.tab._smoothing_panel._window_length.set(11)
        self.tab._smoothing_panel._polyorder.set(2)
        n_before = len(self.graph.nodes)
        op_id, out_id = self.tab._smoothing_panel._apply()
        n_after = len(self.graph.nodes)
        self.assertEqual(n_after - n_before, 2)

        op = self.graph.get_node(op_id)
        out = self.graph.get_node(out_id)
        self.assertEqual(op.type, OperationType.SMOOTH)
        self.assertEqual(op.input_ids, [d2_id])
        # Output carries the natural op NodeType (SMOOTHED), not
        # the parent's type (SECOND_DERIVATIVE). The y-axis-misroute
        # caveat is the open Phase 4u friction #10 / per-style
        # y_axis override hook.
        self.assertEqual(out.type, NodeType.SMOOTHED)
        self.assertEqual(out.metadata["smoothing_parent_id"], d2_id)

    # ---- audit-stability: SECOND_DERIVATIVE keeps the other
    # ---- panels disabled ----------------------------------------

    def test_second_derivative_subject_disables_non_smoothing_panels(self):
        # With a SECOND_DERIVATIVE subject in the shared combobox,
        # ONLY SmoothingPanel becomes enabled (CS-49 widening).
        # NormalisationPanel, PeakPickingPanel, SecondDerivativePanel,
        # and the inline baseline section all stay disabled — those
        # tuples were intentionally NOT widened in Phase 4x.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        _, d2_id = self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()
        self._select_shared(d2_id)

        self.assertEqual(
            str(self.tab._smoothing_panel._apply_btn.cget("state")),
            "normal",
            "SmoothingPanel — widened in Phase 4x — must enable")
        self.assertEqual(
            str(self.tab._normalisation_panel._apply_btn.cget("state")),
            "disabled",
            "NormalisationPanel — audit-time NOT widened — stays "
            "disabled on a SECOND_DERIVATIVE subject")
        self.assertEqual(
            str(self.tab._peak_picking_panel._apply_btn.cget("state")),
            "disabled",
            "PeakPickingPanel — audit-time NOT widened — stays "
            "disabled on a SECOND_DERIVATIVE subject")
        self.assertEqual(
            str(self.tab._second_derivative_panel._apply_btn.cget("state")),
            "disabled",
            "SecondDerivativePanel — chained derivatives excluded "
            "by audit decision — stays disabled")
        self.assertEqual(
            str(self.tab._apply_baseline_btn.cget("state")),
            "disabled",
            "Inline baseline — Phase 4x added SMOOTHED only, NOT "
            "SECOND_DERIVATIVE — stays disabled")

    # ---- combobox order: spectrum first, then derivative -------

    def test_shared_combobox_orders_spectrum_then_derivative(self):
        # _refresh_shared_subjects walks _spectrum_nodes() FIRST
        # (UVVIS → BASELINE → NORMALISED → SMOOTHED) then
        # _second_derivative_nodes(). This pins the order so a
        # future re-shuffle has to update both the docstring and
        # this test.
        u1 = self._add_uvvis("u1")
        self.tab.update_idletasks()
        _, d2_id = self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertEqual(len(items), 2)
        # First entry maps to UVVIS; last entry maps to
        # SECOND_DERIVATIVE.
        first_id = self.tab._shared_subject_map[items[0]]
        last_id = self.tab._shared_subject_map[items[-1]]
        self.assertEqual(first_id, u1)
        self.assertEqual(last_id, d2_id)
        # NodeType sanity — defends the test against future label
        # collisions.
        self.assertEqual(self.graph.get_node(first_id).type,
                         NodeType.UVVIS)
        self.assertEqual(self.graph.get_node(last_id).type,
                         NodeType.SECOND_DERIVATIVE)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display required")
class TestUVVisTabPhase4yYAxisOverride(unittest.TestCase):
    """Phase 4y (CS-50) — per-style ``y_axis`` override end-to-end.

    Combines the renderer's per-node style threading (commit 3)
    with the user-facing flows: a node carrying
    ``style["y_axis"] = "secondary"`` lands on the secondary axis
    even though its NodeType-default is "primary"; a SECOND_DERIVATIVE
    overridden to "primary" lands on primary; a SmoothingPanel apply
    on a SECOND_DERIVATIVE parent auto-inherits the parent's
    effective role (closes Phase 4x friction #6); the per-row ∀
    fan-out widens its scope to every renderable node.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)
        self.tab.pack(fill=tk.BOTH, expand=True)
        self.tab.update_idletasks()

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    # ---- fixtures ----

    def _add_uvvis(self, nid: str = "u1",
                   y_axis_override: str | None = None) -> str:
        wl = np.linspace(200.0, 800.0, 601)
        absorb = np.exp(-((wl - 500.0) ** 2) / (2.0 * 25.5 ** 2)) + 0.05
        from node_styles import default_spectrum_style
        style = default_spectrum_style("#1f77b4")
        if y_axis_override is not None:
            style["y_axis"] = y_axis_override
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"_load_id": f"L_{nid}", "source_file": f"syn_{nid}"},
            label=nid, state=NodeState.COMMITTED,
            style=style,
        ))
        return nid

    def _select_shared(self, node_id: str) -> None:
        for key, nid in self.tab._shared_subject_map.items():
            if nid == node_id:
                self.tab._shared_subject.set(key)
                self.tab.update_idletasks()
                return
        self.fail(f"node {node_id!r} not in shared subject map")

    # ---- override routes UVVIS to secondary ----

    def test_uvvis_with_secondary_override_renders_on_secondary(self):
        # A UVVIS node with ``style["y_axis"] = "secondary"`` lands
        # on the secondary axis even though its NodeType-default is
        # "primary". Pre-CS-50 the override was unread; the renderer
        # now threads ``node.style`` into ``_resolve_y_axis_role``.
        self._add_uvvis("u1", y_axis_override="secondary")
        self.tab._redraw()
        self.tab.update_idletasks()
        self.assertIn("secondary", self.tab._axes_by_role)
        sec = self.tab._axes_by_role["secondary"]
        self.assertEqual(len(sec.get_lines()), 1)
        # Primary stays empty of node lines (the override removed
        # the only spectrum from the primary axis).
        self.assertEqual(len(self.tab._ax.get_lines()), 0)

    def test_uvvis_with_default_renders_on_primary_unchanged(self):
        # The freshly-created default ``style["y_axis"] = None``
        # must preserve pre-CS-50 routing exactly — no secondary
        # axis at all when only UVVIS is present.
        self._add_uvvis("u1")
        self.tab._redraw()
        self.tab.update_idletasks()
        self.assertNotIn("secondary", self.tab._axes_by_role)
        self.assertEqual(len(self.tab._ax.get_lines()), 1)

    def test_second_derivative_override_can_route_back_to_primary(self):
        # The carry-forward T register entry's "small-magnitude
        # derivative shares parent's scale" case: a SECOND_DERIVATIVE
        # overridden to "primary" lands on primary.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        # Apply second-derivative panel to create the derivative.
        _, deriv_id = self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()
        # Override the derivative to primary.
        self.graph.set_style(deriv_id, {"y_axis": "primary"})
        self.tab._redraw()
        self.tab.update_idletasks()
        # No secondary axis: both nodes route to primary now.
        self.assertNotIn("secondary", self.tab._axes_by_role)
        self.assertEqual(len(self.tab._ax.get_lines()), 2)

    # ---- baseline-curve overlay follows the per-node override ----

    def test_baseline_overlay_follows_per_node_y_axis_override(self):
        # CS-29 dashed overlay follows the BASELINE node's effective
        # axis after Phase 4y — the overlay's get_axis(role) call
        # threads the BASELINE node's style. A BASELINE overridden to
        # "secondary" puts both its main render AND its dashed
        # overlay on the secondary axis.
        from nodes import OperationType
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self.tab._baseline_mode.set("linear")
        self.tab._baseline_anchor_lo.set("250")
        self.tab._baseline_anchor_hi.set("750")
        self.tab._refresh_baseline_param_rows()
        # Walk the existing inline baseline Apply path. The helper
        # returns (op_id, baseline_id) — unpack and address the
        # data-side child.
        _op_id, baseline_id = self.tab._apply_baseline()
        self.tab.update_idletasks()
        self.graph.set_style(baseline_id, {"y_axis": "secondary"})
        self.tab._redraw()
        self.tab.update_idletasks()
        self.assertIn("secondary", self.tab._axes_by_role)
        sec_lines = self.tab._axes_by_role["secondary"].get_lines()
        # Two lines on secondary: the main BASELINE render + the
        # dashed overlay. Without the per-bn threading the overlay
        # would land on primary while the main render landed on
        # secondary — visually broken.
        self.assertEqual(len(sec_lines), 2)
        # One must carry the dashed linestyle (the overlay).
        styles = [ln.get_linestyle() for ln in sec_lines]
        self.assertIn("--", styles)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display required")
class TestUVVisTabPhase4yCrossTypedInheritance(unittest.TestCase):
    """Phase 4y (CS-50) — cross-typed-Apply ``y_axis`` inheritance.

    SmoothingPanel's CS-49 widening accepts a SECOND_DERIVATIVE
    parent. Without inheritance the resulting SMOOTHED node routes
    to primary (NodeType default) — the visually-broken case Phase
    4x friction #6 documented. Decision (i) of this session: the
    apply-time code on ``SmoothingPanel._apply`` auto-sets
    ``style["y_axis"]`` on the new node to the parent's effective
    role when (and only when) the NodeType defaults differ.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)
        self.tab.pack(fill=tk.BOTH, expand=True)
        self.tab.update_idletasks()

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str = "u1") -> str:
        wl = np.linspace(200.0, 800.0, 601)
        absorb = np.exp(-((wl - 500.0) ** 2) / (2.0 * 25.5 ** 2)) + 0.05
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"_load_id": f"L_{nid}", "source_file": f"syn_{nid}"},
            label=nid, state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08,
                   "y_axis": None},
        ))
        return nid

    def _select_shared(self, node_id: str) -> None:
        for key, nid in self.tab._shared_subject_map.items():
            if nid == node_id:
                self.tab._shared_subject.set(key)
                self.tab.update_idletasks()
                return
        self.fail(f"node {node_id!r} not in shared subject map")

    # ---- inheritance fires when defaults differ ----

    def test_smoothed_of_second_derivative_inherits_secondary(self):
        # The Phase 4x friction #6 case: smooth a SECOND_DERIVATIVE.
        # NodeType defaults differ (SMOOTHED → primary,
        # SECOND_DERIVATIVE → secondary), so the apply-time hook
        # writes ``style["y_axis"] = "secondary"`` onto the new
        # SMOOTHED node so it renders alongside its parent.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        _, deriv_id = self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()
        self._select_shared(deriv_id)
        self.tab._smoothing_panel._mode_var.set("savgol")
        self.tab._smoothing_panel._window_length.set(5)
        self.tab._smoothing_panel._polyorder.set(2)
        _, smoothed_id = self.tab._smoothing_panel._apply()
        self.tab.update_idletasks()
        smoothed = self.graph.get_node(smoothed_id)
        self.assertEqual(smoothed.style.get("y_axis"), "secondary")
        # The renderer routes accordingly.
        self.tab._redraw()
        self.tab.update_idletasks()
        self.assertIn("secondary", self.tab._axes_by_role)
        sec_lines = self.tab._axes_by_role["secondary"].get_lines()
        # Both the SECOND_DERIVATIVE parent and the SMOOTHED child
        # land on secondary — two lines.
        self.assertEqual(len(sec_lines), 2)

    def test_smoothed_of_uvvis_does_not_set_y_axis(self):
        # Same-default case (UVVIS → primary, SMOOTHED → primary):
        # the inheritance hook leaves ``style["y_axis"] = None`` so
        # future routing-table edits propagate cleanly.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self.tab._smoothing_panel._mode_var.set("savgol")
        self.tab._smoothing_panel._window_length.set(5)
        self.tab._smoothing_panel._polyorder.set(2)
        _, smoothed_id = self.tab._smoothing_panel._apply()
        self.tab.update_idletasks()
        self.assertIsNone(self.graph.get_node(smoothed_id).style.get("y_axis"))

    def test_smoothed_inherits_parent_override_not_just_default(self):
        # Parent's *effective* role drives the decision: a UVVIS with
        # an explicit override to "secondary" smooths into a
        # SMOOTHED child that also lands on "secondary".
        from node_styles import default_spectrum_style
        wl = np.linspace(200.0, 800.0, 601)
        absorb = np.exp(-((wl - 500.0) ** 2) / (2.0 * 25.5 ** 2)) + 0.05
        style = default_spectrum_style("#1f77b4")
        style["y_axis"] = "secondary"
        self.graph.add_node(DataNode(
            id="u2", type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"_load_id": "L_u2", "source_file": "syn_u2"},
            label="u2", state=NodeState.COMMITTED,
            style=style,
        ))
        self.tab.update_idletasks()
        self._select_shared("u2")
        self.tab._smoothing_panel._mode_var.set("savgol")
        self.tab._smoothing_panel._window_length.set(5)
        self.tab._smoothing_panel._polyorder.set(2)
        _, smoothed_id = self.tab._smoothing_panel._apply()
        self.tab.update_idletasks()
        # SMOOTHED's NodeType-default is primary; the parent's
        # effective role is secondary; the hook writes "secondary".
        self.assertEqual(
            self.graph.get_node(smoothed_id).style.get("y_axis"),
            "secondary",
        )


@unittest.skipUnless(_HAS_DISPLAY, "Tk display required")
class TestUVVisTabPhase4yApplyToAllScope(unittest.TestCase):
    """Phase 4y (CS-50) — per-row ∀ widens for ``y_axis``.

    Per Decision (iii): the per-row ∀ button next to the StyleDialog
    Combobox writes the chosen role to **every renderable node**
    (UVVIS / BASELINE / NORMALISED / SMOOTHED / SECOND_DERIVATIVE /
    PEAK_LIST). Other style keys preserve the existing
    ``_spectrum_nodes()`` (UVVIS + BASELINE + NORMALISED + SMOOTHED)
    scope so a linewidth ∀ does not silently rewrite annotation
    overlays.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)
        self.tab.pack(fill=tk.BOTH, expand=True)
        self.tab.update_idletasks()

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str = "u1") -> str:
        wl = np.linspace(200.0, 800.0, 601)
        absorb = np.exp(-((wl - 500.0) ** 2) / (2.0 * 25.5 ** 2)) + 0.05
        from node_styles import default_spectrum_style
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"_load_id": f"L_{nid}", "source_file": f"syn_{nid}"},
            label=nid, state=NodeState.COMMITTED,
            style=default_spectrum_style("#1f77b4"),
        ))
        return nid

    def test_y_axis_fans_out_to_second_derivative_too(self):
        # A UVVIS + a SECOND_DERIVATIVE child. Fan-out scope for
        # ``y_axis`` includes the derivative, even though it's not
        # in ``_spectrum_nodes``.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        _, deriv_id = self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()
        self.tab._on_uvvis_apply_to_all("y_axis", "secondary")
        self.assertEqual(
            self.graph.get_node("u1").style.get("y_axis"), "secondary"
        )
        self.assertEqual(
            self.graph.get_node(deriv_id).style.get("y_axis"), "secondary"
        )

    def test_y_axis_fans_out_to_peak_list_too(self):
        # Add a PEAK_LIST node by running peak-picking on the UVVIS.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        _, peak_id = self.tab._peak_picking_panel._apply()
        self.tab.update_idletasks()
        self.tab._on_uvvis_apply_to_all("y_axis", "tertiary")
        self.assertEqual(
            self.graph.get_node(peak_id).style.get("y_axis"), "tertiary"
        )

    def test_other_keys_preserve_spectrum_only_scope(self):
        # A linewidth fan-out hits UVVIS (in _spectrum_nodes) but
        # NOT the SECOND_DERIVATIVE (outside it). Pinning the
        # narrower scope so a future widening lands deliberately.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        _, deriv_id = self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()
        # Snapshot the derivative's pre-fan-out linewidth.
        original_lw = self.graph.get_node(deriv_id).style.get("linewidth", 1.5)
        self.tab._on_uvvis_apply_to_all("linewidth", 3.5)
        # UVVIS got the new value.
        self.assertAlmostEqual(
            self.graph.get_node("u1").style.get("linewidth"), 3.5
        )
        # SECOND_DERIVATIVE kept its original value (untouched
        # because it's outside _spectrum_nodes).
        self.assertAlmostEqual(
            self.graph.get_node(deriv_id).style.get("linewidth", original_lw),
            original_lw,
        )


class TestUVVisTabPerAxisRangeScalePhase4am(unittest.TestCase):
    """CS-64 (Phase 4am) — per-axis range / autoscale / scale renderer wiring.

    Each per-axis role (primary_x / secondary_x / primary_y /
    secondary_y / tertiary_y) reads its own ``cfg["axes"][role]``
    slot in ``_redraw``. The legacy top-bar ``_xlim_lo`` /
    ``_xlim_hi`` / ``_ylim_lo`` / ``_ylim_hi`` Tk vars remain the
    fallback for primary_x / primary_y when ``autoscale=True``
    (default); ``autoscale=False`` makes the schema range_lo /
    range_hi bounds win.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str = "u1") -> DataNode:
        wl = np.linspace(300, 600, 10)
        absorb = np.linspace(0.1, 0.9, 10)
        node = DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label=nid,
            state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        )
        self.graph.add_node(node)
        return node

    def _add_second_derivative(self, nid: str = "d1") -> DataNode:
        wl = np.linspace(300, 600, 10)
        absorb = np.linspace(-0.01, 0.01, 10)
        node = DataNode(
            id=nid, type=NodeType.SECOND_DERIVATIVE,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label=nid,
            state=NodeState.COMMITTED,
            style={"color": "#ff7f0e", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        )
        self.graph.add_node(node)
        return node

    # ---- module-level helpers ----

    def test_per_axis_range_reads_string(self):
        import uvvis_tab
        cfg = {"axes": {"primary_y": {"range_lo": "0.25"}}}
        self.assertEqual(
            uvvis_tab._per_axis_range(cfg, "primary_y", "range_lo"),
            "0.25",
        )

    def test_per_axis_range_missing_returns_empty(self):
        import uvvis_tab
        self.assertEqual(
            uvvis_tab._per_axis_range({}, "primary_y", "range_lo"),
            "",
        )

    def test_per_axis_autoscale_defaults_to_true(self):
        import uvvis_tab
        self.assertIs(uvvis_tab._per_axis_autoscale({}, "primary_y"), True)

    def test_per_axis_autoscale_reads_false(self):
        import uvvis_tab
        cfg = {"axes": {"primary_y": {"autoscale": False}}}
        self.assertIs(uvvis_tab._per_axis_autoscale(cfg, "primary_y"), False)

    def test_per_axis_scale_defaults_to_linear(self):
        import uvvis_tab
        self.assertEqual(uvvis_tab._per_axis_scale({}, "primary_y"), "linear")

    def test_per_axis_scale_reads_log(self):
        import uvvis_tab
        cfg = {"axes": {"primary_y": {"scale": "log"}}}
        self.assertEqual(uvvis_tab._per_axis_scale(cfg, "primary_y"), "log")

    def test_per_axis_scale_rejects_unknown(self):
        import uvvis_tab
        cfg = {"axes": {"primary_y": {"scale": "symlog"}}}
        # Defensive fallback: unknown scale → "linear".
        self.assertEqual(uvvis_tab._per_axis_scale(cfg, "primary_y"), "linear")

    def test_parse_lim_str_empty_returns_none(self):
        import uvvis_tab
        self.assertIsNone(uvvis_tab._parse_lim_str(""))
        self.assertIsNone(uvvis_tab._parse_lim_str("   "))

    def test_parse_lim_str_garbage_returns_none(self):
        import uvvis_tab
        self.assertIsNone(uvvis_tab._parse_lim_str("not a number"))

    def test_parse_lim_str_valid_returns_float(self):
        import uvvis_tab
        self.assertEqual(uvvis_tab._parse_lim_str("0.5"), 0.5)
        self.assertEqual(uvvis_tab._parse_lim_str(" -1.25 "), -1.25)

    # ---- renderer wiring: primary_y range + autoscale ----

    def test_primary_y_autoscale_false_uses_schema_range(self):
        self._add_uvvis()
        self.tab._plot_config = {
            "axes": {
                "primary_y": {
                    "range_lo": "0.2", "range_hi": "0.8",
                    "autoscale": False, "scale": "linear",
                },
            },
        }
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        lo, hi = ax.get_ylim()
        self.assertAlmostEqual(lo, 0.2, places=6)
        self.assertAlmostEqual(hi, 0.8, places=6)

    def test_primary_y_autoscale_true_ignores_schema_range(self):
        self._add_uvvis()
        # Schema range present but autoscale=True → renderer falls
        # back to legacy top-bar Tk vars (which are empty), so no
        # clamp is applied and matplotlib autoscales.
        self.tab._plot_config = {
            "axes": {
                "primary_y": {
                    "range_lo": "0.2", "range_hi": "0.8",
                    "autoscale": True, "scale": "linear",
                },
            },
        }
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        lo, hi = ax.get_ylim()
        # Autoscale picks data extents (0.1, 0.9) with matplotlib's
        # default margin padding, NOT the schema's 0.2/0.8 clamp.
        self.assertLess(lo, 0.2)
        self.assertGreater(hi, 0.8)

    def test_primary_y_autoscale_true_honours_legacy_top_bar(self):
        self._add_uvvis()
        self.tab._ylim_lo.set("0.3")
        self.tab._ylim_hi.set("0.7")
        # Default schema (autoscale=True) → legacy top-bar wins.
        self.tab._plot_config = {}
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        lo, hi = ax.get_ylim()
        self.assertAlmostEqual(lo, 0.3, places=6)
        self.assertAlmostEqual(hi, 0.7, places=6)

    # ---- renderer wiring: primary_y scale ----

    def test_primary_y_scale_log_applied(self):
        self._add_uvvis()
        self.tab._plot_config = {
            "axes": {"primary_y": {"scale": "log"}},
        }
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        self.assertEqual(ax.get_yscale(), "log")

    def test_primary_y_scale_linear_default(self):
        self._add_uvvis()
        self.tab._plot_config = {}
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        self.assertEqual(ax.get_yscale(), "linear")

    # ---- renderer wiring: primary_x scale ----

    def test_primary_x_scale_log_applied(self):
        self._add_uvvis()
        self.tab._plot_config = {
            "axes": {"primary_x": {"scale": "log"}},
        }
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        self.assertEqual(ax.get_xscale(), "log")

    # ---- twin Y-axes ----

    def test_secondary_y_range_applied_to_twin_axis(self):
        self._add_uvvis()
        self._add_second_derivative()
        self.tab._plot_config = {
            "axes": {
                "secondary_y": {
                    "range_lo": "-2.5", "range_hi": "2.5",
                    "autoscale": False, "scale": "linear",
                },
            },
        }
        self.tab._redraw()
        twin = self.tab._axes_by_role.get("secondary")
        self.assertIsNotNone(twin, "secondary_y twin axis should exist")
        lo, hi = twin.get_ylim()
        self.assertAlmostEqual(lo, -2.5, places=6)
        self.assertAlmostEqual(hi, 2.5, places=6)

    def test_secondary_y_scale_log_applied_to_twin_axis(self):
        self._add_uvvis()
        self._add_second_derivative()
        self.tab._plot_config = {
            "axes": {"secondary_y": {"scale": "log"}},
        }
        self.tab._redraw()
        twin = self.tab._axes_by_role.get("secondary")
        self.assertIsNotNone(twin)
        self.assertEqual(twin.get_yscale(), "log")

    # ---- empty-bound semantics ----

    def test_primary_y_autoscale_false_with_only_lo_leaves_hi(self):
        self._add_uvvis()
        self.tab._plot_config = {
            "axes": {
                "primary_y": {
                    "range_lo": "0.4", "range_hi": "",
                    "autoscale": False, "scale": "linear",
                },
            },
        }
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        lo, hi = ax.get_ylim()
        self.assertAlmostEqual(lo, 0.4, places=6)
        # hi end was empty → no clamp → matplotlib autoscale-ish high
        self.assertGreater(hi, 0.4)

    # ---- defensive: missing axes sub-dict doesn't crash ----

    def test_missing_axes_subdict_does_not_crash(self):
        self._add_uvvis()
        self.tab._plot_config = {}
        # Should not raise.
        self.tab._redraw()


@unittest.skipUnless(_root is not None, "Tk root unavailable")
class TestUVVisTabPerAxisPolishPhase4an(unittest.TestCase):
    """CS-65 (Phase 4an) — per-axis tick spacing + grid + colour
    renderer wiring.

    Tick spacing applies via matplotlib.ticker.MultipleLocator; empty
    string / garbage / non-positive values fall back to matplotlib's
    auto-locator. Per-axis grid_show toggles x- and y- grids on the
    primary independently. Axis colour applies to the per-role spine
    + tick params + axis-label.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str = "u1") -> DataNode:
        wl = np.linspace(300, 600, 10)
        absorb = np.linspace(0.1, 0.9, 10)
        node = DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label=nid,
            state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        )
        self.graph.add_node(node)
        return node

    def _add_second_derivative(self, nid: str = "d1") -> DataNode:
        wl = np.linspace(300, 600, 10)
        absorb = np.linspace(-0.01, 0.01, 10)
        node = DataNode(
            id=nid, type=NodeType.SECOND_DERIVATIVE,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "synthetic"},
            label=nid,
            state=NodeState.COMMITTED,
            style={"color": "#ff7f0e", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        )
        self.graph.add_node(node)
        return node

    # ---- tick spacing ----

    def test_primary_x_tick_major_applies_multiplelocator(self):
        from matplotlib.ticker import MultipleLocator
        self._add_uvvis()
        self.tab._plot_config = {
            "axes": {"primary_x": {"tick_major": "50"}},
        }
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        locator = ax.xaxis.get_major_locator()
        self.assertIsInstance(locator, MultipleLocator)
        # MultipleLocator picks ticks at integer multiples of its
        # base; tick_values(0, 200) returns [0, 50, 100, 150, 200].
        ticks = locator.tick_values(0, 200)
        self.assertAlmostEqual(float(ticks[1] - ticks[0]), 50.0)

    def test_primary_y_tick_minor_applies_multiplelocator(self):
        from matplotlib.ticker import MultipleLocator
        self._add_uvvis()
        self.tab._plot_config = {
            "axes": {"primary_y": {"tick_minor": "0.05"}},
        }
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        locator = ax.yaxis.get_minor_locator()
        self.assertIsInstance(locator, MultipleLocator)

    def test_empty_tick_major_keeps_auto_locator(self):
        from matplotlib.ticker import MultipleLocator
        self._add_uvvis()
        self.tab._plot_config = {
            "axes": {"primary_x": {"tick_major": ""}},
        }
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        # Auto-locator is NOT MultipleLocator.
        self.assertNotIsInstance(
            ax.xaxis.get_major_locator(), MultipleLocator,
        )

    def test_garbage_tick_major_keeps_auto_locator(self):
        from matplotlib.ticker import MultipleLocator
        self._add_uvvis()
        self.tab._plot_config = {
            "axes": {"primary_x": {"tick_major": "not a number"}},
        }
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        self.assertNotIsInstance(
            ax.xaxis.get_major_locator(), MultipleLocator,
        )

    def test_non_positive_tick_major_keeps_auto_locator(self):
        from matplotlib.ticker import MultipleLocator
        self._add_uvvis()
        for bad in ("0", "-3.5"):
            self.tab._plot_config = {
                "axes": {"primary_x": {"tick_major": bad}},
            }
            self.tab._redraw()
            ax = self.tab._axes_by_role["primary"]
            self.assertNotIsInstance(
                ax.xaxis.get_major_locator(), MultipleLocator,
                msg=f"tick_major={bad!r} should reject",
            )

    def test_secondary_y_tick_major_applies_to_twin_axis(self):
        from matplotlib.ticker import MultipleLocator
        self._add_uvvis()
        self._add_second_derivative()
        self.tab._plot_config = {
            "axes": {"secondary_y": {"tick_major": "0.005"}},
        }
        self.tab._redraw()
        twin = self.tab._axes_by_role.get("secondary")
        self.assertIsNotNone(twin)
        self.assertIsInstance(
            twin.yaxis.get_major_locator(), MultipleLocator,
        )

    # ---- per-axis grid ----

    def test_primary_x_grid_default_true_paints_x_grid(self):
        self._add_uvvis()
        self.tab._plot_config = {}
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        # Default: grid_show=True for primary_x → x-grid major gridlines
        # are visible.
        x_visible = any(
            gl.get_visible() for gl in ax.xaxis.get_gridlines()
        )
        self.assertTrue(x_visible)

    def test_primary_x_grid_show_false_disables_x_grid(self):
        self._add_uvvis()
        self.tab._plot_config = {
            "axes": {"primary_x": {"grid_show": False}},
            "grid": True,
        }
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        x_visible = any(
            gl.get_visible() for gl in ax.xaxis.get_gridlines()
        )
        self.assertFalse(x_visible)

    def test_primary_y_grid_show_false_keeps_x_grid(self):
        # Independence: turning off the y-grid leaves the x-grid alone.
        self._add_uvvis()
        self.tab._plot_config = {
            "axes": {
                "primary_x": {"grid_show": True},
                "primary_y": {"grid_show": False},
            },
            "grid": True,
        }
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        x_visible = any(
            gl.get_visible() for gl in ax.xaxis.get_gridlines()
        )
        y_visible = any(
            gl.get_visible() for gl in ax.yaxis.get_gridlines()
        )
        self.assertTrue(x_visible)
        self.assertFalse(y_visible)

    def test_global_grid_false_overrides_per_axis_true(self):
        # Master switch wins.
        self._add_uvvis()
        self.tab._plot_config = {
            "axes": {
                "primary_x": {"grid_show": True},
                "primary_y": {"grid_show": True},
            },
            "grid": False,
        }
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        x_visible = any(
            gl.get_visible() for gl in ax.xaxis.get_gridlines()
        )
        y_visible = any(
            gl.get_visible() for gl in ax.yaxis.get_gridlines()
        )
        self.assertFalse(x_visible)
        self.assertFalse(y_visible)

    # ---- axis colour ----

    def test_primary_x_axis_color_sets_bottom_spine(self):
        self._add_uvvis()
        self.tab._plot_config = {
            "axes": {"primary_x": {"axis_color": "#ff0000"}},
        }
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        spine_color = ax.spines["bottom"].get_edgecolor()
        # matplotlib returns RGBA tuple; compare R/G/B components.
        self.assertAlmostEqual(spine_color[0], 1.0, places=2)
        self.assertAlmostEqual(spine_color[1], 0.0, places=2)
        self.assertAlmostEqual(spine_color[2], 0.0, places=2)

    def test_primary_y_axis_color_sets_left_spine(self):
        self._add_uvvis()
        self.tab._plot_config = {
            "axes": {"primary_y": {"axis_color": "#00cc00"}},
        }
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        spine_color = ax.spines["left"].get_edgecolor()
        self.assertAlmostEqual(spine_color[0], 0.0, places=2)
        self.assertGreater(spine_color[1], 0.5)
        self.assertAlmostEqual(spine_color[2], 0.0, places=2)

    def test_secondary_y_axis_color_sets_right_spine(self):
        self._add_uvvis()
        self._add_second_derivative()
        self.tab._plot_config = {
            "axes": {"secondary_y": {"axis_color": "#0000ff"}},
        }
        self.tab._redraw()
        twin = self.tab._axes_by_role.get("secondary")
        self.assertIsNotNone(twin)
        spine_color = twin.spines["right"].get_edgecolor()
        self.assertAlmostEqual(spine_color[2], 1.0, places=2)

    def test_axis_color_sets_axis_label_color(self):
        self._add_uvvis()
        self.tab._plot_config = {
            "axes": {"primary_y": {"axis_color": "#aa00aa"}},
        }
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        label_color = ax.yaxis.label.get_color()
        self.assertEqual(label_color, "#aa00aa")

    # ---- order: scale BEFORE colour preserves the colour ----

    def test_scale_then_colour_order_preserves_colour(self):
        # Re-set scale at the call site doesn't reset the spine
        # colour because colour is applied AFTER scale.
        self._add_uvvis()
        self.tab._plot_config = {
            "axes": {
                "primary_y": {
                    "scale": "log", "axis_color": "#ff8800",
                    "range_lo": "0.1", "range_hi": "1.0",
                    "autoscale": False,
                },
            },
        }
        self.tab._redraw()
        ax = self.tab._axes_by_role["primary"]
        self.assertEqual(ax.get_yscale(), "log")
        spine_color = ax.spines["left"].get_edgecolor()
        self.assertAlmostEqual(spine_color[0], 1.0, places=2)
        self.assertGreater(spine_color[1], 0.3)

    # ---- defensive ----

    def test_missing_polish_keys_do_not_crash(self):
        self._add_uvvis()
        # No "axes" sub-dict at all.
        self.tab._plot_config = {}
        self.tab._redraw()
        # axes sub-dict present but polish keys missing.
        self.tab._plot_config = {"axes": {"primary_x": {}}}
        self.tab._redraw()


# =====================================================================
# CS-68 Phase 4ap — live-preview × CS-66 modeless integration
# =====================================================================


class TestUVVisTabLivePreviewModelessPhase4ap(unittest.TestCase):
    """Integration: modeless Plot Settings (CS-66) + live-preview (CS-68).

    Phase 4ao friction #9 surfaced an uncovered flow: with Plot
    Settings open AND no global Baseline-curves gate, the user can
    toggle a per-row ``~`` in ScanTreeWidget and the canvas should
    redraw while the dialog stays open. Phase 4ap (CS-68) adds a
    second uncovered flow: a discrete edit IN the dialog (e.g. a
    Combobox change) commits live to the host's plot config and
    redraws the host's canvas without an Apply gesture.
    """

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        import plot_settings_dialog
        cls.UVVisTab = UVVisTab
        cls.psd = plot_settings_dialog

    def setUp(self):
        from nodes import OperationNode, OperationType
        self.OperationNode = OperationNode
        self.OperationType = OperationType
        self.psd._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)
        self.tab._x_unit.set("nm")

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis_with_baseline(self):
        """Build a UVVIS parent + BASELINE child graph for canvas tests."""
        wl = np.linspace(300.0, 600.0, 6)
        parent_abs = np.array([1.0, 1.5, 2.0, 1.8, 1.4, 0.9])
        baseline_function = np.array([0.4, 0.5, 0.6, 0.55, 0.45, 0.3])
        child_abs = parent_abs - baseline_function
        parent = DataNode(
            id="p1", type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": parent_abs},
            metadata={"source_file": "synthetic"},
            label="parent-spec",
            state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True},
        )
        op = self.OperationNode(
            id="op1", type=self.OperationType.BASELINE,
            engine="internal", engine_version="test",
            params={"mode": "linear"},
            input_ids=["p1"], output_ids=["c1"],
            status="SUCCESS", state=NodeState.COMMITTED,
        )
        child = DataNode(
            id="c1", type=NodeType.BASELINE,
            arrays={"wavelength_nm": wl, "absorbance": child_abs},
            metadata={}, label="parent · baseline (linear)",
            state=NodeState.COMMITTED,
            style={"color": "#ff7f0e", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True},
        )
        self.graph.add_node(parent)
        self.graph.add_node(op)
        self.graph.add_node(child)
        self.graph.add_edge("p1", "op1")
        self.graph.add_edge("op1", "c1")

    def _open_plot_settings(self):
        """Open Plot Settings via the host's wired callback (CS-66 modeless)."""
        # The host wires open via _on_open_plot_settings; calling
        # the underlying factory directly with the same arguments
        # mirrors that path without depending on a button click.
        return self.psd.open_plot_config_dialog(
            self.tab,
            self.tab._plot_config,
            on_apply=self.tab._on_plot_config_changed,
        )

    # ---- Modeless × per-row toggle redraw (CS-66 friction #9) ----

    def test_per_row_toggle_redraws_canvas_with_dialog_open(self):
        """Toggle CS-36 ~ on a BASELINE row → canvas redraws → dialog still open."""
        self._add_uvvis_with_baseline()
        self.tab._redraw()
        # Pre-check: dashed overlay present.
        self.assertTrue(any(
            ln.get_linestyle() == "--"
            for ln in self.tab._ax.get_lines()
        ))

        dlg = self._open_plot_settings()
        try:
            self.assertEqual(int(dlg.winfo_exists()), 1)

            # Toggle the per-row ~ off (CS-36 mutation routes through
            # set_style → GraphEvent.NODE_STYLE_CHANGED → tab._redraw).
            self.graph.set_style("c1", {"show_baseline_curve": False})

            # Dialog still alive (CS-66 modeless contract).
            self.assertEqual(int(dlg.winfo_exists()), 1)
            # Canvas redrew without the dashed overlay.
            self.assertFalse(any(
                ln.get_linestyle() == "--"
                for ln in self.tab._ax.get_lines()
            ), "per-row ~ toggle off should hide the dashed overlay")
        finally:
            dlg.destroy()

    # ---- Live-preview from inside the dialog (CS-68) ----

    def test_dialog_combobox_edit_commits_live_to_host_config(self):
        """Combobox edit in Plot Settings commits live to tab._plot_config."""
        self._add_uvvis_with_baseline()
        self.tab._plot_config["legend_position"] = "best"
        self.tab._redraw()

        dlg = self._open_plot_settings()
        try:
            # Discrete-widget edit fires _on_var_write →
            # _apply_changes_live → tab._on_plot_config_changed →
            # tab._redraw. The host's plot_config dict carries the
            # new value because PlotConfigDialog's _config IS that
            # dict (mutated in place).
            dlg._control_vars["legend_position"].set("upper right")
            dlg.update_idletasks()
            self.assertEqual(
                self.tab._plot_config["legend_position"], "upper right",
                "CS-68 live-preview must mirror discrete-widget edits "
                "into the host's plot_config dict",
            )
            # Dialog stays open (no commit-and-close behaviour).
            self.assertEqual(int(dlg.winfo_exists()), 1)
        finally:
            dlg.destroy()

    def test_dialog_cancel_reverts_after_live_edits(self):
        """Cancel reverts every live edit via the __init__ snapshot."""
        self._add_uvvis_with_baseline()
        self.tab._plot_config["legend_position"] = "best"
        self.tab._redraw()

        dlg = self._open_plot_settings()
        try:
            dlg._control_vars["legend_position"].set("lower left")
            dlg.update_idletasks()
            self.assertEqual(
                self.tab._plot_config["legend_position"], "lower left",
            )
            # Cancel reverts via _snapshot.
            dlg._do_cancel()
            self.assertEqual(
                self.tab._plot_config["legend_position"], "best",
                "Cancel must revert live-applied edits via _snapshot",
            )
        finally:
            try:
                dlg.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
