"""Layout pieces for narrow, short containers -- docks and side panels.

Everything here is about one failure: a Qt layout propagates its
children's size hints up as its own *minimum* size, so a single long
label, a row of small controls or a tall tab quietly pins how narrow or
short the whole dock can be dragged, and pushes whatever sits below it
off the bottom of a laptop screen with no way to scroll to it.
"""

from __future__ import annotations

from qtpy.QtCore import QPoint, QRect, QSize, Qt
from qtpy.QtWidgets import QFrame, QLabel, QLayout, QScrollArea, QSizePolicy, QWidget

# Floor for any internally-scrolling region, in px -- small enough that a
# dock can be dragged genuinely short, tall enough to still show a row or
# two of whatever is inside rather than a bare pair of scrollbars.
SCROLL_MIN_HEIGHT_PX = 56


def scrolled(widget: QWidget, min_height: int = SCROLL_MIN_HEIGHT_PX) -> QScrollArea:
    """Wrap `widget` so its height stops dictating its container's minimum
    height. A `QScrollArea` reports a small minimum regardless of its
    content and scrolls internally instead; the explicit floor matters
    because its own minimum (scrollbars plus frame) still adds up to
    ~90px per nested area otherwise."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(widget)
    area.setMinimumHeight(min_height)
    return area


def hline() -> QFrame:
    """A thin horizontal rule between a panel's logical sections."""
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


def wrapping_label(text: str = "") -> QLabel:
    """A word-wrapped label that can never widen its container.

    A word-wrapped `QLabel` still reports its longest *unwrapped* line as
    its `sizeHint`, and that hint becomes the container's minimum width --
    so one long error message or file path permanently stops a dock from
    being dragged narrower. An `Ignored` horizontal policy lets it take
    whatever width it is given and wrap inside it."""
    label = QLabel(text)
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    return label


class FlowLayout(QLayout):
    """A horizontal layout that wraps onto as many lines as it needs.

    A `QHBoxLayout` of small controls has a hard minimum width -- the sum
    of all of them -- which in a dock is often the single biggest thing
    stopping the panel from being dragged narrow. Reflowing costs a line
    of height at narrow widths and nothing at wide ones, and drops the
    minimum width to that of the widest *single* control.

    Qt's documented flow-layout pattern: `heightForWidth` reports what the
    wrap would cost, and `_do_layout` either measures or places.
    """

    def __init__(self, parent: QWidget | None = None, margin: int = 0, spacing: int = 4) -> None:
        super().__init__(parent)
        self._items: list = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item) -> None:  # noqa: N802 (Qt virtual)
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        # The widest single item, not their sum -- the whole point.
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y, line_height = effective.x(), effective.y(), 0
        for item in self._items:
            space_x = space_y = self.spacing()
            widget = item.widget()
            if widget is not None:
                style = widget.style()
                button = QSizePolicy.ControlType.PushButton
                space_x += style.layoutSpacing(button, button, Qt.Orientation.Horizontal)
                space_y += style.layoutSpacing(button, button, Qt.Orientation.Vertical)
            hint = item.sizeHint()
            next_x = x + hint.width() + space_x
            if next_x - space_x > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + space_y
                next_x = x + hint.width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


def flow_row(*widgets: QWidget, spacing: int = 4) -> QWidget:
    """A `FlowLayout` of `widgets` in a container sized to actually use it:
    a widget whose layout has height-for-width only gets the taller
    geometry it asks for when its own size policy says so too.

    Items are placed at their size hints, so a widget with an `Ignored`
    policy (e.g. `wrapping_label`) gets no width here -- put plain
    controls in a flow row, not wrapping text."""
    container = QWidget()
    layout = FlowLayout(container, spacing=spacing)
    for widget in widgets:
        layout.addWidget(widget)
    policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
    policy.setHeightForWidth(True)
    container.setSizePolicy(policy)
    return container
