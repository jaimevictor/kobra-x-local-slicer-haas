# Codex / VS Code handoff

Use this order so failures are attributable.

## 1. Static and unit verification

```bash
cd kobra-x-local-slicer
python3 -m venv .venv
. .venv/bin/activate
pip install -r kobra_x_local_slicer/requirements-dev.txt
python -m compileall -q kobra_x_local_slicer/app
pytest -q -m 'not hardware' --ignore=tests/integration/test_golden_slice.py
```

## 2. Golden Orca validation

```bash
./scripts/golden_slice.sh
```

Confirm the script sees all CLI flags used by `OrcaRunner`, produces exactly one G-code and passes
`tests/integration/test_golden_slice.py`. If Orca's exact `--export-3mf` syntax differs for the
auto-orient preview, update only `export_oriented_3mf()` and add an integration assertion; do not
weaken slice output validation.

## 3. Image build

```bash
./scripts/build_addon.sh
```

Inspect the Docker log for:

- exact Orca AppImage SHA success
- dynamic discovery of the `resources/profiles/Anycubic` directory
- resolver output `manifest.json`
- local Three.js files copied into `app/static/vendor`

Then inspect the built image:

```bash
docker run --rm --entrypoint sh kobra-x-local-slicer:0.1.1 -c \
 'cat /opt/kobra/profiles/resolved/manifest.json && /opt/venv/bin/python -m compileall -q /opt/kobra/app'
```

## 4. Home Assistant App install

Add/publish the repository, reload the App store, install and build on the amd64 HAOS host. Verify:

- no privileged/full-access/host-network request
- panel loads only through Ingress
- direct access to port 8099 from another LAN host is denied
- `/data/config.json` stores only printer host, selected HA device ID and entity IDs

Run onboarding and map all required HA roles. Do not hardcode entity IDs in source.

## 5. LAN query validation

With no print command:

- confirm handshake and local MQTT connect
- compare raw/parsed/normalized ACE output
- verify material/color for all visible slots
- verify HA cross-check versus MQTT/LAN
- verify unchanged sticky error states do not block but new/current faults do

## 6. Slicing workflow

Test STL and a known single-plate 3MF. Also test negative fixtures:

- two plates -> exact required message
- ambiguous plate count -> fail closed
- painted/multi-extruder project -> reject
- foreign embedded project profiles -> sanitizer removes them
- G-code M600/T1/250 °C -> validator rejects

Verify profile hashes and G-code SHA are visible in the UI.

## 7. Upload-only hardware validation

Run the upload acceptance test with a safe G-code. Confirm no HTTP redirect and no token in logs.
If firmware rejects one of the optional BBL-style headers, capture the exact requirement and update
`KobraUploadClient` with a test. Do not pretend to be a different client version without evidence.

## 8. Physical print/start last

Follow `docs/HARDWARE_TESTS.md`. Test normal ACK, forced timeout after publish, and reconciliation.
The invariant to preserve is: `start_calls == 1` for every transaction, including timeouts.
