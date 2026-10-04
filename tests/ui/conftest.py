import pytest

from fixtures import open_session


@pytest.fixture
def session(qtbot, ds):
    """The edge-case dataset open in a Session, its queue built; closed afterwards."""
    s = open_session(qtbot, ds.yaml)
    yield s
    s.close()
