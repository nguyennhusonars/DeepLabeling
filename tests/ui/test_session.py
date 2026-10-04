import pytest
import yaml

from deeplabeling.core.edits import AddBox, Intent
from deeplabeling.core.queue import HasClass, ImageFilter
from deeplabeling.ui.session import OUT_OF_RANGE, Session
from fixtures import FakePrompter, assert_only_changed, open_session

BOX = (0.5, 0.5, 0.2, 0.2)


def record(signal):
    got = []
    signal.connect(lambda *args: got.append(args))
    return got


def test_opening_builds_every_image_and_starts_on_the_first(session, ds):
    assert len(session.queue) == 15 and session.queue.complete
    assert session.current().key == "camA/images/0001.jpg"
    assert session.reviewed_counts() == (0, 15)


def test_ids_the_yaml_does_not_name_raise_a_standing_notice(qtbot, ds):
    s = Session(FakePrompter())
    with qtbot.waitSignal(s.standing, timeout=5000,
                          check_params_cb=lambda key, text: key == OUT_OF_RANGE and bool(text)) as caught:
        s.open(ds.yaml)
    assert "2 boxes in 1 images" in caught.args[1] and "data.yaml" in caught.args[1]
    s.close()


def test_paging_marks_nothing(session):
    for _ in range(3):
        assert session.move(1)
    session.move(-1)
    assert session.workspace.review.count() == 0


def test_done_and_next_marks_and_moves(session):
    session.done_and_next()
    assert session.workspace.review.is_marked("camA/images/0001.jpg")
    assert session.current().key == "camA/images/0002.jpg" and session.left() == 14


def test_the_end_of_the_queue_is_said_not_passed(session):
    status = record(session.status)
    session.go_to(session.queue.items[-1].key)
    assert not session.move(1)
    assert status[-1] == ("the end of the queue",)


def test_toggle_reviewed(session):
    session.toggle_reviewed()
    assert session.workspace.review.is_marked("camA/images/0001.jpg")
    session.toggle_reviewed()
    assert not session.workspace.review.is_marked("camA/images/0001.jpg")


def test_mark_negative_creates_an_empty_file_and_undo_removes_it(session, ds):
    session.go_to("camA/images/0003.jpg")
    before = ds.snapshot()
    changed = record(session.labelsChanged)
    session.mark_negative()
    assert_only_changed(before, ds.snapshot(), {"camA/labels/0003.txt"})
    assert ds.lbl("camA/0003").read_bytes() == b""
    assert changed == [((ds.img("camA/0003.jpg"),),)]
    assert session.workspace.review.is_marked("camA/images/0003.jpg")   # an edit marks
    session.undo()
    assert not ds.lbl("camA/0003").exists()
    session.redo()
    assert ds.lbl("camA/0003").read_bytes() == b""


def test_mark_negative_on_a_labelled_image_is_refused_visibly(session, ds):
    notices = record(session.notice)
    before = ds.snapshot()
    session.mark_negative()
    assert_only_changed(before, ds.snapshot(), set())
    level, text, image = notices[-1]
    assert level == "error" and "already has a label file" in text and image == ds.img("camA/0001.jpg")


def test_undo_goes_to_the_image_it_changes(session, ds):
    session.go_to("camA/images/0003.jpg")
    session.mark_negative()
    session.go_to("seg/images/poly1.jpg")
    session.undo()
    assert session.current().key == "camA/images/0003.jpg"


def test_an_undecodable_image_is_never_edited(qtbot, session, ds):
    with qtbot.waitSignal(session.images.failed, timeout=5000):
        session.go_to("bad/images/corrupt.jpg")
    notices, before = record(session.notice), ds.snapshot()
    session.apply(Intent(ds.img("bad/corrupt.jpg"), (AddBox(0, BOX),), "draw"))
    assert_only_changed(before, ds.snapshot(), set())
    assert "cannot be decoded" in notices[-1][1]


def test_a_queue_and_its_cursor_survive_a_reopen(qtbot, ds):
    s = open_session(qtbot, ds.yaml)
    with qtbot.waitSignal(s.queueDone, timeout=5000):
        s.set_queue(ImageFilter(conditions=(HasClass(("bus_m",)),)))
    assert [it.key for it in s.queue.items] == [
        "camA/images/sub/0005.jpg", "camB/images/0001.jpg", "camB/images/rot.jpg"]
    s.go_to("camB/images/0001.jpg")
    s.close()
    again = open_session(qtbot, ds.yaml)
    assert again.queue.source == ImageFilter(conditions=(HasClass(("bus_m",)),))
    assert again.current().key == "camB/images/0001.jpg"
    again.close()


def test_an_item_that_stops_matching_is_marked_not_removed(qtbot, session, ds):
    with qtbot.waitSignal(session.queueDone, timeout=5000):
        session.set_queue(ImageFilter(conditions=(HasClass(("car",)),)))
    changed = record(session.itemsChanged)
    ds.lbl("camA/0001").write_bytes(b"0 0.5 0.5 0.2 0.2\n")       # no car left
    session.labels(session.current().entry)                         # the store notices
    assert "camA/images/0001.jpg" in session.queue.stale and "camA/images/0001.jpg" in session.queue
    assert ["camA/images/0001.jpg"] in [args[0] for args in changed]
    assert session.badge(session.current()) == "1 box · no longer matches"


def test_badges(session):
    by_key = {it.key: it for it in session.queue.items}
    assert session.badge(by_key["camA/images/0001.jpg"]) == "2 boxes"
    assert session.badge(by_key["camA/images/0002.jpg"]) == "negative"
    assert session.badge(by_key["camA/images/0003.jpg"]) == "missing"
    assert session.badge(by_key["camB/images/twin.jpg"]) == "shared"
    assert session.describe_item(by_key["camA/images/0002.jpg"]).startswith("· camA/images/0002.jpg")


def test_go_to_by_number_or_name(session):
    assert session.go_to_text("3") and session.current().key == "camA/images/0003.jpg"
    assert session.go_to_text("POLY") and session.current().key == "seg/images/poly1.jpg"
    status = record(session.status)
    assert not session.go_to_text("nothing like it")
    assert "no item matches" in status[-1][0]


def test_a_root_already_open_is_refused_and_the_first_stays_open(qtbot, session, ds):
    prompter = FakePrompter()
    second = Session(prompter)
    assert not second.open(ds.yaml)
    assert "already open" in prompter.errors[0][1] and second.workspace is None
    assert session.workspace is not None


def test_a_failed_open_reopens_the_previous_dataset(qtbot, session, ds):
    assert not session.open(ds.root / "nowhere.yaml")
    assert session.prompter.errors and session.current_source()[0] == str(ds.yaml)


def test_declining_a_new_taxonomy_opens_nothing_and_says_nothing(qtbot, ds):
    open_session(qtbot, ds.yaml).close()
    data = yaml.safe_load(ds.yaml.read_text(encoding="utf-8"))
    data["names"] = ["a", "b"]
    other = ds.root / "other.yaml"
    other.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    prompter = FakePrompter(taxonomy=False)
    s = Session(prompter)
    assert not s.open(other)
    assert s.workspace is None and prompter.errors == [] and prompter.asked[0][0] == "taxonomy"


def test_the_reviewed_count_covers_this_datasets_images_only(session):
    session.workspace.review.mark("data_UK/images/elsewhere.jpg")
    session.toggle_reviewed()
    assert session.reviewed_counts() == (1, 15)


def test_a_failing_build_becomes_a_notice(qtbot, session):
    class Boom(ImageFilter):
        def build(self, ctx, emit, cancelled=lambda: False, **kw):
            raise RuntimeError("boom")

    with qtbot.waitSignal(session.notice, timeout=5000) as caught:
        session.set_queue(Boom())
    assert caught.args[0] == "error" and "RuntimeError: boom" in caught.args[1]


def test_closing_saves_and_frees_the_root(qtbot, ds, state_dir):
    s = open_session(qtbot, ds.yaml)
    s.done_and_next()
    s.close()
    assert list(state_dir.glob("datasets/*/review.json"))
    open_session(qtbot, ds.yaml).close()


def test_a_superseded_build_never_feeds_the_new_queue(qtbot, session):
    with qtbot.waitSignal(session.queueDone, timeout=5000):
        session.set_queue(ImageFilter(conditions=(HasClass(("car",)),)))
        session.set_queue(ImageFilter(conditions=(HasClass(("bus_m",)),)))
    qtbot.wait(100)                         # let any late batch of the first build arrive
    assert [it.key for it in session.queue.items] == [
        "camA/images/sub/0005.jpg", "camB/images/0001.jpg", "camB/images/rot.jpg"]


def test_an_outside_edit_to_the_image_on_screen_is_noticed_unasked(qtbot, session, ds):
    ds.lbl("camA/0001").write_bytes(b"3 0.5 0.5 0.1 0.1\n")
    with qtbot.waitSignal(session.labelsChanged, timeout=5000) as caught:
        pass                                # nothing touches the file: the watch must
    assert caught.args[0] == (ds.img("camA/0001.jpg"),)


def test_a_full_disk_while_opening_says_why(qtbot, ds, monkeypatch):
    from deeplabeling.core import workspace

    def full_disk(self):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(workspace.DatasetLock, "acquire", full_disk)
    prompter = FakePrompter()
    s = Session(prompter)
    assert not s.open(ds.yaml)
    assert s.workspace is None and "No space left" in prompter.errors[0][1]
