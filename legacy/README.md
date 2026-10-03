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
