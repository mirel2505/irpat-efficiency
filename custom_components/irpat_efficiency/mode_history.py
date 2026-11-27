"""Evidence of a reported operating mode between meter observations."""
from math import isfinite

MODES = ('heating', 'cooling', 'dhw', 'standby', 'defrost', 'off')


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def observation(binding, raw, changed_at, reported_at, now, *, max_age=300):
    """Return a mapped HA observation with its state-change timestamp.

    HA state timestamps are evidence of reported state, not physical continuity.
    The mapping identity prevents comparison after reconfiguration.
    """
    if not binding or not isinstance(raw, str) or raw in ('unknown', 'unavailable'):
        return None
    if not all(_finite(v) for v in (changed_at, reported_at, now, max_age)):
        return None
    if max_age <= 0 or not changed_at <= reported_at <= now or now-reported_at > max_age:
        return None
    mode = binding['mapping'].get(raw)
    if mode not in MODES:
        return None
    return {'signature': [binding['entity_id'], sorted(binding['mapping'].items())],
            'raw': raw, 'mode': mode, 'changed_at': changed_at,
            'reported_at': reported_at, 'observed_at': now}


def interval_mode(before, after, start, end, *, max_gap=360):
    """Attribute only intervals covered by unchanged reported state evidence.

    Meter timestamps must lie inside the observation window. A changed
    last_changed timestamp rejects even a transition that returned to the same
    raw state. This is not proof of unreported equipment activity.
    """
    if not before or not after or not all(_finite(v) for v in (start, end, max_gap)):
        return None
    if not 0 < end-start <= max_gap:
        return None
    if not before['observed_at'] <= start < end <= after['observed_at']:
        return None
    if after['observed_at']-before['observed_at'] > max_gap:
        return None
    if any(before[k] != after[k] for k in ('signature', 'raw', 'mode', 'changed_at')):
        return None
    if before['changed_at'] > start or after['reported_at'] < end:
        return None
    return before['mode']


def transition(previous, current, now):
    """Describe a change in observed evidence, not a reconstructed event time."""
    if not _finite(now):
        raise ValueError('invalid_timestamp')
    if previous is None and current is None:
        return None
    keys = ('signature', 'raw', 'mode', 'changed_at')
    if previous and current and all(previous[k] == current[k] for k in keys):
        return None
    return {'observed_at': now, 'previous_mode': previous['mode'] if previous else None,
            'mode': current['mode'] if current else None,
            'reported_change_at': current['changed_at'] if current else None,
            'reported_only': True}
