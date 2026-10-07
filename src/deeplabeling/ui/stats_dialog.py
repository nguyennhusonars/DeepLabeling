"""Statistics of this queue… (docs/design/2026-10-07-bulk-and-stats.md#statistics): computed
on a worker over the queue's images, shown as tables that copy as TSV and as four charts.

matplotlib (and numpy) are imported when the charts are first drawn, never at the app's start;
and the charts are drawn when their tab is shown, not when the numbers come in, so a
recompute never holds the window up for matplotlib.
"""

from __future__ import annotations

import time

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.stats import GRID, PER_IMAGE_MAX, SIZE_LABELS, stats_of
from .reassign_dialog import class_label
from .statsview import class_table, files_table, per_image_table, sizes_table, table_classes, tsv

TABLES = ("Classes", "Label files", "Box sizes", "Boxes per image")
ALL = "all classes"


class StatsDialog(QDialog):
    def __init__(self, session, prompter, parent=None):
        super().__init__(parent)
        self._session, self._prompter = session, prompter
        ws = session.workspace
        self._names = ws.dataset.names
        self.setWindowTitle(f"Statistics — {session.queue.source.describe(ws.dataset)}")
        self.stats = None
        self._job = None
        self.drawn_class: int | None = None         #: the class the size and centre charts show; None: all
        self.drawn_for = None                       #: the stats the charts were drawn from
        self.status = QLabel()
        self.tabs = QTabWidget()
        self.tables: dict[str, QTableWidget] = {}
        self._shown: dict[str, tuple] = {}          #: each table's (header, rows), as copied
        for name in TABLES:
            table = QTableWidget()
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.tables[name] = table
            self.tabs.addTab(table, name)
        self.charts = QWidget()
        self.chart_class = QComboBox()
        self.chart_class.currentIndexChanged.connect(lambda _: self._draw_if_shown(again=True))
        self.canvas = None                          #: the matplotlib canvas, once drawn
        self._chart_layout = QVBoxLayout(self.charts)
        row = QHBoxLayout()
        row.addWidget(QLabel("Class"))
        row.addWidget(self.chart_class, 1)
        self._chart_layout.addLayout(row)
        self.tabs.addTab(self.charts, "Charts")
        self.tabs.currentChanged.connect(self._tab_shown)
        self.copy_button, self.recompute_button = QPushButton("Copy"), QPushButton("Recompute")
        self.save_button = QPushButton("Save charts…")
        self.copy_button.clicked.connect(self.copy)
        self.recompute_button.clicked.connect(self.recompute)
        self.save_button.clicked.connect(self.save_charts)
        QShortcut(QKeySequence.Copy, self, self.copy)
        buttons = QHBoxLayout()
        for button in (self.copy_button, self.recompute_button, self.save_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(buttons)
        session.closed.connect(self.close)         # its labels are the dataset's
        self.recompute()

    # -- computing -------------------------------------------------------------------------

    def recompute(self) -> None:
        """Read the queue's images again, on a worker; the tables and charts follow."""
        if self._job is not None:
            self._job.cancel()
        session = self._session
        why = session.queue_not_whole()
        if why:
            self.status.setText(why)                # the last numbers stay; nothing of part of a queue
            return
        ws, entries = session.workspace, session.queue_images()
        self.setWindowTitle(f"Statistics — {session.queue.source.describe(ws.dataset)}")
        store, sizes = ws.store, ws.sizes
        self.status.setText(f"reading 0 / {len(entries):,}")
        token = []
        job = session.io.start(
            lambda emit, cancelled: stats_of(entries, store.get, sizes.get, cancelled,
                                             progress=lambda done, total: emit((done, total))),
            batch=lambda told: self._told(token, told),
            done=lambda stats: self._done(token, stats),
            failed=lambda why: self._failed(token, why))
        token.append(job)
        self._job = job

    def _told(self, token, told) -> None:
        if token and token[0] is self._job:
            self.status.setText(f"reading {told[0]:,} / {told[1]:,}")

    def _done(self, token, stats) -> None:
        if not token or token[0] is not self._job:
            return                                  # cancelled, or recomputed since
        self._job = None
        if stats is None:
            return
        self.stats = stats
        images = sum(stats.files[(split, "images")] for split in stats.splits)
        self.status.setText(f"{images:,} images · computed {time.strftime('%H:%M')}" if images else "no images")
        self._fill()

    def _failed(self, token, why: str) -> None:
        if token and token[0] is self._job:
            self._job = None
            self.status.setText(f"the statistics could not be computed: {why}")

    def closeEvent(self, event) -> None:
        if self._job is not None:
            self._job.cancel()
            self._job = None
        super().closeEvent(event)

    # -- showing ---------------------------------------------------------------------------

    def _fill(self) -> None:
        stats, names = self.stats, self._names
        for name, (header, rows) in zip(TABLES, (class_table(stats, names), files_table(stats),
                                                 sizes_table(stats, names), per_image_table(stats))):
            self._shown[name] = (header, rows)
            table = self.tables[name]
            table.clear()
            table.setColumnCount(len(header))
            table.setRowCount(len(rows))
            table.setHorizontalHeaderLabels(header)
            for r, row in enumerate(rows):
                for c, text in enumerate(row):
                    table.setItem(r, c, QTableWidgetItem(text))
            table.resizeColumnsToContents()
        chosen = self.chart_class.currentData()
        self.chart_class.blockSignals(True)
        self.chart_class.clear()
        self.chart_class.addItem(ALL, None)
        for cls in table_classes(stats, names):
            self.chart_class.addItem(class_label(cls, names), cls)
        self.chart_class.setCurrentIndex(max(self.chart_class.findData(chosen), 0))    # a recompute keeps it
        self.chart_class.blockSignals(False)
        self._draw_if_shown()

    def copy(self) -> None:
        """The table on show, as TSV."""
        table = self.tabs.currentWidget()
        name = next((n for n, t in self.tables.items() if t is table), None)
        if name in self._shown:
            QApplication.clipboard().setText(tsv(*self._shown[name]))

    def _tab_shown(self, _=None) -> None:
        self.copy_button.setEnabled(self.tabs.currentWidget() is not self.charts)
        self._draw_if_shown()

    def _draw_if_shown(self, again: bool = False) -> None:
        """Draw the charts if their tab is on show and they are not drawn from these numbers."""
        if self.tabs.currentWidget() is self.charts and (again or self.drawn_for is not self.stats):
            self._draw()

    def _empty(self) -> bool:
        stats = self.stats
        return stats is None or not any(stats.files[(split, "images")] for split in stats.splits)

    def _draw(self) -> None:
        stats = self.stats
        if self._empty():
            if self.canvas is not None:
                self.canvas.hide()                  # no numbers: no charts of the last ones
            return
        import numpy as np
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure

        if self.canvas is None:
            self.canvas = FigureCanvasQTAgg(Figure(figsize=(9, 6), layout="constrained"))
            self._chart_layout.addWidget(self.canvas, 1)
        self.canvas.show()
        cls = self.chart_class.currentData()
        self.drawn_class, self.drawn_for = cls, stats
        figure, names = self.canvas.figure, self._names
        figure.clear()
        balance, sizes, centres, per_image = figure.subplots(2, 2).flat
        classes = table_classes(stats, names)
        x = np.arange(len(classes))
        width = 0.8 / max(len(stats.splits), 1)
        for i, split in enumerate(stats.splits):
            balance.bar(x + i * width, [stats.boxes[(split, c)] for c in classes], width, label=split)
        balance.set_xticks(x + width * (len(stats.splits) - 1) / 2, [class_label(c, names) for c in classes],
                           rotation=45, ha="right")
        balance.set_title("Class balance")
        balance.legend()
        chosen = classes if cls is None else [cls]
        counts = [sum(stats.sizes[(c, b)] for c in chosen) for b in range(len(SIZE_LABELS))]
        sizes.bar(range(len(SIZE_LABELS)), counts)
        sizes.set_xticks(range(len(SIZE_LABELS)), SIZE_LABELS, rotation=45, ha="right")
        if any(counts):                             # a log axis of nothing but zeros has no range
            sizes.set_yscale("log", nonpositive="clip")
            sizes.set_ylim(bottom=0.5)              # a bucket of one box still shows its bar
        sizes.set_title("Box sizes, √(w·h) px")
        grid = np.zeros((GRID, GRID))
        for (c, gx, gy), n in stats.centres.items():
            if c in chosen:
                grid[gy, gx] += n
        centres.imshow(grid, cmap="viridis", extent=(0, 1, 1, 0))
        centres.set_title("Box centres")
        per_image.bar(range(PER_IMAGE_MAX + 1), [stats.per_image[n] for n in range(PER_IMAGE_MAX + 1)])
        per_image.set_title(f"Boxes per image ({PER_IMAGE_MAX} = {PER_IMAGE_MAX} or more)")
        self.canvas.draw()

    def save_charts(self) -> None:
        if self._empty():
            return
        if self.drawn_for is not self.stats:
            self._draw()                            # saved as they would show
        path = self._prompter.choose_save_path("Save charts", "PNG image (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        try:
            self.canvas.figure.savefig(path, dpi=100)
        except OSError as e:
            self._prompter.error("Could not save the charts", str(e))
