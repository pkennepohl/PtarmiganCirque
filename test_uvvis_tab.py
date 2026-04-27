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


if __name__ == "__main__":
    unittest.main(verbosity=2)
