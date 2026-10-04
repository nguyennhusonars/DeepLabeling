import pytest

from deeplabeling.ui.images import ImageCache, decode_image
from deeplabeling.ui.workers import Jobs
from fixtures import make_image


def test_decoding_applies_exif_rotation(ds):
    image = decode_image(ds.img("camB/rot.jpg"))
    assert (image.width(), image.height()) == (48, 64)


def test_an_unreadable_image_raises(ds):
    with pytest.raises(ValueError):
        decode_image(ds.img("bad/corrupt.jpg"))


def test_kept_images_are_decoded_and_served(qtbot, ds):
    cache = ImageCache(Jobs(2))
    with qtbot.waitSignals([cache.ready, cache.ready], timeout=5000):
        cache.keep([ds.img("camA/0001.jpg"), ds.img("camA/0002.jpg")])
    assert cache.get(ds.img("camA/0001.jpg")).width() == 64
    assert cache.error(ds.img("camA/0001.jpg")) is None


def test_an_undecodable_image_is_an_error_not_an_image(qtbot, ds):
    cache = ImageCache(Jobs(1))
    with qtbot.waitSignal(cache.failed, timeout=5000) as caught:
        cache.request(ds.img("bad/corrupt.jpg"))
    assert caught.args[0] == ds.img("bad/corrupt.jpg")
    assert cache.get(ds.img("bad/corrupt.jpg")) is None and cache.error(ds.img("bad/corrupt.jpg"))


def test_the_budget_evicts_old_images_but_never_kept_ones(qtbot, tmp_path):
    paths = [tmp_path / f"{i}.png" for i in range(4)]
    for p in paths:
        make_image(p, 100, 100)                       # 40 KB decoded each
    cache = ImageCache(Jobs(1), limit_bytes=60_000)
    for p in paths[:3]:
        with qtbot.waitSignal(cache.ready, timeout=5000):
            cache.request(p)
    assert cache.cached_bytes <= 60_000 and cache.get(paths[2]) is not None
    with qtbot.waitSignal(cache.ready, timeout=5000):
        cache.keep([paths[3], paths[2]])
    assert cache.get(paths[3]) is not None and cache.get(paths[2]) is not None


def test_a_decode_finishing_after_clear_is_ignored(qtbot, ds):
    jobs = Jobs(1)
    cache = ImageCache(jobs)
    ready = []
    cache.ready.connect(ready.append)
    cache.request(ds.img("camA/0001.jpg"))
    cache.clear()
    jobs.wait(5000)
    qtbot.wait(50)
    assert ready == [] and cache.get(ds.img("camA/0001.jpg")) is None
