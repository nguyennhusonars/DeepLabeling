"""The Blurry queue source (docs/design/2026-10-27-blurry.md#the-queue)."""

import os

import cv2
import numpy as np
import pytest

from deeplabeling.core.blurry import Blurry, BlurSettings
from deeplabeling.core.dataset import Dataset
from deeplabeling.core.findings import Findings
from deeplabeling.core.imagesize import ImageSizes
from deeplabeling.core.queue import BuildContext, ImageFilter, NameContains, Scored, source_from_json
from deeplabeling.core.sharpstore import SHARP_NAME, SharpnessStore
from deeplabeling.core.store import LabelStore
from fixtures import build_blur_dataset

BLURRED = {"cam/images/0003.jpg", "cam/images/0017.jpg"}


def built(yaml, source, sharp, dismissed=frozenset(), cancel_after=None):
    """Run a build as the session does: (items, Scored rows, ctx, finished). The rows are
    written to `sharp`, so the next build is warm."""
    dataset = Dataset.open(yaml)
    ctx = BuildContext(dataset, LabelStore(dataset), frozenset(), sizes=ImageSizes(), sharpness=sharp,
                       dismissed=dismissed)
    items, rows, seen = [], [], []

    def emit(batch):
        if isinstance(batch, Scored):
            rows.extend(batch.rows)
            sharp.put_many(batch.rows)
        else:
            items.extend(batch)

    def progress(done, total):
        seen.append(done)

    cancelled = (lambda: False) if cancel_after is None else (lambda: bool(seen) and seen[-1] >= cancel_after)
    finished = source.build(ctx, emit, cancelled, progress=progress, interval=0)
    return items, rows, ctx, finished


@pytest.fixture
def blur(tmp_path):
    return build_blur_dataset(tmp_path / "b")


@pytest.fixture
def sharp(tmp_path):
    s = SharpnessStore(tmp_path / SHARP_NAME)
    yield s
    s.close()


def test_the_blurred_images_come_first(blur, sharp):
    items, rows, _, finished = built(blur.yaml, Blurry(settings=BlurSettings(share=0.1)), sharp)
    assert finished and len(rows) == 30
    heads = [i for i in items if i.focus.cls_id == 0]
    assert {i.entry.rel for i in heads[:2]} == BLURRED and len(heads) == 3          # ceil(0.1 * 30)
    humans = [i for i in items if i.focus.cls_id == 1]
    assert {i.entry.rel for i in humans[:2]} == BLURRED
    first = items[0]
    assert first.finding.kind == "blurry" and first.key == f"{first.entry.rel}#{first.focus.index}#blurry"
    assert first.finding.score == 0 and first.finding.z < 0 and first.finding.model_box is None
    assert first.finding.group in ("32–63 px", "16–31 px")
    assert [i.sort_key for i in items] == sorted(i.sort_key for i in items)


def test_a_warm_build_decodes_nothing(blur, sharp, monkeypatch):
    cold, _, _, _ = built(blur.yaml, Blurry(), sharp)
    monkeypatch.setattr(cv2, "imread", lambda *a, **kw: pytest.fail("decoded on a warm build"))
    warm, rows, _, _ = built(blur.yaml, Blurry(), sharp)
    assert [i.key for i in warm] == [i.key for i in cold] and rows == []


def test_a_class_change_needs_no_rescore_and_a_moved_box_rescores_its_image(blur, sharp, monkeypatch):
    built(blur.yaml, Blurry(), sharp)
    label = blur.root / "cam/labels/0005.txt"
    label.write_text(label.read_text().replace("0 0.312500", "1 0.312500", 1))     # same box, another class
    decoded = []
    real = cv2.imread
    monkeypatch.setattr(cv2, "imread", lambda path, *a: (decoded.append(path), real(path, *a))[1])
    built(blur.yaml, Blurry(), sharp)
    assert decoded == []
    label.write_text(label.read_text().replace("0.312500 0.375000", "0.300000 0.375000", 1))   # moved
    _, rows, _, _ = built(blur.yaml, Blurry(), sharp)
    assert decoded == [str(blur.root / "cam/images/0005.jpg")] and [r[0] for r in rows] == ["cam/images/0005.jpg"]


def test_a_changed_image_is_rescored(blur, sharp):
    built(blur.yaml, Blurry(), sharp)
    image = blur.root / "cam/images/0009.jpg"
    st = image.stat()
    os.utime(image, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))                   # re-encoded in place
    _, rows, _, _ = built(blur.yaml, Blurry(), sharp)
    assert [r[0] for r in rows] == ["cam/images/0009.jpg"]


def test_dismissed_boxes_are_peers_but_not_listed(blur, sharp):
    items, _, _, _ = built(blur.yaml, Blurry(settings=BlurSettings(share=0.1)), sharp)
    first = items[0]
    dismissed = frozenset({(first.entry.rel, first.finding.text, "blurry")})
    again, _, _, _ = built(blur.yaml, Blurry(settings=BlurSettings(share=0.1)), sharp, dismissed)
    assert [i.key for i in again] == [i.key for i in items if i.key != first.key]   # nothing pulled in
    assert again[0].finding.score == items[1].finding.score                          # ranks unmoved


def test_the_edge_case_dataset_counts_what_it_cannot_rank(ds, sharp):
    """Tiny boxes, flat crops, a corrupt image, a polygon: counted, never an error."""
    items, _, ctx, finished = built(ds.yaml, Blurry(settings=BlurSettings(min_side=8)), sharp)
    assert finished and items == []
    assert ctx.left_out["cannot decode"] == {"bad/images/corrupt.jpg"}
    assert ctx.unsettled["flat"] + ctx.unsettled["too few peers"] > 0
    assert all("#" in key for what in ("flat", "too few peers", "too small") for key in ctx.left_out[what])
    poly = Dataset.open(ds.yaml).entry(ds.img("seg/poly1.jpg")).rel
    assert not any(key.startswith(poly) for keys in ctx.left_out.values() for key in keys)   # polygons unscored


def test_boxes_under_the_minimum_side_are_counted_too_small(blur, sharp):
    items, _, ctx, _ = built(blur.yaml, Blurry(settings=BlurSettings(min_side=32)), sharp)
    assert ctx.unsettled["too small"] == 30 and all(i.focus.cls_id == 0 for i in items)   # the 20 px humans


def test_a_cancelled_build_has_emitted_its_scores(blur, sharp):
    _, rows, _, finished = built(blur.yaml, Blurry(), sharp, cancel_after=10)
    assert not finished and 10 <= len(rows) < 30
    _, rest, _, _ = built(blur.yaml, Blurry(), sharp)
    assert len(rest) == 30 - len(rows)                                              # the rest resumes


def test_an_item_holds_while_its_line_text_is_there(blur, sharp):
    items, _, ctx, _ = built(blur.yaml, Blurry(settings=BlurSettings(share=0.1)), sharp)
    item = items[0]
    source = Blurry(settings=BlurSettings(share=0.1))
    assert source.holds(item, ctx)
    label = item.entry.label_path
    label.write_text(label.read_text().replace(item.finding.text + "\n", ""))
    assert not source.holds(item, ctx) and source.still(item.entry, [item], ctx) == set()


def test_json_round_trip_and_source_from_json():
    source = Blurry(ImageFilter(("val",), (NameContains("cam"),)), BlurSettings(0.2, 24))
    assert source_from_json(source.to_json()) == source
    assert source.to_json()["source"] == "blurry" and not Blurry.needs_model
    assert isinstance(source_from_json(Findings().to_json()), Findings)
    with pytest.raises(ValueError, match="not a blurry queue"):
        Blurry.from_json({"source": "blurry"})


def test_it_describes_itself(blur):
    dataset = Dataset.open(blur.yaml)
    assert Blurry().describe(dataset) == "blurry: 5% of each class and size, ≥ 16 px"
    assert Blurry(ImageFilter(conditions=(NameContains("cam"),))).describe(dataset).startswith(
        "blurry: 5% of each class and size, ≥ 16 px of ")


def test_the_workspace_opens_and_closes_the_score_store(ds):
    from deeplabeling.core.workspace import Workspace

    ws = Workspace.open(ds.yaml, confirm_taxonomy=lambda *a: True)
    try:
        assert ws.sharpness.path.name == SHARP_NAME and ws.sharpness.path.parent == ws.directory
    finally:
        ws.close()
    assert ws.sharpness.get("x", (1, 1)) is None                                  # closed: answers nothing


def test_scores_go_out_in_small_batches(tmp_path, sharp):
    """Each Scored batch is written on the GUI thread: 500 images' took 202 ms (2026-10-27)."""
    from deeplabeling.core.blurry import SCORE_BATCH

    blur = build_blur_dataset(tmp_path / "many", n=2 * SCORE_BATCH + 3)
    dataset = Dataset.open(blur.yaml)
    ctx = BuildContext(dataset, LabelStore(dataset), frozenset(), sizes=ImageSizes(), sharpness=sharp)
    sizes = []
    Blurry().build(ctx, lambda b: sizes.append(len(b.rows)) if isinstance(b, Scored) else None)
    assert sizes == [SCORE_BATCH, SCORE_BATCH, 3]
