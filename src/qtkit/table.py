"""A read-only, sortable Qt table over columns of numpy arrays."""

from __future__ import annotations

from typing import Any, Mapping, Optional

import numpy as np
from qtpy.QtCore import QAbstractTableModel, QModelIndex, Qt
from qtpy.QtWidgets import QAbstractItemView, QHeaderView, QSizePolicy, QTableView

from qtkit.filters import columns_of


def format_cell(value: Any) -> str:
    """Floats at 4 significant figures, missing values blank."""
    if value is None:
        return ""
    if isinstance(value, (float, np.floating)):
        return "" if np.isnan(value) else f"{value:.4g}"
    return str(value)


class ColumnTableModel(QAbstractTableModel):
    """Table model over ``{name: array}`` columns of equal length.

    Cells are read straight out of per-column numpy arrays, so a
    many-thousand-row table scrolls without converting the whole thing to
    Python objects up front. Sorting (`view.setSortingEnabled(True)`)
    reorders the arrays themselves with a stable argsort, missing values
    last, instead of juggling a proxy's row mapping.

    Load with `set_columns`, or `set_frame` for a polars/pandas frame."""

    def __init__(self, columns: Optional[Mapping[str, Any]] = None, parent=None) -> None:
        super().__init__(parent)
        self._names: list[str] = []
        self._arrays: list[np.ndarray] = []
        self._length = 0
        if columns:
            self.set_columns(columns)

    def set_columns(self, columns: Mapping[str, Any]) -> None:
        arrays = {name: np.asarray(values) for name, values in columns.items()}
        lengths = {len(a) for a in arrays.values()}
        if len(lengths) > 1:
            raise ValueError(f"columns have different lengths: {sorted(lengths)}")
        self.beginResetModel()
        self._names = list(arrays)
        self._arrays = list(arrays.values())
        self._length = lengths.pop() if lengths else 0
        self.endResetModel()

    def set_frame(self, frame) -> None:
        self.set_columns(columns_of(frame))

    def clear(self) -> None:
        self.set_columns({})

    # -- access ---------------------------------------------------------

    def column_names(self) -> list[str]:
        return list(self._names)

    def column(self, name: str) -> np.ndarray:
        """The named column in its current (possibly sorted) row order."""
        return self._arrays[self._names.index(name)]

    def row_dict(self, row: int) -> dict[str, Any]:
        return {name: array[row].item() if hasattr(array[row], "item") else array[row]
                for name, array in zip(self._names, self._arrays)}

    def find_row(self, name: str, value: Any) -> Optional[int]:
        """First row whose `name` column equals `value`, or None."""
        if name not in self._names:
            return None
        hits = np.flatnonzero(self.column(name) == value)
        return int(hits[0]) if hits.size else None

    # -- Qt model -------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else self._length

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._names)

    def headerData(self, section: int, orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self._names[section] if 0 <= section < len(self._names) else None
        return str(section)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        array = self._arrays[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return format_cell(array[index.row()])
        if role == Qt.ItemDataRole.TextAlignmentRole and np.issubdtype(array.dtype, np.number):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        if self._length == 0 or not 0 <= column < len(self._names):
            return
        key = self._arrays[column]
        descending = order == Qt.SortOrder.DescendingOrder
        if np.issubdtype(key.dtype, np.number):
            values = key.astype(np.float64)
            missing = np.isnan(values)
            values = np.where(missing, 0.0, -values if descending else values)
            # lexsort: last key is primary -- missing last, then value.
            permutation = np.lexsort((values, missing))
        else:
            as_text = np.array([format_cell(v) for v in key])
            permutation = np.argsort(as_text, kind="stable")
            if descending:
                permutation = permutation[::-1]
        self.layoutAboutToBeChanged.emit()
        self._arrays = [array[permutation] for array in self._arrays]
        self.layoutChanged.emit()


def table_view(model: QAbstractTableModel, column_width: int = 88, row_height: int = 18) -> QTableView:
    """A `QTableView` set up for a narrow panel: sortable, whole-row single
    selection, no row-number header, compact rows, fixed-width
    interactive columns (sizing 40 columns to their contents makes
    horizontal scrolling the only way to reach any of them), and willing
    to shrink to a couple of rows.

    Alternating rows are shaded with a translucent gray rather than a
    palette color. A host stylesheet that styles the table but not its
    alternate color (napari's) otherwise leaves Qt's default -- white
    stripes on a dark table -- and under a stylesheet the palette doesn't
    reliably report the real background to derive one from."""
    view = QTableView()
    view.setModel(model)
    view.setSortingEnabled(True)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    view.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    view.verticalHeader().setVisible(False)
    view.verticalHeader().setDefaultSectionSize(row_height)
    header = view.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(True)
    header.setDefaultSectionSize(column_width)
    view.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
    view.setMinimumHeight(3 * row_height + 4)

    view.setStyleSheet("QTableView { alternate-background-color: rgba(128, 128, 128, 28); }")
    view.setAlternatingRowColors(True)
    return view
