from datetime import UTC, datetime
from types import SimpleNamespace
import pytest

from app.core.config import Settings
from app.core.models import JobRecord, JobState
from app.core.service import AppService, ServiceError
from app.api import routes
from app.ha.client import _printer_ip
from app.slicer.orca import LAYER_PROFILES, MATERIAL_PROFILES, OrcaRunner


def test_official_kobra_x_profile_choices_are_bounded(tmp_path):
    runner = OrcaRunner(tmp_path, 10, 1000)
    assert set(LAYER_PROFILES) == {"0.08", "0.12", "0.16", "0.20", "0.24", "0.28"}
    assert set(MATERIAL_PROFILES) == {"PLA", "PLA+", "PETG", "ABS", "ASA", "TPU"}
    for name in (*LAYER_PROFILES.values(), *MATERIAL_PROFILES.values()):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    assert runner._process_for_slice(tmp_path, False, "0.16").name == LAYER_PROFILES["0.16"]
    assert runner.load_filament_profile("PETG") == {}


def test_layer_change_invalidates_previous_confirmation(tmp_path):
    service = AppService(Settings(data_dir=tmp_path))
    now = datetime.now(UTC)
    job = JobRecord(id="job", original_filename="a.stl", input_filename="input.stl", input_type="stl", state=JobState.READY_TO_SLICE, created_at=now, updated_at=now, approved_gcode_sha256="old", table_clear_confirmed=True)
    service.store.create_dir("job")
    service.store.save(job)
    updated = service.set_layer_height("job", "0.16")
    assert updated.layer_height == "0.16"
    assert updated.approved_gcode_sha256 is None
    assert updated.table_clear_confirmed is False
    with pytest.raises(ServiceError, match="unsupported layer"):
        service.set_layer_height("job", "0.30")


def test_ha_device_ip_is_validated_and_only_from_selected_device():
    rows = [{"translation_key": "printer_online", "entity_id": "binary_sensor.kobra"}]
    states = {"binary_sensor.kobra": {"attributes": {"ip_address": "192.168.1.42"}}}
    assert _printer_ip({}, rows, states) == "192.168.1.42"
    assert _printer_ip({"configuration_url": "http://10.0.0.4/status"}, rows, states) == "192.168.1.42"
    assert _printer_ip({"configuration_url": "https://example.com/"}, rows, {}) is None


@pytest.mark.asyncio
async def test_config_save_starts_lifecycle_with_temporarily_unavailable_entities(monkeypatch, tmp_path):
    class Adapter:
        def __init__(self, device_id):
            self.device_id = device_id
            self.entities = dict.fromkeys(routes.ESSENTIAL_KEYS, "sensor.test")

        async def resolve(self):
            pass

        async def snapshot(self):
            return SimpleNamespace(essential_entities_available=False)

    class Lan:
        def __init__(self, host):
            self.host = host

    class Service:
        lan = None
        _ha = None
        started = False

        async def start(self):
            self.started = True

    service = Service()
    state = SimpleNamespace(settings=Settings(data_dir=tmp_path), service=service, integration_error="old")
    monkeypatch.setattr(routes, "AnycubicHomeAssistantAdapter", Adapter)
    monkeypatch.setattr(routes, "ValidatedLegacyLanStart", Lan)
    result = await routes.set_config(
        routes.ConfigInput(printer_host="192.168.1.20", ha_device_id="printer"),
        SimpleNamespace(app=SimpleNamespace(state=state)),
    )
    assert result == {"ok": True}
    assert service.started is True
    assert service.lan.host == "192.168.1.20"
    assert state.integration_error is None


@pytest.mark.asyncio
async def test_gcode_upload_rejected_before_creating_job(tmp_path):
    from fastapi import UploadFile
    from io import BytesIO
    service = AppService(Settings(data_dir=tmp_path))
    with pytest.raises(ServiceError, match="STL or 3MF"):
        await service.create_job(UploadFile(filename="part_MK3S.gcode", file=BytesIO(b"G1 X1")))
    assert service.store.list() == []


def test_ip_falls_back_to_registry_when_live_address_invalid():
    rows = [{"translation_key": "ip_address", "entity_id": "sensor.ip"}]
    states = {"sensor.ip": {"state": "unavailable", "attributes": {}}}
    assert _printer_ip({"configuration_url": "http://10.0.0.4/status"}, rows, states) == "10.0.0.4"
