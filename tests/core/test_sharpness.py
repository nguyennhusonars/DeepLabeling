"""The two sharpness measures (docs/design/2026-10-27-blurry.md#the-measure)."""

import cv2
import numpy as np
import pytest

from deeplabeling.core.crops import crop_rect
from deeplabeling.core.sharpness import box_rect, crete_roffet, is_flat, score_image, tiled_ratio
from fixtures import make_exif_rotated_image


def textured(seed=0, n=64):
    """A crop with detail at every scale, softened a little as a real image is."""
    noise = np.random.default_rng(seed).integers(0, 256, (n, n)).astype(np.uint8)
    return cv2.GaussianBlur(noise, (0, 0), 1.0)


def test_blur_lowers_both_measures():
    sharp = textured()
    blurred = cv2.GaussianBlur(sharp, (0, 0), 2.0)
    assert tiled_ratio(blurred) < tiled_ratio(sharp)
    assert crete_roffet(blurred) > crete_roffet(sharp)          # scikit-image's sense: 1 is blurriest


def test_flat_tiles_are_skipped():
    """A sharp patch on a plain background scores as sharp detail does: most tiles are
    plain, and kept they would put the 80th percentile on one of them."""
    crop = np.full((128, 128), 120, np.uint8)
    crop[:40, :40] = textured(1, 40)
    assert tiled_ratio(crop) == pytest.approx(tiled_ratio(textured(2, 128)), abs=0.5)


def test_a_flat_crop_is_flat():
    assert is_flat(np.full((40, 40), 17, np.uint8))
    assert is_flat(np.full((40, 40), 17, np.uint8) + np.eye(40, dtype=np.uint8))     # std under 2
    assert not is_flat(textured())


def test_the_port_equals_scikit_image():
    blur_effect = pytest.importorskip("skimage.measure").blur_effect
    for seed, n in ((0, 16), (1, 40), (2, 97)):
        g = textured(seed, n)
        assert crete_roffet(g) == pytest.approx(blur_effect(g, h_size=11), abs=1e-6)
    rect = textured(3, 60)[:, :23]                                  # not square
    assert crete_roffet(rect) == pytest.approx(blur_effect(rect, h_size=11), abs=1e-6)


def test_box_rect_is_the_crop_grids_rule_and_clips():
    assert box_rect((0.5, 0.5, 0.2, 0.2), 64, 48) == (26, 19, 38, 29)
    assert box_rect((0.98, 0.5, 0.2, 0.2), 64, 48)[2] == 64          # clipped at the right
    assert box_rect((1.5, 0.5, 0.2, 0.2), 64, 48) is None             # wholly off the frame
    assert box_rect((0.5, 0.5, 0.0, 0.2), 64, 48) is None             # no width
    x0, y0, x1, y1 = box_rect((0.5, 0.5, 0.2, 0.2), 640, 480)
    assert crop_rect((0.5, 0.5, 0.2, 0.2), None, 640, 480) == (x0 - 32, y0 - 32, x1 + 32, y1 + 32)   # padded by a quarter


def test_score_image_scores_each_rectangle_once_and_skips_small_ones():
    grey = np.zeros((100, 200), np.uint8)
    grey[:, :100] = textured(4, 100)
    boxes = [(0.25, 0.5, 0.3, 0.6), (0.25, 0.5, 0.3, 0.6), (0.9, 0.9, 0.02, 0.02), (0.75, 0.5, 0.3, 0.6)]
    scores = score_image(grey, boxes)
    assert [s[:4] for s in scores] == [box_rect(boxes[0], 200, 100), box_rect(boxes[3], 200, 100)]
    textured_score, flat_score = scores
    assert textured_score[4] is not None and textured_score[5] is not None
    assert flat_score[4:] == (None, None)                           # the black half is flat


def test_an_exif_rotated_image_is_read_as_shown(tmp_path):
    """The build measures boxes on the image as shown, as the crop grid draws them."""
    path = tmp_path / "rot.jpg"
    make_exif_rotated_image(path, 64, 48)                           # stored 64 x 48, shown 48 x 64
    assert cv2.imread(str(path), cv2.IMREAD_GRAYSCALE).shape == (64, 48)
