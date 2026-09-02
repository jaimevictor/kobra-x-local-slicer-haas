from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.core.models import JobRecord, JobState, Orientation
from app.core.service import AppService
from app.kobra.ace import parse_ace_payload
from app.slicer.orca import OrcaError


def _recoverable_job(service: AppService) -> None:
    service.store.create_dir("job")
    service.store.save(
        JobRecord(
            id="job",
            original_filename="cube.stl",
            input_filename="input.stl",
            input_type="stl",
            state=JobState.FAILED_RECOVERABLE,
            error="Orca slicing failed: exit=-11",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )


@pytest.mark.asyncio
async def test_orientation_recovers_a_failed_slice_for_retry(tmp_path):
    service = AppService(Settings(data_dir=tmp_path))
    _recoverable_job(service)

    record, preview = await service.set_orientation("job", Orientation.ROTATE_Z_90)

    assert preview is None
    assert record.state == JobState.READY_TO_SLICE
    assert record.orientation == Orientation.ROTATE_Z_90
    assert record.error is None


def test_support_change_recovers_a_failed_slice_for_retry(tmp_path):
    service = AppService(Settings(data_dir=tmp_path))
    _recoverable_job(service)

    record = service.set_supports("job", True)

    assert record.state == JobState.READY_TO_SLICE
    assert record.supports_enabled is True
    assert record.error is None


@pytest.mark.asyncio
async def test_orca_failure_is_recorded_as_recoverable(monkeypatch, tmp_path):
    service = AppService(Settings(data_dir=tmp_path))
    service.store.create_dir("job")
    service.store.save(
        JobRecord(
            id="job",
            original_filename="cube.stl",
            input_filename="input.stl",
            input_type="stl",
            state=JobState.READY_TO_SLICE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    ace = parse_ace_payload(
        {"data": {"slots": [{"materialType": "PLA", "isLoaded": True}]}}
    )

    async def fresh_ace(_job_id):
        return ace

    async def printer_snapshot():
        return None

    async def broken_slice(*_args, **_kwargs):
        raise OrcaError("Orca slicing failed: exit=-11")

    monkeypatch.setattr(service, "ace", fresh_ace)
    monkeypatch.setattr(service, "printer_snapshot", printer_snapshot)
    monkeypatch.setattr(service.orca, "slice", broken_slice)

    with pytest.raises(OrcaError, match="exit=-11"):
        await service.slice("job")

    record = service.job("job")
    assert record.state == JobState.FAILED_RECOVERABLE
    assert record.error == "Orca slicing failed: exit=-11"
