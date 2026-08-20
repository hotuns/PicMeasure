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

## Remote database configuration

Copy `remote_config.example.json` to `remote_config.json` in the project root, then fill in
the THCPN MySQL and OSS values. `remote_config.json` contains credentials and is excluded
from Git.

```text
remote_config.example.json -> remote_config.json
```

When running from source, PicMeasure reads this file from the current project directory.
The packaged application reads it from the directory containing `PicMeasure.exe` or the
macOS `PicMeasure` executable. It does not read configuration from another project or from
a machine-specific absolute path. The individual `PICMEASURE_DB_*` and
`PICMEASURE_OSS_BASE_URL` environment variables can still override values when needed.

## Frontend development

```bash
cd web
npm install
npm run dev
```

Run the Python API separately with `uv run picmeasure web --no-open`. The Vite development
server proxies `/api` requests to the local Python service.

## Build desktop package

The desktop package is a PyInstaller one-folder distribution. Build it on the same
operating system on which it will run: build the Windows EXE on Windows, and build the
macOS executable on macOS.

### Windows EXE

Install these tools first:

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- Node.js 20 or newer

Open Command Prompt or PowerShell in the project root, then run:

```bat
uv sync --extra dev
cd web
npm ci
npm run build
cd ..
build.bat
```

If `remote_config.json` exists in the project root, `build.bat` copies it beside the EXE.
Before building on another computer, create this file from `remote_config.example.json`,
or place it manually in `dist\PicMeasure` after the build.

The result is written to:

```text
dist\PicMeasure\PicMeasure.exe
```

Run `dist\PicMeasure\PicMeasure.exe` to start the local service. It opens
`http://127.0.0.1:8765` automatically. Distribute the entire `dist\PicMeasure` folder;
the EXE cannot be copied out and used by itself. Keep `stereo.toml` beside the EXE when
stereo measurement is required.

### macOS folder

From the project root, run:

```bash
uv sync --extra dev
cd web
npm ci
npm run build
cd ..
./scripts/build_bundle.sh
```

The result is written to `dist/PicMeasure`. Start it with:

```bash
./dist/PicMeasure/PicMeasure
```

The first launch of a packaged build can take several seconds while bundled dependencies
are loaded.

### Rebuild after code changes

Frontend changes under `web/src` must be compiled before packaging. Python-only changes
do not require `npm run build`, but running the complete sequence above is the recommended
release build procedure.

## Verification

```bash
uv run pytest
uv run ruff check src tests
cd web && npm run build && npm run lint
```
