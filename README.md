# PicMeasure

PicMeasure is a local image measurement workbench for tree branches. Python and OpenCV
provide reference-ball calibration, edge-assisted point selection, stereo correspondence,
and 3D triangulation. The browser interface provides one workspace for calibration, length,
and diameter measurements.

## Run

```bash
uv sync --extra dev
uv run picmeasure gui
```

`picmeasure gui` now opens the browser workbench at `http://127.0.0.1:8765`. The previous
Tkinter and Matplotlib interface remains available as `uv run picmeasure legacy-gui` during
the migration period.

## Frontend development

```bash
cd web
npm install
npm run dev
```

Run the Python API separately with `uv run picmeasure web --no-open`. The Vite development
server proxies `/api` requests to the local Python service.

## Verification

```bash
uv run pytest
uv run ruff check src tests
cd web && npm run build && npm run lint
```
