"""Qt runs offscreen unless the caller chose a platform explicitly.

Set before any QApplication exists: pytest-qt creates it lazily, after this
module is imported. Use `QT_QPA_PLATFORM=xcb xvfb-run -a pytest` when a test
needs a real X server.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def ds(tmp_path):
    """The edge-case dataset (tests/fixtures.py), freshly built for one test."""
    from fixtures import build_dataset

    return build_dataset(tmp_path / "ds")
