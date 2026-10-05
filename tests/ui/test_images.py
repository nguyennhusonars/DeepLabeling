import threading

import pytest

from deeplabeling.ui.images import ImageCache, decode_image, decode_thumb
from deeplabeling.ui.workers import Jobs
from fixtures import make_exif_rotated_image, make_image


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


def test_a_thumbnail_is_decoded_at_display_size_and_keeps_its_aspect(tmp_path):
    make_image(tmp_path / "big.jpg", 640, 480)
    thumb = decode_thumb(tmp_path / "big.jpg")
    assert (thumb.width(), thumb.height()) == (160, 120)


def test_a_thumbnail_applies_exif_rotation(tmp_path):
    make_exif_rotated_image(tmp_path / "rot.jpg", 640, 480)
    thumb = decode_thumb(tmp_path / "rot.jpg")
    assert (thumb.width(), thumb.height()) == (120, 160)


def test_a_small_image_is_not_enlarged(ds):
    thumb = decode_thumb(ds.img("camA/0001.jpg"))
    assert (thumb.width(), thumb.height()) == (64, 48)


def test_an_unreadable_thumbnail_raises(ds):
    with pytest.raises(ValueError):
        decode_thumb(ds.img("bad/corrupt.jpg"))


def test_wanting_other_tiles_cancels_the_decodes_no_longer_in_view(qtbot, ds):
    gate = threading.Event()

    def slow(path):
        gate.wait(5)
        return decode_image(path)

    jobs = Jobs(1)
    cache = ImageCache(jobs, decode=slow)
    a, b, c = ds.img("camA/0001.jpg"), ds.img("camA/0002.jpg"), ds.img("camA/0003.jpg")
    ready = []
    cache.ready.connect(ready.append)
    cache.want([a, b])
    cache.want([c])                                 # scrolled: a and b left the view
    gate.set()
    qtbot.waitUntil(lambda: cache.get(c) is not None, timeout=5000)
    jobs.wait(5000)
    qtbot.wait(20)
    assert ready == [c] and cache.get(a) is None and cache.get(b) is None


def test_the_session_keeps_thumbnails_until_the_dataset_closes(qtbot, session, ds):
    path = ds.img("camA/0001.jpg")
    with qtbot.waitSignal(session.thumbs.ready, timeout=5000):
        session.thumbs.want([path])
    assert session.thumbs.get(path).width() == 64
    session.close()
    assert session.thumbs.get(path) is None
