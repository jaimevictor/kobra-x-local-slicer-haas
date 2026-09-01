from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.models import JobRecord, JobState, PrinterJobSnapshot, PrinterSnapshot
from app.core.service import AppService, ServiceError


def _snapshot(*, paused: bool, busy: bool = True) -> PrinterSnapshot:
    now = datetime.now(UTC)
    return PrinterSnapshot(
        observed_at=now,
        snapshot_received_at=now,
        last_health_check_at=now,
        stale=False,
        ha_connected=True,
        essential_entities_available=True,
        online=True,
        busy=busy,
        job=PrinterJobSnapshot(in_progress=busy, paused=paused),
    )


@pytest.mark.asyncio
async def test_pause_printing_job_requires_and_records_observed_transition(
    monkeypatch, tmp_path
):
    service = AppService(Settings(data_dir=tmp_path, ha_device_id="device"))
    service.store.create_dir("job")
    service.store.save(
        JobRecord(
            id="job",
            original_filename="cube.stl",
            input_filename="input.stl",
            input_type="stl",
            state=JobState.PRINTING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    calls = 0

    async def printer_snapshot():
        nonlocal calls
        calls += 1
        return _snapshot(paused=calls > 1)

    async def press(action):
        assert action == "pause"
        return {"action": action, "accepted": True}

    monkeypatch.setattr(service, "printer_snapshot", printer_snapshot)
    service._ha = SimpleNamespace(printer_device_id="device", press=press)

    record = await service.control("job", "pause")

    assert record.action_log[-1]["confirmed"] is True
    assert record.action_log[-1]["confirmed_at"]


@pytest.mark.asyncio
async def test_pause_rejects_non_printing_state(tmp_path):
    service = AppService(Settings(data_dir=tmp_path, ha_device_id="device"))
    service.store.create_dir("job")
    service.store.save(
        JobRecord(
            id="job",
            original_filename="cube.stl",
            input_filename="input.stl",
            input_type="stl",
            state=JobState.COMPLETED,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )

    with pytest.raises(ServiceError, match="cannot pause"):
        await service.control("job", "pause")


@pytest.mark.asyncio
async def test_cancel_transitions_job_only_after_inactive_state(monkeypatch, tmp_path):
    service = AppService(Settings(data_dir=tmp_path, ha_device_id="device"))
    service.store.create_dir("job")
    service.store.save(
        JobRecord(
            id="job",
            original_filename="cube.stl",
            input_filename="input.stl",
            input_type="stl",
            state=JobState.PRINTING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    calls = 0

    async def printer_snapshot():
        nonlocal calls
        calls += 1
        return _snapshot(paused=False, busy=calls == 1)

    async def press(action):
        assert action == "cancel"
        return {"action": action, "accepted": True}

    monkeypatch.setattr(service, "printer_snapshot", printer_snapshot)
    service._ha = SimpleNamespace(printer_device_id="device", press=press)

    record = await service.control("job", "cancel")

    assert record.state == JobState.CANCELLED
    assert record.action_log[-1]["confirmed"] is True
