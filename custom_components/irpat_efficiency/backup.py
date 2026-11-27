"""Prepare irPaT's local stores for Home Assistant's native backup."""
import logging
from datetime import datetime, timezone

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_pre_backup(hass):
    """Retry pending event saves without blocking unrelated system backups."""
    runtime = hass.data.get(DOMAIN, {})
    for key in ("defrost_monitors", "mode_monitors"):
        for entry_id, monitor in list(runtime.get(key, {}).items()):
            async with monitor.lock:
                if monitor.closed:
                    continue
                try:
                    await monitor.journal.async_flush(datetime.now(timezone.utc).timestamp())
                except Exception:
                    _LOGGER.exception("Backup preparation: %s has unsaved observations for %s",
                                      key, entry_id)
    for key in ("histories", "energy_monitors"):
        for entry_id, monitor in list(runtime.get(key, {}).items()):
            if monitor.save_failed:
                _LOGGER.warning("Backup preparation: %s last save failed for %s; only committed data is recoverable",
                                key, entry_id)


async def async_post_backup(hass):
    """No resume action is needed: collection was not paused."""
