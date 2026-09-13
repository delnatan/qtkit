"""The semantic colors widgets share, and nothing else.

Two kinds of color show up in a data-analysis UI, and they want opposite
treatment:

- *Chrome* -- backgrounds, text, borders, the histogram's own bars. These
  come from the widget's ``QPalette`` and are never hardcoded here, so the
  same widget reads correctly under napari's theme, an app's own global
  stylesheet (pyvistra's), or the OS default, light or dark.
- *Meaning* -- "this worked", "look at this", "this failed", "this is
  running". These must NOT follow the theme: a green "ok" has to stay
  green whatever the background is, or the color stops carrying the
  message. They live here, as :class:`Status` levels with one hex each.
"""

from __future__ import annotations

from enum import Enum

from qtpy.QtGui import QColor, QPalette


class Status(str, Enum):
    """Levels of the status color language. A ``str`` enum so a plain
    ``"ok"`` works anywhere a ``Status`` does."""

    NEUTRAL = "neutral"
    OK = "ok"
    CAUTION = "caution"
    ERROR = "error"
    RUNNING = "running"
    INACTIVE = "inactive"


STATUS_COLORS: dict[Status, str] = {
    Status.NEUTRAL: "#9a9a9a",
    Status.OK: "#22c55e",
    Status.CAUTION: "#f59e0b",
    Status.ERROR: "#ef4444",
    Status.RUNNING: "#3b82f6",
    Status.INACTIVE: "#5a5a5a",
}


def status_color(level: Status | str) -> QColor:
    """The color for `level`; unknown levels read as neutral rather than
    raising, since a status is display, not control flow."""
    try:
        return QColor(STATUS_COLORS[Status(level)])
    except ValueError:
        return QColor(STATUS_COLORS[Status.NEUTRAL])


def is_dark(palette: QPalette) -> bool:
    """Whether `palette`'s window background is dark."""
    return palette.color(QPalette.ColorRole.Window).lightness() < 128


def dim_color(palette: QPalette, alpha: int = 130) -> QColor:
    """A translucent wash that pushes content back from the eye on either
    theme: black over a dark background, the window color over a light
    one (a black wash on white reads as a hard gray block, not a dimming).
    Used for the out-of-range regions of a range histogram."""
    color = QColor(0, 0, 0) if is_dark(palette) else QColor(palette.color(QPalette.ColorRole.Window))
    color.setAlpha(alpha)
    return color
