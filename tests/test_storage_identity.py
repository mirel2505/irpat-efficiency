"""Beta reset must isolate data while preserving compatibility with existing stores."""
import unittest
from types import SimpleNamespace
from custom_components.irpat_efficiency.storage_identity import (
    STORE_KINDS, generation, storage_key, fresh_options, GENERATION_KEY,
)
from custom_components.irpat_efficiency.topology import empty_topology


class StorageIdentityTests(unittest.TestCase):
    def test_legacy_keys_are_unchanged(self):
        entry = SimpleNamespace(entry_id="abc", options={})
        for kind in STORE_KINDS:
            self.assertEqual(storage_key(entry, kind), f"irpat_efficiency.{kind}.abc")

    def test_reset_creates_empty_options_and_unique_storage(self):
        old = SimpleNamespace(entry_id="abc", options={"topology": {"rooms": ["old"]}})
        first = SimpleNamespace(entry_id="abc", options=fresh_options())
        second = SimpleNamespace(entry_id="abc", options=fresh_options())
        self.assertEqual(first.options["topology"], empty_topology())
        self.assertNotEqual(generation(first), generation(second))
        for kind in STORE_KINDS:
            self.assertEqual(len({storage_key(entry, kind) for entry in (old, first, second)}), 3)
        self.assertEqual(old.options["topology"]["rooms"], ["old"])

    def test_invalid_generation_and_store_kind_rejected(self):
        for value in ("../bad", "", 42, "g"*32):
            with self.assertRaises(ValueError):
                storage_key(SimpleNamespace(entry_id="abc", options={GENERATION_KEY: value}), "history")
        with self.assertRaises(ValueError):
            storage_key(SimpleNamespace(entry_id="abc"), "../other")
