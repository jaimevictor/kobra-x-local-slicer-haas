from __future__ import annotations

import stat
import math
import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

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


def _normalise_package_path(base: PurePosixPath, target: str) -> str:
    parts: list[str] = [] if target.startswith("/") else list(base.parts)
    for part in PurePosixPath(target).parts:
        if part in {"", ".", "/"}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _source_parent_for_relationships(name: str) -> PurePosixPath | None:
    path = PurePosixPath(name)
    if path.name == ".rels" and path.parent.name == "_rels":
        return PurePosixPath()
    if path.parent.name != "_rels" or not path.name.endswith(".rels"):
        return None
    source_name = path.name[:-5]
    return path.parent.parent / source_name


def _rewrite_relationships(name: str, raw: bytes) -> bytes:
    source = _source_parent_for_relationships(name)
    if source is None:
        return raw
    root = DET.fromstring(raw)
    changed = False
    for element in list(root):
        target = element.attrib.get("Target")
        if _local(element.tag) == "Relationship" and target and _blocked_for_slicing(_normalise_package_path(source.parent, target)):
            root.remove(element)
            changed = True
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) if changed else raw


def _rewrite_content_types(raw: bytes) -> bytes:
    root = DET.fromstring(raw)
    changed = False
    for element in list(root):
        part_name = element.attrib.get("PartName", "").lstrip("/")
        if _local(element.tag) == "Override" and _blocked_for_slicing(part_name):
            root.remove(element)
            changed = True
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) if changed else raw


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
                    if info.filename.lower().endswith(".rels"):
                        data = _rewrite_relationships(info.filename, data)
                    elif info.filename == "[Content_Types].xml":
                        data = _rewrite_content_types(data)
                    zout.writestr(clean, data)
            tmp.replace(dst)
    except zipfile.BadZipFile as exc:
        raise ThreeMFError("invalid 3MF ZIP container") from exc
    return sorted(removed)


_IDENTITY_TRANSFORM = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)


def _attr(element, name: str) -> str | None:
    """Read a normal or namespaced XML attribute by its local name."""
    for key, value in element.attrib.items():
        if _local(key) == name:
            return value
    return None


def _parse_transform(value: str | None) -> tuple[float, ...]:
    if value is None:
        return _IDENTITY_TRANSFORM
    try:
        transform = tuple(float(part) for part in value.split())
    except ValueError as exc:
        raise ThreeMFError("invalid 3MF transform") from exc
    if len(transform) != 12 or not all(math.isfinite(number) for number in transform):
        raise ThreeMFError("invalid 3MF transform")
    return transform


def _compose_transform(first: tuple[float, ...], second: tuple[float, ...]) -> tuple[float, ...]:
    """Return the 3MF transform which applies ``first`` and then ``second``.

    3MF uses a row-vector 3x4 affine matrix: x' = x*m00 + y*m10 + z*m20 + m30.
    """
    linear = tuple(
        sum(first[row * 3 + index] * second[index * 3 + column] for index in range(3))
        for row in range(3)
        for column in range(3)
    )
    translation = tuple(
        sum(first[9 + index] * second[index * 3 + column] for index in range(3)) + second[9 + column]
        for column in range(3)
    )
    return linear + translation


def _apply_transform(point: tuple[float, float, float], transform: tuple[float, ...]) -> tuple[float, float, float]:
    x, y, z = point
    result = (
        x * transform[0] + y * transform[3] + z * transform[6] + transform[9],
        x * transform[1] + y * transform[4] + z * transform[7] + transform[10],
        x * transform[2] + y * transform[5] + z * transform[8] + transform[11],
    )
    if not all(math.isfinite(number) for number in result):
        raise ThreeMFError("3MF mesh contains non-finite coordinates")
    return result


def _normal(a: tuple[float, float, float], b: tuple[float, float, float], c: tuple[float, float, float]) -> tuple[float, float, float]:
    ux, uy, uz = (b[i] - a[i] for i in range(3))
    vx, vy, vz = (c[i] - a[i] for i in range(3))
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (0.0, 0.0, 0.0) if length == 0 else (nx / length, ny / length, nz / length)


def three_mf_to_stl(src: Path, dst: Path, *, max_decompressed: int) -> int:
    """Flatten a validated standard 3MF package into a geometry-only binary STL.

    Some old BambuStudio projects make OrcaSlicer 2.4.2 segfault even after their
    project metadata is stripped. A neutral STL avoids the fragile project loader,
    while keeping the printable build transforms from the selected 3MF plate.
    """
    try:
        with zipfile.ZipFile(src, "r") as zf:
            infos = _safe_members(zf, max_decompressed)
            names = {info.filename for info in infos}
            if MODEL_FILE not in names:
                raise ThreeMFError(f"unsupported 3MF: {MODEL_FILE} missing")
            models: dict[str, tuple[dict[str, object], list[ET.Element]]] = {}

            def model(name: str) -> tuple[dict[str, object], list[ET.Element]]:
                if name in models:
                    return models[name]
                if name not in names:
                    raise ThreeMFError(f"3MF component model missing: {name}")
                try:
                    root = DET.fromstring(_read_limited(zf, name, 64 * 1024 * 1024))
                except Exception as exc:
                    raise ThreeMFError(f"invalid 3MF component model: {name}") from exc
                resources = next((element for element in root if _local(element.tag) == "resources"), None)
                objects: dict[str, object] = {}
                if resources is not None:
                    for element in resources:
                        if _local(element.tag) == "object" and (object_id := _attr(element, "id")):
                            objects[object_id] = element
                build = next((element for element in root if _local(element.tag) == "build"), None)
                items = [element for element in build or () if _local(element.tag) == "item"]
                models[name] = (objects, items)
                return models[name]

            triangles_written = 0
            tmp = dst.with_suffix(dst.suffix + ".tmp")
            with tmp.open("wb+") as out:
                out.write(b"Kobra X Local Slicer 3MF geometry fallback".ljust(80, b"\0"))
                out.write(struct.pack("<I", 0))

                def emit_object(model_name: str, object_id: str, transform: tuple[float, ...], stack: set[tuple[str, str]]) -> None:
                    nonlocal triangles_written
                    key = (model_name, object_id)
                    if key in stack or len(stack) >= 32:
                        raise ThreeMFError("3MF component graph is recursive or too deep")
                    objects, _ = model(model_name)
                    element = objects.get(object_id)
                    if not isinstance(element, ET.Element):
                        raise ThreeMFError(f"3MF object missing: {object_id}")
                    next_stack = stack | {key}
                    mesh = next((child for child in element if _local(child.tag) == "mesh"), None)
                    if mesh is not None:
                        vertices_node = next((child for child in mesh if _local(child.tag) == "vertices"), None)
                        triangles_node = next((child for child in mesh if _local(child.tag) == "triangles"), None)
                        if vertices_node is None or triangles_node is None:
                            raise ThreeMFError("3MF mesh is missing vertices or triangles")
                        vertices: list[tuple[float, float, float]] = []
                        for vertex in vertices_node:
                            if _local(vertex.tag) != "vertex":
                                continue
                            try:
                                point = tuple(float(_attr(vertex, axis) or "") for axis in ("x", "y", "z"))
                            except ValueError as exc:
                                raise ThreeMFError("invalid 3MF vertex") from exc
                            if not all(math.isfinite(number) for number in point):
                                raise ThreeMFError("3MF mesh contains non-finite coordinates")
                            vertices.append(_apply_transform(point, transform))
                        for triangle in triangles_node:
                            if _local(triangle.tag) != "triangle":
                                continue
                            try:
                                indexes = tuple(int(_attr(triangle, name) or "") for name in ("v1", "v2", "v3"))
                                a, b, c = (vertices[index] for index in indexes)
                            except (ValueError, IndexError) as exc:
                                raise ThreeMFError("invalid 3MF triangle index") from exc
                            triangles_written += 1
                            if triangles_written > 2_000_000:
                                raise ThreeMFError("3MF triangle limit exceeded")
                            out.write(struct.pack("<12fH", *_normal(a, b, c), *a, *b, *c, 0))
                        return
                    components = next((child for child in element if _local(child.tag) == "components"), None)
                    if components is None:
                        raise ThreeMFError("3MF object has neither mesh nor components")
                    for component in components:
                        if _local(component.tag) != "component":
                            continue
                        component_id = _attr(component, "objectid")
                        if not component_id:
                            raise ThreeMFError("3MF component missing objectid")
                        path = _attr(component, "path")
                        child_model = _normalise_package_path(PurePosixPath(model_name).parent, path) if path else model_name
                        if child_model not in names:
                            raise ThreeMFError(f"3MF component model missing: {child_model}")
                        emit_object(child_model, component_id, _compose_transform(_parse_transform(_attr(component, "transform")), transform), next_stack)

                root_objects, root_build = model(MODEL_FILE)
                if not root_build:
                    raise ThreeMFError("3MF contains no printable build items")
                for item in root_build:
                    object_id = _attr(item, "objectid")
                    if not object_id or object_id not in root_objects:
                        raise ThreeMFError("3MF build item references an unknown object")
                    if (_attr(item, "printable") or "1") == "0":
                        continue
                    emit_object(MODEL_FILE, object_id, _parse_transform(_attr(item, "transform")), set())
                if triangles_written == 0:
                    raise ThreeMFError("3MF contains no printable triangles")
                out.seek(80)
                out.write(struct.pack("<I", triangles_written))
            tmp.replace(dst)
            return triangles_written
    except zipfile.BadZipFile as exc:
        raise ThreeMFError("invalid 3MF ZIP container") from exc

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
