"""Browser regression checks with fixture APIs; never contacts a printer.
Run after installing playwright and its Chromium browser:
python scripts/verify_ui.py --vendor-dir PATH_TO_BUILT_VENDOR [--browser PATH]
"""

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "kobra_x_local_slicer/app/static"
SLOT = {
    "human_slot": 1,
    "material_type": "PETG",
    "rgb": [160, 160, 160],
    "loaded": True,
}
BASE_JOB = {
    "id": "fixture-job",
    "original_filename": "cube.stl",
    "input_type": "stl",
    "orientation": "original",
    "layer_height": "0.20",
    "nozzle_diameter": "0.4",
    "supports_enabled": False,
    "selected_slot": SLOT,
    "state": "READY_TO_SLICE",
}
STATS = {
    "temperatures": {},
    "dimensions": {
        "min_x": 0,
        "max_x": 20,
        "min_y": 0,
        "max_y": 20,
        "min_z": 0,
        "max_z": 20,
    },
    "estimated_print_time_seconds": 3600,
    "filament_mass_g": 5.5,
    "layer_count": 2,
    "orca_version": "2.4.2",
    "gcode_sha256": "a" * 64,
}
SNAPSHOT = {
    "online": True,
    "stale": False,
    "status": "printing",
    "job": {
        "name": "cube.stl",
        "in_progress": True,
        "progress": 68,
        "elapsed_minutes": 184,
        "remaining_minutes": 88,
    },
    "thermal": {
        "nozzle_current": 235,
        "nozzle_target": 235,
        "bed_current": 80,
        "bed_target": 80,
    },
    "capabilities": {
        "pause_via_ha": True,
        "resume_via_ha": False,
        "cancel_via_ha": True,
    },
}


def run(browser_path, vendor_dir, output_dir):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=browser_path, headless=True
        )
        for width, height, locale in [(390, 844, "pt-BR"), (1440, 1000, "en-US")]:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                locale=locale,
                color_scheme="light",
            )
            page = context.new_page()
            errors, starts, confirmations = [], [], []
            job = dict(BASE_JOB)
            snapshot = json.loads(json.dumps(SNAPSHOT))
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("dialog", lambda dialog: dialog.accept())

            def route(request_route):
                path = urlparse(request_route.request.url).path
                method = request_route.request.method
                if path == "/":
                    return request_route.fulfill(
                        path=str(
                            ROOT / "kobra_x_local_slicer/app/templates/index.html"
                        ),
                        content_type="text/html",
                    )
                if path.startswith("/static/"):
                    file = (
                        vendor_dir / Path(path).name
                        if "/vendor/" in path or "/libs/" in path
                        else STATIC / Path(path).name
                    )
                    return request_route.fulfill(
                        path=str(file),
                        content_type="text/css"
                        if file.suffix == ".css"
                        else "text/javascript",
                    )
                payload = {}
                if path == "/api/health":
                    payload = {"snapshot_available": True}
                elif path == "/api/printer/state":
                    payload = snapshot
                elif path == "/api/config":
                    payload = {
                        "printer_host": "192.168.1.50",
                        "ha_device_id": "fixture",
                    }
                elif path == "/api/jobs/active":
                    payload = []
                elif path == "/api/jobs":
                    job.clear()
                    job.update(BASE_JOB)
                    payload = job
                elif path.endswith("/model"):
                    return request_route.fulfill(
                        path=str(ROOT / "tests/fixtures/20mm_cube.stl"),
                        content_type="application/octet-stream",
                    )
                elif path.endswith("/ace"):
                    payload = {"normalized": [SLOT]}
                elif path.endswith("/slice"):
                    job.update(state="AWAITING_CONFIRMATION", slice_stats=STATS)
                    payload = job
                elif path.endswith("/toolpath"):
                    payload = {
                        "layers": [
                            [
                                [120, 120],
                                [140, 120],
                                [140, 140],
                                [120, 140],
                                [120, 120],
                            ],
                            [[125, 125], [135, 125], [135, 135]],
                        ]
                    }
                elif path.endswith("/layer"):
                    job.update(
                        state="READY_TO_SLICE",
                        layer_height=request_route.request.post_data_json[
                            "layer_height"
                        ],
                    )
                    payload = job
                elif path.endswith("/confirm"):
                    confirmations.append(request_route.request.post_data_json)
                    job["state"] = "PREFLIGHT"
                    payload = job
                elif path.endswith("/print"):
                    starts.append(path)
                    job["state"] = "START_UNKNOWN"
                    payload = job
                elif method == "GET" and path.startswith("/api/jobs/"):
                    payload = job
                return request_route.fulfill(json=payload)

            page.route("**/*", route)
            page.goto("http://kobra.test/")
            page.wait_for_function(
                "document.querySelector('#monitorPercent').textContent === '68%'"
            )
            assert page.locator("[data-step=preview]").is_disabled()

            def check_layout(stage):
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= innerWidth"
                ), stage
                assert page.locator("[data-panel]:visible").count() == 1, stage
                if output_dir:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    page.screenshot(
                        path=str(output_dir / f"{width}-{stage}.png"), full_page=True
                    )

            check_layout("import")
            page.locator("#fileInput").set_input_files(
                str(ROOT / "tests/fixtures/20mm_cube.stl")
            )
            page.wait_for_function("!document.querySelector('#sliceBtn').disabled")
            check_layout("prepare")
            assert page.locator(".slot").get_attribute("aria-pressed") == "true"
            page.locator("#sliceBtn").click()
            page.locator("#resultCard").wait_for(state="visible")
            check_layout("preview")
            assert page.locator("#summaryStats .stat").count() == 2
            page.locator("#layerSlider").fill("1")
            assert page.locator("#layerLabel").inner_text() == "2/2"
            page.locator("#reviewBtn").click()
            check_layout("ready")
            assert page.locator("#printBtn").is_disabled()
            page.locator("#tableClear").check()
            assert page.locator("#printBtn").is_enabled()
            # Editing a prepared option must revoke both the review and consent.
            page.locator("[data-step=prepare]").click()
            page.locator("#layerSelect").select_option("0.16")
            page.wait_for_function(
                "document.querySelector('[data-step=ready]').disabled"
            )
            assert not page.locator("#tableClear").is_checked()
            assert page.locator("#printBtn").is_disabled()
            page.locator("#sliceBtn").click()
            page.locator("#resultCard").wait_for(state="visible")
            page.locator("#reviewBtn").click()
            page.locator("#tableClear").check()
            page.locator("#printBtn").click()
            page.locator("#monitorCard").wait_for(state="visible")
            check_layout("monitor")
            assert confirmations == [{"gcode_sha256": "a" * 64, "table_clear": True}]
            assert len(starts) == 1
            assert page.locator("[data-step=ready]").is_disabled()
            assert (
                "incerto" in page.locator("#monitorHint").inner_text()
                if locale == "pt-BR"
                else "uncertain" in page.locator("#monitorHint").inner_text()
            )
            # A stale snapshot must clear numbers and disable physical controls.
            snapshot["stale"] = True
            page.wait_for_function(
                "document.querySelector('#monitorPercent').textContent === '—'",
                timeout=10000,
            )
            assert page.locator("#monitorNozzle").inner_text() == "—"
            assert page.locator("[data-job-action=pause]").is_disabled()
            page.locator("#themeToggle").click()
            check_layout("dark-monitor")
            # New upload must not expose a previous job's review.
            page.locator("[data-step=import]").click()
            page.locator("#fileInput").set_input_files(
                str(ROOT / "tests/fixtures/20mm_cube.stl")
            )
            page.locator("[data-panel=prepare]").wait_for(state="visible")
            assert page.locator("[data-step=ready]").is_disabled()
            assert not errors, errors
            print(
                f"{width}px {locale}: five stages, consent reset, hash, single start, stale telemetry, dark mode, upload reset passed"
            )
            context.close()
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor-dir", type=Path, required=True)
    parser.add_argument("--browser")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    run(args.browser, args.vendor_dir.resolve(), args.output_dir)
