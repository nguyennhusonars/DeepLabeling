# Environment

Owns: the Python environment, which `ultralytics` gets imported, the OpenCV and setuptools
installs, and disk space.

## Python

- conda base (`/home/sonnn/miniconda3`): Python 3.10.12, PySide6 6.6.0, pytest-qt
  (2026-10-02; check with `python3 --version` and `pip show PySide6 pytest-qt`).
- A shell can have another conda env active: in the 2026-10-04 session bare `python3` was
  the `insightface` env, which has no PySide6. Use base's interpreter,
  `/home/sonnn/miniconda3/bin/python3`, or `conda activate base` first.
- Nothing of this project is installed into it: `run.sh` sets `PYTHONPATH=src`, and pytest
  takes `pythonpath = ["src"]` from [pyproject.toml](../../pyproject.toml). Never
  `pip install -e .` here.
- Other conda envs exist (`conda env list`); none is used here.
- `imghdr` was removed in Python 3.13; never use it. The legacy replacement,
  `legacy/yolo_labeling/core/imagetype.py::sniff`, reproduces 3.10's rules on purpose —
  its JPEG rule knows JFIF/Exif headers only; 3.11 added a bare-DQT form.

## PySide6 and NumPy

- Any PySide6 import (it loads `shiboken6`) prints "A module that was compiled using NumPy
  1.x cannot be run in NumPy 2.2.6 as it may crash": PySide6 6.6.0's shiboken6 was built
  against NumPy 1.x, and base has NumPy 2.2.6.
- Verified 2026-10-02: exit codes are unaffected so far. NumPy↔Qt conversions are where a
  crash would show. Upgrading PySide6 is the app design's call.

## Which ultralytics gets imported

- `import ultralytics` resolves to the editable install `/home/sonnn/Documents/ultralytics`
  (8.4.129 on 2026-10-02) — except when the launch directory is
  `/home/sonnn/Documents/ultralytics_sonnn`. `python3 -m …` and `python3 -c …` put the
  launch directory first on `sys.path`, and that checkout's own `ultralytics/` package
  shadows the editable install. `run.sh` uses `python3 -m`.
- Check which one a directory would load **without importing it** (`find_spec` does not
  run the package, so it cannot touch the settings file):

```sh
python3 -c "import importlib.util as u; print(u.find_spec('ultralytics').origin)"
```

- Models trained with fork-only modules need that fork importable: `ultralytics_sonnn`
  changed the Attention block (its commit `ab38b2253`).
- Importing ultralytics from a different checkout rewrites
  `~/.config/Ultralytics/settings.json`. On 2026-10-02 that turned `runs_dir` and
  `weights_dir` into absolute paths under `ultralytics_sonnn` and changed `datasets_dir`.
  The only backup, `~/.config/Ultralytics/settings.json.bak`, is from 2026-08-26; the user
  chose not to restore it.
- The legacy app imported ultralytics (and matplotlib) lazily, at the point of use, which
  kept its own package import at about 0.1 s instead of 1.6 s.

**Rule:** import ultralytics lazily, only to load a model, and know which checkout the
launch directory resolves to before importing it.

## OpenCV

- One `cv2` directory in base's site-packages is claimed by two distributions,
  `opencv-python` 5.0.0.93 and `opencv-contrib-python` 4.7.0.72; both RECORD files list
  `cv2/__init__.py`. A third record, `opencv-contrib-python` 4.6.0.66, is a stale
  dist-info in the user site (`~/.local/lib/python3.10/site-packages`) whose `cv2/` files
  are gone — and it is the version `pip list` shows. `import cv2` loads 5.0.0. (All
  measured 2026-10-02.)
- Declaring `opencv-python` as a dependency does not reinstall it: pip sees it as
  satisfied.

**Rule:** trust `import cv2`, not `pip list`; never uninstall or upgrade one of these
distributions to fix another — they share files.

```sh
python3 -c "import cv2; print(cv2.__version__, cv2.__file__)"
```

## setuptools

- pip's metadata says setuptools 60.2.0 (`setuptools-60.2.0.dist-info`), while
  `import setuptools` loads 82.0.1 (a `setuptools-82.0.1-py3.10.egg-info` record in the same
  site-packages). Measured 2026-10-02.
- An editable install of a `pyproject.toml` project (PEP 660) needs setuptools ≥ 64. pip's
  metadata sees 60.2, so such an install relies on pip's build isolation, which downloads
  its own setuptools (network); `--no-build-isolation` would build with whichever
  setuptools imports — untested here. This project never needs either: nothing is
  installed.

## Disk

- The disk is about 99% full: 7.8 GB free on 2026-10-02. Check before anything large:
  `df -h /home/sonnn/Documents/PGit`.
- Hence the disk [landmine](../../CLAUDE.md#landmines): datasets and prediction caches are
  read in place, never copied.
