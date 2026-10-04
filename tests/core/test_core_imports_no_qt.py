"""deeplabeling.core runs headless: importing every module with PySide6 blocked works."""

import os
import pkgutil
import subprocess
import sys
from pathlib import Path

import deeplabeling.core

SRC = Path(__file__).resolve().parents[2] / "src"


def test_the_core_imports_without_qt():
    modules = sorted(m.name for m in pkgutil.iter_modules(deeplabeling.core.__path__,
                                                          "deeplabeling.core."))
    assert "deeplabeling.core.workspace" in modules
    code = "import sys\nsys.modules['PySide6'] = None\n" + "".join(f"import {m}\n" for m in modules)
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            env={**os.environ, "PYTHONPATH": str(SRC)})
    assert result.returncode == 0, result.stderr
