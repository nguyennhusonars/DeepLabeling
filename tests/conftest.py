"""Qt runs offscreen, and no test can touch the real app state.

QT_QPA_PLATFORM is set before any QApplication exists: pytest-qt creates it
lazily, after this module is imported. Use `QT_QPA_PLATFORM=xcb xvfb-run -a
pytest` when a test needs a real X server.
"""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REAL_STATE = Path(__file__).resolve().parents[1] / ".deeplabeling"


def _stamp(folder: Path):
    if not folder.exists():
        return None
    return sorted((str(p.relative_to(folder)), p.stat().st_mtime_ns, p.stat().st_size)
                  for p in folder.rglob("*") if p.is_file())


@pytest.fixture(scope="session", autouse=True)
def _real_state_untouched():
    """Fail the run if any test wrote to the real app state (CLAUDE.md landmine 10)."""
    before = _stamp(REAL_STATE)
    yield
    assert _stamp(REAL_STATE) == before, f"a test changed {REAL_STATE}"


@pytest.fixture(autouse=True)
def state_dir(tmp_path_factory, monkeypatch):
    """Every test gets its own empty app-state folder."""
    folder = tmp_path_factory.mktemp("state")
    monkeypatch.setenv("DEEPLABELING_STATE_DIR", str(folder))
    return folder


@pytest.fixture
def ds(tmp_path):
    """The edge-case dataset (tests/fixtures.py), freshly built for one test."""
    from fixtures import build_dataset

    return build_dataset(tmp_path / "ds")
