#!/usr/bin/env sh
set -eu
docker build --platform linux/amd64 -t kobra-x-local-slicer:0.1.8 ./kobra_x_local_slicer
