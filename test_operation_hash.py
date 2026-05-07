"""Pure-module tests for the per-OperationType implementation hash
registry (Phase 4v / CS-45).

Run with:  python -m pytest test_operation_hash.py -v
"""

from __future__ import annotations

import unittest

from nodes import OperationType
import operation_hash
from operation_hash import (
    SENTINEL_PREFIX,
    clear_registry,
    compute_implementation_hash,
    is_registered,
    register_default_implementations,
    register_implementation,
    registered_op_types,
)


def _f1():
    return 1


def _f2():
    return 2


def _f3():
    """A third stub with a different docstring + return value."""
    return 3


class _CleanRegistryMixin:
    """Tests in this file mutate the module-level registry; reset
    before and after each test so coupling between cases stays nil."""

    def setUp(self):
        clear_registry()

    def tearDown(self):
        clear_registry()


class TestUnregisteredSentinel(_CleanRegistryMixin, unittest.TestCase):
    """Unregistered ops return a sentinel, not a hash."""

    def test_sentinel_for_every_unregistered_op(self):
        for op_type in OperationType:
            h = compute_implementation_hash(op_type)
            self.assertTrue(h.startswith(SENTINEL_PREFIX),
                            f"{op_type.name} should be unregistered")
            self.assertIn(op_type.name, h)

    def test_is_registered_negative(self):
        self.assertFalse(is_registered(OperationType.BASELINE))


class TestRegistration(_CleanRegistryMixin, unittest.TestCase):
    """register_implementation stores the bundle and replaces prior."""

    def test_register_makes_op_visible_in_registered(self):
        register_implementation(OperationType.LOAD, _f1)
        self.assertIn(OperationType.LOAD, registered_op_types())
        self.assertTrue(is_registered(OperationType.LOAD))

    def test_register_replaces_prior_bundle(self):
        register_implementation(OperationType.LOAD, _f1)
        h1 = compute_implementation_hash(OperationType.LOAD)
        register_implementation(OperationType.LOAD, _f2)
        h2 = compute_implementation_hash(OperationType.LOAD)
        self.assertNotEqual(h1, h2,
                            "Re-registering with a different bundle "
                            "must change the hash")

    def test_clear_registry_wipes(self):
        register_implementation(OperationType.LOAD, _f1)
        clear_registry()
        self.assertEqual(registered_op_types(), ())


class TestHashDeterminism(_CleanRegistryMixin, unittest.TestCase):
    """The same registration produces the same hash; bundle order
    does not affect the result."""

    def test_same_bundle_same_hash(self):
        register_implementation(OperationType.LOAD, _f1, _f2)
        a = compute_implementation_hash(OperationType.LOAD)
        clear_registry()
        register_implementation(OperationType.LOAD, _f1, _f2)
        b = compute_implementation_hash(OperationType.LOAD)
        self.assertEqual(a, b)

    def test_bundle_order_does_not_matter(self):
        register_implementation(OperationType.LOAD, _f1, _f2)
        a = compute_implementation_hash(OperationType.LOAD)
        clear_registry()
        register_implementation(OperationType.LOAD, _f2, _f1)
        b = compute_implementation_hash(OperationType.LOAD)
        self.assertEqual(a, b,
                         "Bundle is sorted by qualname before hashing")

    def test_adding_helper_changes_hash(self):
        register_implementation(OperationType.LOAD, _f1)
        h1 = compute_implementation_hash(OperationType.LOAD)
        register_implementation(OperationType.LOAD, _f1, _f3)
        h2 = compute_implementation_hash(OperationType.LOAD)
        self.assertNotEqual(h1, h2)


class TestDomainSeparation(_CleanRegistryMixin, unittest.TestCase):
    """Two ops with the same callables get different hashes."""

    def test_different_op_types_with_same_bundle_differ(self):
        register_implementation(OperationType.LOAD, _f1)
        register_implementation(OperationType.NORMALISE, _f1)
        h_load = compute_implementation_hash(OperationType.LOAD)
        h_norm = compute_implementation_hash(OperationType.NORMALISE)
        self.assertNotEqual(h_load, h_norm,
                            "Hash domain-separates by op_type.name")


class TestHashCache(_CleanRegistryMixin, unittest.TestCase):
    """The cache is invalidated on re-registration."""

    def test_cache_repopulates_after_reregister(self):
        register_implementation(OperationType.LOAD, _f1)
        first = compute_implementation_hash(OperationType.LOAD)
        # Cache should be populated; second call returns same value.
        self.assertEqual(compute_implementation_hash(OperationType.LOAD),
                         first)
        register_implementation(OperationType.LOAD, _f3)
        second = compute_implementation_hash(OperationType.LOAD)
        self.assertNotEqual(first, second)


class TestDefaultRegistrations(_CleanRegistryMixin, unittest.TestCase):
    """register_default_implementations covers every shipped compute_*
    op_type."""

    EXPECTED_REGISTERED = {
        "BASELINE", "NORMALISE", "SMOOTH",
        "PEAK_PICK", "SECOND_DERIVATIVE", "LOAD",
    }

    def test_default_registers_expected_ops(self):
        register_default_implementations()
        actual = {t.name for t in registered_op_types()}
        self.assertEqual(actual, self.EXPECTED_REGISTERED)

    def test_default_leaves_other_ops_unregistered(self):
        register_default_implementations()
        for op_type in OperationType:
            if op_type.name in self.EXPECTED_REGISTERED:
                self.assertFalse(
                    compute_implementation_hash(op_type)
                    .startswith(SENTINEL_PREFIX),
                    f"{op_type.name} should have a real hash")
            else:
                self.assertTrue(
                    compute_implementation_hash(op_type)
                    .startswith(SENTINEL_PREFIX),
                    f"{op_type.name} should be unregistered")

    def test_default_is_idempotent(self):
        register_default_implementations()
        snapshot = {t: compute_implementation_hash(t)
                    for t in registered_op_types()}
        register_default_implementations()
        for t, h in snapshot.items():
            self.assertEqual(compute_implementation_hash(t), h)


class TestSourceHashSensitivity(_CleanRegistryMixin, unittest.TestCase):
    """Auto-source-hash detects function body differences (not
    qualname-only changes)."""

    def test_two_different_function_bodies_hash_differently(self):
        # _f1 returns 1, _f2 returns 2 — same name space, different
        # source bytes ⇒ different hashes when registered alone.
        register_implementation(OperationType.LOAD, _f1)
        h_f1 = compute_implementation_hash(OperationType.LOAD)
        clear_registry()
        register_implementation(OperationType.LOAD, _f2)
        h_f2 = compute_implementation_hash(OperationType.LOAD)
        self.assertNotEqual(h_f1, h_f2)

    def test_real_baseline_hash_is_64_hex_chars(self):
        register_default_implementations()
        h = compute_implementation_hash(OperationType.BASELINE)
        self.assertEqual(len(h), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in h))


if __name__ == "__main__":
    unittest.main()
