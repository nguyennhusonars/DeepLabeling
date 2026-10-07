"""Every launch path reaches Session.open and restores the same per-dataset settings
(docs/design/2026-10-04-app-foundation.md#state-and-settings)."""

import shutil

import pytest

from deeplabeling.__main__ import launch, parse_args
from deeplabeling.core.queue import HasClass, ImageFilter
from deeplabeling.ui.prompter import QtPrompter, taxonomy_question
from fixtures import FakePrompter

BUS_M = ImageFilter(conditions=(HasClass(("bus_m",)),))


def start(qtbot, argv, prompter=None):
    w = launch(argv, prompter or FakePrompter())
    qtbot.addWidget(w)
    if w.session.workspace is not None:
        qtbot.waitUntil(lambda: w.session.queue is not None and w.session.queue.complete)
    return w


def leave_with_queue(qtbot, w, source):
    with qtbot.waitSignal(w.session.queueDone, timeout=5000):
        w.session.set_queue(source)
    w.close()


def test_arguments():
    args = parse_args(["/d/images", "--labels", "/d/lbl"])
    assert (args.dataset, args.labels) == ("/d/images", "/d/lbl")
    assert parse_args([]).dataset is None


def test_a_yaml_on_the_command_line(qtbot, ds):
    w = start(qtbot, [str(ds.yaml)])
    assert w.session.current_source() == (str(ds.yaml), None)
    leave_with_queue(qtbot, w, BUS_M)
    again = start(qtbot, [str(ds.yaml)])
    assert again.session.queue.source == BUS_M
    again.close()


def test_an_image_folder_with_a_label_folder(qtbot, ds):
    frames, labels = ds.root / "frames", ds.root / "frame_labels"
    w = start(qtbot, [str(frames), "--labels", str(labels)])
    assert w.session.current_source() == (str(frames), str(labels))
    assert len(w.session.queue) == 1
    leave_with_queue(qtbot, w, ImageFilter(conditions=(HasClass(("0",), present=False),)))
    again = start(qtbot, [str(frames), "--labels", str(labels)])
    assert again.session.queue.source.conditions[0].present is False
    again.close()


def test_no_argument_reopens_the_last_dataset(qtbot, ds):
    leave_with_queue(qtbot, start(qtbot, [str(ds.yaml)]), BUS_M)
    w = start(qtbot, [])
    assert w.session.current_source() == (str(ds.yaml), None) and w.session.queue.source == BUS_M
    w.close()


def test_no_argument_and_the_last_dataset_gone_asks_for_one(qtbot, ds, tmp_path):
    copy = tmp_path / "copy"
    shutil.copytree(ds.root / "camA", copy / "camA")
    yml = copy / "data.yaml"
    yml.write_text(f"path: {copy}\ntrain: [camA/images]\nnames: [person, car]\n")
    start(qtbot, [str(yml)]).close()
    shutil.rmtree(copy)
    prompter = FakePrompter(yaml=ds.yaml)
    w = start(qtbot, [], prompter)
    qtbot.waitUntil(lambda: ("yaml",) in prompter.asked)
    qtbot.waitUntil(lambda: w.session.workspace is not None)
    assert w.session.current_source() == (str(ds.yaml), None)
    w.close()


def test_the_dataset_chip_opens_a_yaml_and_restores_its_settings(qtbot, ds):
    leave_with_queue(qtbot, start(qtbot, [str(ds.yaml)]), BUS_M)
    prompter = FakePrompter(yaml=ds.yaml)
    w = launch([str(ds.root / "camA/images")], prompter)
    qtbot.addWidget(w)
    with qtbot.waitSignal(w.session.queueDone, timeout=5000):
        w.open_yaml()
    assert w.session.current_source() == (str(ds.yaml), None) and w.session.queue.source == BUS_M
    w.close()


def test_an_image_folder_without_images_in_its_path_asks_for_its_labels(qtbot, ds):
    prompter = FakePrompter(folders=[ds.root / "frames", ds.root / "frame_labels"])
    w = start(qtbot, [str(ds.yaml)], prompter)
    with qtbot.waitSignal(w.session.queueDone, timeout=5000):
        w.open_folder()
    assert w.session.current_source() == (str(ds.root / "frames"), str(ds.root / "frame_labels"))
    assert [a for a in prompter.asked if a[0] == "folder"] == [
        ("folder", "Image folder"), ("folder", "Label folder for these images")]
    w.close()


def test_a_dataset_that_cannot_open_says_why(qtbot, ds):
    prompter = FakePrompter()
    w = start(qtbot, [str(ds.root / "frames")], prompter)
    assert w.session.workspace is None
    assert "label folder" in prompter.errors[0][1]
    assert w.canvas.message.startswith("📁 No dataset open")
    w.close()


def test_the_real_taxonomy_question_names_both_yamls(monkeypatch):
    text = taxonomy_question("/d/data_13class.yaml", ["a"] * 13, "/d/data_7class.yaml", ("b",) * 7)
    assert "data_13class.yaml: 13 classes" in text and "data_7class.yaml: 7 classes" in text
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    assert QtPrompter().confirm_taxonomy("/d/a.yaml", ["a"], "/d/b.yaml", ("b",)) is True
