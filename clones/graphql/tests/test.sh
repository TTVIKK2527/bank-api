#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src:$PWD/../grpc/src:$PWD/../grpc/tests${PYTHONPATH:+:$PYTHONPATH}"
exec "${PYTHON:-python3}" -m unittest discover -s tests -v
