"""Helpers for dock widgets living inside napari. Nothing here imports
napari itself -- the viewer is passed in -- so this module is safe to
import from code that may run without it."""

from __future__ import annotations

from qtpy.QtCore import QTimer
from qtpy.QtWidgets import QWidget


def live_layer(viewer, layer):
    """`layer` if it is still in `viewer`, else None.

    A widget that holds on to a layer it created (an overlay, a preview)
    must check before each use: anything can remove a layer -- the user,
    or another widget clearing the viewer -- and writing to a removed layer
    raises nothing and shows nothing, so the overlay just silently stops
    appearing. Recreate it when this returns None."""
    return layer if layer is not None and layer in viewer.layers else None


def tabify_with_open_widget(viewer, widget: QWidget, sibling_class_name: str) -> None:
    """Land `widget`'s dock as a tab on an already-open dock whose inner
    widget's class is named `sibling_class_name`, instead of napari's
    default of stacking a second dock below the first.

    Matched by class name so the two widgets needn't import each other.
    Deferred a tick because this is meant to be called from the widget's
    `__init__`, before napari has wrapped it in its dock. Uses the
    QMainWindow behind `viewer.window`, which is private napari API but is
    the route napari itself uses to tabify docks."""

    def _tabify() -> None:
        own_dock = widget.parent()
        if own_dock is None:
            return
        for inner in viewer.window.dock_widgets.values():
            if type(inner).__name__ != sibling_class_name:
                continue
            sibling_dock = inner.parent()
            if sibling_dock is not None and sibling_dock is not own_dock:
                viewer.window._qt_window.tabifyDockWidget(sibling_dock, own_dock)
                own_dock.show()
                own_dock.raise_()
            return

    QTimer.singleShot(0, _tabify)
