# DeepLabeling

A labeling and dataset-cleaning tool for YOLO datasets, built on PySide6 / Qt. It
replaces `yolo_labeling` (Tkinter), kept as a frozen reference in
[legacy/](legacy/README.md) — never imported, never edited.

**Status:** slice 1 is built: the core, the viewer, editing on the canvas and the queue
grid. Slice 2 (model assist) is next. The design and the plans are in
[docs/design/](docs/design/).

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
| [docs/design/](docs/design/) | specs and plans | starting a feature |
| `.claude/skills/*/SKILL.md` | when to act, and the procedure | the skill triggers |
| [tools/check_docs.py](tools/check_docs.py) | the drift checks | the hook reports a FAIL |

## Rules

1. **One fact, one home.** Need another document's fact? Link to it; never restate it.
2. **Prefer a command over a restatement.** Counts, lists and paths a command can compute
   are not written down — the legacy SPEC's "343 tests" went stale within a day. A
   measurement that justifies a rule is kept, with its date and the command that
   reproduces it.
3. **Cite code as `<path>.py::<symbol>`, from the repo root — never by line number.** Line
   numbers keep pointing somewhere after an edit, just at the wrong code.

`tools/check_docs.py` checks links, `path::symbol` citations, the knowledge index, the
skills' frontmatter, and the legacy snapshot and its imports. Rules 1–2, and rule 3's
"never by line number", are judgement calls it cannot check. A hook runs the checker after
every Write/Edit — run it yourself after a Bash edit, move or delete.

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
