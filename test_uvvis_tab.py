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
        from uvvis_tab import UVVisTab, _PALETTE
        cls.UVVisTab = UVVisTab
        cls._PALETTE = _PALETTE

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
        # The button is placed between the legacy "+ Add to TDDFT
        # Overlay" slot (which stands in for the deferred Send-to-Compare)
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
        self.assertTrue(hasattr(self.tab, "_baseline_subject_cb"))
        self.assertTrue(hasattr(self.tab, "_apply_baseline_btn"))
        # All four modes are exposed on the combobox.
        values = self.tab._baseline_mode_cb.cget("values")
        # Tk returns either a tuple or a string of space-separated names.
        if isinstance(values, str):
            values = tuple(values.split())
        self.assertEqual(
            tuple(values),
            ("linear", "polynomial", "spline", "rubberband"),
        )

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

        # Each mode rebuilds the frame; counts differ between modes.
        self.assertGreater(linear_count, 0)
        self.assertGreater(poly_count, linear_count,
                           "polynomial has more rows than linear")
        self.assertGreater(spline_count, 0)
        self.assertEqual(rb_count, 1,
                         "rubberband shows only the 'no parameters' label")

    # ---- Apply materialises provisional pair -----------------------

    def test_apply_creates_provisional_op_and_data_node(self):
        self._add_uvvis("u1")
        # Pick the freshly-loaded subject in the combobox.
        items = self.tab._baseline_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertTrue(len(items) >= 1, "subject combobox should list u1")
        self.tab._baseline_subject.set(items[0])

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
        items = self.tab._baseline_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._baseline_subject.set(items[0])
        self.tab._baseline_mode.set("linear")
        self.tab._baseline_anchor_lo.set("200")
        self.tab._baseline_anchor_hi.set("800")

        _, out_id = self.tab._apply_baseline()
        out = self.graph.get_node(out_id)
        self.assertAlmostEqual(float(out.arrays["absorbance"].max()),
                               1.0, places=4)

    # ---- ScanTreeWidget integration --------------------------------

    def test_provisional_baseline_appears_in_sidebar(self):
        self._add_uvvis("u1")
        items = self.tab._baseline_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._baseline_subject.set(items[0])
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
        items = self.tab._baseline_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._baseline_subject.set(items[0])
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
        items = self.tab._baseline_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.tab._baseline_subject.set(items[0])
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
        items_before = self.tab._baseline_subject_cb.cget("values")
        if isinstance(items_before, str):
            items_before = tuple(items_before.split())
        self.assertEqual(len(items_before), 1)

        self.tab._baseline_subject.set(items_before[0])
        self.tab._baseline_mode.set("rubberband")
        self.tab._apply_baseline()
        self.tab.update_idletasks()

        items_after = self.tab._baseline_subject_cb.cget("values")
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
        items = self.tab._normalisation_panel._subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertGreaterEqual(len(items), 1)
        self.tab._normalisation_panel._subject_var.set(items[0])

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
