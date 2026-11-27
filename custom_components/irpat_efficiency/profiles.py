"""Manual reference profiles; restoring a profile never sends device commands."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from .stability import finite


def create_profile(name, topology, zone_id, snapshots, mode, *, now=None):
    """Capture complete manual readings for every circuit in one zone."""
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise ValueError("invalid_name")
    if mode not in ("heating", "cooling"):
        raise ValueError("invalid_mode")
    zone = next((z for z in topology["zones"] if z["id"] == zone_id), None)
    if zone is None:
        raise ValueError("invalid_zone")
    manifolds = {m["id"] for m in topology["manifolds"] if m["zone_id"] == zone_id}
    if not manifolds or len(snapshots) != len(manifolds) or {s["manifold_id"] for s in snapshots} != manifolds:
        raise ValueError("incomplete_manifolds")
    flows = {}
    references = {}
    for s in snapshots:
        mid = s["manifold_id"]
        circuits = {c["id"] for c in topology["circuits"] if c["manifold_id"] == mid}
        readings = s["flows_lmin"]
        if not circuits or set(readings) != circuits or not all(finite(v) and v >= 0 for v in readings.values()):
            raise ValueError("incomplete_circuits")
        flows.update(readings)
        references[mid] = {"snapshot_id": s["id"], "timestamp": s["timestamp"], "circuit_ids": sorted(circuits)}
    room_ids = {c.get("room_id") for c in topology["circuits"] if c["manifold_id"] in manifolds}
    targets = {r["id"]: r.get(f"{mode}_target_c") for r in topology["rooms"] if r["id"] in room_ids}
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("invalid_timestamp")
    return {"id": uuid4().hex, "name": name.strip(), "zone_id": zone_id, "mode": mode,
            "created_at": stamp.astimezone(timezone.utc).isoformat(), "flows_lmin": flows,
            "references": references, "targets_c": targets, "zone": deepcopy(zone),
            "status": "manual_reference", "automatic_restore": False}
