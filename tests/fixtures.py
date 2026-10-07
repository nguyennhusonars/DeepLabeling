"""A generated dataset holding every edge case, and the change-detection helpers.

Rewritten from the legacy suite's fixtures (legacy/ is never imported). Nothing
binary is committed: `build_dataset` writes the whole tree in well under a second.
"""

from __future__ import annotations

import hashlib
import io
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import cv2
import numpy as np
import yaml
from PIL import Image

from deeplabeling.core.queue import Condition

CAMA_0001 = "0 0.500000 0.500000 0.200000 0.300000\n1 0.250000 0.250000 0.100000 0.100000\n"
CAMB_0001 = "2 0.750000 0.750000 0.150000 0.150000\n"
#: Two polygons: 4 points and 5 points.
POLY1 = (
    "0 0.10 0.10 0.20 0.10 0.20 0.20 0.10 0.20\n"
    "1 0.30 0.30 0.45 0.30 0.45 0.50 0.38 0.55 0.30 0.50\n"
)
#: A box line, then a polygon line.
MIXED = "0 0.50 0.50 0.20 0.20\n1 0.60 0.60 0.70 0.60 0.70 0.70 0.60 0.70\n"
CRLF = "0 0.500000 0.500000 0.200000 0.200000\r\n1 0.300000 0.300000 0.100000 0.100000\r\n"
#: Two valid boxes beside an image that cannot be decoded.
BAD_CORRUPT = "0 0.400000 0.400000 0.200000 0.200000\n1 0.600000 0.600000 0.100000 0.100000\n"
#: Every malformed shape the parser must survive. Lines 5, 6 and 10 (0-based) are
#: three identical class-0 boxes; the last line has no newline.
GAUNTLET = (
    "1 0.5 0.5 0.2 0.2\n"           # 0 valid
    "99 0.5 0.5 0.1 0.1\n"          # 1 class id past the names
    "-1 0.5 0.5 0.1 0.1\n"          # 2 negative class id
    "0 1.4 0.5 0.2 0.2\n"           # 3 cx > 1
    "0 0.5 0.5\n"                   # 4 too few fields
    "0 0.5 0.5 0.2 0.2 0.95\n"      # 5 an extra (confidence) column
    "0 0.5 0.5 0.2 0.2\r\n"         # 6 CRLF
    "abc 0.5 0.5 0.2 0.2\n"         # 7 non-numeric class
    "\n"                            # 8 blank
    "   \n"                         # 9 whitespace only
    "0 0.5 0.5 0.2 0.2"             # 10 no final newline
)
CLASS_NAMES = ["person", "car", "bus_m", "bus_l"]
GROUPS = {"person": ["person"], "car": ["car"], "bus": ["bus_m", "bus_l"]}


def make_image(path: Path, w: int = 64, h: int = 48) -> None:
    """A small image with two coloured rectangles; the format follows the suffix."""
    path.parent.mkdir(parents=True, exist_ok=True)
    a = np.full((h, w, 3), 40, np.uint8)
    cv2.rectangle(a, (w // 8, h // 8), (w // 2, h // 2), (0, 180, 0), -1)
    cv2.rectangle(a, (w // 2, h // 2), (w - w // 8, h - h // 8), (0, 0, 180), -1)
    ok, buf = cv2.imencode(".png" if path.suffix.lower() == ".png" else ".jpg", a)
    assert ok
    path.write_bytes(buf.tobytes())   # imwrite cannot take a non-ASCII path


def make_exif_rotated_image(path: Path, w: int = 64, h: int = 48) -> None:
    """A JPEG stored w x h with EXIF orientation 6: displayed h x w."""
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (w, h), (90, 90, 90))
    exif = im.getexif()
    exif[274] = 6
    buf = io.BytesIO()
    im.save(buf, format="JPEG", exif=exif)
    path.write_bytes(buf.getvalue())


def _txt(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def read_exact(path: Path) -> str:
    """The file's text with every line ending as it is on disk.

    `Path.read_text()` turns CRLF into LF, which would let a byte-identity
    assertion pass against a file that was in fact rewritten."""
    return Path(path).read_bytes().decode("utf-8")


@dataclass
class DatasetFixture:
    root: Path

    @property
    def yaml(self) -> Path:
        return self.root / "data.yaml"

    def img(self, rel: str) -> Path:
        """`img("camA/0001.jpg")` -> `<root>/camA/images/0001.jpg`."""
        folder, name = rel.split("/", 1)
        return self.root / folder / "images" / name

    def lbl(self, rel: str) -> Path:
        """`lbl("camA/0001")` -> `<root>/camA/labels/0001.txt`."""
        folder, name = rel.split("/", 1)
        return self.root / folder / "labels" / f"{name}.txt"

    def snapshot(self) -> dict[str, str]:
        return snapshot(self.root)


def build_dataset(root: Path) -> DatasetFixture:
    """The edge-case dataset. Train: camA, camB, weird. Val: bad, crlf, seg."""
    root.mkdir(parents=True, exist_ok=True)
    # camA: ordinary, negative, unlabelled, uppercase, and a subfolder
    make_image(root / "camA/images/0001.jpg")
    _txt(root / "camA/labels/0001.txt", CAMA_0001)
    make_image(root / "camA/images/0002.jpg")
    _txt(root / "camA/labels/0002.txt", "")
    make_image(root / "camA/images/0003.jpg")
    make_image(root / "camA/images/0004.JPG")
    make_image(root / "camA/images/sub/0005.jpg")
    _txt(root / "camA/labels/sub/0005.txt", CAMB_0001)
    # camB: a stem camA also has, EXIF rotation, and two images sharing one label
    make_image(root / "camB/images/0001.jpg")
    _txt(root / "camB/labels/0001.txt", CAMB_0001)
    make_exif_rotated_image(root / "camB/images/rot.jpg")
    _txt(root / "camB/labels/rot.txt", CAMB_0001)
    make_image(root / "camB/images/twin.jpg")
    make_image(root / "camB/images/twin.png")
    _txt(root / "camB/labels/twin.txt", "0 0.500000 0.500000 0.100000 0.100000\n")
    # weird: unicode and a space in the stem
    make_image(root / "weird/images/имя пробел.jpg")
    _txt(root / "weird/labels/имя пробел.txt", "0 0.500000 0.500000 0.100000 0.100000\n")
    # val
    (root / "bad/images").mkdir(parents=True, exist_ok=True)
    (root / "bad/images/corrupt.jpg").write_bytes(b"this is not an image")
    _txt(root / "bad/labels/corrupt.txt", BAD_CORRUPT)
    make_image(root / "bad/images/ok.jpg")
    _txt(root / "bad/labels/ok.txt", GAUNTLET)
    make_image(root / "crlf/images/c.jpg")
    _txt(root / "crlf/labels/c.txt", CRLF)
    make_image(root / "seg/images/poly1.jpg")
    _txt(root / "seg/labels/poly1.txt", POLY1)
    make_image(root / "seg/images/mixed.jpg")
    _txt(root / "seg/labels/mixed.txt", MIXED)
    # not listed in the yaml
    make_image(root / "frames/x0001.jpg")                   # no 'images' in its path
    _txt(root / "labels_only/labels/ghost.txt", "0 0.5 0.5 0.1 0.1\n")
    (root / "data.yaml").write_text(yaml.safe_dump({
        "path": str(root),
        "train": ["camA/images", "camB/images", "weird/images"],
        "val": ["bad/images", "crlf/images", "seg/images"],
        "names": CLASS_NAMES,
        "groups": GROUPS,
    }, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return DatasetFixture(root)


SRC = Path(__file__).resolve().parents[1] / "src"

_HOLD = """
import sys, time
sys.path.insert(0, {src!r})
from deeplabeling.core.state import DatasetLock
lock = DatasetLock({directory!r})
lock.acquire()
print("held", flush=True)
time.sleep(60)
"""


@contextmanager
def held_elsewhere(directory: Path):
    """Another live process holds the dataset lock in `directory`; yields its pid."""
    child = subprocess.Popen([sys.executable, "-c", _HOLD.format(src=str(SRC), directory=str(directory))],
                             stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "held"
        yield child.pid
    finally:
        child.kill()
        child.wait()
        child.stdout.close()


def snapshot(root: Path) -> dict[str, str]:
    """Every .txt under `root` -> the sha256 of its bytes. A missing file is absent."""
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).rglob("*.txt"))}


def diff_snapshots(before: dict[str, str], after: dict[str, str]) -> dict[str, str]:
    """{relative path: 'added' | 'removed' | 'modified'} for everything that moved."""
    changed = {}
    for k in before.keys() | after.keys():
        if k not in after:
            changed[k] = "removed"
        elif k not in before:
            changed[k] = "added"
        elif before[k] != after[k]:
            changed[k] = "modified"
    return changed


def assert_only_changed(before: dict[str, str], after: dict[str, str], expected: set[str]) -> None:
    """Exactly `expected` label files changed; pass set() to assert nothing was written."""
    changed = diff_snapshots(before, after)
    unexpected = {k: v for k, v in changed.items() if k not in expected}
    missing = expected - changed.keys()
    problems = []
    if unexpected:
        problems.append(f"unexpectedly changed: {unexpected}")
    if missing:
        problems.append(f"expected to change but did not: {sorted(missing)}")
    assert not problems, "; ".join(problems)


class FakeProgress:
    """A progress dialog that records its values and is cancelled at `cancel_at`."""

    def __init__(self, title, total, cancel_at=None):
        self.title, self.total, self.cancel_at = title, total, cancel_at
        self.values: list[int] = []
        self.closed = False

    def set(self, value):
        self.values.append(value)

    def cancelled(self):
        return self.cancel_at is not None and bool(self.values) and self.values[-1] >= self.cancel_at

    def close(self):
        self.closed = True


class FakePrompter:
    """Answers the UI's dialogs from preset values and records what was asked."""

    def __init__(self, *, taxonomy=True, yaml=None, folders=(), queue=None, text=None, class_name=None,
                 weights=None, threshold=None, class_map=None, cancel_at=None, accept_queue=True,
                 reassign=None, accept_reassign=True, save_path=None):
        self.taxonomy, self.yaml, self.queue, self.text = taxonomy, yaml, queue, text
        self.class_name = class_name
        self.weights, self.threshold = weights, threshold
        self.class_map = class_map          #: {model class name: dataset class name or None}
        self.cancel_at = cancel_at          #: a progress is cancelled once it reaches this ({title: n}, or n)
        self.progresses: list[FakeProgress] = []
        self.accept_queue = accept_queue    #: the answer to the queue accept's confirmation
        self.reassign = reassign            #: (from, to) the reassign dialog answers, or None
        self.accept_reassign = accept_reassign
        self.save_path = save_path          #: where a save dialog answers to save, or None
        self.folders = list(folders)
        self.errors: list[tuple[str, str]] = []
        self.asked: list[tuple] = []

    def confirm_taxonomy(self, *args):
        self.asked.append(("taxonomy",) + args)
        return self.taxonomy

    def error(self, title, text):
        self.errors.append((title, text))

    def choose_yaml(self):
        self.asked.append(("yaml",))
        return None if self.yaml is None else str(self.yaml)

    def choose_folder(self, title):
        self.asked.append(("folder", title))
        return str(self.folders.pop(0)) if self.folders else None

    def edit_queue(self, dataset, current, conf=None):
        self.asked.append(("queue", current, conf))
        return self.queue

    def ask_text(self, title, label):
        self.asked.append(("text", title))
        return self.text

    def pick_class(self, infos):
        self.asked.append(("class", tuple(info.name for info in infos)))
        return next((info for info in infos if info.name == self.class_name), None)

    def choose_weights(self):
        self.asked.append(("weights",))
        return None if self.weights is None else str(self.weights)

    def ask_threshold(self, current):
        self.asked.append(("threshold", current))
        return self.threshold

    def confirm_queue_accept(self, text):
        self.asked.append(("queue accept", text))
        return self.accept_queue

    def ask_reassign(self, names, unnamed_ids):
        self.asked.append(("reassign", tuple(names), tuple(unnamed_ids)))
        return self.reassign

    def choose_save_path(self, title, filter):
        self.asked.append(("save", title))
        return None if self.save_path is None else str(self.save_path)

    def confirm_reassign(self, text):
        self.asked.append(("reassign question", text))
        return self.accept_reassign

    def progress(self, title, total):
        at = self.cancel_at.get(title) if isinstance(self.cancel_at, dict) else self.cancel_at
        self.progresses.append(FakeProgress(title, total, at))
        return self.progresses[-1]

    def edit_class_map(self, cmap, dataset_names):
        self.asked.append(("class map", cmap.model_names, tuple(dataset_names)))
        if self.class_map is None:
            return None
        for name, target in self.class_map.items():
            cmap = cmap.with_target(cmap.model_names.index(name), target)
        return cmap


def open_session(qtbot, source, prompter=None, **kw):
    """A Session with `source` open and its first queue fully built."""
    from deeplabeling.ui.session import Session

    s = Session(prompter or FakePrompter())
    with qtbot.waitSignal(s.queueDone, timeout=5000):
        assert s.open(source, **kw)
    return s


def wait_decoded(qtbot, session, image):
    """Edits wait for the image to be decoded; so do tests that edit."""
    qtbot.waitUntil(lambda: session.images.get(image) is not None, timeout=5000)


@dataclass(frozen=True)
class Broken(Condition):
    """A condition whose test raises, as a build meets an unreadable disk."""

    kind: ClassVar[str] = "broken"
    needs_labels: ClassVar[bool] = False

    def test(self, entry, ctx):
        raise OSError("the disk went away")

    def describe(self, dataset):
        return "broken"

    def to_json(self):
        return {"kind": self.kind}


class FakePredictor:
    """Stands in for UltralyticsPredictor: finds what it is told per file name, fails the
    names it is told to, records what it was asked, and can be held at a gate."""

    def __init__(self, path, *, names=("car", "truck", "human"), found=None, fail=(), gate=None):
        from deeplabeling.core.inference import ModelError

        if "broken" in Path(path).name:
            raise ModelError(f"{Path(path).name} failed to load: not a model")
        self.key, self.names = f"fake:{Path(path).name}", tuple(names)
        self.found, self.fail, self.gate = dict(found or {}), set(fail), gate
        self.asked: list[str] = []
        self.closed = False

    def predict(self, paths):
        from deeplabeling.core.inference import Failure

        if self.gate is not None:
            self.gate.wait(10)
        out = []
        for path in paths:
            self.asked.append(Path(path).name)
            out.append(Failure(f"{Path(path).name}: CUDA out of memory") if Path(path).name in self.fail
                       else list(self.found.get(Path(path).name, [])))
        return out

    def close(self):
        self.closed = True
