"""Numeric entry sized to the data it edits."""

from __future__ import annotations

import math
from typing import Optional

from qtpy.QtCore import Signal
from qtpy.QtWidgets import QCheckBox, QDoubleSpinBox, QHBoxLayout, QWidget


def adaptive_decimals_step(data_min: float, data_max: float) -> tuple[int, float]:
    """`(decimals, step)` giving ~3-4 significant figures across the span
    `data_min..data_max`. A fixed two-decimal spinbox is useless on a
    diffusion coefficient (~1e-2) and needlessly fussy on a 16-bit
    intensity (~1e4); this sizes both to the span instead."""
    span = data_max - data_min
    if not math.isfinite(span) or span <= 0:
        span = 1.0
    order = math.floor(math.log10(span))
    decimals = max(0, min(4 - order, 10))
    step = span * 0.01
    step_order = math.floor(math.log10(step))
    step = round(step, -step_order)
    return decimals, step if step > 0 else 10.0**-decimals


def format_adaptive(value: float, data_min: float, data_max: float) -> str:
    """`value` printed at the precision `adaptive_decimals_step` would edit
    it at, switching to scientific notation for very small or very large
    magnitudes."""
    span = data_max - data_min
    if not math.isfinite(span) or span <= 0:
        span = 1.0
    decimals = max(0, min(4 - math.floor(math.log10(span)), 8))
    magnitude = abs(value) if value != 0 else span
    if math.isfinite(magnitude) and magnitude > 0:
        order = math.floor(math.log10(magnitude))
        if order < -4 or order > 6:
            return f"{value:.2e}"
    return f"{value:.{decimals}f}"


def configure_spinbox_for_range(
    spinbox: QDoubleSpinBox,
    data_min: float,
    data_max: float,
    margin: float = 0.1,
    precision_range: Optional[tuple[float, float]] = None,
) -> None:
    """Set `spinbox`'s decimals, step and range for data spanning
    `data_min..data_max`, with `margin` (a fraction of the span) of room
    either side. Silent: no `valueChanged` while reconfiguring.

    `precision_range`, given, sizes decimals/step instead of
    `data_min..data_max` -- pass a percentile-trimmed range when the full
    span is dominated by a few outliers, so they don't zero out the
    decimals needed to work the bulk of the distribution (a handful of
    failed fits blowing a localization-precision column out to 1e5
    shouldn't turn its spinbox into an integer field at 0.01)."""
    precision_min, precision_max = precision_range if precision_range is not None else (data_min, data_max)
    decimals, step = adaptive_decimals_step(precision_min, precision_max)
    span = data_max - data_min
    pad = span * margin if span > 0 else 1.0
    blocked = spinbox.blockSignals(True)
    spinbox.setDecimals(decimals)
    spinbox.setSingleStep(step)
    spinbox.setRange(data_min - pad, data_max + pad)
    spinbox.blockSignals(blocked)


def double_spinbox(
    value: float,
    minimum: float,
    maximum: float,
    step: float,
    decimals: int,
    tooltip: str = "",
    suffix: str = "",
) -> QDoubleSpinBox:
    """A configured `QDoubleSpinBox` in one call."""
    box = QDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(decimals)
    box.setSingleStep(step)
    box.setValue(value)
    box.setToolTip(tooltip)
    if suffix:
        box.setSuffix(suffix)
    return box


class OptionalSpinBox(QWidget):
    """A number, or "let the algorithm decide" -- a spinbox beside a
    checkbox that, when checked, disables it and makes `value()` return
    None.

    The shape of every "auto" parameter: a camera gain estimated per frame
    unless measured, a threshold derived from the data unless given, a
    band that can be switched off. `valueChanged` carries the effective
    value (float, or None when automatic)."""

    valueChanged = Signal(object)

    def __init__(
        self,
        spinbox: QDoubleSpinBox,
        auto_text: str = "auto",
        auto: bool = True,
        auto_tooltip: str = "",
    ) -> None:
        super().__init__()
        self.spinbox = spinbox
        self.auto = QCheckBox(auto_text)
        self.auto.setToolTip(auto_tooltip)
        self.auto.setChecked(auto)
        spinbox.setEnabled(not auto)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(spinbox)
        layout.addWidget(self.auto)

        self.auto.toggled.connect(self._on_auto_toggled)
        spinbox.valueChanged.connect(lambda _v: self.valueChanged.emit(self.value()))

    def _on_auto_toggled(self, checked: bool) -> None:
        self.spinbox.setEnabled(not checked)
        self.valueChanged.emit(self.value())

    def value(self) -> Optional[float]:
        return None if self.auto.isChecked() else self.spinbox.value()

    def set_value(self, value: Optional[float]) -> None:
        """None checks "auto"; a number unchecks it and shows the number."""
        before = self.value()
        blocked = self.blockSignals(True)
        if value is None:
            self.auto.setChecked(True)
        else:
            self.spinbox.setValue(float(value))
            self.auto.setChecked(False)
        self.blockSignals(blocked)
        # One signal carrying the final value, not one per internal step.
        if self.value() != before:
            self.valueChanged.emit(self.value())
