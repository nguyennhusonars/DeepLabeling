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
