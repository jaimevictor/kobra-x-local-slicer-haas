from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.core.models import JobRecord, JobState, StartPublishState
from app.core.service import AppService, ServiceError


def _job(service, job_id, state):
    service.store.create_dir(job_id)
    record = JobRecord(
        id=job_id, original_filename="cube.stl", input_filename="input.stl", input_type="stl",
        state=state, created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    service.store.save(record)


@pytest.mark.asyncio
async def test_restart_recovers_transient_states_without_starting(monkeypatch, tmp_path):
    service = AppService(Settings(data_dir=tmp_path))
    _job(service, "slice", JobState.SLICING)
    _job(service, "preflight", JobState.PREFLIGHT)
    _job(service, "uploading", JobState.UPLOADING_TO_PRINTER)
    _job(service, "uploaded", JobState.UPLOADED_TO_PRINTER)
    _job(service, "starting", JobState.STARTING)

    async def no_ha():
        raise ServiceError("HA unavailable")

    monkeypatch.setattr(service, "printer_snapshot", no_ha)
    await service.reconcile_active_jobs()
    assert service.job("slice").state == JobState.FAILED_RECOVERABLE
    assert service.job("preflight").state == JobState.AWAITING_CONFIRMATION
    assert service.job("uploading").state == JobState.FAILED_RECOVERABLE
    assert service.job("uploaded").state == JobState.AWAITING_CONFIRMATION
    assert service.job("starting").state == JobState.START_UNKNOWN
