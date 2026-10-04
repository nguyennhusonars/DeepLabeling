"""Read-only checks against the real pvn-vehicle dataset, skipped where it is absent.

Nothing here writes: the dataset is opened and its paths compared."""

import glob
from pathlib import Path

import pytest
import yaml

from deeplabeling.core.dataset import IMG_FORMATS, Dataset
from deeplabeling.core.paths import training_label_path

PVN = Path("/home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle")
pytestmark = pytest.mark.skipif(not (PVN / "data_13class.yaml").is_file(),
                                reason="pvn-vehicle is not on this machine")


def test_data_13class_opens_to_what_training_reads():
    yml = PVN / "data_13class.yaml"
    data = yaml.safe_load(yml.read_text())
    expected = set()
    for split in ("train", "val"):
        for folder in data[split]:
            where = (PVN / folder).resolve()
            expected |= {f for f in glob.glob(f"{glob.escape(str(where))}/**/*.*", recursive=True)
                         if f.rpartition(".")[-1].lower() in IMG_FORMATS}
    d = Dataset.open(yml)
    assert {str(e.path) for e in d.images} == expected
    assert all(e.label_path == training_label_path(e.path) for e in d.images)
    assert d.names == tuple(data["names"])
