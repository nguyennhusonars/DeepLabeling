"""Bulk reassign, planned and written as one edit
(docs/design/2026-10-07-bulk-and-stats.md#bulk-reassign)."""

import pytest

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.editor import Editor
from deeplabeling.core.history import History
from deeplabeling.core.reassign import Reassign, plan_reassign
from deeplabeling.core.review import ReviewMarks
from deeplabeling.core.store import LabelStore
from fixtures import CAMA_0001, CRLF, MIXED, POLY1, assert_only_changed, read_exact

#: Every class-0 box of the edge-case dataset, as person -> bus_l (3) writes it.
WRITTEN = {"camA/labels/0001.txt", "weird/labels/имя пробел.txt", "bad/labels/corrupt.txt",
           "bad/labels/ok.txt", "crlf/labels/c.txt", "seg/labels/poly1.txt", "seg/labels/mixed.txt"}
GAUNTLET_AFTER = (
    "1 0.5 0.5 0.2 0.2\n"
    "99 0.5 0.5 0.1 0.1\n"
    "-1 0.5 0.5 0.1 0.1\n"
    "3 1.4 0.5 0.2 0.2\n"
    "0 0.5 0.5\n"                   # unparsable: left as it is
    "3 0.5 0.5 0.2 0.2 0.95\n"
    "3 0.5 0.5 0.2 0.2\r\n"
    "abc 0.5 0.5 0.2 0.2\n"
    "\n"
    "   \n"
    "3 0.5 0.5 0.2 0.2"             # still no final newline: only the class token changes
)


@pytest.fixture
def setup(ds, tmp_path):
    dataset = Dataset.open(ds.yaml)
    store = LabelStore(dataset)
    editor = Editor(store, History(store), ReviewMarks(tmp_path / "review.json", dataset.root))
    return dataset, store, editor


def test_every_box_of_the_class_becomes_the_other_and_nothing_else_changes(ds, setup):
    dataset, store, editor = setup
    plan = plan_reassign(dataset.images, store.get, 0, 3, "reassign person to bus_l")
    assert (plan.boxes, len(plan.intents), plan.read_only) == (10, 7, 2)      # the twins share a file
    before = ds.snapshot()
    editor.apply_many(plan.intents, "reassign person to bus_l")
    assert_only_changed(before, ds.snapshot(), WRITTEN)
    assert read_exact(ds.lbl("camA/0001")) == "3" + CAMA_0001[1:]
    assert read_exact(ds.lbl("crlf/c")) == "3" + CRLF[1:]                     # CRLF kept
    assert read_exact(ds.lbl("seg/poly1")) == "3" + POLY1[1:]                 # a polygon keeps its points
    assert read_exact(ds.lbl("seg/mixed")) == "3" + MIXED[1:]
    assert read_exact(ds.lbl("bad/ok")) == GAUNTLET_AFTER
    assert editor.history.depth == 1 and editor.undo() is not None                  # one edit, undone whole
    assert read_exact(ds.lbl("camA/0001")) == CAMA_0001


def test_an_id_the_yaml_does_not_name_can_be_reassigned(ds, setup):
    dataset, store, editor = setup
    plan = plan_reassign(dataset.images, store.get, 99, 1, "reassign #99 to car")
    assert (plan.boxes, len(plan.intents)) == (1, 1)
    editor.apply_many(plan.intents, "reassign #99 to car")
    assert read_exact(ds.lbl("bad/ok")).splitlines()[1] == "1 0.5 0.5 0.1 0.1"


def test_an_unreadable_label_file_is_counted_as_it_may_hold_the_class(ds, setup):
    dataset, store, _ = setup
    ds.lbl("camA/0001").chmod(0o000)
    try:
        plan = plan_reassign(dataset.images, LabelStore(dataset).get, 1, 2, "reassign car to bus_m")
    finally:
        ds.lbl("camA/0001").chmod(0o644)
    assert plan.read_only == 1 and all(i.image != ds.img("camA/0001.jpg") for i in plan.intents)


def test_plans_made_a_chunk_at_a_time_add_up(ds, setup):
    dataset, store, _ = setup
    whole = plan_reassign(dataset.images, store.get, 0, 3, "r")
    parts = [plan_reassign(dataset.images[i:i + 4], store.get, 0, 3, "r") for i in range(0, len(dataset.images), 4)]
    total = Reassign((), 0, 0)
    for part in parts:
        total += part
    assert total == whole


def test_a_class_onto_itself_is_refused(ds, setup):
    dataset, store, _ = setup
    with pytest.raises(ValueError, match="the same class"):
        plan_reassign(dataset.images, store.get, 1, 1, "r")



def test_a_crlf_file_without_a_final_newline_stays_crlf(ds, setup):
    dataset, store, editor = setup
    ds.lbl("crlf/c").write_bytes(b"0 0.5 0.5 0.2 0.2\r\n0 0.3 0.3 0.1 0.1")
    plan = plan_reassign(dataset.images, LabelStore(dataset).get, 0, 3, "r")
    editor.apply_many(plan.intents, "r")
    assert ds.lbl("crlf/c").read_bytes() == b"3 0.5 0.5 0.2 0.2\r\n3 0.3 0.3 0.1 0.1"
