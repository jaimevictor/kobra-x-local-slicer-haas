from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.models import Bounds, SliceStats, TemperatureStats

_TEMP = re.compile(r"\bS(-?\d+(?:\.\d+)?)\b", re.I)
_AXIS = re.compile(r"\b([XYZE])(-?(?:\d+(?:\.\d*)?|\.\d+))", re.I)
_TIME = re.compile(r";\s*(?:model printing time|estimated printing time)\s*(?:=|:)\s*(.+)", re.I)
_FILAMENT_MM = re.compile(r";\s*filament used \[mm\]\s*=\s*([0-9.]+)", re.I)
_FILAMENT_G = re.compile(r";\s*filament used \[g\]\s*=\s*([0-9.]+)", re.I)
_LAYER_COUNT = re.compile(r";\s*(?:total layer number|total_layer_count)\s*=\s*(\d+)", re.I)
_LAYER_MARK = re.compile(r";\s*(?:LAYER_CHANGE|layer:)\s*(\d+)?", re.I)


class GCodeValidationError(ValueError):
    pass


@dataclass(slots=True)
class GCodeAnalysis:
    stats: SliceStats
    tools: set[int]
    has_m600: bool
    has_g9111: bool
    preview_layers: list[list[tuple[float, float]]]


def _first(v: Any, default=None):
    if isinstance(v, list):
        return v[0] if v else default
    return v if v is not None else default


def _num(v: Any, default: float | None = None) -> float | None:
    try:
        return float(_first(v))
    except (TypeError, ValueError):
        return default


def _parse_duration(text: str) -> int | None:
    total = 0
    matched = False
    for value, unit in re.findall(r"(\d+)\s*([dhms])", text.lower()):
        matched = True
        total += int(value) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
    return total if matched else None


def _target(line: str) -> float | None:
    m = _TEMP.search(line)
    return float(m.group(1)) if m else None


def _temperature_policy(filament_profile: dict[str, Any]) -> tuple[float, float, float, float]:
    nozzle_low = _num(filament_profile.get("nozzle_temperature_range_low"))
    nozzle_high = _num(filament_profile.get("nozzle_temperature_range_high"))
    if nozzle_low is None or nozzle_high is None:
        vals = [x for x in (_num(filament_profile.get("nozzle_temperature")), _num(filament_profile.get("nozzle_temperature_initial_layer"))) if x is not None]
        if not vals:
            raise GCodeValidationError("filament profile lacks nozzle temperature policy")
        nozzle_low, nozzle_high = min(vals) - 10, max(vals) + 10
    bed_values = []
    for key, value in filament_profile.items():
        if key.endswith("plate_temp") or key.endswith("plate_temp_initial_layer"):
            n = _num(value)
            if n is not None and n > 0:
                bed_values.append(n)
    if not bed_values:
        raise GCodeValidationError("filament profile lacks bed temperature policy")
    return nozzle_low, nozzle_high, max(0, min(bed_values) - 5), max(bed_values) + 5


def inspect_gcode(
    path: Path,
    *,
    filament_profile: dict[str, Any],
    gcode_limit_bytes: int,
    orca_version: str,
    profile_manifest_sha256: str | None = None,
    profile_versions: dict[str, str] | None = None,
) -> GCodeAnalysis:
    size = path.stat().st_size
    if size <= 0 or size > gcode_limit_bytes:
        raise GCodeValidationError("G-code empty or exceeds configured size limit")

    sha = hashlib.sha256()
    nozzle_targets: list[float] = []
    bed_targets: list[float] = []
    tools: set[int] = set()
    has_m600 = False
    has_g9111 = False
    layer_count: int | None = None
    estimated: int | None = None
    filament_mm: float | None = None
    filament_g: float | None = None
    absolute_xyz = True
    absolute_e = True
    pos = {"X": 0.0, "Y": 0.0, "Z": 0.0, "E": 0.0}
    mins = [math.inf, math.inf, math.inf]
    maxs = [-math.inf, -math.inf, -math.inf]
    preview_layers: list[list[tuple[float, float]]] = [[]]
    current_preview_layer = 0
    first_layer_nozzle = first_layer_bed = None
    second_layer_seen = False
    last_extrusion_z: float | None = None

    with path.open("rb") as raw:
        for raw_line in raw:
            sha.update(raw_line)
            line = raw_line.decode("utf-8", "replace").strip()
            mt = _TIME.match(line)
            if mt and estimated is None:
                estimated = _parse_duration(mt.group(1))
            mm = _FILAMENT_MM.match(line)
            if mm:
                filament_mm = float(mm.group(1))
            mg = _FILAMENT_G.match(line)
            if mg:
                filament_g = float(mg.group(1))
            ml = _LAYER_COUNT.match(line)
            if ml:
                layer_count = int(ml.group(1))
            if "LAYER_CHANGE" in line.upper() or line.upper().startswith(";LAYER:"):
                if preview_layers[current_preview_layer]:
                    preview_layers.append([])
                    current_preview_layer += 1
                    if current_preview_layer >= 1:
                        second_layer_seen = True
            command = line.split(";", 1)[0].strip()
            if not command:
                continue
            upper = command.upper()
            if upper.startswith("G9111"):
                has_g9111 = True
                mb = re.search(r"\bBEDTEMP=(-?\d+(?:\.\d+)?)", upper)
                mn = re.search(r"\bEXTRUDERTEMP=(-?\d+(?:\.\d+)?)", upper)
                if mb:
                    bed_targets.append(float(mb.group(1)))
                    first_layer_bed = first_layer_bed or float(mb.group(1))
                if mn:
                    nozzle_targets.append(float(mn.group(1)))
                    first_layer_nozzle = first_layer_nozzle or float(mn.group(1))
            code = upper.split()[0]
            if code in {"M104", "M109"}:
                v = _target(upper)
                if v is not None and v > 0:
                    nozzle_targets.append(v)
                    if not second_layer_seen and first_layer_nozzle is None:
                        first_layer_nozzle = v
            if code in {"M140", "M190"}:
                v = _target(upper)
                if v is not None and v > 0:
                    bed_targets.append(v)
                    if not second_layer_seen and first_layer_bed is None:
                        first_layer_bed = v
            if code == "M600":
                has_m600 = True
            if re.fullmatch(r"T\d+", code):
                tools.add(int(code[1:]))
            if code == "G90": absolute_xyz = True
            elif code == "G91": absolute_xyz = False
            elif code == "M82": absolute_e = True
            elif code == "M83": absolute_e = False
            elif code in {"G0", "G1"}:
                vals = {m.group(1).upper(): float(m.group(2)) for m in _AXIS.finditer(upper)}
                old_e = pos["E"]
                for axis in ("X", "Y", "Z"):
                    if axis in vals:
                        pos[axis] = vals[axis] if absolute_xyz else pos[axis] + vals[axis]
                if "E" in vals:
                    pos["E"] = vals["E"] if absolute_e else pos["E"] + vals["E"]
                extruding = "E" in vals and pos["E"] > old_e + 1e-8
                if extruding:
                    # Orca comments can be disabled. A new extrusion Z is a reliable fallback
                    # for layer segmentation because Z-hop travel does not itself extrude.
                    if last_extrusion_z is not None and pos["Z"] > last_extrusion_z + 0.001:
                        if preview_layers[current_preview_layer]:
                            preview_layers.append([])
                            current_preview_layer += 1
                            second_layer_seen = True
                    last_extrusion_z = pos["Z"]
                    for i, axis in enumerate(("X", "Y", "Z")):
                        mins[i] = min(mins[i], pos[axis]); maxs[i] = max(maxs[i], pos[axis])
                    if "X" in vals or "Y" in vals:
                        layer = preview_layers[current_preview_layer]
                        if len(layer) < 50000:
                            layer.append((pos["X"], pos["Y"]))

    if not has_g9111:
        raise GCodeValidationError("Kobra X start G-code marker G9111 missing")
    if has_m600:
        raise GCodeValidationError("M600 detected in generated G-code")
    if any(t > 0 for t in tools):
        raise GCodeValidationError(f"multiple/additional tools detected: {sorted(tools)}")
    nozzle_low, nozzle_high, bed_low, bed_high = _temperature_policy(filament_profile)
    if not nozzle_targets or not bed_targets:
        raise GCodeValidationError("required thermal targets missing from G-code")
    if any(t < nozzle_low or t > nozzle_high for t in nozzle_targets):
        raise GCodeValidationError(f"nozzle target outside profile range {nozzle_low:g}-{nozzle_high:g} C")
    if any(t < bed_low or t > bed_high for t in bed_targets):
        raise GCodeValidationError(f"bed target outside profile-derived range {bed_low:g}-{bed_high:g} C")
    if not all(math.isfinite(v) for v in mins + maxs):
        raise GCodeValidationError("could not derive printed bounds from extrusion moves")
    bounds = Bounds(min_x=mins[0], min_y=mins[1], min_z=mins[2], max_x=maxs[0], max_y=maxs[1], max_z=maxs[2])
    sx, sy, sz = bounds.size
    if sx > 260.01 or sy > 260.01 or sz > 260.01 or mins[0] < -0.01 or mins[1] < -0.01 or mins[2] < -0.01:
        raise GCodeValidationError(f"printed bounds outside 260x260x260: {bounds.model_dump()}")

    printing_nozzle = next((x for x in nozzle_targets if x != first_layer_nozzle), first_layer_nozzle)
    printing_bed = next((x for x in bed_targets if x != first_layer_bed), first_layer_bed)
    if layer_count is None:
        layer_count = len([x for x in preview_layers if x])
    stats = SliceStats(
        estimated_print_time_seconds=estimated,
        filament_length_mm=filament_mm,
        filament_mass_g=filament_g,
        layer_count=layer_count,
        temperatures=TemperatureStats(
            first_layer_nozzle=first_layer_nozzle,
            printing_nozzle=printing_nozzle,
            first_layer_bed=first_layer_bed,
            printing_bed=printing_bed,
            all_nozzle_targets=sorted(set(nozzle_targets)),
            all_bed_targets=sorted(set(bed_targets)),
        ),
        dimensions=bounds,
        gcode_sha256=sha.hexdigest(),
        gcode_bytes=size,
        orca_version=orca_version,
        profile_manifest_sha256=profile_manifest_sha256,
        profile_versions=profile_versions or {},
    )
    return GCodeAnalysis(stats=stats, tools=tools, has_m600=has_m600, has_g9111=has_g9111, preview_layers=[x for x in preview_layers if x])


def write_preview(path: Path, layers: list[list[tuple[float, float]]]) -> None:
    payload = {"layers": [[[round(x, 3), round(y, 3)] for x, y in layer] for layer in layers]}
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
