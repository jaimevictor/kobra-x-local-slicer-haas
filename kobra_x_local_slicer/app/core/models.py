from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobState(str, Enum):
    UPLOADED = "UPLOADED"; INSPECTING = "INSPECTING"; READY_TO_SLICE = "READY_TO_SLICE"
    SLICING = "SLICING"; SLICED = "SLICED"; AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    PREFLIGHT = "PREFLIGHT"; UPLOADING_TO_PRINTER = "UPLOADING_TO_PRINTER"
    UPLOADED_TO_PRINTER = "UPLOADED_TO_PRINTER"; STARTING = "STARTING"; START_UNKNOWN = "START_UNKNOWN"
    PRINT_ACCEPTED = "PRINT_ACCEPTED"; MONITORING = "MONITORING"; FAILED = "FAILED"
    CANCELLED = "CANCELLED"; EXPIRED = "EXPIRED"


class StartPublishState(str, Enum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    INTENT_PERSISTED = "INTENT_PERSISTED"
    PUBLISH_ATTEMPTED = "PUBLISH_ATTEMPTED"
    ACK_ACCEPTED = "ACK_ACCEPTED"
    ACK_REJECTED = "ACK_REJECTED"
    DELIVERY_UNKNOWN = "DELIVERY_UNKNOWN"
    RECONCILED = "RECONCILED"


class Orientation(str, Enum):
    ORIGINAL = "original"; ROTATE_X_90 = "rotate_x_90"; ROTATE_Y_90 = "rotate_y_90"; ROTATE_Z_90 = "rotate_z_90"; AUTO = "auto"


class Bounds(BaseModel):
    min_x: float; min_y: float; min_z: float; max_x: float; max_y: float; max_z: float
    @property
    def size(self) -> tuple[float, float, float]: return (self.max_x-self.min_x, self.max_y-self.min_y, self.max_z-self.min_z)


class AceSlot(BaseModel):
    human_slot: int
    protocol_slot_index: int
    material_type: str | None = None
    rgb: tuple[int, int, int] | None = None
    loaded: bool | None = None
    color_hex: str | None = None
    colors_hex: list[str] = Field(default_factory=list)
    is_multi_color: bool | None = None
    sku: str | None = None
    spool_loaded: bool | None = None
    status: str | None = None
    edit_status: str | None = None
    consumables_percent: float | None = None
    raw_state: str | None = None


class AceSnapshot(BaseModel):
    raw: dict[str, Any]
    parsed: list[dict[str, Any]]
    normalized: list[AceSlot]
    loaded_slot: int | None = None


class PrinterJobSnapshot(BaseModel):
    name: str | None = None
    state: str | None = None
    progress: float | None = None
    current_layer: int | None = None
    total_layers: int | None = None
    elapsed_minutes: float | None = None
    remaining_minutes: float | None = None
    eta: str | None = None
    paused: bool | None = None


class PrinterThermalSnapshot(BaseModel):
    nozzle_current: float | None = None
    nozzle_target: float | None = None
    bed_current: float | None = None
    bed_target: float | None = None


class PrinterFaultSnapshot(BaseModel):
    code: str | None = None
    message: str | None = None


class PrinterSnapshot(BaseModel):
    source: str = "home_assistant:anycubic_cloud"
    integration_version: str | None = None
    printer_device_id: str | None = None
    observed_at: datetime
    stale: bool
    ha_connected: bool
    essential_entities_available: bool
    online: bool | None = None
    available: bool | None = None
    busy: bool | None = None
    status: str | None = None
    job: PrinterJobSnapshot = Field(default_factory=PrinterJobSnapshot)
    thermal: PrinterThermalSnapshot = Field(default_factory=PrinterThermalSnapshot)
    ace: AceSnapshot | None = None
    fault: PrinterFaultSnapshot = Field(default_factory=PrinterFaultSnapshot)
    capabilities: dict[str, bool] = Field(default_factory=dict)


class TemperatureStats(BaseModel):
    first_layer_nozzle: float | None = None; printing_nozzle: float | None = None
    first_layer_bed: float | None = None; printing_bed: float | None = None
    all_nozzle_targets: list[float] = Field(default_factory=list); all_bed_targets: list[float] = Field(default_factory=list)


class SliceStats(BaseModel):
    estimated_print_time_seconds: int | None = None; filament_length_mm: float | None = None; filament_mass_g: float | None = None; layer_count: int | None = None
    temperatures: TemperatureStats; dimensions: Bounds; gcode_sha256: str; gcode_bytes: int; orca_version: str
    profile_manifest_sha256: str | None = None; profile_versions: dict[str, str] = Field(default_factory=dict)


class JobRecord(BaseModel):
    id: str; original_filename: str; input_filename: str; input_type: str; state: JobState
    created_at: datetime; updated_at: datetime; orientation: Orientation = Orientation.ORIGINAL
    supports_enabled: bool = False
    selected_slot: AceSlot | None = None; ace_snapshot: AceSnapshot | None = None; slice_stats: SliceStats | None = None
    approved_gcode_sha256: str | None = None; approved_slot_snapshot: AceSlot | None = None; table_clear_confirmed: bool = False
    remote_filename: str | None = None; error: str | None = None
    printer_snapshot_at_slice: PrinterSnapshot | None = None
    action_log: list[dict[str, Any]] = Field(default_factory=list)
    start_attempt_id: str | None = None
    start_intent_created_at: datetime | None = None
    start_transport: str | None = None
    start_publish_state: StartPublishState = StartPublishState.NOT_ATTEMPTED
    start_attempted_at: datetime | None = None


class PrintStartResult(BaseModel):
    sent: bool; ack_received: bool; accepted: bool; unknown: bool; raw_ack: dict[str, Any] | None = None
