#!/bin/sh
# Launch DeepLabeling from this checkout without installing it.
ROOT=$(cd "$(dirname "$0")" && pwd)
PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m deeplabeling "$@"
