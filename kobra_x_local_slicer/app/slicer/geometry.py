from __future__ import annotations
import struct
import re
import math
from dataclasses import dataclass
from pathlib import Path
from app.core.models import Bounds, Orientation


@dataclass
class MeshInspection:
    triangles: int
    volume_mm3: float
    bounds: Bounds


def inspect_stl(path: Path) -> MeshInspection:
    data = path.read_bytes()
    if data.lstrip().lower().startswith(b"solid"):
        vertices = []
        for x, y, z in re.findall(
            r"\bvertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)",
            data.decode("ascii", "strict"),
            re.I,
        ):
            vertices.append((float(x), float(y), float(z)))
        if not vertices or len(vertices) % 3:
            raise ValueError("invalid ASCII STL")
        xs, ys, zs = zip(*vertices)
        return MeshInspection(
            len(vertices) // 3,
            0.0,
            Bounds(
                min_x=min(xs),
                min_y=min(ys),
                min_z=min(zs),
                max_x=max(xs),
                max_y=max(ys),
                max_z=max(zs),
            ),
        )
    if len(data) < 84:
        raise ValueError("invalid STL")
    count = struct.unpack_from("<I", data, 80)[0]
    if 84 + count * 50 != len(data):
        raise ValueError("only binary STL is supported")
    xs = []
    ys = []
    zs = []
    for n in range(count):
        values = struct.unpack_from("<12f", data, 84 + n * 50)
        for x, y, z in zip(values[3::3], values[4::3], values[5::3]):
            xs.append(x)
            ys.append(y)
            zs.append(z)
    if not xs:
        raise ValueError("STL contains no triangles")
    return MeshInspection(
        count,
        0.0,
        Bounds(
            min_x=min(xs),
            min_y=min(ys),
            min_z=min(zs),
            max_x=max(xs),
            max_y=max(ys),
            max_z=max(zs),
        ),
    )


def rotate_stl(src: Path, dst: Path, orientation: Orientation) -> None:
    """Bake a right-angle rotation and bed placement without Orca CLI transforms.

    Preserve the source, facet order and winding. Coordinates use the same
    right-handed rotation and 260 mm bed centering as the Three.js preview.
    """
    rotations = {
        Orientation.ROTATE_X_90: lambda x, y, z: (x, -z, y),
        Orientation.ROTATE_Y_90: lambda x, y, z: (z, y, -x),
        Orientation.ROTATE_Z_90: lambda x, y, z: (-y, x, z),
    }
    if orientation not in rotations:
        raise ValueError("unsupported baked STL rotation")
    if src.resolve() == dst.resolve():
        raise ValueError("rotated STL must not overwrite the source")
    rotate = rotations[orientation]
    data = src.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0] if len(data) >= 84 else 0
    binary = len(data) == 84 + count * 50
    text = None if binary else data.decode("ascii", "strict")
    pattern = r"\bvertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)"

    def vertices():
        if binary:
            for index in range(count):
                values = struct.unpack_from("<12f", data, 84 + index * 50)
                for offset in (3, 6, 9):
                    yield rotate(*values[offset : offset + 3])
        else:
            for match in re.finditer(pattern, text, re.I):
                yield rotate(*(float(number) for number in match.groups()))

    minimum = [math.inf] * 3
    maximum = [-math.inf] * 3
    vertex_count = 0
    for point in vertices():
        if not all(math.isfinite(value) for value in point):
            raise ValueError("STL contains non-finite coordinates")
        vertex_count += 1
        for axis, value in enumerate(point):
            minimum[axis] = min(minimum[axis], value)
            maximum[axis] = max(maximum[axis], value)
    if not vertex_count or vertex_count % 3:
        raise ValueError("invalid STL triangle data")
    shift = (
        130 - (minimum[0] + maximum[0]) / 2,
        130 - (minimum[1] + maximum[1]) / 2,
        -minimum[2],
    )
    temporary = dst.with_suffix(dst.suffix + ".tmp")
    try:
        with temporary.open("wb") as out:
            out.write(b"Kobra X baked orientation".ljust(80, b"\0"))
            out.write(struct.pack("<I", vertex_count // 3))
            iterator = iter(vertices())
            for _ in range(vertex_count // 3):
                a, b, c = [
                    tuple(
                        value + shift[axis] for axis, value in enumerate(next(iterator))
                    )
                    for _ in range(3)
                ]
                u = tuple(b[index] - a[index] for index in range(3))
                v = tuple(c[index] - a[index] for index in range(3))
                normal = (
                    u[1] * v[2] - u[2] * v[1],
                    u[2] * v[0] - u[0] * v[2],
                    u[0] * v[1] - u[1] * v[0],
                )
                length = math.sqrt(sum(value * value for value in normal))
                normal = (
                    tuple(value / length for value in normal) if length else (0, 0, 0)
                )
                out.write(struct.pack("<12fH", *normal, *a, *b, *c, 0))
        temporary.replace(dst)
    finally:
        temporary.unlink(missing_ok=True)
