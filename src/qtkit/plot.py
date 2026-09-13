"""Matplotlib figures in their own windows, and an x/y column picker.

Needs matplotlib (``qtkit[plot]``); imported lazily so the rest of qtkit
doesn't."""

from __future__ import annotations

from typing import Optional, Sequence

from qtpy.QtCore import Signal
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PlotWindow(QDialog):
    """A resizable, non-modal window for one matplotlib Figure, with the
    pan/zoom/save toolbar. A canvas embedded in a narrow side panel is
    only good for a glance; this is for reading a plot.

    Keep one per kind of plot and call `show_figure` again to replace its
    contents, rather than opening a window per plot."""

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(False)
        self.resize(700, 550)
        self._canvas = None
        self._toolbar = None
        self._layout = QVBoxLayout(self)

    def show_figure(self, figure) -> None:
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT

        for widget in (self._toolbar, self._canvas):
            if widget is not None:
                self._layout.removeWidget(widget)
                widget.deleteLater()
        self._canvas = FigureCanvasQTAgg(figure)
        self._toolbar = NavigationToolbar2QT(self._canvas, self)
        self._layout.addWidget(self._toolbar)
        self._layout.addWidget(self._canvas)
        self._canvas.draw()
        self.show()
        self.raise_()
        self.activateWindow()


class AxisPicker(QWidget):
    """Pick an x and a y column, with log-scale toggles and a "Show plot"
    button. Holds only the choice; the owner has the data and does the
    plotting when `plotRequested` fires."""

    plotRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None, log_x: bool = True, log_y: bool = False) -> None:
        super().__init__(parent)
        self._x = QComboBox()
        self._y = QComboBox()
        self._log_x = QCheckBox("log x")
        self._log_x.setChecked(log_x)
        self._log_y = QCheckBox("log y")
        self._log_y.setChecked(log_y)
        self._button = QPushButton("Show plot")
        self._button.setEnabled(False)
        self._button.clicked.connect(self.plotRequested)

        form = QFormLayout()
        form.addRow("x:", self._x)
        form.addRow("y:", self._y)
        logs = QHBoxLayout()
        logs.addWidget(self._log_x)
        logs.addWidget(self._log_y)
        logs.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(form)
        layout.addLayout(logs)
        layout.addWidget(self._button)

    def set_columns(
        self, columns: Sequence[str], prefer_x: Optional[str] = None, prefer_y: Optional[str] = None
    ) -> None:
        """Offer `columns`, selecting `prefer_*` if given and present, else
        keeping the current choice if it survived."""
        for picker, prefer in ((self._x, prefer_x), (self._y, prefer_y)):
            current = prefer or picker.currentText()
            blocked = picker.blockSignals(True)
            picker.clear()
            picker.addItems(list(columns))
            if current in columns:
                picker.setCurrentText(current)
            picker.blockSignals(blocked)
        self._button.setEnabled(bool(columns))

    def clear(self) -> None:
        self.set_columns([])

    def selection(self) -> tuple[str, str, bool, bool]:
        """`(x, y, log_x, log_y)`."""
        return self._x.currentText(), self._y.currentText(), self._log_x.isChecked(), self._log_y.isChecked()
