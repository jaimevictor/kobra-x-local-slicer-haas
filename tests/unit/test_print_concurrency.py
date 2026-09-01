import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.core.models import AceSlot, JobRecord, JobState, PrintStartResult
from app.core.service import AppService, ServiceError


def _record(service: AppService, job_id: str) -> JobRecord:
    directory = service.store.create_dir(job_id)
    (directory / "output.gcode").write_text("G1 X1", encoding="utf-8")
    record = JobRecord(
        id=job_id, original_filename="cube.stl", input_filename="input.stl", input_type="stl",
        state=JobState.AWAITING_CONFIRMATION, created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        approved_gcode_sha256="approved", table_clear_confirmed=True,
    )
    service.store.save(record)
    return record


class _Upload:
    def __init__(self, *args, **kwargs):
        pass

    async def upload(self, *args, **kwargs):
        return {"code": 200}


@pytest.mark.asyncio
async def test_concurrent_calls_for_one_job_publish_once(monkeypatch, tmp_path):
    service = AppService(Settings(data_dir=tmp_path))
    _record(service, "one")
    calls = 0

    async def preflight(job_id):
        record = service.job(job_id)
        record.state = JobState.PREFLIGHT
        service.store.save(record)
        return record, {"data": {"urls": {"fileUploadurl": "http://127.0.0.1:18910/gcode_upload?s=x"}}}, None, AceSlot(human_slot=1, protocol_slot_index=0, material_type="PLA")

    async def start_once(payload):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.02)
        return PrintStartResult(sent=True, ack_received=False, accepted=False, unknown=True)

    service.lan = SimpleNamespace(broker=SimpleNamespace(device_id="printer"), publish_print_start_once=start_once)
    monkeypatch.setattr(service, "preflight", preflight)
    with patch("app.core.service.DirectLanFileTransfer", _Upload):
        results = await asyncio.gather(service.print("one"), service.print("one"), return_exceptions=True)
    assert calls == 1
    assert sum(isinstance(result, ServiceError) for result in results) == 1
    record = service.job("one")
    assert record.start_attempt_id
    assert record.start_publish_state.value == "DELIVERY_UNKNOWN"


@pytest.mark.asyncio
async def test_two_jobs_do_not_overlap_start_transactions(monkeypatch, tmp_path):
    service = AppService(Settings(data_dir=tmp_path))
    _record(service, "one")
    _record(service, "two")
    active = maximum = calls = 0

    async def preflight(job_id):
        record = service.job(job_id)
        record.state = JobState.PREFLIGHT
        service.store.save(record)
        return record, {"data": {"urls": {"fileUploadurl": "http://127.0.0.1:18910/gcode_upload?s=x"}}}, None, AceSlot(human_slot=1, protocol_slot_index=0, material_type="PLA")

    async def start_once(payload):
        nonlocal active, maximum, calls
        calls += 1
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.02)
        active -= 1
        return PrintStartResult(sent=True, ack_received=False, accepted=False, unknown=True)

    service.lan = SimpleNamespace(broker=SimpleNamespace(device_id="printer"), publish_print_start_once=start_once)
    monkeypatch.setattr(service, "preflight", preflight)
    with patch("app.core.service.DirectLanFileTransfer", _Upload):
        await asyncio.gather(service.print("one"), service.print("two"))
    assert calls == 2
    assert maximum == 1
