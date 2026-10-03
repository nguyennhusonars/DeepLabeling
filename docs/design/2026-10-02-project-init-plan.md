# DeepLabeling project init — Implementation Plan


**Status:** executed 2026-10-02. This plan is history; the knowledge docs and CLAUDE.md are the live facts.
> **Executed 2026-10-02 — do not re-run.** Kept as the record of how the scaffold was built; the live facts are in CLAUDE.md and docs/knowledge/.

**Goal:** Create the DeepLabeling repository — knowledge, four project skills, a docs drift checker with its hook, a frozen legacy reference and an empty launchable Qt window — as one initial commit.

**Architecture:** Plain files plus one Python checker (`tools/check_docs.py`) that turns the three documentation rules into machine checks, and a non-blocking PostToolUse hook that runs it after every edit. The app package is an empty PySide6 shell in `src/` layout; nothing is installed into the shared conda env except `pytest-qt`.

**Tech Stack:** Python 3.10 (conda base), PySide6 6.6, pytest + pytest-qt, PyYAML, Pillow, sh + jq for the hook.

**Spec:** [2026-10-02-project-init.md](2026-10-02-project-init.md) — read it with this plan; the landmines, the knowledge-file ownership table and the check list are defined there and implemented here.

## Global Constraints

- Python `>= 3.10`; run everything with conda base's `python3` (3.10.12) and its PySide6 6.6.0.
- Install exactly one package into base: `pytest-qt`. No new conda env. No `pip install -e .` of this project.
- Run without installing: `run.sh` sets `PYTHONPATH=src`; pytest uses `pythonpath = ["src"]`.
- **Exactly one git commit**, at the end (Task 7), approved by the user. No intermediate commits.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; identity Son Nguyen <sonnn@mkvision.com>.
- Never copy datasets or prediction caches: about 7.8 GB of disk is free.
- `legacy/` is read-only and never imported; snapshot source `/home/sonnn/Documents/PGit/yolo_labeling`, excluding `class_config.json`, `.yolo_labeling_cache/`, `__pycache__/`, `.pytest_cache/`, `*.egg-info/`.
- Docs rules: one fact, one home; prefer a command over a restatement (no hard-coded counts); cite code as `<path>.py::<symbol>` relative to the repo root, never by line number.
- The hook never blocks an edit.
- Qt tests run with `QT_QPA_PLATFORM=offscreen`.

## Review Focus

1. **Code fences and inline code in docs** — links and citations inside fenced blocks (including a 4-backtick fence wrapping a 3-backtick one) or inside inline code must be ignored, or the spec and this plan would fail their own check. *(Task 2 tests `test_links_inside_code_fences_are_ignored`, `test_nested_fences_close_correctly`, `test_links_inside_inline_code_are_ignored`.)*
2. **Link targets that are not files** — `https://…`, `mailto:`, `#anchor` and `file.md#section` must not be reported missing. *(Task 2 `test_urls_and_anchors_are_not_files`.)*
3. **The hook firing on files it should ignore** — a file outside this repository, or a non-doc type, must produce no output. *(Task 6 `test_a_file_outside_the_repo_is_ignored`, `test_an_irrelevant_file_type_is_ignored`.)*
4. **The hook failing quietly** — a malformed payload must exit 0 silently, but a checker that crashes must be reported, never mistaken for a pass. *(Task 6 `test_a_malformed_payload_is_ignored`, `test_a_crashing_checker_is_reported`.)*
5. **Legacy snapshot drift that is not a modification** — an added or deleted file must fail; a `__pycache__/` appearing must not. *(Task 2 `test_any_change_to_the_snapshot_fails`, `test_pycache_in_the_snapshot_is_not_a_change`.)*

## File map

| File | Responsibility | Task |
|---|---|---|
| `pyproject.toml`, `.gitignore`, `run.sh` | project metadata, ignore rules, launcher | 1 |
| `src/deeplabeling/__init__.py`, `__main__.py` | the empty window | 1 |
| `tests/conftest.py`, `tests/test_smoke.py` | offscreen Qt; visible-window smoke tests | 1 |
| `tools/check_docs.py`, `tests/test_check_docs.py` | the drift checker and its tests | 2 |
| `legacy/README.md`, `legacy/MANIFEST.sha256`, `legacy/yolo_labeling/` | frozen reference | 3 |
| `CLAUDE.md`, `docs/knowledge/*.md` | the knowledge base | 4 |
| `.claude/skills/*/SKILL.md`, `.claude/skills/dataset-analysis/scripts/*.py`, `tests/test_dataset_scripts.py` | skills and analysis scripts | 5 |
| `.claude/hooks/check-docs-drift.sh`, `.claude/settings.json`, `tests/test_hook.py` | the hook | 6 |
| spec/plan status lines, `tests/test_check_docs.py` (repo test) | final verification and the commit | 7 |

---

### Task 1: Repository skeleton and the empty window

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `run.sh`, `src/deeplabeling/__init__.py`, `src/deeplabeling/__main__.py`, `tests/conftest.py`, `tests/test_smoke.py`

**Interfaces:**
- Produces: `src/deeplabeling/__main__.py::build_window` → `QMainWindow` titled "DeepLabeling"; `src/deeplabeling/__main__.py::main` → `int` exit code.

- [ ] **Step 1: Initialise git and install pytest-qt**

```bash
cd /home/sonnn/Documents/PGit/DeepLabeling
git init -b main
python3 -m pip install pytest-qt
python3 -c "import importlib.metadata as m; print('pytest-qt', m.version('pytest-qt'), '| PySide6', m.version('PySide6'))"
```

Expected: `Initialized empty Git repository`, pip success, PySide6 `6.6.0`.

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.build_meta"

[project]
name = "deeplabeling"
version = "0.1.0"
description = "Labeling and dataset-cleaning tool for YOLO datasets"
requires-python = ">=3.10"
dependencies = ["PySide6", "numpy", "opencv-python", "Pillow", "PyYAML"]

[project.optional-dependencies]
# Install the ultralytics checkout your models were trained with: a model using
# a fork's custom modules does not load under stock ultralytics.
model = ["ultralytics"]
test = ["pytest", "pytest-qt"]

[project.scripts]
deeplabeling = "deeplabeling.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
norecursedirs = ["legacy", ".remember", ".git", ".deeplabeling"]
qt_api = "pyside6"
addopts = "-q"
```

- [ ] **Step 3: Write `.gitignore` and `run.sh`**

`.gitignore`:
```
# App state (config, caches) — see docs/design/2026-10-02-project-init.md
.deeplabeling/
__pycache__/
.pytest_cache/
*.egg-info/
```

`run.sh`:
```sh
#!/bin/sh
# Launch DeepLabeling from this checkout without installing it.
ROOT=$(cd "$(dirname "$0")" && pwd)
PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m deeplabeling "$@"
```

```bash
chmod +x run.sh
```

- [ ] **Step 4: Write the failing smoke tests**

`tests/conftest.py`:
```python
"""Qt runs offscreen unless the caller chose a platform explicitly.

Set before any QApplication exists: pytest-qt creates it lazily, after this
module is imported. Use `QT_QPA_PLATFORM=xcb xvfb-run -a pytest` when a test
needs a real X server.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
```

`tests/test_smoke.py`:
```python
"""The window must be VISIBLE and render pixels, not merely exist.

The legacy app twice shipped a feature whose tests passed on widget state while
the user could not see it. Assert what is on screen.
"""

from deeplabeling.__main__ import build_window


def test_the_main_window_is_visible_and_titled(qtbot):
    window = build_window()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)
    assert window.windowTitle() == "DeepLabeling"
    assert window.width() > 0 and window.height() > 0


def test_the_window_renders_pixels(qtbot):
    window = build_window()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)
    image = window.grab().toImage()
    assert not image.isNull()
    assert (image.width(), image.height()) == (window.width(), window.height())
```

- [ ] **Step 5: Run them to verify they fail**

Run: `python3 -m pytest tests/test_smoke.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'deeplabeling'`.

- [ ] **Step 6: Write the package**

`src/deeplabeling/__init__.py`:
```python
"""DeepLabeling: labeling and dataset cleaning for YOLO datasets."""
```

`src/deeplabeling/__main__.py`:
```python
"""Entry point: `python -m deeplabeling` opens the main window."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMainWindow


def build_window() -> QMainWindow:
    """The main window. Empty until the app design says what goes in it."""
    window = QMainWindow()
    window.setWindowTitle("DeepLabeling")
    window.resize(1280, 800)
    return window


def main(argv: list[str] | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv)
    window = build_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_smoke.py`
Expected: `2 passed`.

---

### Task 2: The drift checker

**Files:**
- Create: `tools/check_docs.py`, `tests/test_check_docs.py`

**Interfaces:**
- Produces: `tools/check_docs.py::Finding` (`level` `"FAIL"|"WARN"`, `check`, `detail`; `str()` → `"FAIL links: a.md -> b.md"`); one function per check, each `(root: Path) -> list[Finding]`: `check_links`, `check_citations`, `check_skills`, `check_index`, `check_legacy`, `check_legacy_imports`, `check_external`; `tools/check_docs.py::run` `(root) -> list[Finding]`; `tools/check_docs.py::main` `(argv=None) -> int` with `-q/--quiet` and `--root`. Exit 1 on any FAIL.
- Used by: Task 6's hook runs `python3 tools/check_docs.py -q --root <repo>` and looks for lines starting `FAIL`.

- [ ] **Step 1: Write the failing tests**

`tests/test_check_docs.py`:
```python
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


def test_legacy_and_remember_docs_are_not_checked(cd, tmp_path):
    write(tmp_path, "legacy/yolo_labeling/SPEC.md", "[x](gone.md)")
    write(tmp_path, ".remember/now.md", "[x](gone.md)")
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_check_docs.py`
Expected: every test ERRORs — `FileNotFoundError` for `tools/check_docs.py`.

- [ ] **Step 3: Write the checker**

`tools/check_docs.py`:
```python
#!/usr/bin/env python3
"""Verify that DeepLabeling's docs still match the code.

Checks — the "Sync 1" table in docs/design/2026-10-02-project-init.md:
  links           relative Markdown links resolve, relative to the containing file
  citations       `path.py::symbol` (from the repo root) names a file defining symbol
  skills          .claude/skills/<dir>/SKILL.md frontmatter: name == dir, description set
  index           CLAUDE.md links exactly the files in docs/knowledge/
  legacy          legacy/MANIFEST.sha256 matches legacy/yolo_labeling exactly
  legacy-imports  nothing in src/ or tests/ imports legacy code
  external        backticked absolute paths exist (WARN only: not ours to keep)

Fenced code blocks hold examples, not claims, so they are skipped. Exit 1 on FAIL.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

#: Never scanned for docs: history, plugin state, caches, app state.
SKIP_DIRS = {".git", ".remember", "legacy", "__pycache__", ".pytest_cache", ".deeplabeling"}

FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
INLINE_CODE = re.compile(r"`[^`\n]*`")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
CITATION = re.compile(r"`([\w./-]+\.py)::([A-Za-z_][\w.]*)`")
EXTERNAL = re.compile(r"`((?:/|~/)[^`\s<>*…]+)`")
LEGACY_IMPORT = re.compile(r"^\s*(?:from|import)\s+(?:legacy|yolo_labeling)\b", re.M)


@dataclass(frozen=True)
class Finding:
    level: str      # "FAIL" | "WARN"
    check: str
    detail: str

    def __str__(self) -> str:
        return f"{self.level} {self.check}: {self.detail}"


def _docs(root: Path):
    for path in sorted(root.rglob("*.md")):
        if not SKIP_DIRS.intersection(path.relative_to(root).parts[:-1]):
            yield path


def _prose(text: str) -> str:
    """Text with fenced blocks blanked. A fence closes only on the same character
    repeated at least as many times, with nothing after it (CommonMark)."""
    out, fence = [], None
    for line in text.splitlines():
        match = FENCE.match(line)
        if fence is None:
            if match:
                fence = match.group(1)
                out.append("")
            else:
                out.append(line)
            continue
        if (match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence)
                and not line.strip()[len(match.group(1)):].strip()):
            fence = None
        out.append("")
    return "\n".join(out)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def check_links(root: Path) -> list[Finding]:
    found = []
    for doc in _docs(root):
        text = INLINE_CODE.sub("", _prose(_read(doc)))
        for target in LINK.findall(text):
            if SCHEME.match(target) or target.startswith("#"):
                continue
            if not (doc.parent / target.split("#", 1)[0]).exists():
                found.append(Finding("FAIL", "links", f"{doc.relative_to(root).as_posix()} -> {target}"))
    return found


def _defines(source: str, symbol: str) -> bool:
    """Every part of a dotted symbol is defined: `def`/`class`, or a top-level assignment."""
    for part in symbol.split("."):
        name = re.escape(part)
        if not re.search(rf"^\s*(?:async\s+def|def|class)\s+{name}\b|^{name}\s*[:=]", source, re.M):
            return False
    return True


def check_citations(root: Path) -> list[Finding]:
    found = []
    for doc in _docs(root):
        where = doc.relative_to(root).as_posix()
        for rel, symbol in CITATION.findall(_prose(_read(doc))):
            target = root / rel
            if not target.is_file():
                found.append(Finding("FAIL", "citations", f"{where}: {rel} does not exist"))
            elif not _defines(_read(target), symbol):
                found.append(Finding("FAIL", "citations", f"{where}: {rel} defines no {symbol}"))
    return found


def _frontmatter(text: str):
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        return None
    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def check_skills(root: Path) -> list[Finding]:
    base = root / ".claude" / "skills"
    if not base.is_dir():
        return []
    found = []
    for folder in sorted(p for p in base.iterdir() if p.is_dir()):
        skill = folder / "SKILL.md"
        if not skill.is_file():
            found.append(Finding("FAIL", "skills", f"{folder.name}: no SKILL.md"))
            continue
        meta = _frontmatter(_read(skill))
        if meta is None:
            found.append(Finding("FAIL", "skills", f"{folder.name}: missing or invalid frontmatter"))
            continue
        if meta.get("name") != folder.name:
            found.append(Finding("FAIL", "skills", f"{folder.name}: name is {meta.get('name')!r}"))
        if not str(meta.get("description") or "").strip():
            found.append(Finding("FAIL", "skills", f"{folder.name}: empty description"))
    return found


def check_index(root: Path) -> list[Finding]:
    claude = root / "CLAUDE.md"
    if not claude.is_file():
        return [Finding("FAIL", "index", "CLAUDE.md is missing")]
    knowledge = root / "docs" / "knowledge"
    on_disk = {p.name for p in knowledge.glob("*.md")} if knowledge.is_dir() else set()
    linked = set()
    for target in LINK.findall(INLINE_CODE.sub("", _prose(_read(claude)))):
        path = os.path.normpath(target.split("#", 1)[0]).replace(os.sep, "/")
        if path.startswith("docs/knowledge/") and path.endswith(".md"):
            linked.add(path.rsplit("/", 1)[1])
    found = [Finding("FAIL", "index", f"docs/knowledge/{n} is not listed in CLAUDE.md")
             for n in sorted(on_disk - linked)]
    found += [Finding("FAIL", "index", f"CLAUDE.md lists docs/knowledge/{n}, which does not exist")
              for n in sorted(linked - on_disk)]
    return found


def check_legacy(root: Path) -> list[Finding]:
    legacy = root / "legacy"
    manifest = legacy / "MANIFEST.sha256"
    if not manifest.is_file():
        return [Finding("FAIL", "legacy", "legacy/MANIFEST.sha256 is missing")]
    expected = {}
    for line in _read(manifest).splitlines():
        if line.strip():
            digest, rel = line.split(None, 1)
            expected[rel.strip().lstrip("*")] = digest
    snapshot = legacy / "yolo_labeling"
    actual = {}
    if snapshot.is_dir():
        for path in snapshot.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                actual[path.relative_to(legacy).as_posix()] = path
    found = [Finding("FAIL", "legacy", f"{rel} is in the manifest but missing")
             for rel in sorted(set(expected) - set(actual))]
    found += [Finding("FAIL", "legacy", f"{rel} was added to the snapshot")
              for rel in sorted(set(actual) - set(expected))]
    found += [Finding("FAIL", "legacy", f"{rel} was modified")
              for rel in sorted(set(expected) & set(actual))
              if hashlib.sha256(actual[rel].read_bytes()).hexdigest() != expected[rel]]
    return found


def check_legacy_imports(root: Path) -> list[Finding]:
    found = []
    for folder in ("src", "tests"):
        base = root / folder
        if base.is_dir():
            for py in sorted(base.rglob("*.py")):
                if LEGACY_IMPORT.search(_read(py)):
                    found.append(Finding("FAIL", "legacy-imports",
                                         f"{py.relative_to(root).as_posix()} imports legacy code"))
    return found


def check_external(root: Path) -> list[Finding]:
    found = []
    for doc in _docs(root):
        for raw in EXTERNAL.findall(_prose(_read(doc))):
            if not Path(raw).expanduser().exists():
                found.append(Finding("WARN", "external",
                                     f"{doc.relative_to(root).as_posix()}: {raw} does not exist"))
    return found


CHECKS = (check_links, check_citations, check_skills, check_index,
          check_legacy, check_legacy_imports, check_external)


def run(root) -> list[Finding]:
    root = Path(root)
    return [finding for check in CHECKS for finding in check(root)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-q", "--quiet", action="store_true", help="print failures only")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    findings = run(args.root)
    failures = [f for f in findings if f.level == "FAIL"]
    for finding in findings:
        if finding.level == "FAIL" or not args.quiet:
            print(finding)
    if not args.quiet:
        print(f"{len(failures)} failure(s), {len(findings) - len(failures)} warning(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_check_docs.py`
Expected: all pass (35 tests).

---

### Task 3: The frozen legacy reference

**Files:**
- Create: `legacy/yolo_labeling/` (copied), `legacy/MANIFEST.sha256`, `legacy/README.md`

**Interfaces:**
- Consumes: `tools/check_docs.py::check_legacy`, `tools/check_docs.py::check_legacy_imports`.
- Produces: citable legacy code for Task 4, e.g. `legacy/yolo_labeling/core/labelio.py::write_label_file`.

- [ ] **Step 1: Copy the snapshot**

```bash
cd /home/sonnn/Documents/PGit/DeepLabeling
mkdir -p legacy
rsync -a --exclude 'class_config.json' --exclude '.yolo_labeling_cache/' \
      --exclude '__pycache__/' --exclude '.pytest_cache/' --exclude '*.egg-info/' \
      /home/sonnn/Documents/PGit/yolo_labeling/ legacy/yolo_labeling/
du -sh legacy/yolo_labeling
find legacy/yolo_labeling -name 'class_config.json' -o -name '*.sqlite' | wc -l
```

Expected: about 1.3M; `0` state files.

- [ ] **Step 2: Write the manifest**

```bash
(cd legacy && find yolo_labeling -type f -not -path '*/__pycache__/*' -print0 | sort -z | xargs -0 sha256sum > MANIFEST.sha256)
wc -l legacy/MANIFEST.sha256
```

- [ ] **Step 3: Write `legacy/README.md`**

```markdown
# legacy/ — read-only reference

`yolo_labeling/` is a frozen copy of the Tkinter labeling app DeepLabeling replaces,
taken on 2026-10-02 from `/home/sonnn/Documents/PGit/yolo_labeling` without its app
state (config, prediction cache).

- **Never edit it.** `MANIFEST.sha256` holds every file's checksum and
  `python3 tools/check_docs.py` fails if anything here changes, appears or disappears.
- **Never import it.** Port what is needed into `src/deeplabeling/` instead; the
  `legacy-imports` check fails on an import from `src/` or `tests/`.
- **Read it with its defects in mind.** Many behaviours here were bugs, fixed late or not
  at all — see [legacy-defects](../docs/knowledge/legacy-defects.md) before copying one,
  and the `legacy-reference` skill for where each feature lives.
- Its own `SPEC.md` is history. Where it disagrees with `docs/knowledge/`, the knowledge
  docs win.
```

- [ ] **Step 4: Verify the checks that apply now**

```bash
python3 -c "
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location('cd', 'tools/check_docs.py'); cd = importlib.util.module_from_spec(spec); spec.loader.exec_module(cd)
root = pathlib.Path('.')
print('legacy:', cd.check_legacy(root)); print('legacy-imports:', cd.check_legacy_imports(root))"
```

Expected: `legacy: []` and `legacy-imports: []`. (The README's link to `legacy-defects.md` resolves after Task 4, and `legacy/` docs are not scanned anyway.)

---

### Task 4: CLAUDE.md and the knowledge base

**Files:**
- Create: `CLAUDE.md`, `docs/knowledge/label-files.md`, `docs/knowledge/matching.md`, `docs/knowledge/caches.md`, `docs/knowledge/datasets.md`, `docs/knowledge/environment.md`, `docs/knowledge/legacy-defects.md`

**Interfaces:**
- Consumes: the legacy snapshot (Task 3) for citations; `tools/check_docs.py::check_index`, `check_links`, `check_citations`.
- Produces: link targets used by the skills in Task 5.

- [ ] **Step 1: Write `CLAUDE.md`**

````markdown
# DeepLabeling

A labeling and dataset-cleaning tool for YOLO datasets, built on PySide6 / Qt. It
replaces `yolo_labeling` (Tkinter), kept as a frozen reference in
[legacy/](legacy/README.md) — never imported, never edited.

**Status:** project scaffold. The app itself is designed next; see
[docs/design/](docs/design/2026-10-02-project-init.md).

```sh
./run.sh                       # launch from this checkout; nothing to install
python3 -m pytest              # Qt offscreen; see the run-and-verify-ui skill
python3 tools/check_docs.py    # are the docs still true?
```

## Where each fact lives

This file is loaded into every session, so it holds only what can be wrong before
knowing which task is in hand. Everything else is one link away.

| File | Owns | Read it when |
|---|---|---|
| `CLAUDE.md` | landmines, rules, this index | always — it is in context |
| [label-files.md](docs/knowledge/label-files.md) | the label format and every rule for reading and writing it | touching label I/O |
| [matching.md](docs/knowledge/matching.md) | how predictions are matched to labels; what each finding means | scans, filters, review |
| [caches.md](docs/knowledge/caches.md) | the prediction cache and label-cache freshness | anything cached |
| [datasets.md](docs/knowledge/datasets.md) | the pvn datasets, class maps, groups, transfer tools, training filters | dataset questions |
| [environment.md](docs/knowledge/environment.md) | the Python env, which ultralytics loads, OpenCV, disk | installing, importing, launching |
| [legacy-defects.md](docs/knowledge/legacy-defects.md) | every legacy defect and the rule it implies | porting, or designing what the legacy app had |
| [docs/design/](docs/design/2026-10-02-project-init.md) | specs and plans | starting a feature |
| `.claude/skills/*/SKILL.md` | when to act, and the procedure | the skill triggers |
| [tools/check_docs.py](tools/check_docs.py) | the drift checks | the hook reports a FAIL |

## Rules

1. **One fact, one home.** Need another document's fact? Link to it; never restate it.
2. **Prefer a command over a restatement.** Counts, lists and paths a command can compute
   are not written down — the legacy SPEC's "343 tests" went stale within a day.
3. **Cite code as `<path>.py::<symbol>`, from the repo root — never by line number.** Line
   numbers keep pointing somewhere after an edit, just at the wrong code.

`tools/check_docs.py` enforces all three, and a hook runs it after every edit.

## Landmines

Each of these cost real damage once.

1. Label files are written only through the one write path: atomic, byte-preserving.
   An empty `.txt` is a negative sample; never delete it.
2. Each image's labels have **one owner in memory**; views never keep their own copy.
   The legacy app kept five and synced them by hand — most of its corruption bugs.
3. The GUI thread never waits on the model; worker threads never touch widgets.
4. A UI change is verified by what is **visible**, not by widget state.
5. Model class ids are not dataset class ids: translate when reading, and an unmapped
   class is *inconclusive*, never "missing".
6. An upper bound never removes a prediction from matching.
7. A widget is seeded from the same value the logic reads, and every setting survives
   every launch path.
8. Which `ultralytics` gets imported depends on the launch directory. Importing it from
   another checkout resets `~/.config/Ultralytics/settings.json`.
9. The disk is nearly full: never copy datasets or prediction caches.
10. Tests write only to temporary folders; real app state is guarded.
````

- [ ] **Step 2: Write `docs/knowledge/label-files.md`**

Open with one line saying what the file owns. Then cover every fact below, citing the legacy implementation as evidence:

- Line format `cls cx cy w h`, normalised; polygons (`cls x1 y1 x2 y2 …`) and extra trailing columns occur and must survive a round trip. A polygon's box is its extent: `legacy/yolo_labeling/core/labelio.py::LabelLine`.
- Round trips are byte-preserving: an untouched line is re-emitted verbatim from its raw text; only a changed line is re-serialised. A class change splices the new id into the raw text rather than reformatting coordinates (`0.30` must not become `0.300000`): `legacy/yolo_labeling/core/labelio.py::LabelLine.with_class`.
- Writes are atomic — temp file, fsync, `os.replace` — so a crash cannot leave a truncated file: `legacy/yolo_labeling/core/labelio.py::write_label_file`.
- Never read with text-mode `readlines()`: universal-newline translation destroys CRLF on every line, not just the edited one.
- Every written line ends with a newline, or the next appended line runs into it.
- An emptied label file is written as **zero bytes**, never deleted: an empty `.txt` is a valid negative sample, a missing one is "unlabelled".
- Before writing a line recorded earlier (e.g. by a scan), re-locate it by class **and** box; refuse if it is gone or ambiguous (several identical lines). Never trust a stored line index: `legacy/yolo_labeling/core/labelio.py::locate_line`.
- One resolver maps an image to its label file, identical for reading and writing; prefix matching respects path boundaries; the longest mapping wins: `legacy/yolo_labeling/core/paths.py::LabelPathResolver`.
- Bulk edits are tested with the only-these-files-changed assertion: hash every `.txt` before and after, and assert the changed set equals the intended set.

- [ ] **Step 3: Write `docs/knowledge/matching.md`**

- Candidates: predictions overlapping a label at IoU ≥ the matching threshold: `legacy/yolo_labeling/core/badscan.py::candidates`.
- The deciding prediction is the **most confident** candidate, not the best-overlapping one; per-class NMS (the Ultralytics default) routinely yields `car 0.80` plus a slightly better aligned `truck 0.35` on one car: `legacy/yolo_labeling/core/badscan.py::deciding`.
- An unmapped deciding class is inconclusive, never a disagreement and never "missing".
- Finding kinds: wrong class; not an object (no candidate — banded on the nearest box's IoU: near 0 stray, higher badly drawn); weakly seen (agrees below a cutoff): `legacy/yolo_labeling/core/badscan.py::classify_gt`, `legacy/yolo_labeling/core/badscan.py::ScanConfig`.
- One shared confidence floor plus per-kind ceilings; an upper bound never removes a prediction from matching; a kind's results never depend on which other kinds are on.
- The checkable-class guard: a label whose class the model cannot emit (directly or via its group) is never "not an object": `legacy/yolo_labeling/ui/classes.py::ClassManagementMixin._checkable_classes`, `legacy/yolo_labeling/core/classmap.py::PredictionClassMap.emittable`.
- Nearest box recorded only at IoU ≥ 0.1, and the review crop's reach is capped, so a long thin prediction cannot shrink a small label to a sliver: `legacy/yolo_labeling/core/badscan.py::NEAREST_MIN_IOU`, `legacy/yolo_labeling/core/crops.py::MAX_REACH`.
- IoU is invariant under independent x/y scaling, so it can be computed on normalised coordinates with no image sizes. Pixel conversion rounds, never truncates.
- Overlap ranges are inclusive (identical boxes are exactly 1.0); a reversed range is refused by name, never swapped mid-edit: `legacy/yolo_labeling/ui/filters.py::FiltersMixin.overlap_iou_in_range`.
- Stacked identical boxes draw as one; show how many are stacked: `legacy/yolo_labeling/app.py::YOLOLabelingTool.detect_current_overlaps`.

- [ ] **Step 4: Write `docs/knowledge/caches.md`**

- Predictions are inferred and cached at a floor (`legacy/yolo_labeling/core/predcache.py::CONF_FLOOR`, 0.10), in **raw model ids**; consumers narrow to their own threshold (`legacy/yolo_labeling/core/predcache.py::filter_conf`) and translate on read. Below the floor nothing exists.
- The durable store is SQLite, keyed by model `name:size:mtime` (`legacy/yolo_labeling/core/predcache.py::model_key`) and image `size+mtime`: `legacy/yolo_labeling/core/predcache.py::PredictionCache`. Table `preds(model, img, size, mtime, floor, boxes)`, boxes JSON `[cls, x1, y1, x2, y2, conf]` in pixels.
- Read the durable store without promoting every row into memory during a dataset pass (about 1 GB at 46k frames): `legacy/yolo_labeling/app.py::YOLOLabelingTool._peek_cached_predictions`. "Never inferred" (`None`) and "inferred, nothing found" (`[]`) are different answers.
- A cached label parse is trusted only while the file's `(mtime_ns, size)` matches; an unstamped entry is stale: `legacy/yolo_labeling/ui/filters.py::FiltersMixin._labels_cache_fresh`.
- Image size comes from the header (about 0.03 ms) honouring EXIF orientation, never from a decode (about 3.4 ms; 46k frames is minutes).
- App state lives in a fixed directory, never relative to the launch directory: `legacy/yolo_labeling/app.py::STATE_DIR`.

- [ ] **Step 5: Write `docs/knowledge/datasets.md`**

- Location `/home/sonnn/Videos/tmp_dataset/pvn-dataset/` with `pvn-vehicle`, `pvn-person`, `pvn-helmet-violation`, `pvn-face-attribute` and others.
- `pvn-vehicle`: yamls `data_13class.yaml` (13 classes + `groups:`), `data_7class.yaml`, `data_UK_new.yaml` (15 classes: adds `LP_UK`, `pickup`); the 13 names and the 7 groups in insertion order (group order defines the merged model's class ids).
- Many top-level folders are copies (`check_run*`, `backup`…); use a yaml's train/val lists, not a recursive walk, to count a split.
- Prediction maps (model id → dataset id) versus class groups (equivalence); auto-mapping by name.
- Label transfer tools live in `/home/sonnn/Documents/ultralytics_sonnn/tools/data_transfer/`: `dataset_transfer.sh`, `merge_label_groups.py` (13 → 7), `backport_merged_edits.py` (7-class edits back onto 13-class labels, scale-aware matching).
- The training fork `/home/sonnn/Documents/ultralytics_sonnn` adds `groups` and `MinBoxFilter` (`min_rel_wh`, `min_rel_area`), applied after augmentation to the output canvas, on train **and** val. Consequences: a size cut in training is not the same cut in validation (square mosaic canvas vs. rect val batches padded to `ceil(s·imgsz/stride + 0.5)·stride`, so a landscape 1080p val image is 672×384), dropped boxes become background, and the validator does not filter predictions. The `dataset-analysis` skill's `size_cut_sim.py` computes it.
- Seven `best.pt` models are in the legacy prediction cache, distinguished only by `name:size:mtime`.

- [ ] **Step 6: Write `docs/knowledge/environment.md`**

- conda base, Python 3.10.12, PySide6 6.6.0, pytest-qt; nothing of this project is installed into it.
- `import ultralytics` resolves to the editable install `/home/sonnn/Documents/ultralytics`, except when the launch directory is `/home/sonnn/Documents/ultralytics_sonnn`, where its local `ultralytics/` shadows it. Models trained with fork-only modules need that fork importable.
- Importing ultralytics from a different checkout resets `~/.config/Ultralytics/settings.json` (`runs_dir`, `weights_dir`, `datasets_dir`); `settings.json.bak` there is from 2026-08-26.
- OpenCV: `opencv-python` 5.0 plus two `opencv-contrib-python` versions share one `cv2` directory. Declaring `opencv-python` does not reinstall it.
- setuptools is 60.2: an editable install with `pyproject.toml` needs build isolation (setuptools ≥ 64).
- Disk is about 99% full; check with `df -h /home/sonnn/Documents/PGit` before anything large.
- `imghdr` is gone in Python 3.13; never use it.

- [ ] **Step 7: Write `docs/knowledge/legacy-defects.md`**

A table — **symptom · root cause · fix · rule for DeepLabeling** — with one row per defect. First read `legacy/yolo_labeling/SPEC.md` and include every defect it lists. Then add these, fixed in the 2026-09/10 sessions:

| Symptom | Root cause | Rule |
|---|---|---|
| Find Bad flagged almost every box | raw model ids compared to dataset ids | translate on read; unmapped = inconclusive |
| Captions overlapped, unreadable | three layers drawn at one anchor | per-layer caption anchors on solid plates |
| GUI froze during scans | GUI thread waited on the model lock | GUI never blocks; non-blocking predict + retry |
| Status bar and toolbar invisible | packed after an expanding sibling; row wider than window; tests asserted state | assert visibility and geometry |
| "Infer all" didn't speed up scans | decoding images to get sizes | header-only size reads |
| Review window edited the wrong box | selection by index across re-sorts; stored line index trusted | selection by identity; locate by class+box, refuse if ambiguous |
| Review edits flattened polygons / lost CRLF | non-atomic writes, text-mode reads, `_loaded_boxes` not updated, reformatting on class change | one write path; one owner of labels |
| A file emptied by deletion vanished | writer removed the file | write zero bytes |
| Duplicates impossible to see | identical rectangles draw as one; `⚠` rendered as `?` by cv2 | show stack counts; ASCII-only cv2 text |
| Filter results differed after restart | settings not persisted; YAML launch skipped config load | persist; restore on every launch path |
| Filters reported stale boxes after import | label cache never checked file freshness | stamp cache entries |
| IoU filter blind after restart | read only in-memory predictions; dropped unmapped classes; threshold entry permanently disabled | read the durable store; geometry-only matching; never disable at setup |
| "Wrong class" flipped between runs | deciding on best overlap with per-class NMS duplicates | decide on most confident |
| Valid labels marked "delete" | model cannot emit their class | checkable-class guard |
| Config written to random folders | state relative to the launch directory | fixed state directory |
| Plain `pytest` could not collect tests | tests imported `core.*` top-level | import the package by its real name |

- [ ] **Step 8: Verify the docs**

Run: `python3 tools/check_docs.py`
Expected: `0 failure(s)`. Fix any FAIL by correcting the doc (or the citation) — never by weakening the checker. Review every WARN: each must be an intentionally cited external path.

---

### Task 5: The four skills and the analysis scripts

**Files:**
- Create: `.claude/skills/label-file-safety/SKILL.md`, `.claude/skills/run-and-verify-ui/SKILL.md`, `.claude/skills/legacy-reference/SKILL.md`, `.claude/skills/dataset-analysis/SKILL.md`, `.claude/skills/dataset-analysis/scripts/overlaps.py`, `.claude/skills/dataset-analysis/scripts/unmatched.py`, `.claude/skills/dataset-analysis/scripts/size_cut_sim.py`, `tests/test_dataset_scripts.py`

**Interfaces:**
- Consumes: knowledge docs from Task 4 (link targets); `tools/check_docs.py::check_skills`.
- Produces: `overlaps.py::scan(root, lo, hi, scope) -> list[(best_iou, Path)]`; `unmatched.py::analyse(db, model, conf_lo, conf_hi, match, classes=None) -> dict` with keys `images`, `no_label_file`, `unmatched_preds`, `unseen_labels`; `size_cut_sim.py::p_train_keep(wn, hn, W, H, t, scale=0.5) -> float`, `size_cut_sim.py::val_keep(wn, hn, W, H, t, imgsz=640, stride=32, pad=0.5) -> bool`.

- [ ] **Step 1: Write the four SKILL.md files**

Each body opens with: `Read [CLAUDE.md](../../../CLAUDE.md) first — the landmines are there and are not repeated here.` Each links to facts rather than restating them. Frontmatter, exactly:

`label-file-safety`:
```yaml
---
name: label-file-safety
description: Rules and test pattern for any code that reads, writes, renames, moves or deletes YOLO label files, or bulk-edits a dataset — including review actions, class reassignment, merges, imports, exports and "fix all" operations. Use it before writing or reviewing such code, even for a one-line change; a wrong write here silently corrupts training data and cannot be undone.
---
```
Body: a checklist (one write path; verify-before-write by class+box; refuse ambiguity; empty = zero bytes; preserve untouched bytes; the only-these-files-changed test), each item linking to its section of `docs/knowledge/label-files.md` (from the skill: `../../../docs/knowledge/label-files.md`); then the test pattern as a short code block (hash all `.txt` before/after, assert the changed set).

`run-and-verify-ui`:
```yaml
---
name: run-and-verify-ui
description: How to launch DeepLabeling headless, drive it, screenshot it and assert what is actually visible. Use it for any change to the UI — layout, widgets, panels, dialogs, canvas drawing — and before claiming a UI change works; tests that only check widget state have passed while the feature was invisible to the user.
---
```
Body: `QT_QPA_PLATFORM=offscreen` (default in `tests/conftest.py`) versus `QT_QPA_PLATFORM=xcb xvfb-run -a`; `qtbot.addWidget`, `waitUntil(widget.isVisible)`; `widget.grab().save(path)` then view the PNG; assert geometry (inside the window, non-zero size, not overlapping a sibling) and visibility, not only state; a UI fix is reported only with a screenshot or a geometry assertion as evidence.

`dataset-analysis`:
```yaml
---
name: dataset-analysis
description: Analyse the pvn YOLO datasets and the legacy prediction cache — label quality, duplicate or overlapping boxes, objects the model sees that nobody labelled, labels the model does not see, class maps and groups, and what a training-time size filter (min_rel_wh / MinBoxFilter) really keeps. Use it for any question about these datasets or their labels, even an informal one, before reasoning from memory.
---
```
Body: link to `docs/knowledge/datasets.md` (from the skill: `../../../docs/knowledge/datasets.md`); each script with its purpose and a sample command; all are read-only (the cache is opened `mode=ro`); they are self-contained until the core modules are ported, then switch to `deeplabeling.core`.

`legacy-reference`:
```yaml
---
name: legacy-reference
description: Where each feature of the old Tkinter app (legacy/yolo_labeling) lives, which of its behaviours were defects, and which of its tests pin what. Use it when porting a feature, designing one the old app had, or answering how the old app did something — so the port copies the fix and not the defect.
---
```
Body: a feature → module map (label I/O `core/labelio.py`; paths `core/paths.py`; geometry `core/geometry.py`; class maps `core/classmap.py`; prediction cache `core/predcache.py`; matching `core/badscan.py`; ranges `core/ranges.py`; crops `core/crops.py`; review marks `core/reviewmarks.py`; filters `ui/filters.py`; Find Bad and crop review `ui/crop_review.py`, `ui/dialogs.py`; classes and settings `ui/classes.py`; batch grid `ui/batch.py`; statistics `ui/stats.py`), all under `legacy/yolo_labeling/`; link to `docs/knowledge/legacy-defects.md` (from the skill: `../../../docs/knowledge/legacy-defects.md`); how to find the pinning tests (`grep -rn <feature> legacy/yolo_labeling/tests`); the legacy suite is not run from here.

- [ ] **Step 2: Write the failing script tests**

`tests/test_dataset_scripts.py`:
```python
"""The analysis scripts produce numbers the user acts on, so their arithmetic is
pinned on tiny synthetic datasets."""

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / ".claude/skills/dataset-analysis/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- overlaps.py -----------------------------------------------------------

@pytest.fixture
def labelled(tmp_path):
    labels = tmp_path / "ds" / "labels"
    labels.mkdir(parents=True)
    (labels / "dup.txt").write_text("0 0.5 0.5 0.2 0.2\n0 0.5 0.5 0.2 0.2\n")       # IoU 1.0
    (labels / "partial.txt").write_text("0 0.5 0.5 0.2 0.2\n0 0.52 0.5 0.2 0.2\n")  # IoU ~0.82
    (labels / "classes.txt").write_text("0 0.5 0.5 0.2 0.2\n1 0.5 0.5 0.2 0.2\n")   # diff class
    (labels / "apart.txt").write_text("0 0.2 0.2 0.1 0.1\n0 0.8 0.8 0.1 0.1\n")     # no overlap
    return tmp_path / "ds"


def names(hits):
    return sorted(p.name for _, p in hits)


def test_exact_duplicates_only(labelled):
    assert names(load("overlaps").scan(labelled, 0.99, 1.0, "same")) == ["dup.txt"]


def test_partial_overlaps_only(labelled):
    assert names(load("overlaps").scan(labelled, 0.5, 0.9, "same")) == ["partial.txt"]


def test_scope_different(labelled):
    assert names(load("overlaps").scan(labelled, 0.5, 1.0, "different")) == ["classes.txt"]


def test_non_overlapping_boxes_never_count_even_from_zero(labelled):
    assert "apart.txt" not in names(load("overlaps").scan(labelled, 0.0, 1.0, "any"))


# -- unmatched.py ----------------------------------------------------------

@pytest.fixture
def cached(tmp_path):
    images, labels = tmp_path / "ds/images", tmp_path / "ds/labels"
    images.mkdir(parents=True)
    labels.mkdir(parents=True)
    for name in ("a.png", "b.png"):
        Image.new("RGB", (100, 100)).save(images / name)
    (labels / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n")          # box 40..60
    db_path = tmp_path / "predictions.sqlite"
    db = sqlite3.connect(db_path)
    db.execute("create table preds (model text, img text, size integer, mtime integer, floor real, boxes text)")
    rows = {
        "a.png": [[0, 40, 40, 60, 60, 0.9], [0, 0, 0, 10, 10, 0.85]],   # one match, one unlabelled
        "b.png": [[0, 10, 10, 30, 30, 0.9]],                             # frame with no label file
    }
    for name, boxes in rows.items():
        db.execute("insert into preds values (?,?,?,?,?,?)",
                   ("m.pt:1:1", str(images / name), 0, 0, 0.1, json.dumps(boxes)))
    db.commit()
    db.close()
    return db_path


def test_unmatched_predictions_and_unlabelled_frames(cached):
    um = load("unmatched")
    db = um.open_ro(cached)
    out = um.analyse(db, "m.pt:1:1", 0.8, 1.0, 0.5)
    assert out["images"] == 2 and out["no_label_file"] == 1
    assert len(out["unmatched_preds"]) == 2
    assert out["unseen_labels"] == []


def test_a_floor_above_the_evidence_makes_the_label_unseen(cached):
    um = load("unmatched")
    out = um.analyse(um.open_ro(cached), "m.pt:1:1", 0.95, 1.0, 0.5)
    assert len(out["unseen_labels"]) == 1 and out["unmatched_preds"] == []


def test_the_cache_is_never_written(cached):
    before = cached.stat().st_mtime_ns
    um = load("unmatched")
    um.analyse(um.open_ro(cached), "m.pt:1:1", 0.25, 1.0, 0.5)
    with pytest.raises(sqlite3.OperationalError):
        um.open_ro(cached).execute("delete from preds")
    assert cached.stat().st_mtime_ns == before


# -- size_cut_sim.py -------------------------------------------------------

def test_val_rect_shapes_pad_the_long_side_too():
    """1080p val images are 672x384: a 1.02%-wide box is BELOW a 1% cut."""
    sim = load("size_cut_sim")
    assert sim.val_keep(0.0102, 0.5, 1920, 1080, 0.01) is False
    assert sim.val_keep(0.0106, 0.5, 1920, 1080, 0.01) is True


def test_val_height_cut_on_1080p():
    sim = load("size_cut_sim")
    assert sim.val_keep(0.5, 0.012, 1920, 1080, 0.01) is True     # 0.012*360/384 = 0.01125
    assert sim.val_keep(0.5, 0.010, 1920, 1080, 0.01) is False


def test_train_keep_probability_on_the_square_canvas():
    sim = load("size_cut_sim")
    p = sim.p_train_keep(0.5, 0.012, 1920, 1080, 0.01, scale=0.5)
    assert p == pytest.approx((1.5 - 0.01 / (0.012 * 0.5625)) / 1.0, rel=1e-6)


def test_train_keep_is_a_probability():
    sim = load("size_cut_sim")
    assert sim.p_train_keep(0.5, 0.5, 1920, 1080, 0.01) == 1.0
    assert sim.p_train_keep(0.001, 0.001, 1920, 1080, 0.01) == 0.0
```

- [ ] **Step 3: Run them to verify they fail**

Run: `python3 -m pytest tests/test_dataset_scripts.py`
Expected: ERRORs — the script files do not exist.

- [ ] **Step 4: Write `scripts/overlaps.py`**

```python
#!/usr/bin/env python3
"""Images whose labels overlap each other — from the label files alone, read-only.

IoU is computed on normalised coordinates, which is exact: IoU does not change
under independent x/y scaling, so no image sizes are needed. A pair counts when
its IoU is inside [--min, --max] (inclusive) and above zero.

  python3 overlaps.py /path/to/dataset --min 0.99 --max 1 --scope same
"""

from __future__ import annotations

import argparse
from pathlib import Path

SCOPES = ("same", "different", "any")


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter <= 0.0:
        return 0.0
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def boxes(label_file: Path):
    out = []
    for line in label_file.read_text(errors="replace").splitlines():
        t = line.split()
        if len(t) < 5:
            continue
        try:
            cls = int(float(t[0]))
            cx, cy, w, h = map(float, t[1:5])
        except ValueError:
            continue
        out.append((cls, (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)))
    return out


def counts(scope, a, b):
    return {"same": a == b, "different": a != b, "any": True}[scope]


def scan(root: Path, lo: float, hi: float, scope: str):
    """[(worst qualifying IoU, label file)] for every file with a qualifying pair."""
    hits = []
    for lf in sorted(Path(root).rglob("*.txt")):
        if "labels" not in lf.parts:
            continue
        bs = boxes(lf)
        qualifying = [v for i, p in enumerate(bs) for q in bs[i + 1:]
                      if counts(scope, p[0], q[0])
                      for v in [iou(p[1], q[1])] if v > 0.0 and lo <= v <= hi]
        if qualifying:
            hits.append((max(qualifying), lf))
    return sorted(hits, key=lambda h: (-h[0], str(h[1])))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", type=Path)
    ap.add_argument("--min", type=float, default=0.5)
    ap.add_argument("--max", type=float, default=1.0)
    ap.add_argument("--scope", choices=SCOPES, default="different")
    ap.add_argument("--list", type=int, default=10, help="show this many files")
    args = ap.parse_args(argv)
    hits = scan(args.root, args.min, args.max, args.scope)
    print(f"{len(hits)} file(s) with a {args.scope}-class pair at IoU {args.min}-{args.max}")
    for value, lf in hits[:args.list]:
        print(f"  {value:.4f}  {lf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Write `scripts/unmatched.py`**

```python
#!/usr/bin/env python3
"""Labels the model does not see, and predictions no label covers — read-only.

Reads the legacy prediction cache (SQLite table `preds`: model, img, size, mtime,
floor, boxes = JSON [cls, x1, y1, x2, y2, conf] in pixels). Labels are found by
the images/ -> labels/ convention; image sizes from the file header.

Matching is geometry only (any class), as in docs/knowledge/matching.md. There is
no checkable-class guard here: labels of a class the model cannot emit will show as
unseen. Restrict the predictions direction with --classes.

  python3 unmatched.py --cache .../predictions.sqlite --conf-lo 0.8
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from PIL import Image


def open_ro(path):
    return sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter <= 0.0:
        return 0.0
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def image_size(path: Path):
    with Image.open(path) as im:
        w, h = im.size
        if im.getexif().get(274, 1) in (5, 6, 7, 8):
            w, h = h, w
    return w, h


def label_file(img: Path) -> Path:
    parts = list(img.parts)
    i = len(parts) - 1 - parts[::-1].index("images")
    parts[i] = "labels"
    return Path(*parts).with_suffix(".txt")


def labels_px(lf: Path, w, h):
    out = []
    if not lf.is_file():
        return out
    for line in lf.read_text(errors="replace").splitlines():
        t = line.split()
        if len(t) < 5:
            continue
        try:
            cls = int(float(t[0]))
            cx, cy, bw, bh = map(float, t[1:5])
        except ValueError:
            continue
        out.append((cls, ((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h)))
    return out


def models(db):
    return db.execute("select model, count(*) from preds group by model order by 2 desc").fetchall()


def analyse(db, model, conf_lo, conf_hi, match, classes=None):
    out = {"images": 0, "no_label_file": 0, "unmatched_preds": [], "unseen_labels": []}
    for img, raw in db.execute("select img, boxes from preds where model = ?", (model,)):
        path = Path(img)
        try:
            w, h = image_size(path)
        except OSError:
            continue
        out["images"] += 1
        lf = label_file(path)
        if not lf.is_file():
            out["no_label_file"] += 1
        labels = labels_px(lf, w, h)
        preds = [(int(b[0]), float(b[5]), tuple(b[1:5])) for b in json.loads(raw) if float(b[5]) >= conf_lo]
        for cls, conf, box in preds:
            if conf > conf_hi or (classes is not None and cls not in classes):
                continue
            if not any(iou(box, lb) >= match for _, lb in labels):
                out["unmatched_preds"].append((img, cls, conf))
        for cls, lb in labels:
            if not any(iou(lb, box) >= match for _, _, box in preds):
                out["unseen_labels"].append((img, cls))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", required=True, type=Path)
    ap.add_argument("--model", help="model key; default: the one with the most rows")
    ap.add_argument("--conf-lo", type=float, default=0.25)
    ap.add_argument("--conf-hi", type=float, default=1.0)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--classes", help="comma-separated model class ids for the predictions direction")
    ap.add_argument("--examples", type=int, default=5)
    args = ap.parse_args(argv)
    db = open_ro(args.cache)
    available = models(db)
    for key, n in available:
        print(f"  {n:>8,}  {key}")
    model = args.model or available[0][0]
    classes = {int(c) for c in args.classes.split(",")} if args.classes else None
    out = analyse(db, model, args.conf_lo, args.conf_hi, args.iou, classes)
    print(f"model {model}: {out['images']:,} images, {out['no_label_file']:,} with no label file")
    print(f"predictions with no label (conf {args.conf_lo}-{args.conf_hi}): {len(out['unmatched_preds']):,}")
    for row in out["unmatched_preds"][:args.examples]:
        print("   ", row)
    print(f"labels the model does not see (conf >= {args.conf_lo}): {len(out['unseen_labels']):,}")
    for row in out["unseen_labels"][:args.examples]:
        print("   ", row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Write `scripts/size_cut_sim.py`**

```python
#!/usr/bin/env python3
"""What a training-time size cut (min_rel_wh / MinBoxFilter) keeps, in train vs val.

MinBoxFilter normalises by the AUGMENTED output image and keeps a box only if
w_rel >= t AND h_rel >= t.
  train: mosaic -> square imgsz canvas; each tile's long side = imgsz; scale jitter
         s ~ U(1 - scale, 1 + scale).  w_rel = wn*(W/L)*s, h_rel = hn*(H/L)*s
  val:   rect batches; each side = ceil(side/L * imgsz/stride + pad) * stride with
         pad 0.5 (BaseDataset.set_rectangle), so a 1080p image is 672 x 384.
Per-image approximation of the batch shape; ignores mosaic crops and cutmix.

  python3 size_cut_sim.py --yaml .../data_13class.yaml --val-thr 0.01 --train-thr 0.005
"""

from __future__ import annotations

import argparse
import collections
import math
from pathlib import Path

import yaml
from PIL import Image


def p_train_keep(wn, hn, W, H, t, scale=0.5):
    L = max(W, H)
    m = min(wn * W / L, hn * H / L)
    if m <= 0:
        return 0.0
    s_min = t / m
    lo, hi = 1 - scale, 1 + scale
    return min(max((hi - s_min) / (hi - lo), 0.0), 1.0)


def val_keep(wn, hn, W, H, t, imgsz=640, stride=32, pad=0.5):
    L = max(W, H)
    r = imgsz / L
    w_rect = math.ceil(W / L * imgsz / stride + pad) * stride
    h_rect = math.ceil(H / L * imgsz / stride + pad) * stride
    return wn * W * r / w_rect >= t and hn * H * r / h_rect >= t


def frames(data, base, split):
    folders = data.get(split) or []
    for rel in [folders] if isinstance(folders, str) else folders:
        d = base / rel
        if not d.is_dir():
            continue
        for img in sorted(d.iterdir()):
            if img.suffix.lower() not in (".jpg", ".jpeg", ".png", ".bmp"):
                continue
            lf = img.parent.parent / "labels" / (img.stem + ".txt")
            if not lf.is_file():
                continue
            try:
                with Image.open(img) as im:
                    W, H = im.size
                    if im.getexif().get(274, 1) in (5, 6, 7, 8):
                        W, H = H, W
            except OSError:
                continue
            rows = []
            for line in lf.read_text(errors="replace").splitlines():
                t = line.split()
                if len(t) >= 5:
                    try:
                        rows.append((int(float(t[0])), float(t[3]), float(t[4])))
                    except ValueError:
                        pass
            yield W, H, rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--yaml", required=True, type=Path)
    ap.add_argument("--val-thr", type=float, default=0.01)
    ap.add_argument("--train-thr", type=float, help="default: same as --val-thr")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--scale", type=float, default=0.5)
    args = ap.parse_args(argv)
    train_thr = args.val_thr if args.train_thr is None else args.train_thr
    data = yaml.safe_load(args.yaml.read_text())
    base = Path(data.get("path") or args.yaml.parent)
    names = data["names"]
    names = dict(enumerate(names)) if isinstance(names, list) else {int(k): v for k, v in names.items()}

    seen, dropped = collections.Counter(), collections.defaultdict(float)
    for W, H, rows in frames(data, base, "train"):
        for c, wn, hn in rows:
            seen[c] += 1
            dropped[c] += 1 - p_train_keep(wn, hn, W, H, train_thr, args.scale)
    print(f"TRAIN (thr {train_thr}): expected share dropped per epoch")
    for c in sorted(seen):
        print(f"  {names.get(c, c):>24}: {dropped[c] / seen[c]:6.1%} of {seen[c]:>8,}")

    ev, starved, total = collections.Counter(), collections.Counter(), 0
    for W, H, rows in frames(data, base, "val"):
        for c, wn, hn in rows:
            total += 1
            if val_keep(wn, hn, W, H, args.val_thr, args.imgsz):
                ev[c] += 1
                starved[c] += p_train_keep(wn, hn, W, H, train_thr, args.scale) < 0.5
    print(f"VAL (thr {args.val_thr}): {total - sum(ev.values()):,} of {total:,} GT removed "
          "(a correct detection of any is scored as a false positive)")
    for c in sorted(ev):
        print(f"  {names.get(c, c):>24}: {ev[c]:>7,} evaluated, "
              f"{starved[c] / ev[c]:6.1%} trained as background in >50% of samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 7: Run the script tests and the docs check**

Run: `python3 -m pytest tests/test_dataset_scripts.py && python3 tools/check_docs.py`
Expected: `11 passed`; `0 failure(s)`.

---

### Task 6: The drift hook

**Files:**
- Create: `.claude/hooks/check-docs-drift.sh`, `.claude/settings.json`, `tests/test_hook.py`

**Interfaces:**
- Consumes: `python3 tools/check_docs.py -q --root <repo>` (Task 2) — prints `FAIL …` lines, exit 1 on failure.
- Produces: on FAIL, JSON on stdout `{"systemMessage": …, "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": …}}`; otherwise no output. Always exit 0.

- [ ] **Step 1: Write the failing hook tests**

`tests/test_hook.py`:
```python
"""The hook must speak up exactly when the docs drift, and never block an edit."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude/hooks/check-docs-drift.sh"


@pytest.fixture
def repo(tmp_path):
    """A minimal repository the checker passes on, with the real hook and checker."""
    (tmp_path / ".claude/hooks").mkdir(parents=True)
    shutil.copy(HOOK, tmp_path / ".claude/hooks/check-docs-drift.sh")
    (tmp_path / "tools").mkdir()
    shutil.copy(ROOT / "tools/check_docs.py", tmp_path / "tools/check_docs.py")
    (tmp_path / "docs/knowledge").mkdir(parents=True)
    (tmp_path / "docs/knowledge/a.md").write_text("fine\n")
    (tmp_path / "CLAUDE.md").write_text("[a](docs/knowledge/a.md)\n")
    (tmp_path / "legacy/yolo_labeling").mkdir(parents=True)
    (tmp_path / "legacy/MANIFEST.sha256").write_text("")
    return tmp_path


def fire(repo, payload):
    hook = repo / ".claude/hooks/check-docs-drift.sh"
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(["sh", str(hook)], input=data, capture_output=True, text=True, timeout=30)


def edited(path):
    return {"tool_name": "Edit", "tool_input": {"file_path": str(path)}}


def test_a_clean_repo_is_silent(repo):
    r = fire(repo, edited(repo / "docs/knowledge/a.md"))
    assert r.returncode == 0 and r.stdout == ""


def test_a_broken_link_is_reported(repo):
    doc = repo / "docs/knowledge/a.md"
    doc.write_text("[x](missing.md)\n")
    r = fire(repo, edited(doc))
    assert r.returncode == 0
    message = json.loads(r.stdout)
    assert "FAIL links" in message["systemMessage"]
    assert message["hookSpecificOutput"]["hookEventName"] == "PostToolUse"


def test_a_file_outside_the_repo_is_ignored(repo, tmp_path_factory):
    (repo / "docs/knowledge/a.md").write_text("[x](missing.md)\n")
    elsewhere = tmp_path_factory.mktemp("elsewhere") / "notes.md"
    elsewhere.write_text("x")
    r = fire(repo, edited(elsewhere))
    assert r.returncode == 0 and r.stdout == ""


def test_an_irrelevant_file_type_is_ignored(repo):
    (repo / "docs/knowledge/a.md").write_text("[x](missing.md)\n")
    r = fire(repo, edited(repo / "picture.png"))
    assert r.returncode == 0 and r.stdout == ""


@pytest.mark.parametrize("payload", ["not json", "{}", '{"tool_input": {}}'])
def test_a_malformed_payload_is_ignored(repo, payload):
    r = fire(repo, payload)
    assert r.returncode == 0 and r.stdout == ""


def test_a_crashing_checker_is_reported(repo):
    """A checker that cannot run must not pass for 'no drift'."""
    (repo / "tools/check_docs.py").write_text("import module_that_does_not_exist\n")
    r = fire(repo, edited(repo / "docs/knowledge/a.md"))
    assert r.returncode == 0
    assert "could not run" in json.loads(r.stdout)["systemMessage"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_hook.py`
Expected: ERRORs — `.claude/hooks/check-docs-drift.sh` does not exist.

- [ ] **Step 3: Write the hook**

`.claude/hooks/check-docs-drift.sh`:
```sh
#!/bin/sh
# PostToolUse / Write|Edit: run tools/check_docs.py after an edit to a doc or code
# file in this repository, and surface any FAIL to the session.
#
# Non-blocking by design: it injects context and never denies. A mid-refactor
# state can be correct and briefly inconsistent.

payload=$(cat)
command -v jq >/dev/null 2>&1 || exit 0
f=$(printf '%s' "$payload" | jq -r '.tool_input.file_path // .tool_response.filePath // empty' 2>/dev/null) || exit 0
[ -n "$f" ] || exit 0

ROOT=$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd) || exit 0
case "$f" in
  "$ROOT"/*) ;;
  *) exit 0 ;;
esac
case "$f" in
  *.md|*.py|*/MANIFEST.sha256|*/pyproject.toml) ;;
  *) exit 0 ;;
esac

out=$(python3 "$ROOT/tools/check_docs.py" -q --root "$ROOT" 2>&1)
rc=$?
if printf '%s' "$out" | grep -q '^FAIL'; then
  MSG="Docs drift check failed after editing $(basename "$f"):

$out

The docs and the code now disagree. Fix whichever is wrong; run
python3 tools/check_docs.py for the full report."
elif [ "$rc" -ne 0 ]; then
  MSG="tools/check_docs.py could not run after editing $(basename "$f"), so drift was NOT checked:

$out"
else
  exit 0
fi

jq -n --arg m "$MSG" '{
  systemMessage: $m,
  hookSpecificOutput: { hookEventName: "PostToolUse", additionalContext: $m }
}'
exit 0
```

```bash
chmod +x .claude/hooks/check-docs-drift.sh
```

- [ ] **Step 4: Write `.claude/settings.json`**

```json
{
  "permissions": {
    "allow": [
      "Bash(./run.sh:*)",
      "Bash(python3 tools/check_docs.py:*)",
      "Bash(python3 -m pytest:*)",
      "Bash(pytest:*)",
      "Bash(git status:*)",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(ls:*)",
      "Bash(find:*)",
      "Bash(grep:*)",
      "Bash(rg:*)",
      "Bash(head:*)",
      "Bash(tail:*)",
      "Bash(wc:*)",
      "Bash(stat:*)",
      "Bash(du:*)",
      "Bash(df:*)"
    ],
    "deny": [
      "Bash(sudo:*)"
    ]
  },
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "sh /home/sonnn/Documents/PGit/DeepLabeling/.claude/hooks/check-docs-drift.sh",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 5: Run the hook tests**

Run: `python3 -m pytest tests/test_hook.py`
Expected: `8 passed`.

---

### Task 7: Final verification and the initial commit

**Files:**
- Modify: `tests/test_check_docs.py` (append one test), `docs/design/2026-10-02-project-init.md` and `docs/design/2026-10-02-project-init-plan.md` (status lines)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Add the whole-repository test**

Append to `tests/test_check_docs.py`:
```python
def test_the_repository_passes(cd):
    """The real repository has no drift. Every other test here proves the
    checker CAN fail; this one proves the project currently does not."""
    assert [str(f) for f in cd.run(ROOT) if f.level == "FAIL"] == []
```

- [ ] **Step 2: Mark the spec and the plan as done**

In `docs/design/2026-10-02-project-init.md`, change the status line to:
`**Status:** approved 2026-10-02 · implemented in the initial commit`.
At the top of this plan, under the title, add: `**Status:** executed 2026-10-02. This plan is history; the knowledge docs and CLAUDE.md are the live facts.`

- [ ] **Step 3: Run everything**

```bash
python3 -m pytest
python3 tools/check_docs.py
```

Expected: all tests pass; `0 failure(s)`. Read every WARN and confirm it is intended.

- [ ] **Step 4: Verify the window on screen, not in state**

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -c "
import sys
from PySide6.QtWidgets import QApplication
from deeplabeling.__main__ import build_window
app = QApplication(sys.argv); w = build_window(); w.show(); app.processEvents()
print('visible', w.isVisible(), '| title', w.windowTitle(), '| size', w.width(), w.height())
w.grab().save('/tmp/claude-1000/deeplabeling-shell.png')"
```

Then open the saved PNG and confirm it is a 1280×800 window image.

- [ ] **Step 5: Verify the hook end to end on the real repository**

```bash
printf '[x](nowhere.md)\n' > docs/knowledge/zz-probe.md
printf '{"tool_input":{"file_path":"%s/docs/knowledge/zz-probe.md"}}' "$PWD" | sh .claude/hooks/check-docs-drift.sh
rm docs/knowledge/zz-probe.md
printf '{"tool_input":{"file_path":"%s/CLAUDE.md"}}' "$PWD" | sh .claude/hooks/check-docs-drift.sh; echo "exit=$?"
```

Expected: the first call prints JSON naming `FAIL links` and `FAIL index`; the second prints nothing and `exit=0`.

- [ ] **Step 6: Commit**

```bash
git add -A
git status --short | grep -E '\.deeplabeling|\.sqlite|class_config\.json' && echo "STATE FILES STAGED - STOP" || echo "no state files staged"
git commit -m "Initialize DeepLabeling: knowledge, skills, drift checks, legacy reference

PySide6 rewrite of yolo_labeling. This commit is the project scaffold only:
CLAUDE.md and docs/knowledge/ distilled from the legacy app, four project
skills, tools/check_docs.py with a PostToolUse hook, a frozen legacy snapshot
with a checksum manifest, and an empty Qt main window.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git log --oneline
git status --short
```

Expected: `no state files staged`; exactly one commit; empty status.
