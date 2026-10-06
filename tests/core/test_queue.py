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


def test_an_item_inserted_after_the_build_takes_its_place_in_dataset_order(dataset):
    items = all_items(dataset)
    queue = Queue(ImageFilter())
    queue.extend([items[0], items[3]])
    queue.go_to(items[3].key)
    assert queue.insert(items[1]) == 1 and queue.insert(items[1]) is None
    assert [it.key for it in queue.items] == [items[0].key, items[1].key, items[3].key]
    assert queue.cursor == items[3].key and queue.index_of(items[3].key) == 2


def test_an_item_inserted_into_an_empty_queue_takes_the_cursor(dataset):
    queue = Queue(ImageFilter())
    queue.insert(all_items(dataset)[2])
    assert queue.cursor == all_items(dataset)[2].key


def test_late_joins_into_a_long_queue_stay_quick():
    """A pass fills a model queue one image at a time, on the GUI thread: each join must
    not walk the whole queue."""
    import time
    from pathlib import Path

    from deeplabeling.core.dataset import ImageEntry

    def item(order):
        rel = f"img/{order:06d}.jpg"
        return QueueItem(rel, ImageEntry(Path("/x") / rel, Path("/x") / f"{order:06d}.txt", "train", rel, order))

    queue = Queue(ImageFilter())
    queue.extend(item(2 * k) for k in range(45_000))
    start = time.perf_counter()
    for k in range(1_000):
        queue.insert(item(2 * k * 45 + 1))                   # spread through the queue
    assert time.perf_counter() - start < 1.0
    assert [it.entry.order for it in queue.items] == sorted(it.entry.order for it in queue.items)
    assert all(queue.index_of(it.key) == i for i, it in enumerate(queue.items))


def test_a_queue_keeps_its_items_in_their_own_order(dataset):
    """A queue of findings is ordered by kind and score, not by image."""
    e = dataset.images
    items = [QueueItem(f"{e[3].rel}#0#wrong class", e[3], rank=(0, -0.9, e[3].order, 0)),
             QueueItem(f"{e[0].rel}#1#wrong class", e[0], rank=(0, -0.8, e[0].order, 1)),
             QueueItem(f"{e[0].rel}#0#not an object", e[0], rank=(1, -1.0, e[0].order, 0))]
    queue = Queue(ImageFilter())
    queue.extend(items)
    late = QueueItem(f"{e[5].rel}#0#wrong class", e[5], rank=(0, -0.85, e[5].order, 0))
    assert queue.insert(late) == 1
    assert [it.key for it in queue.items] == [items[0].key, late.key, items[1].key, items[2].key]
    assert queue.has_image(e[0].rel) and queue.keys_of(e[0].rel) == [items[1].key, items[2].key]
    assert queue.index_of(items[2].key) == 3 and not queue.has_image(e[1].rel)


def test_a_queue_refuses_items_out_of_their_order(dataset):
    e = dataset.images
    queue = Queue(ImageFilter())
    queue.extend([QueueItem(e[1].rel, e[1])])
    with pytest.raises(ValueError, match="out of order"):
        queue.extend([QueueItem(e[0].rel, e[0])])


def test_each_item_of_a_changed_image_is_rechecked_by_its_source(dataset, ctx):
    e = dataset.images[0]

    class OneHolds(ImageFilter):
        def holds(self, item, ctx):
            return item.key.endswith("#keep")

    queue = Queue(OneHolds())
    queue.extend([QueueItem(f"{e.rel}#keep", e, rank=(0,)), QueueItem(f"{e.rel}#gone", e, rank=(1,))])
    queue.recheck(e, ctx)
    assert queue.stale == {f"{e.rel}#gone"}
