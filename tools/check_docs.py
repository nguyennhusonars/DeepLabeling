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

import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

#: Never scanned for docs: history, plugin state, caches, app state.
SKIP_DIRS = {".git", ".remember", ".superpowers", "legacy", "__pycache__", ".pytest_cache", ".deeplabeling"}

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
