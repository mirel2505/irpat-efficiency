"""Persistent manual reference profiles with serialized writes."""
from copy import deepcopy
import asyncio

from .profiles import create_profile


class ProfileStore:
    def __init__(self, store):
        self.store = store
        self.profiles = []
        self.lock = asyncio.Lock()
        self.closed = False

    async def async_load(self):
        data = await self.store.async_load()
        if data is not None:
            if not isinstance(data, dict) or not isinstance(data.get("profiles"), list):
                raise ValueError("invalid_profiles")
            self.profiles = deepcopy(data["profiles"])

    def list_profiles(self):
        return deepcopy(self.profiles)

    async def async_create(self, topology, zone_id, name, mode, snapshot_ids, journal):
        async with self.lock:
            if self.closed:
                raise ValueError("profiles_closed")
            if not snapshot_ids or len(set(snapshot_ids)) != len(snapshot_ids):
                raise ValueError("invalid_references")
            index = {s["id"]: s for s in journal}
            if not all(sid in index for sid in snapshot_ids):
                raise ValueError("missing_reference")
            profile = create_profile(name, topology, zone_id,
                                     [index[sid] for sid in snapshot_ids], mode)
            updated = [*self.profiles, profile]
            await self.store.async_save({"profiles": deepcopy(updated)})
            self.profiles = updated
            return deepcopy(profile)

    async def async_close(self):
        async with self.lock:
            self.closed = True


def compare_profile(profile, topology, snapshot):
    """Compare recorded raw flows only; do not infer a valve adjustment."""
    mid = snapshot["manifold_id"]
    if mid not in profile["references"]:
        raise ValueError("invalid_manifold")
    current = {c["id"] for c in topology["circuits"] if c["manifold_id"] == mid}
    reference = profile["references"][mid]
    # Check topology captured for this manifold, not just the zone-wide IDs.
    expected = set(reference.get("circuit_ids", []))
    if not expected or expected != current:
        raise ValueError("topology_changed")
    return {cid: {"reference_lmin": profile["flows_lmin"][cid],
                  "observed_lmin": snapshot["flows_lmin"].get(cid)}
            for cid in sorted(current)}
