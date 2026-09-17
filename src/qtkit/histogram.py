"""A range picked by dragging handles across a distribution.

The one control behind contrast limits, QC filters and colormap ranges:
the decision (where to cut) and its evidence (what the population looks
like) share the same few hundred pixels, so `flux > 1200` is chosen by
seeing the trough at 1200 rather than typed in blind.

Merged from pyvistra's `widgets/histogram.py` (center-drag, value labels,
tint color) and spt-pipeline's port of it (palette-aware drawing, the
spinbox row).
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from qtpy.QtCore import QRectF, Qt, Signal
from qtpy.QtGui import QBrush, QColor, QPainter, QPalette, QPen
from qtpy.QtWidgets import QAbstractSpinBox, QDoubleSpinBox, QHBoxLayout, QWidget

from qtkit.colors import dim_color
from qtkit.spinbox import configure_spinbox_for_range, format_adaptive

# Pixel distance from a handle within which a press grabs it.
HANDLE_GRAB_PX = 8
# Bin count is Freedman-Diaconis by default, clamped to this range.
MIN_BINS = 10
MAX_BINS = 200
# Threshold (in data units) below which integer-valued data gets one bin per
# value, when the caller hasn't forced a bin count -- the old DEFAULT_BINS.
INTEGER_BIN_BUDGET = 100
# View bounds for log mode when there's no positive data to show at all.
LOG_FALLBACK_MIN, LOG_FALLBACK_MAX = 1.0, 10.0


def _fd_bin_count(x: np.ndarray, min_bins: int = MIN_BINS, max_bins: int = MAX_BINS) -> int:
    """Freedman-Diaconis bin count for `x`, clamped to `min_bins..max_bins`.
    Falls back to Sturges' rule when the IQR is zero (heavily duplicated or
    near-constant data), where FD's bin width would be zero too."""
    n = x.size
    if n < 2:
        return min_bins
    q75, q25 = np.percentile(x, [75, 25])
    iqr = q75 - q25
    if iqr <= 0:
        return int(np.clip(np.ceil(np.log2(n) + 1), min_bins, max_bins))
    width = 2 * iqr * n ** (-1 / 3)
    data_range = x.max() - x.min()
    if width <= 0 or data_range <= 0:
        return min_bins
    return int(np.clip(np.ceil(data_range / width), min_bins, max_bins))


class HistogramCanvas(QWidget):
    """Histogram with draggable min/max handles, bar heights always
    log-compressed (`np.log1p`) so a tall peak doesn't flatten rarer bins.
    `set_log_scale` is a separate, opt-in switch for the bin *axis*
    (x-values), not this height compression.

    Drag a handle to move one bound, or drag between them to slide the
    whole window. When a bound goes past the data, the view widens to keep
    the handle on screen.

    Signals
    -------
    rangeChanged(lo, hi)
        On every movement of a drag -- for cheap live feedback.
    rangeCommitted(lo, hi)
        Once, when a drag that moved something is released -- for
        consumers too expensive to run at mouse-move rate.

    `set_data` and `set_range` are silent: programmatic setup is never
    mistaken for a user's choice.
    """

    rangeChanged = Signal(float, float)
    rangeCommitted = Signal(float, float)

    def __init__(self, parent: Optional[QWidget] = None, show_labels: bool = False) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumWidth(110)
        self._show_labels = show_labels
        self.setMinimumHeight(64 if show_labels else 40)

        self._counts: Optional[np.ndarray] = None
        self._color: Optional[QColor] = None
        self._log_scale = False
        self._raw_values: Optional[np.ndarray] = None
        self._bins_arg: Optional[int] = None
        self.data_min, self.data_max = 0.0, 1.0
        # Extent the bars are drawn over -- the data range, or half a unit
        # wider for integer data binned one bin per value.
        self._bars_min, self._bars_max = 0.0, 1.0
        self.lo, self.hi = 0.0, 1.0
        self._view_min, self._view_max = 0.0, 1.0

        self._dragging: Optional[str] = None  # "min" | "max" | "center"
        self._moved = False
        self._last_x = 0.0

    # -- data and range -------------------------------------------------

    def set_data(self, values, bins: Optional[int] = None) -> None:
        """Histogram `values` (non-finite entries ignored). An empty or
        all-NaN input draws flat rather than raising.

        `bins` forces a fixed bin count; left as None (the default), the
        count is Freedman-Diaconis, data-driven rather than a flat guess.

        Integer-valued data spanning no more than the bin budget gets one
        bin per value, centered on it: a track length of 3..15 spread over
        100 bins is a dozen slivers, most of them hidden under the
        handles. Log mode (`set_log_scale`) has no analog of this -- it
        always uses the adaptive or forced bin count."""
        self._raw_values = np.asarray(values, dtype=np.float64).ravel()
        self._bins_arg = bins
        self._rebin()
        self._update_view()
        self.update()

    def _rebin(self) -> None:
        raw = self._raw_values if self._raw_values is not None else np.empty(0)
        finite = raw[np.isfinite(raw)]
        if self._log_scale:
            self._rebin_log(finite)
        else:
            self._rebin_linear(finite)

    def _rebin_linear(self, finite: np.ndarray) -> None:
        if finite.size == 0:
            self.data_min, self.data_max = 0.0, 1.0
            self._bars_min, self._bars_max = 0.0, 1.0
            self._counts = np.zeros(self._bins_arg or MIN_BINS)
            return
        self.data_min, self.data_max = float(finite.min()), float(finite.max())
        span = self.data_max - self.data_min
        budget = self._bins_arg if self._bins_arg is not None else INTEGER_BIN_BUDGET
        if span <= budget and np.all(finite == np.round(finite)):
            n = int(span) + 1
            self._bars_min, self._bars_max = self.data_min - 0.5, self.data_max + 0.5
            counts, _ = np.histogram(finite, bins=n, range=(self._bars_min, self._bars_max))
            if span == 0:
                self.data_max = self.data_min + 1e-9
        else:
            # A near-constant column would make non-increasing bin edges.
            min_span = max(abs(self.data_min), abs(self.data_max), 1.0) * 1e-9
            if span < min_span:
                self.data_max = self.data_min + min_span
            n_bins = self._bins_arg if self._bins_arg is not None else _fd_bin_count(finite)
            self._bars_min, self._bars_max = self.data_min, self.data_max
            counts, _ = np.histogram(finite, bins=n_bins, range=(self.data_min, self.data_max))
        self._counts = np.log1p(counts)

    def _rebin_log(self, finite: np.ndarray) -> None:
        """Bin the positive subset of `finite` (values <= 0 have no place
        on a log axis, so they're dropped like NaN/Inf already are)."""
        pos = finite[finite > 0]
        if pos.size == 0:
            self.data_min, self.data_max = LOG_FALLBACK_MIN, LOG_FALLBACK_MAX
            self._bars_min, self._bars_max = self.data_min, self.data_max
            self._counts = np.zeros(self._bins_arg or MIN_BINS)
            return
        self.data_min, self.data_max = float(pos.min()), float(pos.max())
        hi = self.data_max if self.data_max > self.data_min else self.data_min * (1 + 1e-9)
        n_bins = self._bins_arg if self._bins_arg is not None else _fd_bin_count(np.log10(pos))
        edges = np.logspace(np.log10(self.data_min), np.log10(hi), n_bins + 1)
        counts, _ = np.histogram(pos, bins=edges)
        self._bars_min, self._bars_max = self.data_min, hi
        self._counts = np.log1p(counts)

    def set_color(self, color: QColor | str | None) -> None:
        """Tint for the bars -- a channel's color, say. None follows the
        palette's text color."""
        self._color = QColor(color) if color is not None else None
        self.update()

    def set_range(self, lo: float, hi: float) -> None:
        self.lo, self.hi = float(lo), float(hi)
        self._update_view()
        self.update()

    def range(self) -> tuple[float, float]:
        return self.lo, self.hi

    def data_range(self) -> tuple[float, float]:
        return self.data_min, self.data_max

    def dragging(self) -> Optional[str]:
        """Which part is being dragged right now: "min", "max", "center"
        or None. Lets a listener tell which bound the user moved."""
        return self._dragging

    def set_log_scale(self, enabled: bool) -> None:
        """Switch bin spacing between linear and log10, re-binning the
        last data given to `set_data` (no need to call it again). Values
        <= 0 are excluded from log-mode binning, same as NaN/Inf always
        are. A drag in progress is cancelled, not committed, since
        nothing was finished when the mode changed under it."""
        if enabled == self._log_scale:
            return
        if self._dragging is not None:
            self._dragging = None
            self._moved = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self._log_scale = enabled
        self._rebin()
        self._clamp_range_to_mode()
        self._update_view()
        self.update()

    def log_scale(self) -> bool:
        return self._log_scale

    def _clamp_range_to_mode(self) -> None:
        """After switching to log mode, pull lo/hi off of <= 0 (e.g. a
        linear-mode range that reached down to 0) so nothing downstream
        ever takes log10 of a non-positive number."""
        if not self._log_scale:
            return
        floor = self.data_min if self.data_min > 0 else 1e-12
        if self.lo <= 0:
            self.lo = floor
        if self.hi <= 0:
            self.hi = floor
        if self.hi <= self.lo:
            self.hi = self.lo * 10

    # -- geometry -------------------------------------------------------

    def _update_view(self) -> None:
        if self._log_scale:
            log_span = math.log10(self._bars_max) - math.log10(self._bars_min)
            margin = log_span * 0.05 or 0.5
            lo = math.log10(self.lo) if self.lo > 0 else math.log10(self.data_min)
            hi = math.log10(self.hi) if self.hi > 0 else math.log10(self.data_max)
            vmin = min(
                math.log10(self._bars_min), lo - margin if self.lo < self.data_min else math.log10(self.data_min)
            )
            vmax = max(
                math.log10(self._bars_max), hi + margin if self.hi > self.data_max else math.log10(self.data_max)
            )
            self._view_min, self._view_max = 10**vmin, 10**vmax
        else:
            margin = (self.data_max - self.data_min) * 0.05 or 1.0
            self._view_min = min(self._bars_min, self.lo - margin if self.lo < self.data_min else self.data_min)
            self._view_max = max(self._bars_max, self.hi + margin if self.hi > self.data_max else self.data_max)

    def _val_to_x(self, value: float) -> float:
        if self._log_scale:
            value = max(value, self._view_min)
            v, lo, hi = math.log10(value), math.log10(self._view_min), math.log10(self._view_max)
        else:
            v, lo, hi = value, self._view_min, self._view_max
        span = hi - lo
        if span <= 0:
            return 0.0
        x = (v - lo) / span * self.width()
        return max(-1e9, min(x, 1e9))

    def _x_to_val(self, x: float) -> float:
        if self._log_scale:
            lo, hi = math.log10(self._view_min), math.log10(self._view_max)
            value = 10 ** (lo + x / max(self.width(), 1) * (hi - lo))
            return max(self._view_min, min(value, self._view_max))
        span = self._view_max - self._view_min
        value = self._view_min + x / max(self.width(), 1) * span
        return max(self._view_min, min(value, self._view_max))

    # -- painting -------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.color(QPalette.ColorRole.Base))
        w, h = self.width(), self.height()
        text_color = palette.color(QPalette.ColorRole.Text)
        label_h = painter.fontMetrics().height() + 2 if self._show_labels else 0
        plot_h = h - label_h

        if self._counts is not None and self._counts.max() > 0:
            fill = QColor(self._color or text_color)
            fill.setAlpha(100)
            painter.setBrush(QBrush(fill))
            painter.setPen(Qt.PenStyle.NoPen)
            x0 = self._val_to_x(self._bars_min)
            pixel_span = max(self._val_to_x(self._bars_max) - x0, 1.0)
            n = len(self._counts)
            peak = self._counts.max()
            for i, count in enumerate(self._counts):
                bar_h = count / peak * plot_h
                painter.drawRect(QRectF(x0 + i / n * pixel_span, plot_h - bar_h, pixel_span / n, bar_h))

        x_lo, x_hi = self._val_to_x(self.lo), self._val_to_x(self.hi)
        shade = dim_color(palette)
        painter.fillRect(QRectF(0, 0, max(x_lo, 0), h), shade)
        painter.fillRect(QRectF(x_hi, 0, max(w - x_hi, 0), h), shade)

        pen = QPen(text_color)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawLine(int(x_lo), 0, int(x_lo), plot_h)
        painter.drawLine(int(x_hi), 0, int(x_hi), plot_h)

        if self._show_labels:
            self._draw_labels(painter, x_lo, x_hi, h)

    def _draw_labels(self, painter: QPainter, x_lo: float, x_hi: float, h: int) -> None:
        metrics = painter.fontMetrics()
        if self._log_scale:
            # A log-mode span (e.g. 1e-3..1e6) would round a small value's
            # decimals to 0 against the shared span -- size each label to
            # its own magnitude instead.
            lo_text = format_adaptive(self.lo, self.lo * 0.1, self.lo * 10)
            hi_text = format_adaptive(self.hi, self.hi * 0.1, self.hi * 10)
        else:
            lo_text = format_adaptive(self.lo, self.data_min, self.data_max)
            hi_text = format_adaptive(self.hi, self.data_min, self.data_max)
        lo_w = metrics.horizontalAdvance(lo_text)
        hi_w = metrics.horizontalAdvance(hi_text)
        w = self.width()
        lo_x = max(2, min(x_lo - lo_w / 2, w - lo_w - hi_w - 8))
        hi_x = min(w - hi_w - 2, max(x_hi - hi_w / 2, lo_x + lo_w + 6))
        baseline = h - metrics.descent() - 1
        painter.drawText(int(lo_x), baseline, lo_text)
        painter.drawText(int(hi_x), baseline, hi_text)

    # -- interaction ----------------------------------------------------

    def _hit(self, x: float) -> Optional[str]:
        d_lo = abs(x - self._val_to_x(self.lo))
        d_hi = abs(x - self._val_to_x(self.hi))
        if min(d_lo, d_hi) < HANDLE_GRAB_PX:
            if d_lo == d_hi:
                # Handles on top of each other: take the one on the side
                # the press is on, so they can always be pulled apart.
                return "min" if x <= self._val_to_x(self.lo) else "max"
            return "min" if d_lo < d_hi else "max"
        if self._val_to_x(self.lo) < x < self._val_to_x(self.hi):
            return "center"
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        x = event.position().x()
        self._dragging = self._hit(x)
        self._moved = False
        self._last_x = x
        if self._dragging == "center":
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        x = event.position().x()
        if self._dragging is None:
            hit = self._hit(x)
            self.setCursor(
                Qt.CursorShape.SizeHorCursor
                if hit in ("min", "max")
                else Qt.CursorShape.OpenHandCursor
                if hit == "center"
                else Qt.CursorShape.ArrowCursor
            )
            return

        eps = (self.hi * 1e-6 or 1e-12) if self._log_scale else ((self.data_max - self.data_min) * 1e-9 or 1e-12)
        if self._dragging == "center":
            delta = (x - self._last_x) / max(self.width(), 1) * (self._view_max - self._view_min)
            # Don't slide the window off the view: clamp the delta.
            delta = max(self._view_min - self.lo, min(delta, self._view_max - self.hi))
            self.lo += delta
            self.hi += delta
        elif self._dragging == "min":
            self.lo = min(self._x_to_val(x), self.hi - eps)
        else:
            self.hi = max(self._x_to_val(x), self.lo + eps)
        self._last_x = x
        self._moved = True
        self._update_view()
        self.update()
        self.rangeChanged.emit(self.lo, self.hi)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        was_dragging = self._dragging is not None and self._moved
        self._dragging = None
        self._moved = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        if was_dragging:
            self.rangeCommitted.emit(self.lo, self.hi)


class HistogramRangeWidget(QWidget):
    """Min spinbox | draggable histogram | max spinbox, kept in step.

    Signals match `HistogramCanvas`: `rangeChanged` live while dragging,
    `rangeCommitted` on release. A spinbox edit is a finished choice, so it
    emits both. `set_data`/`set_range` are silent."""

    rangeChanged = Signal(float, float)
    rangeCommitted = Signal(float, float)

    def __init__(
        self, parent: Optional[QWidget] = None, show_spinboxes: bool = True, show_labels: bool = False
    ) -> None:
        super().__init__(parent)
        self.canvas = HistogramCanvas(show_labels=show_labels)
        self._min_spin = QDoubleSpinBox()
        self._max_spin = QDoubleSpinBox()
        for spin in (self._min_spin, self._max_spin):
            spin.setKeyboardTracking(False)
            # No step buttons: dragging is the coarse control and these are
            # for typing an exact value (the wheel still steps). With them,
            # some styles (napari's) need ~110px just to show a number,
            # which is a third of a dock.
            spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            spin.setAlignment(Qt.AlignmentFlag.AlignRight)
            spin.setVisible(show_spinboxes)
        self._fit_spin_width()

        self._min_spin.valueChanged.connect(self._on_min_spin)
        self._max_spin.valueChanged.connect(self._on_max_spin)
        self.canvas.rangeChanged.connect(self._on_canvas_changed)
        self.canvas.rangeCommitted.connect(self.rangeCommitted)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._min_spin)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self._max_spin)

    def set_data(self, values, bins: Optional[int] = None) -> None:
        self.canvas.set_data(values, bins)
        for spin in (self._min_spin, self._max_spin):
            configure_spinbox_for_range(spin, *self.canvas.data_range())
        self._fit_spin_width()

    def set_log_scale(self, enabled: bool) -> None:
        self.canvas.set_log_scale(enabled)
        for spin in (self._min_spin, self._max_spin):
            configure_spinbox_for_range(spin, *self.canvas.data_range())
        self._fit_spin_width()
        self._set_spins(*self.canvas.range())

    def log_scale(self) -> bool:
        return self.canvas.log_scale()

    def _fit_spin_width(self) -> None:
        """Size both spinboxes to the longest value they can show."""
        spin = self._min_spin
        texts = [spin.textFromValue(v) for v in (spin.minimum(), spin.maximum())]
        text_width = max(spin.fontMetrics().horizontalAdvance(t) for t in texts)
        width = text_width + 2 * spin.fontMetrics().averageCharWidth() + 8
        for box in (self._min_spin, self._max_spin):
            box.setFixedWidth(max(width, 48))

    def set_color(self, color: QColor | str | None) -> None:
        self.canvas.set_color(color)

    def set_range(self, lo: float, hi: float) -> None:
        self.canvas.set_range(lo, hi)
        self._set_spins(lo, hi)

    def range(self) -> tuple[float, float]:
        return self.canvas.range()

    def data_range(self) -> tuple[float, float]:
        return self.canvas.data_range()

    def dragging(self) -> Optional[str]:
        return self.canvas.dragging()

    def _set_spins(self, lo: float, hi: float) -> None:
        for spin, value in ((self._min_spin, lo), (self._max_spin, hi)):
            blocked = spin.blockSignals(True)
            if not spin.minimum() <= value <= spin.maximum():
                spin.setRange(min(spin.minimum(), value), max(spin.maximum(), value))
            spin.setValue(value)
            spin.blockSignals(blocked)

    def _on_min_spin(self, value: float) -> None:
        if value < self._max_spin.value():
            self._spin_edit(value, self._max_spin.value())

    def _on_max_spin(self, value: float) -> None:
        if value > self._min_spin.value():
            self._spin_edit(self._min_spin.value(), value)

    def _spin_edit(self, lo: float, hi: float) -> None:
        self.canvas.set_range(lo, hi)
        self.rangeChanged.emit(lo, hi)
        self.rangeCommitted.emit(lo, hi)

    def _on_canvas_changed(self, lo: float, hi: float) -> None:
        self._set_spins(lo, hi)
        self.rangeChanged.emit(lo, hi)
