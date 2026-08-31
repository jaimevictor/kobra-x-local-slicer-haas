# Kobra X Local Slicer

Reference Home Assistant App for **local-only** STL/3MF slicing and LAN printing on an
**Anycubic Kobra X + ACE**. V1 is deliberately narrow: 0.4 mm nozzle, 0.20 mm layer,
PLA, one color, one plate, STL or single-plate 3MF.

## Safety model

The App never auto-starts from a completed slice. A user confirmation is bound to the SHA-256
of the generated G-code. Immediately before printing the App refreshes LAN/MQTT, Home Assistant
cross-check state, ACE material/color, local G-code hash and printer availability. `print/start`
is sent **at most once**. A timeout or disconnect after publish enters `START_UNKNOWN`; the App
queries current printer state/filename and never sends a second start automatically.

The upload URL returned by the printer is treated as untrusted input. It must be exactly
`http://<configured-printer-host>:18910/gcode_upload?s=<non-empty-token>`. Redirects are disabled,
and the token is neither logged nor persisted.

## Build inputs

- Home Assistant OS / Supervisor App, target `amd64`
- OrcaSlicer `2.4.2` pinned exactly
- Ubuntu 24.04 Orca AppImage SHA-256:
  `d12fb8c8eac1aecd2dfb6377acd48f994f8fa439ed5292fa532dd82880f029fd`
- Orca source commit for v2.4.2:
  `8500fcdccaa10b5099ac20d252af3a7c560046f1`
- `anycubic-cloud-api==0.4.26`
- Three.js `0.179.1` copied locally during build; no CDN dependency

Official Anycubic Kobra X machine/process/filament presets are extracted from the pinned Orca
AppImage during the Docker build. `scripts/resolve_profiles.py` recursively resolves `inherits`,
applies ancestors root-first, writes flattened JSON, hashes every source file and records the
Orca source ref/commit in `manifest.json`.

Orca 2.4.2 CLI rejects the official Kobra X cutter-only `retraction_distances_when_cut=["0"]`
value even though the machine has no cutter. The resolver records and removes only that invalid
CLI field from the flattened machine preset; all slicer values retain official provenance.

## Repository layout

```text
repository.yaml
kobra_x_local_slicer/
  config.yaml
  Dockerfile
  run.sh
  requirements*.txt
  scripts/resolve_profiles.py
  rootfs/etc/nginx/http.d/kobra.conf
  app/
    main.py
    api/routes.py
    core/{config,models,security,service,state_machine,storage}.py
    ha/client.py
    kobra/{ace,lan,upload}.py
    slicer/{gcode,geometry,orca,profile_resolver,three_mf}.py
    templates/index.html
    static/{app.js,app.css,vendor/}
profiles/{source,resolved}/
scripts/{golden_slice,build_addon}.sh
 tests/{unit,integration,fixtures}/
docs/{ARCHITECTURE,PROTOCOL,HARDWARE_TESTS,CODEX_HANDOFF}.md
SECURITY.md
NOTICE
LICENSE
.github/workflows/ci.yml
```

## Local tests

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r kobra_x_local_slicer/requirements-dev.txt
pytest -q -m 'not hardware'
```

The real Orca golden slicing test is:

```bash
./scripts/golden_slice.sh
```

It downloads only the exact 2.4.2 AppImage, checks SHA-256, extracts the official Anycubic
profiles, checks expected CLI flags, slices `tests/fixtures/20mm_cube.stl`, and runs the golden
assertions. It does **not** contact a printer.

## Build the App image

```bash
./scripts/build_addon.sh
```

For Supervisor installation, add this repository as a local/custom App repository or have Codex
publish it to the target Git repository, then reload the App store and build/install the
`kobra_x_local_slicer` folder.

## Onboarding

The Ingress panel asks for the Kobra X LAN IP and discovers `anycubic_cloud` devices through the
Home Assistant WebSocket registry API using `SUPERVISOR_TOKEN`. It proposes role mappings, but
requires the safety-critical roles (`online`, `available`, `busy`, `job_in_progress`, `state`,
`filename`) to be mapped before saving. Only entity IDs are persisted in `/data/config.json`.
No Home Assistant long-lived token or Anycubic cloud credential is stored.

## Known verification points

Two details remain intentionally marked for real build/hardware verification rather than being
invented:

1. Auto-orient is intentionally limited to safe manual preview because a supported Orca 2.4.2
   CLI invocation has not been verified in this environment.
2. Upload reproduces the observed BBL-style header names, but identifies this client as
   `KobraXLocalSlicer/0.1.0` instead of inventing an Anycubic Slicer Next version. If the Kobra X
   firmware turns out to require a specific value for an optional header, capture it in a
   hardware test and pin it explicitly.

See `docs/CODEX_HANDOFF.md` and `docs/HARDWARE_TESTS.md` for validation and physical-test sequencing.
