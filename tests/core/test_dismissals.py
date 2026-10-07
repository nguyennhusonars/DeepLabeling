"""Findings looked at and judged fine (docs/design/2026-10-06-find-bad.md#dismissals)."""

import json

from deeplabeling.core.dismissals import Dismissals

CAR = ("camA/images/0001.jpg", "1 0.250000 0.250000 0.100000 0.100000", "wrong class")


def dismissals(tmp_path):
    return Dismissals(tmp_path / "dismissals.json", tmp_path / "root")


def test_a_dismissal_is_the_image_the_line_as_it_is_and_the_kind(tmp_path):
    d = dismissals(tmp_path)
    assert d.dismiss(*CAR) and not d.dismiss(*CAR)
    assert d.has(*CAR)
    assert not d.has(CAR[0], "1 0.300000 0.250000 0.100000 0.100000", CAR[2])     # the line edited since
    assert not d.has(CAR[0], CAR[1], "weakly seen")                             # another kind
    assert d.toggle(*CAR) is False and not d.has(*CAR) and d.toggle(*CAR) is True


def test_a_snapshot_is_safe_to_hand_to_a_worker(tmp_path):
    d = dismissals(tmp_path)
    d.dismiss(*CAR)
    snap = d.snapshot()
    d.undismiss(*CAR)
    assert snap == frozenset({CAR}) and d.snapshot() == frozenset()


def test_save_writes_version_root_and_dismissals_and_reloads(tmp_path):
    d = dismissals(tmp_path)
    d.dismiss(*CAR)
    assert d.save() and not d.dirty
    data = json.loads((tmp_path / "dismissals.json").read_text())
    assert data == {"version": 1, "root": str(tmp_path / "root"), "dismissed": [list(CAR)]}
    assert dismissals(tmp_path).has(*CAR)


def test_nothing_to_save_writes_nothing(tmp_path):
    assert not dismissals(tmp_path).save()
    assert not (tmp_path / "dismissals.json").exists()


def test_an_unreadable_file_is_kept_and_dismissals_start_empty(tmp_path):
    (tmp_path / "dismissals.json").write_bytes(b"{broken")
    d = dismissals(tmp_path)
    assert d.snapshot() == frozenset() and "kept as" in d.warning
    d.dismiss(*CAR)
    assert d.save()
    kept = [p for p in tmp_path.iterdir() if ".unreadable-" in p.name]
    assert len(kept) == 1 and kept[0].read_bytes() == b"{broken"


def test_a_bad_entry_is_skipped_and_said(tmp_path):
    (tmp_path / "dismissals.json").write_text('{"version": 1, "dismissed": [["a", "0 1 1 1 1", "wrong class"], ["b"]]}')
    d = dismissals(tmp_path)
    assert d.snapshot() == {("a", "0 1 1 1 1", "wrong class")} and "1 unreadable dismissal" in d.warning


def test_a_workspace_keeps_and_saves_its_dataset_s_dismissals(ds):
    from deeplabeling.core.workspace import Workspace

    ws = Workspace.open(ds.yaml, confirm_taxonomy=lambda *a: True)
    ws.dismissals.dismiss(*CAR)
    ws.close()
    again = Workspace.open(ds.yaml, confirm_taxonomy=lambda *a: True)
    try:
        assert again.dismissals.has(*CAR) and again.dismissals.path.name == "dismissals.json"
    finally:
        again.close()


def test_a_snapshot_is_made_once_until_a_dismissal_changes(tmp_path):
    d = dismissals(tmp_path)
    d.dismiss(*CAR)
    first = d.snapshot()
    assert d.snapshot() is first                    # a build, and every late join, share it
    d.dismiss(*CAR)                                 # already: nothing changed
    assert d.snapshot() is first
    d.undismiss(*CAR)
    assert d.snapshot() == frozenset() and d.snapshot() is not first
