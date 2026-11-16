#!/bin/sh
set -eu
cd "$(dirname "$0")"
./generate.sh
export PYTHONPATH="$PWD/generated:$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
exec "${PYTHON:-python3}" src/server.py "$@"
