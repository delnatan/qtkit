# qtkit

Reusable Qt widgets and interaction patterns for scientific image-analysis
apps: napari dock widgets, standalone vispy/Qt viewers (pyvistra), and
anything else in the `microscopy` workspace that puts a control next to data.

Pure `qtpy` + `numpy` + `superqt`. Nothing here imports napari, polars or
matplotlib at module level.

## Contracts every widget follows

- **Chrome follows the palette, meaning does not.** Backgrounds, text and
  plot bars come from the widget's `QPalette`, so a widget reads correctly
  under napari's theme, an app's global stylesheet, or the OS theme, light or
  dark. Status colors (`qtkit.colors.Status`: ok / caution / error / running
  / ...) are fixed, because a green "ok" has to stay green.
- **Programmatic setters are silent.** `set_data`, `set_range`, `set_source`,
  `set_filters` never emit the widget's change signals; only a user's action
  does. Restoring saved state never reads as the user changing it.
- **Live vs. committed.** Anything draggable emits `...Changed` on every
  movement and `...Committed` once when the gesture ends. Connect cheap
  feedback to the first and expensive recomputation to the second (or
  debounce the first).
- **Narrow and short containers are the default.** No widget lets a long
  label, a row of controls or a tall page set its container's minimum size
  (see `qtkit.layouts`).
- **Plain data at the boundary.** A filter is a `FilterSpec`
  (`{column: (lo | None, hi | None)}`), a table is `{name: numpy array}`. Both
  serialize to JSON/TOML as they are and need no Qt to apply.

## What lives where

| Module | Contents |
|---|---|
| `colors` | `Status` levels and their colors; `dim_color` for theme-aware shading |
| `labels` | `status_label` / `set_status` result lines, `note_label` explanations |
| `layouts` | `scrolled`, `wrapping_label`, `FlowLayout` / `flow_row`, `hline` |
| `sections` | `CollapsibleSection`, `StepPager` (one step of a flow at a time) |
| `spinbox` | adaptive decimals/step for a data range, `OptionalSpinBox` (value or "auto") |
| `histogram` | `HistogramCanvas` (drag handles or the window between them), `HistogramRangeWidget` (with spinboxes); `set_log_scale(bool)` for log-spaced bins, adaptive (Freedman-Diaconis) bin count by default |
| `filters` | `FilterSpec`, `filter_mask`, `FilterPanel` (stacked histogram range filters, "N of M pass") |
| `table` | `ColumnTableModel`: sortable read-only table over numpy columns (missing values last) |
| `plot` | `PlotWindow` for matplotlib figures, `AxisPicker` (x/y column + log toggles) — needs `qtkit[plot]` |
| `napari` | `live_layer` (held layers can vanish), `tabify_with_open_widget` |
| `gallery` | every widget on synthetic data: `python -m qtkit.gallery [--dark\|--light]` |

### Filters in one example

```python
from qtkit import FilterPanel, columns_of, filter_mask

panel = FilterPanel(noun="tracks")
panel.set_source(columns_of(tracks_df), offered=["track_length", "mean_step_um"])
panel.filtersChanged.connect(redraw_preview)      # live
panel.filtersCommitted.connect(recompute_stats)   # once per gesture

spec = panel.filters()           # {"track_length": (5.0, None)}
keep = filter_mask(columns_of(tracks_df), spec)   # same rule, no Qt
```

A handle left at its column's data extreme means *unbounded* on that side, so
an untouched row is not a filter and never appears in the spec.

## Using it from a sibling project

As a workspace member (the `microscopy` workspace):

```toml
[tool.uv.sources]
qtkit = { workspace = true, editable = true }
```

Or as a path dependency from a project with its own environment:

```toml
[tool.uv.sources]
qtkit = { path = "../qtkit", editable = true }
```

## Development

```
uv sync
uv run pytest            # uses pytest-qt; QT_QPA_PLATFORM=offscreen works headless
uv run python -m qtkit.gallery --dark
```

Anything touching drawing or sizing: open the gallery, drag the window narrow
and short, flip `--dark`/`--light`, and look.

## Next up

- Task runner: one worker slot, progress, cancel, errors surfaced (from
  spt-pipeline's run machinery and pyvistra's `BufferProcessingRunner`).
- Status file list: folder of inputs with per-row status, keybindings, drag
  and drop (spt-pipeline's experiment list + pyvistra's
  `FlaggableFileListWidget`).
- Theme: pyvistra's design tokens and stylesheet as an opt-in app theme.
- `ColorButton`, and a napari layer manager (owned layers updated in place).
