from __future__ import annotations

import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from defusedxml import ElementTree as DET

MODEL_FILE = "3D/3dmodel.model"
MODEL_SETTINGS = "Metadata/model_settings.config"
PROJECT_SETTINGS = "Metadata/project_settings.config"


class ThreeMFError(ValueError):
    pass


@dataclass(slots=True)
class ThreeMFInspection:
    plate_count: int
    plate_ids: list[int]
    multicolor: bool
    reasons: list[str]
    decompressed_bytes: int


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _safe_members(zf: zipfile.ZipFile, max_decompressed: int) -> list[zipfile.ZipInfo]:
    infos = zf.infolist()
    total = 0
    for info in infos:
        p = PurePosixPath(info.filename)
        if p.is_absolute() or ".." in p.parts or "\\" in info.filename:
            raise ThreeMFError("3MF contains path traversal")
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            raise ThreeMFError("3MF contains symlink")
        if info.file_size < 0 or info.compress_size < 0:
            raise ThreeMFError("invalid ZIP member sizes")
        total += info.file_size
        if total > max_decompressed:
            raise ThreeMFError("3MF decompressed-size limit exceeded")
        # Per-member ratio catches tiny compressed bombs before extraction.
        if info.file_size > 16 * 1024 * 1024 and info.compress_size > 0:
            if info.file_size / info.compress_size > 200:
                raise ThreeMFError("suspicious ZIP compression ratio")
    return infos


def _read_limited(zf: zipfile.ZipFile, name: str, limit: int = 16 * 1024 * 1024) -> bytes:
    try:
        info = zf.getinfo(name)
    except KeyError as exc:
        raise ThreeMFError(f"required 3MF member missing: {name}") from exc
    if info.file_size > limit:
        raise ThreeMFError(f"3MF metadata member too large: {name}")
    with zf.open(info, "r") as fh:
        data = fh.read(limit + 1)
    if len(data) > limit:
        raise ThreeMFError(f"3MF metadata member too large: {name}")
    return data


def _metadata_value(element, key: str) -> str | None:
    for child in element:
        if _local(child.tag) == "metadata" and child.attrib.get("key") == key:
            return child.attrib.get("value")
    return None


def _plate_ids_from_model_settings(raw: bytes) -> tuple[list[int], bool]:
    root = DET.fromstring(raw)
    plate_ids: list[int] = []
    saw_plate = False
    for elem in root.iter():
        if _local(elem.tag) != "plate":
            continue
        saw_plate = True
        has_instance = any(_local(x.tag) == "model_instance" for x in elem)
        if not has_instance:
            continue
        value = _metadata_value(elem, "plater_id")
        if value is None:
            raise ThreeMFError("Orca/Bambu plate metadata missing plater_id; refusing ambiguous project")
        try:
            plate_id = int(value)
        except ValueError as exc:
            raise ThreeMFError("invalid plater_id in 3MF") from exc
        if plate_id < 1:
            raise ThreeMFError("invalid plater_id in 3MF")
        plate_ids.append(plate_id)
    if saw_plate and not plate_ids:
        raise ThreeMFError("plate metadata exists but no printable plate assignment was found")
    return sorted(set(plate_ids)), saw_plate


def _standard_build_is_single_plate(raw: bytes) -> bool:
    root = DET.fromstring(raw)
    builds = [x for x in root if _local(x.tag) == "build"]
    if len(builds) != 1:
        return False
    return any(_local(x.tag) == "item" for x in builds[0])


def _multicolor_reasons(model_raw: bytes, model_settings_raw: bytes | None, zf: zipfile.ZipFile) -> list[str]:
    reasons: list[str] = []
    model = DET.fromstring(model_raw)

    material_refs: set[tuple[str, str]] = set()
    for elem in model.iter():
        if _local(elem.tag) == "triangle":
            for key, value in elem.attrib.items():
                lname = _local(key)
                if lname in {"paint_color", "mmu_segmentation"} and value not in {"", "0", "00"}:
                    reasons.append("per-face filament painting present")
                    break
            pid = elem.attrib.get("pid")
            pindex = elem.attrib.get("p1") or elem.attrib.get("pindex")
            if pid is not None and pindex is not None:
                material_refs.add((pid, pindex))
    if len(material_refs) > 1:
        reasons.append("multiple 3MF material/color property assignments are used")

    if model_settings_raw:
        settings = DET.fromstring(model_settings_raw)
        extruders: set[int] = set()
        for elem in settings.iter():
            if _local(elem.tag) != "metadata" or elem.attrib.get("key") != "extruder":
                continue
            value = elem.attrib.get("value")
            if value is None:
                continue
            try:
                extruder = int(value)
            except ValueError:
                reasons.append("unparseable extruder assignment")
                continue
            # Orca convention: 0 means inherit/default, 1 means first filament.
            if extruder > 1:
                extruders.add(extruder)
        if extruders:
            reasons.append(f"project assigns objects/parts to additional extruders: {sorted(extruders)}")

    for name in zf.namelist():
        lname = name.lower()
        if lname.endswith("custom_gcode_per_layer.xml") or lname.endswith("layer_config_ranges.xml"):
            raw = _read_limited(zf, name, 4 * 1024 * 1024).decode("utf-8", "ignore").upper()
            if "M600" in raw or any(f">T{i}<" in raw or f" T{i}" in raw for i in range(1, 16)):
                reasons.append("custom per-layer filament/tool change data present")
                break

    return sorted(set(reasons))



BLOCKED_SLICING_METADATA = {
    "metadata/project_settings.config",
    "metadata/print_profile.config",
    "metadata/model_settings.config",
    "metadata/_rels/model_settings.config.rels",
    "metadata/slice_info.config",
    "metadata/filament_sequence.json",
    "metadata/layer_heights_profile.txt",
    "metadata/layer_config_ranges.xml",
    "metadata/custom_gcode_per_layer.xml",
    "metadata/brim_ear_points.txt",
    "metadata/cut_information.xml",
    "metadata/slic3r_pe.config",
    "metadata/slic3r_pe_model.config",
}
BLOCKED_SLICING_PREFIXES = (
    "metadata/print_setting_",
    "metadata/process_settings_",
    "metadata/filament_settings_",
    "metadata/machine_settings_",
)


def _blocked_for_slicing(name: str) -> bool:
    lowered = name.lower()
    return lowered in BLOCKED_SLICING_METADATA or any(lowered.startswith(p) for p in BLOCKED_SLICING_PREFIXES)


def sanitize_3mf_for_slicing(src: Path, dst: Path, *, max_decompressed: int) -> list[str]:
    """Create a geometry-preserving copy that cannot import project/preset slicing settings.

    Plate/color validation must run on the original *before* this function. We then remove
    Orca/Bambu metadata files that can inject printer/process/filament or per-object slicing
    overrides. Core 3MF geometry, relationships, component models and texture resources remain.
    """
    removed: list[str] = []
    try:
        with zipfile.ZipFile(src, "r") as zin:
            infos = _safe_members(zin, max_decompressed)
            if MODEL_FILE not in {i.filename for i in infos}:
                raise ThreeMFError(f"unsupported 3MF: {MODEL_FILE} missing")
            tmp = dst.with_suffix(dst.suffix + ".tmp")
            with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zout:
                zout.comment = zin.comment
                for info in infos:
                    if info.is_dir():
                        continue
                    if _blocked_for_slicing(info.filename):
                        removed.append(info.filename)
                        continue
                    # Recreate a plain regular-file ZipInfo instead of copying external attrs.
                    clean = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                    clean.compress_type = zipfile.ZIP_DEFLATED
                    clean.external_attr = 0o600 << 16
                    clean.create_system = 3
                    with zin.open(info, "r") as source:
                        data = source.read(info.file_size + 1)
                    if len(data) != info.file_size:
                        raise ThreeMFError(f"3MF member size changed while reading: {info.filename}")
                    zout.writestr(clean, data)
            tmp.replace(dst)
    except zipfile.BadZipFile as exc:
        raise ThreeMFError("invalid 3MF ZIP container") from exc
    return sorted(removed)

def inspect_3mf(path: Path, *, max_decompressed: int) -> ThreeMFInspection:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            infos = _safe_members(zf, max_decompressed)
            names = {i.filename for i in infos}
            if MODEL_FILE not in names:
                raise ThreeMFError(f"unsupported 3MF: {MODEL_FILE} missing")
            model_raw = _read_limited(zf, MODEL_FILE, 64 * 1024 * 1024)
            model_settings_raw = _read_limited(zf, MODEL_SETTINGS) if MODEL_SETTINGS in names else None

            if model_settings_raw is not None:
                plate_ids, saw_plate = _plate_ids_from_model_settings(model_settings_raw)
                if not saw_plate:
                    if not _standard_build_is_single_plate(model_raw):
                        raise ThreeMFError("cannot determine 3MF plate count safely")
                    plate_ids = [1]
            else:
                if not _standard_build_is_single_plate(model_raw):
                    raise ThreeMFError("cannot determine 3MF plate count safely")
                plate_ids = [1]

            if len(plate_ids) > 1:
                raise ThreeMFError(
                    "Este projeto possui mais de uma placa. Deixe apenas uma placa no arquivo e envie novamente."
                )
            if len(plate_ids) != 1:
                raise ThreeMFError("cannot determine 3MF plate count safely")

            reasons = _multicolor_reasons(model_raw, model_settings_raw, zf)
            if reasons:
                raise ThreeMFError("3MF multicolor/multi-filament is not supported in V1: " + "; ".join(reasons))

            return ThreeMFInspection(
                plate_count=1,
                plate_ids=plate_ids,
                multicolor=False,
                reasons=[],
                decompressed_bytes=sum(i.file_size for i in infos),
            )
    except zipfile.BadZipFile as exc:
        raise ThreeMFError("invalid 3MF ZIP container") from exc
