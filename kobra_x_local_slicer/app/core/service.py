from __future__ import annotations

import hashlib
from dataclasses import asdict
import json
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.core.config import Settings
from app.core.models import JobRecord, JobState, Orientation
from app.core.security import sanitize_filename
from app.core.state_machine import assert_transition
from app.core.storage import JobStore
from app.ha.client import HomeAssistantClient, HomeAssistantError, new_errors
from app.kobra.ace import parse_ace_payload, pla_slots, select_default_pla
from app.kobra.lan import KobraLanSession
from app.kobra.upload import KobraUploadClient, extract_upload_url
from app.slicer.gcode import inspect_gcode, write_preview
from app.slicer.geometry import inspect_stl
from app.slicer.orca import OrcaRunner
from app.slicer.three_mf import inspect_3mf, sanitize_3mf_for_slicing


class ServiceError(RuntimeError):
    pass


ACTIVE_STATES = {"checking", "heating", "printing", "paused", "pausing"}
FREE_STATES = {"free", "idle", "available", "ready"}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _lan_state(info: dict[str, Any], print_report: dict[str, Any] | None) -> tuple[str | None, str | None, bool]:
    data = info.get("data") if isinstance(info.get("data"), dict) else {}
    state = str(data.get("state") or info.get("state") or "").lower() or None
    filename = None
    active = state in ACTIVE_STATES if state else False
    if isinstance(print_report, dict):
        p_data = print_report.get("data") if isinstance(print_report.get("data"), dict) else {}
        p_state = str(print_report.get("state") or p_data.get("state") or "").lower()
        if p_state:
            state = p_state
            active = p_state in ACTIVE_STATES
        f = p_data.get("filename")
        if f:
            filename = str(f)
    return state, filename, active


class AppService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = JobStore(settings)
        self.orca = OrcaRunner(
            profile_dir=settings.profile_dir,
            timeout_seconds=settings.slicing_timeout_seconds,
            gcode_limit_bytes=settings.gcode_limit_bytes,
        )
        self.lan = KobraLanSession(settings.printer_host) if settings.printer_host else None
        self._job_locks: dict[str, Any] = {}

    async def close(self) -> None:
        if self.lan:
            await self.lan.close()

    def _save(self, record: JobRecord) -> JobRecord:
        record.updated_at = _utcnow()
        self.store.save(record)
        return record

    def _transition(self, record: JobRecord, target: JobState) -> None:
        assert_transition(record.state, target)
        record.state = target
        self._save(record)

    def job(self, job_id: str) -> JobRecord:
        return self.store.load(job_id)

    def _slicing_input(self, record: JobRecord) -> Path:
        directory = self.store.job_dir(record.id)
        if record.input_type == "3mf":
            sanitized = directory / "input_sanitized.3mf"
            if not sanitized.is_file():
                raise ServiceError("sanitized 3MF missing; upload/inspection must be repeated")
            return sanitized
        return directory / record.input_filename

    async def create_job(self, upload: UploadFile) -> JobRecord:
        filename = sanitize_filename(upload.filename or "upload", allowed_extensions={".stl", ".3mf"})
        self.store.enforce_limits()
        job_id = str(uuid.uuid4())
        directory = self.store.create_dir(job_id)
        suffix = Path(filename).suffix.lower()
        input_name = f"input{suffix}"
        path = directory / input_name
        written = 0
        try:
            with path.open("xb") as out:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > self.settings.upload_limit_bytes:
                        raise ServiceError("upload exceeds configured limit")
                    out.write(chunk)
            if written == 0:
                raise ServiceError("empty upload")
            self.store.enforce_limits(incoming_bytes=0)
            record = JobRecord(
                id=job_id,
                original_filename=filename,
                input_filename=input_name,
                input_type=suffix[1:],
                state=JobState.UPLOADED,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            self.store.save(record)
            self._transition(record, JobState.INSPECTING)
            if suffix == ".3mf":
                inspection = inspect_3mf(path, max_decompressed=self.settings.decompressed_3mf_limit_bytes)
                removed = sanitize_3mf_for_slicing(
                    path, directory / "input_sanitized.3mf",
                    max_decompressed=self.settings.decompressed_3mf_limit_bytes,
                )
                payload = asdict(inspection)
                payload["removed_slicing_metadata"] = removed
                (directory / "input_inspection.json").write_text(
                    json.dumps(payload, indent=2), encoding="utf-8"
                )
            else:
                mesh = inspect_stl(path)
                sx, sy, sz = mesh.bounds.size
                if sx > 260.01 or sy > 260.01 or sz > 260.01:
                    raise ServiceError(f"model bounding box {sx:.2f}x{sy:.2f}x{sz:.2f} exceeds Kobra X volume before orientation")
                (directory / "input_inspection.json").write_text(
                    json.dumps({"triangles": mesh.triangles, "volume_mm3": mesh.volume_mm3, "bounds": mesh.bounds.model_dump()}, indent=2),
                    encoding="utf-8",
                )
            if self.settings.ha_entity_map:
                try:
                    record.ha_error_baseline = (await HomeAssistantClient().cross_check(self.settings.ha_entity_map)).error_states
                    self._save(record)
                except Exception:
                    # Upload/inspection may continue; final preflight requires a successful HA cross-check.
                    pass
            self._transition(record, JobState.READY_TO_SLICE)
            return record
        except Exception as exc:
            try:
                record = self.store.load(job_id)
                if record.state not in {JobState.FAILED, JobState.CANCELLED}:
                    record.state = JobState.FAILED
                    record.error = str(exc)
                    self._save(record)
            except Exception:
                pass
            raise
        finally:
            await upload.close()

    async def ace(self, job_id: str | None = None):
        if not self.lan:
            raise ServiceError("printer_host not configured")
        payload = await self.lan.query_ace()
        snapshot = parse_ace_payload(payload)
        if job_id:
            record = self.job(job_id)
            record.ace_snapshot = snapshot
            default = select_default_pla(snapshot)
            if record.selected_slot is None and default is not None:
                record.selected_slot = default
            self._save(record)
        return snapshot

    async def select_slot(self, job_id: str, human_slot: int) -> JobRecord:
        record = self.job(job_id)
        snapshot = await self.ace(job_id)
        matches = [s for s in snapshot.normalized if s.human_slot == human_slot]
        if len(matches) != 1:
            raise ServiceError("ACE slot not found")
        slot = matches[0]
        if slot.material_type != "PLA":
            raise ServiceError("Material não suportado pelo slicer automático V1. Selecione um slot PLA.")
        record = self.job(job_id)
        record.selected_slot = slot
        record.approved_gcode_sha256 = None
        record.approved_slot_snapshot = None
        record.table_clear_confirmed = False
        return self._save(record)

    async def set_orientation(self, job_id: str, orientation: Orientation) -> tuple[JobRecord, str | None]:
        record = self.job(job_id)
        if record.state not in {JobState.READY_TO_SLICE, JobState.SLICED, JobState.AWAITING_CONFIRMATION}:
            raise ServiceError("orientation cannot change in current state")
        record.orientation = orientation
        record.slice_stats = None
        record.approved_gcode_sha256 = None
        record.approved_slot_snapshot = None
        record.table_clear_confirmed = False
        if record.state in {JobState.SLICED, JobState.AWAITING_CONFIRMATION}:
            self._transition(record, JobState.READY_TO_SLICE)
        preview: str | None = None
        if orientation == Orientation.AUTO:
            directory = self.store.job_dir(job_id)
            oriented = await self.orca.export_oriented_3mf(self._slicing_input(record), directory, orientation)
            preview = oriented.name
        return self._save(record), preview

    def set_supports(self, job_id: str, enabled: bool) -> JobRecord:
        record = self.job(job_id)
        if record.state not in {JobState.READY_TO_SLICE, JobState.SLICED, JobState.AWAITING_CONFIRMATION}:
            raise ServiceError("supports cannot change in current state")
        record.supports_enabled = enabled
        record.slice_stats = None
        record.approved_gcode_sha256 = None
        record.approved_slot_snapshot = None
        record.table_clear_confirmed = False
        if record.state in {JobState.SLICED, JobState.AWAITING_CONFIRMATION}:
            self._transition(record, JobState.READY_TO_SLICE)
        return self._save(record)

    async def slice(self, job_id: str) -> JobRecord:
        record = self.job(job_id)
        if record.state not in {JobState.READY_TO_SLICE, JobState.SLICED, JobState.AWAITING_CONFIRMATION}:
            raise ServiceError("job is not ready to slice")
        fresh_ace = await self.ace(job_id)
        record = self.job(job_id)
        pla = pla_slots(fresh_ace)
        if not pla:
            raise ServiceError("nenhum slot PLA disponível")
        if record.selected_slot is None:
            default = select_default_pla(fresh_ace)
            if default is None:
                raise ServiceError("multiple PLA slots available; select one")
            record.selected_slot = default
        current = next((s for s in fresh_ace.normalized if s.protocol_slot_index == record.selected_slot.protocol_slot_index), None)
        if current is None or current.material_type != "PLA":
            raise ServiceError("selected ACE slot no longer contains PLA")
        record.selected_slot = current
        if record.state != JobState.READY_TO_SLICE:
            self._transition(record, JobState.READY_TO_SLICE)
        else:
            self._save(record)
        self._transition(record, JobState.SLICING)
        directory = self.store.job_dir(job_id)
        try:
            gcode = await self.orca.slice(self._slicing_input(record), directory, record.orientation, record.supports_enabled)
            analysis = inspect_gcode(
                gcode,
                filament_profile=self.orca.load_filament_profile(),
                gcode_limit_bytes=self.settings.gcode_limit_bytes,
                orca_version=self.orca.version,
                profile_manifest_sha256=self.orca.manifest_sha256(),
                profile_versions=self.orca.profile_versions(),
            )
            write_preview(directory / "toolpath.json", analysis.preview_layers)
            record.slice_stats = analysis.stats
            record.approved_gcode_sha256 = None
            record.approved_slot_snapshot = None
            record.table_clear_confirmed = False
            self._transition(record, JobState.SLICED)
            self._transition(record, JobState.AWAITING_CONFIRMATION)
            return record
        except Exception as exc:
            record.state = JobState.FAILED
            record.error = str(exc)
            self._save(record)
            raise

    def confirm(self, job_id: str, gcode_sha256: str, table_clear: bool) -> JobRecord:
        record = self.job(job_id)
        if record.state != JobState.AWAITING_CONFIRMATION or not record.slice_stats or not record.selected_slot:
            raise ServiceError("job is not awaiting confirmation")
        actual = _hash_file(self.store.job_dir(job_id) / "output.gcode")
        if actual != record.slice_stats.gcode_sha256 or gcode_sha256 != actual:
            raise ServiceError("G-code hash changed; re-slice required")
        if not table_clear:
            raise ServiceError("A mesa está livre e pronta must be confirmed")
        record.approved_gcode_sha256 = actual
        record.approved_slot_snapshot = record.selected_slot.model_copy(deep=True)
        record.table_clear_confirmed = True
        return self._save(record)

    async def _ha_cross_check(self, record: JobRecord):
        if not self.settings.ha_entity_map:
            raise ServiceError("Home Assistant entity mapping is not configured")
        try:
            ha = await HomeAssistantClient().cross_check(self.settings.ha_entity_map)
        except HomeAssistantError as exc:
            raise ServiceError(f"Home Assistant cross-check failed: {exc}") from exc
        changed_errors = new_errors(ha.error_states, record.ha_error_baseline)
        if changed_errors or ha.current_fault is True:
            raise ServiceError(f"new/current Home Assistant error state: {changed_errors or 'fault active'}")
        return ha

    async def preflight(self, job_id: str) -> tuple[JobRecord, dict[str, Any], Any, Any]:
        record = self.job(job_id)
        if record.state != JobState.AWAITING_CONFIRMATION:
            raise ServiceError("job is not ready for print preflight")
        if not record.table_clear_confirmed or not record.approved_gcode_sha256:
            raise ServiceError("human confirmation missing")
        directory = self.store.job_dir(job_id)
        gcode = directory / "output.gcode"
        if not gcode.is_file() or _hash_file(gcode) != record.approved_gcode_sha256:
            raise ServiceError("approved G-code hash no longer matches")
        if not self.lan:
            raise ServiceError("printer_host not configured")
        self._transition(record, JobState.PREFLIGHT)
        try:
            info = await self.lan.query_info()
            print_report = await self.lan.query_print()
            state, current_filename, lan_active = _lan_state(info, print_report)
            if state is None or state not in FREE_STATES or lan_active:
                raise ServiceError(f"printer LAN state is not free/available: {state}")
            ha = await self._ha_cross_check(record)
            required_ha = {
                "online": ha.online,
                "available": ha.available,
                "busy": ha.busy,
                "job_in_progress": ha.job_in_progress,
                "state": ha.state,
            }
            missing = [key for key, value in required_ha.items() if value is None]
            if missing:
                raise ServiceError(f"Home Assistant cross-check is incomplete for: {', '.join(missing)}")
            if ha.online is not True or ha.available is not True or ha.busy is not False or ha.job_in_progress is not False:
                raise ServiceError(f"Home Assistant reports printer unavailable/busy: {ha.model_dump()}")
            if str(ha.state).lower() not in FREE_STATES:
                raise ServiceError(f"Home Assistant printer state disagrees with LAN: {ha.state} vs {state}")

            fresh_ace = parse_ace_payload(await self.lan.query_ace())
            if record.selected_slot is None or record.approved_slot_snapshot is None:
                raise ServiceError("selected/approved ACE slot missing")
            slot = next((s for s in fresh_ace.normalized if s.protocol_slot_index == record.selected_slot.protocol_slot_index), None)
            if slot is None:
                raise ServiceError("selected ACE slot no longer exists")
            if slot.material_type != "PLA":
                record.approved_gcode_sha256 = None
                record.approved_slot_snapshot = None
                record.table_clear_confirmed = False
                self._transition(record, JobState.AWAITING_CONFIRMATION)
                self._transition(record, JobState.READY_TO_SLICE)
                raise ServiceError("ACE material changed; slice invalidated and re-slice required")
            if slot.rgb != record.approved_slot_snapshot.rgb:
                record.selected_slot = slot
                record.approved_gcode_sha256 = None
                record.approved_slot_snapshot = None
                record.table_clear_confirmed = False
                self._transition(record, JobState.AWAITING_CONFIRMATION)
                raise ServiceError("ACE color changed; preview/mapping updated and human confirmation is required again")
            record.ace_snapshot = fresh_ace
            record.selected_slot = slot
            return record, info, ha, slot
        except Exception:
            if record.state == JobState.PREFLIGHT:
                self._transition(record, JobState.AWAITING_CONFIRMATION)
            raise

    async def print(self, job_id: str) -> JobRecord:
        if os.getenv("KOBRA_HARDWARE_TEST") != "1" or os.getenv("KOBRA_ALLOW_PHYSICAL_PRINT") != "1":
            raise ServiceError("physical print/start is disabled; set KOBRA_HARDWARE_TEST=1 and KOBRA_ALLOW_PHYSICAL_PRINT=1 for a controlled hardware test")
        record, info, _ha, slot = await self.preflight(job_id)
        assert self.lan and self.lan.broker and record.approved_gcode_sha256
        directory = self.store.job_dir(job_id)
        gcode = directory / "output.gcode"
        remote_filename = sanitize_filename(f"kx_{job_id[:8]}_{Path(record.original_filename).stem}.gcode")
        upload_url = extract_upload_url(info)
        self._transition(record, JobState.UPLOADING_TO_PRINTER)
        uploader = KobraUploadClient(
            self.settings.printer_host,
            device_id=self.lan.broker.device_id,
            client_version="0.1.3",
        )
        try:
            await uploader.upload(upload_url, gcode, remote_filename)
        except Exception as exc:
            record.state = JobState.FAILED
            record.error = f"upload failed; not retried automatically: {exc}"
            self._save(record)
            raise
        record.remote_filename = remote_filename
        self._transition(record, JobState.UPLOADED_TO_PRINTER)
        self._transition(record, JobState.STARTING)
        rgb = list(slot.rgb or (255, 255, 255))
        payload = {
            "filename": remote_filename,
            "taskid": str(int(time.time())),
            "use_ams": True,
            "ams_box_mapping": [
                {"slot_index": slot.protocol_slot_index, "material_type": "PLA", "color": rgb}
            ],
        }
        result = await self.lan.publish_print_start_once(payload)
        if result.accepted:
            self._transition(record, JobState.PRINT_ACCEPTED)
            self._transition(record, JobState.MONITORING)
            return record

        # Critical idempotency rule: never publish print/start a second time.
        record.state = JobState.START_UNKNOWN
        record.error = "print/start delivery/ACK uncertain; command will not be retried"
        self._save(record)
        report = await self.lan.query_print(timeout=5.0)
        if report:
            p_data = report.get("data") if isinstance(report.get("data"), dict) else {}
            p_state = str(report.get("state") or p_data.get("state") or "").lower()
            p_filename = str(p_data.get("filename") or "")
            if p_state in ACTIVE_STATES and p_filename == remote_filename:
                self._transition(record, JobState.PRINT_ACCEPTED)
                self._transition(record, JobState.MONITORING)
        return record
