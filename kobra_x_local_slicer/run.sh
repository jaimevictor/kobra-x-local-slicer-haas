#!/usr/bin/env sh
set -eu
mkdir -p /data/jobs
nginx
exec /opt/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8098 --proxy-headers
