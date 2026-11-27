"""Test persistence and failure behavior with a simulated store."""
import unittest
from copy import deepcopy
import asyncio

from custom_components.irpat_efficiency.profile_store import ProfileStore, compare_profile


class Store:
    data = None
    fail = False

    async def async_load(self):
        return deepcopy(self.data)

    async def async_save(self, data):
        await asyncio.sleep(0)
        if self.fail:
            raise OSError("disk error")
        self.data = deepcopy(data)


class ProfileStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = Store()
        self.repo = ProfileStore(self.store)
        await self.repo.async_load()
        self.topology = {"zones": [{"id": "z"}], "manifolds": [{"id": "m", "zone_id": "z"}],
                         "circuits": [{"id": "a", "manifold_id": "m"}], "rooms": []}
        self.journal = [{"id": "s", "manifold_id": "m", "timestamp": "2026-01-01T00:00:00+00:00",
                         "flows_lmin": {"a": 1.2}}]

    async def create(self, ids=None):
        return await self.repo.async_create(self.topology, "z", "Reference", "heating",
                                            ["s"] if ids is None else ids, self.journal)

    async def test_reload(self):
        p = await self.create()
        restored = ProfileStore(self.store)
        await restored.async_load()
        self.assertEqual(restored.list_profiles()[0]["id"], p["id"])

    async def test_failed_save(self):
        self.store.fail = True
        with self.assertRaises(OSError):
            await self.create()
        self.assertEqual(self.repo.list_profiles(), [])

    async def test_concurrent(self):
        await asyncio.gather(self.create(), self.create())
        self.assertEqual(len(self.repo.list_profiles()), 2)

    async def test_invalid_reference(self):
        for ids in ([], ["missing"], ["s", "s"]):
            with self.assertRaises(ValueError):
                await self.create(ids)

    async def test_copy_and_closed(self):
        p = await self.create()
        p["flows_lmin"]["a"] = 9
        self.assertEqual(self.repo.list_profiles()[0]["flows_lmin"]["a"], 1.2)
        await self.repo.async_close()
        with self.assertRaises(ValueError):
            await self.create()

    async def test_comparison_and_changed_topology(self):
        p = await self.create()
        s = {"manifold_id": "m", "flows_lmin": {"a": 0.9}}
        self.assertEqual(compare_profile(p, self.topology, s)["a"],
                         {"reference_lmin": 1.2, "observed_lmin": 0.9})
        self.topology["circuits"].append({"id": "b", "manifold_id": "m"})
        with self.assertRaisesRegex(ValueError, "topology_changed"):
            compare_profile(p, self.topology, s)
