"""Blurry's settings, groups and ranking (docs/design/2026-10-27-blurry.md#the-measure)."""

import pytest

from deeplabeling.core.blurry import MIN_PEERS, BlurSettings, candidate, octave, octave_name, rank


def cands(name, n, side, cls=0, start=0, lap=lambda i: float(i), cr=lambda i: 1 - i / 100):
    """n boxes whose sharpness rises with i: box 0 is the blurriest on both measures."""
    return [candidate(f"{name}{i}", start + i, 0, cls, side, lap(i), cr(i)) for i in range(n)]


def test_settings_refuse_by_name():
    with pytest.raises(ValueError, match="share: must be above 0% and at most 100%"):
        BlurSettings(share=0)
    with pytest.raises(ValueError, match="share: must be above 0% and at most 100%"):
        BlurSettings(share=1.01)
    with pytest.raises(ValueError, match="minimum side: must be from 8 to 4096 px"):
        BlurSettings(min_side=7)
    with pytest.raises(ValueError, match="minimum side: must be from 8 to 4096 px"):
        BlurSettings(min_side=16.5)
    assert BlurSettings.from_json(BlurSettings(0.1, 24).to_json()) == BlurSettings(0.1, 24)
    assert BlurSettings().to_json() == {"share": 0.05, "min_side": 16}
    with pytest.raises(ValueError, match="not Blurry settings"):
        BlurSettings.from_json({"share": "lots"})


def test_octaves():
    assert [octave(s) for s in (8, 15, 16, 31, 32, 127, 128, 900)] == [0, 0, 1, 1, 2, 3, 4, 4]
    assert octave_name(0) == "8–15 px" and octave_name(1) == "16–31 px" and octave_name(4) == "128+ px"


def test_the_blurriest_share_of_each_group_is_listed_rounded_up():
    listed, small = rank(cands("head", 40, 20) + cands("car", 25, 40, cls=1, start=100), 0.05)
    assert sorted(listed) == ["car0", "car1", "head0", "head1"]          # ceil(2.0), ceil(1.25)
    assert listed["head0"][1] == 0 and listed["head1"][1] == 1 / 40
    assert listed["car1"][1] == 1 / 25 and small == set()
    assert listed["head0"][0] < listed["head1"][0] < 0                  # z: blurrier is lower


def test_class_and_size_make_the_groups():
    """The same class in two octaves, and two classes in one octave: four groups of 20."""
    boxes = (cands("a", 20, 20) + cands("b", 20, 40, start=20) +
             cands("c", 20, 20, cls=1, start=40) + cands("d", 20, 40, cls=1, start=60))
    listed, _ = rank(boxes, 0.05)
    assert sorted(listed) == ["a0", "b0", "c0", "d0"]


def test_a_small_group_is_not_ranked_and_said():
    listed, small = rank(cands("head", MIN_PEERS - 1, 20) + cands("car", MIN_PEERS, 20, cls=1), 0.5)
    assert not any(k.startswith("head") for k in listed)
    assert small == {f"head{i}" for i in range(MIN_PEERS - 1)}
    assert len([k for k in listed if k.startswith("car")]) == MIN_PEERS // 2


def test_a_group_of_equal_values_lists_its_share_with_z_zero():
    listed, _ = rank(cands("same", 30, 20, lap=lambda i: 1.0, cr=lambda i: 0.5), 0.1)
    assert sorted(listed) == ["same0", "same1", "same2"]                # ties by dataset order
    assert all(z == 0 for z, _ in listed.values())


def test_the_score_averages_both_z():
    """Box x is the blurriest by one measure only; box y is second blurriest by both."""
    boxes = cands("p", 40, 20, lap=lambda i: float(i + 2), cr=lambda i: 1 - (i + 2) / 100)
    boxes.append(candidate("x", 99, 0, 0, 20, 0.0, 1 - 30 / 100))       # Laplacian lowest, CR middling
    boxes.append(candidate("y", 98, 0, 0, 20, 1.0, 1 - 1 / 100))        # second on both
    listed, _ = rank(boxes, 1 / 42)                                      # one listed
    assert list(listed) == ["y"]


def test_the_share_is_not_pushed_up_by_float_error():
    listed, _ = rank(cands("h", 100, 20), 0.07)                         # 0.07 * 100 is 7.000000000000001
    assert len(listed) == 7


def test_a_candidate_is_not_tracked_by_the_garbage_collector():
    """Hundreds of thousands are kept until the ranking: tracked, they made every full
    collection walk them, and the window waited 200-280 ms each time (2026-10-27)."""
    import gc

    c = candidate("k", 0, 0, 0, 20, 1.0, 0.5)
    gc.collect()
    assert not gc.is_tracked(c)
