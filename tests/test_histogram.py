import numpy as np
from qtpy.QtCore import QPoint, Qt

from qtkit.histogram import HistogramCanvas, HistogramRangeWidget


def make_canvas(qtbot, **kwargs):
    canvas = HistogramCanvas(**kwargs)
    qtbot.addWidget(canvas)
    canvas.resize(400, 60)
    canvas.show()
    qtbot.waitExposed(canvas)
    canvas.set_data(np.linspace(0, 100, 1000))
    canvas.set_range(20, 80)
    return canvas


def x_of(canvas, value):
    return int(canvas._val_to_x(value))


def test_set_data_handles_empty_and_constant(qtbot):
    canvas = HistogramCanvas()
    qtbot.addWidget(canvas)
    canvas.set_data([np.nan, np.inf])
    assert canvas.data_range() == (0.0, 1.0)
    canvas.set_data(np.full(10, 5.0, dtype=np.float32))
    lo, hi = canvas.data_range()
    assert lo == 5.0 and hi > lo


def test_drag_min_emits_live_then_commit_once(qtbot):
    canvas = make_canvas(qtbot)
    changed, committed = [], []
    canvas.rangeChanged.connect(lambda lo, hi: changed.append((lo, hi)))
    canvas.rangeCommitted.connect(lambda lo, hi: committed.append((lo, hi)))
    y = 30
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x_of(canvas, 20), y))
    for value in (25, 30, 40):
        qtbot.mouseMove(canvas, QPoint(x_of(canvas, value), y))
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x_of(canvas, 40), y))
    assert len(changed) >= 1 and len(committed) == 1
    lo, hi = canvas.range()
    assert 35 < lo < 45 and hi == 80


def test_center_drag_moves_both(qtbot):
    canvas = make_canvas(qtbot)
    y = 30
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x_of(canvas, 50), y))
    qtbot.mouseMove(canvas, QPoint(x_of(canvas, 60), y))
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x_of(canvas, 60), y))
    lo, hi = canvas.range()
    assert abs((hi - lo) - 60) < 1e-6 and 25 < lo < 35


def test_click_without_move_does_not_commit(qtbot):
    canvas = make_canvas(qtbot)
    with qtbot.assertNotEmitted(canvas.rangeCommitted):
        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x_of(canvas, 20), 30))


def test_range_widget_spinbox_edit_emits_both_and_set_range_is_silent(qtbot):
    widget = HistogramRangeWidget()
    qtbot.addWidget(widget)
    widget.set_data(np.linspace(0, 1, 100))
    with qtbot.assertNotEmitted(widget.rangeChanged):
        widget.set_range(0.2, 0.8)
    with qtbot.waitSignals([widget.rangeChanged, widget.rangeCommitted]):
        widget._max_spin.setValue(0.5)
    assert widget.range() == (0.2, 0.5)


def test_range_outside_data_widens_view(qtbot):
    canvas = make_canvas(qtbot)
    canvas.set_range(-50, 200)
    assert canvas._view_min < -50 and canvas._view_max > 200


def test_integer_data_gets_one_bin_per_value(qtbot):
    canvas = HistogramCanvas()
    qtbot.addWidget(canvas)
    canvas.set_data([3, 3, 4, 15, 15, 15])
    assert len(canvas._counts) == 13
    assert canvas.data_range() == (3.0, 15.0)
    assert canvas._view_min <= 2.5 and canvas._view_max >= 15.5


def test_spinboxes_fit_their_values(qtbot):
    widget = HistogramRangeWidget()
    qtbot.addWidget(widget)
    widget.set_data(np.array([0.0, 123456.0]))
    spin = widget._min_spin
    needed = spin.fontMetrics().horizontalAdvance(spin.textFromValue(spin.maximum()))
    assert spin.width() >= needed
