"""Reusable Qt widgets and interaction patterns for scientific
image-analysis apps. See README.md for what lives where."""

from qtkit.colors import STATUS_COLORS, Status, status_color
from qtkit.filters import FilterPanel, FilterRow, FilterSpec, columns_of, filter_mask, numeric_columns
from qtkit.histogram import HistogramCanvas, HistogramRangeWidget
from qtkit.labels import note_label, set_status, status_label, style_status_label
from qtkit.layouts import FlowLayout, flow_row, hline, scrolled, wrapping_label
from qtkit.sections import CollapsibleSection, StepPager
from qtkit.spinbox import OptionalSpinBox, configure_spinbox_for_range, double_spinbox
from qtkit.table import ColumnTableModel, table_view

__version__ = "0.1.0"

__all__ = [
    "STATUS_COLORS",
    "CollapsibleSection",
    "ColumnTableModel",
    "FilterPanel",
    "FilterRow",
    "FilterSpec",
    "FlowLayout",
    "HistogramCanvas",
    "HistogramRangeWidget",
    "OptionalSpinBox",
    "Status",
    "StepPager",
    "columns_of",
    "configure_spinbox_for_range",
    "double_spinbox",
    "filter_mask",
    "flow_row",
    "hline",
    "note_label",
    "numeric_columns",
    "scrolled",
    "set_status",
    "status_color",
    "status_label",
    "style_status_label",
    "table_view",
    "wrapping_label",
]
