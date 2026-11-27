"""Transactional room history and configuration-epoch isolation."""
from copy import deepcopy
from math import ceil, isfinite

from .history import SAMPLE_SECONDS, record_samples


def valid_timestamp(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


async def save_sample(store, data, saved_hash, since, current_hash, timestamp, values):
    """Publish the returned snapshot only after saving succeeds."""
    if not valid_timestamp(timestamp):
        raise ValueError('invalid_timestamp')
    if saved_hash != current_hash or not valid_timestamp(since):
        since = timestamp
    prospective = deepcopy(data)
    record_samples(prospective, timestamp, values)
    result = {'rooms': prospective, 'configuration_hash': current_hash,
              'configuration_since': since}
    await store.async_save(deepcopy(result))
    return result


def current_series(data, saved_hash, since, current_hash):
    """Exclude older configurations, including the ambiguous transition slot."""
    if saved_hash != current_hash or not valid_timestamp(since):
        return {}
    first = ceil(since / SAMPLE_SECONDS) * SAMPLE_SECONDS
    return {room: {key: value for key, value in series.items() if int(key) >= first}
            for room, series in data.items()}
