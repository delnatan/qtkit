import numpy as np
import pytest

from qtkit.filters import FilterPanel, columns_of, filter_mask, intersect, numeric_columns


@pytest.fixture
def table():
    return {
        "id": np.arange(6),
        "flux": np.array([1.0, 2.0, 3.0, 4.0, np.nan, 6.0]),
        "const": np.ones(6),
        "name": np.array(list("abcdef")),
    }


def test_filter_mask_bounds_and_missing(table):
    assert filter_mask(table, {"flux": (2.0, 4.0)}).tolist() == [False, True, True, True, False, False]
    # One side unbounded; NaN still fails a bounded side.
    assert filter_mask(table, {"flux": (None, 3.0)}).tolist() == [True, True, True, False, False, False]
    assert filter_mask(table, {"flux": (None, None)}).all()
    # A column the table doesn't have is skipped, not fatal.
    assert filter_mask(table, {"nope": (0, 1)}).all()
    assert filter_mask({}, {"x": (0, 1)}, length=3).tolist() == [True, True, True]


def test_numeric_columns_skips_constant_text_and_skip(table):
    assert numeric_columns(table) == ["id", "flux"]
    assert numeric_columns(table, skip={"id"}) == ["flux"]


def test_intersect():
    assert intersect((1, None), (None, 5)) == (1, 5)
    assert intersect((1, 9), (2, 5)) == (2, 5)
    assert intersect((None, None), (None, None)) == (None, None)


def test_columns_of_polars():
    pl = pytest.importorskip("polars")
    cols = columns_of(pl.DataFrame({"a": [1, 2], "b": [0.5, 1.5]}))
    assert list(cols) == ["a", "b"] and cols["b"].tolist() == [0.5, 1.5]


def test_panel_unmoved_row_is_not_a_filter(qtbot, table):
    panel = FilterPanel(noun="spots")
    qtbot.addWidget(panel)
    panel.set_source(table)
    with qtbot.waitSignals([panel.filtersChanged, panel.filtersCommitted]):
        row = panel.add_filter("flux")
    assert panel.filters() == {}
    assert "all 6 spots pass" in panel.summary_text()

    row.set_bounds(2.0, None)
    assert panel.filters() == {"flux": (2.0, None)}
    assert panel.n_passing() == 4


def test_panel_set_filters_is_silent_and_restores(qtbot, table):
    panel = FilterPanel()
    qtbot.addWidget(panel)
    panel.set_source(table)
    with qtbot.assertNotEmitted(panel.filtersChanged):
        panel.set_filters({"flux": (None, 3.0), "not_offered": (0, 1)})
    assert panel.filters() == {"flux": (None, 3.0)}


def test_duplicate_rows_intersect(qtbot, table):
    panel = FilterPanel()
    qtbot.addWidget(panel)
    panel.set_source(table)
    panel.add_filter("flux").set_bounds(2.0, None)
    panel.add_filter("flux").set_bounds(None, 4.0)
    assert panel.filters() == {"flux": (2.0, 4.0)}


def test_refresh_keeps_bounded_sides_and_unbounded_stays_unbounded(qtbot, table):
    panel = FilterPanel()
    qtbot.addWidget(panel)
    panel.set_source(table)
    panel.add_filter("flux").set_bounds(2.0, None)
    wider = dict(table, flux=np.array([0.0, 2.0, 3.0, 4.0, 5.0, 60.0]))
    with qtbot.assertNotEmitted(panel.filtersChanged):
        panel.set_source(wider)
    assert panel.filters() == {"flux": (2.0, None)}
