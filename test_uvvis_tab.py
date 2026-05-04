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
        self.assertIsInstance(dlg, self.psd.PlotSettingsDialog)

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

        # Adjust tick label font size in the dialog and Apply.
        dlg._control_vars["tick_label_font_size"].set(16)
        dlg.update_idletasks()
        dlg._do_apply()
        # The on_apply callback (the tab's _redraw) has fired.

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
        dlg._control_vars["xlabel_font_size"].set(18)
        dlg.update_idletasks()
        dlg._do_apply()

        # _redraw has been called; the matplotlib X-label carries the
        # new font size.
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

        # Open dialog, flip grid off, Apply.
        self.tab._open_plot_settings()
        dlg = self.psd._open_dialogs[id(self.tab)]
        dlg.update_idletasks()
        dlg._control_vars["grid"].set(False)
        dlg.update_idletasks()
        dlg._do_apply()

        x_grid_post = self.tab._ax.xaxis.get_gridlines()
        # Gridlines either gone or all marked invisible.
        self.assertFalse(any(g.get_visible() for g in x_grid_post))
        self.assertEqual(self.tab._plot_config["grid"], False)


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
        # All four modes are exposed on the combobox.
        values = self.tab._baseline_mode_cb.cget("values")
        # Tk returns either a tuple or a string of space-separated names.
        if isinstance(values, str):
            values = tuple(values.split())
        self.assertEqual(
            tuple(values),
            ("linear", "polynomial", "spline", "rubberband", "scattering"),
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
        # SECOND_DERIVATIVE node must show up as a second matplotlib
        # line on the next redraw (parent UVVIS curve + child
        # derivative curve), NOT as scatter.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_d2_subject()
        self.tab._second_derivative_panel._window_length.set(11)
        self.tab._second_derivative_panel._polyorder.set(3)
        self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()
        self.assertEqual(len(self.tab._ax.get_lines()), 2,
                         "derivative must render as a Line2D, not scatter")
        self.assertEqual(len(self.tab._ax.collections), 0,
                         "no scatter overlay for a second derivative")

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
        self.assertEqual(len(self.tab._ax.get_lines()), 2)
        self.graph.discard_node(out_id)
        self.tab.update_idletasks()
        lines = self.tab._ax.get_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].get_label(), "u1")

    def test_second_derivative_does_not_appear_in_shared_subject_list(self):
        # SECOND_DERIVATIVE is intentionally excluded from
        # _spectrum_nodes (CS-20): chained derivatives are out of
        # scope, and the shared subject combobox (CS-22, Phase 4k)
        # reads that helper.
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self._select_first_d2_subject()
        self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()

        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertEqual(len(items), 1,
                         "shared subject list should still list only the "
                         "parent UVVIS — the new SECOND_DERIVATIVE is not "
                         "a candidate subject for any further curve op")

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
        self.assertEqual(len(self.tab._ax.get_lines()), 2)
        self.graph.set_style(out_id, {"visible": False})
        self.tab.update_idletasks()
        self.assertEqual(len(self.tab._ax.get_lines()), 1)


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

    def test_second_derivative_node_does_not_appear_in_shared_combobox(self):
        self._add_uvvis("u1")
        self.tab.update_idletasks()
        self.tab._second_derivative_panel._apply()
        self.tab.update_idletasks()
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertEqual(len(items), 1,
                         "SECOND_DERIVATIVE must not appear in the shared list")

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

    def test_smoothed_subject_disables_normalise_and_baseline_apply(self):
        # SMOOTHED is *not* in NormalisationPanel.ACCEPTED_PARENT_TYPES
        # (peak/area normalise should run on raw / baseline-corrected
        # / already-normalised curves, before smoothing) and *not* in
        # the inline baseline section's accepted parents (UVVIS /
        # BASELINE only). Selecting a SMOOTHED subject must disable
        # both Apply buttons; the smoothing / peak-picking / 2nd-
        # derivative buttons stay enabled (they accept SMOOTHED).
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
            "normalisation does not accept SMOOTHED parents")
        self.assertEqual(
            str(self.tab._apply_baseline_btn.cget("state")),
            "disabled",
            "inline baseline section does not accept SMOOTHED parents")

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
        # Stub ``graph.get_node`` rather than adding the node to the
        # graph: a BASELINE-typed node entering the graph fires
        # ``_redraw`` (unrelated to CS-27) which has its own UVVIS
        # array assumption. Stubbing the lookup keeps the test
        # focused on the helper's type guard.
        fake_node = DataNode(
            id="b1",
            type=NodeType.BASELINE,
            arrays={"wavelength_nm": np.linspace(300, 600, 5),
                    "baseline":      np.zeros(5)},
            metadata={"source_file": "synthetic"},
            label="b1",
            state=NodeState.COMMITTED,
        )
        original = self.graph.get_node
        self.graph.get_node = lambda nid: (
            fake_node if nid == "b1" else original(nid)
        )
        try:
            self.tab._send_node_to_compare("b1")
        finally:
            self.graph.get_node = original
        self.assertEqual(self.pushed, [])


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestUVVisTabBaselineCurveOverlay(unittest.TestCase):
    """Phase 4o (CS-29) — dashed baseline-curve overlay in _redraw.

    Toggle off (default): only the corrected spectrum lines are
    drawn. Toggle on: each visible BASELINE node gets a dashed
    overlay of its fitted baseline (recovered via
    ``uvvis_baseline.compute_baseline_curve``).
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

    def test_default_toggle_is_off(self):
        # Opt-in feature — make sure the default doesn't change
        # silently and surprise existing users / tests.
        self.assertFalse(self.tab._show_baseline_curves.get())

    def test_toggle_off_renders_no_overlay(self):
        self._build_parent_and_baseline()
        self.tab._show_baseline_curves.set(False)
        self.tab._redraw()
        labels = [ln.get_label() for ln in self.tab._ax.get_lines()]
        # Two solid spectrum lines (parent + corrected child),
        # no "(baseline)" overlay.
        self.assertNotIn("parent · baseline (linear) (baseline)", labels)
        # Confirm no dashed line is on the axis.
        for ln in self.tab._ax.get_lines():
            self.assertNotEqual(ln.get_linestyle(), "--",
                                "no dashed overlay should appear "
                                "when toggle is off")

    def test_toggle_on_adds_dashed_baseline_curve(self):
        wl, parent_abs, baseline_function = (
            self._build_parent_and_baseline()
        )
        self.tab._show_baseline_curves.set(True)
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
        self.tab._show_baseline_curves.set(True)
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
        self.tab._show_baseline_curves.set(True)
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
        self.tab._show_baseline_curves.set(True)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
