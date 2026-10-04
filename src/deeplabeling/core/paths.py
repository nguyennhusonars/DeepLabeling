"""Which label file belongs to an image (docs/knowledge/label-files.md#one-path-resolver)."""

from __future__ import annotations

import os
from pathlib import Path


def training_label_path(image: Path) -> Path:
    """The label file training reads for `image` (ultralytics' img2label_paths).

    The last /images/ becomes /labels/ and the extension .txt. With no /images/ in
    the path that leaves the .txt beside the image, which is what training reads.
    """
    s = str(image)
    sa, sb = f"{os.sep}images{os.sep}", f"{os.sep}labels{os.sep}"
    return Path(sb.join(s.rsplit(sa, 1)).rsplit(".", 1)[0] + ".txt")


def folder_label_path(image: Path, image_dir: Path, label_dir: Path) -> Path:
    """The label file in an explicitly given label folder, mirroring the image's
    subfolders: flattening them would read and write a shadow file beside the real one."""
    return label_dir / image.relative_to(image_dir).with_suffix(".txt")
