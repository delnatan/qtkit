"""Ways to show less at once: a foldable section, and a step pager."""

from __future__ import annotations

from qtpy.QtCore import Qt, Signal
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

        self._toggle = QToolButton()
        self._toggle.setText(title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.setAutoRaise(True)
        self._toggle.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.toggled.connect(self._on_toggled)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._toggle)
        header.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(header)
        layout.addWidget(content)
        self._apply(expanded)

    def _apply(self, expanded: bool) -> None:
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self._content.setVisible(expanded)

    def _on_toggled(self, checked: bool) -> None:
        self._apply(checked)
        self.toggled.emit(checked)

    def is_expanded(self) -> bool:
        return self._toggle.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        self._toggle.setChecked(expanded)

    def set_title(self, title: str) -> None:
        self._toggle.setText(title)


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
        self._title.setText(f"{index + 1} / {total} · {self._titles[index]}")
        self._prev.setEnabled(index > 0)
        self._next.setEnabled(index < total - 1)
        self._prev.setToolTip(f"Back to {self._titles[index - 1]}" if index > 0 else "")
        self._next.setToolTip(f"On to {self._titles[index + 1]}" if index < total - 1 else "")
        for i, action in enumerate(self._menu.actions()):
            action.setEnabled(i != index)
        self._stack.updateGeometry()
        self.pageChanged.emit(index)
