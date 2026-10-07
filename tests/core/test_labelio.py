import pytest

from deeplabeling.core.labelio import (
    LabelLine,
    decode_label_bytes,
    encode_label_text,
    format_box,
    locate_line,
    parse_label_bytes,
    render_label_bytes,
)
from fixtures import CRLF, GAUNTLET, MIXED, POLY1

ROUND_TRIPS = [
    b"",
    b"0 0.5 0.5 0.2 0.2\n",
    CRLF.encode(),
    b"0 0.5 0.5 0.2 0.2",
    b"\n\n   \n",
    b"0 0.5 0.5 0.2 0.2\n\xff\xfe not utf-8\n",
    b"inf 0.5 0.5 0.2 0.2\nnan 1 1 1 1\n",
    GAUNTLET.encode(),
    POLY1.encode(),
    MIXED.encode(),
]


@pytest.mark.parametrize("data", ROUND_TRIPS)
def test_parse_then_render_returns_the_same_bytes(data):
    assert render_label_bytes(parse_label_bytes(data)) == data


@pytest.mark.parametrize("data", [bytes(range(256)), b"\xc3\x28\x80"])
def test_decoding_is_lossless_for_any_bytes(data):
    assert encode_label_text(decode_label_bytes(data)) == data


def test_the_gauntlet_parses_without_raising():
    lines = parse_label_bytes(GAUNTLET.encode())
    assert [ln.parsed for ln in lines] == [True, True, True, True, False, True, True,
                                           False, False, False, True]
    assert [ln.cls_id for ln in lines if ln.parsed] == [1, 99, -1, 0, 0, 0, 0]


def test_a_class_that_is_infinite_or_nan_is_unparsed():
    assert [ln.parsed for ln in parse_label_bytes(b"inf 0.5 0.5 0.2 0.2\nnan 1 1 1 1\n")] == [False, False]


def test_a_polygon_is_shown_by_its_extent():
    poly = parse_label_bytes(POLY1.encode())[0]
    assert poly.is_polygon
    assert poly.bbox == pytest.approx((0.15, 0.15, 0.1, 0.1))


def test_an_extra_column_is_still_a_box():
    line = parse_label_bytes(b"0 0.5 0.5 0.2 0.2 0.95\n")[0]
    assert line.parsed and not line.is_polygon
    assert line.bbox == (0.5, 0.5, 0.2, 0.2)


@pytest.mark.parametrize("raw, ending", [
    ("0 1 1 1 1\n", "\n"), ("0 1 1 1 1\r\n", "\r\n"), ("0 1 1 1 1", ""), ("\n", "\n"),
])
def test_terminator(raw, ending):
    assert LabelLine(None, (), raw).terminator == ending


def test_with_class_splices_the_id_and_keeps_every_digit():
    line = parse_label_bytes(b"  0 0.30 0.5 0.2 0.2 0.95\r\n")[0]
    assert line.with_class(12).raw == "  12 0.30 0.5 0.2 0.2 0.95\r\n"


def test_with_class_keeps_polygon_points():
    poly = parse_label_bytes(POLY1.encode())[0]
    assert poly.with_class(3).raw == "3" + POLY1.splitlines(keepends=True)[0][1:]


def test_with_class_keeps_a_last_line_without_its_newline_so():
    line = parse_label_bytes(b"0 0.5 0.5 0.2 0.2")[0]
    assert line.with_class(1).raw == "1 0.5 0.5 0.2 0.2"       # an append gives it the file's ending


def test_with_bbox_writes_a_plain_box_and_keeps_crlf():
    line = parse_label_bytes(b"0 0.5 0.5 0.2 0.2 0.95\r\n")[0]
    moved = line.with_bbox((0.25, 0.75, 0.1, 0.2))
    assert moved.raw == "0 0.250000 0.750000 0.100000 0.200000\r\n"
    assert moved.bbox == (0.25, 0.75, 0.1, 0.2)


def test_format_box_never_writes_negative_zero():
    assert format_box(0, (-0.0, 0.5, 0.1, 0.1)).raw == "0 0.000000 0.500000 0.100000 0.100000\n"


THREE = parse_label_bytes(b"0 0.5 0.5 0.2 0.2\n1 0.3 0.3 0.1 0.1\n1 0.7 0.7 0.1 0.1\n")


def test_locate_trusts_a_correct_hint():
    assert locate_line(THREE, 1, (0.7, 0.7, 0.1, 0.1), hint=2) == 2


def test_locate_searches_when_the_hint_is_stale():
    assert locate_line(THREE, 1, (0.7, 0.7, 0.1, 0.1), hint=0) == 2
    assert locate_line(THREE, 1, (0.7, 0.7, 0.1, 0.1), hint=9) == 2


def test_locate_needs_the_class_to_agree():
    assert locate_line(THREE, 0, (0.3, 0.3, 0.1, 0.1)) is None


def test_locate_tolerates_a_small_drift_only():
    assert locate_line(THREE, 0, (0.5015, 0.5, 0.2, 0.2)) == 0
    assert locate_line(THREE, 0, (0.503, 0.5, 0.2, 0.2)) is None


def test_locate_refuses_identical_lines_without_a_correct_hint():
    lines = parse_label_bytes(GAUNTLET.encode())
    assert locate_line(lines, 0, (0.5, 0.5, 0.2, 0.2)) is None
    assert locate_line(lines, 0, (0.5, 0.5, 0.2, 0.2), hint=6) == 6


def test_locate_finds_a_polygon_by_its_extent():
    lines = parse_label_bytes(POLY1.encode())
    assert locate_line(lines, 1, lines[1].bbox) == 1
