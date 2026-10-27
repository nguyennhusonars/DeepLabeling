import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.findings import FindSettings, Findings
from deeplabeling.core.queue import (
    Boxes,
    HasClass,
    ImageFilter,
    LabelStateIs,
    ModelDisagrees,
    NameContains,
    Overlap,
    Reviewed,
)
from deeplabeling.core.blurry import Blurry, BlurSettings
from deeplabeling.ui.queue_editor import QueueEditor


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)


def editor(qtbot, dataset, current, **kw):
    dialog = QueueEditor(dataset, current, **kw)
    qtbot.addWidget(dialog)
    return dialog


@pytest.mark.parametrize("current", [
    ImageFilter(),
    ImageFilter(("val",), (HasClass(("car", "bus_l")), LabelStateIs("boxes"),
                           Reviewed(False), NameContains("cam"))),
    ImageFilter(conditions=(HasClass(("person",), present=False), LabelStateIs("missing"))),
    ImageFilter(conditions=(Boxes(("car", "bus_m"), w=(10, 30), unit="px"), Reviewed(False))),
    ImageFilter(conditions=(Boxes((), h=(None, 5), unit="%"), Overlap("same", 0.99, 1.0))),
    ImageFilter(conditions=(Overlap("different", 0.5, 1.0), ModelDisagrees("either", 0.6, (0.3, 0.9)))),
    ImageFilter(conditions=(ModelDisagrees("unseen"),)),
])
def test_the_editor_is_seeded_from_the_queue_in_force(qtbot, dataset, current):
    assert editor(qtbot, dataset, current).filter() == current


@pytest.mark.parametrize("setup, why", [
    (lambda d: d.class_mode.setCurrentText("has"), "Classes — choose a class, or any class"),
    (lambda d: d.class_mode.setCurrentText("lacks"), "Classes — choose a class, or any class"),
    (lambda d: [box.setChecked(False) for box in d.splits.values()], "Splits — choose at least one"),
])
def test_a_choice_left_half_made_is_refused_not_ignored(qtbot, dataset, setup, why):
    dialog = editor(qtbot, dataset, ImageFilter())
    setup(dialog)
    with pytest.raises(ValueError, match=why):
        dialog.filter()


def test_the_widgets_build_the_filter(qtbot, dataset):
    dialog = editor(qtbot, dataset, ImageFilter())
    dialog.splits["train"].setChecked(False)
    dialog.class_mode.setCurrentText("lacks")
    dialog.classes.item(1).setCheckState(Qt.Checked)
    dialog.review_mode.setCurrentText("not reviewed")
    dialog.name.setText("  seg ")
    assert dialog.filter() == ImageFilter(("val",), (HasClass(("car",), present=False),
                                                     Reviewed(False), NameContains("seg")))



def test_the_new_rows_build_their_conditions(qtbot, dataset):
    dialog = editor(qtbot, dataset, ImageFilter(), conf=0.4)
    dialog.class_mode.setCurrentText("has")
    dialog.classes.item(1).setCheckState(Qt.Checked)
    dialog.size_w_hi.setText("10")
    dialog.size_unit.setCurrentText("%")
    dialog.overlap_mode.setCurrentText("same class")
    dialog.overlap_lo.setText("0.99")
    dialog.model_mode.setCurrentText("unlabelled predictions")
    assert dialog.filter() == ImageFilter(conditions=(
        Boxes(("car",), w=(None, 10), unit="%"), Overlap("same", 0.99, 1.0),
        ModelDisagrees("unlabelled", 0.5, (0.4, 1.0))))


def test_a_size_with_any_class_is_a_size_of_any_box(qtbot, dataset):
    dialog = editor(qtbot, dataset, ImageFilter())
    dialog.size_h_lo.setText("100")
    assert dialog.filter() == ImageFilter(conditions=(Boxes((), h=(100, None), unit="px"),))


@pytest.mark.parametrize("setup, why", [
    (lambda d: (d.size_w_lo.setText("30"), d.size_w_hi.setText("10")),
     "Box size — width: 30 is above 10: put the lower end first"),
    (lambda d: d.size_w_lo.setText("abc"), "Box size — width: “abc” is not a number"),
    (lambda d: (d.class_mode.setCurrentText("lacks"), d.classes.item(0).setCheckState(Qt.Checked),
                d.size_w_hi.setText("10")),
     "Box size — needs Classes: has, or any class"),
    (lambda d: (d.overlap_mode.setCurrentText("any class"), d.overlap_hi.setText("1.5")),
     "Overlap — IoU: the upper end cannot be above 1"),
    (lambda d: (d.model_mode.setCurrentText("either"), d.model_lo.setText("0.05")),
     "Model — confidence: the lower end cannot be below 0.1"),
    (lambda d: (d.model_mode.setCurrentText("either"), d.model_iou.setText("")),
     "Model — matching IoU: “” is not a number"),
    (lambda d: (d.overlap_mode.setCurrentText("same class"), d.overlap_lo.setText("abc")),
     "Overlap — IoU: “abc” is not a number"),
])
def test_ok_refuses_by_name_and_the_dialog_stays_open(qtbot, dataset, setup, why):
    dialog = editor(qtbot, dataset, ImageFilter())
    dialog.show()
    setup(dialog)
    dialog.accept()
    assert dialog.isVisible() and dialog.result() != QDialog.Accepted
    assert dialog.error.text() == why and dialog.error.isVisible()


def test_ok_takes_what_the_rows_say_once_they_are_right(qtbot, dataset):
    dialog = editor(qtbot, dataset, ImageFilter())
    dialog.show()
    dialog.size_w_lo.setText("30")
    dialog.size_w_hi.setText("10")
    dialog.accept()
    dialog.size_w_lo.setText("5")
    dialog.accept()
    assert dialog.result() == QDialog.Accepted
    assert dialog.chosen == ImageFilter(conditions=(Boxes((), w=(5, 10), unit="px"),))


def test_every_row_is_visible_inside_the_dialog_and_none_overlaps(qtbot, dataset):
    from PySide6.QtCore import QPoint, QRect

    dialog = editor(qtbot, dataset, ImageFilter(conditions=(Overlap("same", 0.5, 1.0), ModelDisagrees("either"))))
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    widgets = [dialog.size_w_lo, dialog.size_w_hi, dialog.size_h_lo, dialog.size_h_hi, dialog.size_unit,
               dialog.overlap_mode, dialog.overlap_lo, dialog.overlap_hi,
               dialog.model_mode, dialog.model_iou, dialog.model_lo, dialog.model_hi]
    rects = []
    for w in widgets:
        rect = QRect(w.mapTo(dialog, QPoint(0, 0)), w.size())
        assert w.isVisible() and w.width() >= 30 and dialog.rect().contains(rect)
        assert not any(rect.intersects(r) for r in rects)
        rects.append(rect)
    assert dialog.height() <= 800



def test_a_saved_value_comes_back_exactly(qtbot, dataset):
    current = ImageFilter(conditions=(ModelDisagrees("unseen", 0.55, (0.123456789, 1.0)),))
    assert editor(qtbot, dataset, current).filter() == current


@pytest.mark.parametrize("current", [
    Findings(),
    Findings(ImageFilter(("val",), (NameContains("cam"),)),
             FindSettings(floor=0.5, match_iou=0.6, ceiling=0.9, band=(0.05, 0.3), weak=True, cutoff=0.7)),
    Findings(settings=FindSettings(wrong_class=False, band=(0.123456789, None))),
])
def test_a_findings_queue_seeds_its_scope_and_its_settings(qtbot, dataset, current):
    assert editor(qtbot, dataset, current).source() == current


def test_findings_start_from_the_default_settings_and_their_rows_show_only_for_findings(qtbot, dataset):
    dialog = editor(qtbot, dataset, ImageFilter(conditions=(Reviewed(False),)), conf=0.25)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    assert dialog.source() == ImageFilter(conditions=(Reviewed(False),)) and not dialog.find_rows.isVisible()
    dialog.source_kind.setCurrentText("Find Bad")
    assert dialog.find_rows.isVisible() and dialog.find_floor.text() == "0.4"      # never the model's 0.25
    assert dialog.source() == Findings(ImageFilter(conditions=(Reviewed(False),)), FindSettings())
    dialog.accept()
    assert dialog.chosen == Findings(ImageFilter(conditions=(Reviewed(False),)), FindSettings())


@pytest.mark.parametrize("setup, why", [
    (lambda d: d.find_floor.setText("x"), "Find Bad — confidence floor: “x” is not a number"),
    (lambda d: d.find_floor.setText("0.05"), "Find Bad — confidence floor: must be from 0.1 to 1"),
    (lambda d: (d.find_weak.setChecked(True), d.find_cutoff.setText("0.3")),
     "Find Bad — weak cutoff: 0.3 is not above the confidence floor 0.4"),
    (lambda d: d.find_band_hi.setText("abc"), "Find Bad — not-an-object band: “abc” is not a number"),
    (lambda d: (d.find_wrong.setChecked(False), d.find_not_object.setChecked(False)),
     "Find Bad — choose at least one kind of finding"),
])
def test_find_bad_settings_are_refused_by_name(qtbot, dataset, setup, why):
    dialog = editor(qtbot, dataset, Findings())
    dialog.show()
    setup(dialog)
    dialog.accept()
    assert dialog.isVisible() and dialog.result() != QDialog.Accepted
    assert dialog.error.text() == why and dialog.error.isVisible()


def test_the_find_bad_rows_are_visible_inside_the_dialog_and_none_overlaps(qtbot, dataset):
    from PySide6.QtCore import QPoint, QRect

    dialog = editor(qtbot, dataset, Findings(ImageFilter(conditions=(ModelDisagrees("either"),))))
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    widgets = [dialog.source_kind, dialog.find_floor, dialog.find_iou, dialog.find_wrong, dialog.find_ceiling,
               dialog.find_not_object, dialog.find_band_lo, dialog.find_band_hi, dialog.find_weak, dialog.find_cutoff,
               dialog.model_mode, dialog.model_hi]
    rects = []
    for w in widgets:
        rect = QRect(w.mapTo(dialog, QPoint(0, 0)), w.size())
        assert w.isVisible() and w.width() >= 30 and dialog.rect().contains(rect)
        assert not any(rect.intersects(r) for r in rects)
        rects.append(rect)
    assert dialog.height() <= 800



def test_the_model_confidence_is_seeded_as_the_value_itself(qtbot, dataset):
    dialog = editor(qtbot, dataset, ImageFilter(), conf=0.123456789)
    assert dialog.model_lo.text() == "0.123456789"


def test_the_dialog_says_how_its_rows_combine(qtbot, dataset):
    from PySide6.QtWidgets import QGroupBox

    dialog = editor(qtbot, dataset, Findings())
    titles = [g.title() for g in dialog.findChildren(QGroupBox)]
    assert titles == ["Images — all must hold", "Find Bad — any checked kind",
                      "Blurry — the blurriest of each class and size"]
    assert dialog.find_rows.title() == "Find Bad — any checked kind"


def test_a_condition_that_is_off_shows_no_fields_and_keeps_its_values(qtbot, dataset):
    dialog = editor(qtbot, dataset, ImageFilter())
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    params = [dialog.overlap_lo, dialog.overlap_hi, dialog.model_iou, dialog.model_lo, dialog.model_hi]
    assert not any(w.isVisible() for w in params) and not dialog.classes.isVisible()
    dialog.overlap_mode.setCurrentText("same class")
    dialog.model_mode.setCurrentText("either")
    dialog.class_mode.setCurrentText("has")
    assert all(w.isVisible() for w in params) and dialog.classes.isVisible()
    assert dialog.overlap_lo.text() == "0.5" and dialog.model_lo.text() == "0.25"
    rows = dialog.classes.count()
    assert dialog.classes.height() <= rows * dialog.classes.sizeHintForRow(0) + 12   # as tall as its rows


@pytest.mark.parametrize("settings", [BlurSettings(0.1, 24), BlurSettings(0.07, 16), BlurSettings()])
def test_a_blurry_queue_seeds_the_dialog_and_comes_back_unchanged(qtbot, dataset, settings):
    current = Blurry(ImageFilter(("val",), (NameContains("cam"),)), settings)
    dialog = editor(qtbot, dataset, current)
    assert dialog.source_kind.currentText() == "Blurry"
    assert dialog.blur_share.text() == f"{settings.share * 100:g}" and dialog.blur_min_side.text() == str(settings.min_side)
    assert dialog.source() == current


def test_the_blurry_group_shows_only_for_blurry_and_warns(qtbot, dataset):
    from PySide6.QtWidgets import QLabel

    dialog = editor(qtbot, dataset, ImageFilter())
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    assert not dialog.blur_rows.isVisible()
    dialog.source_kind.setCurrentText("Blurry")
    assert dialog.blur_rows.isVisible() and not dialog.find_rows.isVisible()
    assert dialog.blur_rows.title() == "Blurry — the blurriest of each class and size"
    warning = [w for w in dialog.blur_rows.findChildren(QLabel) if w.text() == "A deleted label leaves its object as background."]
    assert warning and warning[0].isVisible()
    assert dialog.source() == Blurry(ImageFilter(), BlurSettings())


@pytest.mark.parametrize("share, side, why", [
    ("0", "16", "Blurry — share: must be above 0% and at most 100%"),
    ("101", "16", "Blurry — share: must be above 0% and at most 100%"),
    ("x", "16", "Blurry — share: “x” is not a number"),
    ("5", "7", "Blurry — minimum side: must be from 8 to 4096 px"),
    ("5", "16.5", "Blurry — minimum side: “16.5” is not a whole number"),
])
def test_blurry_settings_are_refused_by_name_and_the_dialog_stays_open(qtbot, dataset, share, side, why):
    dialog = editor(qtbot, dataset, Blurry())
    dialog.blur_share.setText(share)
    dialog.blur_min_side.setText(side)
    dialog.accept()
    assert dialog.result() != QDialog.Accepted and dialog.error.text() == why and dialog.chosen is None


def test_the_blurry_rows_are_visible_inside_the_dialog_and_none_overlaps(qtbot, dataset):
    from PySide6.QtCore import QPoint, QRect

    dialog = editor(qtbot, dataset, Blurry())
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    rects = []
    for w in (dialog.source_kind, dialog.blur_share, dialog.blur_min_side):
        rect = QRect(w.mapTo(dialog, QPoint(0, 0)), w.size())
        assert w.isVisible() and w.width() >= 30 and dialog.rect().contains(rect)
        assert not any(rect.intersects(r) for r in rects)
        rects.append(rect)
