"""Actual Core backup platform discovery and native backup/restore in temp dirs only."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.backup_restore import restore_backup, RESTORE_BACKUP_FILE, RESTORE_BACKUP_RESULT_FILE
from homeassistant.components.backup.manager import BackupManager, CoreBackupReaderWriter
from homeassistant.setup import async_setup_component

try:
    from pytest_homeassistant.common import MockConfigEntry
except ModuleNotFoundError as exc:
    if exc.name != "pytest_homeassistant":
        raise
    from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.irpat_efficiency.const import DOMAIN
from custom_components.irpat_efficiency.topology import empty_topology


async def test_native_backup_platform_flush(hass, enable_custom_integrations):
    entry = MockConfigEntry(domain=DOMAIN, title="Test", data={}, options={"topology": empty_topology()})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    manager = BackupManager(hass, CoreBackupReaderWriter(hass))
    await manager.load_platforms()
    assert DOMAIN in manager.platforms
    runtime = hass.data[DOMAIN]
    stamp = datetime.now(timezone.utc).timestamp()
    mode = runtime["mode_monitors"][entry.entry_id].journal
    defrost = runtime["defrost_monitors"][entry.entry_id].journal
    event = {"source_id": "synthetic", "observed_at": stamp, "mode": "heating"}
    cycle = {"source_id": "synthetic", "end": stamp}
    mode.append(event)
    defrost.append(cycle)
    await manager.async_pre_backup_actions()
    assert mode.committed == [event] and not mode.pending
    assert defrost.committed == [cycle] and not defrost.pending
    await manager.async_post_backup_actions()


@pytest.mark.parametrize("password", [None, "synthetic-test-password"])
async def test_native_archive_restore_files(hass, tmp_path, password):
    """Exercise native archive writer and startup restore on synthetic files.

    This proves archive inclusion and byte recovery, not a complete HAOS reboot.
    """
    def roundtrip():
        source = tmp_path / "source"
        target = tmp_path / "target"
        (source / ".storage").mkdir(parents=True)
        (target / ".storage").mkdir(parents=True)
        assert source != target and source.parent == target.parent == tmp_path
        records = {
            "history": {"rooms": {"room": {"0": 21.5}}, "configuration_hash": "test", "configuration_since": 0},
            "energy": {},
            "journal": {"entries": []},
            "profiles": {"profiles": []},
            "defrost": {"events": [{"source_id": "test", "end": 123}]},
            "modes": {"events": [{"source_id": "test", "observed_at": 123, "mode": "heating"}]},
            "reports": {"observations": [], "reports": []},
        }
        expected = {}
        for suffix, data in records.items():
            key = f"{DOMAIN}.{suffix}.test"
            relative = f".storage/{key}"
            expected[relative] = json.dumps({"version": 1, "minor_version": 1, "key": key, "data": data}).encode()
        expected[".storage/core.config_entries"] = json.dumps({
            "version": 1, "minor_version": 5, "key": "core.config_entries",
            "data": {"entries": [{"entry_id": "test", "domain": DOMAIN, "options": {"topology": empty_topology()}}]}
        }).encode()
        expected["configuration.yaml"] = b"default_config:\n"
        for relative, data in expected.items():
            (source / relative).write_bytes(data)
        (target / ".storage" / f"{DOMAIN}.journal.test").write_text("newer synthetic content")
        (target / "keep-test-db.txt").write_text("temporary restore target only")
        reader = CoreBackupReaderWriter(SimpleNamespace(config=SimpleNamespace(
            path=lambda *parts: str(source.joinpath(*parts)))))
        archive = tmp_path / "backup.tar"
        written, size = reader._mkdir_and_generate_backup_contents(
            {"slug": "test", "compressed": True, "homeassistant": {"version": HA_VERSION}},
            False, password, archive)
        assert written == archive and size > 0
        (target / RESTORE_BACKUP_FILE).write_text(json.dumps({
            "path": str(archive), "password": password, "remove_after_restore": False,
            "restore_database": False, "restore_homeassistant": True}))
        assert restore_backup(str(target))
        assert json.loads((target / RESTORE_BACKUP_RESULT_FILE).read_text())["success"] is True
        assert not (target / RESTORE_BACKUP_FILE).exists()
        for relative, data in expected.items():
            assert (target / relative).read_bytes() == data, relative
            assert (source / relative).read_bytes() == data, relative
        assert archive.exists()
    await hass.async_add_executor_job(roundtrip)
