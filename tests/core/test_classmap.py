"""The class map: model class names onto dataset class names, kept per model class list
(docs/design/2026-10-05-model-assist.md#the-class-map)."""

import pytest
import yaml

from deeplabeling.core.classmap import CLASS_MAPS, ClassMap, load_class_map, normalize, save_class_map
from deeplabeling.core.dataset import Dataset
from deeplabeling.core.settings import JsonFile, Settings

MODEL = ("BSD", "Bus-M", "car", "human")                     # a model's classes, by id


@pytest.fixture
def dataset(ds):
    return Dataset.open(ds.yaml)                            # person, car, bus_m, bus_l


@pytest.fixture
def settings(tmp_path):
    return Settings(JsonFile(tmp_path / "dataset.json"), "root", ("root",))


def test_names_match_ignoring_case_spaces_dashes_and_underscores():
    assert normalize("Bus_M") == normalize("bus m") == normalize("busm") == normalize("BUS-M")


def test_a_new_map_is_seeded_by_name(dataset):
    cmap = ClassMap.seeded(MODEL, dataset.names)
    assert cmap.targets == (None, "bus_m", "car", None)
    assert [cmap.translate(i, dataset) for i in range(4)] == [None, 2, 1, None]


def test_a_class_past_the_model_list_translates_to_nothing(dataset):
    assert ClassMap.seeded(MODEL, dataset.names).translate(9, dataset) is None


def test_a_map_is_kept_by_the_model_class_list(dataset, settings):
    cmap = load_class_map(settings, MODEL, dataset.names).with_target(3, "person")
    save_class_map(settings, cmap)
    assert load_class_map(settings, MODEL, dataset.names) == cmap        # retrained, same classes
    other = load_class_map(settings, ("car", "truck"), dataset.names)     # another best.pt
    assert other.targets == ("car", None)


def test_a_yaml_without_the_mapped_name_translates_it_to_nothing(dataset, ds):
    cmap = ClassMap.seeded(MODEL, dataset.names)
    assert cmap.translate(1, dataset) == 2
    data = yaml.safe_load(ds.yaml.read_text(encoding="utf-8"))
    data["names"] = ["person", "car"]                       # another yaml of the root, no bus_m
    (ds.root / "two.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    seven = Dataset.open(ds.root / "two.yaml")
    assert cmap.translate(1, seven) is None and cmap.translate(2, seven) == 1


def test_a_stored_map_missing_a_class_seeds_that_one_and_drops_strangers(dataset, settings):
    key = ClassMap.seeded(MODEL, dataset.names).key
    settings.set(CLASS_MAPS, {key: {"car": None, "human": "person", "ghost": "bus_l"}})
    cmap = load_class_map(settings, MODEL, dataset.names)
    assert cmap.targets == (None, "bus_m", None, "person")   # car stays unmapped: the user chose
    assert cmap.to_json() == {"BSD": None, "Bus-M": "bus_m", "car": None, "human": "person"}


def test_the_settings_refuse_what_is_not_a_map_of_maps(settings):
    with pytest.raises(ValueError):
        settings.set(CLASS_MAPS, {"k": ["car"]})
