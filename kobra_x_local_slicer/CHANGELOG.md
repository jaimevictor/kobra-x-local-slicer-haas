# Changelog

## 2.2.0

- Introduce a mobile-first five-stage print workflow with purple accents and light/dark themes.
- Keep technical settings collapsed; make ACE slot selection keyboard accessible.
- Improve 3D camera orientation and automatically fit the layer toolpath preview.
- Add validation summary and live Home Assistant progress, time and temperature monitoring.
- Clear stale telemetry, disable unavailable controls, and preserve hash-bound consent and at-most-once print start.
- Reset review and table-clear consent after model or preparation changes; allow reimporting the same file.
- Add fixture-only mobile/desktop browser regression checks without contacting a printer.

## 2.1.1

- Prefer live Home Assistant IP state over registry metadata during printer discovery.
- Replace stale saved addresses on discovery and preserve unsaved connection edits during health polling.
- Show printer selection, saving, success, and failure feedback; clear the selection list after saving.
- Validate required entity mappings when saving, allowing temporarily unavailable telemetry. Print preflight still requires available telemetry.
- Explain that uploads require STL or 3MF models and reject pre-sliced G-code before creating a job.
