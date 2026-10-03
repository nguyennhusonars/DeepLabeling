"""Qt runs offscreen unless the caller chose a platform explicitly.

Set before any QApplication exists: pytest-qt creates it lazily, after this
module is imported. Use `QT_QPA_PLATFORM=xcb xvfb-run -a pytest` when a test
needs a real X server.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
