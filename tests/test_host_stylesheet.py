"""qtkit widgets under a host application's stylesheet.

A host (pyvistra) styles every button amber with dark text and wide
padding, and every spin box; each test below is a way that broke a qtkit
widget, checked with such a stylesheet installed on the application."""

import numpy as np
import pytest
from qtpy.QtCore import QPoint, Qt
from qtpy.QtGui import QPalette
from qtpy.QtWidgets import QComboBox, QFormLayout, QWidget

from qtkit import CollapsibleSection, FilterPanel, flow_row
from qtkit.histogram import HistogramRangeWidget
from qtkit.spinbox import adaptive_decimals_step, format_adaptive

HOST_STYLE = """
QWidget { color: #f2efe9; background-color: #1c1a17; font-size: 12px; }
QPushButton, QToolButton { background-color: #e0a030; color: #1c1a17; padding: 6px 12px; font-weight: 600; }
QSpinBox, QDoubleSpinBox { border: 1px solid #3a352e; padding: 4px; }
QComboBox { border: 1px solid #3a352e; padding: 4px; min-width: 6em; }
"""


@pytest.fixture
def host_style(qapp):
    previous = qapp.styleSheet()
    qapp.setStyleSheet(HOST_STYLE)
    yield
    qapp.setStyleSheet(previous)


def test_section_header_takes_the_host_text_color_not_the_button_color(qtbot, host_style):
    from qtkit.sections import _DisclosureHeader

    section = CollapsibleSection("Expert settings", QWidget())
    qtbot.addWidget(section)
    section.show()
    header = section.findChild(_DisclosureHeader)
    assert header.palette().color(QPalette.ColorRole.WindowText).name() == "#f2efe9"


def test_section_header_toggles_by_click_and_keyboard(qtbot, host_style):
    from qtkit.sections import _DisclosureHeader

    body = QWidget()
    section = CollapsibleSection("Title", body)
    qtbot.addWidget(section)
    section.show()
    header = section.findChild(_DisclosureHeader)
    with qtbot.waitSignal(section.toggled):
        qtbot.mouseClick(header, Qt.MouseButton.LeftButton, pos=QPoint(10, header.height() // 2))
    assert section.is_expanded() and body.isVisible()
    header.setFocus()
    qtbot.keyClick(header, Qt.Key.Key_Space)
    assert not section.is_expanded() and not body.isVisible()


def test_histogram_spinboxes_show_their_value(qtbot, host_style):
    # Qt 6.12 lays out a NoButtons spin box's editor 1 px wide under any
    # stylesheet -- the boxes rendered blank. Only a Qt >= 6.12 run can
    # catch a regression here (6.11 never had the bug).
    widget = HistogramRangeWidget()
    qtbot.addWidget(widget)
    widget.set_data(np.linspace(0.0, 10.0, 100))
    widget.show()
    for spin in (widget._min_spin, widget._max_spin):
        assert spin.lineEdit().width() > 20


def test_filter_row_glyph_buttons_keep_their_width(qtbot, host_style):
    panel = FilterPanel()
    qtbot.addWidget(panel)
    panel.set_source({"flux": np.arange(10.0)})
    panel.set_filters({"flux": (None, None)})
    panel.resize(400, 200)
    panel.show()
    buttons = {b.text(): b for b in panel.findChildren(type(panel._add_button)) if b.text() in ("log", "⤢", "✕")}
    assert buttons["log"].width() == 32 and buttons["✕"].width() == 24 and buttons["⤢"].width() == 24


def test_flow_row_in_a_form_stays_on_one_line_when_there_is_room(qtbot, host_style):
    combo = QComboBox()
    combo.addItems(["spatial_class", "track_length"])
    other = QComboBox()
    other.addItem("x")
    row = flow_row(combo, other)
    host = QWidget()
    form = QFormLayout(host)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
    form.addRow("color by", row)
    qtbot.addWidget(host)
    host.resize(500, 100)
    host.show()
    assert combo.width() >= combo.sizeHint().width()  # not clipped
    assert other.geometry().top() < combo.geometry().bottom()  # same line
    assert row.layout().minimumSize().width() >= combo.sizeHint().width()


def test_a_single_repeated_value_gets_ordinary_precision():
    assert adaptive_decimals_step(1.0, 1.0 + 1e-9)[0] == 4
    assert format_adaptive(1.0, 1.0, 1.0 + 1e-9) == "1.0000"
    # A genuinely small span is still a span.
    assert adaptive_decimals_step(1e-5, 2e-5)[0] > 6
