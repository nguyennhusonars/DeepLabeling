# Slice 1a: the headless core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `deeplabeling.core`: the label document model (one owner, edits as before/after bytes, global undo), the dataset as training sees it, queues, review marks, settings and app state. It's fully unit-tested and imports no Qt.

**Architecture:** Pure-Python modules under `src/deeplabeling/core/`. `LabelStore` is the only code that reads label files into memory or writes them, always through `write_atomic`. An `Edit` records each file's bytes before and after, which is all undo needs. `Workspace.open` is the one funnel that opens a dataset: it holds the per-root lock, applies the taxonomy guard, and wires the store, history, editor and review marks together. The Qt UI (plan 1b, written once this lands) wraps these objects and adds no label logic.

**Tech Stack:** Python 3.10 (conda base), PyYAML, Pillow, OpenCV and NumPy (test data only), pytest.

**Spec:** [2026-10-04-app-foundation.md](2026-10-04-app-foundation.md). Read it with this plan. This plan implements its Architecture, Label document model, Dataset, Queue, Review marks, State and settings and Errors sections. The window, canvas and keys are plan 1b.

## Global Constraints

- **Interpreter:** conda base, `/home/sonnn/miniconda3/bin/python3` (3.10.12). A shell may have another conda env active: in the session that wrote this plan, bare `python3` was the `insightface` env, which has no PySide6. Every command below spells out the full path.
- **Install nothing.** Everything needed is already in base. Never `pip install -e .`.
- **`src/deeplabeling/core/` never imports PySide6.** Task 11 adds a test that enforces it.
- **One write path.** Label files are written only by `LabelStore.apply` and `LabelStore.restore`, through `write_atomic`. Read the `label-file-safety` skill before any task that touches label files (4, 5, 8).
- **Tests write only under `tmp_path`.** From Task 6, every test runs with `DEEPLABELING_STATE_DIR` set to a temporary folder, and the session fails if the real `.deeplabeling/` changed (landmine 10). Real datasets are only ever read.
- **Disk is nearly full** (about 7.5 GB free): never copy a dataset or a prediction cache.
- **`legacy/` is never imported** and never edited. Port by rewriting; `tools/check_docs.py` enforces the import rule.
- **Doc rules:** one fact, one home; prefer a command over a restatement; cite code as `` `<path>.py::<symbol>` `` from the repo root, never by line number. Run `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py` after any doc edit.
- **Git:** work on branch `slice1-core`. One commit per task, every message ending with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Every task ends green:** the full suite passes (`/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings`) before its commit. PySide6 imports print a NumPy 1.x/2.x warning; it is known and harmless ([environment.md](../knowledge/environment.md#pyside6-and-numpy)).

## Review Focus

These are the failure modes most likely to hurt someone using the app. The spec implies each of them, and each has a named test in the task that owns the code:

1. **A label file changes outside the app between showing and editing.** The transfer tools import whole label zips, for example. The edit must reach the right line or be refused, never land on the wrong line. *(Task 4 `test_a_stale_index_still_finds_the_line`, `test_a_box_that_is_gone_is_refused`; Task 5 `test_apply_refuses_a_box_that_changed_outside`.)*
2. **Undo after the file changed outside.** The undo must be refused, the outside change kept, and the edit dropped, while earlier edits stay undoable. *(Task 8 `test_undo_after_an_outside_change_is_refused_and_dropped`.)*
3. **Opening the labels under the wrong yaml.** pvn-vehicle's 7-class and 13-class yamls read the same files. The app must ask before switching taxonomy, and must count ids the yaml does not name. *(Task 10 `test_a_different_class_list_asks_first_and_can_be_declined`, `test_out_of_range_ids_are_counted`.)*
4. **Bytes the user never touched.** CRLF, a missing final newline, polygons, extra columns and bytes that are not UTF-8 must survive an edit elsewhere, and an undo must restore them exactly. *(Task 1 `test_parse_then_render_returns_the_same_bytes`; Task 4 `test_bytes_that_are_not_utf8_survive_an_edit_elsewhere`; Task 8 `test_undo_then_redo_is_byte_exact_on_the_gauntlet`.)*
5. **A full disk or a crash mid-write.** The old file must stay intact, no temporary file may be left behind, and nothing may be recorded in the history. *(Task 1 `test_a_failed_write_leaves_the_target_and_no_temporary_file`; Task 5 `test_a_failed_write_is_refused_and_leaves_the_file`.)*

## Spec amendments

Found while planning. Task 11 records them in the spec.

| Spec said | This plan does | Why |
|---|---|---|
| port `imagetype`; add `imagesize` | both wait for slice 3 | nothing in slice 1 needs them; the UI gets sizes from Qt's decode |
| `paths.py` has `is_within` | dropped | review keys come from `ImageEntry.rel`, which `Dataset` computes |
| `LabelStore.apply` pushes history and marks review | `Editor.apply` does: store, then history, then marks | keeps the store to reading and writing files; `Editor` is the GUI thread's one entry point |
| — | new `atomic.py`, `editor.py`, `taxonomy.py`, `workspace.py` | the one writer; the apply/undo facade; the guard; the open funnel |
| stamp `(mtime_ns, size)` | `(inode, mtime_ns, size)` | an atomic replace changes the inode, so a same-size rewrite within one mtime tick is still seen |
| decode with `errors="replace"` (legacy) | `surrogateescape` | a byte that is not UTF-8 then survives a write exactly |
| a re-serialised line ends in `\n` | it keeps a CRLF ending; an appended line follows the file's last ending | a CRLF file stays CRLF |
| — | `write_atomic` keeps the target's permission bits | the legacy `mkstemp` writer turned 1,987 pvn-vehicle label files into `0600` (counted 2026-10-04; Task 11 records the command) |
| a missing listed folder | is recorded on the dataset, not fatal | the user can still open the rest and fix the yaml |

## File map

| File | Responsibility | Task |
|---|---|---|
| `pyproject.toml` | add `tests` to pytest's `pythonpath` | 1 |
| `tests/fixtures.py`, `tests/conftest.py` | the edge-case dataset, change detection, the `ds` fixture | 1 |
| `src/deeplabeling/core/__init__.py`, `atomic.py`, `labelio.py` | the one writer; lines and their bytes | 1 |
| `src/deeplabeling/core/geometry.py`, `overlap.py` | IoU and conversions; the stack-count predicate | 2 |
| `src/deeplabeling/core/paths.py`, `dataset.py` | the training label rule; opening a yaml or folder | 3 |
| `src/deeplabeling/core/edits.py` | intents, edits, `materialize` | 4 |
| `src/deeplabeling/core/store.py` | `LabelStore`, `ImageLabels` | 5 |
| `src/deeplabeling/core/state.py`, `settings.py`, `tests/conftest.py` | the state folder and lock; the settings registry; the real-state guard | 6 |
| `src/deeplabeling/core/review.py` | review marks | 7 |
| `src/deeplabeling/core/history.py`, `editor.py` | undo/redo; apply + record + mark | 8 |
| `src/deeplabeling/core/queue.py` | conditions, `ImageFilter`, `Queue` | 9 |
| `src/deeplabeling/core/taxonomy.py`, `workspace.py` | the guard; the open funnel | 10 |
| `tests/core/test_core_imports_no_qt.py`, `.claude/skills/dataset-analysis/scripts/overlaps.py`, docs | the Qt guard; one overlap implementation; knowledge updates | 11 |

All core tests live in `tests/core/`, with unique basenames. They import the edge-case dataset as `from fixtures import …`, because Task 1 puts `tests/` on pytest's path.

---

### Task 1: Test data, the atomic writer, label lines

**Files:**
- Modify: `pyproject.toml` (the `pythonpath` line)
- Modify: `tests/conftest.py`
- Create: `tests/fixtures.py`, `src/deeplabeling/core/__init__.py`, `src/deeplabeling/core/atomic.py`, `src/deeplabeling/core/labelio.py`
- Test: `tests/core/test_atomic.py`, `tests/core/test_labelio.py`

**Interfaces:**
- Produces: `deeplabeling.core.atomic.write_atomic(path, data: bytes) -> None`.
- Produces in `deeplabeling.core.labelio`:
  - `Box = tuple[float, float, float, float]`, plus `PRECISION = 6` and `LOCATE_TOL = 0.002`;
  - `LabelLine(cls_id: int | None, coords: tuple[float, ...], raw: str)`, frozen, with `.parsed`, `.is_polygon`, `.bbox -> Box`, `.terminator -> str`, `.with_class(cls_id) -> LabelLine` and `.with_bbox(bbox) -> LabelLine`;
  - `format_box(cls_id, bbox, terminator="\n") -> LabelLine`;
  - `parse_label_text(str)` and `parse_label_bytes(bytes)`, each returning `tuple[LabelLine, ...]`;
  - `render_label_bytes(lines) -> bytes`, `decode_label_bytes(bytes) -> str`, `encode_label_text(str) -> bytes`;
  - `locate_line(lines, cls_id, bbox, hint=None) -> int | None`.
- Produces in `tests/fixtures.py`:
  - text constants `CAMA_0001`, `CAMB_0001`, `POLY1`, `MIXED`, `CRLF`, `BAD_CORRUPT`, `GAUNTLET`, and the lists `CLASS_NAMES` and `GROUPS`;
  - `make_image(path, w=64, h=48)` and `make_exif_rotated_image(path, w=64, h=48)`;
  - `read_exact(path) -> str`;
  - `DatasetFixture` with `.root`, `.yaml`, `.img(rel)`, `.lbl(rel)` and `.snapshot()`;
  - `build_dataset(root) -> DatasetFixture`;
  - `snapshot(root)`, `diff_snapshots(before, after)` and `assert_only_changed(before, after, expected)`.
- Produces: the pytest fixture `ds` (a built `DatasetFixture` under `tmp_path`).

- [ ] **Step 1: Branch, and commit the approved design**

```bash
cd /home/sonnn/Documents/PGit/DeepLabeling
git checkout -b slice1-core
git add .gitignore docs/design/2026-10-04-app-foundation.md docs/design/2026-10-04-app-foundation-core-plan.md docs/knowledge/datasets.md
git commit -m "docs: app foundation design and the slice 1a core plan" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Put `tests/` on pytest's path**

In `pyproject.toml`, replace `pythonpath = ["src"]` with:

```toml
pythonpath = ["src", "tests"]
```

- [ ] **Step 3: Write the edge-case dataset**

Create `tests/fixtures.py`:

```python
"""A generated dataset holding every edge case, and the change-detection helpers.

Rewritten from the legacy suite's fixtures (legacy/ is never imported). Nothing
binary is committed: `build_dataset` writes the whole tree in well under a second.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import yaml
from PIL import Image

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
```

Replace `tests/conftest.py` with:

```python
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
```

- [ ] **Step 4: Write the failing tests**

Create `tests/core/test_atomic.py`:

```python
import os
import stat

import pytest

from deeplabeling.core import atomic
from deeplabeling.core.atomic import write_atomic


def mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def test_writes_the_exact_bytes(tmp_path):
    target = tmp_path / "a.txt"
    write_atomic(target, b"0 0.5 0.5 0.2 0.2\r\n\xff")
    assert target.read_bytes() == b"0 0.5 0.5 0.2 0.2\r\n\xff"


def test_replaces_an_existing_file(tmp_path):
    target = tmp_path / "a.txt"
    target.write_bytes(b"old")
    write_atomic(target, b"new")
    assert target.read_bytes() == b"new"


def test_creates_missing_parent_folders(tmp_path):
    target = tmp_path / "x" / "labels" / "a.txt"
    write_atomic(target, b"")
    assert target.read_bytes() == b""


def test_a_failed_write_leaves_the_target_and_no_temporary_file(tmp_path, monkeypatch):
    target = tmp_path / "a.txt"
    target.write_bytes(b"old")

    def full_disk(src, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(atomic.os, "replace", full_disk)
    with pytest.raises(OSError):
        write_atomic(target, b"new")
    assert target.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["a.txt"]


def test_an_existing_file_keeps_its_permissions(tmp_path):
    target = tmp_path / "a.txt"
    target.write_bytes(b"old")
    os.chmod(target, 0o664)
    write_atomic(target, b"new")
    assert mode(target) == 0o664


def test_a_new_file_gets_the_default_permissions_not_0600(tmp_path):
    target = tmp_path / "a.txt"
    write_atomic(target, b"new")
    assert mode(target) == 0o666 & ~atomic._UMASK
```

Create `tests/core/test_labelio.py`:

```python
import pytest

from deeplabeling.core.labelio import (
    LabelLine,
    decode_label_bytes,
    encode_label_text,
    format_box,
    locate_line,
    parse_label_bytes,
    render_label_bytes,
)
from fixtures import CRLF, GAUNTLET, MIXED, POLY1

ROUND_TRIPS = [
    b"",
    b"0 0.5 0.5 0.2 0.2\n",
    CRLF.encode(),
    b"0 0.5 0.5 0.2 0.2",
    b"\n\n   \n",
    b"0 0.5 0.5 0.2 0.2\n\xff\xfe not utf-8\n",
    b"inf 0.5 0.5 0.2 0.2\nnan 1 1 1 1\n",
    GAUNTLET.encode(),
    POLY1.encode(),
    MIXED.encode(),
]


@pytest.mark.parametrize("data", ROUND_TRIPS)
def test_parse_then_render_returns_the_same_bytes(data):
    assert render_label_bytes(parse_label_bytes(data)) == data


@pytest.mark.parametrize("data", [bytes(range(256)), b"\xc3\x28\x80"])
def test_decoding_is_lossless_for_any_bytes(data):
    assert encode_label_text(decode_label_bytes(data)) == data


def test_the_gauntlet_parses_without_raising():
    lines = parse_label_bytes(GAUNTLET.encode())
    assert [ln.parsed for ln in lines] == [True, True, True, True, False, True, True,
                                           False, False, False, True]
    assert [ln.cls_id for ln in lines if ln.parsed] == [1, 99, -1, 0, 0, 0, 0]


def test_a_class_that_is_infinite_or_nan_is_unparsed():
    assert [ln.parsed for ln in parse_label_bytes(b"inf 0.5 0.5 0.2 0.2\nnan 1 1 1 1\n")] == [False, False]


def test_a_polygon_is_shown_by_its_extent():
    poly = parse_label_bytes(POLY1.encode())[0]
    assert poly.is_polygon
    assert poly.bbox == pytest.approx((0.15, 0.15, 0.1, 0.1))


def test_an_extra_column_is_still_a_box():
    line = parse_label_bytes(b"0 0.5 0.5 0.2 0.2 0.95\n")[0]
    assert line.parsed and not line.is_polygon
    assert line.bbox == (0.5, 0.5, 0.2, 0.2)


@pytest.mark.parametrize("raw, ending", [
    ("0 1 1 1 1\n", "\n"), ("0 1 1 1 1\r\n", "\r\n"), ("0 1 1 1 1", ""), ("\n", "\n"),
])
def test_terminator(raw, ending):
    assert LabelLine(None, (), raw).terminator == ending


def test_with_class_splices_the_id_and_keeps_every_digit():
    line = parse_label_bytes(b"  0 0.30 0.5 0.2 0.2 0.95\r\n")[0]
    assert line.with_class(12).raw == "  12 0.30 0.5 0.2 0.2 0.95\r\n"


def test_with_class_keeps_polygon_points():
    poly = parse_label_bytes(POLY1.encode())[0]
    assert poly.with_class(3).raw == "3" + POLY1.splitlines(keepends=True)[0][1:]


def test_with_class_gives_a_last_line_its_newline():
    line = parse_label_bytes(b"0 0.5 0.5 0.2 0.2")[0]
    assert line.with_class(1).raw == "1 0.5 0.5 0.2 0.2\n"


def test_with_bbox_writes_a_plain_box_and_keeps_crlf():
    line = parse_label_bytes(b"0 0.5 0.5 0.2 0.2 0.95\r\n")[0]
    moved = line.with_bbox((0.25, 0.75, 0.1, 0.2))
    assert moved.raw == "0 0.250000 0.750000 0.100000 0.200000\r\n"
    assert moved.bbox == (0.25, 0.75, 0.1, 0.2)


def test_format_box_never_writes_negative_zero():
    assert format_box(0, (-0.0, 0.5, 0.1, 0.1)).raw == "0 0.000000 0.500000 0.100000 0.100000\n"


THREE = parse_label_bytes(b"0 0.5 0.5 0.2 0.2\n1 0.3 0.3 0.1 0.1\n1 0.7 0.7 0.1 0.1\n")


def test_locate_trusts_a_correct_hint():
    assert locate_line(THREE, 1, (0.7, 0.7, 0.1, 0.1), hint=2) == 2


def test_locate_searches_when_the_hint_is_stale():
    assert locate_line(THREE, 1, (0.7, 0.7, 0.1, 0.1), hint=0) == 2
    assert locate_line(THREE, 1, (0.7, 0.7, 0.1, 0.1), hint=9) == 2


def test_locate_needs_the_class_to_agree():
    assert locate_line(THREE, 0, (0.3, 0.3, 0.1, 0.1)) is None


def test_locate_tolerates_a_small_drift_only():
    assert locate_line(THREE, 0, (0.5015, 0.5, 0.2, 0.2)) == 0
    assert locate_line(THREE, 0, (0.503, 0.5, 0.2, 0.2)) is None


def test_locate_refuses_identical_lines_without_a_correct_hint():
    lines = parse_label_bytes(GAUNTLET.encode())
    assert locate_line(lines, 0, (0.5, 0.5, 0.2, 0.2)) is None
    assert locate_line(lines, 0, (0.5, 0.5, 0.2, 0.2), hint=6) == 6


def test_locate_finds_a_polygon_by_its_extent():
    lines = parse_label_bytes(POLY1.encode())
    assert locate_line(lines, 1, lines[1].bbox) == 1
```

- [ ] **Step 5: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core -q`
Expected: collection errors, `ModuleNotFoundError: No module named 'deeplabeling.core'`.

- [ ] **Step 6: Write the core package, the writer and the line model**

Create `src/deeplabeling/core/__init__.py`:

```python
"""DeepLabeling's core: label files, datasets, queues and app state.

Nothing here imports Qt (tests/core/test_core_imports_no_qt.py checks it), so the
core runs headless and the dataset-analysis scripts can import it.
"""
```

Create `src/deeplabeling/core/atomic.py`:

```python
"""The one atomic file writer. Every file DeepLabeling writes goes through it."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

#: Read once, at import: the umask can only be read by setting it, which must not
#: race with other threads creating files.
_UMASK = os.umask(0)
os.umask(_UMASK)


def write_atomic(path, data: bytes) -> None:
    """Replace `path` with `data` so that a crash leaves the old file or the new one.

    The bytes go to a temporary file beside the target, are flushed and fsynced,
    and `os.replace` moves them into place. On any failure the temporary file is
    removed and the target is untouched. Missing parent folders are created.

    The file keeps the target's permission bits, or gets the default ones (0o666
    less the umask) when new. `mkstemp` alone creates 0o600, which made every
    label file the legacy app edited private to its owner.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = os.stat(path).st_mode & 0o7777
    except FileNotFoundError:
        mode = 0o666 & ~_UMASK
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            os.fchmod(f.fileno(), mode)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
```

Create `src/deeplabeling/core/labelio.py`:

```python
"""Reading and editing YOLO label files, byte for byte.

The rules are in docs/knowledge/label-files.md: every line keeps its exact source
text, line ending included, and only a line the user changed is re-serialised;
the parser never raises; a line to act on is located by class and box.

Bytes are decoded with `surrogateescape`, so bytes that are not UTF-8 survive too:
`encode_label_text(decode_label_bytes(b)) == b` for every `b`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

Box = tuple[float, float, float, float]

#: Digits after the point in a re-serialised coordinate.
PRECISION = 6

#: How far a recorded box may drift from a line's box and still be that line.
LOCATE_TOL = 0.002

#: Leading whitespace and the class token, for splicing in a new class id.
_FIRST_TOKEN = re.compile(r"^(\s*)(\S+)")


def decode_label_bytes(data: bytes) -> str:
    return data.decode("utf-8", "surrogateescape")


def encode_label_text(text: str) -> bytes:
    return text.encode("utf-8", "surrogateescape")


@dataclass(frozen=True)
class LabelLine:
    """One line of a label file, emitted exactly as `raw`.

    `cls_id` is None when the line could not be parsed. `coords` holds every
    number after the class id: 4 for a box, 5 for a box with an extra column,
    more for a polygon.
    """

    cls_id: int | None
    coords: tuple[float, ...]
    raw: str

    @property
    def parsed(self) -> bool:
        return self.cls_id is not None and len(self.coords) >= 4

    @property
    def is_polygon(self) -> bool:
        """More than a box and one extra column: ultralytics reads it as a segment."""
        return len(self.coords) > 5

    @property
    def bbox(self) -> Box:
        """Normalised (cx, cy, w, h); for a polygon, the extent of its points."""
        if not self.parsed:
            return (0.0, 0.0, 0.0, 0.0)
        if self.is_polygon:
            xs, ys = self.coords[0::2], self.coords[1::2]
            x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
            return ((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1)
        cx, cy, w, h = self.coords[:4]
        return (cx, cy, w, h)

    @property
    def terminator(self) -> str:
        """The line's own line ending; "" for a last line without one."""
        body = self.raw.splitlines()
        return self.raw[len(body[0]):] if body else self.raw

    def with_class(self, cls_id: int) -> LabelLine:
        """This line with another class id, spliced into the raw text.

        Every coordinate keeps its exact digits. A last line without a line
        ending gains "\\n", so nothing appended later can run into it.
        """
        raw = _FIRST_TOKEN.sub(lambda m: f"{m.group(1)}{int(cls_id)}", self.raw, count=1)
        if not self.terminator:
            raw += "\n"
        return LabelLine(int(cls_id), self.coords, raw)

    def with_bbox(self, bbox: Box) -> LabelLine:
        """This line as a plain 5-token box at `bbox`, keeping a CRLF ending.

        Polygon points and extra columns are dropped: callers refuse polygons.
        """
        return format_box(self.cls_id, bbox, "\r\n" if self.terminator == "\r\n" else "\n")


def format_box(cls_id: int, bbox: Box, terminator: str = "\n") -> LabelLine:
    """A new 5-token box line with coordinates at PRECISION digits."""
    text = " ".join(f"{v + 0.0:.{PRECISION}f}" for v in bbox)   # + 0.0 turns -0.0 into 0.0
    coords = tuple(float(t) for t in text.split())
    return LabelLine(int(cls_id), coords, f"{int(cls_id)} {text}{terminator}")


def parse_label_text(text: str) -> tuple[LabelLine, ...]:
    """Every line of `text`, each keeping its raw text. Never raises."""
    lines = []
    for raw in text.splitlines(keepends=True):
        parts = raw.split()
        if len(parts) < 5:
            lines.append(LabelLine(None, (), raw))
            continue
        try:
            cls_id = int(float(parts[0]))
            coords = tuple(float(p) for p in parts[1:])
        except (ValueError, OverflowError):
            lines.append(LabelLine(None, (), raw))
            continue
        lines.append(LabelLine(cls_id, coords, raw))
    return tuple(lines)


def parse_label_bytes(data: bytes) -> tuple[LabelLine, ...]:
    return parse_label_text(decode_label_bytes(data))


def render_label_bytes(lines: Sequence[LabelLine]) -> bytes:
    return encode_label_text("".join(line.raw for line in lines))


def locate_line(lines: Sequence[LabelLine], cls_id: int, bbox: Box,
                hint: int | None = None) -> int | None:
    """Index of the one line holding class `cls_id` at `bbox`, or None.

    `hint`, the index the line had when it was recorded, is tried first since it
    is nearly always right. Otherwise every line is searched, and None is
    returned unless exactly one matches: class AND box must agree, and two
    identical lines make the answer ambiguous.
    """
    def holds(line: LabelLine) -> bool:
        return (line.parsed and line.cls_id == cls_id
                and all(abs(a - b) <= LOCATE_TOL for a, b in zip(line.bbox, bbox)))

    if hint is not None and 0 <= hint < len(lines) and holds(lines[hint]):
        return hint
    hits = [i for i, line in enumerate(lines) if holds(line)]
    return hits[0] if len(hits) == 1 else None
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core -q`
Expected: all pass.

- [ ] **Step 8: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings`
Expected: every test passes, the 60 earlier ones included.

```bash
git add pyproject.toml tests/conftest.py tests/fixtures.py tests/core src/deeplabeling/core
git commit -m "core: atomic writer and byte-preserving label lines" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Geometry and the overlap predicate

**Files:**
- Create: `src/deeplabeling/core/geometry.py`, `src/deeplabeling/core/overlap.py`
- Test: `tests/core/test_geometry.py`, `tests/core/test_overlap.py`

**Interfaces:**
- Consumes: nothing.
- Produces in `deeplabeling.core.geometry`: `Box`, `corners(box)`, `iou_xyxy(a, b)`, `iou(a, b)`, `norm_to_px(box, img_w, img_h)` and `px_to_norm(x1, y1, x2, y2, img_w, img_h)`.
- Produces in `deeplabeling.core.overlap`:
  - `SCOPES = ("any", "same", "different")` and `DUPLICATES = ("any", 0.99, 1.0)`;
  - `pair_counts(scope, cls_a, cls_b) -> bool` and `iou_in_range(value, lo, hi) -> bool`;
  - `stack_counts(boxes: Sequence[tuple[int, Box]], scope, lo, hi) -> dict[int, int]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_geometry.py`:

```python
import math

import pytest

from deeplabeling.core.geometry import corners, iou, iou_xyxy, norm_to_px, px_to_norm


def test_corners():
    assert corners((0.5, 0.5, 0.2, 0.4)) == pytest.approx((0.4, 0.3, 0.6, 0.7))


def test_identical_boxes_have_iou_exactly_one():
    assert iou((0.5, 0.5, 0.2, 0.2), (0.5, 0.5, 0.2, 0.2)) == 1.0


def test_disjoint_and_touching_boxes_have_iou_zero():
    assert iou((0.2, 0.2, 0.1, 0.1), (0.8, 0.8, 0.1, 0.1)) == 0.0
    assert iou_xyxy((0, 0, 1, 1), (1, 0, 2, 1)) == 0.0


def test_a_known_overlap():
    assert iou_xyxy((0, 0, 2, 1), (1, 0, 3, 1)) == pytest.approx(1 / 3)


def test_degenerate_boxes_have_iou_zero():
    assert iou_xyxy((0, 0, 0, 0), (0, 0, 0, 0)) == 0.0


def test_iou_does_not_depend_on_the_image_size():
    a, b = (0.4, 0.5, 0.3, 0.2), (0.5, 0.45, 0.2, 0.3)
    assert iou(a, b) == pytest.approx(iou_xyxy(norm_to_px(a, 1920, 1080), norm_to_px(b, 1920, 1080)))


def test_pixels_and_back():
    box = (0.31, 0.47, 0.123, 0.456)
    assert px_to_norm(*norm_to_px(box, 640, 480), 640, 480) == pytest.approx(box)


def test_corners_in_any_order():
    assert px_to_norm(60, 40, 20, 10, 100, 100) == pytest.approx((0.4, 0.25, 0.4, 0.3))


def test_a_box_partly_outside_is_clamped_to_the_image():
    cx, cy, w, h = px_to_norm(-10, -10, 30, 30, 100, 100)
    assert (cx, cy, w, h) == pytest.approx((0.15, 0.15, 0.3, 0.3))
    assert cx - w / 2 >= 0 and cy - h / 2 >= 0


def test_a_zero_size_image_is_an_error():
    with pytest.raises(ValueError):
        px_to_norm(0, 0, 1, 1, 0, 10)


def test_no_nan_from_a_box_entirely_outside():
    assert not any(math.isnan(v) for v in px_to_norm(200, 200, 300, 300, 100, 100))
```

Create `tests/core/test_overlap.py`:

```python
import pytest

from deeplabeling.core.overlap import DUPLICATES, iou_in_range, pair_counts, stack_counts

A = (0.5, 0.5, 0.2, 0.2)
FAR = (0.1, 0.1, 0.05, 0.05)


def test_identical_boxes_are_counted():
    assert stack_counts([(0, A), (0, A), (1, FAR)], *DUPLICATES) == {0: 2, 1: 2}


def test_three_identical_boxes_each_read_three():
    assert stack_counts([(0, A), (0, A), (2, A)], *DUPLICATES) == {0: 3, 1: 3, 2: 3}


def test_the_count_is_per_box_in_a_chain():
    a, b, c = (0.30, 0.5, 0.2, 0.2), (0.40, 0.5, 0.2, 0.2), (0.55, 0.5, 0.2, 0.2)
    assert stack_counts([(0, a), (0, b), (0, c)], "any", 0.1, 1.0) == {0: 2, 1: 3, 2: 2}


@pytest.mark.parametrize("scope, expected", [("any", True), ("same", False), ("different", True)])
def test_scope_for_a_different_class_pair(scope, expected):
    assert pair_counts(scope, 0, 1) is expected


@pytest.mark.parametrize("scope, expected", [("any", True), ("same", True), ("different", False)])
def test_scope_for_a_same_class_pair(scope, expected):
    assert pair_counts(scope, 2, 2) is expected


def test_a_pair_that_does_not_touch_never_counts_even_from_zero():
    assert stack_counts([(0, A), (0, FAR)], "any", 0.0, 1.0) == {}


def test_a_max_below_one_hides_exact_duplicates():
    assert stack_counts([(0, A), (0, A)], "any", 0.5, 0.9) == {}


def test_the_range_is_inclusive():
    assert iou_in_range(1.0, 0.99, 1.0) and iou_in_range(0.99, 0.99, 1.0)


def test_an_unknown_scope_is_an_error():
    with pytest.raises(ValueError):
        pair_counts("both", 0, 0)
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_geometry.py tests/core/test_overlap.py -q`
Expected: `ModuleNotFoundError` for `deeplabeling.core.geometry` and `.overlap`.

- [ ] **Step 3: Write geometry and overlap**

Create `src/deeplabeling/core/geometry.py`:

```python
"""Box geometry.

A normalised box is (cx, cy, w, h) in [0, 1]; a pixel box is (x1, y1, x2, y2) in
image pixels, unrounded. IoU does not change under independent x/y scaling, so it
is computed on normalised corners, with no image size
(docs/knowledge/matching.md#geometry).
"""

from __future__ import annotations

Box = tuple[float, float, float, float]


def corners(box: Box) -> Box:
    """(cx, cy, w, h) -> (x1, y1, x2, y2), in the same units."""
    cx, cy, w, h = box
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def iou_xyxy(a: Box, b: Box) -> float:
    """IoU of two (x1, y1, x2, y2) boxes; 0.0 for disjoint or degenerate ones."""
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    if ix <= 0.0 or iy <= 0.0:
        return 0.0
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0.0 else 0.0


def iou(a: Box, b: Box) -> float:
    """IoU of two normalised (cx, cy, w, h) boxes."""
    return iou_xyxy(corners(a), corners(b))


def norm_to_px(box: Box, img_w: int, img_h: int) -> Box:
    """Normalised (cx, cy, w, h) -> pixel (x1, y1, x2, y2), unrounded."""
    x1, y1, x2, y2 = corners(box)
    return (x1 * img_w, y1 * img_h, x2 * img_w, y2 * img_h)


def px_to_norm(x1: float, y1: float, x2: float, y2: float, img_w: int, img_h: int) -> Box:
    """Pixel corners, in either order -> normalised (cx, cy, w, h), clamped.

    Each corner is clamped to the image first, so the whole box lies inside it;
    clamping cx, cy, w and h one by one would not guarantee that.
    """
    if img_w <= 0 or img_h <= 0:
        raise ValueError(f"image size must be positive, got {img_w}x{img_h}")
    lx, hx = sorted((min(max(x1, 0.0), img_w), min(max(x2, 0.0), img_w)))
    ly, hy = sorted((min(max(y1, 0.0), img_h), min(max(y2, 0.0), img_h)))
    return ((lx + hx) / 2 / img_w, (ly + hy) / 2 / img_h, (hx - lx) / img_w, (hy - ly) / img_h)
```

Create `src/deeplabeling/core/overlap.py`:

```python
"""Which labelled boxes overlap one another: the one predicate the canvas's stack
counts and slice 3's overlap filter share
(docs/knowledge/matching.md#overlap-between-labels)."""

from __future__ import annotations

from collections.abc import Sequence

from .geometry import Box, iou

SCOPES = ("any", "same", "different")

#: What slice 1's canvas counts: exact duplicates, of any class.
DUPLICATES = ("any", 0.99, 1.0)


def pair_counts(scope: str, cls_a: int, cls_b: int) -> bool:
    """Whether a pair of classes counts as an overlap under `scope`."""
    if scope == "any":
        return True
    if scope == "same":
        return cls_a == cls_b
    if scope == "different":
        return cls_a != cls_b
    raise ValueError(f"unknown overlap scope {scope!r}")


def iou_in_range(value: float, lo: float, hi: float) -> bool:
    """Inclusive at both ends; a pair that does not touch never counts, even from 0."""
    return value > 0.0 and lo <= value <= hi


def stack_counts(boxes: Sequence[tuple[int, Box]], scope: str, lo: float, hi: float) -> dict[int, int]:
    """{position: boxes stacked on it, itself included} for every box with a partner.

    `boxes` are (class, normalised box) pairs. The count is per box, not per
    group: in a chain A-B-C where A and C do not touch, A reads 2 and B reads 3.
    """
    partners: dict[int, int] = {}
    for i in range(len(boxes)):
        ci, bi = boxes[i]
        for j in range(i + 1, len(boxes)):
            cj, bj = boxes[j]
            if pair_counts(scope, ci, cj) and iou_in_range(iou(bi, bj), lo, hi):
                partners[i] = partners.get(i, 0) + 1
                partners[j] = partners.get(j, 0) + 1
    return {i: n + 1 for i, n in partners.items()}
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_geometry.py tests/core/test_overlap.py -q`
Expected: all pass.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings`
Expected: all pass.

```bash
git add src/deeplabeling/core/geometry.py src/deeplabeling/core/overlap.py tests/core/test_geometry.py tests/core/test_overlap.py
git commit -m "core: geometry and the overlap predicate" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Label paths and the dataset

**Files:**
- Create: `src/deeplabeling/core/paths.py`, `src/deeplabeling/core/dataset.py`
- Test: `tests/core/test_paths.py`, `tests/core/test_dataset.py`, `tests/core/test_real_datasets.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (the `ds` fixture from Task 1).
- Produces: `deeplabeling.core.paths.training_label_path(image: Path) -> Path` and `folder_label_path(image: Path, label_dir: Path) -> Path`.
- Produces in `deeplabeling.core.dataset`:
  - the constants `IMG_FORMATS`, `SPLITS = ("train", "val", "test")` and `FOLDER_SPLIT = "images"`;
  - `DatasetError(Exception)`;
  - `ImageEntry(path, label_path, split, rel, order)`, frozen;
  - `Dataset`, frozen and compared by identity, with the fields `source`, `labels`, `root`, `names: tuple[str, ...]`, `groups: dict[str, tuple[str, ...]]`, `images: tuple[ImageEntry, ...]`, `shared_labels: frozenset[Path]` and `missing: tuple[Path, ...]`;
  - its methods `Dataset.open(source, labels=None)`, `.opening_key -> str`, `.splits`, `.entry(image) -> ImageEntry` (raising `KeyError` for an unknown image), `.id_of(name) -> int | None` and `.known(cls_id) -> bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_paths.py`:

```python
from pathlib import Path

import pytest

from deeplabeling.core.paths import folder_label_path, training_label_path


@pytest.mark.parametrize("image, label", [
    ("/d/camA/images/0001.jpg", "/d/camA/labels/0001.txt"),
    ("/d/images/sub/a.jpg", "/d/labels/sub/a.txt"),
    ("/d/images/x/images/a.jpg", "/d/images/x/labels/a.txt"),     # the LAST /images/
    ("/d/frames/a.jpg", "/d/frames/a.txt"),                       # beside it, as training reads
    ("/d/my_images/a.jpg", "/d/my_images/a.txt"),                 # a name, not a folder
    ("/d/v1.2/images/a.b.jpg", "/d/v1.2/labels/a.b.txt"),
])
def test_the_training_rule(image, label):
    assert training_label_path(Path(image)) == Path(label)


def test_an_explicit_label_folder():
    assert folder_label_path(Path("/d/frames/sub/a.jpg"), Path("/l")) == Path("/l/a.txt")
```

Create `tests/core/test_dataset.py`:

```python
import pytest
import yaml

from deeplabeling.core.dataset import FOLDER_SPLIT, Dataset, DatasetError
from deeplabeling.core.paths import training_label_path
from fixtures import CLASS_NAMES, make_image

ORDER = [
    "camA/images/0001.jpg", "camA/images/0002.jpg", "camA/images/0003.jpg",
    "camA/images/0004.JPG", "camA/images/sub/0005.jpg",
    "camB/images/0001.jpg", "camB/images/rot.jpg", "camB/images/twin.jpg",
    "camB/images/twin.png", "weird/images/имя пробел.jpg",
    "bad/images/corrupt.jpg", "bad/images/ok.jpg", "crlf/images/c.jpg",
    "seg/images/mixed.jpg", "seg/images/poly1.jpg",
]


def rewrite_yaml(ds, **changes):
    data = yaml.safe_load(ds.yaml.read_text(encoding="utf-8"))
    data.update(changes)
    ds.yaml.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def test_images_are_found_recursively_and_sorted_train_first(ds):
    d = Dataset.open(ds.yaml)
    assert [e.rel for e in d.images] == ORDER
    assert [e.order for e in d.images] == list(range(len(ORDER)))
    assert d.splits == ("train", "val")
    assert [e.split for e in d.images].count("val") == 5


def test_label_paths_follow_the_training_rule(ds):
    d = Dataset.open(ds.yaml)
    assert all(e.label_path == training_label_path(e.path) for e in d.images)
    assert d.entry(ds.img("camA/sub/0005.jpg")).label_path == ds.lbl("camA/sub/0005")


def test_the_root_is_a_realpath_and_keys_are_posix(ds):
    d = Dataset.open(ds.yaml)
    assert d.root == ds.root.resolve()
    assert d.entry(ds.img("weird/имя пробел.jpg")).rel == "weird/images/имя пробел.jpg"


def test_names_and_groups(ds):
    d = Dataset.open(ds.yaml)
    assert d.names == tuple(CLASS_NAMES)
    assert d.groups["bus"] == ("bus_m", "bus_l")
    assert d.id_of("bus_l") == 3 and d.id_of("truck") is None
    assert d.known(3) and not d.known(4) and not d.known(-1)


def test_two_images_sharing_one_label_file_are_found(ds):
    assert Dataset.open(ds.yaml).shared_labels == {ds.lbl("camB/twin")}


def test_a_missing_listed_folder_is_recorded_not_fatal(ds):
    rewrite_yaml(ds, test=["gone/images"])
    d = Dataset.open(ds.yaml)
    assert d.missing == ((ds.root / "gone/images").resolve(),)
    assert len(d.images) == len(ORDER)


def test_an_image_listed_in_two_splits_appears_once_under_the_first(ds):
    rewrite_yaml(ds, test=["camA/images"])
    d = Dataset.open(ds.yaml)
    assert len(d.images) == len(ORDER)
    assert d.entry(ds.img("camA/0001.jpg")).split == "train"


def test_a_txt_list_of_images(ds):
    listing = ds.root / "list.txt"
    listing.write_text(f"./camA/images/0001.jpg\ncamB/images/0001.jpg\n{ds.img('crlf/c.jpg')}\n\n")
    rewrite_yaml(ds, train=["list.txt"], val=None)
    d = Dataset.open(ds.yaml)
    assert [e.rel for e in d.images] == ["camA/images/0001.jpg", "camB/images/0001.jpg", "crlf/images/c.jpg"]


def test_names_as_a_dict_with_a_gap(ds):
    rewrite_yaml(ds, names={0: "a", 2: "c"})
    assert Dataset.open(ds.yaml).names == ("a", "class_1", "c")


def test_nc_alone_gives_numbered_names(ds):
    data = yaml.safe_load(ds.yaml.read_text(encoding="utf-8"))
    del data["names"]
    data["nc"] = 2
    ds.yaml.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert Dataset.open(ds.yaml).names == ("class_0", "class_1")


def test_neither_names_nor_nc_is_refused(ds):
    data = yaml.safe_load(ds.yaml.read_text(encoding="utf-8"))
    del data["names"]
    ds.yaml.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(DatasetError, match="names"):
        Dataset.open(ds.yaml)


def test_a_relative_path_is_relative_to_the_yaml(ds):
    sub = ds.root / "cfg"
    sub.mkdir()
    data = yaml.safe_load(ds.yaml.read_text(encoding="utf-8"))
    data["path"] = ".."
    (sub / "data.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert Dataset.open(sub / "data.yaml").root == ds.root.resolve()


def test_a_yaml_listing_no_images_is_refused(ds):
    rewrite_yaml(ds, train=["gone/images"], val=None)
    with pytest.raises(DatasetError, match="no images"):
        Dataset.open(ds.yaml)


def test_something_that_is_not_a_dataset_is_refused(ds):
    with pytest.raises(DatasetError):
        Dataset.open(ds.lbl("camA/0001"))
    with pytest.raises(DatasetError):
        Dataset.open(ds.root / "nowhere")


def test_a_yaml_with_a_label_folder_is_refused(ds):
    with pytest.raises(DatasetError):
        Dataset.open(ds.yaml, labels=ds.root)


def test_a_folder_launch_uses_the_training_rule(ds):
    d = Dataset.open(ds.root / "camA/images")
    assert [e.rel for e in d.images] == ["0001.jpg", "0002.jpg", "0003.jpg", "0004.JPG", "sub/0005.jpg"]
    assert d.splits == (FOLDER_SPLIT,)
    assert d.entry(ds.img("camA/0001.jpg")).label_path == ds.lbl("camA/0001")
    assert d.names == ()
    assert d.known(57)


def test_a_folder_launch_reads_classes_txt(ds):
    (ds.root / "camA/labels/classes.txt").write_text("a\nb\n\n")
    assert Dataset.open(ds.root / "camA/images").names == ("a", "b")


def test_a_folder_with_no_images_component_needs_a_label_folder(ds):
    with pytest.raises(DatasetError, match="label folder"):
        Dataset.open(ds.root / "frames")
    d = Dataset.open(ds.root / "frames", labels=ds.root / "frame_labels")
    assert d.images[0].label_path == ds.root / "frame_labels/x0001.txt"


def test_a_folder_with_no_images_is_refused(ds):
    (ds.root / "empty/images").mkdir(parents=True)
    with pytest.raises(DatasetError, match="no images"):
        Dataset.open(ds.root / "empty/images")


def test_opening_keys_tell_launches_apart(ds):
    by_yaml = Dataset.open(ds.yaml).opening_key
    by_folder = Dataset.open(ds.root / "frames", labels=ds.root / "l").opening_key
    assert by_yaml == str(ds.yaml) and by_folder != by_yaml and "|" in by_folder


def test_an_image_added_after_open_is_unknown(ds):
    d = Dataset.open(ds.yaml)
    make_image(ds.img("camA/late.jpg"))
    with pytest.raises(KeyError):
        d.entry(ds.img("camA/late.jpg"))
```

Create `tests/core/test_real_datasets.py`:

```python
"""Read-only checks against the real pvn-vehicle dataset, skipped where it is absent.

Nothing here writes: the dataset is opened and its paths compared."""

import glob
from pathlib import Path

import pytest
import yaml

from deeplabeling.core.dataset import IMG_FORMATS, Dataset
from deeplabeling.core.paths import training_label_path

PVN = Path("/home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle")
pytestmark = pytest.mark.skipif(not (PVN / "data_13class.yaml").is_file(),
                                reason="pvn-vehicle is not on this machine")


def test_data_13class_opens_to_what_training_reads():
    yml = PVN / "data_13class.yaml"
    data = yaml.safe_load(yml.read_text())
    expected = set()
    for split in ("train", "val"):
        for folder in data[split]:
            where = (PVN / folder).resolve()
            expected |= {f for f in glob.glob(f"{glob.escape(str(where))}/**/*.*", recursive=True)
                         if f.rpartition(".")[-1].lower() in IMG_FORMATS}
    d = Dataset.open(yml)
    assert {str(e.path) for e in d.images} == expected
    assert all(e.label_path == training_label_path(e.path) for e in d.images)
    assert d.names == tuple(data["names"])
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_paths.py tests/core/test_dataset.py tests/core/test_real_datasets.py -q`
Expected: `ModuleNotFoundError` for `deeplabeling.core.paths` and `.dataset`.

- [ ] **Step 3: Write paths and dataset**

Create `src/deeplabeling/core/paths.py`:

```python
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


def folder_label_path(image: Path, label_dir: Path) -> Path:
    """The label file in an explicitly given label folder."""
    return label_dir / f"{image.stem}.txt"
```

Create `src/deeplabeling/core/dataset.py`:

```python
"""A dataset: its images, their label files and its class names, found the way
training finds them (docs/design/2026-10-04-app-foundation.md#dataset)."""

from __future__ import annotations

import glob
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .paths import folder_label_path, training_label_path

#: The union of IMG_FORMATS in the editable ultralytics install and the training
#: fork, which differ: avif, heif and jp2 in one, pfm in the other.
IMG_FORMATS = frozenset({
    "avif", "bmp", "dng", "heic", "heif", "jp2", "jpeg", "jpg", "mpo", "pfm",
    "png", "tif", "tiff", "webp",
})
SPLITS = ("train", "val", "test")
#: The one split of a folder launch.
FOLDER_SPLIT = "images"


class DatasetError(Exception):
    """The dataset cannot be opened. The message is for the user."""


@dataclass(frozen=True)
class ImageEntry:
    path: Path        #: absolute, as training builds it
    label_path: Path
    split: str
    rel: str          #: the POSIX path under the root, or the absolute path outside it
    order: int        #: the position in dataset order


@dataclass(frozen=True, eq=False)
class Dataset:
    source: Path                        #: the yaml, or the image folder
    labels: Path | None                 #: a folder launch's explicit label folder
    root: Path                          #: the canonical root, a realpath
    names: tuple[str, ...]              #: class names by id; empty when unknown
    groups: dict[str, tuple[str, ...]]
    images: tuple[ImageEntry, ...]
    shared_labels: frozenset[Path]      #: label files more than one image resolves to
    missing: tuple[Path, ...]           #: listed folders or lists that do not exist
    _by_path: dict[Path, ImageEntry] = field(default_factory=dict, repr=False)
    _ids: dict[str, int] = field(default_factory=dict, repr=False)

    @classmethod
    def open(cls, source, labels=None) -> Dataset:
        """Open a dataset yaml, or an image folder with an optional label folder."""
        source = Path(source).expanduser().absolute()
        if source.is_file() and source.suffix.lower() in (".yaml", ".yml"):
            if labels is not None:
                raise DatasetError("a yaml says where its labels are; do not give a label folder too")
            return _from_yaml(source)
        if source.is_dir():
            return _from_folder(source, Path(labels).expanduser().absolute() if labels else None)
        raise DatasetError(f"not a dataset yaml or an image folder: {source}")

    @property
    def opening_key(self) -> str:
        """Tells apart the ways of opening one root: the yaml, or the folders."""
        return str(self.source) if self.labels is None else f"{self.source}|{self.labels}"

    @property
    def splits(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(e.split for e in self.images))

    def entry(self, image) -> ImageEntry:
        return self._by_path[Path(image)]

    def id_of(self, name: str) -> int | None:
        return self._ids.get(name)

    def known(self, cls_id: int) -> bool:
        """Whether a label may use `cls_id`; any id >= 0 when the names are unknown."""
        return cls_id >= 0 and (not self.names or cls_id < len(self.names))


def _from_yaml(path: Path) -> Dataset:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
        raise DatasetError(f"cannot read {path.name}: {e}") from e
    if not isinstance(data, dict):
        raise DatasetError(f"{path.name} is not a dataset yaml")
    base = Path(str(data["path"])).expanduser() if data.get("path") else path.parent
    if not base.is_absolute():
        base = path.parent / base
    names = _names(data, path.name)
    found: list[tuple[str, Path]] = []
    missing: list[Path] = []
    for split in SPLITS:
        listed = data.get(split)
        if not listed:
            continue
        files: list[str] = []
        for item in listed if isinstance(listed, list) else [listed]:
            where = (base / str(item)).resolve()
            got = _list_images(where)
            if got is None:
                missing.append(where)
            else:
                files += got
        found += [(split, Path(f)) for f in sorted(files)]
    if not found:
        raise DatasetError(f"{path.name} lists no images")
    return _build(path, None, base.resolve(), names, _groups(data), found, missing,
                  training_label_path)


def _from_folder(folder: Path, labels: Path | None) -> Dataset:
    folder = folder.resolve()
    if labels is None and "images" not in folder.parts:
        raise DatasetError(f"{folder} has no 'images' folder in its path, so where its labels "
                           "are cannot be worked out: give the label folder too")
    files = _list_images(folder) or []
    if not files:
        raise DatasetError(f"no images in {folder}")
    label_dir = labels or training_label_path(folder / "_.jpg").parent
    if labels:
        def label_of(image: Path) -> Path:
            return folder_label_path(image, labels)
    else:
        label_of = training_label_path
    found = [(FOLDER_SPLIT, Path(f)) for f in sorted(files)]
    return _build(folder, labels, folder, _classes_txt(label_dir / "classes.txt"), {}, found, [],
                  label_of)


def _list_images(where: Path) -> list[str] | None:
    """Image files under a folder (recursively) or in a list file; None if neither exists."""
    if where.is_dir():
        files = glob.glob(os.path.join(glob.escape(str(where)), "**", "*.*"), recursive=True)
    elif where.is_file():
        files = []
        for line in where.read_text(encoding="utf-8").strip().splitlines():
            line = line.strip()
            if line.startswith("./"):
                line = str(where.parent) + os.sep + line[2:]
            files.append(line if os.path.isabs(line) else str(where.parent / line))
    else:
        return None
    return [f for f in files if f.rpartition(".")[-1].lower() in IMG_FORMATS]


def _names(data: dict, label: str) -> tuple[str, ...]:
    names = data.get("names")
    if isinstance(names, list):
        return tuple(str(n) for n in names)
    if isinstance(names, dict):
        try:
            by_id = {int(k): str(v) for k, v in names.items()}
        except (TypeError, ValueError) as e:
            raise DatasetError(f"{label}: a key under names is not a class id") from e
        return tuple(by_id.get(i, f"class_{i}") for i in range(max(by_id, default=-1) + 1))
    nc = data.get("nc")
    if isinstance(nc, int) and nc > 0:
        return tuple(f"class_{i}" for i in range(nc))
    raise DatasetError(f"{label} has neither names nor nc")


def _groups(data: dict) -> dict[str, tuple[str, ...]]:
    groups = data.get("groups")
    if not isinstance(groups, dict):
        return {}
    return {str(g): tuple(str(m) for m in members)
            for g, members in groups.items() if isinstance(members, list)}


def _classes_txt(path: Path) -> tuple[str, ...]:
    if not path.is_file():
        return ()
    return tuple(n.strip() for n in path.read_text(encoding="utf-8").splitlines() if n.strip())


def _build(source: Path, labels: Path | None, root: Path, names: tuple[str, ...],
           groups: dict[str, tuple[str, ...]], found: list[tuple[str, Path]],
           missing: list[Path], label_of: Callable[[Path], Path]) -> Dataset:
    entries: list[ImageEntry] = []
    by_path: dict[Path, ImageEntry] = {}
    users: dict[Path, int] = {}
    for split, image in found:
        if image in by_path:
            continue
        label = label_of(image)
        try:
            rel = image.relative_to(root).as_posix()
        except ValueError:
            rel = str(image)
        entry = ImageEntry(image, label, split, rel, len(entries))
        entries.append(entry)
        by_path[image] = entry
        users[label] = users.get(label, 0) + 1
    ids: dict[str, int] = {}
    for i, name in enumerate(names):
        ids.setdefault(name, i)
    return Dataset(source, labels, root, tuple(names), groups, tuple(entries),
                   frozenset(p for p, n in users.items() if n > 1), tuple(missing), by_path, ids)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_paths.py tests/core/test_dataset.py tests/core/test_real_datasets.py -q`
Expected: all pass. The real-dataset test runs here, since pvn-vehicle is present, and takes about a second.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings`
Expected: all pass.

```bash
git add src/deeplabeling/core/paths.py src/deeplabeling/core/dataset.py tests/core/test_paths.py tests/core/test_dataset.py tests/core/test_real_datasets.py
git commit -m "core: datasets found the way training finds them" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Intents, edits and `materialize`

Read the `label-file-safety` skill first.

**Files:**
- Create: `src/deeplabeling/core/edits.py`
- Test: `tests/core/test_edits.py`

**Interfaces:**
- Consumes: from `deeplabeling.core.labelio`, `Box`, `LabelLine`, `format_box`, `locate_line`, `parse_label_bytes` and `render_label_bytes`.
- Produces in `deeplabeling.core.edits`:
  - `Refused(Exception)`, whose message is for the user;
  - `LineRef(index: int, cls_id: int, bbox: Box)`, built with `LineRef.of(lines, index)`;
  - the operations `AddBox(cls_id, bbox)`, `SetBox(ref, bbox)`, `SetClass(ref, cls_id)`, `DeleteLine(ref)` and `CreateEmpty()`, together typed as `Op`;
  - `Intent(image: Path, ops: tuple[Op, ...], description: str)`;
  - `FileChange(path: Path, before: bytes | None, after: bytes | None)`, with `.nbytes`;
  - `Edit(changes: tuple[FileChange, ...], images: tuple[Path, ...], description: str)`, with `.nbytes`;
  - `materialize(before: bytes | None, ops, *, class_ok: Callable[[int], bool]) -> bytes`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_edits.py`:

```python
import math
from pathlib import Path

import pytest

from deeplabeling.core.edits import (
    AddBox,
    CreateEmpty,
    DeleteLine,
    Edit,
    FileChange,
    LineRef,
    Refused,
    SetBox,
    SetClass,
    materialize,
)
from deeplabeling.core.labelio import parse_label_bytes
from fixtures import CRLF, GAUNTLET, POLY1

TWO = b"0 0.5 0.5 0.2 0.2\n1 0.3 0.3 0.1 0.1\n"
NEW = (0.1, 0.1, 0.1, 0.1)
NEW_LINE = b"3 0.100000 0.100000 0.100000 0.100000"


def ref(data: bytes, index: int) -> LineRef:
    return LineRef.of(parse_label_bytes(data), index)


def run(before, *ops):
    return materialize(before, ops, class_ok=lambda c: c < 4)


def test_adding_to_a_missing_file_creates_one_line():
    assert run(None, AddBox(3, NEW)) == NEW_LINE + b"\n"


def test_adding_to_an_empty_file():
    assert run(b"", AddBox(3, NEW)) == NEW_LINE + b"\n"


def test_adding_appends_and_keeps_every_other_byte():
    assert run(TWO, AddBox(3, NEW)) == TWO + NEW_LINE + b"\n"


def test_adding_gives_an_unterminated_last_line_its_newline_first():
    assert run(b"0 0.5 0.5 0.2 0.2", AddBox(3, NEW)) == b"0 0.5 0.5 0.2 0.2\n" + NEW_LINE + b"\n"


def test_adding_to_a_crlf_file_uses_crlf():
    assert run(CRLF.encode(), AddBox(3, NEW)) == CRLF.encode() + NEW_LINE + b"\r\n"


def test_a_class_change_splices_and_keeps_crlf():
    data = CRLF.encode()
    assert run(data, SetClass(ref(data, 1), 3)) == data.replace(b"\n1 0.3", b"\n3 0.3")


def test_a_class_change_keeps_a_polygons_points():
    data = POLY1.encode()
    assert run(data, SetClass(ref(data, 0), 2)) == b"2" + data[1:]


def test_a_new_box_rewrites_only_that_line():
    assert run(TWO, SetBox(ref(TWO, 1), (0.4, 0.4, 0.2, 0.2))) == (
        b"0 0.5 0.5 0.2 0.2\n1 0.400000 0.400000 0.200000 0.200000\n")


def test_setting_the_same_box_or_class_changes_nothing():
    assert run(TWO, SetBox(ref(TWO, 0), (0.5, 0.5, 0.2, 0.2))) == TWO
    assert run(TWO, SetClass(ref(TWO, 0), 0)) == TWO


def test_moving_a_polygon_is_refused():
    data = POLY1.encode()
    with pytest.raises(Refused, match="polygon"):
        run(data, SetBox(ref(data, 0), (0.5, 0.5, 0.1, 0.1)))


def test_deleting_a_middle_line_keeps_the_others():
    three = TWO + b"2 0.7 0.7 0.1 0.1\n"
    assert run(three, DeleteLine(ref(three, 1))) == b"0 0.5 0.5 0.2 0.2\n2 0.7 0.7 0.1 0.1\n"


def test_deleting_the_only_box_leaves_zero_bytes():
    data = b"0 0.5 0.5 0.2 0.2\n"
    assert run(data, DeleteLine(ref(data, 0))) == b""


def test_deleting_every_box_keeps_unparsable_lines():
    data = b"0 0.5 0.5 0.2 0.2\n# note\n"
    assert run(data, DeleteLine(ref(data, 0))) == b"# note\n"


def test_a_stale_index_still_finds_the_line():
    assert run(TWO, DeleteLine(LineRef(0, 1, (0.3, 0.3, 0.1, 0.1)))) == b"0 0.5 0.5 0.2 0.2\n"


def test_a_box_that_is_gone_is_refused():
    with pytest.raises(Refused):
        run(TWO, DeleteLine(LineRef(1, 1, (0.9, 0.9, 0.1, 0.1))))


def test_identical_lines_need_a_correct_index():
    data = GAUNTLET.encode()
    with pytest.raises(Refused):
        run(data, DeleteLine(LineRef(0, 0, (0.5, 0.5, 0.2, 0.2))))
    kept = GAUNTLET.splitlines(keepends=True)
    del kept[6]
    assert run(data, DeleteLine(LineRef(6, 0, (0.5, 0.5, 0.2, 0.2)))) == "".join(kept).encode()


def test_two_changes_to_one_box_are_refused():
    r = ref(TWO, 0)
    with pytest.raises(Refused, match="same box"):
        run(TWO, SetClass(r, 2), DeleteLine(r))


def test_one_intent_can_delete_reclassify_and_add():
    out = run(TWO, DeleteLine(ref(TWO, 0)), SetClass(ref(TWO, 1), 2), AddBox(3, NEW))
    assert out == b"2 0.3 0.3 0.1 0.1\n" + NEW_LINE + b"\n"


def test_marking_negative_creates_an_empty_file():
    assert run(None, CreateEmpty()) == b""


def test_marking_negative_needs_a_missing_file_and_nothing_else():
    with pytest.raises(Refused):
        run(b"", CreateEmpty())
    with pytest.raises(Refused):
        run(None, CreateEmpty(), AddBox(3, NEW))


@pytest.mark.parametrize("op", [AddBox(4, NEW), AddBox(-1, NEW), AddBox(True, NEW)])
def test_a_class_the_dataset_does_not_have_is_refused(op):
    with pytest.raises(Refused, match="class"):
        run(TWO, op)


def test_reclassifying_to_an_unknown_class_is_refused():
    with pytest.raises(Refused, match="class"):
        run(TWO, SetClass(ref(TWO, 0), 9))


@pytest.mark.parametrize("bbox", [
    (0.5, 0.5, 0.0, 0.1), (0.95, 0.5, 0.2, 0.2), (math.nan, 0.5, 0.1, 0.1), (0.5, 0.5, -0.1, 0.1),
])
def test_an_empty_or_outside_box_is_refused(bbox):
    with pytest.raises(Refused, match="box"):
        run(TWO, AddBox(0, bbox))


def test_bytes_that_are_not_utf8_survive_an_edit_elsewhere():
    data = b"0 0.5 0.5 0.2 0.2\n\xff\xfe junk\n"
    assert run(data, DeleteLine(ref(data, 0))) == b"\xff\xfe junk\n"


def test_a_class_change_in_the_gauntlet_touches_one_line():
    data = GAUNTLET.encode()
    assert run(data, SetClass(ref(data, 0), 2)) == b"2" + data[1:]


def test_nothing_to_do_is_refused():
    with pytest.raises(Refused):
        run(TWO)


def test_an_edit_counts_its_bytes():
    edit = Edit((FileChange(Path("a.txt"), None, b"abc"), FileChange(Path("b.txt"), b"xy", b"")), (), "x")
    assert edit.nbytes == 5
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_edits.py -q`
Expected: `ModuleNotFoundError: No module named 'deeplabeling.core.edits'`.

- [ ] **Step 3: Write `edits.py`**

Create `src/deeplabeling/core/edits.py`:

```python
"""Edits to label files (docs/design/2026-10-04-app-foundation.md#edits).

An Intent is what the user asked for: operations on one image's lines. An Edit is
what was done: each file's bytes before and after, which is all undo needs.
`materialize` turns operations into new bytes against the file as it is now. It
locates every line by class and box first, so an intent built from an older
snapshot either reaches the right line or is refused
(docs/knowledge/label-files.md#locate-before-writing).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from .labelio import Box, LabelLine, format_box, locate_line, parse_label_bytes, render_label_bytes


class Refused(Exception):
    """An edit or undo that would be wrong, so it was not done. The message is for the user."""


@dataclass(frozen=True)
class LineRef:
    """Where a box was: its line index (only a hint), its class and its normalised box."""

    index: int
    cls_id: int
    bbox: Box

    @classmethod
    def of(cls, lines: Sequence[LabelLine], index: int) -> LineRef:
        line = lines[index]
        return cls(index, line.cls_id, line.bbox)


@dataclass(frozen=True)
class AddBox:
    cls_id: int
    bbox: Box


@dataclass(frozen=True)
class SetBox:
    ref: LineRef
    bbox: Box


@dataclass(frozen=True)
class SetClass:
    ref: LineRef
    cls_id: int


@dataclass(frozen=True)
class DeleteLine:
    ref: LineRef


@dataclass(frozen=True)
class CreateEmpty:
    """Create an empty label file on an image that has none: an explicit negative sample."""


Op = Union[AddBox, SetBox, SetClass, DeleteLine, CreateEmpty]


@dataclass(frozen=True)
class Intent:
    image: Path
    ops: tuple[Op, ...]
    description: str


@dataclass(frozen=True)
class FileChange:
    path: Path
    before: bytes | None    #: None: the file did not exist
    after: bytes | None

    @property
    def nbytes(self) -> int:
        return len(self.before or b"") + len(self.after or b"")


@dataclass(frozen=True)
class Edit:
    changes: tuple[FileChange, ...]
    images: tuple[Path, ...]
    description: str

    @property
    def nbytes(self) -> int:
        return sum(change.nbytes for change in self.changes)


def materialize(before: bytes | None, ops: Sequence[Op], *,
                class_ok: Callable[[int], bool]) -> bytes:
    """The file's new bytes once `ops` are applied to `before`. Refuses rather than guesses."""
    if not ops:
        raise Refused("there is nothing to change")
    if any(isinstance(op, CreateEmpty) for op in ops):
        if len(ops) > 1:
            raise Refused("marking an image negative cannot be combined with other edits")
        if before is not None:
            raise Refused("this image already has a label file")
        return b""
    lines = list(parse_label_bytes(before or b""))
    targets: dict[int, Op] = {}
    added: list[AddBox] = []
    for op in ops:
        if isinstance(op, AddBox):
            _check_class(op.cls_id, class_ok)
            _check_box(op.bbox)
            added.append(op)
            continue
        index = locate_line(lines, op.ref.cls_id, op.ref.bbox, op.ref.index)
        if index is None:
            raise Refused(f"a class-{op.ref.cls_id} box changed in the file since it was shown, "
                          "or more than one line matches it; nothing was written")
        if index in targets:
            raise Refused("two changes were aimed at the same box")
        if isinstance(op, SetBox):
            if lines[index].is_polygon:
                raise Refused("a polygon cannot be moved or resized here; reclassify or delete it")
            _check_box(op.bbox)
        elif isinstance(op, SetClass):
            _check_class(op.cls_id, class_ok)
        targets[index] = op
    out: list[LabelLine] = []
    for index, line in enumerate(lines):
        op = targets.get(index)
        if op is None:
            out.append(line)
        elif isinstance(op, SetClass):
            out.append(line if op.cls_id == line.cls_id else line.with_class(op.cls_id))
        elif isinstance(op, SetBox):
            out.append(line if _same_box(line.bbox, op.bbox) else line.with_bbox(op.bbox))
        # a DeleteLine target is simply left out
    if added:
        ending = _line_ending(out)
        if out and not out[-1].terminator:
            last = out[-1]
            out[-1] = LabelLine(last.cls_id, last.coords, last.raw + ending)
        out += [format_box(op.cls_id, op.bbox, ending) for op in added]
    return render_label_bytes(out)


def _line_ending(lines: Sequence[LabelLine]) -> str:
    """CRLF when the file's last line ending is CRLF, else LF."""
    for line in reversed(lines):
        if line.terminator:
            return "\r\n" if line.terminator == "\r\n" else "\n"
    return "\n"


def _same_box(a: Box, b: Box) -> bool:
    return all(abs(x - y) <= 1e-9 for x, y in zip(a, b))


def _check_class(cls_id, class_ok: Callable[[int], bool]) -> None:
    if (not isinstance(cls_id, int) or isinstance(cls_id, bool)
            or cls_id < 0 or not class_ok(cls_id)):
        raise Refused(f"class {cls_id} is not one of this dataset's classes")


def _check_box(bbox: Box) -> None:
    cx, cy, w, h = bbox
    tol = 1e-9
    if (not all(math.isfinite(v) for v in bbox) or w <= 0 or h <= 0
            or cx - w / 2 < -tol or cy - h / 2 < -tol
            or cx + w / 2 > 1 + tol or cy + h / 2 > 1 + tol):
        raise Refused(f"the box {bbox} is empty or outside the image")
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_edits.py -q`
Expected: all pass.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings`
Expected: all pass.

```bash
git add src/deeplabeling/core/edits.py tests/core/test_edits.py
git commit -m "core: edits located by class and box, materialized to bytes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The label store

Read the `label-file-safety` skill first.

**Files:**
- Create: `src/deeplabeling/core/store.py`
- Test: `tests/core/test_store.py`

**Interfaces:**
- Consumes:
  - `write_atomic` (Task 1) and `parse_label_bytes` (Task 1);
  - `Dataset` and `ImageEntry` (Task 3);
  - `Edit`, `FileChange`, `Intent`, `LineRef`, `Refused` and `materialize` (Task 4).
- Produces in `deeplabeling.core.store`:
  - `Stamp = tuple[int, int, int]`, holding `(inode, mtime_ns, size)`;
  - `LabelState`, with the values `MISSING`, `OK`, `SHARED` and `ERROR`;
  - `ImageLabels(image, label_path, state, raw=None, lines=(), stamp=None, error="")`, frozen, with `.editable`, `.boxes -> tuple[tuple[int, LabelLine], ...]`, `.unparsed`, `.negative` and `.ref(index) -> LineRef`;
  - `LabelStore(dataset, *, cache_bytes=256 * 2**20, on_reload: Callable[[Path], None] | None = None)`.
    - `.dataset` is the dataset it serves.
    - `.get(image) -> ImageLabels` may be called from any thread.
    - Cache helpers: `.pin(image | None)`, `.cached_bytes`, `.cached_count` and `.is_cached(image)`.
    - Writes, on the owner thread only: `.apply(intent) -> Edit | None` and `.restore(edit, *, undo: bool) -> None`. Both raise `Refused`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_store.py`:

```python
import os
import threading

import pytest

from deeplabeling.core import store as store_module
from deeplabeling.core.atomic import write_atomic
from deeplabeling.core.dataset import Dataset
from deeplabeling.core.edits import (
    AddBox,
    CreateEmpty,
    DeleteLine,
    Edit,
    FileChange,
    Intent,
    Refused,
    SetClass,
)
from deeplabeling.core.store import LabelState, LabelStore
from fixtures import CAMA_0001, CRLF, GAUNTLET, assert_only_changed, make_image, read_exact

BOX = (0.5, 0.5, 0.2, 0.2)


@pytest.fixture
def store(ds):
    return LabelStore(Dataset.open(ds.yaml))


def intent(image, *ops):
    return Intent(image, ops, "test")


def test_an_existing_label_file(store, ds):
    snap = store.get(ds.img("camA/0001.jpg"))
    assert snap.state is LabelState.OK and snap.raw == CAMA_0001.encode()
    assert [i for i, _ in snap.boxes] == [0, 1]
    assert snap.editable and not snap.negative and snap.unparsed == 0


def test_an_empty_label_file_is_a_negative_sample(store, ds):
    snap = store.get(ds.img("camA/0002.jpg"))
    assert snap.state is LabelState.OK and snap.negative and snap.editable


def test_no_label_file_is_missing(store, ds):
    snap = store.get(ds.img("camA/0003.jpg"))
    assert snap.state is LabelState.MISSING and snap.raw is None
    assert snap.editable and not snap.negative


def test_twin_images_share_a_read_only_label_file(store, ds):
    for name in ("camB/twin.jpg", "camB/twin.png"):
        snap = store.get(ds.img(name))
        assert snap.state is LabelState.SHARED and not snap.editable
        assert len(snap.boxes) == 1 and "another image" in snap.error


def test_an_unreadable_label_file_is_an_error(store, ds):
    ds.lbl("camA/0003").mkdir()
    snap = store.get(ds.img("camA/0003.jpg"))
    assert snap.state is LabelState.ERROR and not snap.editable
    assert "cannot read" in snap.error


def test_an_unchanged_file_comes_from_the_cache(store, ds):
    img = ds.img("camA/0001.jpg")
    assert store.get(img) is store.get(img)


def test_an_outside_change_is_seen_and_reported(ds):
    seen = []
    store = LabelStore(Dataset.open(ds.yaml), on_reload=seen.append)
    img = ds.img("camA/0001.jpg")
    store.get(img)
    ds.lbl("camA/0001").write_bytes(b"3 0.5 0.5 0.1 0.1\n")
    assert store.get(img).raw == b"3 0.5 0.5 0.1 0.1\n"
    assert seen == [img]


def test_a_same_size_change_in_place_is_seen(store, ds):
    img, path = ds.img("camA/0001.jpg"), ds.lbl("camA/0001")
    store.get(img)
    st = os.stat(path)
    path.write_bytes(CAMA_0001.replace("1 0.25", "3 0.25").encode())
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    assert store.get(img).lines[1].cls_id == 3


def test_a_replaced_file_with_the_same_size_and_time_is_seen(store, ds):
    img, path = ds.img("camA/0001.jpg"), ds.lbl("camA/0001")
    store.get(img)
    st = os.stat(path)
    write_atomic(path, CAMA_0001.replace("1 0.25", "3 0.25").encode())
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert store.get(img).lines[1].cls_id == 3


def test_an_outside_deletion_is_seen_and_reported(ds):
    seen = []
    store = LabelStore(Dataset.open(ds.yaml), on_reload=seen.append)
    img = ds.img("camA/0001.jpg")
    store.get(img)
    ds.lbl("camA/0001").unlink()
    assert store.get(img).state is LabelState.MISSING
    assert seen == [img]


def test_adding_a_box_creates_the_file_and_nothing_else(store, ds):
    before = ds.snapshot()
    img = ds.img("camA/0003.jpg")
    edit = store.apply(intent(img, AddBox(1, BOX)))
    assert_only_changed(before, ds.snapshot(), {"camA/labels/0003.txt"})
    assert edit.changes == (
        FileChange(ds.lbl("camA/0003"), None, b"1 0.500000 0.500000 0.200000 0.200000\n"),)
    assert edit.images == (img,) and edit.description == "test"
    assert store.get(img).state is LabelState.OK


def test_a_missing_labels_folder_is_created(ds):
    make_image(ds.img("camA/fresh/0009.jpg"))
    store = LabelStore(Dataset.open(ds.yaml))
    store.apply(intent(ds.img("camA/fresh/0009.jpg"), AddBox(0, BOX)))
    assert ds.lbl("camA/fresh/0009").is_file()


def test_a_class_change_keeps_crlf_and_every_untouched_byte(store, ds):
    img = ds.img("crlf/c.jpg")
    store.apply(intent(img, SetClass(store.get(img).ref(0), 2)))
    assert read_exact(ds.lbl("crlf/c")) == "2" + CRLF[1:]


def test_a_shared_file_is_refused_and_nothing_is_written(store, ds):
    before = ds.snapshot()
    with pytest.raises(Refused, match="another image"):
        store.apply(intent(ds.img("camB/twin.jpg"), AddBox(0, BOX)))
    assert_only_changed(before, ds.snapshot(), set())


def test_an_unreadable_file_is_refused(store, ds):
    ds.lbl("camA/0003").mkdir()
    with pytest.raises(Refused, match="cannot read"):
        store.apply(intent(ds.img("camA/0003.jpg"), AddBox(0, BOX)))


def test_apply_refuses_a_box_that_changed_outside(store, ds):
    img = ds.img("camA/0001.jpg")
    ref = store.get(img).ref(1)
    ds.lbl("camA/0001").write_bytes(b"0 0.500000 0.500000 0.200000 0.300000\n")
    before = ds.snapshot()
    with pytest.raises(Refused):
        store.apply(intent(img, DeleteLine(ref)))
    assert_only_changed(before, ds.snapshot(), set())


def test_an_edit_that_changes_nothing_writes_nothing(store, ds):
    img, path = ds.img("camA/0001.jpg"), ds.lbl("camA/0001")
    mtime = os.stat(path).st_mtime_ns
    assert store.apply(intent(img, SetClass(store.get(img).ref(0), 0))) is None
    assert os.stat(path).st_mtime_ns == mtime


def test_a_failed_write_is_refused_and_leaves_the_file(store, ds, monkeypatch):
    img = ds.img("camA/0001.jpg")
    store.get(img)

    def full_disk(path, data):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(store_module, "write_atomic", full_disk)
    with pytest.raises(Refused, match="No space"):
        store.apply(intent(img, AddBox(0, BOX)))
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001
    assert store.get(img).raw == CAMA_0001.encode()


def test_writing_from_another_thread_is_an_error(store, ds):
    errors = []

    def write():
        try:
            store.apply(intent(ds.img("camA/0003.jpg"), AddBox(0, BOX)))
        except RuntimeError as e:
            errors.append(e)

    thread = threading.Thread(target=write)
    thread.start()
    thread.join()
    assert len(errors) == 1 and not ds.lbl("camA/0003").exists()


def test_reading_from_many_threads_agrees(ds):
    store = LabelStore(Dataset.open(ds.yaml), cache_bytes=1)   # forces real loads
    images = [e.path for e in store.dataset.images]
    expected = {img: store.get(img).raw for img in images}
    mismatches = []

    def read():
        for img in images * 20:
            if store.get(img).raw != expected[img]:
                mismatches.append(img)

    threads = [threading.Thread(target=read) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert mismatches == []


def test_undo_and_redo_are_byte_exact(store, ds):
    img, path = ds.img("bad/ok.jpg"), ds.lbl("bad/ok")
    edit = store.apply(intent(img, SetClass(store.get(img).ref(0), 2)))
    store.restore(edit, undo=True)
    assert read_exact(path) == GAUNTLET
    store.restore(edit, undo=False)
    assert read_exact(path) == "2" + GAUNTLET[1:]


def test_undoing_a_created_file_deletes_it(store, ds):
    img = ds.img("camA/0003.jpg")
    edit = store.apply(intent(img, AddBox(0, BOX)))
    store.restore(edit, undo=True)
    assert not ds.lbl("camA/0003").exists()
    assert store.get(img).state is LabelState.MISSING


def test_undoing_mark_negative_deletes_the_empty_file(store, ds):
    img = ds.img("camA/0003.jpg")
    edit = store.apply(intent(img, CreateEmpty()))
    assert ds.lbl("camA/0003").read_bytes() == b""
    store.restore(edit, undo=True)
    assert not ds.lbl("camA/0003").exists()


def test_restore_refuses_a_file_changed_since(store, ds):
    img, path = ds.img("camA/0001.jpg"), ds.lbl("camA/0001")
    edit = store.apply(intent(img, AddBox(0, BOX)))
    path.write_bytes(b"outside\n")
    with pytest.raises(Refused, match="changed since"):
        store.restore(edit, undo=True)
    assert path.read_bytes() == b"outside\n"


def test_restore_checks_every_file_before_writing_any(store, ds):
    a, b = ds.lbl("camA/0001"), ds.lbl("camB/0001")
    edit = Edit((FileChange(a, b"x\n", a.read_bytes()), FileChange(b, b"y\n", b"not there\n")),
                (ds.img("camA/0001.jpg"), ds.img("camB/0001.jpg")), "two files")
    before = ds.snapshot()
    with pytest.raises(Refused):
        store.restore(edit, undo=True)
    assert_only_changed(before, ds.snapshot(), set())


def test_the_cache_stays_within_its_budget(ds):
    store = LabelStore(Dataset.open(ds.yaml), cache_bytes=5000)
    for entry in store.dataset.images:
        store.get(entry.path)
    assert store.cached_bytes <= 5000
    assert store.cached_count < len(store.dataset.images)


def test_the_pinned_image_is_never_evicted(ds):
    store = LabelStore(Dataset.open(ds.yaml), cache_bytes=1)
    pinned = ds.img("camA/0001.jpg")
    store.pin(pinned)
    store.get(pinned)
    for entry in store.dataset.images:
        store.get(entry.path)
    assert store.is_cached(pinned)
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_store.py -q`
Expected: `ModuleNotFoundError: No module named 'deeplabeling.core.store'`.

- [ ] **Step 3: Write `store.py`**

Create `src/deeplabeling/core/store.py`:

```python
"""The one owner of every image's labels in memory
(docs/design/2026-10-04-app-foundation.md#label-document-model).

`get` may be called from any thread. `apply` and `restore` write files and run
only on the thread that created the store: the GUI thread.
"""

from __future__ import annotations

import enum
import os
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .atomic import write_atomic
from .dataset import Dataset, ImageEntry
from .edits import Edit, FileChange, Intent, LineRef, Refused, materialize
from .labelio import LabelLine, parse_label_bytes

#: (inode, mtime_ns, size). An atomic replace changes the inode, and a class
#: change keeps the size, so all three are compared.
Stamp = tuple[int, int, int]

_SHARED = "another image uses the same label file, so it is not edited here"


class LabelState(enum.Enum):
    MISSING = "missing"     #: no label file: not labelled yet
    OK = "ok"
    SHARED = "shared"       #: another image resolves to the same file; read-only
    ERROR = "error"         #: the file cannot be read; read-only


@dataclass(frozen=True)
class ImageLabels:
    image: Path
    label_path: Path
    state: LabelState
    raw: bytes | None = None
    lines: tuple[LabelLine, ...] = ()
    stamp: Stamp | None = None
    error: str = ""

    @property
    def editable(self) -> bool:
        return self.state in (LabelState.MISSING, LabelState.OK)

    @property
    def boxes(self) -> tuple[tuple[int, LabelLine], ...]:
        """(line index, line) for every parsed line."""
        return tuple((i, line) for i, line in enumerate(self.lines) if line.parsed)

    @property
    def unparsed(self) -> int:
        return sum(1 for line in self.lines if not line.parsed)

    @property
    def negative(self) -> bool:
        """A label file with no box in it: a negative sample."""
        return self.raw is not None and not self.boxes

    def ref(self, index: int) -> LineRef:
        return LineRef.of(self.lines, index)


def _cost(snap: ImageLabels) -> int:
    """Roughly the bytes a cached snapshot holds."""
    return 400 + len(snap.raw or b"") + 200 * len(snap.lines)


def _error(entry: ImageEntry, e: OSError) -> ImageLabels:
    return ImageLabels(entry.path, entry.label_path, LabelState.ERROR,
                       error=f"cannot read {entry.label_path.name}: {e.strerror or e}")


def _read_or_none(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise Refused(f"cannot read {path.name}: {e.strerror or e}") from e


class LabelStore:
    def __init__(self, dataset: Dataset, *, cache_bytes: int = 256 * 2**20,
                 on_reload: Callable[[Path], None] | None = None):
        self.dataset = dataset
        self._limit = cache_bytes
        self._on_reload = on_reload or (lambda image: None)
        self._lock = threading.Lock()
        self._cache: OrderedDict[Path, ImageLabels] = OrderedDict()
        self._costs: dict[Path, int] = {}
        self._total = 0
        self._pinned: Path | None = None
        self._owner = threading.get_ident()

    # -- reading, from any thread ------------------------------------------

    def get(self, image) -> ImageLabels:
        """The image's labels as its file is now.

        Every call stats the file; a changed stamp means a reload, and replacing a
        cached copy is reported to `on_reload`, on the calling thread.
        """
        return self._load(self.dataset.entry(image), notify=True)

    def pin(self, image) -> None:
        """Keep this image cached whatever the budget: the image on screen."""
        with self._lock:
            self._pinned = Path(image) if image is not None else None

    @property
    def cached_bytes(self) -> int:
        return self._total

    @property
    def cached_count(self) -> int:
        return len(self._cache)

    def is_cached(self, image) -> bool:
        with self._lock:
            return Path(image) in self._cache

    def _load(self, entry: ImageEntry, *, notify: bool) -> ImageLabels:
        shared = entry.label_path in self.dataset.shared_labels
        try:
            st = os.stat(entry.label_path)
        except FileNotFoundError:
            dropped = self._drop(entry.path)
            if notify and dropped is not None:
                self._on_reload(entry.path)
            return ImageLabels(entry.path, entry.label_path,
                               LabelState.SHARED if shared else LabelState.MISSING,
                               error=_SHARED if shared else "")
        except OSError as e:
            return _error(entry, e)
        # The stamp is taken BEFORE the bytes are read: a change in between leaves
        # a stamp older than the bytes, so the next call reloads again -- safe --
        # instead of trusting stale bytes under a new stamp.
        stamp = (st.st_ino, st.st_mtime_ns, st.st_size)
        with self._lock:
            cached = self._cache.get(entry.path)
            if cached is not None and cached.stamp == stamp:
                self._cache.move_to_end(entry.path)
                return cached
        try:
            raw = entry.label_path.read_bytes()
        except OSError as e:
            return _error(entry, e)
        snap = ImageLabels(entry.path, entry.label_path,
                           LabelState.SHARED if shared else LabelState.OK,
                           raw, parse_label_bytes(raw), stamp, _SHARED if shared else "")
        self._remember(snap)
        if notify and cached is not None and cached.raw != raw:
            self._on_reload(entry.path)
        return snap

    def _remember(self, snap: ImageLabels) -> None:
        cost = _cost(snap)
        with self._lock:
            if snap.image in self._cache:
                del self._cache[snap.image]
                self._total -= self._costs.pop(snap.image)
            self._cache[snap.image] = snap
            self._costs[snap.image] = cost
            self._total += cost
            for victim in list(self._cache):
                if self._total <= self._limit:
                    break
                if victim in (self._pinned, snap.image):
                    continue
                del self._cache[victim]
                self._total -= self._costs.pop(victim)

    def _drop(self, image: Path) -> ImageLabels | None:
        with self._lock:
            snap = self._cache.pop(image, None)
            if snap is not None:
                self._total -= self._costs.pop(image)
            return snap

    # -- writing, on the owner thread --------------------------------------

    def apply(self, intent: Intent) -> Edit | None:
        """Write `intent` to the image's label file. None when it changes nothing."""
        self._check_thread()
        snap = self.get(intent.image)
        if not snap.editable:
            raise Refused(snap.error or f"{snap.label_path.name} cannot be edited")
        after = materialize(snap.raw, intent.ops, class_ok=self.dataset.known)
        if after == snap.raw:
            return None
        self._write(snap.label_path, after)
        self._load(self.dataset.entry(intent.image), notify=False)
        return Edit((FileChange(snap.label_path, snap.raw, after),), (snap.image,),
                    intent.description)

    def restore(self, edit: Edit, *, undo: bool) -> None:
        """Put every file of `edit` back as it was before it (undo) or after it (redo).

        Every file is checked first. If any no longer holds what `edit` left (undo)
        or found (redo), something else changed it, and nothing at all is written.
        A file absent on the target side is deleted: only ever a file this edit
        created, and only while it still holds exactly what the edit wrote.
        """
        self._check_thread()
        for change in edit.changes:
            expected = change.after if undo else change.before
            if _read_or_none(change.path) != expected:
                raise Refused(f"{change.path.name} has changed since, so it is left as it is")
        for change in edit.changes:
            target = change.before if undo else change.after
            if target is None:
                try:
                    change.path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as e:
                    raise Refused(f"could not remove {change.path.name}: {e.strerror or e}") from e
            else:
                self._write(change.path, target)
        for image in edit.images:
            self._load(self.dataset.entry(image), notify=False)

    def _write(self, path: Path, data: bytes) -> None:
        try:
            write_atomic(path, data)
        except OSError as e:
            raise Refused(f"could not write {path.name}: {e.strerror or e}; "
                          "the file is unchanged") from e

    def _check_thread(self) -> None:
        if threading.get_ident() != self._owner:
            raise RuntimeError("label files are written only on the thread that created the store")
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_store.py -q`
Expected: all pass.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings`
Expected: all pass.

```bash
git add src/deeplabeling/core/store.py tests/core/test_store.py
git commit -m "core: the label store, the one owner of labels in memory" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: App state, settings and the real-state guard

**Files:**
- Create: `src/deeplabeling/core/state.py`, `src/deeplabeling/core/settings.py`
- Modify: `tests/conftest.py`
- Test: `tests/core/test_state.py`, `tests/core/test_settings.py`

**Interfaces:**
- Consumes: `write_atomic` (Task 1).
- Produces in `deeplabeling.core.state`:
  - `ENV = "DEEPLABELING_STATE_DIR"` and `REPO_ROOT`;
  - `state_dir() -> Path` and `dataset_state_dir(root: Path) -> Path`;
  - `Locked(Exception)`, with `.pid`;
  - `DatasetLock(directory)`, with `.path`, `.held`, `.acquire()` (raising `Locked`) and `.release()`;
  - `set_aside(path, error) -> tuple[str, bool]`, which returns a warning and whether the path may still be written.
- Produces in `deeplabeling.core.settings`:
  - `SCOPES = ("global", "root", "opening")`;
  - `Setting(key, scope, default, valid)` and the `REGISTRY` dict;
  - `define(key, scope, default, valid) -> Setting`;
  - the validators `is_str_or_none`, `is_str_list` and `is_str_map`;
  - `JsonFile(path)`, with `.data`, `.dirty`, `.warning`, `.writable` and `.save() -> bool`;
  - `Settings(file, scope, section=())`, with `.get(setting)` and `.set(setting, value)`.
- Produces: the autouse fixtures `state_dir` (the per-test temporary state folder) and `_real_state_untouched` (session-wide).

- [ ] **Step 1: Guard the real state in `tests/conftest.py`**

Replace `tests/conftest.py` with:

```python
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
```

- [ ] **Step 2: Write the failing tests**

Create `tests/core/test_state.py`:

```python
import os
import subprocess
import sys
from pathlib import Path

import pytest

from deeplabeling.core import state
from deeplabeling.core.state import DatasetLock, Locked, dataset_state_dir, set_aside, state_dir


def test_the_state_folder_comes_from_the_environment():
    assert state_dir() == Path(os.environ[state.ENV])


def test_without_the_override_it_is_the_repository_folder(monkeypatch):
    monkeypatch.delenv(state.ENV)
    assert state_dir() == Path(__file__).resolve().parents[2] / ".deeplabeling"


def test_dataset_folders_are_stable_and_distinct(tmp_path):
    a, b = tmp_path / "x" / "pvn", tmp_path / "y" / "pvn"
    assert dataset_state_dir(a) == dataset_state_dir(a)
    assert dataset_state_dir(a) != dataset_state_dir(b)
    assert dataset_state_dir(a).name.startswith("pvn-")
    assert dataset_state_dir(a).parent == state_dir() / "datasets"


def test_a_lock_holds_our_pid_until_released(tmp_path):
    lock = DatasetLock(tmp_path)
    lock.acquire()
    assert lock.path.read_text().strip() == str(os.getpid()) and lock.held
    lock.release()
    assert not lock.path.exists() and not lock.held


def test_a_lock_held_by_another_live_process_refuses(tmp_path):
    (tmp_path / "lock").write_text(f"{os.getppid()}\n")
    with pytest.raises(Locked) as caught:
        DatasetLock(tmp_path).acquire()
    assert caught.value.pid == os.getppid()
    assert "delete" in str(caught.value)


def test_a_lock_left_by_a_dead_process_is_taken_over(tmp_path):
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    (tmp_path / "lock").write_text(f"{child.pid}\n")
    lock = DatasetLock(tmp_path)
    lock.acquire()
    assert lock.path.read_text().strip() == str(os.getpid())


def test_our_own_lock_can_be_taken_again(tmp_path):
    DatasetLock(tmp_path).acquire()
    DatasetLock(tmp_path).acquire()


def test_release_leaves_someone_elses_lock(tmp_path):
    lock = DatasetLock(tmp_path)
    lock.acquire()
    lock.path.write_text(f"{os.getppid()}\n")
    lock.release()
    assert lock.path.exists()


def test_set_aside_keeps_the_unreadable_file(tmp_path):
    bad = tmp_path / "review.json"
    bad.write_bytes(b"{not json")
    warning, writable = set_aside(bad, ValueError("bad"))
    assert writable and not bad.exists()
    kept = [p for p in tmp_path.iterdir() if p.name.startswith("review.json.unreadable-")]
    assert len(kept) == 1 and kept[0].read_bytes() == b"{not json"
    assert kept[0].name in warning


def test_set_aside_that_cannot_move_forbids_writing(tmp_path, monkeypatch):
    bad = tmp_path / "review.json"
    bad.write_bytes(b"{not json")

    def cannot(src, dst):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(state.os, "replace", cannot)
    warning, writable = set_aside(bad, ValueError("bad"))
    assert not writable and bad.read_bytes() == b"{not json" and "nothing will be saved" in warning
```

Create `tests/core/test_settings.py`:

```python
import pytest

from deeplabeling.core import settings, state
from deeplabeling.core.settings import JsonFile, Settings, define, is_str_list, is_str_map


@pytest.fixture(autouse=True)
def registry(monkeypatch):
    """Each test defines its settings in an empty registry."""
    monkeypatch.setattr(settings, "REGISTRY", {})


def test_a_setting_is_defined_once():
    define("a.b", "global", 1, lambda v: isinstance(v, int))
    with pytest.raises(ValueError, match="twice"):
        define("a.b", "global", 1, lambda v: isinstance(v, int))


def test_a_definition_needs_a_valid_default_and_a_known_scope():
    with pytest.raises(ValueError):
        define("x", "global", "one", lambda v: isinstance(v, int))
    with pytest.raises(ValueError):
        define("y", "machine", 1, lambda v: True)


def test_get_gives_the_default_until_set(tmp_path):
    s = define("n", "global", 3, lambda v: isinstance(v, int))
    values = Settings(JsonFile(tmp_path / "s.json"), "global")
    assert values.get(s) == 3
    values.set(s, 5)
    assert values.get(s) == 5


def test_an_invalid_value_is_refused(tmp_path):
    s = define("n", "global", 3, lambda v: isinstance(v, int))
    with pytest.raises(ValueError):
        Settings(JsonFile(tmp_path / "s.json"), "global").set(s, "five")


def test_an_invalid_stored_value_reads_as_the_default(tmp_path):
    s = define("n", "global", 3, lambda v: isinstance(v, int))
    (tmp_path / "s.json").write_text('{"n": "hand-edited"}')
    assert Settings(JsonFile(tmp_path / "s.json"), "global").get(s) == 3


def test_a_setting_belongs_to_its_scope(tmp_path):
    s = define("n", "root", 3, lambda v: isinstance(v, int))
    with pytest.raises(ValueError, match="root"):
        Settings(JsonFile(tmp_path / "s.json"), "global").get(s)


def test_values_survive_a_save_and_reload(tmp_path):
    s = define("names", "root", [], is_str_list)
    file = JsonFile(tmp_path / "d.json")
    Settings(file, "root", ("root",)).set(s, ["car", "bus"])
    assert file.save()
    assert Settings(JsonFile(tmp_path / "d.json"), "root", ("root",)).get(s) == ["car", "bus"]


def test_sections_are_independent(tmp_path):
    s = define("cursor", "opening", None, lambda v: v is None or isinstance(v, str))
    file = JsonFile(tmp_path / "d.json")
    Settings(file, "opening", ("openings", "a.yaml")).set(s, "img1")
    assert Settings(file, "opening", ("openings", "b.yaml")).get(s) is None


def test_get_returns_a_copy(tmp_path):
    s = define("colors", "root", {}, is_str_map)
    values = Settings(JsonFile(tmp_path / "d.json"), "root")
    values.set(s, {"car": "#00ff00"})
    values.get(s)["car"] = "#ff0000"
    assert values.get(s) == {"car": "#00ff00"}


def test_setting_the_same_value_does_not_dirty_the_file(tmp_path):
    s = define("n", "global", 3, lambda v: isinstance(v, int))
    file = JsonFile(tmp_path / "s.json")
    Settings(file, "global").set(s, 3)
    assert file.dirty
    file.save()
    Settings(file, "global").set(s, 3)
    assert not file.dirty and not file.save()


@pytest.mark.parametrize("content", [b"{broken", b"[1, 2]", b"\xff\xfe"])
def test_an_unreadable_file_is_set_aside_and_defaults_apply(tmp_path, content):
    s = define("n", "global", 3, lambda v: isinstance(v, int))
    (tmp_path / "s.json").write_bytes(content)
    file = JsonFile(tmp_path / "s.json")
    assert file.warning and file.writable
    assert Settings(file, "global").get(s) == 3
    Settings(file, "global").set(s, 4)
    assert file.save()
    kept = [p for p in tmp_path.iterdir() if ".unreadable-" in p.name]
    assert len(kept) == 1 and kept[0].read_bytes() == content


def test_a_file_that_cannot_be_set_aside_is_never_overwritten(tmp_path, monkeypatch):
    s = define("n", "global", 3, lambda v: isinstance(v, int))
    (tmp_path / "s.json").write_bytes(b"{broken")

    def cannot(src, dst):
        raise OSError(13, "Permission denied")

    with monkeypatch.context() as m:
        m.setattr(state.os, "replace", cannot)
        file = JsonFile(tmp_path / "s.json")
    Settings(file, "global").set(s, 4)
    assert not file.writable and not file.save()
    assert (tmp_path / "s.json").read_bytes() == b"{broken"
```

- [ ] **Step 3: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_state.py tests/core/test_settings.py -q`
Expected: `ModuleNotFoundError` for `deeplabeling.core.state` and `.settings`.

- [ ] **Step 4: Write `state.py` and `settings.py`**

Create `src/deeplabeling/core/state.py`:

```python
"""Where DeepLabeling keeps its state (docs/knowledge/caches.md#where-app-state-lives):
one fixed folder found from this file's location, never from the launch folder."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from .atomic import write_atomic

ENV = "DEEPLABELING_STATE_DIR"

#: src/deeplabeling/core/state.py -> the repository root.
REPO_ROOT = Path(__file__).resolve().parents[3]


def state_dir() -> Path:
    override = os.environ.get(ENV)
    return Path(override) if override else REPO_ROOT / ".deeplabeling"


def dataset_state_dir(root: Path) -> Path:
    """One dataset root's folder: a readable name plus a hash of the whole root."""
    digest = hashlib.sha1(os.fsencode(str(root))).hexdigest()[:8]
    return state_dir() / "datasets" / f"{root.name or 'root'}-{digest}"


class Locked(Exception):
    def __init__(self, pid: int, path: Path):
        super().__init__(f"this dataset is open in another DeepLabeling (process {pid}); "
                         f"if none is running, delete {path}")
        self.pid = pid


class DatasetLock:
    """One DeepLabeling per dataset root: a file holding the owner's process id."""

    def __init__(self, directory: Path):
        self.path = Path(directory) / "lock"
        self.held = False

    def acquire(self) -> None:
        pid = _read_pid(self.path)
        if pid is not None and pid != os.getpid() and _alive(pid):
            raise Locked(pid, self.path)
        write_atomic(self.path, f"{os.getpid()}\n".encode())
        self.held = True

    def release(self) -> None:
        if self.held and _read_pid(self.path) == os.getpid():
            self.path.unlink(missing_ok=True)
        self.held = False


def set_aside(path: Path, error: Exception) -> tuple[str, bool]:
    """Move an unreadable state file aside so that nothing overwrites it.

    Returns the warning to show and whether `path` may be written afterwards.
    """
    aside = path.with_name(f"{path.name}.unreadable-{time.strftime('%Y%m%d-%H%M%S')}")
    try:
        os.replace(path, aside)
    except OSError:
        return (f"{path.name} could not be read ({error}) or moved aside; it is left as "
                "it is, and nothing will be saved to it", False)
    return (f"{path.name} could not be read ({error}); it was kept as {aside.name}, "
            "and its contents start empty", True)


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
```

Create `src/deeplabeling/core/settings.py`:

```python
"""Settings (docs/design/2026-10-04-app-foundation.md#state-and-settings).

Each setting is defined once -- key, scope, default, validator -- and its value is
read only through `Settings.get`, which falls back to the default for a missing or
invalid stored value. A widget seeded from `get` therefore shows the value the
logic uses (CLAUDE.md landmine 7). Values are JSON values.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atomic import write_atomic
from .state import set_aside

#: global: settings.json. root: a dataset root's dataset.json. opening: one
#: yaml's (or one folder launch's) section of that file.
SCOPES = ("global", "root", "opening")


@dataclass(frozen=True)
class Setting:
    key: str
    scope: str
    default: Any
    valid: Callable[[Any], bool]


REGISTRY: dict[str, Setting] = {}


def define(key: str, scope: str, default: Any, valid: Callable[[Any], bool]) -> Setting:
    if scope not in SCOPES:
        raise ValueError(f"unknown scope {scope!r}")
    if key in REGISTRY:
        raise ValueError(f"setting {key!r} is defined twice")
    if not valid(default):
        raise ValueError(f"the default of {key!r} is not valid: {default!r}")
    setting = Setting(key, scope, default, valid)
    REGISTRY[key] = setting
    return setting


def is_str_or_none(v) -> bool:
    return v is None or isinstance(v, str)


def is_str_list(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def is_str_map(v) -> bool:
    return isinstance(v, dict) and all(isinstance(k, str) and isinstance(x, str)
                                       for k, x in v.items())


class JsonFile:
    """A JSON object on disk, loaded once and saved atomically.

    A file that cannot be read is moved aside, never overwritten, and `warning`
    says so; its settings then start from their defaults.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict = {}
        self.dirty = False
        self.warning = ""
        self.writable = True
        try:
            data = json.loads(self.path.read_bytes())
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
            self.data = data
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            self.warning, self.writable = set_aside(self.path, e)

    def save(self) -> bool:
        if not self.dirty or not self.writable:
            return False
        write_atomic(self.path, json.dumps(self.data, indent=1, sort_keys=True).encode())
        self.dirty = False
        return True


class Settings:
    """One scope's values, kept in a section of a JsonFile."""

    def __init__(self, file: JsonFile, scope: str, section: tuple[str, ...] = ()):
        self.file = file
        self.scope = scope
        self.section = section

    def get(self, setting: Setting):
        self._check(setting)
        node = self._node(create=False)
        value = node.get(setting.key, setting.default) if node is not None else setting.default
        return copy.deepcopy(value if setting.valid(value) else setting.default)

    def set(self, setting: Setting, value) -> None:
        self._check(setting)
        if not setting.valid(value):
            raise ValueError(f"not a valid value for {setting.key}: {value!r}")
        node = self._node(create=True)
        if setting.key not in node or node[setting.key] != value:
            node[setting.key] = copy.deepcopy(value)
            self.file.dirty = True

    def _check(self, setting: Setting) -> None:
        if setting.scope != self.scope:
            raise ValueError(f"{setting.key} is a {setting.scope} setting, not a {self.scope} one")

    def _node(self, *, create: bool) -> dict | None:
        node = self.file.data
        for name in self.section:
            child = node.get(name)
            if not isinstance(child, dict):
                if not create:
                    return None
                child = node[name] = {}
            node = child
        return node
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_state.py tests/core/test_settings.py -q`
Expected: all pass.

- [ ] **Step 6: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings`
Expected: all pass, and the session-level real-state guard does not fail.

```bash
git add src/deeplabeling/core/state.py src/deeplabeling/core/settings.py tests/conftest.py tests/core/test_state.py tests/core/test_settings.py
git commit -m "core: app state folder, per-root lock, settings registry; guard real state in tests" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Review marks

**Files:**
- Create: `src/deeplabeling/core/review.py`
- Test: `tests/core/test_review.py`

**Interfaces:**
- Consumes: `write_atomic` (Task 1), `set_aside` (Task 6).
- Produces in `deeplabeling.core.review`:
  - `SCHEMA_VERSION = 1`;
  - `ReviewMarks(path, root)`, with the attributes `.marks: dict[str, int]`, `.dirty`, `.warning` and `.writable`;
  - its methods `.is_marked(rel)`, `.marked_at(rel) -> int | None`, `.mark(rel, when=None) -> bool`, `.mark_many(rels) -> int`, `.unmark(rel) -> bool`, `.toggle(rel) -> bool` (the new state), `.count() -> int`, `.keys() -> frozenset[str]` and `.save() -> bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_review.py`:

```python
import json

from deeplabeling.core import state
from deeplabeling.core.review import ReviewMarks


def marks(tmp_path):
    return ReviewMarks(tmp_path / "review.json", tmp_path / "root")


def test_marking_once_changes_things_and_twice_does_not(tmp_path):
    r = marks(tmp_path)
    assert r.mark("camA/images/0001.jpg", when=100) and r.dirty
    assert not r.mark("camA/images/0001.jpg", when=200)
    assert r.marked_at("camA/images/0001.jpg") == 100 and r.is_marked("camA/images/0001.jpg")


def test_unmark_toggle_and_count(tmp_path):
    r = marks(tmp_path)
    assert r.mark_many(["a", "b", "a"]) == 2 and r.count() == 2
    assert r.unmark("a") and not r.unmark("a")
    assert r.toggle("a") is True and r.toggle("a") is False
    assert r.count() == 1


def test_keys_is_a_snapshot(tmp_path):
    r = marks(tmp_path)
    r.mark("a")
    frozen = r.keys()
    r.mark("b")
    assert frozen == {"a"}


def test_save_writes_version_root_and_marks_and_reloads(tmp_path):
    r = marks(tmp_path)
    r.mark("camA/images/0001.jpg", when=100)
    assert r.save() and not r.dirty
    data = json.loads((tmp_path / "review.json").read_text())
    assert data == {"version": 1, "root": str(tmp_path / "root"),
                    "marks": {"camA/images/0001.jpg": 100}}
    assert marks(tmp_path).marks == {"camA/images/0001.jpg": 100}


def test_nothing_to_save_writes_nothing(tmp_path):
    assert not marks(tmp_path).save()
    assert not (tmp_path / "review.json").exists()


def test_unicode_and_undecodable_keys_round_trip(tmp_path):
    r = marks(tmp_path)
    r.mark("weird/images/имя пробел.jpg", when=1)
    r.mark("x/\udcff.jpg", when=2)
    r.save()
    assert marks(tmp_path).marks == {"weird/images/имя пробел.jpg": 1, "x/\udcff.jpg": 2}


def test_an_unreadable_file_is_kept_and_marks_start_empty(tmp_path):
    (tmp_path / "review.json").write_bytes(b"{broken")
    r = marks(tmp_path)
    assert r.marks == {} and "kept as" in r.warning
    r.mark("a")
    assert r.save()
    kept = [p for p in tmp_path.iterdir() if ".unreadable-" in p.name]
    assert len(kept) == 1 and kept[0].read_bytes() == b"{broken"


def test_a_bad_entry_is_skipped_and_said(tmp_path):
    (tmp_path / "review.json").write_text('{"version": 1, "marks": {"a": 5, "b": "soon"}}')
    r = marks(tmp_path)
    assert r.marks == {"a": 5} and "1 review mark" in r.warning


def test_a_file_that_cannot_be_set_aside_is_never_overwritten(tmp_path, monkeypatch):
    (tmp_path / "review.json").write_bytes(b"{broken")

    def cannot(src, dst):
        raise OSError(13, "Permission denied")

    with monkeypatch.context() as m:
        m.setattr(state.os, "replace", cannot)
        r = marks(tmp_path)
    r.mark("a")
    assert not r.writable and not r.save()
    assert (tmp_path / "review.json").read_bytes() == b"{broken"
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_review.py -q`
Expected: `ModuleNotFoundError: No module named 'deeplabeling.core.review'`.

- [ ] **Step 3: Write `review.py`**

Create `src/deeplabeling/core/review.py`:

```python
"""Which images have been reviewed (docs/design/2026-10-04-app-foundation.md#review-marks).

Keyed by ImageEntry.rel and saved atomically as {"version": 1, "root": ...,
"marks": {rel: unix time}}. What marks an image -- an edit, done & next, mark
page, never mere viewing -- is the caller's rule; this is only the record.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from pathlib import Path

from .atomic import write_atomic
from .state import set_aside

SCHEMA_VERSION = 1


class ReviewMarks:
    def __init__(self, path: Path, root: Path):
        self.path = Path(path)
        self.root = Path(root)
        self.marks: dict[str, int] = {}
        self.dirty = False
        self.warning = ""
        self.writable = True
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_bytes())
            stored = data["marks"]
            if not isinstance(stored, dict):
                raise TypeError("marks is not an object")
        except FileNotFoundError:
            return
        except (OSError, ValueError, KeyError, TypeError) as e:
            self.warning, self.writable = set_aside(self.path, e)
            return
        bad = 0
        for key, when in stored.items():
            try:
                self.marks[str(key)] = int(when)
            except (TypeError, ValueError):
                bad += 1
        if bad:
            self.warning = f"{bad} review mark(s) in {self.path.name} could not be read and were skipped"

    def is_marked(self, rel: str) -> bool:
        return rel in self.marks

    def marked_at(self, rel: str) -> int | None:
        return self.marks.get(rel)

    def count(self) -> int:
        return len(self.marks)

    def keys(self) -> frozenset[str]:
        """A snapshot, safe to hand to a worker thread."""
        return frozenset(self.marks)

    def mark(self, rel: str, when: int | None = None) -> bool:
        """Mark one image; False when it already was (its time is kept)."""
        if rel in self.marks:
            return False
        self.marks[rel] = int(time.time() if when is None else when)
        self.dirty = True
        return True

    def mark_many(self, rels: Iterable[str]) -> int:
        return sum(1 for rel in rels if self.mark(rel))

    def unmark(self, rel: str) -> bool:
        if rel not in self.marks:
            return False
        del self.marks[rel]
        self.dirty = True
        return True

    def toggle(self, rel: str) -> bool:
        """Flip one image; returns its new state."""
        if self.unmark(rel):
            return False
        self.mark(rel)
        return True

    def save(self) -> bool:
        if not self.dirty or not self.writable:
            return False
        payload = {"version": SCHEMA_VERSION, "root": str(self.root), "marks": self.marks}
        write_atomic(self.path, json.dumps(payload, indent=1, sort_keys=True).encode())
        self.dirty = False
        return True
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_review.py -q`
Expected: all pass.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings`
Expected: all pass.

```bash
git add src/deeplabeling/core/review.py tests/core/test_review.py
git commit -m "core: review marks that never overwrite an unreadable file" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: History and the editor

Read the `label-file-safety` skill first.

**Files:**
- Create: `src/deeplabeling/core/history.py`, `src/deeplabeling/core/editor.py`
- Test: `tests/core/test_history.py`

**Interfaces:**
- Consumes: `Edit`, `Intent` and `Refused` (Task 4); `LabelStore` (Task 5); `ReviewMarks` (Task 7).
- Produces: `deeplabeling.core.history.History(store, *, cap_bytes=64 * 2**20)`, with `.push(edit)`, `.undo() -> Edit | None`, `.redo() -> Edit | None` (both raising `Refused`, after dropping the refused edit), `.can_undo`, `.can_redo`, `.depth`, `.peek_undo()` and `.peek_redo()`.
- Produces: `deeplabeling.core.editor.Editor(store, history, review, *, on_labels_changed: Callable[[tuple[Path, ...]], None] | None = None, on_history_changed: Callable[[], None] | None = None)`, with `.store`, `.history`, `.review`, `.apply(intent) -> Edit | None`, `.undo() -> Edit | None` and `.redo() -> Edit | None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_history.py`:

```python
import pytest

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.edits import AddBox, DeleteLine, Intent, Refused, SetClass
from deeplabeling.core.editor import Editor
from deeplabeling.core.history import History
from deeplabeling.core.review import ReviewMarks
from deeplabeling.core.store import LabelStore
from fixtures import GAUNTLET, read_exact

BOX = (0.5, 0.5, 0.2, 0.2)


class Recorder:
    def __init__(self):
        self.labels = []
        self.history = 0

    def labels_changed(self, images):
        self.labels.append(images)

    def history_changed(self):
        self.history += 1


@pytest.fixture
def rec():
    return Recorder()


@pytest.fixture
def editor(ds, tmp_path, rec):
    dataset = Dataset.open(ds.yaml)
    store = LabelStore(dataset)
    return Editor(store, History(store), ReviewMarks(tmp_path / "review.json", dataset.root),
                  on_labels_changed=rec.labels_changed, on_history_changed=rec.history_changed)


def add(ds, name="camA/0003.jpg"):
    return Intent(ds.img(name), (AddBox(0, BOX),), "draw a box")


def test_an_applied_edit_is_written_recorded_and_marks_the_image(editor, ds, rec):
    edit = editor.apply(add(ds))
    assert ds.lbl("camA/0003").is_file()
    assert editor.history.peek_undo() is edit and editor.history.depth == 1
    assert editor.review.is_marked("camA/images/0003.jpg")
    assert rec.labels == [(ds.img("camA/0003.jpg"),)] and rec.history == 1


def test_an_edit_that_changes_nothing_records_nothing(editor, ds, rec):
    img = ds.img("camA/0001.jpg")
    same = Intent(img, (SetClass(editor.store.get(img).ref(0), 0),), "same class")
    assert editor.apply(same) is None
    assert editor.history.depth == 0 and editor.review.count() == 0 and rec.labels == []


def test_a_refused_edit_records_nothing(editor, ds, rec):
    with pytest.raises(Refused):
        editor.apply(Intent(ds.img("camB/twin.jpg"), (AddBox(0, BOX),), "draw"))
    assert editor.history.depth == 0 and editor.review.count() == 0 and rec.labels == []


def test_undo_then_redo_is_byte_exact_on_the_gauntlet(editor, ds):
    img = ds.img("bad/ok.jpg")
    before = ds.snapshot()
    editor.apply(Intent(img, (DeleteLine(editor.store.get(img).ref(6)),), "delete"))
    after = ds.snapshot()
    editor.undo()
    assert ds.snapshot() == before and read_exact(ds.lbl("bad/ok")) == GAUNTLET
    editor.redo()
    assert ds.snapshot() == after


def test_undo_walks_back_across_images(editor, ds, rec):
    first = editor.apply(add(ds, "camA/0003.jpg"))
    second = editor.apply(add(ds, "camA/0004.JPG"))
    assert editor.history.peek_undo() is second
    assert editor.undo() is second and not ds.lbl("camA/0004").exists()
    assert editor.history.peek_undo() is first and editor.history.peek_redo() is second
    assert rec.labels[-1] == (ds.img("camA/0004.JPG"),)


def test_a_new_edit_clears_redo(editor, ds):
    editor.apply(add(ds))
    editor.undo()
    editor.apply(add(ds, "camA/0004.JPG"))
    assert not editor.history.can_redo and editor.redo() is None


def test_nothing_to_undo_or_redo(editor):
    assert editor.undo() is None and editor.redo() is None


def test_undo_after_an_outside_change_is_refused_and_dropped(editor, ds):
    first = editor.apply(add(ds, "camA/0004.JPG"))
    editor.apply(add(ds))
    ds.lbl("camA/0003").write_bytes(b"outside\n")
    with pytest.raises(Refused, match="dropped"):
        editor.undo()
    assert ds.lbl("camA/0003").read_bytes() == b"outside\n"
    assert editor.history.depth == 1 and editor.history.peek_undo() is first
    assert editor.undo() is first and not ds.lbl("camA/0004").exists()


def test_redo_after_an_outside_change_is_refused_and_dropped(editor, ds):
    editor.apply(add(ds))
    editor.undo()
    ds.lbl("camA/0003").write_bytes(b"outside\n")
    with pytest.raises(Refused, match="dropped"):
        editor.redo()
    assert not editor.history.can_redo
    assert ds.lbl("camA/0003").read_bytes() == b"outside\n"


def test_the_history_drops_its_oldest_edits_past_its_budget(ds, tmp_path):
    dataset = Dataset.open(ds.yaml)
    store = LabelStore(dataset)
    history = History(store, cap_bytes=1)
    editor = Editor(store, history, ReviewMarks(tmp_path / "r.json", dataset.root))
    editor.apply(add(ds))
    newest = editor.apply(add(ds, "camA/0004.JPG"))
    assert history.depth == 1 and history.peek_undo() is newest


def test_undo_keeps_the_review_mark(editor, ds):
    editor.apply(add(ds))
    editor.undo()
    assert editor.review.is_marked("camA/images/0003.jpg")


def test_a_refused_undo_still_reports_the_history_change(editor, ds, rec):
    editor.apply(add(ds))
    ds.lbl("camA/0003").write_bytes(b"outside\n")
    count = rec.history
    with pytest.raises(Refused):
        editor.undo()
    assert rec.history == count + 1
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_history.py -q`
Expected: `ModuleNotFoundError: No module named 'deeplabeling.core.editor'`.

- [ ] **Step 3: Write `history.py` and `editor.py`**

Create `src/deeplabeling/core/history.py`:

```python
"""Undo and redo across every image (docs/design/2026-10-04-app-foundation.md#history)."""

from __future__ import annotations

from collections import deque

from .edits import Edit, Refused
from .store import LabelStore


class History:
    """One global list of Edits, capped in bytes; the oldest are dropped first.

    Undo and redo go through `LabelStore.restore`, which refuses when a file no
    longer holds what the edit left. A refused edit can never succeed, so it is
    dropped, and the edits before it stay undoable.
    """

    def __init__(self, store: LabelStore, *, cap_bytes: int = 64 * 2**20):
        self._store = store
        self._cap = cap_bytes
        self._undo: deque[Edit] = deque()
        self._redo: list[Edit] = []
        self._bytes = 0

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def depth(self) -> int:
        return len(self._undo)

    def peek_undo(self) -> Edit | None:
        """The edit `undo` would revert, so the UI can move to its image first."""
        return self._undo[-1] if self._undo else None

    def peek_redo(self) -> Edit | None:
        return self._redo[-1] if self._redo else None

    def push(self, edit: Edit) -> None:
        self._bytes -= sum(e.nbytes for e in self._redo)
        self._redo.clear()
        self._undo.append(edit)
        self._bytes += edit.nbytes
        while self._bytes > self._cap and len(self._undo) > 1:
            self._bytes -= self._undo.popleft().nbytes

    def undo(self) -> Edit | None:
        if not self._undo:
            return None
        edit = self._undo[-1]
        try:
            self._store.restore(edit, undo=True)
        except Refused as e:
            self._undo.pop()
            self._bytes -= edit.nbytes
            raise Refused(f"cannot undo “{edit.description}”: {e}. "
                          "It has been dropped from the history.") from e
        self._redo.append(self._undo.pop())
        return edit

    def redo(self) -> Edit | None:
        if not self._redo:
            return None
        edit = self._redo[-1]
        try:
            self._store.restore(edit, undo=False)
        except Refused as e:
            self._redo.pop()
            self._bytes -= edit.nbytes
            raise Refused(f"cannot redo “{edit.description}”: {e}. "
                          "It has been dropped from the history.") from e
        self._undo.append(self._redo.pop())
        return edit
```

Create `src/deeplabeling/core/editor.py`:

```python
"""The GUI thread's one way to change labels (docs/design/2026-10-04-app-foundation.md#edits).

An applied edit is written by the store, recorded in the history and marks its
image reviewed; the listeners hear which images changed.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .edits import Edit, Intent
from .history import History
from .review import ReviewMarks
from .store import LabelStore


class Editor:
    def __init__(self, store: LabelStore, history: History, review: ReviewMarks, *,
                 on_labels_changed: Callable[[tuple[Path, ...]], None] | None = None,
                 on_history_changed: Callable[[], None] | None = None):
        self.store = store
        self.history = history
        self.review = review
        self._labels_changed = on_labels_changed or (lambda images: None)
        self._history_changed = on_history_changed or (lambda: None)

    def apply(self, intent: Intent) -> Edit | None:
        """Write, record and mark. On Refused nothing has changed."""
        edit = self.store.apply(intent)
        if edit is None:
            return None
        self.history.push(edit)
        self.review.mark(self.store.dataset.entry(intent.image).rel)
        self._labels_changed(edit.images)
        self._history_changed()
        return edit

    def undo(self) -> Edit | None:
        try:
            edit = self.history.undo()
        finally:
            self._history_changed()     # a refused undo still dropped an edit
        if edit is not None:
            self._labels_changed(edit.images)
        return edit

    def redo(self) -> Edit | None:
        try:
            edit = self.history.redo()
        finally:
            self._history_changed()
        if edit is not None:
            self._labels_changed(edit.images)
        return edit
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_history.py -q`
Expected: all pass.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings`
Expected: all pass.

```bash
git add src/deeplabeling/core/history.py src/deeplabeling/core/editor.py tests/core/test_history.py
git commit -m "core: global undo/redo and the editor facade" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Queues

**Files:**
- Create: `src/deeplabeling/core/queue.py`
- Test: `tests/core/test_queue.py`

**Interfaces:**
- Consumes: `Dataset` and `ImageEntry` (Task 3); `ImageLabels`, `LabelState` and `LabelStore` (Task 5).
- Produces in `deeplabeling.core.queue`:
  - `QueueItem(key: str, entry: ImageEntry)`;
  - `BuildContext(dataset, store, reviewed: frozenset[str])`, with `.labels(entry)`;
  - the base class `Condition`, with `kind`, `needs_labels`, `.test(entry, ctx)`, `.describe(dataset)`, `.highlight(labels, dataset) -> frozenset[int]` and `.to_json()`;
  - the conditions `HasClass(names: tuple[str, ...], present=True)`, `LabelStateIs(state)` (where `state` is one of `LABEL_STATES = ("missing", "negative", "boxes")`), `Reviewed(value=True)` and `NameContains(text)`;
  - `condition_from_json(data) -> Condition`;
  - `ImageFilter(splits: tuple[str, ...] = (), conditions: tuple[Condition, ...] = ())`, with `.describe(dataset)`, `.matches(entry, ctx)`, `.highlight(labels, dataset)`, `.build(ctx, emit, cancelled=..., *, batch=500, interval=0.2) -> bool` (False when cancelled), `.to_json()` and `ImageFilter.from_json(data)`;
  - `Queue(source, *, follow: ImageEntry | None = None)`.
    - Attributes: `.source`, `.items`, `.cursor`, `.stale: set[str]` and `.complete`.
    - Building: `.extend(batch)` and `.finish()`.
    - The cursor: `.current() -> QueueItem | None`, `.position() -> int | None`, `.move(delta) -> bool` and `.go_to(key) -> bool`.
    - Status: `.left(is_reviewed) -> int` and `.recheck(entry, ctx)`.
    - It supports `len()` and `in`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_queue.py`:

```python
import pytest

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.queue import (
    BuildContext,
    HasClass,
    ImageFilter,
    LabelStateIs,
    NameContains,
    Queue,
    QueueItem,
    Reviewed,
)
from deeplabeling.core.store import LabelStore


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)


@pytest.fixture
def ctx(dataset):
    return BuildContext(dataset, LabelStore(dataset), frozenset({"camA/images/0001.jpg"}))


def build(source, ctx, **kw):
    batches = []
    done = source.build(ctx, batches.append, **kw)
    return done, batches


def keys(source, ctx):
    done, batches = build(source, ctx)
    assert done
    return [item.key for batch in batches for item in batch]


def all_items(dataset):
    return [QueueItem(e.rel, e) for e in dataset.images]


def test_all_images_in_dataset_order(ctx, dataset):
    assert keys(ImageFilter(), ctx) == [e.rel for e in dataset.images]


def test_items_arrive_in_batches(ctx):
    _, batches = build(ImageFilter(), ctx, batch=4, interval=1e9)
    assert [len(b) for b in batches] == [4, 4, 4, 3]


def test_a_zero_interval_sends_each_match_at_once(ctx):
    _, batches = build(ImageFilter(), ctx, interval=0)
    assert all(len(b) == 1 for b in batches)


def test_a_cancelled_build_stops(ctx):
    calls = []

    def cancelled():
        calls.append(1)
        return len(calls) > 3

    done, _ = build(ImageFilter(), ctx, cancelled=cancelled)
    assert not done and len(calls) == 4


def test_has_class_by_name(ctx):
    assert keys(ImageFilter(conditions=(HasClass(("bus_m",)),)), ctx) == [
        "camA/images/sub/0005.jpg", "camB/images/0001.jpg", "camB/images/rot.jpg"]


def test_lacks_class(ctx):
    lacking = keys(ImageFilter(conditions=(HasClass(("person",), present=False),)), ctx)
    assert "camA/images/0001.jpg" not in lacking and "camA/images/0003.jpg" in lacking


def test_an_unknown_class_name_never_matches(ctx):
    assert keys(ImageFilter(conditions=(HasClass(("truck",)),)), ctx) == []


def test_has_class_highlights_its_boxes(ctx, ds):
    labels = ctx.store.get(ds.img("camA/0001.jpg"))
    assert ImageFilter(conditions=(HasClass(("car",)),)).highlight(labels, ctx.dataset) == {1}
    lacks = ImageFilter(conditions=(HasClass(("car",), present=False),))
    assert lacks.highlight(labels, ctx.dataset) == frozenset()


@pytest.mark.parametrize("state, expected", [
    ("missing", ["camA/images/0003.jpg", "camA/images/0004.JPG"]),
    ("negative", ["camA/images/0002.jpg"]),
])
def test_label_state(ctx, state, expected):
    assert keys(ImageFilter(conditions=(LabelStateIs(state),)), ctx) == expected


def test_label_state_boxes(ctx):
    assert len(keys(ImageFilter(conditions=(LabelStateIs("boxes"),)), ctx)) == 12


def test_an_unknown_label_state_is_an_error():
    with pytest.raises(ValueError):
        LabelStateIs("maybe")


def test_reviewed_uses_the_snapshot(ctx):
    assert keys(ImageFilter(conditions=(Reviewed(),)), ctx) == ["camA/images/0001.jpg"]
    assert "camA/images/0001.jpg" not in keys(ImageFilter(conditions=(Reviewed(False),)), ctx)


def test_name_contains_ignores_case(ctx):
    assert keys(ImageFilter(conditions=(NameContains("TWIN"),)), ctx) == [
        "camB/images/twin.jpg", "camB/images/twin.png"]


def test_splits(ctx):
    in_val = keys(ImageFilter(splits=("val",)), ctx)
    assert len(in_val) == 5 and in_val[0] == "bad/images/corrupt.jpg"


def test_every_condition_must_hold(ctx):
    f = ImageFilter(splits=("train",), conditions=(HasClass(("bus_m",)), NameContains("camB")))
    assert keys(f, ctx) == ["camB/images/0001.jpg", "camB/images/rot.jpg"]


def test_cheap_conditions_run_before_labels_are_read(dataset):
    class NoReading:
        calls = 0

        def get(self, image):
            NoReading.calls += 1
            raise AssertionError("labels were read")

    ctx = BuildContext(dataset, NoReading(), frozenset())
    f = ImageFilter(conditions=(HasClass(("car",)), NameContains("no such name")))
    assert keys(f, ctx) == [] and NoReading.calls == 0


def test_descriptions(dataset):
    assert ImageFilter().describe(dataset) == "all images"
    f = ImageFilter(splits=("val",), conditions=(HasClass(("bus_l", "bus_m")), Reviewed(False)))
    assert f.describe(dataset) == "has bus_l or bus_m and not reviewed in val"


def test_a_filter_survives_json():
    f = ImageFilter(splits=("val",), conditions=(
        HasClass(("car",), present=False), LabelStateIs("negative"), Reviewed(False),
        NameContains("cam")))
    assert ImageFilter.from_json(f.to_json()) == f


@pytest.mark.parametrize("data", [
    {"conditions": [{"kind": "colour"}]}, {"conditions": [{"kind": "name"}]},
    {"splits": "val"}, [], {"conditions": ["name"]},
])
def test_bad_json_is_an_error(data):
    with pytest.raises(ValueError):
        ImageFilter.from_json(data)


def test_the_cursor_starts_on_the_first_item(dataset):
    q = Queue(ImageFilter())
    assert q.current() is None and q.position() is None
    q.extend(all_items(dataset)[:3])
    assert q.cursor == dataset.images[0].rel and q.position() == 0


def test_moving_stops_at_either_end(dataset):
    q = Queue(ImageFilter())
    q.extend(all_items(dataset)[:2])
    assert not q.move(-1) and q.position() == 0
    assert q.move(1) and q.position() == 1
    assert not q.move(1) and q.position() == 1


def test_go_to(dataset):
    q = Queue(ImageFilter())
    q.extend(all_items(dataset))
    assert q.go_to("crlf/images/c.jpg") and q.current().entry.rel == "crlf/images/c.jpg"
    assert not q.go_to("nope") and q.cursor == "crlf/images/c.jpg"


def test_a_followed_item_takes_the_cursor_when_it_arrives(dataset):
    target = dataset.images[5]
    q = Queue(ImageFilter(), follow=target)
    q.extend(all_items(dataset)[:3])
    assert q.position() == 0
    q.extend(all_items(dataset)[3:])
    assert q.cursor == target.rel


def test_a_followed_item_that_is_gone_gives_way_to_the_next(dataset):
    target = dataset.images[5]
    q = Queue(ImageFilter(), follow=target)
    q.extend([item for item in all_items(dataset) if item.key != target.rel])
    q.finish()
    assert q.cursor == dataset.images[6].rel and q.complete


def test_with_nothing_after_it_the_cursor_takes_the_last_item(dataset):
    q = Queue(ImageFilter(), follow=dataset.images[-1])
    q.extend(all_items(dataset)[:4])
    q.finish()
    assert q.cursor == dataset.images[3].rel


def test_moving_cancels_the_follow(dataset):
    q = Queue(ImageFilter(), follow=dataset.images[5])
    q.extend(all_items(dataset)[:3])
    q.move(1)
    q.extend(all_items(dataset)[3:])
    q.finish()
    assert q.position() == 1


def test_left_counts_unreviewed_items(dataset):
    q = Queue(ImageFilter())
    q.extend(all_items(dataset)[:4])
    assert q.left(lambda key: key == dataset.images[0].rel) == 3


def test_recheck_marks_an_item_that_no_longer_matches(ctx, ds):
    f = ImageFilter(conditions=(HasClass(("car",)),))
    q = Queue(f)
    f.build(ctx, q.extend)
    q.finish()
    entry = ctx.dataset.entry(ds.img("camA/0001.jpg"))
    ds.lbl("camA/0001").write_bytes(b"0 0.5 0.5 0.2 0.2\n")
    q.recheck(entry, ctx)
    assert entry.rel in q.stale and entry.rel in q
    ds.lbl("camA/0001").write_bytes(b"1 0.5 0.5 0.2 0.2\n2 0.1 0.1 0.1 0.1\n")   # another size
    q.recheck(entry, ctx)
    assert entry.rel not in q.stale


def test_duplicate_items_are_ignored(dataset):
    q = Queue(ImageFilter())
    q.extend(all_items(dataset)[:2])
    q.extend(all_items(dataset)[:2])
    assert len(q) == 2
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_queue.py -q`
Expected: `ModuleNotFoundError: No module named 'deeplabeling.core.queue'`.

- [ ] **Step 3: Write `queue.py`**

Create `src/deeplabeling/core/queue.py`:

```python
"""Queues: the list being worked through (docs/design/2026-10-04-app-foundation.md#queue).

A source builds its items on a worker from immutable inputs -- the dataset, the
thread-safe store and a snapshot of the review marks -- and streams them in
batches. A Queue holds them on the GUI thread with one cursor, an identity key.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import ClassVar

from .dataset import Dataset, ImageEntry
from .store import ImageLabels, LabelState, LabelStore

LABEL_STATES = ("missing", "negative", "boxes")


@dataclass(frozen=True)
class QueueItem:
    key: str
    entry: ImageEntry


@dataclass(frozen=True)
class BuildContext:
    dataset: Dataset
    store: LabelStore
    reviewed: frozenset[str]        #: review-mark keys, snapshotted before the build

    def labels(self, entry: ImageEntry) -> ImageLabels:
        return self.store.get(entry.path)


class Condition:
    """One test an image must pass. Subclasses are frozen dataclasses."""

    kind: ClassVar[str]
    needs_labels: ClassVar[bool] = True

    def test(self, entry: ImageEntry, ctx: BuildContext) -> bool:
        raise NotImplementedError

    def describe(self, dataset: Dataset) -> str:
        raise NotImplementedError

    def highlight(self, labels: ImageLabels, dataset: Dataset) -> frozenset[int]:
        """Line indices of the boxes that made the condition hold."""
        return frozenset()

    def to_json(self) -> dict:
        raise NotImplementedError


@dataclass(frozen=True)
class HasClass(Condition):
    """The image has (or lacks) a box of any of the named classes."""

    names: tuple[str, ...]
    present: bool = True
    kind: ClassVar[str] = "class"

    def _ids(self, dataset: Dataset) -> set[int]:
        return {i for i in map(dataset.id_of, self.names) if i is not None}

    def test(self, entry, ctx):
        ids = self._ids(ctx.dataset)
        found = any(line.cls_id in ids for _, line in ctx.labels(entry).boxes)
        return found == self.present

    def describe(self, dataset):
        return ("has " if self.present else "lacks ") + " or ".join(self.names)

    def highlight(self, labels, dataset):
        if not self.present:
            return frozenset()
        ids = self._ids(dataset)
        return frozenset(i for i, line in labels.boxes if line.cls_id in ids)

    def to_json(self):
        return {"kind": self.kind, "names": list(self.names), "present": self.present}


@dataclass(frozen=True)
class LabelStateIs(Condition):
    """No label file, an empty one (a negative sample), or one with boxes."""

    state: str
    kind: ClassVar[str] = "label"

    def __post_init__(self):
        if self.state not in LABEL_STATES:
            raise ValueError(f"unknown label state {self.state!r}")

    def test(self, entry, ctx):
        labels = ctx.labels(entry)
        if self.state == "missing":
            return labels.raw is None and labels.state is not LabelState.ERROR
        if self.state == "negative":
            return labels.negative
        return bool(labels.boxes)

    def describe(self, dataset):
        return {"missing": "no label file", "negative": "negative",
                "boxes": "has boxes"}[self.state]

    def to_json(self):
        return {"kind": self.kind, "state": self.state}


@dataclass(frozen=True)
class Reviewed(Condition):
    value: bool = True
    kind: ClassVar[str] = "reviewed"
    needs_labels: ClassVar[bool] = False

    def test(self, entry, ctx):
        return (entry.rel in ctx.reviewed) == self.value

    def describe(self, dataset):
        return "reviewed" if self.value else "not reviewed"

    def to_json(self):
        return {"kind": self.kind, "value": self.value}


@dataclass(frozen=True)
class NameContains(Condition):
    """The dataset-relative path contains the text, ignoring case."""

    text: str
    kind: ClassVar[str] = "name"
    needs_labels: ClassVar[bool] = False

    def test(self, entry, ctx):
        return self.text.lower() in entry.rel.lower()

    def describe(self, dataset):
        return f'name contains "{self.text}"'

    def to_json(self):
        return {"kind": self.kind, "text": self.text}


def condition_from_json(data) -> Condition:
    try:
        kind = data["kind"]
        if kind == "class":
            return HasClass(tuple(str(n) for n in data["names"]), bool(data.get("present", True)))
        if kind == "label":
            return LabelStateIs(str(data["state"]))
        if kind == "reviewed":
            return Reviewed(bool(data.get("value", True)))
        if kind == "name":
            return NameContains(str(data["text"]))
    except (KeyError, TypeError) as e:
        raise ValueError(f"not a queue condition: {data!r}") from e
    raise ValueError(f"unknown queue condition {kind!r}")


@dataclass(frozen=True)
class ImageFilter:
    """Every image of the chosen splits that passes every condition, in dataset order.

    Slice 3 adds conditions; it does not add a second filter system.
    """

    splits: tuple[str, ...] = ()
    conditions: tuple[Condition, ...] = ()

    def describe(self, dataset: Dataset) -> str:
        text = " and ".join(c.describe(dataset) for c in self.conditions) or "all images"
        return f"{text} in {' + '.join(self.splits)}" if self.splits else text

    def matches(self, entry: ImageEntry, ctx: BuildContext) -> bool:
        if self.splits and entry.split not in self.splits:
            return False
        cheap_first = sorted(self.conditions, key=lambda c: c.needs_labels)
        return all(c.test(entry, ctx) for c in cheap_first)

    def highlight(self, labels: ImageLabels, dataset: Dataset) -> frozenset[int]:
        found: frozenset[int] = frozenset()
        for condition in self.conditions:
            found |= condition.highlight(labels, dataset)
        return found

    def build(self, ctx: BuildContext, emit: Callable[[list[QueueItem]], None],
              cancelled: Callable[[], bool] = lambda: False, *,
              batch: int = 500, interval: float = 0.2) -> bool:
        """Stream the matching items to `emit`. False when cancelled part-way."""
        pending: list[QueueItem] = []
        last = time.monotonic()
        for entry in ctx.dataset.images:
            if cancelled():
                return False
            if self.matches(entry, ctx):
                pending.append(QueueItem(entry.rel, entry))
            now = time.monotonic()
            if pending and (len(pending) >= batch or now - last >= interval):
                emit(pending)
                pending, last = [], now
        if pending:
            emit(pending)
        return True

    def to_json(self) -> dict:
        return {"splits": list(self.splits), "conditions": [c.to_json() for c in self.conditions]}

    @classmethod
    def from_json(cls, data) -> ImageFilter:
        if not isinstance(data, dict):
            raise ValueError(f"not a queue: {data!r}")
        splits, conditions = data.get("splits", []), data.get("conditions", [])
        if (not isinstance(splits, list) or not all(isinstance(s, str) for s in splits)
                or not isinstance(conditions, list)):
            raise ValueError(f"not a queue: {data!r}")
        return cls(tuple(splits), tuple(condition_from_json(c) for c in conditions))


class Queue:
    """A queue's items in order, one cursor (an identity key), and which items no
    longer match since the queue was built. Used on the GUI thread."""

    def __init__(self, source: ImageFilter, *, follow: ImageEntry | None = None):
        self.source = source
        self.items: list[QueueItem] = []
        self.cursor: str | None = None
        self.stale: set[str] = set()
        self.complete = False
        self._pos: dict[str, int] = {}
        self._follow = follow       #: the item the cursor was on before a rebuild
        self._moved = False

    def __len__(self) -> int:
        return len(self.items)

    def __contains__(self, key: str) -> bool:
        return key in self._pos

    def extend(self, batch: Iterable[QueueItem]) -> None:
        for item in batch:
            if item.key in self._pos:
                continue
            self._pos[item.key] = len(self.items)
            self.items.append(item)
            if self._follow is not None and not self._moved and item.key == self._follow.rel:
                self.cursor = item.key
                self._follow = None
        if self.cursor is None and self.items:
            self.cursor = self.items[0].key

    def finish(self) -> None:
        """The build is done. A cursor still waiting for its old item takes the first
        item after it in dataset order, or the last item."""
        self.complete = True
        if self._follow is not None and not self._moved and self.items:
            after = next((it for it in self.items if it.entry.order > self._follow.order), None)
            self.cursor = (after or self.items[-1]).key
        self._follow = None

    def current(self) -> QueueItem | None:
        return self.items[self._pos[self.cursor]] if self.cursor is not None else None

    def position(self) -> int | None:
        return self._pos[self.cursor] if self.cursor is not None else None

    def move(self, delta: int) -> bool:
        """Step through the queue; False, and no move, at either end."""
        if self.cursor is None:
            return False
        index = self._pos[self.cursor] + delta
        if not 0 <= index < len(self.items):
            return False
        return self._set(self.items[index].key)

    def go_to(self, key: str) -> bool:
        return key in self._pos and self._set(key)

    def _set(self, key: str) -> bool:
        self.cursor = key
        self._moved = True
        self._follow = None
        return True

    def left(self, is_reviewed: Callable[[str], bool]) -> int:
        return sum(1 for item in self.items if not is_reviewed(item.key))

    def recheck(self, entry: ImageEntry, ctx: BuildContext) -> None:
        """After `entry` changed: mark its item stale while it no longer matches."""
        if entry.rel not in self._pos:
            return
        if self.source.matches(entry, ctx):
            self.stale.discard(entry.rel)
        else:
            self.stale.add(entry.rel)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_queue.py -q`
Expected: all pass.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings`
Expected: all pass.

```bash
git add src/deeplabeling/core/queue.py tests/core/test_queue.py
git commit -m "core: queues with streaming builds and an identity cursor" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: The taxonomy guard and the workspace

**Files:**
- Create: `src/deeplabeling/core/taxonomy.py`, `src/deeplabeling/core/workspace.py`
- Test: `tests/core/test_workspace.py`

**Interfaces:**
- Consumes:
  - `Dataset` (Task 3) and `LabelStore` (Task 5);
  - `DatasetLock`, `Locked` and `dataset_state_dir` (Task 6), with `JsonFile`, `Settings`, `define` and the validators (also Task 6);
  - `ReviewMarks` (Task 7), with `History` and `Editor` (Task 8).
- Produces in `deeplabeling.core.taxonomy`: `OutOfRange(boxes=0, images=0, ids=())`, with `.message(dataset) -> str`; `count_out_of_range(dataset, store, cancelled=...) -> OutOfRange | None`; and `names_changed(last, names) -> bool`.
- Produces in `deeplabeling.core.workspace`:
  - the settings `TAXONOMY_NAMES`, `TAXONOMY_SOURCE`, `CLASS_COLORS` and `CLASS_HOTKEYS` (scope root), and `QUEUE_SOURCE`, `QUEUE_CURSOR` and `ACTIVE_CLASS` (scope opening);
  - `ConfirmTaxonomy = Callable[[str, list[str], str, tuple[str, ...]], bool]`;
  - `OpenCancelled(Exception)`;
  - `Workspace`, opened with `Workspace.open(source, labels=None, *, confirm_taxonomy, on_labels_changed=None, on_history_changed=None, on_reload=None)`.
    - Fields: `dataset`, `directory`, `lock`, `file`, `root_settings`, `opening_settings`, `review`, `store`, `history` and `editor`.
    - Members: `.warnings`, `.save()` and `.close()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_workspace.py`:

```python
import json
import os

import pytest
import yaml

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.edits import AddBox, Intent
from deeplabeling.core.state import Locked, dataset_state_dir
from deeplabeling.core.store import LabelStore
from deeplabeling.core.taxonomy import OutOfRange, count_out_of_range, names_changed
from deeplabeling.core.workspace import (
    CLASS_COLORS,
    QUEUE_CURSOR,
    TAXONOMY_NAMES,
    OpenCancelled,
    Workspace,
)

NAMES = ["person", "car", "bus_m", "bus_l"]


def never(*args):
    raise AssertionError(f"asked about the taxonomy: {args}")


def second_yaml(ds, names):
    data = yaml.safe_load(ds.yaml.read_text(encoding="utf-8"))
    data["names"] = names
    path = ds.root / "other.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_opening_takes_the_lock_and_records_the_class_names(ds):
    ws = Workspace.open(ds.yaml, confirm_taxonomy=never)
    assert ws.directory == dataset_state_dir(ds.root.resolve())
    assert ws.lock.path.read_text().strip() == str(os.getpid())
    data = json.loads((ws.directory / "dataset.json").read_text())
    assert data["root"]["taxonomy.names"] == NAMES
    assert data["root"]["taxonomy.source"] == str(ds.yaml)
    assert ws.warnings == ()
    ws.close()
    assert not ws.lock.path.exists()


def test_marks_and_settings_survive_a_reopen(ds):
    ws = Workspace.open(ds.yaml, confirm_taxonomy=never)
    ws.editor.apply(Intent(ds.img("camA/0003.jpg"), (AddBox(0, (0.5, 0.5, 0.2, 0.2)),), "draw"))
    ws.opening_settings.set(QUEUE_CURSOR, "camA/images/0003.jpg")
    ws.close()
    again = Workspace.open(ds.yaml, confirm_taxonomy=never)
    assert again.review.is_marked("camA/images/0003.jpg")
    assert again.opening_settings.get(QUEUE_CURSOR) == "camA/images/0003.jpg"
    again.close()


def test_a_root_open_elsewhere_is_refused(ds):
    lock = dataset_state_dir(ds.root.resolve()) / "lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(f"{os.getppid()}\n")
    with pytest.raises(Locked):
        Workspace.open(ds.yaml, confirm_taxonomy=never)


def test_a_different_class_list_asks_first_and_can_be_declined(ds):
    Workspace.open(ds.yaml, confirm_taxonomy=never).close()
    other = second_yaml(ds, ["BSD", "BSV", "bus"])
    asked = []

    def decline(*args):
        asked.append(args)
        return False

    with pytest.raises(OpenCancelled):
        Workspace.open(other, confirm_taxonomy=decline)
    assert asked == [(str(ds.yaml), NAMES, str(other), ("BSD", "BSV", "bus"))]
    assert not (dataset_state_dir(ds.root.resolve()) / "lock").exists()
    ws = Workspace.open(other, confirm_taxonomy=lambda *args: True)
    assert ws.root_settings.get(TAXONOMY_NAMES) == ["BSD", "BSV", "bus"]
    ws.close()


def test_the_same_class_list_asks_nothing(ds):
    Workspace.open(ds.yaml, confirm_taxonomy=never).close()
    Workspace.open(second_yaml(ds, NAMES), confirm_taxonomy=never).close()


def test_openings_of_one_root_share_root_settings_only(ds):
    ws = Workspace.open(ds.yaml, confirm_taxonomy=never)
    ws.root_settings.set(CLASS_COLORS, {"car": "#00ff00"})
    ws.opening_settings.set(QUEUE_CURSOR, "camA/images/0001.jpg")
    ws.close()
    other = Workspace.open(second_yaml(ds, NAMES), confirm_taxonomy=never)
    assert other.root_settings.get(CLASS_COLORS) == {"car": "#00ff00"}
    assert other.opening_settings.get(QUEUE_CURSOR) is None
    other.close()


def test_an_unreadable_state_file_is_a_warning_not_a_failure(ds):
    directory = dataset_state_dir(ds.root.resolve())
    directory.mkdir(parents=True)
    (directory / "review.json").write_bytes(b"{broken")
    ws = Workspace.open(ds.yaml, confirm_taxonomy=never)
    assert len(ws.warnings) == 1 and "review.json" in ws.warnings[0]
    ws.close()


def test_out_of_range_ids_are_counted(ds):
    dataset = Dataset.open(ds.yaml)
    found = count_out_of_range(dataset, LabelStore(dataset))
    assert found == OutOfRange(boxes=2, images=1, ids=(-1, 99))
    assert "data.yaml does not name" in found.message(dataset)


def test_nothing_is_out_of_range_without_names(ds):
    dataset = Dataset.open(ds.root / "camA/images")
    assert count_out_of_range(dataset, LabelStore(dataset)) == OutOfRange()


def test_a_cancelled_count_returns_none(ds):
    dataset = Dataset.open(ds.yaml)
    assert count_out_of_range(dataset, LabelStore(dataset), cancelled=lambda: True) is None


def test_names_changed():
    assert not names_changed(None, ("a",))
    assert not names_changed(["a"], ("a",))
    assert names_changed(["a"], ("a", "b"))
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_workspace.py -q`
Expected: `ModuleNotFoundError: No module named 'deeplabeling.core.taxonomy'`.

- [ ] **Step 3: Write `taxonomy.py` and `workspace.py`**

Create `src/deeplabeling/core/taxonomy.py`:

```python
"""The taxonomy guard (docs/design/2026-10-04-app-foundation.md#dataset): one set of
label files can be read under more than one yaml, and only one of them is right."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .dataset import Dataset
from .store import LabelStore


@dataclass(frozen=True)
class OutOfRange:
    """Boxes whose class id the dataset's names do not cover."""

    boxes: int = 0
    images: int = 0
    ids: tuple[int, ...] = ()

    def message(self, dataset: Dataset) -> str:
        if not self.boxes:
            return ""
        shown = ", ".join(map(str, self.ids[:5])) + (", …" if len(self.ids) > 5 else "")
        return (f"{self.boxes} boxes in {self.images} images have class ids ({shown}) that "
                f"{dataset.source.name} does not name. Is it the right yaml for these labels?")


def count_out_of_range(dataset: Dataset, store: LabelStore,
                       cancelled: Callable[[], bool] = lambda: False) -> OutOfRange | None:
    """Read every image's labels through `store` -- warming its cache -- and count the
    boxes the names do not cover. None when cancelled. With no names, none are."""
    if not dataset.names:
        return OutOfRange()
    boxes = images = 0
    ids: set[int] = set()
    for entry in dataset.images:
        if cancelled():
            return None
        bad = [line.cls_id for _, line in store.get(entry.path).boxes
               if not dataset.known(line.cls_id)]
        if bad:
            boxes += len(bad)
            images += 1
            ids.update(bad)
    return OutOfRange(boxes, images, tuple(sorted(ids)))


def names_changed(last: list[str] | None, names: tuple[str, ...]) -> bool:
    """Whether a root last opened with `last` is now opened with other names."""
    return last is not None and tuple(last) != tuple(names)
```

Create `src/deeplabeling/core/workspace.py`:

```python
"""Opening a dataset: the one funnel every launch path goes through
(docs/design/2026-10-04-app-foundation.md#state-and-settings)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .dataset import Dataset
from .editor import Editor
from .history import History
from .review import ReviewMarks
from .settings import JsonFile, Settings, define, is_str_list, is_str_map, is_str_or_none
from .state import DatasetLock, dataset_state_dir
from .store import LabelStore
from .taxonomy import names_changed

TAXONOMY_NAMES = define("taxonomy.names", "root", None, lambda v: v is None or is_str_list(v))
TAXONOMY_SOURCE = define("taxonomy.source", "root", "", lambda v: isinstance(v, str))
CLASS_COLORS = define("classes.colors", "root", {}, is_str_map)
CLASS_HOTKEYS = define("classes.hotkeys", "root", {}, is_str_map)
QUEUE_SOURCE = define("queue.source", "opening", None, lambda v: v is None or isinstance(v, dict))
QUEUE_CURSOR = define("queue.cursor", "opening", None, is_str_or_none)
ACTIVE_CLASS = define("classes.active", "opening", None, is_str_or_none)

#: (source last opened, its names, this source, these names) -> open anyway?
ConfirmTaxonomy = Callable[[str, list[str], str, tuple[str, ...]], bool]


class OpenCancelled(Exception):
    """The user chose not to open the dataset."""


@dataclass(eq=False)
class Workspace:
    dataset: Dataset
    directory: Path
    lock: DatasetLock
    file: JsonFile
    root_settings: Settings
    opening_settings: Settings
    review: ReviewMarks
    store: LabelStore
    history: History
    editor: Editor

    @classmethod
    def open(cls, source, labels=None, *, confirm_taxonomy: ConfirmTaxonomy,
             on_labels_changed: Callable[[tuple[Path, ...]], None] | None = None,
             on_history_changed: Callable[[], None] | None = None,
             on_reload: Callable[[Path], None] | None = None) -> Workspace:
        """Open a dataset for editing. Raises DatasetError, Locked or OpenCancelled."""
        dataset = Dataset.open(source, labels)
        directory = dataset_state_dir(dataset.root)
        lock = DatasetLock(directory)
        lock.acquire()
        try:
            file = JsonFile(directory / "dataset.json")
            root = Settings(file, "root", ("root",))
            last = root.get(TAXONOMY_NAMES)
            if names_changed(last, dataset.names) and not confirm_taxonomy(
                    root.get(TAXONOMY_SOURCE), last, str(dataset.source), dataset.names):
                raise OpenCancelled(f"{dataset.source.name} was not opened")
            root.set(TAXONOMY_NAMES, list(dataset.names))
            root.set(TAXONOMY_SOURCE, str(dataset.source))
            file.save()
            review = ReviewMarks(directory / "review.json", dataset.root)
            store = LabelStore(dataset, on_reload=on_reload)
            history = History(store)
            editor = Editor(store, history, review, on_labels_changed=on_labels_changed,
                            on_history_changed=on_history_changed)
        except BaseException:
            lock.release()
            raise
        return cls(dataset, directory, lock, file, root,
                   Settings(file, "opening", ("openings", dataset.opening_key)),
                   review, store, history, editor)

    @property
    def warnings(self) -> tuple[str, ...]:
        """State files that could not be read, for the notice strip."""
        return tuple(w for w in (self.file.warning, self.review.warning) if w)

    def save(self) -> None:
        self.review.save()
        self.file.save()

    def close(self) -> None:
        try:
            self.save()
        finally:
            self.lock.release()
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_workspace.py -q`
Expected: all pass.

- [ ] **Step 5: Run the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings`
Expected: all pass.

```bash
git add src/deeplabeling/core/taxonomy.py src/deeplabeling/core/workspace.py tests/core/test_workspace.py
git commit -m "core: the taxonomy guard and the workspace open funnel" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: The Qt guard, one overlap implementation, and the docs

**Files:**
- Create: `tests/core/test_core_imports_no_qt.py`
- Modify: `.claude/skills/dataset-analysis/scripts/overlaps.py`, `.claude/skills/dataset-analysis/SKILL.md`, `tests/test_dataset_scripts.py`
- Modify: `docs/knowledge/label-files.md`, `docs/knowledge/caches.md`, `docs/knowledge/legacy-defects.md`, `docs/knowledge/environment.md`, `CLAUDE.md`, `docs/design/2026-10-04-app-foundation.md`

**Interfaces:**
- Consumes: every core module; `labelio`, `geometry` and `overlap` in particular.
- Produces: no new code interfaces. Afterwards the docs describe the code as it is.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_core_imports_no_qt.py`:

```python
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
```

Append to `tests/test_dataset_scripts.py`, after `test_non_overlapping_boxes_never_count_even_from_zero`:

```python
def test_polygons_are_compared_by_their_extent(tmp_path):
    labels = tmp_path / "ds" / "labels"
    labels.mkdir(parents=True)
    # a square polygon 0.1..0.3 and the box with exactly that extent
    (labels / "poly.txt").write_text("0 0.1 0.1 0.3 0.1 0.3 0.3 0.1 0.3\n0 0.2 0.2 0.2 0.2\n")
    assert names(load("overlaps").scan(tmp_path / "ds", 0.99, 1.0, "same")) == ["poly.txt"]
```

- [ ] **Step 2: Run them to see what fails**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_core_imports_no_qt.py tests/test_dataset_scripts.py -q`
Expected: the Qt guard PASSES, since the core is already headless. `test_polygons_are_compared_by_their_extent` FAILS, because the old script reads a polygon's first two points as its box.

- [ ] **Step 3: Move `overlaps.py` onto the core**

In `.claude/skills/dataset-analysis/scripts/overlaps.py`, keep the `#!/usr/bin/env python3` line. Replace everything after it, up to and including the last line of `scan` (`return sorted(hits, key=…)`), with the block below. That removes the docstring, the imports, `SCOPES`, `iou`, `boxes`, `counts` and `scan`, and puts back new versions:

```python
"""Images whose labels overlap each other — from the label files alone, read-only.

IoU is computed on normalised coordinates, which is exact: IoU does not change
under independent x/y scaling, so no image sizes are needed. A pair counts when
its IoU is inside [--min, --max] (inclusive) and above zero. The parsing and the
overlap predicate are deeplabeling.core's, so this script agrees with the app.

  python3 overlaps.py /path/to/dataset --min 0.99 --max 1 --scope same
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

from deeplabeling.core.geometry import iou  # noqa: E402
from deeplabeling.core.labelio import parse_label_bytes  # noqa: E402
from deeplabeling.core.overlap import SCOPES, iou_in_range, pair_counts  # noqa: E402


def boxes(label_file: Path):
    """(class, normalised box) for every parsed line; a polygon by its extent."""
    return [(line.cls_id, line.bbox)
            for line in parse_label_bytes(label_file.read_bytes()) if line.parsed]


def scan(root: Path, lo: float, hi: float, scope: str):
    """[(worst qualifying IoU, label file)] for every file with a qualifying pair."""
    hits = []
    for lf in sorted(Path(root).rglob("*.txt")):
        if "labels" not in lf.parts:
            continue
        bs = boxes(lf)
        qualifying = [v for i, p in enumerate(bs) for q in bs[i + 1:]
                      if pair_counts(scope, p[0], q[0])
                      for v in [iou(p[1], q[1])] if iou_in_range(v, lo, hi)]
        if qualifying:
            hits.append((max(qualifying), lf))
    return sorted(hits, key=lambda h: (-h[0], str(h[1])))
```

`main()` and the `__main__` guard stay as they are. `main()` uses `SCOPES` as the `--scope` choices; it is now the core's tuple, with the same three values.

In `.claude/skills/dataset-analysis/SKILL.md`, replace:

```markdown
mode=ro`; none of the three ever writes a label file, a dataset or the cache. They are
self-contained (no project imports) until `deeplabeling.core` exists — port them to
import its label parsing and geometry instead of reimplementing it, once it does.
```

with:

```markdown
mode=ro`; none of the three ever writes a label file, a dataset or the cache.
`overlaps.py` imports its label parsing and overlap predicate from `deeplabeling.core`,
so it agrees with the app. `unmatched.py` and `size_cut_sim.py` still parse labels
themselves; they move onto the core with slice 4's port of the matching code.
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings tests/core/test_core_imports_no_qt.py tests/test_dataset_scripts.py -q`
Expected: all pass, the four earlier overlap tests included.

Also confirm the script still runs as a script: `/home/sonnn/miniconda3/bin/python3 .claude/skills/dataset-analysis/scripts/overlaps.py /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/1_data5 --min 0.99 --max 1 --scope same --list 3`
Expected: a "N file(s) with a same-class pair…" line, then at most 3 files. It is read-only.

- [ ] **Step 5: Update the knowledge docs**

Make each replacement exactly; the old text is quoted from the current files.

`docs/knowledge/label-files.md`, in **Line format**, replace:

```markdown
**Rule:** polygons, extra columns and unparsable lines survive every round trip. Show a
polygon by its extent; never write the extent in its place unless the user edited that
polygon's geometry (whether DeepLabeling edits polygons is the app design's call).
```

with:

```markdown
**Rule:** polygons, extra columns and unparsable lines survive every round trip. Show a
polygon by its extent and never write the extent in its place: DeepLabeling refuses to
move or resize a polygon
([app design](../design/2026-10-04-app-foundation.md#lines-the-editor-cannot-change)).
```

In **Reading**, replace:

```markdown
- Read bytes and decode (`utf-8`, `errors="replace"`), then split with
  `splitlines(keepends=True)` so each line keeps its own terminator:
  `legacy/yolo_labeling/core/labelio.py::read_label_file`.
```

with:

```markdown
- Read bytes and decode with `surrogateescape`, then split with
  `splitlines(keepends=True)` so each line keeps its own terminator:
  `src/deeplabeling/core/labelio.py::parse_label_bytes`. With `surrogateescape` the round
  trip is exact for any bytes; the legacy reader's `errors="replace"`
  (`legacy/yolo_labeling/core/labelio.py::read_label_file`) turned a byte that is not
  UTF-8 into U+FFFD, which the next write then kept.
```

In **Writing**, replace:

```markdown
  terminators pass through untranslated.
- **Trailing newline.**
```

with:

```markdown
  terminators pass through untranslated.
- **Permissions kept.** The replacement keeps the target's permission bits, and a new
  file gets `0o666` less the umask: `src/deeplabeling/core/atomic.py::write_atomic`. A
  bare `mkstemp` creates `0600`, as the legacy writer's did
  ([legacy-defects.md](legacy-defects.md#not-fixed-in-the-legacy-app)).
- **Line endings.** A re-serialised line keeps a CRLF ending, and an appended line uses
  the file's last line ending (`src/deeplabeling/core/edits.py::materialize`), so a CRLF
  file stays CRLF.
- **Trailing newline.**
```

In **One path resolver**, replace:

```markdown
- One resolver maps an image to its label file, and reading and writing use the same one:
  `legacy/yolo_labeling/core/paths.py::LabelPathResolver`. Order:
  1. an explicit label folder;
  2. the longest matching per-folder mapping from `data.yaml`;
  3. convention: `…/images/x.jpg` pairs with `…/labels/x.txt`; otherwise a `labels`
     directory beside or above the image, preferring one that exists.
- Prefix matching respects path boundaries
```

with:

```markdown
- One rule maps an image to its label file, and reading and writing use the same one.
  DeepLabeling's is training's own (ultralytics' `img2label_paths`): the last `images`
  folder in the path becomes `labels` and the extension `.txt`, which leaves the `.txt`
  beside an image with no `images` folder in its path:
  `src/deeplabeling/core/paths.py::training_label_path`.
  A folder launch with an explicit label folder uses `<folder>/<stem>.txt`; a folder
  launch with neither is refused, never guessed
  ([app design](../design/2026-10-04-app-foundation.md#dataset)).
- The legacy resolver (`legacy/yolo_labeling/core/paths.py::LabelPathResolver`) tried an
  explicit folder, then the longest yaml folder mapping, then convention with fallbacks.
  On pvn-vehicle it agrees with training's rule for every image (measured 2026-10-04;
  the command is in the [app design](../design/2026-10-04-app-foundation.md#dataset)).
- In the legacy resolver, prefix matching respects path boundaries
```

`docs/knowledge/caches.md`, in **Label-cache freshness**, replace:

```markdown
- Size alone is not enough: reassigning a class rewrites one byte and keeps the length.
```

with:

```markdown
- Size alone is not enough: reassigning a class rewrites one byte and keeps the length.
- DeepLabeling stamps `(inode, mtime_ns, size)`
  (`src/deeplabeling/core/store.py::LabelStore.get`): an atomic replace makes a new
  inode, so a same-size rewrite within one mtime tick is still noticed.
```

In **Where app state lives**, replace:

```markdown
- DeepLabeling's directory is provisional:
  [design spec](../design/2026-10-02-project-init.md#package-skeleton).
```

with:

```markdown
- DeepLabeling's is `<repository>/.deeplabeling/`, or `DEEPLABELING_STATE_DIR` when set:
  `src/deeplabeling/core/state.py::state_dir`. Its layout is in the
  [app design](../design/2026-10-04-app-foundation.md#state-and-settings); the tests
  guard it with `tests/conftest.py::_real_state_untouched`.
```

`docs/knowledge/legacy-defects.md`, in **Not fixed in the legacy app**, replace the cell:

```markdown
| decide in the app design what counts as reviewed |
```

with:

```markdown
| only an edit, done & next or mark page marks an image ([app design](../design/2026-10-04-app-foundation.md#review-marks)) |
```

After the table's last row (`| Inference coverage counts the loaded model's rows, … | a coverage readout states its denominator |`), add the row:

```markdown
| Every label file the legacy app edited became private (mode `0600`): `mkstemp` creates `0600`, and `os.replace` keeps it. Found by reading the code; counted 2026-10-04 with the command below — 1,987 pvn-vehicle label files are `0600`, the rest `0664` | `legacy/yolo_labeling/core/labelio.py::write_label_file` | an atomic write keeps the target's permission bits: `src/deeplabeling/core/atomic.py::write_atomic` |
```

Then replace the file's last paragraph, which begins "Scope limits SPEC §9 lists that are choices rather than defects — decide each in the app design:" and ends with its link to the prediction-maps section of `datasets.md`, with:

````markdown
```sh
find /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle -name '*.txt' -path '*labels*' -perm 600 | wc -l
```

Scope limits SPEC §9 lists that are choices rather than defects, as the
[app design](../design/2026-10-04-app-foundation.md) decided them: a polygon cannot be
moved or resized, only reclassified or deleted; images are found the way training finds
them, recursively; viewing an image never marks it reviewed; a second DeepLabeling on the
same dataset root is refused; per-dataset state is keyed on the canonical root.
EXIF-rotated images still need labels in the rotation-applied geometry, semantic
segmentation stays out of scope, and Find Bad can only check distinctions the model can
make ([datasets.md](datasets.md#prediction-maps-and-class-groups)).
````

`docs/knowledge/environment.md`, in **Python**, after the bullet that begins "- conda base (`/home/sonnn/miniconda3`): Python 3.10.12, PySide6 6.6.0, pytest-qt", add:

```markdown
- A shell can have another conda env active: in the 2026-10-04 session bare `python3` was
  the `insightface` env, which has no PySide6. Use base's interpreter,
  `/home/sonnn/miniconda3/bin/python3`, or `conda activate base` first.
```

`CLAUDE.md`, replace:

```markdown
**Status:** project scaffold. The app itself is designed next; see
[docs/design/](docs/design/).
```

with:

```markdown
**Status:** slice 1's headless core is built (`src/deeplabeling/core/`); its Qt UI is
next. The design and the plans are in [docs/design/](docs/design/).
```

- [ ] **Step 6: Fold the spec amendments into the spec**

In `docs/design/2026-10-04-app-foundation.md`:

1. Replace `**Status:** draft 2026-10-04 · awaiting review` with `**Status:** approved 2026-10-04 · slice 1a (the core) implemented; the amendments found while planning it are folded in`.
2. In **Architecture**, replace the `core/` part of the tree with:

```
  core/                 imports no PySide6, enforced by a test; scripts import it too
    atomic.py           the one atomic writer; keeps permission bits
    labelio.py          port: LabelLine, parse, render, locate_line
    paths.py            the label-path rule (see Dataset)
    geometry.py         port: iou, normalised <-> pixel, clamp
    dataset.py          Dataset: from a yaml or a folder pair
    edits.py            LineRef, intents, Edit (bytes before/after per file), materialize
    store.py            LabelStore: the one owner of every image's labels
    history.py          global undo/redo of Edits
    editor.py           apply / undo / redo: write, record, mark reviewed, notify
    overlap.py          stack counts (the predicate slice 3's overlap filter reuses)
    queue.py            Condition, ImageFilter, QueueItem, Queue (cursor, statuses)
    review.py           review marks
    settings.py         the settings registry
    state.py            where app state lives; the per-root lock
    taxonomy.py         the taxonomy guard's checks
    workspace.py        Workspace.open: the one funnel every launch path goes through
```

3. In **Architecture**, replace "and only `LabelStore.apply` writes one, through `labelio`'s\natomic writer." with "and only `LabelStore.apply` and `LabelStore.restore` write one,\nthrough `atomic.write_atomic`."
4. In **Snapshots**, replace "the file's `(mtime_ns, size)` stamp" with "the file's `(inode, mtime_ns, size)` stamp".
5. In **Edits**, replace step 4 ("4. updates the snapshot, pushes the Edit onto the history, marks the image reviewed, and\n   emits `labelsChanged`.") with:

```markdown
4. updates the snapshot. `Editor.apply`, the GUI thread's one entry point, then pushes
   the Edit onto the history, marks the image reviewed and emits `labelsChanged`.
```

6. In **Port order (slice 1)**, replace items 1–6 with:

```markdown
1. `labelio` and `geometry`: ported with their tests.
2. `paths`: rewritten to training's rule.
3. `overlap`: the stack count from
   `legacy/yolo_labeling/app.py::YOLOLabelingTool.detect_current_overlaps`.
4. New code: `atomic`, `dataset`, `edits`, `store`, `history`, `editor`, `queue`,
   `review`, `settings`, `state`, `taxonomy`, `workspace`.
5. The UI.

`imagetype`, and `imagesize` (from
`legacy/yolo_labeling/ui/filters.py::FiltersMixin._image_size`), wait for slice 3: nothing
in slice 1 needs them, because the UI takes sizes from Qt's decode.
```

7. In **Docs to update in slice 1**, add a bullet:

```markdown
- [environment.md](../knowledge/environment.md#python): which interpreter to use when
  another conda env is active.
```

- [ ] **Step 7: Check the docs and run everything**

Run: `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py`
Expected: exit 0 and no FAIL lines. A WARN for an external path is acceptable only if that path really is absent.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -p no:warnings`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add tests/core/test_core_imports_no_qt.py tests/test_dataset_scripts.py .claude/skills/dataset-analysis docs CLAUDE.md
git commit -m "core: enforce no Qt in core; overlaps.py uses the core; docs match the code" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git status --short
```

Expected: `git status --short` prints nothing.
