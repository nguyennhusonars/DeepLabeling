---
name: label-file-safety
description: Rules and test pattern for any code that reads, writes, renames, moves or deletes YOLO label files, or bulk-edits a dataset — including review actions, class reassignment, merges, imports, exports and "fix all" operations. Use it before writing or reviewing such code, even for a one-line change; a wrong write here silently corrupts training data and cannot be undone.
---

Read [CLAUDE.md](../../../CLAUDE.md) first — the landmines are there and are not repeated here.

Before writing or reviewing any code that touches a label file, check it against this list:

- **One write path.** Every write goes through the single atomic writer; nothing else
  ever opens a label file to write it — see
  [Writing](../../../docs/knowledge/label-files.md#writing).
- **Verify-before-write by class and box.** Locate the line to change by its class and
  box, never by a stored line index — see
  [Locate before writing](../../../docs/knowledge/label-files.md#locate-before-writing).
- **Refuse ambiguity.** If more than one line matches, stop and report it instead of
  picking one — see
  [Locate before writing](../../../docs/knowledge/label-files.md#locate-before-writing).
- **Empty means zero bytes.** An emptied label file is written as zero bytes; it is
  never deleted — see
  [Empty file is a negative sample](../../../docs/knowledge/label-files.md#empty-file-is-a-negative-sample).
- **Preserve untouched bytes.** A line nobody changed is re-emitted exactly as read;
  only a changed line is re-serialised — see
  [Byte-preserving round trips](../../../docs/knowledge/label-files.md#byte-preserving-round-trips).
- **The only-these-files-changed test.** Every test of a review action, reassignment,
  merge, import, export or bulk "fix all" asserts exactly which files changed — see
  [Testing bulk edits](../../../docs/knowledge/label-files.md#testing-bulk-edits).

Test pattern — hash every `.txt` before and after the operation, and assert the set of
changed files against what the operation was meant to touch:

```python
import hashlib

def snapshot(root):
    return {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*.txt")}

before = snapshot(dataset_root)
run_the_operation()
after = snapshot(dataset_root)

changed = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
assert changed == expected_changed_files   # expect set() when nothing may be written
```
