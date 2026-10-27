"""Opening a dataset: the one funnel every launch path goes through
(docs/design/2026-10-04-app-foundation.md#state-and-settings)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .dataset import Dataset
from .dismissals import Dismissals
from .editor import Editor
from .history import History
from .imagesize import ImageSizes
from .predstore import STORE_NAME, PredictionStore
from .review import ReviewMarks
from .sharpstore import SHARP_NAME, SharpnessStore
from .settings import JsonFile, Settings, define, is_str_list, is_str_map, is_str_or_none
from .state import DatasetLock, dataset_state_dir
from .store import LabelStore
from .taxonomy import names_changed

TAXONOMY_NAMES = define("taxonomy.names", "root", None, lambda v: v is None or is_str_list(v))
TAXONOMY_SOURCE = define("taxonomy.source", "root", "", lambda v: isinstance(v, str))
CLASS_COLORS = define("classes.colors", "root", {}, is_str_map)
CLASS_HOTKEYS = define("classes.hotkeys", "root", {}, is_str_map)
QUEUE_SOURCE = define("queue.source", "opening", None, lambda v: v is None or isinstance(v, dict))
QUEUE_CURSOR = define("queue.cursor", "opening", None, is_str_or_none)
ACTIVE_CLASS = define("classes.active", "opening", None, is_str_or_none)

#: (source last opened, its names, this source, these names) -> open anyway?
ConfirmTaxonomy = Callable[[str, list[str], str, tuple[str, ...]], bool]


class OpenCancelled(Exception):
    """The user chose not to open the dataset."""


@dataclass(eq=False)
class Workspace:
    dataset: Dataset
    directory: Path
    lock: DatasetLock
    file: JsonFile
    root_settings: Settings
    opening_settings: Settings
    review: ReviewMarks
    store: LabelStore
    history: History
    editor: Editor
    predictions: PredictionStore
    dismissals: Dismissals
    sharpness: SharpnessStore
    sizes: ImageSizes = field(default_factory=ImageSizes)   #: its images' sizes, read from headers

    @classmethod
    def open(cls, source, labels=None, *, confirm_taxonomy: ConfirmTaxonomy,
             on_labels_changed: Callable[[tuple[Path, ...]], None] | None = None,
             on_history_changed: Callable[[], None] | None = None,
             on_reload: Callable[[Path], None] | None = None) -> Workspace:
        """Open a dataset for editing. Raises DatasetError, Locked or OpenCancelled."""
        dataset = Dataset.open(source, labels)
        directory = dataset_state_dir(dataset.root)
        lock = DatasetLock(directory)
        lock.acquire()
        try:
            file = JsonFile(directory / "dataset.json")
            root = Settings(file, "root", ("root",))
            last = root.get(TAXONOMY_NAMES)
            if names_changed(last, dataset.names) and not confirm_taxonomy(
                    root.get(TAXONOMY_SOURCE), last, str(dataset.source), dataset.names):
                raise OpenCancelled(f"{dataset.source.name} was not opened")
            root.set(TAXONOMY_NAMES, list(dataset.names))
            root.set(TAXONOMY_SOURCE, str(dataset.source))
            file.save()
            review = ReviewMarks(directory / "review.json", dataset.root)
            store = LabelStore(dataset, on_reload=on_reload)
            history = History(store)
            editor = Editor(store, history, review, on_labels_changed=on_labels_changed,
                            on_history_changed=on_history_changed)
            predictions = PredictionStore(directory / STORE_NAME)
            dismissals = Dismissals(directory / "dismissals.json", dataset.root)
            sharpness = SharpnessStore(directory / SHARP_NAME)
        except BaseException:
            lock.release()
            raise
        return cls(dataset, directory, lock, file, root,
                   Settings(file, "opening", ("openings", dataset.opening_key)),
                   review, store, history, editor, predictions, dismissals, sharpness)

    @property
    def warnings(self) -> tuple[str, ...]:
        """State files that could not be read, for the notice strip."""
        return tuple(w for w in (self.file.warning, self.review.warning, self.predictions.warning,
                                 self.dismissals.warning, self.sharpness.warning) if w)

    def save(self) -> None:
        self.review.save()
        self.dismissals.save()
        self.file.save()

    def close(self) -> None:
        try:
            self.save()
        finally:
            self.predictions.close()
            self.sharpness.close()
            self.lock.release()
