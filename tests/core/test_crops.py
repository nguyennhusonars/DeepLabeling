"""The review crop: the label is its subject, the model's box widens it only so far
(docs/knowledge/matching.md#the-nearest-box-and-the-review-crop)."""

from deeplabeling.core.crops import crop_rect


def test_a_label_alone_is_padded_by_a_quarter_of_its_larger_side():
    # a 100 x 40 px label at the centre of a 1000 x 1000 frame: pad 25
    assert crop_rect((0.5, 0.5, 0.1, 0.04), None, 1000, 1000) == (425, 455, 575, 545)


def test_the_pad_is_at_least_4_px():
    # an 8 x 8 px label: a quarter of 8 is 2, so 4
    assert crop_rect((0.5, 0.5, 0.008, 0.008), None, 1000, 1000) == (492, 492, 508, 508)


def test_the_model_s_box_widens_the_crop_to_hold_both():
    label, model = (0.5, 0.5, 0.1, 0.1), (0.55, 0.5, 0.1, 0.1)
    assert crop_rect(label, model, 1000, 1000) == (425, 425, 625, 575)


def test_a_long_prediction_reaches_at_most_twice_the_label_s_side():
    # a 400 x 40 prediction over a 40 x 40 label (IoU 0.1): the crop reaches 80 px each way,
    # not 180, so the label keeps about a fifth of the crop's width
    label, model = (0.5, 0.5, 0.04, 0.04), (0.5, 0.5, 0.4, 0.04)
    x1, y1, x2, y2 = crop_rect(label, model, 1000, 1000)
    assert (x1, x2) == (480 - 80 - 10, 520 + 80 + 10) and (y1, y2) == (470, 530)


def test_the_crop_stays_inside_the_frame():
    assert crop_rect((0.02, 0.02, 0.04, 0.04), None, 1000, 1000) == (0, 0, 50, 50)


def test_a_box_outside_the_frame_has_no_crop():
    assert crop_rect((1.5, 1.5, 0.1, 0.1), None, 100, 100) is None
