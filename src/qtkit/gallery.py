"""Every qtkit widget on one screen, on synthetic data.

    python -m qtkit.gallery          # follow the OS theme
    python -m qtkit.gallery --dark   # force a dark palette
    python -m qtkit.gallery --light

The visual check for anything touching drawing or sizing: resize the
window narrow and short, flip the theme, and see that nothing clips,
pins the width, or loses contrast.
"""

from __future__ import annotations

import sys

import numpy as np
from qtpy.QtCore import Qt
from qtpy.QtGui import QColor, QPalette
from qtpy.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from qtkit import (
    CollapsibleSection,
    ColumnTableModel,
    FilterPanel,
    HistogramRangeWidget,
    OptionalSpinBox,
    Status,
    StepPager,
    double_spinbox,
    flow_row,
    note_label,
    scrolled,
    set_status,
    status_label,
    style_status_label,
)


def dark_palette() -> QPalette:
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "#26282b",
        QPalette.ColorRole.WindowText: "#e6e6e6",
        QPalette.ColorRole.Base: "#1d1f21",
        QPalette.ColorRole.AlternateBase: "#2a2d30",
        QPalette.ColorRole.Text: "#e6e6e6",
        QPalette.ColorRole.Button: "#33363a",
        QPalette.ColorRole.ButtonText: "#e6e6e6",
        QPalette.ColorRole.Highlight: "#e0a030",
        QPalette.ColorRole.HighlightedText: "#1a1a19",
        QPalette.ColorRole.ToolTipBase: "#33363a",
        QPalette.ColorRole.ToolTipText: "#e6e6e6",
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#6b6e72"))
    return palette


def synthetic_table(n: int = 2000, seed: int = 0) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    bright = rng.random(n) < 0.3
    return {
        "id": np.arange(n),
        "flux": np.where(bright, rng.normal(4000, 600, n), rng.normal(1200, 300, n)),
        "fit_sigma": rng.gamma(20, 0.07, n),
        "D_um2_s": 10 ** rng.normal(-1.5, 0.5, n),
        "alpha": np.clip(rng.normal(0.8, 0.2, n), 0.05, 2.0),
    }


def build() -> QWidget:
    table = synthetic_table()

    # Left: controls
    histogram = HistogramRangeWidget(show_labels=True)
    histogram.set_data(table["flux"])
    histogram.set_range(900, 5000)
    readout = status_label("drag a handle, or between them")
    histogram.rangeChanged.connect(lambda lo, hi: set_status(readout, f"live {lo:.0f}–{hi:.0f}"))
    histogram.rangeCommitted.connect(
        lambda lo, hi: set_status(readout, f"committed {lo:.0f}–{hi:.0f}", Status.OK)
    )

    tinted = HistogramRangeWidget(show_spinboxes=False)
    tinted.set_data(table["alpha"])
    tinted.set_color("#e0a030")
    tinted.set_range(0.5, 1.2)

    log_histogram = HistogramRangeWidget(show_labels=True)
    log_histogram.set_data(table["D_um2_s"])
    log_scale_check = QCheckBox("log scale")
    log_scale_check.toggled.connect(log_histogram.set_log_scale)

    gain = OptionalSpinBox(double_spinbox(2.0, 1e-3, 1e3, 0.1, 3), auto_text="estimate per frame")
    chips = []
    for level in Status:
        chip = QLabel(f"● {level.value}")
        style_status_label(chip, level)
        chips.append(chip)
    status_row = flow_row(*chips)
    form = QFormLayout()
    form.addRow("gain (ADU/e-)", gain)
    form.addRow("model", QComboBox())
    expert = QWidget()
    expert.setLayout(form)

    pager = StepPager()
    for i, title in enumerate(("Camera", "Detect", "Filter")):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.addWidget(note_label(f"Step {i + 1}: {title}. Pages that aren't showing take no height."))
        for _ in range(i * 3):
            page_layout.addWidget(QPushButton(f"{title} control"))
        pager.add_page(title, page)

    left = QWidget()
    left_layout = QVBoxLayout(left)
    left_layout.addWidget(QLabel("<b>HistogramRangeWidget</b> (labels, spinboxes)"))
    left_layout.addWidget(histogram)
    left_layout.addWidget(readout)
    left_layout.addWidget(QLabel("<b>tinted, no spinboxes</b>"))
    left_layout.addWidget(tinted)
    left_layout.addWidget(QLabel("<b>D_um2_s, log-scale toggle</b>"))
    left_layout.addWidget(log_histogram)
    left_layout.addWidget(log_scale_check)
    left_layout.addWidget(QLabel("<b>Status levels</b>"))
    left_layout.addWidget(status_row)
    left_layout.addWidget(CollapsibleSection("Expert settings (OptionalSpinBox)", expert))
    left_layout.addWidget(QLabel("<b>StepPager</b>"))
    left_layout.addWidget(pager)
    left_layout.addStretch()

    # Right: filter panel driving a table
    model = ColumnTableModel()
    view = QTableView()
    view.setModel(model)
    view.setSortingEnabled(True)
    view.verticalHeader().setVisible(False)
    filters = FilterPanel(noun="spots")
    filters.set_source(table, offered=["flux", "fit_sigma", "D_um2_s", "alpha"])
    filters.add_filter("flux")

    def refresh() -> None:
        mask = filters.mask()
        model.set_columns({k: v[mask] for k, v in table.items()})

    filters.filtersChanged.connect(refresh)
    refresh()

    right = QSplitter(Qt.Orientation.Vertical)
    right.addWidget(scrolled(filters))
    right.addWidget(view)

    root = QWidget()
    root.setWindowTitle("qtkit gallery")
    layout = QHBoxLayout(root)
    splitter = QSplitter()
    splitter.addWidget(scrolled(left))
    splitter.addWidget(right)
    layout.addWidget(splitter)
    root.resize(1000, 700)
    return root


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(argv)
    if "--dark" in argv:
        app.setStyle("Fusion")
        app.setPalette(dark_palette())
    elif "--light" in argv:
        app.setStyle("Fusion")
        app.setPalette(app.style().standardPalette())
    window = build()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
