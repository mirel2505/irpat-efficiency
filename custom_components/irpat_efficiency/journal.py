"""Validated manual hydraulic observations; no equipment control."""
from datetime import datetime, timezone
from math import isfinite
from uuid import uuid4

from .calculations import normalize_flow


def _flow(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ValueError("invalid_flow")
    return float(value)


def make_snapshot(topology, manifold_id, readings, *, phase="observation", previous=None,
                  manifold_total_lmin=None, source_total_m3h=None, note="", now=None, adjusted_circuit_ids=None):
    """Validate a partial or complete manual snapshot against the manifold."""
    if phase not in ("observation", "before", "after", "adjustment"):
        raise ValueError("invalid_phase")
    if not any(m["id"] == manifold_id for m in topology["manifolds"]):
        raise ValueError("invalid_manifold")
    if phase == "after" and (not previous or previous["phase"] != "before"
                              or previous["manifold_id"] != manifold_id):
        raise ValueError("missing_before")
    if phase == "adjustment" and (not previous or previous["manifold_id"] != manifold_id):
        raise ValueError("missing_reference")
    if phase not in ("after", "adjustment") and previous is not None:
        raise ValueError("unexpected_reference")
    if not isinstance(note, str) or len(note) > 2000:
        raise ValueError("invalid_note")
    allowed = {c["id"] for c in topology["circuits"] if c["manifold_id"] == manifold_id}
    if not readings or not set(readings) <= allowed:
        raise ValueError("invalid_circuit")
    flows = {key: _flow(value) for key, value in readings.items()}
    if not any(value is not None for value in flows.values()):
        raise ValueError("no_readings")
    adjusted = [] if adjusted_circuit_ids is None else adjusted_circuit_ids
    if (not isinstance(adjusted, list) or any(not isinstance(cid, str) for cid in adjusted)
            or len(set(adjusted)) != len(adjusted) or not set(adjusted) <= allowed
            or (adjusted and phase not in ("adjustment", "after"))
            or (phase == "adjustment" and not adjusted)):
        raise ValueError("invalid_adjusted_circuits")
    if any(flows.get(cid) is None for cid in adjusted):
        raise ValueError("missing_adjusted_reading")
    total = _flow(manifold_total_lmin)
    source = _flow(source_total_m3h)
    provenance = "manual_manifold" if total is not None else None
    if total is None and set(flows) == allowed and all(v is not None for v in flows.values()):
        total = sum(flows.values())
        provenance = "sum_all_circuits"
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("invalid_timestamp")
    stamp = stamp.astimezone(timezone.utc)
    if previous is not None and stamp < datetime.fromisoformat(previous["timestamp"]):
        raise ValueError("invalid_timestamp")
    changes = {}
    if previous is not None:
        for cid, value in flows.items():
            old = previous["flows_lmin"].get(cid)
            if old is not None and value is not None:
                changes[cid] = {"before_lmin": old, "after_lmin": value, "difference_lmin": value-old,
                                "direct_adjustment": cid in adjusted if adjusted else None}
    return {"adjusted_circuit_ids": adjusted, "flow_changes": changes,
            "id": uuid4().hex, "timestamp": stamp.isoformat(), "manifold_id": manifold_id,
            "phase": phase, "previous_id": previous["id"] if previous else None,
            "flows_lmin": flows, "manifold_total_lmin": total, "total_provenance": provenance,
            "source_total_m3h": source, "note": note.strip()}


def compare_snapshots(before, after, *, comparable=False):
    """Normalize to the prior manifold total only after explicit comparability review."""
    if (not comparable or before["manifold_id"] != after["manifold_id"]
            or not before["total_provenance"] or before["total_provenance"] != after["total_provenance"]):
        return None
    reference = before["manifold_total_lmin"]
    current = after["manifold_total_lmin"]
    if not reference or not current:
        return None
    if any(sum(v for v in snapshot["flows_lmin"].values() if v is not None) > snapshot["manifold_total_lmin"] + 1e-9
           for snapshot in (before, after)):
        return None
    result = {}
    for key in before["flows_lmin"].keys() & after["flows_lmin"].keys():
        initial = before["flows_lmin"][key]
        actual = after["flows_lmin"][key]
        adjusted = normalize_flow(actual, current, reference)
        if initial is not None and initial <= reference and adjusted is not None:
            result[key] = {"before_lmin": initial, "after_lmin": actual,
                           "normalized_after_lmin": adjusted, "difference_lmin": adjusted - initial}
    return result or None
