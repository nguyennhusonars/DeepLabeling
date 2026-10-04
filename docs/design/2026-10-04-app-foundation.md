# DeepLabeling — app foundation and slice 1 (the editor)

**Status:** approved 2026-10-04 · slices 1a (the core) and 1b (the viewer) implemented; the amendments found while building them are folded in; 1c (editing) next
**Scope:** the architecture every feature sits on, and **slice 1**: open a dataset, work
through a queue of images, and fix their boxes. Later slices get their own spec, plan and
build; [Later slices](#later-slices) records what each starts from.

## Why

One user (the author) spends time in four workflows, all of them daily:

1. fixing boxes one image at a time;
2. cleaning with the model: Find Bad, then reassigning or deleting the boxes it flags;
3. hunting with filters (overlap, IoU, size, class), then fixing the frames found;
4. pre-labeling: running the model, accepting its predictions, correcting them.

In the legacy app ([legacy/README.md](../../legacy/README.md)) all four went wrong in the
same four ways:

- **Can't see state.** It was unclear which filter, model or threshold was in force.
- **Modes don't mix.** Single view, the batch grid and crop review each navigated and
  selected differently, and switching between them lost your place.
- **Review loses context.** Crop review ran in its own window, so you saw the crop but not
  the frame, and a fix bigger than the crop meant going back to the main editor.
- **Too many controls.** The few daily controls were buried among the rare ones.

The four workflows share one loop: **a list of things to look at → see one in context →
fix it.** DeepLabeling is built around that loop. A *queue* holds the list, and the same
window serves every workflow.

## Decisions

| Question | Decision |
|---|---|
| Users | One person. A second DeepLabeling on the same dataset is refused, not supported |
| Legacy state | **Clean break.** DeepLabeling has its own prediction cache and its own review marks; it reads nothing of the legacy app's state |
| Layout | **Three panes**: queue, frame, inspector, under an always-visible state bar ([Window](#window)) |
| When an edit reaches disk | **Every edit**, as soon as it is made, atomically. There is no save key and no unsaved state |
| Undo | **Global**: one history across images, covering every edit, bulk and review ones included |
| What counts as reviewed | An image is marked when it is **edited**, on **done & next**, or by **mark page** in the grid. Viewing an image never marks it |
| Code structure | **Pure-Python core, thin Qt shell.** An edit records each file's bytes before and after it. An on-disk journal is deferred; this design keeps it a small addition |
| Which images and labels | Exactly what training reads ([Dataset](#dataset)) |

## Slices

Each slice replaces the legacy app for one workflow. The order follows the dependencies:
slice 3's IoU filter and slice 4 both read slice 2's prediction cache.

| # | Slice | Replaces the legacy app for |
|---|---|---|
| 1 | **Foundation + editor** (this spec) | fixing boxes one image at a time |
| 2 | Model assist: prediction cache and worker, a predictions layer, accept, a dataset inference pass, the class-map editor | pre-labeling |
| 3 | Filters as queue conditions: size, name, overlap, Label/Prediction IoU | hunting with filters |
| 4 | Find Bad as a queue source: findings in the queue, crop tiles in the grid, the finding spotlighted in the full frame, dismissals that persist | cleaning with the model |
| 5 | Bulk reassign, statistics, crop export and the Qwen round trip | the rest |

## Architecture

```
src/deeplabeling/
  core/                 imports no PySide6, enforced by a test; scripts import it too
    atomic.py           the one atomic writer; keeps permission bits
    labelio.py          port: LabelLine, parse, render, locate_line
    paths.py            the label-path rule (see Dataset)
    geometry.py         port: iou, normalised <-> pixel, clamp
    dataset.py          Dataset: from a yaml or a folder pair
    edits.py            LineRef, intents, Edit (bytes before/after per file), materialize
    store.py            LabelStore: the one owner of every image's labels
    history.py          global undo/redo of Edits
    editor.py           apply / undo / redo: write, record, mark reviewed, notify
    overlap.py          stack counts (the predicate slice 3's overlap filter reuses)
    queue.py            Condition, ImageFilter, QueueItem, Queue (cursor, statuses)
    review.py           review marks
    settings.py         the settings registry
    state.py            where app state lives; the per-root lock
    taxonomy.py         the taxonomy guard's checks
    workspace.py        Workspace.open: the one funnel every launch path goes through
  ui/
    session.py          the GUI thread's hold on one dataset: workspace, queue, jobs, actions;
                        the only object the widgets talk to (it is the "store bridge")
    main_window.py      layout A; wires the parts together
    state_bar.py  queue_panel.py  canvas.py  inspector.py  notices.py  queue_editor.py
    boxes.py  classes.py  what the canvas draws, computed without Qt; class colours, hotkeys
    images.py           decoding on workers into a byte-bounded cache
    keymap.py           the action registry: id, default key, description
    workers.py          QThreadPool jobs; results by queued signal through a relay
    settings_ui.py      global settings, the debounced saver, binding widgets to settings
    prompter.py         the real dialogs (tests answer the same calls with FakePrompter)
```

**One owner** ([landmine 2](../../CLAUDE.md#landmines)). Only `LabelStore` turns a label
file into labels in memory, and only `LabelStore.apply` and `LabelStore.restore` write one,
through `atomic.write_atomic`. Views hold immutable snapshots, re-fetch them when `labelsChanged(image)`
fires, and have nothing to mutate.

**Threads** ([landmine 3](../../CLAUDE.md#landmines)):

- The GUI thread owns the store's write path, the history, the settings and every write.
- Workers decode images and thumbnails, build queues, and (from slice 2) run inference and
  scans. A worker gets immutable inputs and a settings snapshot taken before it starts,
  and reports by queued signal. It never writes a file and never touches a widget.
- `LabelStore.get` is safe from any thread: a snapshot is a pure function of the file's
  bytes and stamp, cached under a lock. `LabelStore.apply` asserts it is on the GUI thread.
- An edit over many files (slice 5) is applied on the GUI thread in time-sliced chunks, so
  it still goes through the one owner.

**Dependencies point one way:** `ui → core`. Nothing under `src/` or `tests/` imports
`legacy/`; [tools/check_docs.py](../../tools/check_docs.py) checks that.

## Label document model

### Snapshots

`LabelStore.get(image)` returns an immutable `ImageLabels`: the label path, the raw bytes,
the parsed `LabelLine`s, the file's `(inode, mtime_ns, size)` stamp, and a state:

| State | Means |
|---|---|
| `missing` | no label file: not labelled yet |
| `ok` | the file exists; zero lines is a [negative sample](../knowledge/label-files.md#empty-file-is-a-negative-sample) |
| `shared` | another image resolves to the same label file (same stem, different extension, same folder); edits are refused |
| `error` | the file exists and cannot be read; edits are refused and the reason shown |

Every `get` stats the file. A changed stamp means a reload, and on the GUI thread a
`labelsChanged`, so an edit made outside the app appears on screen
([label-cache freshness](../knowledge/caches.md#label-cache-freshness)). The snapshot cache
is bounded in bytes (256 MB). The current image's snapshot stays pinned in it.

### Edits

A box is addressed by a `LineRef`: the label path, the line index as a hint, the class, and
the normalised box. That is the record
[locate before writing](../knowledge/label-files.md#locate-before-writing) needs. A user
action builds an **intent**: one or more operations on one image.

| Operation | Bytes it changes |
|---|---|
| `AddBox(cls, box)` | appends one line; gives the old last line its newline first |
| `SetBox(ref, box)` | re-serialises that line only, as a plain 5-token box |
| `SetClass(ref, cls)` | splices the id into that line's raw text |
| `DeleteLine(ref)` | removes that line; removing the last one leaves **zero bytes** |
| `CreateEmpty()` | creates an empty file on a `missing` image (an explicit negative sample) |

The full rules are in [label-files.md](../knowledge/label-files.md#byte-preserving-round-trips).

`LabelStore.apply(intent)`:

1. reads the current snapshot and locates every `LineRef` in it, by class and box. If a
   line is gone or ambiguous, the whole intent is refused and the refusal is shown;
2. computes the after-bytes, and with them an **Edit**: `{label path: (before | absent,
   after)}`, the images touched and a description;
3. writes each file atomically, creating the labels folder if it does not exist;
4. updates the snapshot. `Editor.apply`, the GUI thread's one entry point, then pushes
   the Edit onto the history, marks the image reviewed and emits `labelsChanged`.

Locating at apply time, not at build time, means an intent built against a snapshot that
changed in the meantime either applies to the right line or is refused. A drag is one
intent, built on mouse release. While the mouse moves, the canvas draws the box and stores
nothing.

Pixel geometry from the canvas becomes normalised coordinates through one conversion that
clamps to [0, 1]. Untouched lines are never converted at all, so nothing drifts
([geometry](../knowledge/matching.md#geometry)).

### History

- One global list of Edits, capped at 64 MB of stored bytes; the oldest are dropped first.
- **Undo** first checks that every file in the Edit still holds the Edit's after-bytes.
  Then it writes the before-bytes back. If any file differs, something else changed it
  since, and the undo is refused as a whole and shown; the file is left untouched.
- **Undoing the edit that created a file** deletes that file, which restores the
  `missing` state the image had. This is the only deletion of a label file in slice 1,
  and it happens only while the file still holds exactly what that edit wrote. Emptying
  a file is never a deletion ([landmine 1](../../CLAUDE.md#landmines)).
- **Redo** is the same in the other direction.
- If the Edit belongs to an image other than the current one, undo and redo first move the
  queue cursor to that image, so the change happens in view.
- The history lives in memory. A journal on disk would append each Edit as it is pushed;
  that is the deferred option, and nothing here has to change to add it.

### Lines the editor cannot change

- **Polygons** are drawn as outlines. They can be reclassified (spliced) and deleted. A move
  or resize is refused with a message, so a polygon never silently becomes a box.
- **Extra columns** (a confidence after the box) survive everything except a geometry edit
  of that line, which writes a plain 5-token box.
- **Unparsable lines** are kept byte for byte, are not drawn, and are counted in the
  inspector.
- **A class id outside the dataset's names** is drawn grey and dashed, captioned `#13?`.
  It is never dropped or remapped. Reclassifying the box fixes it.

### Negative samples are explicit

**Done & next** marks the image reviewed and never touches its label file. A separate
**mark negative** action applies `CreateEmpty` to a `missing` image with no boxes. Skipping
an unlabelled image therefore never makes it a negative sample.

## Dataset

`Dataset.open(spec)` is the one funnel for every launch path. A spec is either a yaml or an
image folder plus an optional label folder.

**Images** are found the way training finds them (`ultralytics/data/base.py`,
`BaseDataset.get_img_files`, in both the editable install and the training fork):

- every directory listed under `train`, `val` and `test` is globbed **recursively**;
- a listed `.txt` file is a list of image paths;
- extensions are matched case-insensitively against ultralytics' image formats;
- each split is sorted by path, and splits keep yaml order;
- an image listed in two splits appears once, under the first.

Legacy discovery was top-level only.

**Label paths** follow training's rule (`ultralytics/data/utils.py`, `img2label_paths`):
replace the **last** `images` folder in the path with `labels`, and the extension with
`.txt`. For a yaml-listed image with no `images` folder in its path, that rule yields a
`.txt` beside the image,
and since that is what training reads, DeepLabeling uses it too. A folder-pair launch with
an explicit label folder mirrors the image folder: `<label folder>/<path under the image
folder>.txt`, so a nested image never reads or writes a flat shadow file
(`src/deeplabeling/core/paths.py::folder_label_path`). A folder launch whose path has no
`images` component and no label folder is refused at open, with a message asking for the
label folder: with no yaml there is no training rule to follow, and DeepLabeling does not
guess. This replaces the legacy
fallbacks in `legacy/yolo_labeling/core/paths.py::LabelPathResolver` and is still the
[one resolver](../knowledge/label-files.md#one-path-resolver).

Measured 2026-10-04 on `data_13class.yaml`: recursive and top-level discovery find the same
images (train 36,725, val 8,527). The legacy resolver agrees with training's rule on every
one of them, so switching changes no label path for the existing data. Reproduce from the
repository root:

```sh
python3 - <<'EOF'
import glob, importlib.util, yaml
from pathlib import Path
s = importlib.util.spec_from_file_location("p", "legacy/yolo_labeling/core/paths.py")
p = importlib.util.module_from_spec(s); s.loader.exec_module(p)
y = Path("/home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/data_13class.yaml")
d, r = yaml.safe_load(y.read_text()), p.LabelPathResolver()
rule = lambda f: "/labels/".join(f.rsplit("/images/", 1)).rsplit(".", 1)[0] + ".txt"
for split in ("train", "val"):
    top = [f for q in d[split] for f in glob.glob(f"{y.parent / q}/*.*")]
    rec = [f for q in d[split] for f in glob.glob(f"{y.parent / q}/**/*.*", recursive=True)]
    print(split, len(top), len(rec), sum(str(r.resolve(f)) != rule(f) for f in rec))
EOF
```

**Classes** come from the yaml's `names` (a list or a dict). A folder pair reads
`classes.txt` from its label folder if there is one, and otherwise shows bare ids. The
yaml's `groups:` block is parsed and kept for slice 4; slice 1 does not use it.

**The canonical root** is the realpath of the yaml's `path:` when it has one, else of the
yaml's folder; for a folder pair, the realpath of the image folder. Per-dataset state is
keyed on it ([State and settings](#state-and-settings)). All three pvn-vehicle yamls
(`data_13class`, `data_7class`, `data_UK_new`) resolve to the same root, so they share
review marks, which describe images, and the lock. Class colours and hotkeys are keyed by
class **name**, so the yamls share those as well, even where their ids differ
([datasets.md](../knowledge/datasets.md#pvn-vehicle)).

**The taxonomy guard.** One set of label files can be read under more than one taxonomy:
[the 7-class and 13-class yamls read the same files](../knowledge/datasets.md#pvn-vehicle).
Under the wrong yaml the names are wrong, and every edit then writes ids from the wrong
taxonomy. Two checks catch this:

- **On open.** The root's state records the class names it was last opened with. Opening
  it with a different list asks for confirmation and names both yamls and both class
  counts. This catches 7-class files opened under the 13-class yaml, where every id is in
  range.
- **While queues build.** Boxes whose id is outside the yaml's names are counted. Any such
  box puts a standing warning in the notice strip ("N boxes have ids ≥ 7, which this yaml
  does not name. Is it the right yaml for these labels?"), and the boxes are drawn as
  `#id?` ([below](#lines-the-editor-cannot-change)).

## Queue

A queue is the list you are working through: what the queue panel shows, what next and
previous walk, and what the state bar describes.

- **`QueueSource`** builds the items on a worker and streams them in batches, so you can
  start on the first item while the rest load. It also describes itself, in one line, for
  the state bar.
- **Slice 1's one source is `ImageFilter`**: a split selection plus conditions, all of
  which must hold. With no conditions it is *all images*. Slice 3 adds more conditions to
  the same source rather than a second filter system. A saved condition names classes by
  name, not id, so it means the same under every yaml of the root.

| Condition (slice 1) | Holds when |
|---|---|
| class present / absent | the image has / lacks a box of the chosen classes |
| label state | `missing`, negative (an empty file), or has boxes |
| review state | reviewed / not reviewed |
| name contains | the dataset-relative path contains the text |

- **A `Condition`** has `test(image) -> bool`, `describe() -> str`, and optionally
  `highlight(snapshot) -> line indices`: the boxes that made it hold, which the canvas
  emphasises. The filter and the view of its result share one predicate
  ([matching.md](../knowledge/matching.md#overlap-between-labels)). In slice 1 the
  class-present condition highlights.
- **A `QueueItem`** has an identity key, an image, and a badge. Slice 4 adds a `focus`, the
  `LineRef` of a finding.
- **A queue is a snapshot.** Editing an image never removes it from the queue, so the item
  never vanishes under the cursor. After every `labelsChanged`, the conditions are
  re-tested on that one image, and an item that no longer matches shows *no longer
  matches*. Refresh rebuilds the queue.
- **The cursor is an identity key**, never an index. Next and previous move in queue order;
  at either end the cursor stays put and the status bar says so.
  After a rebuild the cursor stays on its key if the key is still there, and otherwise
  moves to the first item after it. The list or grid selection mirrors the cursor; there
  is no second notion of the current item.
- **Left** is the number of items not yet reviewed. It is shown beside the total.
- **The last queue and its cursor** are saved per dataset and restored on open.

### Review marks

- Stored per dataset as `{version, root, marks: {path: unix time}}`. Each key is the
  dataset-relative POSIX path, or the absolute path for an image outside the root.
- Written atomically, debounced by 2 s, and flushed when the dataset is closed or switched.
- **Marked** by an applied edit, by done & next, and by mark page.
- **Toggled** by `K`.
- **Never marked by viewing.** Paging, opening an image and rebuilding a queue mark
  nothing.
- Marks are not edits, so undo does not touch them.

## Window

Layout A, as chosen in the 2026-10-04 brainstorm (mockups in
`.superpowers/brainstorm/`, which git ignores).

```
┌ state bar: [pvn-vehicle · data_13class.yaml] [Queue: class has bus_l · 1,203 · 1,180 left] [Layers] [Reviewed 12,430 / 45,252] ┐
│ queue panel     │ notice strip (refusals, errors — stays until dismissed)        │ inspector        │
│ list ⇄ grid (G) │ canvas: the whole frame, boxes, captions, selection             │ image · classes  │
│                 │                                                               │ · boxes          │
└ status: camA/images/0418.jpg · 1920×1080 · item 412 / 1,203 · written 0.2 s ago · ↶ 14 ───────────────┘
```

**State bar.** A row of chips, always visible. Each chip shows a setting in force, and
clicking it changes that setting.

| Chip | Shows | Click |
|---|---|---|
| Dataset | name, yaml, splits, image count | open another dataset; recent datasets |
| Queue | the source's one-line description, items, left, a spinner while building | the queue editor: splits, conditions, refresh |
| Layers | labels, captions, crosshair (slice 2 adds predictions) | toggles |
| Reviewed | `12,430 / 45,252`, with the dataset as the denominator | — |

**Queue panel** (left dock). A virtualised list: the dataset-relative path, a badge
(`3 boxes`, `negative`, `missing`, *no longer matches*) and a reviewed tick. `G` switches it
to a grid of thumbnails with their label boxes drawn on them, and widens the panel to the
last grid width. In the grid, **mark page** marks every visible tile. Thumbnails decode at
display size on workers, only for visible rows, into a cache bounded in bytes (64 MB).

**Canvas** (centre, a `QGraphicsView`):

- **Scene and labels.** Scene coordinates are image pixels. Each box is drawn in its
  class's colour, with a caption on a solid plate inside its top edge. A box stacked on
  others shows the count: `car x2`. In slice 1 the stack count uses `core/overlap.py` with
  scope *any class* and IoU 0.99–1.00; slice 3's overlap filter reuses the same predicate
  ([why counts](../knowledge/matching.md#overlap-between-labels)). A box a condition
  highlighted gets a thicker outline.
- **Mouse.** Left-drag on empty space draws a box of the **active class**. Click selects a
  box; clicking again at the same spot cycles through the boxes under the cursor,
  smallest first. Shift+click adds to or removes from the selection. Drag a selected box
  to move it, or a handle to resize it. A drag under 3 px is a click. The wheel zooms
  about the cursor; middle- or right-drag pans. Each new image is fitted to the view.
- **Images.** Decoding runs on workers with Qt's EXIF auto-transform, matching the EXIF
  handling of [the size function](../knowledge/caches.md#image-sizes). The current image,
  the next two and the previous one are kept decoded, in a cache bounded in bytes
  (512 MB). An image that cannot be decoded shows a message, and editing it is disabled.

**Inspector** (right dock):

- **Image:** the path, the size, the label state, the unparsable-line count, and when it
  was reviewed.
- **Classes:** a palette of hotkey, swatch, name and count in this image. Clicking a class
  reclassifies the selection, or sets the active class when nothing is selected.
- **Boxes:** this image's boxes, with their selection kept in step with the canvas.

**Notice strip.** Every refusal and error appears above the canvas and stays until you
dismiss it or the next edit to that image succeeds. Progress never goes here or in the
status bar; it goes in the queue chip. In the legacy app, a refusal shown in the status bar
was overwritten by progress within 150 ms.

**Keys.** One registry, `ui/keymap.py`, defines every action. The `?` overlay is generated
from it, so the help cannot drift from the keys. No key works while a text field has focus.

| Key | Action |
|---|---|
| `→` `↓` / `←` `↑` | next / previous item (in the grid, `↑` `↓` move by row) |
| `Space` | done & next: mark reviewed, go to the next item |
| `K` | toggle reviewed |
| `N` | mark negative (a `missing` image with no boxes) |
| `1`–`9`, `0` | reclassify the selection, or set the active class when nothing is selected |
| `C` | class picker: type to filter, `Enter` to choose (for classes past the tenth hotkey) |
| `Del`, `Backspace` | delete the selected boxes |
| `Tab` / `Shift+Tab` | select the next / previous box |
| `Ctrl+A` | select every box |
| `Esc` | cancel the drawing, or clear the selection |
| `Ctrl+Z` / `Ctrl+Shift+Z`, `Ctrl+Y` | undo / redo |
| `Ctrl+C` / `Ctrl+V` | copy / paste the selected boxes as normalised, clamped coordinates; one edit |
| `F`, `+`, `-` | fit, zoom in, zoom out |
| `L`, `T` | toggle the labels layer, the captions |
| `G` | queue list ⇄ grid |
| `Ctrl+G` | go to an item by number or name |
| `?` | shortcut help |

No single key deletes a file, and every label change can be undone. Deleting an image is
not in slice 1.

**Smallest window:** 1024×640. At that size the state bar, the notice strip and the
canvas stay fully visible, and the docks shrink or can be closed.

## State and settings

**Where state lives** ([caches.md](../knowledge/caches.md#where-app-state-lives)):
`<repository>/.deeplabeling/`, found from the package's own location and never from the
launch directory. `DEEPLABELING_STATE_DIR` overrides it, and the tests always set it.

```
.deeplabeling/
  settings.json                       global settings
  datasets/<root name>-<sha1(root)[:8]>/
    dataset.json                      class colours and hotkeys by name; the class names last opened with;
                                      per opening (yaml or image folder): last queue, cursor, active class
    review.json                       review marks
    lock                              the pid of the DeepLabeling that has this root open
```

- **The lock** is an exclusive `flock` on the `lock` file, held while the root is open
  (`src/deeplabeling/core/state.py::DatasetLock`). A second open of the same root is
  refused, from another process or from this one (switching yaml means closing first),
  and the message names the holder's pid. The kernel drops the lock when its process
  dies, so a crash never leaves a stale lock to delete by hand.
- **Settings registry.** `core/settings.py` defines each setting once: its key, scope
  (global or dataset), default and validator. The registry is the list of settings.
  Widgets bind through one helper that seeds the widget from `settings.get` and writes
  every change back. A widget therefore cannot show a value the logic is not using, and
  every setting persists ([landmine 7](../../CLAUDE.md#landmines)). Writes are atomic and
  debounced.
- **Launch paths** all reach `Dataset.open`:
  - `./run.sh DATA.yaml`;
  - `./run.sh IMAGE_DIR [--labels LABEL_DIR]`;
  - `./run.sh` with no argument: reopen the last dataset, or the open dialog if there is
    none or it is gone;
  - the dataset chip.

  Each one restores the same per-dataset settings, and each has a test.

## Errors

| Situation | What happens | Where it shows |
|---|---|---|
| A line to edit is gone or ambiguous | the intent is refused; nothing is written | notice strip |
| Undo or redo of a file changed since | refused as a whole; nothing is written | notice strip |
| The image cannot be decoded | editing it is disabled; its label file is never written | canvas message, notice strip |
| The label file cannot be read | state `error`; edits refused | inspector, notice strip |
| The label file is shared by two images | state `shared`; edits refused | inspector |
| A move or resize of a polygon | refused | notice strip |
| A write fails (disk full, permissions) | the atomic writer leaves the old file; the Edit is not pushed | notice strip |
| The dataset is open in another DeepLabeling | the open is refused | dialog |
| The root was last opened with different class names | the open asks for confirmation, naming both yamls | dialog |
| Boxes with an id outside the yaml's names | counted; drawn as `#id?`; never dropped | notice strip (standing), canvas |
| A folder launch with no `images` component and no label folder | the open is refused | dialog |
| A worker raises | its job stops; the rest of the app carries on | notice strip |

## Performance targets

Measured on `data_13class.yaml`, on this machine, during the slice 1 build. A missed
target is recorded with its measured value, not quietly dropped.

| Action | Target | Measured 2026-10-04 |
|---|---|---|
| launch to the first image shown | ≤ 3 s | 1.13 s |
| next image, prefetched 1920×1080 JPEG | ≤ 100 ms | 2 ms, the worst of 10 |
| next image, not prefetched 4096×2336 | ≤ 300 ms | 46 ms, a frame at least 4000 px wide |
| one edit applied and written | ≤ 20 ms | 2 ms, the worst of 50 (ext4 on NVMe) |
| an *all images* queue: first items / complete | ≤ 1 s / ≤ 3 s | 109 ms / 272 ms |
| a class condition over 45k label files, cold / warm cache | ≤ 30 s / ≤ 5 s, streaming | 4.4 s / 0.69 s |

- "Cold" is the first pass after opening, while the open-time count of unnamed class ids
  reads every label file too; the OS page cache was warm.
- Before two fixes in plan 1b, launch took 7.4 s and the all-images queue 3.9 s: the queue
  list scrolled to the cursor on every batch of a building queue, re-laying out every row
  so far, and the state bar recounted the whole queue per batch.
- Reproduce, read-only (app state goes to a temporary folder):

```sh
/home/sonnn/miniconda3/bin/python3 tools/measure_ui.py /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/data_13class.yaml --class bus_l
```

## Testing

- **Core, headless.** One fixture generator, rewritten from
  `legacy/yolo_labeling/tests/fixtures.py::build_dataset`, covers multi-folder layouts,
  same-stem images in different folders, same-stem different-extension images in one
  folder, polygons, extra columns, CRLF, a missing final newline, malformed lines, an
  unreadable image, uppercase extensions, EXIF rotation, unicode names and a label with no
  image.
- **Every write path** is checked with an `assert_only_changed` rewritten from
  `legacy/yolo_labeling/tests/fixtures.py::assert_only_changed`. Every operation and every
  undo checks that the target file's bytes are exact, and that no other file in the
  fixture changed.
- **Undo and redo** restore byte-identical files. A file changed between an edit and its
  undo makes the undo refuse and stay untouched.
- **Core imports no Qt.** `deeplabeling.core` is imported in a subprocess with `PySide6`
  blocked.
- **UI, pytest-qt offscreen**, following the `run-and-verify-ui` skill
  ([landmine 4](../../CLAUDE.md#landmines)). The tests assert what is visible: from
  `grab()`, the state bar, queue, canvas and notice strip have non-zero, on-screen geometry
  at 1024×640 and at 1920×1080. A drawn box's colour appears at its scene position. A
  refusal's text is in the visible notice strip.
- **Review marks.** Paging marks nothing; done & next and an edit mark; marks survive a
  restart.
- **Single instance.** A second open of the same root is refused, even through a different
  yaml.
- **Taxonomy guard.** Reopening a root with a different class list asks first. Out-of-range
  ids are counted and drawn, never dropped.
- **Launch paths.** Each one restores a changed setting.
- **Real state is guarded** ([landmine 10](../../CLAUDE.md#landmines)): every test runs with
  `DEEPLABELING_STATE_DIR` in a temporary folder, and the session fails if the real
  `.deeplabeling/` changed. The pattern is `legacy/yolo_labeling/tests/conftest.py::state_dir`.

## Port order (slice 1)

The `legacy-reference` skill maps each module to the legacy tests that pin it. Each port
brings the fix, not the defect ([legacy-defects.md](../knowledge/legacy-defects.md)).

1. `labelio` and `geometry`: ported with their tests.
2. `paths`: rewritten to training's rule.
3. `overlap`: the stack count from
   `legacy/yolo_labeling/app.py::YOLOLabelingTool.detect_current_overlaps`.
4. New code: `atomic`, `dataset`, `edits`, `store`, `history`, `editor`, `queue`,
   `review`, `settings`, `state`, `taxonomy`, `workspace`.
5. The UI.

`imagetype`, and `imagesize` (from
`legacy/yolo_labeling/ui/filters.py::FiltersMixin._image_size`), wait for slice 3: nothing
in slice 1 needs them, because the UI takes sizes from Qt's decode.

`classmap` and `predcache` wait for slice 2, `ranges` for slice 3, and `badscan` and
`crops` for slice 4. `draw` is not ported: Qt draws the captions, which also ends the
ASCII-only caption limit of OpenCV's fonts. The `dataset-analysis` scripts move onto
`deeplabeling.core` so there is one implementation
([init spec](2026-10-02-project-init.md#skills)): `overlaps.py` in slice 1, once
`labelio` and `overlap` exist; `unmatched.py` and `size_cut_sim.py` with slice 4's port
of the matching code.

## Docs to update in slice 1

- [label-files.md](../knowledge/label-files.md#one-path-resolver): the resolver is
  training's rule; the measurement above shows that nothing moves.
- [caches.md](../knowledge/caches.md#where-app-state-lives): the state directory is
  decided.
- [legacy-defects.md](../knowledge/legacy-defects.md#not-fixed-in-the-legacy-app): resolve
  its "decide in the app design" items by linking here. Polygon edits are refused; images
  are found the way training finds them; viewing never marks an image reviewed; a second
  instance is refused; per-dataset state is keyed on the canonical root.
- [CLAUDE.md](../../CLAUDE.md): the status line.
- [environment.md](../knowledge/environment.md#python): which interpreter to use when
  another conda env is active.

## Notes for plan 1b (the UI)

From the slice 1a whole-branch review; the core is built, these are what the UI must do.

- **Open on the GUI thread.** `LabelStore` writes only on the thread that created it,
  and `Workspace.open` creates it.
- **`on_reload` fires on whichever thread called `get`.** A worker building a queue may be
  the first to see an outside change, so the bridge forwards it with a queued signal.
- **`Workspace.open` can raise `OSError`** (a full disk while taking the lock or saving
  `dataset.json`) as well as `DatasetError`, `Locked` and `OpenCancelled`. Catch it and
  say why.
- **"Reviewed X / N" counts marks among this dataset's images only.** `ReviewMarks.count`
  counts every mark under the root, and yamls sharing a root list different folders.
- **Switching yaml on one root means closing first**: a second open of an open root is
  refused, even in the same process ([The lock](#state-and-settings)).

## Later slices

What each later spec starts from. None of this is designed yet.

- **2 · Model assist.** Port `classmap` and `predcache` into a new store under
  `.deeplabeling/` (clean break), following [caches.md](../knowledge/caches.md). Inference
  runs on one worker and the GUI never waits on it. The predictions layer gets its own
  caption anchor. Accepting predictions is an `AddBox` intent, so it can be undone. The
  model chip joins the state bar.
- **3 · Filters.** Size, name, overlap and IoU conditions for `ImageFilter`, each with its
  `highlight` ([matching.md](../knowledge/matching.md)). Ranges follow
  `legacy/yolo_labeling/core/ranges.py::range_error`.
- **4 · Find Bad.** A `QueueSource` that streams findings with `focus` set. Grid tiles show
  the crop. The canvas spotlights the finding in the whole frame, with the finding's
  actions in the inspector. Dismissals persist per dataset.
- **5 · Bulk and the rest.** Bulk reassign is one multi-file Edit, applied in chunks and
  undoable. Then statistics, crop export with unique names (legacy #7), and the Qwen round
  trip.

## Out of scope

- Several people on one dataset, or merging their work.
- Reading or migrating the legacy app's state.
- Editing polygon geometry; semantic segmentation.
- Deleting images (to be decided in a later slice, with undo).
- An on-disk edit journal (deferred; see [History](#history)).
