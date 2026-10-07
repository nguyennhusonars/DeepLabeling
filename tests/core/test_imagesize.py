"""Image sizes from the file header, EXIF orientation honoured, never decoded
(docs/knowledge/caches.md#image-sizes)."""

import threading

from PIL import Image

from deeplabeling.core import imagesize
from deeplabeling.core.imagesize import ImageSizes, image_size
from fixtures import make_image


def test_a_size_is_width_by_height(ds):
    assert image_size(ds.img("camA/0001.jpg")) == (64, 48)


def test_a_quarter_turn_in_exif_swaps_width_and_height(ds):
    assert image_size(ds.img("camB/rot.jpg")) == (48, 64)       # stored 64 x 48, orientation 6


def test_a_file_that_is_no_image_has_no_size(ds):
    assert image_size(ds.img("bad/corrupt.jpg")) is None
    assert image_size(ds.root / "nowhere.jpg") is None


def test_the_pixels_are_never_decoded(ds, monkeypatch):
    def refuse(self):
        raise AssertionError("decoded")

    monkeypatch.setattr(Image.Image, "load", refuse)
    assert image_size(ds.img("camB/rot.jpg")) == (48, 64)


def test_sizes_are_served_from_the_cache_while_the_file_is_unchanged(ds, monkeypatch):
    sizes, calls = ImageSizes(), []
    real = imagesize.image_size
    monkeypatch.setattr(imagesize, "image_size", lambda path: calls.append(path) or real(path))
    path = ds.img("camA/0001.jpg")
    assert sizes.get(path) == sizes.get(path) == (64, 48)
    assert len(calls) == 1
    make_image(path, 80, 60)                                     # replaced: a new stamp
    assert sizes.get(path) == (80, 60) and len(calls) == 2


def test_an_unreadable_size_is_cached_too_and_a_missing_file_is_none(ds, monkeypatch):
    sizes, calls = ImageSizes(), []
    real = imagesize.image_size
    monkeypatch.setattr(imagesize, "image_size", lambda path: calls.append(path) or real(path))
    assert sizes.get(ds.img("bad/corrupt.jpg")) is None and sizes.get(ds.img("bad/corrupt.jpg")) is None
    assert len(calls) == 1
    assert sizes.get(ds.root / "nowhere.jpg") is None


def test_many_threads_share_one_cache(ds):
    sizes, seen, errors = ImageSizes(), [], []

    def ask():
        try:
            for _ in range(50):
                seen.append(sizes.get(ds.img("camA/0001.jpg")))
        except Exception as e:                                  # pragma: no cover - the failure
            errors.append(e)

    threads = [threading.Thread(target=ask) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and set(seen) == {(64, 48)}


def test_a_workspace_keeps_one_cache_for_its_dataset(ds):
    from deeplabeling.core.workspace import Workspace

    ws = Workspace.open(ds.yaml, confirm_taxonomy=lambda *a: True)
    try:
        assert isinstance(ws.sizes, ImageSizes) and ws.sizes.get(ds.img("camB/rot.jpg")) == (48, 64)
    finally:
        ws.close()


def test_a_png_is_never_decoded_either(ds, monkeypatch):
    def refuse(self):
        raise AssertionError("decoded")

    monkeypatch.setattr(Image.Image, "load", refuse)
    assert image_size(ds.img("camB/twin.png")) == (64, 48)



def test_a_path_is_kept_as_given_not_copied(ds):
    from deeplabeling.core.imagesize import ImageSizes

    sizes, path = ImageSizes(), ds.img("camA/0001.jpg")
    sizes.get(path)
    assert next(iter(sizes._sizes)) is path                 # 45k copies were 45k survivors for the GC
