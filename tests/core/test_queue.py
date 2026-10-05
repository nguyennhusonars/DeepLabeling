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


def test_index_of_finds_a_row_by_key(dataset):
    q = Queue(ImageFilter())
    q.extend(all_items(dataset)[:3])
    assert q.index_of(dataset.images[2].rel) == 2 and q.index_of("nope") is None


def test_a_failed_build_keeps_what_came_and_settles_the_cursor(dataset):
    q = Queue(ImageFilter(), follow=dataset.images[5])
    q.extend(all_items(dataset)[:3])
    q.fail("OSError: the disk went away")
    assert len(q) == 3 and q.complete and q.failed == "OSError: the disk went away"
    assert q.cursor == dataset.images[2].rel            # the followed item never came
