# Changelog

## 2.2.2

- Fix Orca 2.4.2 Linux CLI segmentation faults when rotating models along X, Y or Z.
- Bake the selected rotation and bed placement into a separate binary STL before slicing; do not pass Orca CLI rotation flags.
- Preserve source geometry, facet winding and the chosen orientation; re-slicing always starts from the original geometry.
- Add asymmetric-geometry checks and real Orca PLA/PETG rotation regression tests.

## 2.2.1

- Stop treating Home Assistant device configuration URLs and registry connections as printer IPs; these can refer to HAOS or outdated DHCP addresses.
- Prefer explicit printer IP sensors over incidental attributes. Ignore restored, disabled and unavailable sources; conflicting addresses require manual entry.
- Show the source entity for a discovered address and request the printer-panel IP when no reliable address is published.
- Preserve manual IP corrections during discovery for the same printer; explain that saved addresses can become outdated.
- Add discovery and browser regression checks for stale registry addresses and manual correction persistence.

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
