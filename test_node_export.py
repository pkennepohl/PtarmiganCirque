"""Tests for node_export.py (Phase 4f, CS-17).

Pure-Python tests writing into a tmpdir — no Tk involvement here. The
``ScanTreeWidget`` Export… menu entry is exercised in
``test_scan_tree_widget.py``.
"""

from __future__ import annotations

import os
import tempfile
import unittest

import numpy as np

from graph import ProjectGraph
from nodes import DataNode, NodeState, NodeType, OperationNode, OperationType
from node_export import EXPORTABLE_NODE_TYPES, export_node_to_file


def _uvvis(nid: str, label: str = "uv",
           wl=(200.0, 300.0, 400.0),
           ab=(0.10, 0.45, 0.70)) -> DataNode:
    return DataNode(
        id=nid, type=NodeType.UVVIS,
        arrays={
            "wavelength_nm": np.asarray(wl, dtype=float),
            "absorbance":    np.asarray(ab, dtype=float),
        },
        metadata={}, label=label,
        state=NodeState.COMMITTED,
    )


class _TmpDirCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="node_export_test_")

    def tearDown(self):
        for name in os.listdir(self._tmpdir):
            try:
                os.remove(os.path.join(self._tmpdir, name))
            except OSError:
                pass
        try:
            os.rmdir(self._tmpdir)
        except OSError:
            pass

    def _path(self, name: str) -> str:
        return os.path.join(self._tmpdir, name)


class TestExtensionDispatch(_TmpDirCase):
    """Format selection is keyed off the path extension."""

    def test_csv_writes_comma_separated_data(self):
        graph = ProjectGraph()
        graph.add_node(_uvvis("aa00bb00cc00"))

        out = self._path("scan.csv")
        export_node_to_file(graph, "aa00bb00cc00", out)

        with open(out, encoding="utf-8") as fh:
            text = fh.read()
        # Skip header lines; find the data block.
        lines = [ln for ln in text.splitlines() if not ln.startswith("# ")]
        # Column header + 3 data rows.
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], "wavelength_nm,absorbance")
        # Each data row carries exactly two comma-separated values.
        for row in lines[1:]:
            self.assertEqual(row.count(","), 1)

    def test_txt_writes_tab_separated_data(self):
        graph = ProjectGraph()
        graph.add_node(_uvvis("aa00bb00cc00"))

        out = self._path("scan.txt")
        export_node_to_file(graph, "aa00bb00cc00", out)

        with open(out, encoding="utf-8") as fh:
            text = fh.read()
        lines = [ln for ln in text.splitlines() if not ln.startswith("# ")]
        self.assertEqual(lines[0], "wavelength_nm\tabsorbance")
        for row in lines[1:]:
            self.assertEqual(row.count("\t"), 1)

    def test_unknown_extension_raises_value_error(self):
        graph = ProjectGraph()
        graph.add_node(_uvvis("aa00bb00cc00"))
        with self.assertRaises(ValueError):
            export_node_to_file(
                graph, "aa00bb00cc00", self._path("scan.xls"),
            )

    def test_extension_case_insensitive(self):
        graph = ProjectGraph()
        graph.add_node(_uvvis("aa00bb00cc00"))
        out = self._path("scan.CSV")
        export_node_to_file(graph, "aa00bb00cc00", out)
        self.assertTrue(os.path.exists(out))


class TestHeaderPresence(_TmpDirCase):
    """The provenance header is mandatory in both formats."""

    def test_csv_carries_provenance_header_above_columns(self):
        graph = ProjectGraph()
        graph.add_node(_uvvis("aa00bb00cc00", label="solo"))

        out = self._path("solo.csv")
        export_node_to_file(graph, "aa00bb00cc00", out)

        with open(out, encoding="utf-8") as fh:
            text = fh.read()
        lines = text.splitlines()
        # First line is the version envelope, before any data.
        self.assertTrue(lines[0].startswith("# ptarmigan_version="))
        # The column header sits between header and data.
        col_index = lines.index("wavelength_nm,absorbance")
        # Every line above col_index is part of the header.
        for line in lines[:col_index]:
            self.assertTrue(line.startswith("# "), line)

    def test_txt_carries_identical_header_to_csv(self):
        graph = ProjectGraph()
        graph.add_node(_uvvis("aa00bb00cc00", label="twin"))

        csv_path = self._path("twin.csv")
        txt_path = self._path("twin.txt")
        export_node_to_file(graph, "aa00bb00cc00", csv_path)
        export_node_to_file(graph, "aa00bb00cc00", txt_path)

        with open(csv_path, encoding="utf-8") as fh:
            csv_text = fh.read()
        with open(txt_path, encoding="utf-8") as fh:
            txt_text = fh.read()
        # Compare just the ``# ``-prefixed lines (excluding the
        # ``exported_at`` line which carries a different per-call
        # timestamp).
        def header(text: str) -> list[str]:
            return [
                ln for ln in text.splitlines()
                if ln.startswith("# ")
                and not ln.startswith("# exported_at=")
            ]
        self.assertEqual(header(csv_text), header(txt_text))


class TestDataBlock(_TmpDirCase):
    """Data block is the canonical wavelength / absorbance pair."""

    def test_two_columns_match_arrays(self):
        wl = (310.0, 320.0, 330.0, 340.0)
        ab = (0.11, 0.22, 0.33, 0.44)
        graph = ProjectGraph()
        graph.add_node(_uvvis("aa00bb00cc00", wl=wl, ab=ab))

        out = self._path("scan.csv")
        export_node_to_file(graph, "aa00bb00cc00", out)

        with open(out, encoding="utf-8") as fh:
            data_lines = [
                ln for ln in fh.read().splitlines()
                if not ln.startswith("# ")
            ][1:]  # skip column header
        parsed = [
            tuple(float(v) for v in ln.split(",")) for ln in data_lines
        ]
        self.assertEqual(parsed, list(zip(wl, ab)))


class TestNodeTypeGate(_TmpDirCase):
    """Only spectrum-shaped nodes are exportable in Phase 4f."""

    def test_xanes_raises_value_error(self):
        graph = ProjectGraph()
        graph.add_node(DataNode(
            id="x" * 12, type=NodeType.XANES,
            arrays={
                "energy": np.asarray([100.0, 200.0]),
                "mu":     np.asarray([0.1, 0.2]),
            },
            metadata={}, label="xa", state=NodeState.COMMITTED,
        ))
        with self.assertRaises(ValueError):
            export_node_to_file(graph, "x" * 12, self._path("xa.csv"))

    def test_baseline_and_normalised_are_exportable(self):
        # The constants must include the three Phase 4f types.
        for nt in (NodeType.UVVIS, NodeType.BASELINE,
                   NodeType.NORMALISED):
            self.assertIn(nt, EXPORTABLE_NODE_TYPES)

    def test_baseline_node_writes_data_block(self):
        graph = ProjectGraph()
        graph.add_node(DataNode(
            id="bb00bb00bb00", type=NodeType.BASELINE,
            arrays={
                "wavelength_nm": np.asarray([200.0, 300.0]),
                "absorbance":    np.asarray([0.01, 0.02]),
            },
            metadata={}, label="bl",
            state=NodeState.COMMITTED,
        ))
        out = self._path("bl.csv")
        export_node_to_file(graph, "bb00bb00bb00", out)
        with open(out, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("wavelength_nm,absorbance", text)


class TestUnknownNodeId(_TmpDirCase):
    def test_missing_id_raises(self):
        graph = ProjectGraph()
        with self.assertRaises(KeyError):
            export_node_to_file(graph, "ghost", self._path("g.csv"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
