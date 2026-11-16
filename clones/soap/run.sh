#!/bin/sh
set -eu
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/src:$PWD/../grpc/src${PYTHONPATH:+:$PYTHONPATH}"
"${PYTHON:-python3}" src/contract.py
exec "${PYTHON:-python3}" src/bank_soap.py "$@"
