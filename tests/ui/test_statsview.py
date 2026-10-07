"""The statistics as tables, and as TSV (docs/design/2026-10-07-bulk-and-stats.md#the-dialog)."""

import pytest

from deeplabeling.core.dataset import Dataset
from deeplabeling.core.imagesize import ImageSizes
from deeplabeling.core.stats import stats_of
from deeplabeling.core.store import LabelStore
from deeplabeling.ui.statsview import class_table, files_table, per_image_table, sizes_table, tsv

NAMES = ("person", "car", "bus_m", "bus_l")


@pytest.fixture
def stats(ds):
    dataset = Dataset.open(ds.yaml)
    return stats_of(dataset.images, LabelStore(dataset).get, ImageSizes().get)


def test_the_classes_table_has_a_row_per_class_then_per_unnamed_id(stats):
    header, rows = class_table(stats, NAMES)
    assert header == ["class", "train boxes", "train images", "train polygons",
                      "val boxes", "val images", "val polygons"]
    assert rows == [["person", "4", "4", "0", "8", "5", "1"], ["car", "1", "1", "0", "5", "5", "2"],
                    ["bus_m", "3", "3", "0", "0", "0", "0"], ["bus_l", "0", "0", "0", "0", "0", "0"],
                    ["#-1?", "0", "0", "0", "1", "1", "0"], ["#99?", "0", "0", "0", "1", "1", "0"]]


def test_the_label_files_table_has_a_row_per_split(stats):
    header, rows = files_table(stats)
    assert header == ["split", "images", "with boxes", "negative", "missing", "unreadable", "shared",
                      "unparsable lines"]
    assert rows == [["train", "10", "7", "1", "2", "0", "2", "0"], ["val", "5", "5", "0", "0", "0", "0", "4"]]


def test_the_box_sizes_table_ends_with_the_images_it_could_not_size(stats):
    header, rows = sizes_table(stats, NAMES)
    assert header == ["class", "< 8", "8–16", "16–32", "32–64", "64–128", "128–256", "≥ 256"]
    assert rows[:3] == [["person", "4", "7", "0", "0", "0", "0", "0"], ["car", "3", "2", "0", "0", "0", "0", "0"],
                        ["bus_m", "0", "3", "0", "0", "0", "0", "0"]]
    assert rows[-1] == ["images whose header cannot be read: 1"]


def test_the_boxes_per_image_table_runs_to_twenty_or_more(stats):
    header, rows = per_image_table(stats)
    assert header == ["boxes", "images"] and len(rows) == 21
    assert rows[:3] == [["0", "3"], ["1", "6"], ["2", "5"]] and rows[7] == ["7", "1"] and rows[-1] == ["20+", "0"]


def test_a_table_copies_as_tab_separated_lines():
    assert tsv(["a", "b"], [["1", "2"], ["3"]]) == "a\tb\n1\t2\n3\n"
