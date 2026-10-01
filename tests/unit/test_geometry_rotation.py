import math
import re
import struct
from pathlib import Path
import pytest
from app.core.models import Orientation
from app.slicer.geometry import inspect_stl, rotate_stl

FIXTURE = Path(__file__).parents[1] / "fixtures/20mm_cube.stl"


def cuboid(path):
    def scale(match):
        x, y, z = map(float, match.groups())
        return f"vertex {x} {y * 2} {z * 3}"

    path.write_text(
        re.sub(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", scale, FIXTURE.read_text()),
        encoding="ascii",
    )


@pytest.mark.parametrize(
    "orientation,expected",
    [
        (Orientation.ROTATE_X_90, (20, 60, 40)),
        (Orientation.ROTATE_Y_90, (60, 40, 20)),
        (Orientation.ROTATE_Z_90, (40, 20, 60)),
    ],
)
def test_baked_rotation_preserves_shape_winding_and_source(
    tmp_path, orientation, expected
):
    source = tmp_path / "source.stl"
    cuboid(source)
    original = source.read_bytes()
    output = tmp_path / "rotated.stl"
    rotate_stl(source, output, orientation)
    bounds = inspect_stl(output).bounds
    assert bounds.size == pytest.approx(expected)
    assert (bounds.min_x + bounds.max_x) / 2 == pytest.approx(130)
    assert (bounds.min_y + bounds.max_y) / 2 == pytest.approx(130)
    assert bounds.min_z == pytest.approx(0)
    assert source.read_bytes() == original
    data = output.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    volume = 0
    for i in range(count):
        values = struct.unpack_from("<12f", data, 84 + i * 50)
        a, b, c = [values[n : n + 3] for n in (3, 6, 9)]
        volume += (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            + a[1] * (b[2] * c[0] - b[0] * c[2])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        ) / 6
        assert math.sqrt(sum(v * v for v in values[:3])) == pytest.approx(1)
    assert volume == pytest.approx(20 * 40 * 60)


def test_binary_rotation_is_always_rebuilt_from_selected_source(tmp_path):
    source = tmp_path / "source.stl"
    cuboid(source)
    binary = tmp_path / "binary.stl"
    rotate_stl(source, binary, Orientation.ROTATE_Z_90)
    output = tmp_path / "output.stl"
    rotate_stl(binary, output, Orientation.ROTATE_Y_90)
    first = output.read_bytes()
    rotate_stl(binary, output, Orientation.ROTATE_Y_90)
    assert output.read_bytes() == first
    assert inspect_stl(output).bounds.size == pytest.approx((60, 20, 40))


def test_rotation_cannot_overwrite_original(tmp_path):
    source = tmp_path / "source.stl"
    cuboid(source)
    original = source.read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        rotate_stl(source, source, Orientation.ROTATE_Y_90)
    assert source.read_bytes() == original
