#!/bin/sh
# Launch DeepLabeling from this checkout without installing it.
# The interpreter: $DEEPLABELING_PYTHON if set, else python3 if it has PySide6, else conda
# base's -- a shell can have another conda env active (docs/knowledge/environment.md#python).
ROOT=$(cd "$(dirname "$0")" && pwd)
PY=${DEEPLABELING_PYTHON:-python3}
if ! "$PY" -c "import PySide6" 2>/dev/null; then
    BASE=$(conda info --base 2>/dev/null)
    if [ -n "$BASE" ] && "$BASE/bin/python3" -c "import PySide6" 2>/dev/null; then
        PY="$BASE/bin/python3"
    else
        echo "DeepLabeling needs a Python with PySide6: $PY has none, and no conda base has it." >&2
        echo "Set DEEPLABELING_PYTHON to one that does, or run 'conda activate base' first." >&2
        exit 1
    fi
fi
PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" exec "$PY" -m deeplabeling "$@"
