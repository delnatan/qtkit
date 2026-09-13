"""Status and explanatory text lines."""

from __future__ import annotations

from qtpy.QtWidgets import QLabel

from qtkit.colors import Status, status_color
from qtkit.layouts import wrapping_label


def style_status_label(label: QLabel, level: Status | str = Status.NEUTRAL) -> None:
    """Color `label` for `level` (see `qtkit.colors.Status`)."""
    label.setStyleSheet(f"color: {status_color(level).name()}; font-size: 11px;")


def status_label(text: str = "", level: Status | str = Status.NEUTRAL) -> QLabel:
    """A one-line result/progress readout that wraps and can never widen
    its container (`layouts.wrapping_label`). Every status line in a panel
    should come from here, and be updated with `set_status`."""
    label = wrapping_label(text)
    style_status_label(label, level)
    return label


def set_status(label: QLabel, text: str, level: Status | str = Status.NEUTRAL) -> None:
    """Set a status label's text and level together, so a stale color from
    the previous result can't linger on new text."""
    style_status_label(label, level)
    label.setText(text)


def note_label(text: str) -> QLabel:
    """A dimmed explanatory line -- the "why" under a control, not a
    result. Disabled rather than recolored, so the theme decides what
    dimmed text looks like."""
    label = wrapping_label(text)
    label.setEnabled(False)
    return label
