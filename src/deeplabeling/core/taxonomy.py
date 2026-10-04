"""The taxonomy guard (docs/design/2026-10-04-app-foundation.md#dataset): one set of
label files can be read under more than one yaml, and only one of them is right."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .dataset import Dataset
from .store import LabelStore


@dataclass(frozen=True)
class OutOfRange:
    """Boxes whose class id the dataset's names do not cover."""

    boxes: int = 0
    images: int = 0
    ids: tuple[int, ...] = ()

    def message(self, dataset: Dataset) -> str:
        if not self.boxes:
            return ""
        shown = ", ".join(map(str, self.ids[:5])) + (", …" if len(self.ids) > 5 else "")
        return (f"{self.boxes} boxes in {self.images} images have class ids ({shown}) that "
                f"{dataset.source.name} does not name. Is it the right yaml for these labels?")


def count_out_of_range(dataset: Dataset, store: LabelStore,
                       cancelled: Callable[[], bool] = lambda: False) -> OutOfRange | None:
    """Read every image's labels through `store` -- warming its cache -- and count the
    boxes the names do not cover. None when cancelled. With no names, none are."""
    if not dataset.names:
        return OutOfRange()
    boxes = images = 0
    ids: set[int] = set()
    for entry in dataset.images:
        if cancelled():
            return None
        bad = [line.cls_id for _, line in store.get(entry.path).boxes
               if not dataset.known(line.cls_id)]
        if bad:
            boxes += len(bad)
            images += 1
            ids.update(bad)
    return OutOfRange(boxes, images, tuple(sorted(ids)))


def names_changed(last: list[str] | None, names: tuple[str, ...]) -> bool:
    """Whether a root last opened with `last` is now opened with other names."""
    return last is not None and tuple(last) != tuple(names)
