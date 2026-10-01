# Changelog

## 2.1.1

- Prefer live Home Assistant IP state over registry metadata during printer discovery.
- Replace stale saved addresses on discovery and preserve unsaved connection edits during health polling.
- Show printer selection, saving, success, and failure feedback; clear the selection list after saving.
- Validate required entity mappings when saving, allowing temporarily unavailable telemetry. Print preflight still requires available telemetry.
- Explain that uploads require STL or 3MF models and reject pre-sliced G-code before creating a job.
