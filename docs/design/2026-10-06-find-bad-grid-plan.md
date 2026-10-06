# Slice 4c: Find Bad in the grid — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish slice 4:
- the grid shows each finding as its crop, the label and the model's box drawn on it;
- several selected tiles take `M`, `B`, `D`, `Delete` or a class key together, as one edit;
- the performance targets are measured with the real model.

**Architecture:**
- `ui/images.py` decodes a crop with `QImageReader`'s clip and scaled size, so a crop of a large frame costs a fraction of its decode. The crop is given in the pixels of the image as shown; `_stored_rect` turns it back through the EXIF orientation into the pixels the file stores. `ImageCache` takes a key function, so the session keeps a third cache of crops, keyed by `Crop(path, rect)`.
- `ui/queue_panel.py` paints a finding's tile from that cache. It draws the label and the model's box as the spotlight does, and captions the tile `car → person 0.80`. A grid of crops selects several tiles and offers no *Mark page*.
- `ui/grid_actions.py` turns a key on several findings into one `Editor.apply_many` edit, which marks nothing reviewed. Findings the key cannot apply to are skipped and counted. `MainWindow._either` sends a key to the tiles when several are selected, and to the full frame otherwise.

**Tech Stack:** Python 3.10 (conda base), PySide6, pytest-qt; plans 4a and 4b.

**Spec:** [2026-10-06-find-bad.md](2026-10-06-find-bad.md). This plan implements:
- *Window → The grid*;
- the grid's rows in *Errors*;
- *Performance targets*.

## Global Constraints

- **Interpreter:** `/home/sonnn/miniconda3/bin/python3` (conda base). Install nothing ([environment.md](../knowledge/environment.md#python)).
- **Every label change goes through `Editor`** ([landmine 1](../../CLAUDE.md#landmines)). A grid action is one `apply_many` edit, undone whole, and it marks nothing reviewed: a crop is not the image.
- **The GUI thread never decodes:** crops decode on the cache's jobs, as thumbnails do ([landmine 3](../../CLAUDE.md#landmines)).
- **A UI change is verified by what is visible** ([landmine 4](../../CLAUDE.md#landmines)):
  - tiles are read back from their pixels;
  - crops are compared with the canvas's own decode;
  - the multi-selection and the captions are looked at in a screenshot.
- **The measurement is read-only:** app state goes to a temporary folder, and nothing in the dataset is written ([landmine 9](../../CLAUDE.md#landmines), [landmine 10](../../CLAUDE.md#landmines)). Run it from the repository root, which resolves `ultralytics` to the editable install ([landmine 8](../../CLAUDE.md#landmines)).
- **Doc rules:** one fact, one home; cite code as `` `<path>.py::<symbol>` ``. Run `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py` after doc edits.
- **Git:** branch `slice4-find-bad-grid` from `main`. One commit per task, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Every task ends green:** `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q` passes before its commit.

## Review Focus

These are the inputs most likely to hurt someone cleaning from the grid. Each has a named test:

1. **A phone photo with an EXIF orientation.** Its crop is the region the label marks, not a mirrored or turned one. *(Task 1 `test_a_crop_is_the_shown_image_cut_and_scaled`, all eight orientations, every pixel.)*
2. **Two findings of one image, fixed together.** One intent carries both ops, and one undo restores both files. *(Task 3 `test_m_on_several_tiles_is_one_edit_that_marks_nothing`.)*
3. **A selection that includes a read-only (shared) label file.** That finding is skipped and counted; the rest is one edit, not a rollback. *(Task 3 `test_a_shared_label_file_is_skipped_and_the_rest_is_one_edit`.)*
4. **A selection that includes a finding already fixed in the full frame.** It is skipped as changed since, and the edit is not refused. *(Task 3 `test_a_finding_whose_line_changed_since_is_skipped`.)*
5. **An image that cannot be decoded.** Its tile says so, and does not spin forever. *(Task 2 `test_a_tile_whose_image_cannot_be_decoded_says_so`.)*

## Found while building this plan

The plan's code was built in a scratch copy first, and its suite ran green there (904 passed).

- **`QImageReader.setClipRect` takes the stored pixels, before the EXIF turn.** Qt mirrors and flips a stored image as its orientation says, then turns it a quarter clockwise, with Rotate270 a turn of its own. `_stored_rect` undoes those steps, and the scaled size is transposed for a quarter turn. A test with flat quadrants passed even with the mirror undone, so the orientation test uses a gradient: every pixel has its own colour, and all of them are compared.
- **Long tile captions elided their middle**, which lost the finding: "0005.jpg · wr…_m → car 0.95". A finding's tile now reads `bus_m → car 0.95 · fixed`, and the list row and the tooltip keep the path.
- **A grid action that meets a changed line would refuse the whole batch:** `Editor.apply_many` rolls everything back on one `Refused`. So `grid_actions` checks each finding's line first (`locate_line`), and skips and counts those that moved.

## Decisions this plan makes

- **A crop is scaled to fill the tile's picture area (160 × 120), enlarged when small:** a 15 × 12 px crop is drawn ten times its size.
- **Several tiles, not one, make a grid action.** A single selected tile is the current finding, and keys act on it as in the full frame: it moves on and marks the image reviewed.
- **`D` on several tiles dismisses those not yet dismissed.** When all of them are dismissed already, it takes them all back. One save covers it.
- **The status bar says what was done and what was skipped**: `took the model's class on 3 findings, as one edit; skipped 1 (the model has no class for it)`.
- ***Mark page* is hidden on a grid of crops**, and refuses if reached: a crop is not the image.

## File map

| File | Responsibility | Task |
|---|---|---|
| `src/deeplabeling/ui/images.py` | `Crop`, `_stored_rect`, `decode_crop`; `ImageCache(key=…)`; `TILE_PICTURE`, `decode_tile` | 1, 2 |
| `src/deeplabeling/ui/findview.py` | `label_color`, `finding_caption` | 2 |
| `src/deeplabeling/ui/session.py` | `Session.crops`, `crop_of`; `apply_many` | 2, 3 |
| `src/deeplabeling/ui/queue_panel.py` | crop tiles; *Mark page* withheld; multi-select, `selected_findings` | 2, 3 |
| `src/deeplabeling/ui/grid_actions.py`, `main_window.py` | the keys on several tiles | 3 |
| `tools/measure_find_bad.py`, the spec, `CLAUDE.md` | the measurements; the status | 4 |

---

### Task 1: Decoding a crop

**Files:**
- Create: `tests/ui/test_crop_decode.py`
- Modify: `src/deeplabeling/ui/images.py`

**Interfaces:**
- Consumes: `decode_image`, `ImageCache`, `Jobs` (slice 1).
- Produces, in `deeplabeling.ui.images`:
  - `Crop(path, rect)`, a `NamedTuple`, with `Crop.of(key)`, which normalises the path;
  - `decode_crop(path, rect, fit) -> QImage`, where `rect` is (x1, y1, x2, y2) in the shown image's pixels and `fit` is (w, h); it raises `ValueError` for an unreadable file;
  - `ImageCache(..., *, key=Path)`.

- [ ] **Step 1: Commit this plan, on a new branch**

```bash
cd /home/sonnn/Documents/PGit/DeepLabeling
git checkout -b slice4-find-bad-grid main
git add docs/design/2026-10-06-find-bad-grid-plan.md
git commit -m "docs: the slice 4c plan, Find Bad in the grid" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/ui/test_crop_decode.py`:

```python
"""A finding's crop, clipped and scaled as it is decoded, EXIF orientation honoured
(docs/design/2026-10-06-find-bad.md#the-grid)."""

import pytest
from PIL import Image
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor

from deeplabeling.ui.images import Crop, ImageCache, decode_crop, decode_image
from deeplabeling.ui.workers import Jobs



def pattern(path, orientation, size=(64, 48)):
    """A stored gradient -- red across, green down: every pixel its own colour -- tagged
    with an EXIF orientation."""
    w, h = size
    im = Image.new("RGB", size)
    im.putdata([(255 * x // (w - 1), 255 * y // (h - 1), 128) for y in range(h) for x in range(w)])
    exif = Image.Exif()
    exif[274] = orientation
    im.save(path, quality=95, exif=exif.tobytes())
    return path


def difference(a, b) -> float:
    """The mean difference per channel, over every pixel."""
    total = 0
    for y in range(a.height()):
        for x in range(a.width()):
            p, q = QColor(a.pixel(x, y)), QColor(b.pixel(x, y))
            total += abs(p.red() - q.red()) + abs(p.green() - q.green()) + abs(p.blue() - q.blue())
    return total / (3 * a.width() * a.height())


@pytest.mark.parametrize("orientation", range(1, 9))
def test_a_crop_is_the_shown_image_cut_and_scaled(tmp_path, orientation):
    path = pattern(tmp_path / f"o{orientation}.jpg", orientation)
    shown = decode_image(path)                                  # the canvas's picture
    rect = (4, 2, 40, 30)                                       # in the shown image's pixels
    crop = decode_crop(path, rect, (160, 120))
    want = shown.copy(QRect(4, 2, 36, 28)).scaled(QSize(160, 120), Qt.KeepAspectRatio, Qt.SmoothTransformation)
    assert crop.size() == want.size() and difference(crop, want) < 6


def test_a_small_crop_is_enlarged_to_fill_the_tile_and_a_large_one_shrunk(tmp_path):
    path = pattern(tmp_path / "p.jpg", 1, (640, 480))
    assert decode_crop(path, (0, 0, 16, 12), (160, 120)).size() == QSize(160, 120)
    assert decode_crop(path, (0, 0, 640, 240), (160, 120)).size() == QSize(160, 60)


def test_an_unreadable_image_is_refused(tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not a jpeg")
    with pytest.raises(ValueError):
        decode_crop(bad, (0, 0, 4, 4), (160, 120))


def test_crops_are_cached_by_image_and_rect(qtbot, tmp_path):
    path = pattern(tmp_path / "p.jpg", 6)
    cache = ImageCache(Jobs(1), decode=lambda c: decode_crop(c.path, c.rect, (160, 120)), key=Crop.of)
    a, b = Crop(path, (0, 0, 8, 8)), Crop(path, (8, 8, 24, 24))
    with qtbot.waitSignals([cache.ready, cache.ready], timeout=5000):
        cache.want([a, b])
    assert cache.get(a) is not None and cache.get(b) is not None and cache.get(a) != cache.get(b)
    assert cache.get(Crop(str(path), (0, 0, 8, 8))) is cache.get(a)       # a str path is the same image
```

- [ ] **Step 3: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_crop_decode.py`
Expected: `cannot import name 'Crop'`.

- [ ] **Step 4: Decode a crop through the EXIF turn; key the cache**

In `src/deeplabeling/ui/images.py`, replace:

```python
"""Decoding images and thumbnails on workers, into caches bounded in bytes
(docs/design/2026-10-04-app-foundation.md#window)."""

from __future__ import annotations
```

with:

```python
"""Decoding images, thumbnails and findings' crops on workers, into caches bounded in
bytes (docs/design/2026-10-04-app-foundation.md#window,
docs/design/2026-10-06-find-bad.md#the-grid)."""

from __future__ import annotations
```

In `src/deeplabeling/ui/images.py`, replace:

```python
from collections.abc import Callable, Iterable
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage, QImageReader

from .workers import Handle, Jobs
```

with:

```python
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import NamedTuple

from PySide6.QtCore import QObject, QRect, QSize, Qt, Signal
from PySide6.QtGui import QImage, QImageIOHandler, QImageReader

from .workers import Handle, Jobs
```

In `src/deeplabeling/ui/images.py`, replace:

```python


class ImageCache(QObject):
    """Decoded images by path. The images it is told to keep -- the current one and
```

with:

```python


class Crop(NamedTuple):
    """A finding's crop: an image and a rect (x1, y1, x2, y2) in its pixels as shown."""

    path: Path
    rect: tuple[int, int, int, int]

    @classmethod
    def of(cls, key) -> Crop:
        """The cache key: the same image, however its path was spelled."""
        return cls(Path(key.path), tuple(key.rect))


def _stored_rect(rect, w: int, h: int, turn) -> QRect:
    """`rect`, in the pixels of the image as shown, in the pixels the file stores (w x h).
    Qt shows a stored image mirrored and flipped as its EXIF says, then turned a quarter
    clockwise; this undoes that, a corner at a time."""
    T = QImageIOHandler.Transformation
    x1, y1, x2, y2 = rect
    corners = [(x1, y1), (x2, y2)]
    if turn == T.TransformationRotate270:
        corners = [(w - y, x) for x, y in corners]          # a quarter anticlockwise, undone
    else:
        if turn & T.TransformationRotate90:
            corners = [(y, h - x) for x, y in corners]
        if turn & T.TransformationMirror:
            corners = [(w - x, y) for x, y in corners]
        if turn & T.TransformationFlip:
            corners = [(x, h - y) for x, y in corners]
    (ax, ay), (bx, by) = corners
    return QRect(min(ax, bx), min(ay, by), abs(bx - ax), abs(by - ay))


def decode_crop(path, rect: tuple[int, int, int, int], fit: tuple[int, int]) -> QImage:
    """The part `rect` of the image as shown (EXIF orientation applied), scaled to fill
    `fit` with its aspect kept -- enlarged when it is smaller. The decoder clips and scales
    as it reads, so a crop of a large frame costs a fraction of its decode. Raises
    ValueError like decode_image."""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    stored, turn = reader.size(), reader.transformation()
    if not stored.isValid():
        raise ValueError(reader.errorString() or "not an image")
    x1, y1, x2, y2 = rect
    size = QSize(x2 - x1, y2 - y1).scaled(QSize(*fit), Qt.KeepAspectRatio)
    if turn & QImageIOHandler.Transformation.TransformationRotate90:
        size.transpose()                                    # scaled before it is turned
    reader.setClipRect(_stored_rect(rect, stored.width(), stored.height(), turn))
    reader.setScaledSize(size)
    image = reader.read()
    if image.isNull():
        raise ValueError(reader.errorString() or "not an image")
    return image


class ImageCache(QObject):
    """Decoded images by path. The images it is told to keep -- the current one and
```

In `src/deeplabeling/ui/images.py`, replace:

```python

    def __init__(self, jobs: Jobs, limit_bytes: int = 512 * 2**20,
                 decode: Callable[[Path], QImage] = decode_image, parent=None):
        super().__init__(parent)
        self._jobs = jobs
        self._limit = limit_bytes
        self._decode = decode
```

with:

```python

    def __init__(self, jobs: Jobs, limit_bytes: int = 512 * 2**20,
                 decode: Callable[[Path], QImage] = decode_image, parent=None, *, key: Callable = Path):
        super().__init__(parent)
        self._jobs = jobs
        self._key = key                 #: what a request names, as the cache keys it: a Path, or a Crop
        self._limit = limit_bytes
        self._decode = decode
```

In `src/deeplabeling/ui/images.py`, replace:

```python

    def get(self, path) -> QImage | None:
        path = Path(path)
        image = self._images.get(path)
        if image is not None:
```

with:

```python

    def get(self, path) -> QImage | None:
        path = self._key(path)
        image = self._images.get(path)
        if image is not None:
```

In `src/deeplabeling/ui/images.py`, replace:

```python

    def error(self, path) -> str | None:
        return self._errors.get(Path(path))

    def keep(self, paths: Iterable) -> None:
        """Decode these, in this order, and keep them whatever the budget."""
        paths = [Path(p) for p in paths]
        self._keep = set(paths)
        for path in paths:
```

with:

```python

    def error(self, path) -> str | None:
        return self._errors.get(self._key(path))

    def keep(self, paths: Iterable) -> None:
        """Decode these, in this order, and keep them whatever the budget."""
        paths = [self._key(p) for p in paths]
        self._keep = set(paths)
        for path in paths:
```

In `src/deeplabeling/ui/images.py`, replace:

```python
        """Keep these and cancel every other decode still waiting: the tiles in view,
        when a scroll has taken the earlier ones out of it."""
        paths = [Path(p) for p in paths]
        wanted = set(paths)
        for path in [p for p in self._pending if p not in wanted]:
```

with:

```python
        """Keep these and cancel every other decode still waiting: the tiles in view,
        when a scroll has taken the earlier ones out of it."""
        paths = [self._key(p) for p in paths]
        wanted = set(paths)
        for path in [p for p in self._pending if p not in wanted]:
```

In `src/deeplabeling/ui/images.py`, replace:

```python

    def request(self, path) -> None:
        path = Path(path)
        if path in self._images or path in self._errors or path in self._pending:
            return
```

with:

```python

    def request(self, path) -> None:
        path = self._key(path)
        if path in self._images or path in self._errors or path in self._pending:
            return
```

- [ ] **Step 5: Run the tests to see them pass, then the full suite, then commit**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_crop_decode.py tests/ui/test_images.py`
Expected: 27 passed.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 890 passed.

```bash
git add src/deeplabeling/ui/images.py tests/ui/test_crop_decode.py
git commit -m "ui: a finding's crop, clipped and scaled as it decodes, through the EXIF turn" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Crop tiles

**Files:**
- Create: `tests/ui/test_crop_tiles.py`
- Modify: `src/deeplabeling/ui/images.py`, `src/deeplabeling/ui/findview.py`, `src/deeplabeling/ui/session.py`, `src/deeplabeling/ui/queue_panel.py`, `tests/ui/test_finding_view.py`

**Interfaces:**
- Consumes:
  - from Task 1: `Crop`, `decode_crop`, `ImageCache(key=…)`;
  - from plan 4a: `crop_rect`;
  - from plan 4b: `spotlight`, `Session.finding_state`, `finding_rows`.
- Produces:
  - `TILE_PICTURE = (160, 120)` and `decode_tile(crop)`;
  - `Session.crops`, an `ImageCache` keyed by `Crop.of`, cleared on close;
  - `Session.crop_of(item) -> Crop | None`;
  - `findview.label_color(f, dataset, colors)` and `findview.finding_caption(f, dataset)`;
  - in `queue_panel`:
    - a finding's tile is its crop, with the label and the model's box drawn on it;
    - `tile_text` gives a finding's caption;
    - `QueuePanel._suit_source` hides *Mark page* on crops, and `mark_page` refuses there.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_crop_tiles.py`:

```python
"""A findings queue's grid: each tile the finding's crop, its label and the model's box
drawn on it (docs/design/2026-10-06-find-bad.md#the-grid)."""

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor

import deeplabeling.ui.model as model_module
from deeplabeling.core.findings import Findings
from deeplabeling.core.workspace import CLASS_COLORS
from deeplabeling.ui.classes import class_color
from deeplabeling.ui.images import Crop
from deeplabeling.ui.queue_panel import tile_thumb_rect
from drive import start
from finding_rows import PERSON, P, factory, load, put_rows

NEAR = (0.27, 0.25, 0.1, 0.1)       #: the model's box for camA/0001's car: IoU 0.67, 1.28 px to the right
ROWS = {"camA/images/0001.jpg": [P(1, NEAR, 0.8), P(1, PERSON, 0.9)],
        "bad/images/corrupt.jpg": [P(0, (0.4, 0.4, 0.2, 0.2), 0.9)]}       # its person: a car, says the model


@pytest.fixture
def window(qtbot, ds, tmp_path, monkeypatch):
    monkeypatch.setattr(model_module, "UltralyticsPredictor", factory)
    w = start(qtbot, [str(ds.yaml)])
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    load(qtbot, w.session, weights)
    put_rows(w.session, ROWS)
    w.session.set_queue(Findings())
    qtbot.waitUntil(lambda: w.session.queue.complete, timeout=5000)
    w.queue_panel.set_grid(True)
    w.resize(1200, 800)
    qtbot.wait(50)
    yield w
    w.close()


def row_of(session, key):
    return session.queue.index_of(key)


def tile(panel, row):
    return panel.view.visualRect(panel.model.index(row))


def shot(panel):
    return panel.view.viewport().grab().toImage()


def column(image, x, y1, y2):
    return [QColor(image.pixel(x + dx, y)) for dx in (-1, 0, 1) for y in range(y1, y2)]


def test_a_finding_tile_is_its_crop_with_the_label_and_the_model_s_box(qtbot, window):
    session, panel = window.session, window.queue_panel
    key = "camA/images/0001.jpg#1#wrong class"
    crop = Crop(session.queue.items[row_of(session, key)].entry.path, (9, 6, 24, 18))
    assert session.crop_of(session.queue.items[row_of(session, key)]) == crop
    qtbot.waitUntil(lambda: session.crops.get(crop) is not None, timeout=5000)
    qtbot.wait(20)
    target = tile_thumb_rect(tile(panel, row_of(session, key)), QSize(150, 120))     # 15 x 12 px, ten times
    image = shot(panel)
    car = QColor(class_color(1, "car", session.workspace.root_settings.get(CLASS_COLORS)))
    # The label (x 12.8-19.2 px) runs from 38 to 102 in the tile; the model's box from 51 to 115.
    assert any(abs(c.red() - car.red()) < 40 and abs(c.green() - car.green()) < 40 and abs(c.blue() - car.blue()) < 40
               for c in column(image, target.x() + 38, target.y() + 40, target.y() + 80))
    assert any(c.red() > 200 and c.green() < 80 and 40 < c.blue() < 120               # the person's #e6194b
               for c in column(image, target.x() + 115, target.y() + 40, target.y() + 80))
    assert session.thumbs.get(crop.path) is None                                       # the crop, not the frame


def test_a_tile_whose_image_cannot_be_decoded_says_so(qtbot, window):
    session, panel = window.session, window.queue_panel
    row = row_of(session, "bad/images/corrupt.jpg#0#wrong class")
    assert row is not None and session.crop_of(session.queue.items[row]) is None
    session.go_to(session.queue.items[row].key)
    qtbot.wait(50)
    cell = tile(panel, row)
    image = shot(panel)
    light = sum(QColor(image.pixel(x, y)).lightness() > 170
                for x in range(cell.left() + 40, cell.right() - 40) for y in range(cell.top() + 50, cell.top() + 80))
    assert light > 20                                       # "cannot decode" is written where the crop goes


def test_mark_page_is_not_offered_on_crops(qtbot, window):
    panel = window.queue_panel
    assert not panel.mark_button.isVisible()
    with qtbot.waitSignal(window.session.status) as said:
        panel.mark_page()
    assert said.args == ["the tiles are crops, not whole images: nothing was marked"]
    assert len(window.session.workspace.review.keys()) == 0
    window.session.set_queue(window.session.queue.source.scope)
    qtbot.waitUntil(lambda: window.session.queue.complete, timeout=5000)
    assert panel.mark_button.isVisible()
```

In `tests/ui/test_finding_view.py`, replace:

```python


def test_a_tile_names_its_image_and_is_ticked_by_it(qtbot, window):
    session = window.session
    item = session.queue.items[1]
    assert tile_text(session, item) == "0001.jpg · wrong class: car → person 0.80"
    session.mark_reviewed([item.key])
    assert tile_text(session, item).startswith("✓ 0001.jpg")


```

with:

```python


def test_a_tile_names_the_label_the_model_s_call_and_its_state(qtbot, window):
    session = window.session
    first, item, nothing = session.queue.items
    assert tile_text(session, item) == "car → person 0.80"
    assert tile_text(session, nothing) == "bus_m → nothing 1.00"
    session.mark_reviewed([item.key])
    assert tile_text(session, item) == "✓ car → person 0.80"
    session.go_to(first.key)
    session.dismiss_current()
    assert tile_text(session, first) == "bus_m → car 0.95 · dismissed"


```

In `tests/ui/test_finding_view.py`, replace:

```python
    window.edit_queue()
    assert window.prompter.asked[-1][1] == Findings()
```

with:

```python
    window.edit_queue()
    assert window.prompter.asked[-1][1] == Findings()


@pytest.mark.parametrize("finding, text", [
    (Finding(1, "", "wrong class", 0.82, 1, CAR, 0, CAR, 0.82), "car → person 0.82"),
    (Finding(1, "", "not an object", 0.97, 2, CAR), "bus_m → nothing 0.97"),
    (Finding(1, "", "weakly seen", 0.59, 1, CAR, 1, CAR, 0.41), "car → car 0.41"),
])
def test_a_tile_caption_is_short(ds, finding, text):
    from deeplabeling.core.dataset import Dataset
    from deeplabeling.ui.findview import finding_caption

    assert finding_caption(finding, Dataset.open(ds.yaml)) == text
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_crop_tiles.py tests/ui/test_finding_view.py`
Expected: 7 failed, 12 passed: `crop_of`.

- [ ] **Step 3: Paint a finding's tile from its crop**

In `src/deeplabeling/ui/images.py`, replace:

```python
THUMB_PX = 160                  #: a thumbnail's longer side, at most
THUMB_BYTES = 64 * 2**20        #: the thumbnail cache's budget (the spec)


```

with:

```python
THUMB_PX = 160                  #: a thumbnail's longer side, at most
THUMB_BYTES = 64 * 2**20        #: the thumbnail cache's budget (the spec)
TILE_PICTURE = (THUMB_PX, 120)  #: a grid tile's picture area: a crop is scaled to fill it


```

In `src/deeplabeling/ui/images.py`, replace:

```python
    if image.isNull():
        raise ValueError(reader.errorString() or "not an image")
    return image


class ImageCache(QObject):
```

with:

```python
    if image.isNull():
        raise ValueError(reader.errorString() or "not an image")
    return image


def decode_tile(crop: Crop) -> QImage:
    """A finding's tile: its crop, scaled to fill the tile's picture area."""
    return decode_crop(crop.path, crop.rect, TILE_PICTURE)


class ImageCache(QObject):
```

In `src/deeplabeling/ui/findview.py`, replace:

```python


def finding_text(f: Finding, dataset: Dataset) -> str:
    """`wrong class: car → truck 0.82`, `not an object: bus_m (nearest 0.03)`, `weakly seen: car 0.41`."""
```

with:

```python


def label_color(f: Finding, dataset: Dataset, colors: dict[str, str]) -> str:
    """The colour the label is drawn in: its class's, grey for an id the names lack."""
    return class_color(f.label_cls, _name(f.label_cls, dataset), colors) if 0 <= f.label_cls < len(dataset.names) \
        else UNKNOWN


def finding_text(f: Finding, dataset: Dataset) -> str:
    """`wrong class: car → truck 0.82`, `not an object: bus_m (nearest 0.03)`, `weakly seen: car 0.41`."""
```

In `src/deeplabeling/ui/findview.py`, replace:

```python
        return f"not an object: {label} (nearest {1 - f.score:.2f})"
    return f"weakly seen: {label} {f.model_conf:.2f}"


```

with:

```python
        return f"not an object: {label} (nearest {1 - f.score:.2f})"
    return f"weakly seen: {label} {f.model_conf:.2f}"


def finding_caption(f: Finding, dataset: Dataset) -> str:
    """A crop tile's caption, short enough for it: `car → person 0.82`, `bus_m → nothing 0.97`.
    The number is the model's confidence, or for nothing there the finding's score."""
    label = _name(f.label_cls, dataset)
    if f.kind == "not an object":
        return f"{label} → nothing {f.score:.2f}"
    return f"{label} → {_name(f.model_cls, dataset)} {f.model_conf:.2f}"


```

In `src/deeplabeling/ui/session.py`, replace:

```python
from PySide6.QtCore import QObject, QTimer, Signal

from ..core.dataset import DatasetError, ImageEntry
from ..core.edits import CreateEmpty, Edit, Intent, Refused
```

with:

```python
from PySide6.QtCore import QObject, QTimer, Signal

from ..core.crops import crop_rect
from ..core.dataset import DatasetError, ImageEntry
from ..core.edits import CreateEmpty, Edit, Intent, Refused
```

In `src/deeplabeling/ui/session.py`, replace:

```python
from .classes import assign_classes
from .findview import finding_text
from .images import THUMB_BYTES, ImageCache, decode_thumb
from .model import ModelSession
from .settings_ui import Saver, global_settings, remember_source
```

with:

```python
from .classes import assign_classes
from .findview import finding_text
from .images import THUMB_BYTES, Crop, ImageCache, decode_thumb, decode_tile
from .model import ModelSession
from .settings_ui import Saver, global_settings, remember_source
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        self.images = ImageCache(Jobs(2), parent=self)
        self.thumbs = ImageCache(Jobs(2), THUMB_BYTES, decode=decode_thumb, parent=self)
        self.saver = Saver(self._save, parent=self)
        self._build = None
```

with:

```python
        self.images = ImageCache(Jobs(2), parent=self)
        self.thumbs = ImageCache(Jobs(2), THUMB_BYTES, decode=decode_thumb, parent=self)
        self.crops = ImageCache(Jobs(2), THUMB_BYTES, decode=decode_tile, parent=self, key=Crop.of)
        self.saver = Saver(self._save, parent=self)
        self._build = None
```

In `src/deeplabeling/ui/session.py`, replace:

```python
        self.images.clear()
        self.thumbs.clear()
        self.io.wait(2000)
        self.workspace, self.queue, self._build, self._by_rel = None, None, None, {}
```

with:

```python
        self.images.clear()
        self.thumbs.clear()
        self.crops.clear()
        self.io.wait(2000)
        self.workspace, self.queue, self._build, self._by_rel = None, None, None, {}
```

In `src/deeplabeling/ui/session.py`, replace:

```python
            self.status.emit("the dismissal is taken back")

    def describe_item(self, item: QueueItem) -> str:
        tick = "✓" if self._require().review.is_marked(item.entry.rel) else "·"
```

with:

```python
            self.status.emit("the dismissal is taken back")

    def crop_of(self, item: QueueItem) -> Crop | None:
        """The crop a finding's tile shows; None for an image item, or when the image's
        header cannot be read -- its crop could not be decoded either."""
        f = item.finding
        if f is None:
            return None
        size = self._require().sizes.get(item.entry.path)
        rect = None if size is None else crop_rect(f.label_box, f.model_box, *size)
        return None if rect is None else Crop(item.entry.path, rect)

    def describe_item(self, item: QueueItem) -> str:
        tick = "✓" if self._require().review.is_marked(item.entry.rel) else "·"
```

In `src/deeplabeling/ui/queue_panel.py`, replace:

```python
"""The queue panel (docs/design/2026-10-04-app-foundation.md#window): the queue as a
virtualised list, or as a grid of thumbnails with their label boxes drawn on them. One
view shows both, so there is one selection, and it mirrors the session's cursor -- there
is no second notion of the current item."""
```

with:

```python
"""The queue panel (docs/design/2026-10-04-app-foundation.md#window): the queue as a
virtualised list, or as a grid of thumbnails with their label boxes drawn on them -- or, for
findings, of their crops (docs/design/2026-10-06-find-bad.md#the-grid). One
view shows both, so there is one selection, and it mirrors the session's cursor -- there
is no second notion of the current item."""
```

In `src/deeplabeling/ui/queue_panel.py`, replace:

```python
)

from ..core.queue import QueueItem
from ..core.workspace import CLASS_COLORS
from .boxes import box_views
from .images import THUMB_PX
from .session import Session

TILE = QSize(176, 150)                      #: one grid cell
THUMB_AREA = QRect(8, 6, THUMB_PX, 120)     #: where a cell's thumbnail goes, within it
TILE_BG, TILE_TEXT, TILE_CURRENT = "#3a3a3a", "#e0e0e0", "#4a90d9"
WANT_MS = 30                                #: thumbnails are wanted this long after a scroll
```

with:

```python
)

from ..core.findings import Findings
from ..core.geometry import norm_to_px
from ..core.queue import QueueItem
from ..core.workspace import CLASS_COLORS
from .boxes import box_views
from .findview import finding_caption, label_color, spotlight
from .images import TILE_PICTURE
from .session import Session

TILE = QSize(176, 150)                      #: one grid cell
THUMB_AREA = QRect(8, 6, *TILE_PICTURE)     #: where a cell's thumbnail goes, within it
TILE_BG, TILE_TEXT, TILE_CURRENT = "#3a3a3a", "#e0e0e0", "#4a90d9"
WANT_MS = 30                                #: thumbnails are wanted this long after a scroll
```

In `src/deeplabeling/ui/queue_panel.py`, replace:

```python

def tile_text(session: Session, item: QueueItem, labels=None) -> str:
    """A tile's caption: the reviewed tick, the file name and the badge."""
    tick = "✓ " if session.workspace.review.is_marked(item.entry.rel) else ""
    return f"{tick}{Path(item.entry.rel).name} · {session.badge(item, labels)}"

```

with:

```python

def tile_text(session: Session, item: QueueItem, labels=None) -> str:
    """A tile's caption: the reviewed tick, then the file name and the badge -- or, on a
    finding's crop, what the label is and what the model calls it, and whether it is
    fixed or dismissed."""
    tick = "✓ " if session.workspace.review.is_marked(item.entry.rel) else ""
    if item.finding is not None:
        state = session.finding_state(item)
        return f"{tick}{finding_caption(item.finding, session.workspace.dataset)}" + (f" · {state}" if state else "")
    return f"{tick}{Path(item.entry.rel).name} · {session.badge(item, labels)}"

```

In `src/deeplabeling/ui/queue_panel.py`, replace:

```python
            painter.drawRect(cell.adjusted(3, 3, -4, -4))
        painter.setPen(QColor(TILE_TEXT))
        thumb = session.thumbs.get(item.entry.path)
        if thumb is None:
            why = session.thumbs.error(item.entry.path)
            painter.drawText(THUMB_AREA.translated(cell.topLeft()), Qt.AlignCenter,
                             "cannot decode" if why else "…")
        else:
            target = tile_thumb_rect(cell, thumb.size())
            painter.drawImage(target, thumb)
            self._draw_boxes(painter, labels, target)
        caption = QRect(cell.x() + 8, cell.y() + THUMB_AREA.bottom() + 4, cell.width() - 16,
                        cell.height() - THUMB_AREA.bottom() - 8)
```

with:

```python
            painter.drawRect(cell.adjusted(3, 3, -4, -4))
        painter.setPen(QColor(TILE_TEXT))
        crop = session.crop_of(item)
        cache, key = (session.thumbs, item.entry.path) if item.finding is None else (session.crops, crop)
        picture = None if key is None else cache.get(key)
        if picture is None:
            why = key is None or cache.error(key)
            painter.drawText(THUMB_AREA.translated(cell.topLeft()), Qt.AlignCenter,
                             "cannot decode" if why else "…")
        else:
            target = tile_thumb_rect(cell, picture.size())
            painter.drawImage(target, picture)
            if item.finding is None:
                self._draw_boxes(painter, labels, target)
            else:
                self._draw_finding(painter, item, crop.rect, target)
        caption = QRect(cell.x() + 8, cell.y() + THUMB_AREA.bottom() + 4, cell.width() - 16,
                        cell.height() - THUMB_AREA.bottom() - 8)
```

In `src/deeplabeling/ui/queue_panel.py`, replace:

```python
                x1, y1, x2, y2 = view.rect
                painter.drawRect(QRectF(target.x() + x1, target.y() + y1, x2 - x1, y2 - y1))
        painter.restore()

```

with:

```python
                x1, y1, x2, y2 = view.rect
                painter.drawRect(QRectF(target.x() + x1, target.y() + y1, x2 - x1, y2 - y1))
        painter.restore()


    def _draw_finding(self, painter, item, rect, target: QRect) -> None:
        """The label in its class colour and the model's box dashed, as the spotlight draws
        them, mapped from the crop `rect` (pixels of the image as shown) onto `target`."""
        session, ws, f = self._session, self._session.workspace, item.finding
        size = ws.sizes.get(item.entry.path)
        if size is None:
            return
        colors = ws.root_settings.get(CLASS_COLORS)
        scale = target.width() / (rect[2] - rect[0])

        def on_tile(r) -> QRectF:
            return QRectF(target.x() + (r[0] - rect[0]) * scale, target.y() + (r[1] - rect[1]) * scale,
                          (r[2] - r[0]) * scale, (r[3] - r[1]) * scale)

        painter.save()
        painter.setBrush(Qt.NoBrush)
        painter.setClipRect(target)
        painter.setPen(QPen(QColor(label_color(f, ws.dataset, colors)), 2))
        painter.drawRect(on_tile(norm_to_px(f.label_box, *size)))
        lit = spotlight(f, ws.dataset, size, colors, session.model.names)
        if lit is not None and lit[1] is not None:
            pen = QPen(QColor(lit[1].color), 2)
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(on_tile(lit[1].rect))
        painter.restore()

```

In `src/deeplabeling/ui/queue_panel.py`, replace:

```python
        session.thumbs.ready.connect(self._thumb_arrived)
        session.thumbs.failed.connect(self._thumb_arrived)
        self._retitle()
        self._follow()
```

with:

```python
        session.thumbs.ready.connect(self._thumb_arrived)
        session.thumbs.failed.connect(self._thumb_arrived)
        session.crops.ready.connect(self._crop_arrived)
        session.crops.failed.connect(self._crop_arrived)
        session.queueReset.connect(self._suit_source)
        self._retitle()
        self._follow()
```

In `src/deeplabeling/ui/queue_panel.py`, replace:

```python
        view.setGridSize(TILE if on else QSize())
        view.setItemDelegate(self._tiles if on else self._rows)
        self.mark_button.setVisible(on)
        self._relayout()
        self._want_soon()
```

with:

```python
        view.setGridSize(TILE if on else QSize())
        view.setItemDelegate(self._tiles if on else self._rows)
        self._suit_source()
        self._relayout()
        self._want_soon()
```

In `src/deeplabeling/ui/queue_panel.py`, replace:

```python
        return [queue.items[row].key for row in self._visible_rows(partial) if row < len(queue)]

    def mark_page(self) -> None:
        """Mark every tile wholly in view reviewed: what was seen, nothing more."""
        session = self._session
        if not self.grid or session.workspace is None or session.queue is None:
            return
        whole = self.visible_keys()
```

with:

```python
        return [queue.items[row].key for row in self._visible_rows(partial) if row < len(queue)]

    def _on_crops(self) -> bool:
        queue = self._session.queue
        return queue is not None and isinstance(queue.source, Findings)

    def _suit_source(self) -> None:
        """A grid of crops offers no mark page: its tiles are not whole images."""
        self.mark_button.setVisible(self.grid and not self._on_crops())

    def mark_page(self) -> None:
        """Mark every tile wholly in view reviewed: what was seen, nothing more."""
        session = self._session
        if not self.grid or session.workspace is None or session.queue is None:
            return
        if self._on_crops():
            session.status.emit("the tiles are crops, not whole images: nothing was marked")
            return
        whole = self.visible_keys()
```

In `src/deeplabeling/ui/queue_panel.py`, replace:

```python

    def _want_thumbs(self) -> None:
        queue = self._session.queue
        if self.grid and queue is not None:
            self._session.thumbs.want([queue.items[row].entry.path
                                       for row in self._visible_rows(partial=True) if row < len(queue)])

    def _thumb_arrived(self, path, *_) -> None:
```

with:

```python

    def _want_thumbs(self) -> None:
        session, queue = self._session, self._session.queue
        if self.grid and queue is not None:
            items = [queue.items[row] for row in self._visible_rows(partial=True) if row < len(queue)]
            session.thumbs.want([item.entry.path for item in items if item.finding is None])
            session.crops.want([crop for crop in map(session.crop_of, items) if crop is not None])

    def _crop_arrived(self, crop, *_) -> None:
        """Repaint the tiles in view: those showing this crop are among them."""
        if self.grid:
            self.view.viewport().update()

    def _thumb_arrived(self, path, *_) -> None:
```

- [ ] **Step 4: Run the tests to see them pass, then the full suite**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_crop_tiles.py tests/ui/test_finding_view.py tests/ui/test_grid.py`
Expected: 45 passed.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 896 passed.

- [ ] **Step 5: Look at it**

Save a screenshot of the window from `test_crop_tiles.py`'s `window` fixture, once every crop has come. Write the file as `tests/ui/test_zz_shot.py`, run it, delete it, and open the PNG (saved outside the repository). Expected:
- each tile shows a crop enlarged to fill its picture area, with the label in its class colour and the model's box dashed;
- the corrupt image's two tiles read `cannot decode`;
- the captions read `bus_m → car 0.95`, `car → person 0.80`, `bus_m → nothing 1.00`, unelided.

- [ ] **Step 6: Commit**

```bash
git add src/deeplabeling/ui/images.py src/deeplabeling/ui/findview.py src/deeplabeling/ui/session.py src/deeplabeling/ui/queue_panel.py tests/ui/test_crop_tiles.py tests/ui/test_finding_view.py
git commit -m "ui: a findings grid shows each finding's crop, with its label and the model's box" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Several tiles, one edit

**Files:**
- Create: `src/deeplabeling/ui/grid_actions.py`, `tests/ui/test_grid_actions.py`
- Modify: `src/deeplabeling/ui/session.py`, `src/deeplabeling/ui/queue_panel.py`, `src/deeplabeling/ui/main_window.py`

**Interfaces:**
- Consumes:
  - `Editor.apply_many(intents, description)` (slice 2), and `locate_line`, `clamp_box`, `class_with_hotkey`;
  - from plan 4b: `Dismissals.has` and `toggle`, `finding_rows.TWO` and `FOUND_TWO`.
- Produces:
  - `Session.apply_many(intents, description) -> Edit | None`, which becomes a notice when refused;
  - `QueuePanel.selected_findings() -> list[QueueItem]`, with Ctrl- and Shift-click selecting several tiles on a grid of crops;
  - in `deeplabeling.ui.grid_actions`: `take_model_class`, `take_model_box`, `delete`, `set_class(session, items, cls_id, name)`, `dismiss`;
  - `MainWindow._either(on_tiles, otherwise)`, used for `M`, `B`, `D`, `Delete` and the class keys.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_grid_actions.py`:

```python
"""Several findings at once, from the grid: selected tiles take a key together, as one
edit that marks nothing (docs/design/2026-10-06-find-bad.md#the-grid)."""

import pytest
from PySide6.QtCore import Qt

import deeplabeling.ui.model as model_module
from deeplabeling.core.dismissals import Dismissals
from deeplabeling.core.edits import Intent, SetClass
from deeplabeling.core.findings import Findings
from drive import start
from finding_rows import FOUND_TWO, TWO, P, factory, load, put_rows
from fixtures import CAMA_0001, CAMB_0001, read_exact

PERSON2 = (0.51, 0.5, 0.2, 0.3)     #: the model's box for camA/0001's person, a little to the right
TWIN = {"camB/images/twin.jpg": [P(0, (0.5, 0.5, 0.1, 0.1), 0.9)]}     # its person, a car: its file is shared


@pytest.fixture
def window(qtbot, ds, tmp_path, monkeypatch):
    monkeypatch.setattr(model_module, "UltralyticsPredictor", factory)
    w = start(qtbot, [str(ds.yaml)])
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    load(qtbot, w.session, weights)
    put_rows(w.session, {**TWO, **TWIN})
    w.session.set_queue(Findings())
    qtbot.waitUntil(lambda: w.session.queue.complete, timeout=5000)
    w.queue_panel.set_grid(True)
    w.resize(1400, 900)
    qtbot.wait(50)
    yield w
    w.close()


def click(qtbot, window, key, modifier=Qt.NoModifier):
    panel = window.queue_panel
    rect = panel.view.visualRect(panel.model.index(window.session.queue.index_of(key)))
    qtbot.mouseClick(panel.view.viewport(), Qt.LeftButton, modifier, rect.center())


def select(qtbot, window, keys):
    click(qtbot, window, keys[0])
    for key in keys[1:]:
        click(qtbot, window, key, Qt.ControlModifier)
    assert [item.key for item in window.queue_panel.selected_findings()] == keys


def states(session, keys):
    return [session.finding_state(session.queue.items[session.queue.index_of(key)]) for key in keys]


def said(qtbot, window, key):
    with qtbot.waitSignal(window.session.status) as signal:
        qtbot.keyClick(window, key)
    return signal.args[0]


def test_ctrl_click_selects_several_tiles_and_a_plain_click_one(qtbot, window):
    select(qtbot, window, FOUND_TWO[:3])
    assert window.session.current().key == FOUND_TWO[2]
    click(qtbot, window, FOUND_TWO[0])
    assert [item.key for item in window.queue_panel.selected_findings()] == FOUND_TWO[:1]


def test_m_on_several_tiles_is_one_edit_that_marks_nothing(qtbot, window, ds):
    select(qtbot, window, FOUND_TWO[:3])
    assert said(qtbot, window, Qt.Key_M) == "took the model's class on 3 findings, as one edit"
    assert read_exact(ds.lbl("camA/sub/0005")) == "1 0.750000 0.750000 0.150000 0.150000\n"
    assert read_exact(ds.lbl("camA/0001")) == "1 0.500000 0.500000 0.200000 0.300000\n0 0.250000 0.250000 0.100000 0.100000\n"
    session = window.session
    assert len(session.workspace.review.keys()) == 0                     # a crop is not the image
    assert states(session, FOUND_TWO[:3]) == ["fixed"] * 3
    session.undo()                                                       # one undo takes it all back
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001 and read_exact(ds.lbl("camA/sub/0005")) == CAMB_0001


def test_a_tile_the_key_cannot_apply_to_is_skipped_and_counted(qtbot, window, ds):
    select(qtbot, window, [FOUND_TWO[0], FOUND_TWO[3]])                 # camB/0001: not an object
    assert said(qtbot, window, Qt.Key_M) == ("took the model's class on 1 finding, as one edit; "
                                             "skipped 1 (the model has no class for it)")
    assert read_exact(ds.lbl("camB/0001")) == CAMB_0001


def test_a_shared_label_file_is_skipped_and_the_rest_is_one_edit(qtbot, window, ds):
    twin = "camB/images/twin.jpg#0#wrong class"
    select(qtbot, window, [FOUND_TWO[0], twin])
    assert said(qtbot, window, Qt.Key_Delete) == ("deleted 1 finding's label, as one edit; "
                                                  "skipped 1 (its label file cannot be edited)")
    assert read_exact(ds.lbl("camA/sub/0005")) == "" and read_exact(ds.lbl("camB/twin")).startswith("0 ")


def test_a_class_key_on_several_tiles_sets_each_label_s_class(qtbot, window, ds):
    select(qtbot, window, FOUND_TWO[1:3])
    assert said(qtbot, window, Qt.Key_3) == "set 2 findings to bus_m, as one edit"
    assert read_exact(ds.lbl("camA/0001")) == "2 0.500000 0.500000 0.200000 0.300000\n2 0.250000 0.250000 0.100000 0.100000\n"


def test_b_on_several_tiles_takes_each_model_box(qtbot, window, ds):
    put_rows(window.session, {"camA/images/0001.jpg": [P(1, (0.26, 0.25, 0.1, 0.1), 0.8), P(0, PERSON2, 0.9)]})
    window.session.set_queue(Findings())
    qtbot.waitUntil(lambda: window.session.queue.complete, timeout=5000)
    select(qtbot, window, FOUND_TWO[1:3])
    assert said(qtbot, window, Qt.Key_B) == "took the model's box on 2 findings, as one edit"
    assert read_exact(ds.lbl("camA/0001")) == "0 0.510000 0.500000 0.200000 0.300000\n1 0.260000 0.250000 0.100000 0.100000\n"



def test_d_on_several_tiles_dismisses_them_together_and_d_again_takes_them_back(qtbot, window, ds):
    select(qtbot, window, FOUND_TWO[:2])
    assert said(qtbot, window, Qt.Key_D) == "dismissed 2 findings"
    session = window.session
    assert states(session, FOUND_TWO[:2]) == ["dismissed"] * 2
    assert said(qtbot, window, Qt.Key_D) == "2 dismissals taken back"
    assert states(session, FOUND_TWO[:2]) == [""] * 2
    qtbot.keyClick(window, Qt.Key_D)
    path = session.workspace.dismissals.path
    window.close()
    saved = Dismissals(path, ds.root)
    assert saved.has("camA/images/sub/0005.jpg", CAMB_0001.strip(), "wrong class")
    assert saved.has("camA/images/0001.jpg", CAMA_0001.splitlines()[0], "wrong class")


def test_a_finding_whose_line_changed_since_is_skipped(qtbot, window, ds):
    session = window.session
    item = session.queue.items[session.queue.index_of(FOUND_TWO[1])]           # camA/0001's person
    session.workspace.editor.apply(Intent(item.entry.path, (SetClass(item.focus, 1),), "fixed elsewhere"))
    select(qtbot, window, FOUND_TWO[:2])
    assert said(qtbot, window, Qt.Key_Delete) == ("deleted 1 finding's label, as one edit; "
                                                  "skipped 1 (its label changed since)")
    assert read_exact(ds.lbl("camA/sub/0005")) == ""
    assert read_exact(ds.lbl("camA/0001")).startswith("1 0.500000 0.500000")
```

- [ ] **Step 2: Run them to see them fail**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_grid_actions.py`
Expected: 8 failed: `selected_findings`.

- [ ] **Step 3: Select several tiles; act on them as one edit**

In `src/deeplabeling/ui/session.py`, replace:

```python
        return edit

    def mark_negative(self) -> None:
        item = self.current()
```

with:

```python
        return edit

    def apply_many(self, intents: list[Intent], description: str) -> Edit | None:
        """Changes to many images as one edit that marks nothing: a grid action on
        several findings. None when refused, which a notice says."""
        ws = self._require()
        if self._busy():
            return None
        try:
            return ws.editor.apply_many(intents, description)
        except Refused as e:
            self.notice.emit("error", f"{description}: {e}", None)
            return None

    def mark_negative(self) -> None:
        item = self.current()
```

In `src/deeplabeling/ui/queue_panel.py`, replace:

```python

    def _suit_source(self) -> None:
        """A grid of crops offers no mark page: its tiles are not whole images."""
        self.mark_button.setVisible(self.grid and not self._on_crops())

    def mark_page(self) -> None:
```

with:

```python

    def _suit_source(self) -> None:
        """A grid of crops selects several tiles (Ctrl- or Shift-click), and offers no mark
        page: its tiles are not whole images."""
        crops = self.grid and self._on_crops()
        self.mark_button.setVisible(self.grid and not crops)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection if crops else QAbstractItemView.SingleSelection)

    def selected_findings(self) -> list[QueueItem]:
        """The findings selected in a grid of crops, in queue order: what a key acts on
        when there are several."""
        queue = self._session.queue
        if not (self.grid and self._on_crops()):
            return []
        rows = sorted(index.row() for index in self.view.selectionModel().selectedIndexes())
        return [queue.items[row] for row in rows if row < len(queue)]

    def mark_page(self) -> None:
```

Create `src/deeplabeling/ui/grid_actions.py`:

```python
"""Several findings at once, from the grid (docs/design/2026-10-06-find-bad.md#the-grid).

Every selected finding takes the key, as one edit that marks nothing reviewed: a crop is
not the image. A finding the key cannot apply to -- its label file read-only, its line
changed since, no model class or box -- is skipped, and the status bar counts it.
"""

from __future__ import annotations

from collections import Counter

from ..core.edits import DeleteLine, Intent, SetBox, SetClass
from ..core.labelio import locate_line
from .actions import clamp_box


def _count(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def _act(session, items, describe, op_for) -> None:
    """Apply `op_for(item)` -- an op, or None and why not -- to every finding that can take it."""
    ops, skipped = {}, Counter()
    for item in items:
        labels, f = session.labels(item.entry), item.focus
        if not labels.editable:
            skipped["its label file cannot be edited"] += 1
            continue
        if locate_line(labels.lines, f.cls_id, f.bbox, f.index) is None:
            skipped["its label changed since"] += 1
            continue
        op, why = op_for(item)
        if op is None:
            skipped[why] += 1
            continue
        ops.setdefault(item.entry.path, []).append(op)
    n = sum(len(o) for o in ops.values())
    if n:
        description = describe(n)
        if session.apply_many([Intent(image, tuple(o), description) for image, o in ops.items()],
                              description) is None:
            return                                  # refused: a notice says why
        text = f"{description}, as one edit"
    else:
        text = "nothing changed"
    if skipped:
        text += "; skipped " + ", ".join(f"{k} ({why})" for why, k in skipped.items())
    session.status.emit(text)


def take_model_class(session, items) -> None:
    def op(item):
        f = item.finding
        if f.model_cls is None or f.kind == "not an object":
            return None, "the model has no class for it"
        if f.model_cls == item.focus.cls_id:
            return None, "it already has the model's class"
        return SetClass(item.focus, f.model_cls), ""
    _act(session, items, lambda n: f"took the model's class on {_count(n, 'finding', 'findings')}", op)


def take_model_box(session, items) -> None:
    def op(item):
        box = item.finding.model_box and clamp_box(item.finding.model_box)
        return (None, "it has no model box") if box is None else (SetBox(item.focus, box), "")
    _act(session, items, lambda n: f"took the model's box on {_count(n, 'finding', 'findings')}", op)


def delete(session, items) -> None:
    _act(session, items, lambda n: f"deleted {n:,} finding's label" if n == 1 else f"deleted {n:,} findings' labels",
         lambda item: (DeleteLine(item.focus), ""))


def set_class(session, items, cls_id: int, name: str) -> None:
    def op(item):
        if item.focus.cls_id == cls_id:
            return None, f"it is a {name} already"
        return SetClass(item.focus, cls_id), ""
    _act(session, items, lambda n: f"set {_count(n, 'finding', 'findings')} to {name}", op)


def dismiss(session, items) -> None:
    """D: dismiss every selected finding -- or, when all are dismissed, take them all back."""
    dismissals = session.workspace.dismissals
    shown = [(item.entry.rel, item.finding.text, item.finding.kind) for item in items]
    back = all(dismissals.has(*d) for d in shown)
    changed = [d for d in shown if dismissals.has(*d) == back]
    for d in changed:
        dismissals.toggle(*d)
    session.saver.schedule()
    session.itemsChanged.emit([item.key for item in items])
    n = len(changed)
    session.status.emit(f"{_count(n, 'dismissal', 'dismissals')} taken back" if back
                        else f"dismissed {_count(n, 'finding', 'findings')}")
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
from ..core.queue import Seen
from ..core.workspace import CLASS_COLORS
from .boxes import box_views, prediction_views
from .canvas import Canvas
from .classes import DEFAULT_HOTKEYS
from .editing import Editing
from .findview import spotlight
```

with:

```python
from ..core.queue import Seen
from ..core.workspace import CLASS_COLORS
from . import grid_actions
from .boxes import box_views, prediction_views
from .canvas import Canvas
from .classes import DEFAULT_HOTKEYS, class_with_hotkey
from .editing import Editing
from .findview import spotlight
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
            "go_to": self.go_to,
            "help": self.show_help,
            **{f"class_{key}": (lambda k=key: self.editing.class_key(k)) for key in DEFAULT_HOTKEYS},
            "pick_class": self.editing.pick_class,
            "delete": self.editing.delete,
            "select_next": lambda: self.editing.select_step(1),
            "select_previous": lambda: self.editing.select_step(-1),
```

with:

```python
            "go_to": self.go_to,
            "help": self.show_help,
            **{f"class_{key}": self._either(lambda items, k=key: self._tiles_class(items, k),
                                            lambda k=key: self.editing.class_key(k)) for key in DEFAULT_HOTKEYS},
            "pick_class": self.editing.pick_class,
            "delete": self._either(lambda items: grid_actions.delete(session, items), self.editing.delete),
            "select_next": lambda: self.editing.select_step(1),
            "select_previous": lambda: self.editing.select_step(-1),
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
            "paste": self.editing.paste,
            "accept_missing": self.editing.accept_missing,
            "take_model_class": self.editing.take_model_class,
            "take_model_box": self.editing.take_model_box,
            "dismiss": session.dismiss_current,
        })
        layers = self.state_bar.layers.menu()
```

with:

```python
            "paste": self.editing.paste,
            "accept_missing": self.editing.accept_missing,
            "take_model_class": self._either(lambda items: grid_actions.take_model_class(session, items),
                                             self.editing.take_model_class),
            "take_model_box": self._either(lambda items: grid_actions.take_model_box(session, items),
                                           self.editing.take_model_box),
            "dismiss": self._either(lambda items: grid_actions.dismiss(session, items), session.dismiss_current),
        })
        layers = self.state_bar.layers.menu()
```

In `src/deeplabeling/ui/main_window.py`, replace:

```python
        self.session.open(folder, labels)

    def edit_queue(self) -> None:
        if self.session.queue is None:
```

with:

```python
        self.session.open(folder, labels)

    def _either(self, on_tiles, otherwise):
        """A key's action: on the tiles selected in a grid of crops, when there are several
        (docs/design/2026-10-06-find-bad.md#the-grid); otherwise its own."""
        def run():
            items = self.queue_panel.selected_findings()
            if len(items) > 1:
                on_tiles(items)
            else:
                otherwise()
        return run

    def _tiles_class(self, items, key: str) -> None:
        info = class_with_hotkey(self.editing.classes(), key)
        if info is None:
            self.editing.class_key(key)             # which says no class has it
        else:
            grid_actions.set_class(self.session, items, info.cls_id, info.name)

    def edit_queue(self) -> None:
        if self.session.queue is None:
```

- [ ] **Step 4: Run the tests to see them pass, then the full suite**

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q tests/ui/test_grid_actions.py tests/ui/test_finding_keys.py tests/ui/test_grid.py tests/ui/test_editing.py`
Expected: 71 passed.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 904 passed.

- [ ] **Step 5: Look at it**

Screenshot `test_grid_actions.py`'s `window` after `select(qtbot, window, FOUND_TWO[:3])` and `M`, with the queue dock widened to three columns. Write it as a temporary test in `tests/ui/`, and delete it after. Expected:
- the three selected tiles are framed;
- their captions end ` · fixed`;
- the status bar reads `took the model's class on 3 findings, as one edit`;
- the state bar still reads `Reviewed 0 / 15`.

- [ ] **Step 6: Commit**

```bash
git add src/deeplabeling/ui/grid_actions.py src/deeplabeling/ui/session.py src/deeplabeling/ui/queue_panel.py src/deeplabeling/ui/main_window.py tests/ui/test_grid_actions.py
git commit -m "ui: selected tiles take M, B, D, Delete or a class key together, as one edit that marks nothing" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The measurements and the status

**Files:**
- Create: `tools/measure_find_bad.py`
- Modify: `docs/design/2026-10-06-find-bad.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: `measure_assist.py`'s `Answers`, `wait`, `md5` and `SETTINGS`; `Findings`; `QueuePanel._visible_rows`.
- Produces: the measured column of the spec's *Performance targets*, and the status.

- [ ] **Step 1: Write the measurement script**

Create `tools/measure_find_bad.py`:

```python
#!/usr/bin/env python3
"""Measure slice 4's performance targets with a real model on a real dataset, read-only
(docs/design/2026-10-06-find-bad.md#performance-targets).

App state -- the prediction store included -- goes to a temporary folder, deleted at the
end. A dataset pass of --pass-seconds fills the store first, so the scan has findings to
judge. Nothing in the dataset is written: no label is edited and nothing is dismissed.
Run it from the repository root, so that `ultralytics` is the editable install
(docs/knowledge/environment.md#which-ultralytics-gets-imported).

  /home/sonnn/miniconda3/bin/python3 tools/measure_find_bad.py DATA.yaml WEIGHTS [--pass-seconds 60]
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from measure_assist import SETTINGS, Answers, md5, wait  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("yaml", type=Path)
    ap.add_argument("weights", type=Path)
    ap.add_argument("--pass-seconds", type=float, default=60.0)
    args = ap.parse_args(argv)
    tmp = tempfile.TemporaryDirectory(prefix="measure-find-bad-")
    os.environ["DEEPLABELING_STATE_DIR"] = str(Path(tmp.name) / "state")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT / "src"))
    print("ultralytics:", importlib.util.find_spec("ultralytics").origin)     # found, not imported
    settings_before = md5(SETTINGS)

    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication

    from deeplabeling.__main__ import launch
    from deeplabeling.core.findings import Findings

    app = QApplication.instance() or QApplication(sys.argv[:1])
    rows = []
    window = launch([str(args.yaml)], Answers())
    window.resize(1440, 900)
    window.show()
    s, model = window.session, window.session.model
    wait(app, lambda: window.canvas.image_size is not None and s.queue is not None and s.queue.complete)
    model.load(args.weights)
    wait(app, lambda: model.state in ("ready", "failed"))
    if model.state == "failed":
        raise SystemExit(model.error)

    t = time.perf_counter()
    model.infer_queue()
    while time.perf_counter() - t < args.pass_seconds:
        app.processEvents()
        time.sleep(0.001)
    model.cancel_pass()
    wait(app, lambda: not model.passing)
    print(f"{len(s.workspace.predictions.inferred(model.key)):,} images inferred")

    def scan(name: str) -> None:
        """A findings queue built in the window: complete, and the longest the event loop
        went without a turn meanwhile, which is what paging would wait."""
        gaps, last = [], [time.perf_counter()]

        def tick():
            now = time.perf_counter()
            gaps.append(now - last[0])
            last[0] = now

        timer = QTimer()
        timer.timeout.connect(tick)
        timer.start(5)
        t = time.perf_counter()
        s.set_queue(Findings())
        total = wait(app, lambda: s.queue.complete, timeout=300)
        timer.stop()
        rows.append((f"a Findings scan, {name}: complete, {len(s.queue):,} findings{s.progress_text()}", total,
                     "≤ 30 s cold, ≤ 5 s warm"))
        rows.append((f"a Findings scan, {name}: the event loop's longest wait", max(gaps), "≤ 100 ms"))

    scan("cold")                                    # every inferred image's label file read
    scan("warm")
    if len(s.queue) < 2:
        raise SystemExit("too few findings to page: pass longer")

    def page() -> float:
        """Seconds to show the next finding on another image, prefetched."""
        nxt = s.queue.items[s.queue.position() + 1].entry.path
        wait(app, lambda: s.images.get(nxt) is not None)
        t = time.perf_counter()
        s.move(1)
        return time.perf_counter() - t + wait(app, lambda: window._shown == nxt and window.canvas.spotlight is not None)

    paging = []
    while len(paging) < 10 and s.queue.position() + 1 < len(s.queue):
        here = s.current().entry.path
        if s.queue.items[s.queue.position() + 1].entry.path == here:
            s.move(1)                               # the same image: nothing to decode
            continue
        paging.append(page())
    rows.append((f"the next finding, prefetched (worst of {len(paging)})", max(paging), "≤ 100 ms"))

    window.queue_panel.set_grid(True)
    window.resizeDocks([window.queue_dock], [4 * 176 + 40], Qt.Horizontal)      # four columns of tiles
    app.processEvents()
    s.crops.clear()
    t = time.perf_counter()
    app.processEvents()
    wanted = lambda: [c for c in map(s.crop_of, (s.queue.items[r] for r in window.queue_panel._visible_rows(True)))
                      if c is not None]
    wait(app, lambda: wanted() and all(s.crops.get(c) is not None or s.crops.error(c) for c in wanted()))
    rows.append((f"a page of crop tiles ({len(wanted())} tiles)", time.perf_counter() - t, "≤ 1 s"))
    window.close()

    for name, value, target in rows:
        shown = f"{value * 1000:.0f} ms" if value < 1 else f"{value:.2f} s"
        print(f"{name:90s} {shown:>10s}   target {target}")
    print("ultralytics settings unchanged:", md5(SETTINGS) == settings_before)
    tmp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Measure, read-only, with the real model**

Run it from the repository root (it prints which `ultralytics` it found, without importing it, and whether the Ultralytics settings file is unchanged):

```sh
/home/sonnn/miniconda3/bin/python3 tools/measure_find_bad.py /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/data_13class.yaml /home/sonnn/Documents/ultralytics/runs/detect/backup/yolo26n_vehicle/weights/best.pt --pass-seconds 60
```

Expected:
- `ultralytics: /home/sonnn/Documents/ultralytics/ultralytics/__init__.py`;
- `ultralytics settings unchanged: True`;
- every row within its target.

The figures vary with the GPU and with how many images the pass reaches. Record the measured values, not the ones below; a missed target is recorded with its value.

- [ ] **Step 3: Record the measurements and the status**

In `CLAUDE.md`, replace:

````markdown
grid. Slice 2 is built: model assist, from a model's predictions on screen to accepting
them across a queue. Slice 3 is built: filters by box size, overlap and where the model
disagrees. Slice 4 (Find Bad) has its core and its full frame built; its grid (plan 4c)
is next. The design and the plans are in [docs/design/](docs/design/).

```sh
````

with:

````markdown
grid. Slice 2 is built: model assist, from a model's predictions on screen to accepting
them across a queue. Slice 3 is built: filters by box size, overlap and where the model
disagrees. Slice 4 is built: Find Bad, the labels the model disagrees with as a queue,
fixed a key at a time in the full frame or many at once in a grid of crops. Slice 5 (bulk
reassign, statistics, crop export) is next. The design and the plans are in
[docs/design/](docs/design/).

```sh
````

In `docs/design/2026-10-06-find-bad.md`, replace:

```markdown
# DeepLabeling — slice 4: Find Bad

**Status:** approved 2026-10-06 · plans 4a (the core) and 4b (the full frame) implemented; 4c (the grid) next
**Scope:** slice 4 of [the app foundation](2026-10-04-app-foundation.md#slices): a queue whose
items are the labels the model disagrees with, each focused on its label line; crop tiles in
```

with:

```markdown
# DeepLabeling — slice 4: Find Bad

**Status:** approved 2026-10-06 · implemented: plans 4a (the core), 4b (the full frame) and 4c (the grid)
**Scope:** slice 4 of [the app foundation](2026-10-04-app-foundation.md#slices): a queue whose
items are the labels the model disagrees with, each focused on its label line; crop tiles in
```

In `docs/design/2026-10-06-find-bad.md`, replace:

```markdown
measured value, not quietly dropped.

| Action | Target |
|---|---|
| a Findings scan over 45k images, complete: cold / warm | ≤ 30 s / ≤ 5 s |
| the window while it scans | the event loop never waits more than 100 ms |
| a page of crop tiles | ≤ 1 s |
| the next finding, prefetched | ≤ 100 ms, as paging images |

## Testing
```

with:

````markdown
measured value, not quietly dropped.

| Action | Target | Measured 2026-10-06, in the window, 7,051 of 45,252 images inferred |
|---|---|---|
| a Findings scan over 45k images, complete: cold / warm | ≤ 30 s / ≤ 5 s | 1.30 s / 1.31 s: 5,910 findings (131 wrong class, 5,779 not an object) |
| the window while it scans | the event loop never waits more than 100 ms | 50 ms cold, 45 ms warm |
| a page of crop tiles | ≤ 1 s | 212 ms, 24 tiles |
| the next finding, prefetched | ≤ 100 ms, as paging images | 11 ms, the worst of 10 |

- A scan judges only the images the model has rows for: the label files it reads grow with
  what is inferred, and a fully inferred dataset scans slower than these figures.
- "Cold" is the first scan after opening, which reads every inferred image's label file;
  the OS page cache was warm. A short dataset pass fills the store first.
- Reproduce, read-only (app state goes to a temporary folder, deleted at the end):

```sh
/home/sonnn/miniconda3/bin/python3 tools/measure_find_bad.py /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/data_13class.yaml /home/sonnn/Documents/ultralytics/runs/detect/backup/yolo26n_vehicle/weights/best.pt --pass-seconds 60
```

## Testing
````

- [ ] **Step 4: Check the docs, run the full suite, and commit**

Run: `/home/sonnn/miniconda3/bin/python3 tools/check_docs.py`
Expected: `0 failure(s), 0 warning(s)`.

Run: `/home/sonnn/miniconda3/bin/python3 -m pytest -o addopts= -p no:warnings -q`
Expected: 904 passed.

```bash
git add tools/measure_find_bad.py docs/design/2026-10-06-find-bad.md CLAUDE.md
git commit -m "docs: slice 4 is built; Find Bad measured with the real model" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
