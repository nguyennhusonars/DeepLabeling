"""Slice 3's queue conditions (docs/design/2026-10-06-filters.md#conditions)."""

import pytest

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.imagesize import ImageSizes
from deeplabeling.core.queue import (
    Boxes,
    BuildContext,
    ImageFilter,
    NameContains,
    Overlap,
    Seen,
    condition_from_json,
)
from deeplabeling.core.store import LabelStore


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)


@pytest.fixture
def ctx(dataset):
    return BuildContext(dataset, LabelStore(dataset), frozenset(), sizes=ImageSizes())


def keys(condition, ctx, *more):
    batches = []
    assert ImageFilter(conditions=(condition, *more)).build(ctx, batches.append)
    return [item.key for batch in batches for item in batch]


# camA/0001 (64 x 48): a person 20% x 30% (12.8 x 14.4 px) and a car 10% x 10% (6.4 x 4.8 px).

def test_size_and_class_hold_on_the_same_box(ctx):
    assert "camA/images/0001.jpg" in keys(Boxes(("car",), w=(None, 10), unit="%"), ctx)
    assert "camA/images/0001.jpg" not in keys(Boxes(("person",), w=(None, 10), unit="%"), ctx)


def test_both_ends_are_inclusive(ctx):
    exact = Boxes(("car",), w=(10, 10), h=(10, 10), unit="%")
    assert "camA/images/0001.jpg" in keys(exact, ctx)
    assert "camA/images/0001.jpg" in keys(Boxes(("car",), w=(6.4, 6.4), h=(4.8, 4.8), unit="px"), ctx)


def test_no_class_means_any_class_and_an_unknown_class_matches_nothing(ctx):
    assert "camA/images/0001.jpg" in keys(Boxes((), w=(20, 20), unit="%"), ctx)
    assert keys(Boxes(("truck",), w=(0, None), unit="%"), ctx) == []


def test_pixels_are_the_frame_as_shown_after_exif_rotation(ctx):
    # camB/0001 (64 x 48) and camB/rot (shown 48 x 64) hold the same bus_m line: 15% x 15%.
    found = keys(Boxes(("bus_m",), w=(7, 8), h=(9, 10), unit="px"), ctx)
    assert "camB/images/rot.jpg" in found and "camB/images/0001.jpg" not in found


def test_an_image_without_a_readable_size_does_not_match_and_is_counted(ctx):
    assert "bad/images/corrupt.jpg" not in keys(Boxes((), w=(0, None), unit="px"), ctx)
    assert ctx.unsettled["could not be sized"] == 1
    assert "bad/images/corrupt.jpg" in keys(Boxes((), w=(0, None), unit="%"), ctx)    # % needs no size


def test_the_cheapest_condition_goes_first_so_skipped_images_are_not_counted(ctx):
    keys(Boxes((), w=(0, None), unit="px"), ctx, NameContains("camA"))
    assert ctx.unsettled == {}


def test_the_highlight_is_the_boxes_that_matched(ctx, dataset):
    labels = ctx.labels(dataset.entry(dataset.root / "camA/images/0001.jpg"))
    assert Boxes((), w=(None, 10), unit="%").highlight(labels, dataset) == {1}
    px = Boxes((), w=(None, 7), unit="px")
    assert px.highlight(labels, dataset, Seen(size=(64, 48))) == {1}
    assert px.highlight(labels, dataset) == frozenset()         # pixels, with no size known


@pytest.mark.parametrize("condition, text", [
    (Boxes(("car",), w=(10, 30), unit="px"), "has a car 10–30 px wide"),
    (Boxes(("car", "bus_m"), h=(None, 5), unit="%"), "has a car or bus_m ≤ 5% high"),
    (Boxes((), w=(50, None), h=(0.5, 2), unit="%"), "has a box ≥ 50% wide, 0.5–2% high"),
])
def test_a_size_reads_as_words(condition, text, dataset):
    assert condition.describe(dataset) == text


def test_a_size_survives_its_json(dataset):
    for condition in (Boxes(("car",), w=(10, 30), unit="px"), Boxes((), h=(None, 5), unit="%")):
        assert condition_from_json(condition.to_json()) == condition


@pytest.mark.parametrize("kw, why", [
    (dict(w=(30, 10)), "width: 30 is above 10: put the lower end first"),
    (dict(h=(-1, 5)), "height: the lower end cannot be below 0"),
    (dict(w=(10, 120), unit="%"), "width: the upper end cannot be above 100"),
    (dict(unit="cm"), "unknown size unit 'cm'"),
])
def test_an_unusable_size_is_refused(kw, why):
    with pytest.raises(ValueError, match=why):
        Boxes((), **kw)


# bad/ok holds the gauntlet: lines 5, 6 and 10 are one class-0 box three times, line 0 is a
# class-1 box on the same spot, and lines 1 (class 99) and 2 (class -1) are one smaller box twice.

@pytest.mark.parametrize("scope, lines", [("same", {5, 6, 10}), ("different", {0, 1, 2, 5, 6, 10}),
                                          ("any", {0, 1, 2, 5, 6, 10})])
def test_overlapping_labels_by_scope_and_the_highlight_is_what_counted(scope, lines, ctx, dataset):
    condition = Overlap(scope, 0.99, 1.0)
    assert keys(condition, ctx) == ["bad/images/ok.jpg"]
    labels = ctx.labels(dataset.entry(dataset.root / "bad/images/ok.jpg"))
    assert condition.highlight(labels, dataset) == lines


def test_a_range_that_excludes_identical_boxes_finds_none_of_them(ctx):
    assert keys(Overlap("any", 0.5, 0.98), ctx) == []


def test_an_overlap_reads_as_words_and_survives_its_json(dataset):
    condition = Overlap("same", 0.99, 1.0)
    assert condition.describe(dataset) == "labels overlapping, same class, IoU 0.99–1.00"
    assert Overlap("different", 0.5, 1.0).describe(dataset) == "labels overlapping, different classes, IoU 0.50–1.00"
    assert condition_from_json(condition.to_json()) == condition


@pytest.mark.parametrize("args, why", [
    (("both", 0.5, 1.0), "unknown overlap scope 'both'"),
    (("same", 0.9, 0.5), "IoU: 0.9 is above 0.5: put the lower end first"),
    (("same", 0.5, 1.5), "IoU: the upper end cannot be above 1"),
])
def test_an_unusable_overlap_is_refused(args, why):
    with pytest.raises(ValueError, match=why):
        Overlap(*args)
