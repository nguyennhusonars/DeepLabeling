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
    chosen: tuple[bool, ...] = ()           #: which targets the user set; the rest are by name

    @property
    def key(self) -> str:
        return json.dumps(list(self.model_names))

    @classmethod
    def seeded(cls, model_names: Sequence[str], dataset_names: Sequence[str]) -> ClassMap:
        names = tuple(model_names)
        return cls(names, tuple(_seed(n, dataset_names) for n in names), (False,) * len(names))

    def translate(self, model_cls: int, dataset: Dataset) -> int | None:
        """The dataset class id a model class id stands for, or None: unmapped, or mapped
        to a name this yaml does not have."""
        if not 0 <= model_cls < len(self.targets) or self.targets[model_cls] is None:
            return None
        return dataset.id_of(self.targets[model_cls])

    def with_target(self, model_cls: int, name: str | None) -> ClassMap:
        """The user's choice for one model class: a dataset class name, or None, not mapped."""
        targets, chosen = list(self.targets), list(self.chosen or (False,) * len(self.targets))
        targets[model_cls], chosen[model_cls] = name, True
        return replace(self, targets=tuple(targets), chosen=tuple(chosen))

    def to_json(self) -> dict[str, str | None]:
        return dict(zip(self.model_names, self.targets))

    def choices(self) -> dict[str, str | None]:
        """Only what the user set: what is saved. The rest is matched by name again on
        every load, so another yaml of the root keeps its own matches."""
        return {n: t for n, t, c in zip(self.model_names, self.targets, self.chosen) if c}


def load_class_map(settings: Settings, model_names: Sequence[str],
                   dataset_names: Sequence[str]) -> ClassMap:
    """This model's map for this yaml: each class the user set keeps that choice -- unless
    it names a class this yaml lacks -- and every other class is matched by name. A stored
    entry for a class the model lacks is ignored."""
    seeded = ClassMap.seeded(model_names, dataset_names)
    stored = settings.get(CLASS_MAPS).get(seeded.key) or {}
    here = set(dataset_names)
    use = [n in stored and (stored[n] is None or stored[n] in here) for n in seeded.model_names]
    return replace(seeded,
                   targets=tuple(stored[n] if u else t for n, t, u in zip(seeded.model_names, seeded.targets, use)),
                   chosen=tuple(use))


def save_class_map(settings: Settings, cmap: ClassMap) -> None:
    """Save the user's choices, keeping those made on another yaml of the root."""
    maps = settings.get(CLASS_MAPS)
    settings.set(CLASS_MAPS, {**maps, cmap.key: {**maps.get(cmap.key, {}), **cmap.choices()}})
