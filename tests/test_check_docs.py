"""The drift checker must fail on what it claims to catch — tested on broken
fixtures, not only on the real repository, or it could pass on every input."""

import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def cd():
    # By path: `tools` is a common top-level name, and conda base may have one.
    spec = importlib.util.spec_from_file_location("check_docs", ROOT / "tools" / "check_docs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(root, rel, text=""):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def fails(findings, check):
    return [f for f in findings if f.level == "FAIL" and f.check == check]


# -- links -----------------------------------------------------------------

def test_a_resolving_link_passes(cd, tmp_path):
    write(tmp_path, "a.md", "[b](b.md)")
    write(tmp_path, "b.md")
    assert cd.check_links(tmp_path) == []


def test_a_broken_link_fails(cd, tmp_path):
    write(tmp_path, "a.md", "see [b](missing.md)")
    assert len(fails(cd.check_links(tmp_path), "links")) == 1


def test_links_resolve_relative_to_the_containing_file(cd, tmp_path):
    write(tmp_path, "docs/x/a.md", "[b](../b.md)")
    write(tmp_path, "docs/b.md")
    assert cd.check_links(tmp_path) == []


def test_links_inside_code_fences_are_ignored(cd, tmp_path):
    write(tmp_path, "a.md", "```\n[b](missing.md)\n```\n")
    assert cd.check_links(tmp_path) == []


def test_nested_fences_close_correctly(cd, tmp_path):
    """A 3-backtick line inside a 4-backtick fence does not close it."""
    write(tmp_path, "a.md", "````md\n```sh\nx\n```\n[b](missing.md)\n````\n[c](gone.md)\n")
    assert [f.detail for f in fails(cd.check_links(tmp_path), "links")] == ["a.md -> gone.md"]


def test_links_inside_inline_code_are_ignored(cd, tmp_path):
    write(tmp_path, "a.md", "write it as `[text](target.md)`")
    assert cd.check_links(tmp_path) == []


def test_urls_and_anchors_are_not_files(cd, tmp_path):
    write(tmp_path, "a.md", "[u](https://x.org) [m](mailto:a@b.c) [h](#top) [s](b.md#sec)")
    write(tmp_path, "b.md")
    assert cd.check_links(tmp_path) == []


def test_legacy_and_plugin_scratch_docs_are_not_checked(cd, tmp_path):
    write(tmp_path, "legacy/yolo_labeling/SPEC.md", "[x](gone.md)")
    write(tmp_path, ".remember/now.md", "[x](gone.md)")
    write(tmp_path, ".superpowers/sdd/x/brief.md", "[x](gone.md)")
    assert cd.check_links(tmp_path) == []


# -- citations -------------------------------------------------------------

def test_a_citation_to_a_defined_symbol_passes(cd, tmp_path):
    write(tmp_path, "src/m.py", "def f():\n    pass\n\nclass C:\n    def g(self):\n        pass\n\nLIMIT = 3\n")
    write(tmp_path, "a.md", "`src/m.py::f` `src/m.py::C.g` `src/m.py::LIMIT`")
    assert cd.check_citations(tmp_path) == []


def test_a_citation_to_a_missing_symbol_fails(cd, tmp_path):
    write(tmp_path, "src/m.py", "def f():\n    pass\n")
    write(tmp_path, "a.md", "`src/m.py::gone`")
    assert len(fails(cd.check_citations(tmp_path), "citations")) == 1


def test_a_citation_to_a_missing_file_fails(cd, tmp_path):
    write(tmp_path, "a.md", "`src/nope.py::f`")
    assert len(fails(cd.check_citations(tmp_path), "citations")) == 1


def test_a_name_that_is_only_called_is_not_defined(cd, tmp_path):
    write(tmp_path, "src/m.py", "def f():\n    gone()\n")
    write(tmp_path, "a.md", "`src/m.py::gone`")
    assert len(fails(cd.check_citations(tmp_path), "citations")) == 1


def test_citations_resolve_from_the_repo_root(cd, tmp_path):
    write(tmp_path, "src/m.py", "def f():\n    pass\n")
    write(tmp_path, "docs/deep/a.md", "`src/m.py::f`")
    assert cd.check_citations(tmp_path) == []


# -- skills ----------------------------------------------------------------

def test_a_well_formed_skill_passes(cd, tmp_path):
    write(tmp_path, ".claude/skills/demo/SKILL.md", "---\nname: demo\ndescription: Use when demoing.\n---\nbody\n")
    assert cd.check_skills(tmp_path) == []


@pytest.mark.parametrize("text", [
    "no frontmatter\n",
    "---\nname: other\ndescription: x\n---\n",
    "---\nname: demo\ndescription: ''\n---\n",
    "---\nname: [unclosed\n---\n",
])
def test_a_malformed_skill_fails(cd, tmp_path, text):
    write(tmp_path, ".claude/skills/demo/SKILL.md", text)
    assert fails(cd.check_skills(tmp_path), "skills")


def test_a_skill_folder_without_skill_md_fails(cd, tmp_path):
    (tmp_path / ".claude/skills/demo").mkdir(parents=True)
    assert fails(cd.check_skills(tmp_path), "skills")


# -- index -----------------------------------------------------------------

def test_the_index_matches(cd, tmp_path):
    write(tmp_path, "docs/knowledge/a.md")
    write(tmp_path, "docs/knowledge/b.md")
    write(tmp_path, "CLAUDE.md", "| [a](docs/knowledge/a.md) | [b](./docs/knowledge/b.md#x) |")
    assert cd.check_index(tmp_path) == []


def test_an_unindexed_knowledge_file_fails(cd, tmp_path):
    write(tmp_path, "docs/knowledge/a.md")
    write(tmp_path, "docs/knowledge/b.md")
    write(tmp_path, "CLAUDE.md", "[a](docs/knowledge/a.md)")
    assert len(fails(cd.check_index(tmp_path), "index")) == 1


def test_an_index_entry_with_no_file_fails(cd, tmp_path):
    write(tmp_path, "CLAUDE.md", "[a](docs/knowledge/a.md)")
    assert len(fails(cd.check_index(tmp_path), "index")) == 1


# -- legacy ----------------------------------------------------------------

def make_snapshot(root):
    write(root, "legacy/yolo_labeling/app.py", "x = 1\n")
    write(root, "legacy/yolo_labeling/core/io.py", "y = 2\n")
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root / 'legacy').as_posix()}"
             for p in sorted((root / "legacy").rglob("*.py"))]
    write(root, "legacy/MANIFEST.sha256", "\n".join(lines) + "\n")


def test_an_untouched_snapshot_passes(cd, tmp_path):
    make_snapshot(tmp_path)
    assert cd.check_legacy(tmp_path) == []


@pytest.mark.parametrize("damage", ["modify", "delete", "add"])
def test_any_change_to_the_snapshot_fails(cd, tmp_path, damage):
    make_snapshot(tmp_path)
    snap = tmp_path / "legacy/yolo_labeling"
    if damage == "modify":
        (snap / "app.py").write_text("x = 2\n")
    elif damage == "delete":
        (snap / "core/io.py").unlink()
    else:
        write(tmp_path, "legacy/yolo_labeling/new.py")
    assert len(fails(cd.check_legacy(tmp_path), "legacy")) == 1


def test_pycache_in_the_snapshot_is_not_a_change(cd, tmp_path):
    make_snapshot(tmp_path)
    write(tmp_path, "legacy/yolo_labeling/__pycache__/app.cpython-310.pyc")
    assert cd.check_legacy(tmp_path) == []


def test_a_missing_manifest_fails(cd, tmp_path):
    assert fails(cd.check_legacy(tmp_path), "legacy")


# -- legacy imports --------------------------------------------------------

@pytest.mark.parametrize("line", [
    "from legacy.yolo_labeling import app",
    "import yolo_labeling",
    "    from yolo_labeling.core import labelio",
])
def test_importing_legacy_code_fails(cd, tmp_path, line):
    write(tmp_path, "src/deeplabeling/x.py", line + "\n")
    assert fails(cd.check_legacy_imports(tmp_path), "legacy-imports")


def test_mentioning_legacy_in_a_string_is_fine(cd, tmp_path):
    write(tmp_path, "src/deeplabeling/x.py", 'NOTE = "ported from legacy yolo_labeling"\n')
    assert cd.check_legacy_imports(tmp_path) == []


# -- external paths --------------------------------------------------------

def test_a_missing_external_path_only_warns(cd, tmp_path):
    write(tmp_path, "a.md", "`/definitely/not/here/x` exists? `/tmp` does.")
    assert [f.level for f in cd.check_external(tmp_path)] == ["WARN"]


# -- command line ----------------------------------------------------------

def test_the_exit_code_follows_failures(cd, tmp_path, capsys):
    write(tmp_path, "a.md", "[x](missing.md)")
    assert cd.main(["--root", str(tmp_path), "-q"]) == 1
    assert "FAIL links: a.md -> missing.md" in capsys.readouterr().out


def test_quiet_mode_hides_warnings(cd, tmp_path, capsys):
    make_snapshot(tmp_path)
    write(tmp_path, "CLAUDE.md", "`/definitely/not/here/x`")
    assert cd.main(["--root", str(tmp_path), "-q"]) == 0
    assert capsys.readouterr().out == ""


def test_the_repository_passes(cd):
    """The real repository has no drift. Every other test here proves the
    checker CAN fail; this one proves the project currently does not."""
    assert [str(f) for f in cd.run(ROOT) if f.level == "FAIL"] == []
