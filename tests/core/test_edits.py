import math
from pathlib import Path

import pytest

from deeplabeling.core.edits import (
    AddBox,
    CreateEmpty,
    DeleteLine,
    Edit,
    FileChange,
    LineRef,
    Refused,
    SetBox,
    SetClass,
    materialize,
)
from deeplabeling.core.labelio import parse_label_bytes
from fixtures import CRLF, GAUNTLET, POLY1

TWO = b"0 0.5 0.5 0.2 0.2\n1 0.3 0.3 0.1 0.1\n"
NEW = (0.1, 0.1, 0.1, 0.1)
NEW_LINE = b"3 0.100000 0.100000 0.100000 0.100000"


def ref(data: bytes, index: int) -> LineRef:
    return LineRef.of(parse_label_bytes(data), index)


def run(before, *ops):
    return materialize(before, ops, class_ok=lambda c: c < 4)


def test_adding_to_a_missing_file_creates_one_line():
    assert run(None, AddBox(3, NEW)) == NEW_LINE + b"\n"


def test_adding_to_an_empty_file():
    assert run(b"", AddBox(3, NEW)) == NEW_LINE + b"\n"


def test_adding_appends_and_keeps_every_other_byte():
    assert run(TWO, AddBox(3, NEW)) == TWO + NEW_LINE + b"\n"


def test_adding_gives_an_unterminated_last_line_its_newline_first():
    assert run(b"0 0.5 0.5 0.2 0.2", AddBox(3, NEW)) == b"0 0.5 0.5 0.2 0.2\n" + NEW_LINE + b"\n"


def test_adding_to_a_crlf_file_uses_crlf():
    assert run(CRLF.encode(), AddBox(3, NEW)) == CRLF.encode() + NEW_LINE + b"\r\n"


def test_a_class_change_splices_and_keeps_crlf():
    data = CRLF.encode()
    assert run(data, SetClass(ref(data, 1), 3)) == data.replace(b"\n1 0.3", b"\n3 0.3")


def test_a_class_change_keeps_a_polygons_points():
    data = POLY1.encode()
    assert run(data, SetClass(ref(data, 0), 2)) == b"2" + data[1:]


def test_a_new_box_rewrites_only_that_line():
    assert run(TWO, SetBox(ref(TWO, 1), (0.4, 0.4, 0.2, 0.2))) == (
        b"0 0.5 0.5 0.2 0.2\n1 0.400000 0.400000 0.200000 0.200000\n")


def test_setting_the_same_box_or_class_changes_nothing():
    assert run(TWO, SetBox(ref(TWO, 0), (0.5, 0.5, 0.2, 0.2))) == TWO
    assert run(TWO, SetClass(ref(TWO, 0), 0)) == TWO


def test_moving_a_polygon_is_refused():
    data = POLY1.encode()
    with pytest.raises(Refused, match="polygon"):
        run(data, SetBox(ref(data, 0), (0.5, 0.5, 0.1, 0.1)))


def test_deleting_a_middle_line_keeps_the_others():
    three = TWO + b"2 0.7 0.7 0.1 0.1\n"
    assert run(three, DeleteLine(ref(three, 1))) == b"0 0.5 0.5 0.2 0.2\n2 0.7 0.7 0.1 0.1\n"


def test_deleting_the_only_box_leaves_zero_bytes():
    data = b"0 0.5 0.5 0.2 0.2\n"
    assert run(data, DeleteLine(ref(data, 0))) == b""


def test_deleting_every_box_keeps_unparsable_lines():
    data = b"0 0.5 0.5 0.2 0.2\n# note\n"
    assert run(data, DeleteLine(ref(data, 0))) == b"# note\n"


def test_a_stale_index_still_finds_the_line():
    assert run(TWO, DeleteLine(LineRef(0, 1, (0.3, 0.3, 0.1, 0.1)))) == b"0 0.5 0.5 0.2 0.2\n"


def test_a_box_that_is_gone_is_refused():
    with pytest.raises(Refused):
        run(TWO, DeleteLine(LineRef(1, 1, (0.9, 0.9, 0.1, 0.1))))


def test_identical_lines_need_a_correct_index():
    data = GAUNTLET.encode()
    with pytest.raises(Refused):
        run(data, DeleteLine(LineRef(0, 0, (0.5, 0.5, 0.2, 0.2))))
    kept = GAUNTLET.splitlines(keepends=True)
    del kept[6]
    assert run(data, DeleteLine(LineRef(6, 0, (0.5, 0.5, 0.2, 0.2)))) == "".join(kept).encode()


def test_two_changes_to_one_box_are_refused():
    r = ref(TWO, 0)
    with pytest.raises(Refused, match="same box"):
        run(TWO, SetClass(r, 2), DeleteLine(r))


def test_one_intent_can_delete_reclassify_and_add():
    out = run(TWO, DeleteLine(ref(TWO, 0)), SetClass(ref(TWO, 1), 2), AddBox(3, NEW))
    assert out == b"2 0.3 0.3 0.1 0.1\n" + NEW_LINE + b"\n"


def test_marking_negative_creates_an_empty_file():
    assert run(None, CreateEmpty()) == b""


def test_marking_negative_needs_a_missing_file_and_nothing_else():
    with pytest.raises(Refused):
        run(b"", CreateEmpty())
    with pytest.raises(Refused):
        run(None, CreateEmpty(), AddBox(3, NEW))


@pytest.mark.parametrize("op", [AddBox(4, NEW), AddBox(-1, NEW), AddBox(True, NEW)])
def test_a_class_the_dataset_does_not_have_is_refused(op):
    with pytest.raises(Refused, match="class"):
        run(TWO, op)


def test_reclassifying_to_an_unknown_class_is_refused():
    with pytest.raises(Refused, match="class"):
        run(TWO, SetClass(ref(TWO, 0), 9))


@pytest.mark.parametrize("bbox", [
    (0.5, 0.5, 0.0, 0.1), (0.95, 0.5, 0.2, 0.2), (math.nan, 0.5, 0.1, 0.1), (0.5, 0.5, -0.1, 0.1),
])
def test_an_empty_or_outside_box_is_refused(bbox):
    with pytest.raises(Refused, match="box"):
        run(TWO, AddBox(0, bbox))


def test_bytes_that_are_not_utf8_survive_an_edit_elsewhere():
    data = b"0 0.5 0.5 0.2 0.2\n\xff\xfe junk\n"
    assert run(data, DeleteLine(ref(data, 0))) == b"\xff\xfe junk\n"


def test_a_class_change_in_the_gauntlet_touches_one_line():
    data = GAUNTLET.encode()
    assert run(data, SetClass(ref(data, 0), 2)) == b"2" + data[1:]


def test_nothing_to_do_is_refused():
    with pytest.raises(Refused):
        run(TWO)


def test_an_edit_counts_its_bytes():
    edit = Edit((FileChange(Path("a.txt"), None, b"abc"), FileChange(Path("b.txt"), b"xy", b"")), (), "x")
    assert edit.nbytes == 5
