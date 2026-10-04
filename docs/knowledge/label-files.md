# Label files

Owns: the YOLO label format and every rule for reading and writing a label file.

The evidence is the legacy implementation, mostly `legacy/yolo_labeling/core/labelio.py`.
Each section ends in the rule DeepLabeling follows.

## Line format

One object per line, whitespace-separated, coordinates normalised to [0, 1].

| Line | Tokens | How the legacy parser reads it |
|---|---|---|
| box | `cls cx cy w h` | 4 coordinates |
| box plus extra columns (e.g. a confidence) | `cls cx cy w h conf` | 5 coordinates: still a box; the extra value stays in `coords` |
| polygon | `cls x1 y1 x2 y2 x3 y3 …` | more than 5 coordinates; its box is the axis-aligned extent of its points |
| anything else | blank, whitespace only, fewer than 5 tokens, a non-numeric field | kept verbatim with no class (`parsed` is false) |

- Evidence: `legacy/yolo_labeling/core/labelio.py::LabelLine` (`is_polygon`, `bbox`),
  `legacy/yolo_labeling/core/labelio.py::parse_label_text`.
- The parser never raises: an unparsable line is kept as it is, not fatal to the lines
  after it.
- Class ids outside the class list (`99`, `-1`) still parse as classes.
- `legacy/yolo_labeling/tests/fixtures.py::GAUNTLET` holds every malformed shape the
  legacy parser survives (CRLF, a confidence column, no final newline, three identical
  class-0 boxes, …). Port it as a fixture.
- Editing a polygon's geometry in the legacy app turns it into a box
  (`legacy/yolo_labeling/core/labelio.py::LabelLine.with_bbox`).

**Rule:** polygons, extra columns and unparsable lines survive every round trip. Show a
polygon by its extent and never write the extent in its place: DeepLabeling refuses to
move or resize a polygon
([app design](../design/2026-10-04-app-foundation.md#lines-the-editor-cannot-change)).

## Byte-preserving round trips

- Every line keeps `raw`, its exact source text including the terminator, and a `dirty`
  flag. A clean line is emitted as `raw`; only a dirty line is re-serialised (`%.6f`):
  `legacy/yolo_labeling/core/labelio.py::LabelLine.render`.
- A class change splices the new id into `raw` (a regex on the first token) instead of
  re-serialising, so `0.30` stays `0.30` — re-serialising turned it into `0.300000` on
  every reassigned line: `legacy/yolo_labeling/core/labelio.py::LabelLine.with_class`.
- Opening and saving an untouched file writes nothing: the legacy save returns early when
  the boxes equal what was loaded (`legacy/yolo_labeling/app.py::YOLOLabelingTool.save_labels`).
  That save still re-serialises every line once anything was edited — see
  [legacy-defects.md](legacy-defects.md#not-fixed-in-the-legacy-app).

**Rule:** a byte the user did not change is not rewritten — not on save, not on a class
change, not in a bulk edit.

## Reading

- Read bytes and decode with `surrogateescape`, then split with
  `splitlines(keepends=True)` so each line keeps its own terminator:
  `src/deeplabeling/core/labelio.py::parse_label_bytes`. With `surrogateescape` the round
  trip is exact for any bytes; the legacy reader's `errors="replace"`
  (`legacy/yolo_labeling/core/labelio.py::read_label_file`) turned a byte that is not
  UTF-8 into U+FFFD, which the next write then kept.
- Never read a file you will write back with text-mode `readlines()` or `read_text()`:
  universal-newline translation destroys CRLF on **every** line of the file, not just the
  edited one.
- The legacy reader returns `[]` for a missing file and for an empty one alike.

**Rule:** the reader keeps terminators, and reports a missing file differently from an
empty one ([why](#empty-file-is-a-negative-sample)).

## Writing

- **Atomic.** Write a temporary file in the target's directory, flush, `fsync`, then
  `os.replace` it over the target; on any failure delete the temporary file and leave the
  original untouched. A crash leaves the old file or the new one, never a truncated one:
  `legacy/yolo_labeling/core/labelio.py::write_label_file`. It opens with `newline=""`, so
  terminators pass through untranslated.
- **Permissions kept.** The replacement keeps the target's permission bits, and a new
  file gets `0o666` less the umask: `src/deeplabeling/core/atomic.py::write_atomic`. A
  bare `mkstemp` creates `0600`, as the legacy writer's did
  ([legacy-defects.md](legacy-defects.md#not-fixed-in-the-legacy-app)).
- **Line endings.** A re-serialised line keeps a CRLF ending, and an appended line uses
  the file's last line ending (`src/deeplabeling/core/edits.py::materialize`), so a CRLF
  file stays CRLF.
- **Trailing newline.** Every line the writer emits ends with a newline, or the next line
  appended later runs into it. A dirty line always gets `\n`; a spliced class change adds
  one to a last line that had none. An untouched last line without a terminator stays
  byte-identical only while it stays last: anything appended after it must give it its
  newline first.
- **Clamped.** Coordinates converted from pixels are clamped to [0, 1]
  (`legacy/yolo_labeling/core/geometry.py::pixel_to_yolo`).

**Rule:** one write function does all of the above, and it is the only code that writes a
label file.

## Empty file is a negative sample

- An empty `.txt` says "this image has no objects" — a valid negative sample. A missing
  `.txt` says "not labelled yet". Deleting an emptied file flips one meaning into the other
  and cannot be undone.
- Evidence: the legacy main save and the review's delete-line writer both write zero bytes
  when the last box goes (`legacy/yolo_labeling/app.py::YOLOLabelingTool.save_labels`,
  `legacy/yolo_labeling/app.py::YOLOLabelingTool._delete_label_line`).

**Rule:** an emptied label file is written as zero bytes, never deleted. Only an explicit
"delete this image" removes a label file.

## Locate before writing

Anything that records a line to act on later — a scan finding, a review entry — stores the
line's class and normalised box with its line index. Before writing, re-locate the line
(`legacy/yolo_labeling/core/labelio.py::locate_line`):

1. the recorded index is a hint, checked first (O(1); it is nearly always right);
2. otherwise search for a parsed line with the same class **and** every box coordinate
   within `legacy/yolo_labeling/core/labelio.py::LOCATE_TOL` (0.002, normalised — saving
   through integer pixels moves coordinates slightly);
3. exactly one match is the line; none or several is a refusal.

- Class **and** box: geometry alone would relocate onto a box of another class drawn on
  the same object — the error the overlap filter's different-class scope exists to find
  ([matching.md](matching.md#overlap-between-labels)).
- Refuse when several lines match: `GAUNTLET` has three identical class-0 boxes, so "take
  the first match" would be a coin flip written to disk.
- Why indices go stale: deleting a sibling shifts every line below it; a save renumbers
  around lines it could not parse; and a stored index is a **file** line number while the
  editor's box list skips unparsed lines, so the two diverge at the first blank or
  malformed line (`legacy/yolo_labeling/app.py::YOLOLabelingTool._label_box_index_for_line`).
- The legacy review flags a refused entry on its selection line, because the status bar is
  overwritten every 150 ms while a scan streams.

**Rule:** never trust a stored line index. Locate by class and box; refuse, visibly, if the
line is gone or ambiguous.

## One path resolver

- One rule maps an image to its label file, and reading and writing use the same one.
  DeepLabeling's is training's own (ultralytics' `img2label_paths`): the last `images`
  folder in the path becomes `labels` and the extension `.txt`, which leaves the `.txt`
  beside an image with no `images` folder in its path:
  `src/deeplabeling/core/paths.py::training_label_path`.
  A folder launch with an explicit label folder uses `<folder>/<stem>.txt`; a folder
  launch with neither is refused, never guessed
  ([app design](../design/2026-10-04-app-foundation.md#dataset)).
- The legacy resolver (`legacy/yolo_labeling/core/paths.py::LabelPathResolver`) tried an
  explicit folder, then the longest yaml folder mapping, then convention with fallbacks.
  On pvn-vehicle it agrees with training's rule for every image (measured 2026-10-04;
  the command is in the [app design](../design/2026-10-04-app-foundation.md#dataset)).
- In the legacy resolver, prefix matching respects path boundaries
  (`legacy/yolo_labeling/core/paths.py::is_within`), and the most specific (longest)
  mapping wins, not dict order.
- Why one: when reading and writing resolve differently — with images in a folder not
  named `images`, load once read `<parent>/../labels` while save created
  `<parent>/labels` — the tool reads its own shadow copy while the real dataset silently
  diverges.

**Rule:** every producer and consumer of a label path calls the one resolver; nothing
matches paths with `str.startswith`.

## Testing bulk edits

The only-these-files-changed assertion: hash every `.txt` under the dataset root before and
after the operation, and assert that the set of changed files (added, removed or modified)
equals the intended set — `set()` when nothing may be written:
`legacy/yolo_labeling/tests/fixtures.py::assert_only_changed` (with
`legacy/yolo_labeling/tests/fixtures.py::snapshot`).

Nearly every data-loss bug in the legacy app was "a file changed that nobody asked to
change".

**Rule:** every test of navigation, filtering, review, reassignment, import, merge or any
bulk edit makes this assertion.
