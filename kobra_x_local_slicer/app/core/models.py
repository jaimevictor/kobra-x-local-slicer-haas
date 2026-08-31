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


class AceSnapshot(BaseModel):
    raw: dict[str, Any]
    parsed: list[dict[str, Any]]
    normalized: list[AceSlot]


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
    selected_slot: AceSlot | None = None; ace_snapshot: AceSnapshot | None = None; slice_stats: SliceStats | None = None
    approved_gcode_sha256: str | None = None; approved_slot_snapshot: AceSlot | None = None; table_clear_confirmed: bool = False
    remote_filename: str | None = None; ha_error_baseline: dict[str, str] = Field(default_factory=dict); error: str | None = None


class PrintStartResult(BaseModel):
    sent: bool; ack_received: bool; accepted: bool; unknown: bool; raw_ack: dict[str, Any] | None = None
