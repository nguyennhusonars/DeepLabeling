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
    assert r.marks == {"a": 5} and "1 unreadable review mark" in r.warning


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
