"""Bounded, regular temperature sampling and comparisons in UTC."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

SAMPLE_SECONDS = 300
RETENTION_DAYS = 8


def bucket(timestamp):
    return int(timestamp) // SAMPLE_SECONDS * SAMPLE_SECONDS


def record_samples(data, timestamp, values):
    """Keep one observation per UTC slot and room; never interpolate gaps."""
    slot = bucket(timestamp)
    cutoff = slot - RETENTION_DAYS * 86400
    for room_id, series in list(data.items()):
        data[room_id] = {k: v for k, v in series.items() if int(k) >= cutoff}
        if not data[room_id]:
            del data[room_id]
    for room_id, value in values.items():
        if value is None or not isinstance(value, (int, float)) or not math.isfinite(value):
            continue
        data.setdefault(room_id, {})[str(slot)] = float(value)


def window_stats(series, start, end):
    """Sample mean, extrema and observed-slot coverage, not continuous proof."""
    first, last = bucket(start), bucket(end)
    expected = max(0, (last - first) // SAMPLE_SECONDS)
    values = [v for k, v in series.items() if first <= int(k) < last]
    return {
        "mean_c": sum(values) / len(values) if values else None,
        "min_c": min(values) if values else None,
        "max_c": max(values) if values else None,
        "count": len(values),
        "expected": expected,
        "coverage": min(1, len(values) / expected) if expected else None,
    }


def previous_local_day(timestamp, tz):
    """Same local clock time yesterday; return None for nonexistent DST time."""
    current = datetime.fromtimestamp(timestamp, tz)
    target = (current.replace(tzinfo=None) - timedelta(days=1)).replace(tzinfo=tz, fold=0)
    restored = target.astimezone(timezone.utc).astimezone(tz)
    if restored.replace(tzinfo=None) != target.replace(tzinfo=None):
        return None
    return target.timestamp()


def compare_room(series, now, tz):
    yesterday = previous_local_day(now, tz)
    prior = series.get(str(bucket(yesterday))) if yesterday is not None else None
    return {
        "yesterday_same_slot_c": prior,
        "yesterday_slot_utc": bucket(yesterday) if yesterday is not None else None,
        "windows": {str(hours): window_stats(series, now-hours*3600, now)
                    for hours in (24, 48, 72, 168)},
    }
