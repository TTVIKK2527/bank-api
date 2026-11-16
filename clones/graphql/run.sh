#!/bin/sh
set -eu
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/src:$PWD/../grpc/src${PYTHONPATH:+:$PYTHONPATH}"
exec "${PYTHON:-python3}" src/bank_graphql.py "$@"
