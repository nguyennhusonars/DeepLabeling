---
name: run-and-verify-ui
description: How to launch DeepLabeling headless, drive it, screenshot it and assert what is actually visible. Use it for any change to the UI — layout, widgets, panels, dialogs, canvas drawing — and before claiming a UI change works; tests that only check widget state have passed while the feature was invisible to the user.
---

Read [CLAUDE.md](../../../CLAUDE.md) first — the landmines are there and are not repeated here.

- **Headless by default.** `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen` unless
  it is already set, so plain `pytest` needs no display. Use a real X server —
  `QT_QPA_PLATFORM=xcb xvfb-run -a pytest ...` — only when you need to watch the window
  yourself, or you suspect offscreen rendering itself is the problem.
- **Build widgets the way pytest-qt expects.** `qtbot.addWidget(widget)` right after
  creating it, then `qtbot.waitUntil(lambda: widget.isVisible())` (or whatever condition
  actually matters) instead of a sleep — a widget can sit through several event-loop
  turns before it is shown.
- **Screenshot it.** `widget.grab().save(path)` produces a real PNG even offscreen.
  Open that PNG and look at it; do not assume it shows what you intended.
- **Assert geometry, not only state.** Reading a value out of a widget or its backing
  model can pass while the widget itself is invisible: zero height, outside its parent's
  bounds, or drawn on top of a sibling. Assert that the widget is visible, that its
  geometry is non-zero and inside the window, and that it does not overlap the widgets
  around it.
- **Evidence for a UI fix is a screenshot or a geometry assertion.** Reporting a UI
  change as working without one of these is not verification — it is a guess.

Lessons from building the viewer (plan 1b):

- **Window shortcuts need the active window.** `with qtbot.waitActive(window): window.show();
  window.activateWindow()` before `qtbot.keyClick`. A synthetic `?` is `Qt.Key_Question`
  with no modifier; a real keyboard reports both forms, a synthetic event only the one sent.
- **`qtbot.waitUntil` wants a bool**: `lambda: bool(items)`, not `lambda: items`.
- **Hold the parent.** A host widget only handed to `qtbot.addWidget` was collected with its
  children mid-test; keep it alive in the fixture (`yield` inside it).
- **A child added to a visible layout is shown on a later event.** Call its `show()`, or
  wait for `isVisible()`, before asserting on it.
- **Read pixels near a line, not on it.** A 2 px cosmetic line on a pixel boundary is
  antialiased across two pixels: sample a small neighbourhood
  (`tests/ui/test_canvas.py::near`).
- **Never name a widget attribute after a QWidget method.** `self.size = QLabel()` broke
  `widget.size()` for everything that measured the widget.
- **A slow UI is profiled, not guessed.** `cProfile` around the action; work done per batch
  in a slot on a growing queue was the culprit last time (see the spec's performance table).

Lessons from building editing (plan 1c):

- **A script outside `tests/` runs on the real display.** Only `tests/conftest.py` sets
  offscreen: a spike run from elsewhere opened on `:0`, where synthetic keys never reached
  the window and every shortcut looked broken. Set `QT_QPA_PLATFORM=offscreen` yourself.
- **Drive the canvas with `tests/ui/drive.py`**: `drag` and `click` take scene (image
  pixel) points and send real mouse events to the viewport.
- **Sample a box edge between its handles.** A selected box's handles sit on its corners
  and edge midpoints and are drawn white over the edge.

Lessons from building the grid (plan 1d):

- **A 15-item fixture hides what 45k items show.** Switching to the grid with the cursor
  mid-queue left it a million pixels out of view, and finding the tiles in view cost 60 ms
  a call during the switch; neither showed in the fixture. Run a UI change on the real
  dataset (`tools/measure_ui.py`, read-only) before calling it done.
- **A list view scrolls by the layout it has.** After changing its flow or grid size, call
  `doItemsLayout()` before `scrollTo()`; and `setCurrentIndex` to the current index
  scrolls nowhere, so scroll explicitly.
- **A painter clip outlives the drawing it was for.** Wrap a clipped part of a delegate's
  paint in `save()`/`restore()`, or everything painted after it is clipped too.
