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
