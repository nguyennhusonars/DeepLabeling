import pytest

from deeplabeling.core import settings, state
from deeplabeling.core.settings import JsonFile, Settings, define, is_str_list, is_str_map


@pytest.fixture(autouse=True)
def registry(monkeypatch):
    """Each test defines its settings in an empty registry."""
    monkeypatch.setattr(settings, "REGISTRY", {})


def test_a_setting_is_defined_once():
    define("a.b", "global", 1, lambda v: isinstance(v, int))
    with pytest.raises(ValueError, match="twice"):
        define("a.b", "global", 1, lambda v: isinstance(v, int))


def test_a_definition_needs_a_valid_default_and_a_known_scope():
    with pytest.raises(ValueError):
        define("x", "global", "one", lambda v: isinstance(v, int))
    with pytest.raises(ValueError):
        define("y", "machine", 1, lambda v: True)


def test_get_gives_the_default_until_set(tmp_path):
    s = define("n", "global", 3, lambda v: isinstance(v, int))
    values = Settings(JsonFile(tmp_path / "s.json"), "global")
    assert values.get(s) == 3
    values.set(s, 5)
    assert values.get(s) == 5


def test_an_invalid_value_is_refused(tmp_path):
    s = define("n", "global", 3, lambda v: isinstance(v, int))
    with pytest.raises(ValueError):
        Settings(JsonFile(tmp_path / "s.json"), "global").set(s, "five")


def test_an_invalid_stored_value_reads_as_the_default(tmp_path):
    s = define("n", "global", 3, lambda v: isinstance(v, int))
    (tmp_path / "s.json").write_text('{"n": "hand-edited"}')
    assert Settings(JsonFile(tmp_path / "s.json"), "global").get(s) == 3


def test_a_setting_belongs_to_its_scope(tmp_path):
    s = define("n", "root", 3, lambda v: isinstance(v, int))
    with pytest.raises(ValueError, match="root"):
        Settings(JsonFile(tmp_path / "s.json"), "global").get(s)


def test_values_survive_a_save_and_reload(tmp_path):
    s = define("names", "root", [], is_str_list)
    file = JsonFile(tmp_path / "d.json")
    Settings(file, "root", ("root",)).set(s, ["car", "bus"])
    assert file.save()
    assert Settings(JsonFile(tmp_path / "d.json"), "root", ("root",)).get(s) == ["car", "bus"]


def test_sections_are_independent(tmp_path):
    s = define("cursor", "opening", None, lambda v: v is None or isinstance(v, str))
    file = JsonFile(tmp_path / "d.json")
    Settings(file, "opening", ("openings", "a.yaml")).set(s, "img1")
    assert Settings(file, "opening", ("openings", "b.yaml")).get(s) is None


def test_get_returns_a_copy(tmp_path):
    s = define("colors", "root", {}, is_str_map)
    values = Settings(JsonFile(tmp_path / "d.json"), "root")
    values.set(s, {"car": "#00ff00"})
    values.get(s)["car"] = "#ff0000"
    assert values.get(s) == {"car": "#00ff00"}


def test_setting_the_same_value_does_not_dirty_the_file(tmp_path):
    s = define("n", "global", 3, lambda v: isinstance(v, int))
    file = JsonFile(tmp_path / "s.json")
    Settings(file, "global").set(s, 3)
    assert file.dirty
    file.save()
    Settings(file, "global").set(s, 3)
    assert not file.dirty and not file.save()


@pytest.mark.parametrize("content", [b"{broken", b"[1, 2]", b"\xff\xfe"])
def test_an_unreadable_file_is_set_aside_and_defaults_apply(tmp_path, content):
    s = define("n", "global", 3, lambda v: isinstance(v, int))
    (tmp_path / "s.json").write_bytes(content)
    file = JsonFile(tmp_path / "s.json")
    assert file.warning and file.writable
    assert Settings(file, "global").get(s) == 3
    Settings(file, "global").set(s, 4)
    assert file.save()
    kept = [p for p in tmp_path.iterdir() if ".unreadable-" in p.name]
    assert len(kept) == 1 and kept[0].read_bytes() == content


def test_a_file_that_cannot_be_set_aside_is_never_overwritten(tmp_path, monkeypatch):
    s = define("n", "global", 3, lambda v: isinstance(v, int))
    (tmp_path / "s.json").write_bytes(b"{broken")

    def cannot(src, dst):
        raise OSError(13, "Permission denied")

    with monkeypatch.context() as m:
        m.setattr(state.os, "replace", cannot)
        file = JsonFile(tmp_path / "s.json")
    Settings(file, "global").set(s, 4)
    assert not file.writable and not file.save()
    assert (tmp_path / "s.json").read_bytes() == b"{broken"
