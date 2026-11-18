"""Ways to show less at once: a foldable section, and a step pager."""

from __future__ import annotations

from qtpy.QtCore import QEvent, QPointF, QRectF, QSize, Qt, Signal
from qtpy.QtGui import QFont, QFontMetrics, QPainter, QPainterPath, QPalette, QPen
from qtpy.QtWidgets import (
    QHBoxLayout,
    QMenu,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from qtkit.layouts import hline


class _DisclosureHeader(QWidget):
    """A section's header: a chevron and a bold title, toggled by a click
    or by Space/Enter when focused.

    Painted rather than a `QToolButton`, because a button class is what
    host stylesheets theme -- pyvistra's paints every button amber with
    dark text, and a widget-level stylesheet can only override properties,
    not opt out of them: made transparent, the button kept the dark
    "text on amber" color, every `palette(...)` role included. A plain
    `QWidget` takes the host's ordinary text color (`WindowText`) instead,
    so the header reads like the labels around it under any theme."""

    toggled = Signal(bool)

    _ARROW = 9.0  # the chevron's box, px

    def __init__(self, title: str, expanded: bool) -> None:
        super().__init__()
        self._title = title
        self._expanded = expanded
        self._hover = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def _font(self) -> QFont:
        font = QFont(self.font())
        font.setBold(True)
        return font

    def sizeHint(self) -> QSize:  # noqa: N802
        metrics = QFontMetrics(self._font())
        width = int(self._ARROW) + 8 + metrics.horizontalAdvance(self._title) + 6
        return QSize(width, max(metrics.height(), int(self._ARROW)) + 8)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(int(self._ARROW) + 12, self.sizeHint().height())

    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool) -> None:
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self.update()
        self.toggled.emit(expanded)

    def set_title(self, title: str) -> None:
        self._title = title
        self.updateGeometry()
        self.update()

    def title(self) -> str:
        return self._title

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.set_expanded(not self._expanded)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.set_expanded(not self._expanded)
            return
        super().keyPressEvent(event)

    def event(self, event) -> bool:
        if event.type() in (QEvent.Type.HoverEnter, QEvent.Type.HoverLeave):
            self._hover = event.type() == QEvent.Type.HoverEnter
            self.update()
        return super().event(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.palette().color(QPalette.ColorRole.WindowText)
        if not self.isEnabled():
            color = self.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText)
        if self._hover or self.hasFocus():
            wash = QPalette(self.palette()).color(QPalette.ColorRole.WindowText)
            wash.setAlpha(28)  # a faint wash of the text color: themed by the host
            painter.fillRect(self.rect(), wash)
        a = self._ARROW
        cy = self.height() / 2.0
        box = QRectF(4.0, cy - a / 2.0, a, a)
        path = QPainterPath()
        if self._expanded:  # pointing down
            path.moveTo(QPointF(box.left(), box.top() + a * 0.3))
            path.lineTo(QPointF(box.center().x(), box.top() + a * 0.75))
            path.lineTo(QPointF(box.right(), box.top() + a * 0.3))
        else:  # pointing right
            path.moveTo(QPointF(box.left() + a * 0.3, box.top()))
            path.lineTo(QPointF(box.left() + a * 0.75, box.center().y()))
            path.lineTo(QPointF(box.left() + a * 0.3, box.bottom()))
        pen = QPen(color, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.setFont(self._font())
        text_rect = self.rect().adjusted(int(box.right()) + 6, 0, 0, 0)
        elided = painter.fontMetrics().elidedText(self._title, Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)


class CollapsibleSection(QWidget):
    """A titled section whose body folds away, for controls that are tall
    but only touched occasionally (a stack of filter histograms, expert
    settings). The header -- a disclosure arrow and the title -- stays
    visible while folded, so what is hidden is never a mystery, unlike a
    splitter pane dragged to zero."""

    toggled = Signal(bool)

    def __init__(self, title: str, content: QWidget, expanded: bool = False) -> None:
        super().__init__()
        self._content = content

        self._toggle = _DisclosureHeader(title, expanded)
        self._toggle.toggled.connect(self._on_toggled)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._toggle)
        layout.addWidget(content)
        self._content.setVisible(expanded)

    def _on_toggled(self, checked: bool) -> None:
        self._content.setVisible(checked)
        self.toggled.emit(checked)

    def is_expanded(self) -> bool:
        return self._toggle.is_expanded()

    def set_expanded(self, expanded: bool) -> None:
        self._toggle.set_expanded(expanded)

    def set_title(self, title: str) -> None:
        self._toggle.set_title(title)


class StepPager(QWidget):
    """A multi-step flow shown one step at a time, behind a
    ``‹  2 / 4 · Detect ▾  ›`` header: arrows leaf between steps and the
    title is a menu for jumping to one.

    Only one step is ever being worked on, and a stacked column of all of
    them puts the current step's action button off-screen as often as not
    in a short container. The space saving is real rather than cosmetic,
    which takes one trick: a `QStackedWidget` reserves the height of its
    *tallest* page and the width of its *widest*, so every page not showing
    gets an `Ignored` size policy, which drops it out of the stack's size
    hint -- the pager is exactly as big as the step in view and resizes as
    you leaf.
    """

    pageChanged = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._titles: list[str] = []

        self._prev = QToolButton()
        self._prev.setArrowType(Qt.ArrowType.LeftArrow)
        self._prev.setAutoRaise(True)
        self._prev.clicked.connect(lambda: self.set_page(self.current_page() - 1))
        self._next = QToolButton()
        self._next.setArrowType(Qt.ArrowType.RightArrow)
        self._next.setAutoRaise(True)
        self._next.clicked.connect(lambda: self.set_page(self.current_page() + 1))

        # Ignored width: a long step name must not set the minimum width.
        self._title = QToolButton()
        self._title.setAutoRaise(True)
        self._title.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._title.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._title.setToolTip("Jump to a step")
        # The "▾" is in the title text, not the style's menu indicator: a
        # host stylesheet's button padding pushes that indicator onto the
        # text (pyvistra's put it over the step name).
        self._title.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0px; }")
        self._menu = QMenu(self._title)
        self._title.setMenu(self._menu)

        self._stack = QStackedWidget()
        self._stack.currentChanged.connect(self._on_current_changed)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(2)
        header.addWidget(self._prev)
        header.addWidget(self._title, stretch=1)
        header.addWidget(self._next)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(header)
        layout.addWidget(hline())
        layout.addWidget(self._stack)

    def add_page(self, title: str, widget: QWidget) -> int:
        # Title first: the first page emits currentChanged synchronously,
        # and `_on_current_changed` reads `_titles[index]`.
        self._titles.append(title)
        index = self._stack.addWidget(widget)
        action = self._menu.addAction(title)
        action.triggered.connect(lambda _checked=False, i=index: self.set_page(i))
        self._on_current_changed(self._stack.currentIndex())
        return index

    def count(self) -> int:
        return self._stack.count()

    def current_page(self) -> int:
        return self._stack.currentIndex()

    def set_page(self, index: int) -> None:
        if 0 <= index < self._stack.count():
            self._stack.setCurrentIndex(index)

    def show_step(self, title: str) -> None:
        """Bring the step called `title` (case-insensitive) to the front.
        Unknown titles are ignored: a caller naming a step is reporting a
        result, and a renamed page is no reason to drop it."""
        for index, existing in enumerate(self._titles):
            if existing.lower() == title.lower():
                self.set_page(index)
                return

    def _on_current_changed(self, index: int) -> None:
        total = self._stack.count()
        if total == 0 or index < 0:
            return
        for i in range(total):
            page = self._stack.widget(i)
            shown = QSizePolicy.Policy.Preferred if i == index else QSizePolicy.Policy.Ignored
            policy = page.sizePolicy()
            policy.setVerticalPolicy(shown)
            policy.setHorizontalPolicy(shown)
            page.setSizePolicy(policy)
        self._title.setText(f"{index + 1} / {total} · {self._titles[index]}  ▾")
        self._prev.setEnabled(index > 0)
        self._next.setEnabled(index < total - 1)
        self._prev.setToolTip(f"Back to {self._titles[index - 1]}" if index > 0 else "")
        self._next.setToolTip(f"On to {self._titles[index + 1]}" if index < total - 1 else "")
        for i, action in enumerate(self._menu.actions()):
            action.setEnabled(i != index)
        self._stack.updateGeometry()
        self.pageChanged.emit(index)
