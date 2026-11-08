"""A stack of histogram range filters over one table's numeric columns.

One filter is one row: pick a column, see its distribution, drag two
handles across it. Rows AND together. This is the "filter" step of the
detect -> filter -> finalize flow Imaris and TrackMate use, and works the
same over any table: detections, per-track metrics, fit results, shape
properties.

A filter is described by a `FilterSpec`, a plain
``{column: (lo, hi)}`` dict where either side may be ``None`` for "no bound
on this side". It is plain data on purpose, so a range dragged here, one
read back from a saved file, and one typed into a config are the same
object, and applying it (`filter_mask`) needs no Qt.

A handle left at (or beyond) its column's data extreme means *unbounded*
on that side, so a row that hasn't been moved is not a filter and is left
out of the spec -- rather than recorded as a cut that was never made. This
replaces explicit "No Min"/"No Max" checkboxes: dragging a handle off the
edge bounds that side, and the reset button (or dragging it back) unbounds
it.

Sources are ``Mapping[str, array]`` -- a dict of numpy arrays, or anything
`columns_of` can turn into one (polars and pandas frames).
"""

from __future__ import annotations

from typing import Iterable, Mapping, Optional, Sequence

import numpy as np
from qtpy.QtCore import Signal
from qtpy.QtWidgets import QComboBox, QHBoxLayout, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from qtkit.histogram import HistogramRangeWidget
from qtkit.layouts import wrapping_label

Bound = Optional[float]
FilterSpec = dict[str, tuple[Bound, Bound]]
Columns = Mapping[str, np.ndarray]


def columns_of(frame, names: Optional[Iterable[str]] = None) -> dict[str, np.ndarray]:
    """``{name: numpy array}`` for `names` (default: every column) of a
    dataframe-like `frame` -- anything with ``.columns`` and
    ``frame[name].to_numpy()``, which polars and pandas both are."""
    names = list(frame.columns) if names is None else list(names)
    return {name: np.asarray(frame[name].to_numpy()) for name in names}


def n_rows(columns: Columns) -> int:
    return len(next(iter(columns.values()))) if columns else 0


def filter_mask(columns: Columns, spec: Optional[FilterSpec], length: Optional[int] = None) -> np.ndarray:
    """Per-row boolean: does the row pass every cut in `spec`?

    Inclusive at both ends; ANDed across columns; a ``None`` side is
    unbounded. A missing or non-finite value fails any bounded side of
    its column. A column the table doesn't have is skipped rather than
    failing everything, since a spec can outlive the table it was drawn
    on. `length` gives the row count when `columns` is empty."""
    length = n_rows(columns) if length is None else length
    mask = np.ones(length, dtype=bool)
    for name, (lo, hi) in (spec or {}).items():
        if name not in columns or (lo is None and hi is None):
            continue
        values = np.asarray(columns[name], dtype=np.float64)
        with np.errstate(invalid="ignore"):
            if lo is not None:
                mask &= values >= lo
            if hi is not None:
                mask &= values <= hi
    return mask


def numeric_columns(columns: Columns, skip: Iterable[str] = ()) -> list[str]:
    """The columns a range filter can sensibly go on: numeric, not in
    `skip` (identity/coordinate columns, typically), and not constant -- a
    column with one distinct value has no distribution to look at."""
    skip = set(skip)
    out = []
    for name, values in columns.items():
        values = np.asarray(values)
        if name in skip or not (np.issubdtype(values.dtype, np.number) or values.dtype == bool):
            continue
        finite = values[np.isfinite(values.astype(np.float64))]
        if finite.size and finite.min() != finite.max():
            out.append(name)
    return out


def intersect(a: tuple[Bound, Bound], b: tuple[Bound, Bound]) -> tuple[Bound, Bound]:
    """The tighter of two ranges, side by side; None only if both are."""
    lo = max((v for v in (a[0], b[0]) if v is not None), default=None)
    hi = min((v for v in (a[1], b[1]) if v is not None), default=None)
    return lo, hi


class FilterRow(QWidget):
    """One column's histogram and handles, with the column re-pickable in
    place -- a row looking at the wrong feature is re-pointed rather than
    removed and re-added.

    The "log" button in the header switches this row's histogram to
    log-spaced bins -- for a column spanning orders of magnitude, where
    linear bins are one spike at the low end. It is a view of the data,
    not part of the cut: a bounded side keeps its value, an unbounded side
    stays unbounded. It is offered per row because whether log helps is a
    property of the column; a tight distribution reads better linear."""

    changed = Signal()
    committed = Signal()
    removeRequested = Signal(object)
    # (column, enabled) when the user toggles "log" -- not from
    # `set_log_scale`.
    logScaleToggled = Signal(str, bool)
    # The user picked another column (after the row re-pointed itself,
    # before `changed`/`committed`), so the owner can restore that
    # column's view settings first.
    columnChanged = Signal(str)

    def __init__(self, columns: Sequence[str], column: Optional[str] = None) -> None:
        super().__init__()
        self._source: Columns = {}
        # Suppresses signals while handles move programmatically, so a
        # repoint or data refresh never reads as a user's cut.
        self._loading = False

        self._column_picker = QComboBox()
        self._column_picker.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._column_picker.addItems(list(columns))
        if column in columns:
            self._column_picker.setCurrentText(column)
        self._column_picker.currentTextChanged.connect(self._on_column_changed)

        self._reset_button = QPushButton("⤢")
        self._reset_button.setFixedWidth(24)
        self._reset_button.setToolTip("Unbound both sides (no cut)")
        self._reset_button.clicked.connect(self._on_reset)

        self._remove_button = QPushButton("✕")
        self._remove_button.setFixedWidth(24)
        self._remove_button.setToolTip("Remove this filter")
        self._remove_button.clicked.connect(lambda: self.removeRequested.emit(self))

        # A checkable button rather than a checkbox: it sits with the
        # row's other small header buttons and costs no extra line.
        self._log_button = QPushButton("log")
        self._log_button.setCheckable(True)
        self._log_button.setFixedWidth(32)
        self._log_button.setToolTip(
            "Log-spaced bins, for a column spanning orders of magnitude.\n"
            "Changes the view only; values <= 0 aren't drawn but still pass\n"
            "an unbounded lower side."
        )
        self._log_button.toggled.connect(self._on_log_toggled)

        self.histogram = HistogramRangeWidget()
        self.histogram.rangeChanged.connect(self._on_range_changed)
        self.histogram.rangeCommitted.connect(self._on_range_committed)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(2)
        head.addWidget(self._column_picker, 1)
        head.addWidget(self._log_button)
        head.addWidget(self._reset_button)
        head.addWidget(self._remove_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(2)
        layout.addLayout(head)
        layout.addWidget(self.histogram)

    def column(self) -> str:
        return self._column_picker.currentText()

    def set_columns(self, columns: Sequence[str]) -> None:
        """Re-offer the column list, staying on the current column if it
        survived."""
        current = self.column()
        blocked = self._column_picker.blockSignals(True)
        self._column_picker.clear()
        self._column_picker.addItems(list(columns))
        if current in columns:
            self._column_picker.setCurrentText(current)
        self._column_picker.blockSignals(blocked)

    def set_source(self, columns: Columns, keep_bounds: bool = True) -> None:
        """Point the row at a table. `keep_bounds` holds the cut where it
        is -- a bounded side keeps its value, an unbounded side stays
        unbounded against the new data's extreme -- as when the same table
        was recomputed; otherwise both sides are unbounded."""
        previous = self.bounds() if keep_bounds else (None, None)
        self._source = columns
        column = self.column()
        if column not in columns:
            return
        self._loading = True
        self.histogram.set_data(columns[column])
        self._loading = False
        self.set_bounds(*previous)
        self._update_log_button()

    def log_scale(self) -> bool:
        return self.histogram.log_scale()

    def set_log_scale(self, enabled: bool) -> None:
        """Switch the histogram's bins between linear and log10, keeping
        the cut (see the class docstring). Silent. Ignored (stays
        linear) for a column with no positive values."""
        enabled = enabled and self._log_button.isEnabled()
        self._apply_log_scale(enabled)
        blocked = self._log_button.blockSignals(True)
        self._log_button.setChecked(enabled)
        self._log_button.blockSignals(blocked)

    def _apply_log_scale(self, enabled: bool) -> bool:
        """Re-bin, then put the cut back. Returns whether the cut moved:
        a side bounded at <= 0 has nowhere to sit on a log axis, so it
        comes back unbounded."""
        if enabled == self.histogram.log_scale():
            return False
        previous = self.bounds()
        self._loading = True
        self.histogram.set_log_scale(enabled)
        self._loading = False
        lo, hi = previous
        if enabled:
            lo = None if lo is not None and lo <= 0 else lo
            hi = None if hi is not None and hi <= 0 else hi
        self.set_bounds(lo, hi)
        return self.bounds() != previous

    def _update_log_button(self) -> None:
        """Log bins need positive values; a column with none offers no
        log view (and drops one it had)."""
        values = self._source.get(self.column()) if self._source else None
        has_positive = values is not None and bool(np.any(np.asarray(values, dtype=np.float64) > 0))
        self._log_button.setEnabled(has_positive)
        if not has_positive and self.log_scale():
            self.set_log_scale(False)

    def _on_log_toggled(self, enabled: bool) -> None:
        moved = self._apply_log_scale(enabled)
        self.logScaleToggled.emit(self.column(), enabled)
        if moved:
            self.changed.emit()
            self.committed.emit()

    def bounds(self) -> tuple[Bound, Bound]:
        """The cut as `(lo, hi)`, a side at or past the data extreme being
        None (unbounded)."""
        data_min, data_max = self.histogram.data_range()
        lo, hi = self.histogram.range()
        return (None if lo <= data_min else lo), (None if hi >= data_max else hi)

    def set_bounds(self, lo: Bound, hi: Bound) -> None:
        data_min, data_max = self.histogram.data_range()
        self._loading = True
        self.histogram.set_range(data_min if lo is None else lo, data_max if hi is None else hi)
        self._loading = False

    def is_active(self) -> bool:
        return self.bounds() != (None, None)

    def _on_reset(self) -> None:
        self.set_bounds(None, None)
        self.changed.emit()
        self.committed.emit()

    def _on_column_changed(self, column: str) -> None:
        self.set_source(self._source, keep_bounds=False)
        self.columnChanged.emit(column)
        self.changed.emit()
        self.committed.emit()

    def _on_range_changed(self, _lo: float, _hi: float) -> None:
        if not self._loading:
            self.changed.emit()

    def _on_range_committed(self, _lo: float, _hi: float) -> None:
        if not self._loading:
            self.committed.emit()


class FilterPanel(QWidget):
    """A stack of `FilterRow`s over one table, with an "N of M pass"
    readout.

    Signals
    -------
    filtersChanged
        On every user-driven change, including each movement of a drag.
    filtersCommitted
        When a change is finished: a drag released, a spinbox edited, a
        row added, removed, repointed or reset.

    Neither fires from `set_source`/`set_filters`.

    `noun` names what one row of the source is ("points", "tracks"), for
    the readout and tooltips.

    Which columns are viewed on log bins is remembered per column, not
    per row: a row re-pointed to a column, or rebuilt by `set_filters`,
    comes back in that column's last view. `log_columns` /
    `set_log_columns` read and seed it (defaults, or a saved session).
    """

    filtersChanged = Signal()
    filtersCommitted = Signal()

    def __init__(self, noun: str = "rows", hint: str = "") -> None:
        super().__init__()
        self._noun = noun
        self._hint = hint
        self._source: Optional[dict[str, np.ndarray]] = None
        self._length = 0
        self._columns: list[str] = []
        self._rows: list[FilterRow] = []
        self._log_columns: set[str] = set()

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)

        singular = noun[:-1] if noun.endswith("s") else noun
        self._add_button = QPushButton("+ Add filter")
        self._add_button.setToolTip(
            f"Add a range filter on another column. Filters AND together:\n"
            f"a {singular} must pass every one of them."
        )
        self._add_button.clicked.connect(self._on_add_clicked)
        self._clear_button = QPushButton("Clear all")
        self._clear_button.clicked.connect(self.clear_filters)

        self._summary = wrapping_label(hint)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(self._add_button)
        buttons.addWidget(self._clear_button)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(self._rows_layout)
        layout.addLayout(buttons)
        layout.addWidget(self._summary)
        # Spare height goes below the panel, not between its rows.
        layout.addStretch()
        self._update_state()

    # -- source ---------------------------------------------------------

    def set_source(self, columns: Optional[Columns], offered: Optional[Sequence[str]] = None) -> None:
        """Point every row at a (re)computed table, keeping the cuts already
        set. `offered` limits which columns rows may pick; by default every
        `numeric_columns` column. Silent."""
        self._source = dict(columns) if columns else None
        self._length = n_rows(self._source) if self._source else 0
        if self._source is None:
            self._columns = list(offered or [])
        elif offered is None:
            self._columns = numeric_columns(self._source)
        else:
            self._columns = [c for c in offered if c in self._source]
        for row in self._rows:
            row.set_columns(self._columns)
            row.set_source(self._source or {}, keep_bounds=True)
            row.set_log_scale(row.column() in self._log_columns)
        self._update_state()

    def columns(self) -> list[str]:
        return list(self._columns)

    # -- log view -------------------------------------------------------

    def log_columns(self) -> set[str]:
        return set(self._log_columns)

    def set_log_columns(self, columns: Iterable[str]) -> None:
        """Which columns' histograms use log bins, here and in rows added
        later. Silent."""
        self._log_columns = set(columns)
        for row in self._rows:
            row.set_log_scale(row.column() in self._log_columns)

    def _on_log_scale_toggled(self, column: str, enabled: bool) -> None:
        if enabled:
            self._log_columns.add(column)
        else:
            self._log_columns.discard(column)
        # Every row on that column follows: two rows on one feature in two
        # different views would be two different-looking histograms of the
        # same data.
        for row in self._rows:
            if row.column() == column:
                row.set_log_scale(enabled)

    def _on_row_column_changed(self, row: "FilterRow", column: str) -> None:
        row.set_log_scale(column in self._log_columns)

    # -- the spec -------------------------------------------------------

    def filters(self) -> FilterSpec:
        """Active cuts. A column filtered by several rows is intersected, so
        a second row narrows the first instead of replacing it."""
        spec: FilterSpec = {}
        for row in self._rows:
            if not row.is_active():
                continue
            bounds = row.bounds()
            column = row.column()
            spec[column] = intersect(spec[column], bounds) if column in spec else bounds
        return spec

    def set_filters(self, spec: Optional[FilterSpec]) -> None:
        """Replace every row with the cuts in `spec` (restoring a saved
        spec, say). Columns not currently offered are skipped. Silent."""
        for row in list(self._rows):
            self._remove_row(row, notify=False)
        for column, (lo, hi) in (spec or {}).items():
            if column in self._columns:
                self._add_row(column, notify=False).set_bounds(lo, hi)
        self._update_state()

    def clear_filters(self) -> None:
        for row in list(self._rows):
            self._remove_row(row, notify=False)
        self._notify(commit=True)

    def has_filters(self) -> bool:
        return bool(self.filters())

    def mask(self) -> Optional[np.ndarray]:
        """Which rows of the source pass, or None with no source."""
        if self._source is None:
            return None
        return filter_mask(self._source, self.filters(), self._length)

    def n_passing(self) -> Optional[int]:
        mask = self.mask()
        return None if mask is None else int(mask.sum())

    def summary_text(self) -> str:
        if self._source is None:
            return self._hint or f"no {self._noun} loaded yet"
        if not self.filters():
            return f"no filters — all {self._length} {self._noun} pass"
        return f"{self.n_passing()} of {self._length} {self._noun} pass"

    # -- rows -----------------------------------------------------------

    def rows(self) -> list[FilterRow]:
        return list(self._rows)

    def add_filter(self, column: Optional[str] = None) -> Optional[FilterRow]:
        """Add a row on `column`, or on the first column no row is on yet
        (so three clicks give three different features)."""
        if column is None:
            taken = {row.column() for row in self._rows}
            column = next((c for c in self._columns if c not in taken), None)
            column = column or (self._columns[0] if self._columns else None)
        if column is None:
            return None
        return self._add_row(column)

    def _add_row(self, column: str, notify: bool = True) -> FilterRow:
        row = FilterRow(self._columns, column)
        row.changed.connect(lambda: self._notify(commit=False))
        row.committed.connect(lambda: self._notify(commit=True))
        row.removeRequested.connect(self._remove_row)
        row.logScaleToggled.connect(self._on_log_scale_toggled)
        row.columnChanged.connect(lambda c, row=row: self._on_row_column_changed(row, c))
        row.set_source(self._source or {}, keep_bounds=False)
        row.set_log_scale(column in self._log_columns)
        self._rows.append(row)
        self._rows_layout.addWidget(row)
        if notify:
            self._notify(commit=True)
        return row

    def _remove_row(self, row: FilterRow, notify: bool = True) -> None:
        if row not in self._rows:
            return
        self._rows.remove(row)
        self._rows_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        if notify:
            self._notify(commit=True)

    def _on_add_clicked(self) -> None:
        self.add_filter()

    def _notify(self, commit: bool) -> None:
        self._update_state()
        self.filtersChanged.emit()
        if commit:
            self.filtersCommitted.emit()

    def _update_state(self) -> None:
        self._summary.setText(self.summary_text())
        self._add_button.setEnabled(bool(self._columns))
        self._clear_button.setEnabled(bool(self._rows))
