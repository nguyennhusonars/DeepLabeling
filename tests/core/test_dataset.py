import pytest
import yaml

from deeplabeling.core.dataset import FOLDER_SPLIT, Dataset, DatasetError
from deeplabeling.core.paths import training_label_path
from fixtures import CLASS_NAMES, make_image

ORDER = [
    "camA/images/0001.jpg", "camA/images/0002.jpg", "camA/images/0003.jpg",
    "camA/images/0004.JPG", "camA/images/sub/0005.jpg",
    "camB/images/0001.jpg", "camB/images/rot.jpg", "camB/images/twin.jpg",
    "camB/images/twin.png", "weird/images/имя пробел.jpg",
    "bad/images/corrupt.jpg", "bad/images/ok.jpg", "crlf/images/c.jpg",
    "seg/images/mixed.jpg", "seg/images/poly1.jpg",
]


def rewrite_yaml(ds, **changes):
    data = yaml.safe_load(ds.yaml.read_text(encoding="utf-8"))
    data.update(changes)
    ds.yaml.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def test_images_are_found_recursively_and_sorted_train_first(ds):
    d = Dataset.open(ds.yaml)
    assert [e.rel for e in d.images] == ORDER
    assert [e.order for e in d.images] == list(range(len(ORDER)))
    assert d.splits == ("train", "val")
    assert [e.split for e in d.images].count("val") == 5


def test_label_paths_follow_the_training_rule(ds):
    d = Dataset.open(ds.yaml)
    assert all(e.label_path == training_label_path(e.path) for e in d.images)
    assert d.entry(ds.img("camA/sub/0005.jpg")).label_path == ds.lbl("camA/sub/0005")


def test_the_root_is_a_realpath_and_keys_are_posix(ds):
    d = Dataset.open(ds.yaml)
    assert d.root == ds.root.resolve()
    assert d.entry(ds.img("weird/имя пробел.jpg")).rel == "weird/images/имя пробел.jpg"


def test_names_and_groups(ds):
    d = Dataset.open(ds.yaml)
    assert d.names == tuple(CLASS_NAMES)
    assert d.groups["bus"] == ("bus_m", "bus_l")
    assert d.id_of("bus_l") == 3 and d.id_of("truck") is None
    assert d.known(3) and not d.known(4) and not d.known(-1)


def test_two_images_sharing_one_label_file_are_found(ds):
    assert Dataset.open(ds.yaml).shared_labels == {ds.lbl("camB/twin")}


def test_a_missing_listed_folder_is_recorded_not_fatal(ds):
    rewrite_yaml(ds, test=["gone/images"])
    d = Dataset.open(ds.yaml)
    assert d.missing == ((ds.root / "gone/images").resolve(),)
    assert len(d.images) == len(ORDER)


def test_an_image_listed_in_two_splits_appears_once_under_the_first(ds):
    rewrite_yaml(ds, test=["camA/images"])
    d = Dataset.open(ds.yaml)
    assert len(d.images) == len(ORDER)
    assert d.entry(ds.img("camA/0001.jpg")).split == "train"


def test_a_txt_list_of_images(ds):
    listing = ds.root / "list.txt"
    listing.write_text(f"./camA/images/0001.jpg\ncamB/images/0001.jpg\n{ds.img('crlf/c.jpg')}\n\n")
    rewrite_yaml(ds, train=["list.txt"], val=None)
    d = Dataset.open(ds.yaml)
    assert [e.rel for e in d.images] == ["camA/images/0001.jpg", "camB/images/0001.jpg", "crlf/images/c.jpg"]


def test_names_as_a_dict_with_a_gap(ds):
    rewrite_yaml(ds, names={0: "a", 2: "c"})
    assert Dataset.open(ds.yaml).names == ("a", "class_1", "c")


def test_nc_alone_gives_numbered_names(ds):
    data = yaml.safe_load(ds.yaml.read_text(encoding="utf-8"))
    del data["names"]
    data["nc"] = 2
    ds.yaml.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert Dataset.open(ds.yaml).names == ("class_0", "class_1")


def test_neither_names_nor_nc_is_refused(ds):
    data = yaml.safe_load(ds.yaml.read_text(encoding="utf-8"))
    del data["names"]
    ds.yaml.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(DatasetError, match="names"):
        Dataset.open(ds.yaml)


def test_a_relative_path_is_relative_to_the_yaml(ds):
    sub = ds.root / "cfg"
    sub.mkdir()
    data = yaml.safe_load(ds.yaml.read_text(encoding="utf-8"))
    data["path"] = ".."
    (sub / "data.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert Dataset.open(sub / "data.yaml").root == ds.root.resolve()


def test_a_yaml_listing_no_images_is_refused(ds):
    rewrite_yaml(ds, train=["gone/images"], val=None)
    with pytest.raises(DatasetError, match="no images"):
        Dataset.open(ds.yaml)


def test_something_that_is_not_a_dataset_is_refused(ds):
    with pytest.raises(DatasetError):
        Dataset.open(ds.lbl("camA/0001"))
    with pytest.raises(DatasetError):
        Dataset.open(ds.root / "nowhere")


def test_a_yaml_with_a_label_folder_is_refused(ds):
    with pytest.raises(DatasetError):
        Dataset.open(ds.yaml, labels=ds.root)


def test_a_folder_launch_uses_the_training_rule(ds):
    d = Dataset.open(ds.root / "camA/images")
    assert [e.rel for e in d.images] == ["0001.jpg", "0002.jpg", "0003.jpg", "0004.JPG", "sub/0005.jpg"]
    assert d.splits == (FOLDER_SPLIT,)
    assert d.entry(ds.img("camA/0001.jpg")).label_path == ds.lbl("camA/0001")
    assert d.names == ()
    assert d.known(57)


def test_a_folder_launch_reads_classes_txt(ds):
    (ds.root / "camA/labels/classes.txt").write_text("a\nb\n\n")
    assert Dataset.open(ds.root / "camA/images").names == ("a", "b")


def test_a_folder_with_no_images_component_needs_a_label_folder(ds):
    with pytest.raises(DatasetError, match="label folder"):
        Dataset.open(ds.root / "frames")
    d = Dataset.open(ds.root / "frames", labels=ds.root / "frame_labels")
    assert d.images[0].label_path == ds.root / "frame_labels/x0001.txt"


def test_an_explicit_label_folder_mirrors_subfolders(ds):
    make_image(ds.root / "frames/sub/y0001.jpg")
    d = Dataset.open(ds.root / "frames", labels=ds.root / "frame_labels")
    assert d.entry(ds.root / "frames/sub/y0001.jpg").label_path == ds.root / "frame_labels/sub/y0001.txt"
    assert d.entry(ds.root / "frames/x0001.jpg").label_path == ds.root / "frame_labels/x0001.txt"


def test_a_folder_with_no_images_is_refused(ds):
    (ds.root / "empty/images").mkdir(parents=True)
    with pytest.raises(DatasetError, match="no images"):
        Dataset.open(ds.root / "empty/images")


def test_opening_keys_tell_launches_apart(ds):
    by_yaml = Dataset.open(ds.yaml).opening_key
    by_folder = Dataset.open(ds.root / "frames", labels=ds.root / "l").opening_key
    assert by_yaml == str(ds.yaml) and by_folder != by_yaml and "|" in by_folder


def test_an_image_added_after_open_is_unknown(ds):
    d = Dataset.open(ds.yaml)
    make_image(ds.img("camA/late.jpg"))
    with pytest.raises(KeyError):
        d.entry(ds.img("camA/late.jpg"))
