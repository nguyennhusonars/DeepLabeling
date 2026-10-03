---
name: legacy-reference
description: Where each feature of the old Tkinter app (legacy/yolo_labeling) lives, which of its behaviours were defects, and which of its tests pin what. Use it when porting a feature, designing one the old app had, or answering how the old app did something — so the port copies the fix and not the defect.
---

Read [CLAUDE.md](../../../CLAUDE.md) first — the landmines are there and are not repeated here.

Feature → module, all under `legacy/yolo_labeling/`:

| Feature | Module |
|---|---|
| Main window: load/save labels, navigation, display, model loading | `app.py` |
| Label I/O | `core/labelio.py` |
| Paths | `core/paths.py` |
| Geometry | `core/geometry.py` |
| Class maps | `core/classmap.py` |
| Prediction cache | `core/predcache.py` |
| Matching | `core/badscan.py` |
| Ranges | `core/ranges.py` |
| Crops | `core/crops.py` |
| Review marks | `core/reviewmarks.py` |
| Caption drawing | `core/draw.py` |
| Image-format sniffing | `core/imagetype.py` |
| Filters | `ui/filters.py` |
| Find Bad and crop review | `ui/crop_review.py`, `ui/dialogs.py` |
| Classes and settings | `ui/classes.py` |
| Batch grid | `ui/batch.py` |
| Statistics | `ui/stats.py` |
| Session telemetry | `ui/session.py` |

Which of these behaviours were defects — and the fix each one implies for
DeepLabeling — is in [legacy-defects.md](../../../docs/knowledge/legacy-defects.md).
Read it before porting a feature from this list, or designing one the old app had, so
the port copies the fix and not the defect it replaced.

To find which tests pin a feature, search by module name, not feature name:
`grep -rn <module> legacy/yolo_labeling/tests`. The legacy suite is not run from here — it
pins the frozen snapshot, not DeepLabeling.
