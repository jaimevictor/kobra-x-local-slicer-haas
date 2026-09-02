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


def test_slice_removes_previous_gcode_from_the_same_job_directory(tmp_path):
    runner = OrcaRunner(tmp_path, timeout_seconds=10, gcode_limit_bytes=1_000_000)
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    old_output = job_dir / "output.gcode"
    old_plate = job_dir / "plate_1.gcode"
    old_output.write_text("old", encoding="utf-8")
    old_plate.write_text("old", encoding="utf-8")

    # The cleanup is deliberately placed before process launch so a re-slice
    # cannot count stale output beside Orca's new plate_1.gcode.
    runner._clear_previous_gcode(job_dir)
    assert not old_output.exists()
    assert not old_plate.exists()


def test_orca_command_can_include_a_headless_wrapper(monkeypatch, tmp_path):
    monkeypatch.setenv("ORCA_APP", "/usr/bin/xvfb-run -a /opt/orca/AppRun")
    runner = OrcaRunner(tmp_path, timeout_seconds=10, gcode_limit_bytes=1_000_000)
    assert runner.app == ("/usr/bin/xvfb-run", "-a", "/opt/orca/AppRun")
