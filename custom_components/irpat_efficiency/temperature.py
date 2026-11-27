"""Pure temperature validation and room summaries, without HA dependencies."""
from __future__ import annotations

import math
from statistics import mean


def temperature_c(value, unit):
    """Convert a finite temperature reading; unknown units are unavailable."""
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(result):
        return None
    if unit in ("°F", "F"):
        result = (result - 32) * 5 / 9
    elif unit in ("K",):
        result -= 273.15
    elif unit not in ("°C", "C"):
        return None
    return result if -60 <= result <= 100 else None


def summarize_room(readings, target_c=None, tolerance_c=0.3):
    """Use the arithmetic mean of valid distinct bindings for this preview.

    No persistent-balance or hardware-control conclusion is made here.
    """
    values = {}
    for reading in readings:
        value = reading.get("temperature_c")
        if value is not None and math.isfinite(value):
            values[reading["entity_id"]] = value
    current = mean(values.values()) if values else None
    deviation = current - target_c if current is not None and target_c is not None else None
    status = "unknown"
    if deviation is not None:
        if abs(deviation) <= tolerance_c + 1e-9:
            status = "within"
        else:
            status = "warm" if deviation > 0 else "cold"
    return {"temperature_c": current, "target_c": target_c, "deviation_c": deviation,
            "status": status, "valid_count": len(values), "configured_count": len(readings)}
