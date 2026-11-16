#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
./generate.sh
export PYTHONPATH="$PWD/generated:$PWD/src:$PWD/tests${PYTHONPATH:+:$PYTHONPATH}"
exec "${PYTHON:-python3}" client/example.py "$@"
