"""The statistics of a queue's images (docs/design/2026-10-07-bulk-and-stats.md#statistics),
checked against the edge-case dataset counted by hand."""

import pytest

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.imagesize import ImageSizes
from deeplabeling.core.stats import GRID, SIZE_LABELS, size_bucket, stats_of
from deeplabeling.core.store import LabelStore

PERSON, CAR, BUS_M, BUS_L = 0, 1, 2, 3


@pytest.fixture
def stats(ds):
    dataset = Dataset.open(ds.yaml)
    return stats_of(dataset.images, LabelStore(dataset).get, ImageSizes().get)


def test_boxes_and_images_per_class_and_split(stats):
    assert stats.splits == ("train", "val")
    assert {k: v for k, v in stats.boxes.items() if v} == {
        ("train", PERSON): 4, ("train", CAR): 1, ("train", BUS_M): 3,
        ("val", PERSON): 8, ("val", CAR): 5, ("val", 99): 1, ("val", -1): 1}
    assert stats.images_with[("train", PERSON)] == 4 and stats.images_with[("val", PERSON)] == 5
    assert stats.images_with[("val", CAR)] == 5 and stats.images_with[("train", BUS_L)] == 0
    assert {k: v for k, v in stats.polygons.items() if v} == {("val", PERSON): 1, ("val", CAR): 2}
    assert stats.classes() == (-1, PERSON, CAR, BUS_M, 99)


def test_label_files_per_split(stats):
    assert {k: v for k, v in stats.files.items() if v} == {
        ("train", "images"): 10, ("train", "with boxes"): 7, ("train", "negative"): 1,
        ("train", "missing"): 2, ("train", "shared"): 2,
        ("val", "images"): 5, ("val", "with boxes"): 5, ("val", "unparsable lines"): 4}


def test_an_unreadable_label_file_is_counted(ds):
    dataset = Dataset.open(ds.yaml)
    ds.lbl("camA/0001").chmod(0o000)
    try:
        stats = stats_of(dataset.images, LabelStore(dataset).get, ImageSizes().get)
    finally:
        ds.lbl("camA/0001").chmod(0o644)
    assert stats.files[("train", "unreadable")] == 1 and stats.boxes[("train", CAR)] == 0


def test_box_sizes_in_pixels_leave_out_only_the_image_whose_header_cannot_be_read(stats):
    small, medium = SIZE_LABELS.index("< 8"), SIZE_LABELS.index("8–16")
    assert {k: v for k, v in stats.sizes.items() if v} == {
        (PERSON, small): 4, (PERSON, medium): 7,            # bad/corrupt's person and car: unsized
        (CAR, small): 3, (CAR, medium): 2,
        (BUS_M, medium): 3,                                 # one of them on the EXIF-turned camB/rot
        (99, small): 1, (-1, small): 1}
    assert stats.unsized == 1


def test_the_size_buckets_take_their_lower_end(stats):
    assert [SIZE_LABELS[size_bucket(px)] for px in (0, 7.99, 8, 15.9, 16, 255.9, 256, 4000)] == [
        "< 8", "< 8", "8–16", "8–16", "16–32", "128–256", "≥ 256", "≥ 256"]


def test_boxes_per_image_with_twenty_or_more_together(stats):
    assert {k: v for k, v in stats.per_image.items() if v} == {0: 3, 1: 6, 2: 5, 7: 1}
    from deeplabeling.core.stats import PER_IMAGE_MAX
    assert PER_IMAGE_MAX == 20


def test_box_centres_on_a_grid_kept_inside_it(stats):
    assert GRID == 20
    person = {(x, y): n for (cls, x, y), n in stats.centres.items() if cls == PERSON and n}
    assert person == {(10, 10): 9, (8, 8): 1, (19, 10): 1, (3, 3): 1}     # cx 1.4 stays in the last column


def test_a_cancelled_computation_gives_nothing_and_progress_is_told(ds):
    dataset = Dataset.open(ds.yaml)
    told = []
    stats_of(dataset.images, LabelStore(dataset).get, ImageSizes().get, progress=lambda d, t: told.append((d, t)))
    assert told[-1] == (15, 15)
    assert stats_of(dataset.images, LabelStore(dataset).get, ImageSizes().get, cancelled=lambda: True) is None


def test_no_images_is_empty_stats(ds):
    stats = stats_of([], None, None)
    assert stats.splits == () and not stats.boxes and stats.classes() == ()


def test_a_long_computation_pauses_so_the_window_gets_the_gil(ds, monkeypatch):
    import deeplabeling.core.stats as stats_module

    dataset = Dataset.open(ds.yaml)
    pauses = []
    monkeypatch.setattr(stats_module, "BREATHE", 4)
    monkeypatch.setattr(stats_module.time, "sleep", lambda s: pauses.append(s))
    stats_of(dataset.images, LabelStore(dataset).get, ImageSizes().get)
    assert len(pauses) == len(dataset.images) // 4 and all(0 < s <= 0.001 for s in pauses)



def test_a_malformed_box_is_counted_but_never_sized_or_placed(ds):
    ds.lbl("camA/0002").write_text("0 0.5 0.5 -0.1 0.1\n0 nan 0.5 0.1 0.1\n0 inf 0.5 0.1 0.1\n")
    dataset = Dataset.open(ds.yaml)
    stats = stats_of(dataset.images, LabelStore(dataset).get, ImageSizes().get)
    assert stats.boxes[("train", PERSON)] == 7 and stats.malformed == 3
    assert sum(n for (cls, _), n in stats.sizes.items() if cls == PERSON) == 13       # nan and inf: sized, not placed
    assert sum(n for (cls, _, _), n in stats.centres.items() if cls == PERSON) == 13  # the -0.1 wide one has a centre


def test_an_unreadable_label_file_is_not_an_image_with_no_boxes(ds):
    dataset = Dataset.open(ds.yaml)
    ds.lbl("camA/0002").chmod(0o000)
    try:
        stats = stats_of(dataset.images, LabelStore(dataset).get, ImageSizes().get)
    finally:
        ds.lbl("camA/0002").chmod(0o644)
    assert sum(stats.per_image.values()) == 14 and stats.per_image[0] == 2
