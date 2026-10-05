"""The class map: the model's class names onto the dataset's
(docs/design/2026-10-05-model-assist.md#the-class-map).

Kept by name on both sides, so the yamls of one root share it, and stored per model
class list, so two models with different classes never share one (the legacy app gave
every best.pt one map: docs/knowledge/legacy-defects.md). Predictions keep the model's
own ids; this map translates them on read (docs/knowledge/caches.md#store-raw-model-ids).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace

from .dataset import Dataset
from .settings import Settings, define


def _is_map_of_maps(v) -> bool:
    return isinstance(v, dict) and all(
        isinstance(k, str) and isinstance(m, dict)
        and all(isinstance(a, str) and (b is None or isinstance(b, str)) for a, b in m.items())
        for k, m in v.items())


#: {model class list, as JSON: {model class name: dataset class name or None}}
CLASS_MAPS = define("models.class_maps", "root", {}, _is_map_of_maps)


def normalize(name: str) -> str:
    """Names compare ignoring case, spaces, dashes and underscores: `Bus_M`, `bus m` and
    `busm` are one name (docs/knowledge/datasets.md#prediction-maps-and-class-groups)."""
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def _seed(name: str, dataset_names: Sequence[str]) -> str | None:
    key = normalize(name)
    return next((d for d in dataset_names if normalize(d) == key), None)  # the first wins


@dataclass(frozen=True)
class ClassMap:
    model_names: tuple[str, ...]            #: the model's classes, by id
    targets: tuple[str | None, ...]         #: the dataset class name each one maps to

    @property
    def key(self) -> str:
        return json.dumps(list(self.model_names))

    @classmethod
    def seeded(cls, model_names: Sequence[str], dataset_names: Sequence[str]) -> ClassMap:
        names = tuple(model_names)
        return cls(names, tuple(_seed(n, dataset_names) for n in names))

    def translate(self, model_cls: int, dataset: Dataset) -> int | None:
        """The dataset class id a model class id stands for, or None: unmapped, or mapped
        to a name this yaml does not have."""
        if not 0 <= model_cls < len(self.targets) or self.targets[model_cls] is None:
            return None
        return dataset.id_of(self.targets[model_cls])

    def with_target(self, model_cls: int, name: str | None) -> ClassMap:
        targets = list(self.targets)
        targets[model_cls] = name
        return replace(self, targets=tuple(targets))

    def to_json(self) -> dict[str, str | None]:
        return dict(zip(self.model_names, self.targets))


def load_class_map(settings: Settings, model_names: Sequence[str],
                   dataset_names: Sequence[str]) -> ClassMap:
    """The stored map for this model class list; a class it does not cover is seeded by
    name, and an entry for a class the model lacks is dropped."""
    seeded = ClassMap.seeded(model_names, dataset_names)
    stored = settings.get(CLASS_MAPS).get(seeded.key)
    if stored is None:
        return seeded
    return replace(seeded, targets=tuple(stored[n] if n in stored else t
                                         for n, t in zip(seeded.model_names, seeded.targets)))


def save_class_map(settings: Settings, cmap: ClassMap) -> None:
    settings.set(CLASS_MAPS, {**settings.get(CLASS_MAPS), cmap.key: cmap.to_json()})
