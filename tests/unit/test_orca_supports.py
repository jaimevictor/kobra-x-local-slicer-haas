import json

from app.slicer.orca import OrcaRunner


def test_support_toggle_writes_a_temporary_enabled_process_profile(tmp_path):
    process = tmp_path / "kobra_x_020_standard.resolved.json"
    process.write_text(json.dumps({"enable_support": "0"}), encoding="utf-8")
    runner = OrcaRunner(tmp_path, timeout_seconds=10, gcode_limit_bytes=1_000_000)
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    enabled = runner._process_for_slice(job_dir, True)
    assert enabled.name == "process_with_supports.json"
    assert json.loads(enabled.read_text(encoding="utf-8"))["enable_support"] == "1"
    assert json.loads(process.read_text(encoding="utf-8"))["enable_support"] == "0"
