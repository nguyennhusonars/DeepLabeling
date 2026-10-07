# DeepLabeling — slice 5: bulk reassign and statistics

**Status:** approved 2026-10-07 · implemented: plans 5a (bulk reassign) and 5b (statistics)
**Scope:** slice 5 of [the app foundation](2026-10-04-app-foundation.md#slices), the last:
one class rewritten to another across a queue, as one edit; and the statistics of a queue,
as tables and charts. Everything slices 1–4 built stays as it is, except where this spec
says so.

## Why

What remains of the legacy app's daily use once the four workflows have moved
([foundation](2026-10-04-app-foundation.md#why)): renaming a class across a dataset or a
filtered part of it, and seeing what a dataset holds — its class balance, the sizes of its
boxes, where they sit. The legacy app's reassign dialog counted from a stale cache, and its
statistics read pixel sizes without EXIF orientation and resolved label paths its own way
([legacy-defects.md](../knowledge/legacy-defects.md)). Each of those is a rule below.

## Decisions

| Question | Decision |
|---|---|
| What reassign changes | **Every box of class A in the queue's images becomes B.** The whole dataset is the queue with no conditions. Only the boxes a condition matched, and a bulk delete, were the alternatives |
| How reassign writes | **As *Accept missing boxes in this queue* does** ([model assist](2026-10-05-model-assist.md#accepting)): looked at a chunk at a time, asked first with counts, written a chunk at a time as one edit, undone whole, marking nothing reviewed |
| What statistics show | **Tables, copyable as TSV, and four charts**: class balance, box sizes, box centres, boxes per image |
| How charts are drawn | **matplotlib, embedded**, imported when the dialog first opens (0.23 s measured 2026-10-07). QtCharts has no heatmap; painting by hand meant writing axes |
| Where they are reached | **The queue chip's menu**: both act on the queue |
| Dropped | **The Qwen round trip and crop export**, at the user's call on 2026-10-07: the export existed to feed Qwen, and slice 4's grid shows boxes as crops |

## The queue's images

Both features act on the images of the queue in force, **each image once** — a Find Bad
queue has several items to an image ([the queue](2026-10-06-find-bad.md#the-queue)). A
queue still building, or waiting for a model, is refused until it is complete, as accepting
across a queue is.

## Bulk reassign

### The dialog

*From* and *To*, with OK and Cancel:

- **From** lists the yaml's classes, then every class id the yaml does not name that the
  open-time check found (`src/deeplabeling/core/taxonomy.py::count_out_of_range`), shown
  `#99?` — so reassigning also repairs stray ids.
- **To** lists the yaml's classes.
- From equal to To is refused, and the dialog stays open, saying why.

### Look, ask, write

1. **Look.** Every image's labels are read through the label store a chunk at a time, on the
   GUI thread, behind a progress dialog that can cancel. An image whose label file cannot be
   edited — shared by two images, or unreadable — is skipped and counted.
2. **Ask.** `Reassign 1,234 car boxes on 567 images to bus?` then what was skipped, then `It
   is one edit: one undo takes it all back. Nothing is marked reviewed.` Nothing to reassign
   asks nothing: the status bar says so.
3. **Write.** A chunk at a time through the one write path
   ([label-files.md](../knowledge/label-files.md#writing)), as one edit. Each line keeps its
   bytes but the class token: coordinates, polygons, extra columns and line endings are
   untouched ([byte-preserving](../knowledge/label-files.md#byte-preserving-round-trips)).
   Cancelling keeps the chunks written, as one edit; a write that fails puts every file
   back, and what cannot be put back stays as an edit undo can retry.
4. **After.** The status bar says what was reassigned, on how many images, and what was
   skipped. The queue rechecks the images as after any edit, so a `has a car` queue shows
   them as *no longer matches*.

## Statistics

### What is computed

On a worker, from the label store and the header-only, EXIF-aware image sizes
([caches.md](../knowledge/caches.md#image-sizes)), into a Qt-free result
(`core/stats.py`):

- **Classes:** per class and split, the boxes, the images with at least one, and how many of
  the boxes are polygons. Ids the yaml does not name are rows of their own, `#99?`.
- **Label files:** per split, the images, those with boxes, negative (a file with no box:
  empty, or holding only lines that cannot be parsed), missing, unreadable, shared, and
  the lines that could not be parsed.
- **Box sizes:** per class, boxes by √(w·h) in pixels of the image as shown, in buckets
  < 8, 8–16, 16–32, 32–64, 64–128, 128–256 and ≥ 256 (each lower end inclusive). Images
  whose header cannot be read are counted; their boxes are left out of the pixel figures,
  never guessed. A box with a width or height not finite and positive, or a centre not
  finite, is counted as a box and left out of the sizes or the centres it cannot have.
- **Boxes per image:** how many images have 0, 1, … 19, and 20 or more. An image whose label
  file cannot be read is not among them: its count is unknown.
- **Box centres:** per class, a 20 × 20 grid of normalised box centres.

### The dialog

- A window of its own, not modal. Its title names the queue, and its status line how many
  images and when it was computed. **Recompute** computes again, for the queue in force,
  once that queue is whole. Closing it cancels a computation under way.
- While it computes: `reading 12,000 / 45,252`, and the window stays responsive.
- **Tables**, one tab each — Classes, Label files, Box sizes, Boxes per image. Each copies
  as TSV (a button, or Ctrl+C).
- **Charts**, drawn with matplotlib from the result when their tab is shown, and again
  when new numbers come while it is shown — never behind a tab, so a recompute does not
  hold the window up:
  - class balance: bars per class, train and val side by side;
  - box sizes: the buckets above, with a log count axis;
  - box centres: the 20 × 20 grid as a heatmap;
  - boxes per image: a histogram.
- A **Class** selector — all, or one — applies to the box sizes and the box centres.
  **Save charts…** writes them as one PNG.
- An empty queue says `no images` in the status line, and shows no charts.

## The queue chip

A click still opens the queue editor. The chip gains a menu (its arrow):

- *Edit queue…*
- *Reassign a class in this queue…*
- *Statistics of this queue…*

## Errors

| Situation | What happens | Where it shows |
|---|---|---|
| Reassign with From equal to To | refused | the dialog stays open, saying why |
| The queue is still building, or waits for a model | refused | status bar |
| No box of class From in the queue's images | nothing is written | status bar |
| A label file shared or unreadable | that image is skipped and counted | the question, then the status bar |
| A write fails part-way | every file written is put back; what cannot be stays as an edit undo can retry | notice |
| Reassign cancelled while looking / while writing | nothing written / the chunks written are kept, as one edit | status bar |
| Statistics meets an unreadable label file | counted as unreadable | the Label files table |
| An image header cannot be read | counted; its boxes are left out of pixel sizes only | the Box sizes table |
| Statistics of an empty queue | `no images`; no charts | the dialog's status line |
| Recompute while the queue is not whole | the last numbers stay; the reason is given | the dialog's status line |
| Save charts… fails | nothing is written | an error dialog |

## Performance targets

Measured on `data_13class.yaml`, on this machine. A missed target is recorded with its
measured value, not quietly dropped.

| Action | Target | Measured 2026-10-07 |
|---|---|---|
| reassign over 45k images: looking / writing 10k boxes | ≤ 30 s / ≤ 30 s, with progress, the window responsive | 750 ms / 938 ms (the write on a generated dataset) |
| statistics over 45k images, complete: cold / warm | ≤ 30 s / ≤ 5 s | 3.15 s / 1.41 s; cold was 8.2–9.6 s in two runs that day with a colder page cache |
| the window while statistics compute | the event loop never waits more than 100 ms | 15–20 ms cold, 10–23 ms warm, in six runs. Before a fix, cold missed in 2 of 4 runs: 200 and 221 ms (see below) |
| the dialog, its charts drawn, once the numbers are in | ≤ 1 s | 580–825 ms the first time (matplotlib imported), 217–221 ms after |

- "Cold" is the first computation after opening. The label files are already in the store
  by then — the open-time check of class ids reads every one — so cold reads the image
  headers; the OS page cache varied between runs.
- A warm computation is all Python on a worker, and held the GIL long enough to stall the
  window 177–223 ms; it pauses 0.5 ms every 256 images (`src/deeplabeling/core/stats.py::stats_of`).
- The cold misses were most likely a full garbage collection on the worker: it holds the GIL
  throughout, and the measurement logs 50–230 ms ones. The cold run made one more `Path`
  for each of 45k images and kept it (`src/deeplabeling/core/imagesize.py::ImageSizes.get`),
  and those survivors brought a full collection into the run. Keeping the path given ended
  the misses. Long full collections still come while a dataset opens and its class ids are
  checked; that is outside these targets.
- The reassign write is timed on a dataset generated in a temporary folder, never on the
  real one. Reproduce, read-only (app state goes to a temporary folder, deleted at the end):

```sh
/home/sonnn/miniconda3/bin/python3 tools/measure_bulk_stats.py /home/sonnn/Videos/tmp_dataset/pvn-dataset/pvn-vehicle/data_13class.yaml
```

## Testing

- **Core, on the generated edge-case dataset:**
  - reassign: only the class token changes, byte for byte — CRLF, polygons, extra columns;
    an unnamed id as From; shared and unreadable files skipped and counted; the plan's
    counts;
  - statistics: every count per split and class against the fixture; each label state;
    pixel sizes on an EXIF-rotated frame; the bucket edges; an unreadable header counted.
- **UI:**
  - the chip's menu; the reassign dialog's refusal; look, ask, write, cancel and undo as
    one edit, nothing marked reviewed;
  - the statistics tables read back, TSV copied; the charts read back from their pixels;
    the progress, and cancelling on close; geometry asserted, and a screenshot looked at.
- **One measurement script**, read-only, for the [targets](#performance-targets).

## Out of scope

- The Qwen round trip and crop export (dropped, see [Decisions](#decisions)).
- Deleting a class in bulk; reassigning only the boxes a condition matched.
- Statistics of predictions; statistics written to a file other than the TSV and the PNG.
