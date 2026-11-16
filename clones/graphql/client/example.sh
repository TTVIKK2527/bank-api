#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src:$PWD/tests:$PWD/../grpc/src:$PWD/../grpc/tests${PYTHONPATH:+:$PYTHONPATH}"
exec "${PYTHON:-python3}" client/example.py "$@"
