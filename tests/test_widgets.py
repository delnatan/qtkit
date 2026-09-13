import numpy as np
import pytest
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from qtkit import (
    CollapsibleSection,
    ColumnTableModel,
    OptionalSpinBox,
    StepPager,
    double_spinbox,
    flow_row,
    status_label,
)
from qtkit.spinbox import adaptive_decimals_step, format_adaptive


def test_status_label_does_not_pin_width(qtbot):
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.addWidget(status_label("x" * 500))
    qtbot.addWidget(container)
    assert container.minimumSizeHint().width() < 100


def test_flow_row_minimum_is_widest_item(qtbot):
    buttons = [QPushButton(f"button number {i}") for i in range(6)]
    row = flow_row(*buttons)
    qtbot.addWidget(row)
    widest = max(b.minimumSizeHint().width() for b in buttons)
    assert row.layout().minimumSize().width() <= widest + 1
    assert row.layout().heightForWidth(widest + 2) > row.layout().heightForWidth(10_000)


def test_step_pager_hidden_pages_take_no_height(qtbot):
    pager = StepPager()
    qtbot.addWidget(pager)
    short, tall = QWidget(), QWidget()
    tall_layout = QVBoxLayout(tall)
    for i in range(30):
        tall_layout.addWidget(QPushButton(f"control {i}"))
    pager.add_page("Short", short)
    pager.add_page("Tall", tall)
    assert pager.sizeHint().height() < 300
    pager.show_step("tall")
    assert pager.current_page() == 1
    assert pager.sizeHint().height() > 300
    pager.show_step("no such step")
    assert pager.current_page() == 1


def test_collapsible_section(qtbot):
    body = QLabel("body")
    section = CollapsibleSection("Title", body)
    qtbot.addWidget(section)
    section.show()
    assert not body.isVisible()
    with qtbot.waitSignal(section.toggled):
        section.set_expanded(True)
    assert body.isVisible() and section.is_expanded()


def test_optional_spinbox(qtbot):
    box = OptionalSpinBox(double_spinbox(2.0, 0, 10, 0.1, 2))
    qtbot.addWidget(box)
    assert box.value() is None and not box.spinbox.isEnabled()
    with qtbot.waitSignal(box.valueChanged) as blocker:
        box.set_value(3.5)
    assert blocker.args == [3.5] and box.value() == 3.5
    box.set_value(None)
    assert box.value() is None


@pytest.mark.parametrize("lo,hi,decimals", [(0, 1, 4), (0, 65535, 0), (0, 0.001, 7), (5, 5, 4)])
def test_adaptive_decimals(lo, hi, decimals):
    assert adaptive_decimals_step(lo, hi)[0] == decimals


def test_format_adaptive():
    assert format_adaptive(0.123456, 0, 1) == "0.1235"
    assert format_adaptive(1e-7, 0, 1) == "1.00e-07"


def test_table_model_sort_missing_last(qtbot):
    model = ColumnTableModel({"id": np.array([0, 1, 2, 3]), "v": np.array([2.0, np.nan, 1.0, 3.0])})
    model.sort(1, Qt.SortOrder.AscendingOrder)
    assert model.column("id").tolist() == [2, 0, 3, 1]
    model.sort(1, Qt.SortOrder.DescendingOrder)
    assert model.column("id").tolist() == [3, 0, 2, 1]
    assert model.find_row("id", 2) == 2
    assert model.row_dict(0) == {"id": 3, "v": 3.0}
    index = model.index(3, 1)
    assert model.data(index) == ""


def test_table_model_rejects_ragged():
    with pytest.raises(ValueError):
        ColumnTableModel({"a": [1, 2], "b": [1]})


def test_gallery_builds(qtbot):
    from qtkit.gallery import build

    window = build()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)


def test_table_view_alternate_rows_are_translucent(qtbot):
    from qtkit import table_view

    view = table_view(ColumnTableModel({"a": [1, 2, 3]}))
    qtbot.addWidget(view)
    assert view.alternatingRowColors() and "rgba" in view.styleSheet()


def test_step_pager_hidden_pages_take_no_width(qtbot):
    pager = StepPager()
    qtbot.addWidget(pager)
    narrow, wide = QWidget(), QWidget()
    wide_layout = QHBoxLayout(wide)
    for i in range(12):
        wide_layout.addWidget(QPushButton(f"wide control {i}"))
    pager.add_page("Narrow", narrow)
    pager.add_page("Wide", wide)
    assert pager.minimumSizeHint().width() < 300
    pager.set_page(1)
    assert pager.minimumSizeHint().width() > 300
