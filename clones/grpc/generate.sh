#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p generated
"${PYTHON:-python3}" -m grpc_tools.protoc -I proto --python_out=generated --grpc_python_out=generated proto/bank.proto
