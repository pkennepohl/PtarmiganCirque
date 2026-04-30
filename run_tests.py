"""Phase 1 test runner.

Runs every test module that exists today. Cross-platform — invoke
with the project's Python interpreter (e.g. ``venv/Scripts/python.exe
run_tests.py`` on Windows, ``venv/bin/python run_tests.py`` on Unix).

Add new test modules to ``TEST_MODULES`` as later phases land.
"""

from __future__ import annotations

import sys
import unittest

TEST_MODULES = (
    "test_nodes",
    "test_graph",
    "test_node_styles",
    "test_scan_tree_widget",
    "test_style_dialog",
    "test_plot_settings_dialog",
    "test_uvvis_baseline",
    "test_uvvis_normalise",
    "test_uvvis_smoothing",
    "test_uvvis_peak_picking",
    "test_uvvis_second_derivative",
    "test_uvvis_tab",
    "test_provenance_export",
    "test_node_export",
)


def main() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for name in TEST_MODULES:
        suite.addTests(loader.loadTestsFromName(name))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
