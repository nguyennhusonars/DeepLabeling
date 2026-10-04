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
