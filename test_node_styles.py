"""Tests for node_styles.py.

Pure module — no Tk required. Phase 4j (CS-21) added the
``pick_default_color`` helper and its companion ``SPECTRUM_PALETTE``;
this file pins both. The pre-existing ``default_spectrum_style`` was
implicitly covered by the per-operation tests' style-dict assertions
but is also pinned here so node_styles has its own dedicated test
module.
"""

from __future__ import annotations

import unittest

import numpy as np

from graph import ProjectGraph
from nodes import DataNode, NodeState, NodeType
from node_styles import (
    DEFAULT_SPECTRUM_STYLE_KEYS,
    SPECTRUM_PALETTE,
    SPECTRUM_PALETTE_NODE_TYPES,
    default_spectrum_style,
    pick_default_color,
)


def _make_data_node(nid: str, node_type: NodeType,
                    state: NodeState = NodeState.COMMITTED) -> DataNode:
    """Build a minimally-valid DataNode for the requested type."""
    if node_type == NodeType.PEAK_LIST:
        # PEAK_LIST stores peak coordinates, not a curve.
        arrays = {
            "wavelength_nm": np.asarray([500.0], dtype=float),
            "absorbance":    np.asarray([1.0], dtype=float),
        }
    else:
        wl = np.linspace(200.0, 800.0, 11)
        arrays = {
            "wavelength_nm": np.asarray(wl, dtype=float),
            "absorbance":    np.asarray(np.zeros_like(wl), dtype=float),
        }
    return DataNode(
        id=nid,
        type=node_type,
        arrays=arrays,
        metadata={"source_file": "syn"},
        label=nid,
        state=state,
        style=default_spectrum_style("#000000"),
    )


# ---------------------------------------------------------------------------
# default_spectrum_style — sanity coverage (no dedicated tests pre-4j)
# ---------------------------------------------------------------------------


class TestDefaultSpectrumStyle(unittest.TestCase):

    def test_returns_eight_universal_keys(self):
        style = default_spectrum_style("#abcdef")
        self.assertEqual(set(style.keys()), set(DEFAULT_SPECTRUM_STYLE_KEYS))

    def test_colour_is_passed_through(self):
        style = default_spectrum_style("#deadbe")
        self.assertEqual(style["color"], "#deadbe")

    def test_factory_defaults_are_stable(self):
        # Pin the non-colour defaults so a future drift is loud.
        style = default_spectrum_style("#000")
        self.assertEqual(style["linestyle"], "solid")
        self.assertEqual(style["linewidth"], 1.5)
        self.assertEqual(style["alpha"], 0.9)
        self.assertTrue(style["visible"])
        self.assertTrue(style["in_legend"])
        self.assertFalse(style["fill"])
        self.assertEqual(style["fill_alpha"], 0.08)


# ---------------------------------------------------------------------------
# SPECTRUM_PALETTE / SPECTRUM_PALETTE_NODE_TYPES — pin shape
# ---------------------------------------------------------------------------


class TestPaletteConstants(unittest.TestCase):

    def test_palette_is_a_tuple_of_ten_hex_strings(self):
        self.assertIsInstance(SPECTRUM_PALETTE, tuple)
        self.assertEqual(len(SPECTRUM_PALETTE), 10)
        for entry in SPECTRUM_PALETTE:
            self.assertIsInstance(entry, str)
            self.assertTrue(entry.startswith("#"))
            self.assertEqual(len(entry), 7)

    def test_palette_first_entry_is_matplotlib_default_blue(self):
        # Pre-4j call sites started at "#1f77b4"; pin the start so
        # callers' visual ordering is preserved across the migration.
        self.assertEqual(SPECTRUM_PALETTE[0], "#1f77b4")

    def test_palette_node_types_is_six_spectrum_shapes(self):
        # Order matters for the deterministic count expression.
        self.assertEqual(SPECTRUM_PALETTE_NODE_TYPES, (
            NodeType.UVVIS,
            NodeType.BASELINE,
            NodeType.NORMALISED,
            NodeType.SMOOTHED,
            NodeType.SECOND_DERIVATIVE,
            NodeType.PEAK_LIST,
        ))


# ---------------------------------------------------------------------------
# pick_default_color — empty graph + single + roll-around
# ---------------------------------------------------------------------------


class TestPickDefaultColorEmpty(unittest.TestCase):

    def test_empty_graph_returns_first_palette_entry(self):
        graph = ProjectGraph()
        self.assertEqual(pick_default_color(graph), SPECTRUM_PALETTE[0])


class TestPickDefaultColorSingleType(unittest.TestCase):

    def test_one_uvvis_node_advances_to_second_palette_entry(self):
        graph = ProjectGraph()
        graph.add_node(_make_data_node("u1", NodeType.UVVIS))
        self.assertEqual(pick_default_color(graph), SPECTRUM_PALETTE[1])

    def test_two_uvvis_nodes_advances_to_third_palette_entry(self):
        graph = ProjectGraph()
        graph.add_node(_make_data_node("u1", NodeType.UVVIS))
        graph.add_node(_make_data_node("u2", NodeType.UVVIS))
        self.assertEqual(pick_default_color(graph), SPECTRUM_PALETTE[2])

    def test_palette_length_wraps_around(self):
        graph = ProjectGraph()
        # Add 10 UVVIS nodes — that consumes every palette entry; the
        # 11th caller wraps back to the first colour.
        for i in range(len(SPECTRUM_PALETTE)):
            graph.add_node(_make_data_node(f"u{i}", NodeType.UVVIS))
        self.assertEqual(pick_default_color(graph), SPECTRUM_PALETTE[0])


class TestPickDefaultColorAllNodeTypes(unittest.TestCase):

    def test_walks_every_spectrum_palette_node_type(self):
        # One node per spectrum-shaped NodeType — six in total — moves
        # the counter to palette index 6.
        graph = ProjectGraph()
        for i, ntype in enumerate(SPECTRUM_PALETTE_NODE_TYPES):
            graph.add_node(_make_data_node(f"n{i}", ntype))
        self.assertEqual(pick_default_color(graph), SPECTRUM_PALETTE[6])

    def test_peak_list_counts_against_the_same_counter(self):
        # Pre-4j peak_picking and second_derivative each carried their
        # own subset — peak_picking saw PEAK_LIST, second_derivative
        # did not, and neither saw the other. CS-21 unifies; verify
        # that PEAK_LIST occupies a slot when picking from any caller.
        graph = ProjectGraph()
        graph.add_node(_make_data_node("p1", NodeType.PEAK_LIST))
        self.assertEqual(pick_default_color(graph), SPECTRUM_PALETTE[1])

    def test_second_derivative_counts_against_the_same_counter(self):
        graph = ProjectGraph()
        graph.add_node(_make_data_node("d1", NodeType.SECOND_DERIVATIVE))
        self.assertEqual(pick_default_color(graph), SPECTRUM_PALETTE[1])


class TestPickDefaultColorIgnoresState(unittest.TestCase):

    def test_provisional_nodes_consume_a_palette_slot(self):
        graph = ProjectGraph()
        graph.add_node(_make_data_node(
            "u1", NodeType.UVVIS, state=NodeState.PROVISIONAL))
        # Provisional still counts — colours stay sticky once chosen.
        self.assertEqual(pick_default_color(graph), SPECTRUM_PALETTE[1])

    def test_discarded_nodes_consume_a_palette_slot(self):
        graph = ProjectGraph()
        graph.add_node(_make_data_node(
            "u1", NodeType.UVVIS, state=NodeState.DISCARDED))
        # Discarded too — discarding does not free up the colour.
        # Locks the visual identity across an undo / redo round trip.
        self.assertEqual(pick_default_color(graph), SPECTRUM_PALETTE[1])


class TestPickDefaultColorOrderIndependence(unittest.TestCase):

    def test_palette_index_is_pure_total_count(self):
        # Two graphs with the same total spectrum-shaped node count
        # but a different mix of types must yield the same colour.
        # Pre-4j this was false: peak_picking-from-graph-A and
        # second_derivative-from-graph-B used different formulas.
        g_a = ProjectGraph()
        g_a.add_node(_make_data_node("u1", NodeType.UVVIS))
        g_a.add_node(_make_data_node("b1", NodeType.BASELINE))
        g_a.add_node(_make_data_node("p1", NodeType.PEAK_LIST))

        g_b = ProjectGraph()
        g_b.add_node(_make_data_node("u1", NodeType.UVVIS))
        g_b.add_node(_make_data_node("u2", NodeType.UVVIS))
        g_b.add_node(_make_data_node("d1", NodeType.SECOND_DERIVATIVE))

        self.assertEqual(pick_default_color(g_a), pick_default_color(g_b))


if __name__ == "__main__":
    unittest.main()
