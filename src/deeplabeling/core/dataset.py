"""A dataset: its images, their label files and its class names, found the way
training finds them (docs/design/2026-10-04-app-foundation.md#dataset)."""

from __future__ import annotations

import glob
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .paths import folder_label_path, training_label_path

#: The union of IMG_FORMATS in the editable ultralytics install and the training
#: fork, which differ: avif, heif and jp2 in one, pfm in the other.
IMG_FORMATS = frozenset({
    "avif", "bmp", "dng", "heic", "heif", "jp2", "jpeg", "jpg", "mpo", "pfm",
    "png", "tif", "tiff", "webp",
})
SPLITS = ("train", "val", "test")
#: The one split of a folder launch.
FOLDER_SPLIT = "images"


class DatasetError(Exception):
    """The dataset cannot be opened. The message is for the user."""


@dataclass(frozen=True)
class ImageEntry:
    path: Path        #: absolute, as training builds it
    label_path: Path
    split: str
    rel: str          #: the POSIX path under the root, or the absolute path outside it
    order: int        #: the position in dataset order


@dataclass(frozen=True, eq=False)
class Dataset:
    source: Path                        #: the yaml, or the image folder
    labels: Path | None                 #: a folder launch's explicit label folder
    root: Path                          #: the canonical root, a realpath
    names: tuple[str, ...]              #: class names by id; empty when unknown
    groups: dict[str, tuple[str, ...]]
    images: tuple[ImageEntry, ...]
    shared_labels: frozenset[Path]      #: label files more than one image resolves to
    missing: tuple[Path, ...]           #: listed folders or lists that do not exist
    _by_path: dict[Path, ImageEntry] = field(default_factory=dict, repr=False)
    _ids: dict[str, int] = field(default_factory=dict, repr=False)

    @classmethod
    def open(cls, source, labels=None) -> Dataset:
        """Open a dataset yaml, or an image folder with an optional label folder."""
        source = Path(source).expanduser().absolute()
        if source.is_file() and source.suffix.lower() in (".yaml", ".yml"):
            if labels is not None:
                raise DatasetError("a yaml says where its labels are; do not give a label folder too")
            return _from_yaml(source)
        if source.is_dir():
            return _from_folder(source, Path(labels).expanduser().absolute() if labels else None)
        raise DatasetError(f"not a dataset yaml or an image folder: {source}")

    @property
    def opening_key(self) -> str:
        """Tells apart the ways of opening one root: the yaml, or the folders."""
        return str(self.source) if self.labels is None else f"{self.source}|{self.labels}"

    @property
    def splits(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(e.split for e in self.images))

    def entry(self, image) -> ImageEntry:
        return self._by_path[Path(image)]

    def id_of(self, name: str) -> int | None:
        return self._ids.get(name)

    def known(self, cls_id: int) -> bool:
        """Whether a label may use `cls_id`; any id >= 0 when the names are unknown."""
        return cls_id >= 0 and (not self.names or cls_id < len(self.names))


def _from_yaml(path: Path) -> Dataset:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
        raise DatasetError(f"cannot read {path.name}: {e}") from e
    if not isinstance(data, dict):
        raise DatasetError(f"{path.name} is not a dataset yaml")
    base = Path(str(data["path"])).expanduser() if data.get("path") else path.parent
    if not base.is_absolute():
        base = path.parent / base
    names = _names(data, path.name)
    found: list[tuple[str, Path]] = []
    missing: list[Path] = []
    for split in SPLITS:
        listed = data.get(split)
        if not listed:
            continue
        files: list[str] = []
        for item in listed if isinstance(listed, list) else [listed]:
            where = (base / str(item)).resolve()
            got = _list_images(where)
            if got is None:
                missing.append(where)
            else:
                files += got
        found += [(split, Path(f)) for f in sorted(files)]
    if not found:
        raise DatasetError(f"{path.name} lists no images")
    return _build(path, None, base.resolve(), names, _groups(data), found, missing,
                  training_label_path)


def _from_folder(folder: Path, labels: Path | None) -> Dataset:
    folder = folder.resolve()
    if labels is None and "images" not in folder.parts:
        raise DatasetError(f"{folder} has no 'images' folder in its path, so where its labels "
                           "are cannot be worked out: give the label folder too")
    files = _list_images(folder) or []
    if not files:
        raise DatasetError(f"no images in {folder}")
    label_dir = labels or training_label_path(folder / "_.jpg").parent
    if labels:
        def label_of(image: Path) -> Path:
            return folder_label_path(image, folder, labels)
    else:
        label_of = training_label_path
    found = [(FOLDER_SPLIT, Path(f)) for f in sorted(files)]
    return _build(folder, labels, folder, _classes_txt(label_dir / "classes.txt"), {}, found, [],
                  label_of)


def _list_images(where: Path) -> list[str] | None:
    """Image files under a folder (recursively) or in a list file; None if neither exists."""
    if where.is_dir():
        files = glob.glob(os.path.join(glob.escape(str(where)), "**", "*.*"), recursive=True)
    elif where.is_file():
        files = []
        for line in where.read_text(encoding="utf-8").strip().splitlines():
            line = line.strip()
            if line.startswith("./"):
                line = str(where.parent) + os.sep + line[2:]
            files.append(line if os.path.isabs(line) else str(where.parent / line))
    else:
        return None
    return [f for f in files if f.rpartition(".")[-1].lower() in IMG_FORMATS]


def _names(data: dict, label: str) -> tuple[str, ...]:
    names = data.get("names")
    if isinstance(names, list):
        return tuple(str(n) for n in names)
    if isinstance(names, dict):
        try:
            by_id = {int(k): str(v) for k, v in names.items()}
        except (TypeError, ValueError) as e:
            raise DatasetError(f"{label}: a key under names is not a class id") from e
        return tuple(by_id.get(i, f"class_{i}") for i in range(max(by_id, default=-1) + 1))
    nc = data.get("nc")
    if isinstance(nc, int) and nc > 0:
        return tuple(f"class_{i}" for i in range(nc))
    raise DatasetError(f"{label} has neither names nor nc")


def _groups(data: dict) -> dict[str, tuple[str, ...]]:
    groups = data.get("groups")
    if not isinstance(groups, dict):
        return {}
    return {str(g): tuple(str(m) for m in members)
            for g, members in groups.items() if isinstance(members, list)}


def _classes_txt(path: Path) -> tuple[str, ...]:
    if not path.is_file():
        return ()
    return tuple(n.strip() for n in path.read_text(encoding="utf-8").splitlines() if n.strip())


def _build(source: Path, labels: Path | None, root: Path, names: tuple[str, ...],
           groups: dict[str, tuple[str, ...]], found: list[tuple[str, Path]],
           missing: list[Path], label_of: Callable[[Path], Path]) -> Dataset:
    entries: list[ImageEntry] = []
    by_path: dict[Path, ImageEntry] = {}
    users: dict[Path, int] = {}
    for split, image in found:
        if image in by_path:
            continue
        label = label_of(image)
        try:
            rel = image.relative_to(root).as_posix()
        except ValueError:
            rel = str(image)
        entry = ImageEntry(image, label, split, rel, len(entries))
        entries.append(entry)
        by_path[image] = entry
        users[label] = users.get(label, 0) + 1
    ids: dict[str, int] = {}
    for i, name in enumerate(names):
        ids.setdefault(name, i)
    return Dataset(source, labels, root, tuple(names), groups, tuple(entries),
                   frozenset(p for p, n in users.items() if n > 1), tuple(missing), by_path, ids)
