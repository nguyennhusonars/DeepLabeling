"""The hook must speak up exactly when the docs drift, and never block an edit."""

import json
import shlex
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


def test_settings_run_the_hook_portably():
    settings = json.loads((ROOT / ".claude/settings.json").read_text())
    command = settings["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert "$CLAUDE_PROJECT_DIR" in command
    assert "/home/" not in command
    resolved = command.replace("$CLAUDE_PROJECT_DIR", str(ROOT))
    script = Path(shlex.split(resolved)[-1])
    assert script.is_file()


def test_settings_do_not_auto_approve_find():
    settings = json.loads((ROOT / ".claude/settings.json").read_text())
    allow = settings["permissions"]["allow"]
    assert not any(entry.startswith("Bash(find") for entry in allow)


def test_a_sibling_path_sharing_the_root_prefix_is_ignored(repo):
    (repo / "docs/knowledge/a.md").write_text("[x](missing.md)\n")
    sibling = repo.parent / (repo.name + "-other")
    sibling.mkdir()
    notes = sibling / "notes.md"
    notes.write_text("x")
    r = fire(repo, edited(notes))
    assert r.returncode == 0 and r.stdout == ""
