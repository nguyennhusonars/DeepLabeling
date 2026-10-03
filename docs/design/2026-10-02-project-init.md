# DeepLabeling — project init

**Status:** approved 2026-10-02 · implemented in the initial commit
**Scope:** the project itself — knowledge, skills, sync tooling, a frozen legacy
reference and an empty, launchable Qt shell. **No labeling features.** The app's
workflows, layout and UX get their own design session once this exists.

## Why

`yolo_labeling` (Tkinter) grew to ~10k lines with poor UX: the navigator, toolbox
and sidebar are hard to find your way around, and features interfere with each other.
Most of the defects fixed in the last session came from one cause — the same labels
held in several places and kept in step by hand. DeepLabeling is a rewrite that
keeps what was learned and drops that structure.

The project must start with that knowledge in place, so every future session
begins from what was learned rather than from the old code.

## Decisions

| Question | Decision |
|---|---|
| UI stack | **PySide6 / Qt** — docks and toolbars for layout, `QGraphicsView` for the canvas, models run in-process |
| "Every edit in sync" | **Both**: docs and knowledge match the code, *and* every label edit is consistent across all views in the app |
| Skills | `label-file-safety`, `run-and-verify-ui`, `dataset-analysis`, `legacy-reference` |
| Legacy reference | **Frozen copy** in `legacy/yolo_labeling/`, read-only, never imported |
| Python environment | conda **base** — already has PySide6 6.6, ultralytics, OpenCV, numpy. Adds only `pytest-qt` |
| Git | `git init`, then **one** initial commit containing this spec and the scaffold |

## Layout

```
DeepLabeling/
├── CLAUDE.md                     always-true facts, where each fact lives, rules, landmines
├── docs/
│   ├── knowledge/                one topic per file — the canonical home of each fact
│   │   ├── label-files.md
│   │   ├── matching.md
│   │   ├── caches.md
│   │   ├── datasets.md
│   │   ├── environment.md
│   │   └── legacy-defects.md
│   └── design/                   specs; this file, then the app design
├── legacy/
│   ├── README.md                 what this is, and the never-import / never-edit rule
│   ├── MANIFEST.sha256           checksums of every file below
│   └── yolo_labeling/            the snapshot
├── src/deeplabeling/
│   ├── __init__.py
│   └── __main__.py               opens an empty main window
├── tests/
│   ├── conftest.py               Qt offscreen by default
│   ├── test_smoke.py
│   └── test_check_docs.py
├── tools/check_docs.py           the drift checker
├── .claude/
│   ├── settings.json             hooks + read-only permission allowlist
│   ├── hooks/check-docs-drift.sh
│   └── skills/
│       ├── label-file-safety/SKILL.md
│       ├── run-and-verify-ui/SKILL.md
│       ├── dataset-analysis/SKILL.md  (+ scripts/)
│       └── legacy-reference/SKILL.md
├── run.sh                        launch without installing (PYTHONPATH=src)
├── pyproject.toml
└── .gitignore
```

`src/` layout, so the package directory is not the repository root. That removes
the `package-dir = {"yolo_labeling" = "."}` mapping the legacy app needed, and the
rule that its folder had to be named after the package.

## Knowledge system

### CLAUDE.md

Loaded into every session, so it holds only what can be wrong **before** knowing
which sub-task is in hand. It should stay well under 150 lines.

- what DeepLabeling is, and that `legacy/` is reference only;
- a **"where each fact lives"** table that indexes `docs/knowledge/`, the skills,
  and the design specs;
- the three rules below;
- the **landmines** — the short list of facts that each cost real damage once:
  1. Label files are written only through the one write path: atomic, byte-preserving.
     An empty `.txt` is a negative sample; never delete it.
  2. Each image's labels have **one owner in memory**; views never keep their own copy.
  3. The GUI thread never waits on the model; worker threads never touch widgets.
  4. A UI change is verified by what is **visible**, not by widget state.
  5. Model class ids are not dataset class ids: translate when reading, and an
     unmapped class is *inconclusive*, never "missing".
  6. An upper bound never removes a prediction from matching.
  7. A widget is seeded from the same value the logic reads, and every setting
     survives every launch path.
  8. Which `ultralytics` gets imported depends on the launch directory. Importing it
     from another checkout resets `~/.config/Ultralytics/settings.json`.
  9. The disk is nearly full: never copy datasets or prediction caches.
  10. Tests write only to temporary folders; real app state is guarded.

### The three rules (from cnngen_convert)

1. **One fact, one home.** A document that needs another document's fact links to
   it instead of restating it.
2. **Prefer a command over a restatement.** Counts, lists and paths that a command can
   compute are not written down. The legacy SPEC's "343 tests", stale within a day,
   is the example.
3. **Cite code by `path::symbol`, never by line number.** Line numbers keep pointing
   somewhere after an edit, just at the wrong code.

### docs/knowledge/

Each file says what it owns. The sources are the legacy SPEC, the legacy code, and
the measurements taken in the last session.

| File | Owns |
|---|---|
| `label-files.md` | YOLO line format incl. polygons and extra columns; byte-preserving round trips (`raw` + dirty); atomic writes; CRLF; trailing newline; empty file = negative sample; locate-by-class-and-box before writing; the only-these-files-changed assertion |
| `matching.md` | candidates, the deciding prediction (most confident, not best overlap), the nearest box, the kinds (wrong class / not an object / weakly seen), the shared floor plus per-kind ceilings, the checkable-class guard, IoU being scale-invariant, rounding not truncation |
| `caches.md` | prediction cache: stored at `CONF_FLOOR` in raw model ids, keyed by model `name:size:mtime` and image `size+mtime`, translated on read, never promoted wholesale into memory; label cache stamped with `(mtime_ns, size)`, and an unstamped entry counts as stale |
| `datasets.md` | the pvn datasets and their yamls; 13 classes → 7 groups; `data_UK`'s 15 classes (`LP_UK`, `pickup`); the label-transfer tools in `ultralytics_sonnn/tools/data_transfer/`; the fork's `MinBoxFilter` and its train/val mismatch; the models in the cache |
| `environment.md` | conda base; ultralytics is an editable install of `~/Documents/ultralytics`, not `ultralytics_sonnn`; the settings.json resets; OpenCV is `opencv-python` 5.0 plus two `opencv-contrib-python` versions; setuptools 60 (editable installs need build isolation); disk space |
| `legacy-defects.md` | every defect fixed in `yolo_labeling`: symptom, root cause, the fix, and the rule it implies for DeepLabeling. This is the do-not-repeat list |

## Sync 1 — docs match code

`tools/check_docs.py` checks the following. Each failure prints `FAIL <check>: <detail>`,
and the script exits non-zero on any failure. `-q` prints failures only.

| Check | Rule |
|---|---|
| links | every relative Markdown link resolves to an existing file |
| citations | every `` `path::symbol` `` names an existing file defining `symbol` (`def`, `class`, or a top-level assignment) |
| skills | each `.claude/skills/<dir>/SKILL.md` has frontmatter with `name: <dir>` and a non-empty `description` |
| index | `CLAUDE.md`'s table and `docs/knowledge/*.md` list the same files |
| legacy | `legacy/MANIFEST.sha256` still matches the snapshot |
| legacy imports | nothing under `src/` or `tests/` imports from `legacy` |
| external paths | every backticked absolute path (`/…` or `~/…`) in the docs exists — **WARN**, not FAIL, since those are not ours to keep |

`.claude/hooks/check-docs-drift.sh` runs on PostToolUse for `Write|Edit` when the
edited file inside the repository is a `.md`, a `.py`, `MANIFEST.sha256` or
`pyproject.toml` — the checker takes well under a second, so there is no reason to
guess which edits matter. On failure it
injects the report as context. It never blocks an edit, because a mid-refactor
state can be correct and briefly inconsistent.

`tests/test_check_docs.py` runs the checker on the real repository, where it must
pass, and on deliberately broken fixtures, where each check must fail. Otherwise the
checker could pass on every input and prove nothing.

## Sync 2 — label edits stay consistent

Recorded now as a rule and enforced once the app exists. This spec doesn't design
it; the app spec does.

- One in-memory owner per image's labels. Every change is a command through it,
  which is also what makes undo possible. Every view subscribes to it, and only it
  writes to disk.
- The legacy app kept **five** copies of the same labels and synced them by hand:
  `label_boxes`, `_loaded_boxes`, `_label_lines`, `labels_cache`, and the crop-review
  entries. Most corruption defects came from two of them disagreeing; see
  `legacy-defects.md`.

## Skills

Each `SKILL.md` follows the cnngen_convert format: a `name`, a trigger-rich
`description`, and a body that starts by pointing at `CLAUDE.md`. It does not repeat
facts; it links to their home.

| Skill | Triggers on | Body |
|---|---|---|
| `label-file-safety` | writing or reviewing any code that reads, writes, renames or deletes label files, or bulk-edits a dataset | the rules, as a checklist; the only-these-files-changed test pattern; links to `label-files.md` |
| `run-and-verify-ui` | any change to what the user sees, or a claim that a UI change works | launch offscreen (`QT_QPA_PLATFORM=offscreen`) or with `xvfb-run`; `QWidget.grab()` screenshots; assert geometry and visibility; never report a UI fix from state-only tests |
| `dataset-analysis` | questions about pvn datasets, class maps, groups, label quality, predictions, or training filters | links to `datasets.md`; read-only scripts with arguments: `overlaps.py`, `unmatched.py`, `size_cut_sim.py` |
| `legacy-reference` | porting a feature, or asking how the old app did something | a map from features to legacy modules; links to `legacy-defects.md`; which legacy tests pin which behaviour, so a port copies the fix and not the defect |

The scripts are **self-contained** for now. Once the core modules are ported they
must switch to `deeplabeling.core`, so there is one matching implementation, not two.

## Legacy snapshot

- **Source:** `/home/sonnn/Documents/PGit/yolo_labeling` — the newest copy, including
  the package-directory state change.
- **Excluded:** `class_config.json`, `.yolo_labeling_cache/`, `__pycache__/`,
  `.pytest_cache/`, `*.egg-info/`, `.remember/`, `.ruff_cache/`. These are app state, 
  tool output, and plugin session state — not reference material.
- **`MANIFEST.sha256`** lists every file; the `legacy` check verifies it.
- **Never imported:** enforced by the `legacy imports` check.

## Package skeleton

- `pyproject.toml`: name `deeplabeling`, `requires-python >= 3.10`, dependencies
  `PySide6`, `numpy`, `opencv-python`, `Pillow`, `PyYAML`; extras `model = [ultralytics]`
  and `test = [pytest, pytest-qt]`; a `deeplabeling` console script; pytest config with
  `pythonpath = ["src"]` and `qt_api = "pyside6"`.
- `src/deeplabeling/__main__.py`: a `QApplication` with an empty `QMainWindow` titled
  "DeepLabeling". Nothing else.
- **Not installed into base.** `run.sh` sets `PYTHONPATH=src`, and pytest finds
  `src/` itself, so the shared environment gains only `pytest-qt`.
- **App state** will live in `.deeplabeling/` at the project root, gitignored. The
  name is provisional; nothing writes there until the app spec says what goes in it.

## Environment

- conda base, Python 3.10.12, PySide6 6.6.0.
- Install `pytest-qt` into base (approved).
- Qt tests run with `QT_QPA_PLATFORM=offscreen`, set in `conftest.py`. `xvfb-run` is
  the fallback when a test needs a real X server.
- About 7.8 GB free: no new conda environment, no copied caches or datasets.

## Git

- `git init -b main`, with identity Son Nguyen <sonnn@mkvision.com>.
- `.gitignore`: `.deeplabeling/`, `__pycache__/`, `.pytest_cache/`, `*.egg-info/`.
  `.remember/` already ignores itself.
- One initial commit: this spec plus the scaffold, with the attribution trailer.

## Verification

1. `python tools/check_docs.py` passes on the repository.
2. `pytest` passes: the smoke test and the checker tests, including the
   broken-fixture cases.
3. `./run.sh` opens a visible window titled "DeepLabeling", confirmed by a
   `grab()` screenshot rather than by widget state.
4. Editing a knowledge file to break a link makes the hook report a FAIL.
5. `git log` shows exactly one commit; `git status` is clean.

## Next

The app design session, inside DeepLabeling: the main workflows (label, review,
clean the dataset), the window layout and navigation, the label document model
(Sync 2), and the order in which the legacy core modules are ported — the pure,
tested ones (`labelio`, `paths`, `geometry`, `classmap`, `predcache`, `badscan`,
`ranges`, `imagetype`) first.
