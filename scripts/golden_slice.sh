#!/usr/bin/env sh
set -eu
docker build --platform linux/amd64 -t kobra-x-local-slicer:0.1.7 ./kobra_x_local_slicer
docker run --rm -e ORCA_GOLDEN=1 -e PYTHONPATH=/opt/kobra -v "$(pwd)/tests:/tests:ro" kobra-x-local-slicer:0.1.7 sh -ec 'xvfb-run -a OrcaSlicer --help >/tmp/orca-help; test -s /tmp/orca-help; /opt/venv/bin/python -m pytest -q /tests/integration/test_golden_slice.py'
