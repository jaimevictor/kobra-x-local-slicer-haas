from __future__ import annotations
import shutil
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from .config import Settings
from .models import JobRecord, JobState


class JobStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        (settings.data_dir / "jobs").mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        return self.settings.data_dir / "jobs" / job_id

    def create_dir(self, job_id: str) -> Path:
        p = self.job_dir(job_id)
        p.mkdir(mode=0o700)
        return p

    def save(self, record: JobRecord) -> None:
        target = self.job_dir(record.id) / "metadata.json"
        temporary = self.job_dir(record.id) / f".metadata-{uuid.uuid4().hex}.tmp"
        payload = record.model_dump_json(indent=2)
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

    def load(self, job_id: str) -> JobRecord:
        return JobRecord.model_validate_json(
            (self.job_dir(job_id) / "metadata.json").read_text(encoding="utf-8")
        )

    def list(self) -> list[JobRecord]:
        records = []
        for directory in (self.settings.data_dir / "jobs").iterdir():
            try:
                records.append(self.load(directory.name))
            except (FileNotFoundError, ValueError):
                continue
        return sorted(records, key=lambda record: record.updated_at, reverse=True)

    def enforce_limits(self, incoming_bytes: int = 0) -> None:
        jobs = self.settings.data_dir / "jobs"
        self.cleanup()
        used = sum(p.stat().st_size for p in jobs.rglob("*") if p.is_file())
        if used + incoming_bytes > self.settings.jobs_storage_limit_bytes:
            raise RuntimeError("job storage quota exceeded")

    def enforce_max_jobs(self) -> None:
        if len(self.list()) >= self.settings.max_jobs:
            raise RuntimeError("maximum retained jobs reached")

    def cleanup(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(hours=self.settings.retention_hours)
        for p in (self.settings.data_dir / "jobs").iterdir():
            try:
                r = self.load(p.name)
                if r.updated_at < cutoff and r.state not in {
                    JobState.SLICING,
                    JobState.PREFLIGHT,
                    JobState.UPLOADING_TO_PRINTER,
                    JobState.UPLOADED_TO_PRINTER,
                    JobState.STARTING,
                    JobState.START_UNKNOWN,
                    JobState.PRINT_ACCEPTED,
                    JobState.MONITORING,
                    JobState.PRINTING,
                    JobState.PAUSED,
                }:
                    shutil.rmtree(p)
            except (FileNotFoundError, ValueError):
                continue
