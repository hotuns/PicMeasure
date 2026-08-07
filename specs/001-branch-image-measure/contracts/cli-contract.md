# CLI Contract: picmeasure

**Feature**: 001-branch-image-measure
**Date**: 2026-04-27
**Tool**: Typer-based CLI
**Invocation**: `picmeasure <command> [OPTIONS] [ARGS]`

---

## Commands

### `picmeasure measure`

Measure one or more images in a single invocation.

```
picmeasure measure [OPTIONS] IMAGES...
```

**Arguments**:

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `IMAGES` | `Path` (one or more) | Yes | Input image file path(s) |

**Options**:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--config` | `Path` | `config.toml` | Path to configuration TOML file |
| `--unit` | `mm\|cm` | from config | Override output measurement unit |
| `--output-dir` | `Path` | from config | Directory to write output files |
| `--output-format` | `json\|csv\|both` | `both` | Export format |
| `--annotate / --no-annotate` | `bool` | `True` | Save annotated image overlay |
| `--camera-config` | `Path` | None | Path to camera calibration YAML |
| `--verbose` | flag | False | Enable debug-level log output |

**Stdout**: Progress messages (one line per image processed)
**Exit codes**:
- `0` — all images processed successfully
- `1` — one or more images failed processing (details in output files)
- `2` — configuration or argument validation error (no processing attempted)

**Example**:
```bash
picmeasure measure branch1.jpg branch2.png \
  --unit mm \
  --output-dir results/ \
  --camera-config camera_calibration.yaml
```

---

### `picmeasure batch`

Process all images in a directory.

```
picmeasure batch [OPTIONS] INPUT_DIR
```

**Arguments**:

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `INPUT_DIR` | `Path` | Yes | Directory containing input images |

**Options**:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--config` | `Path` | `config.toml` | Path to configuration TOML file |
| `--pattern` | `str` | `"*.jpg,*.jpeg,*.png,*.tiff,*.tif"` | Glob pattern(s) for image matching |
| `--unit` | `mm\|cm` | from config | Override output measurement unit |
| `--output-dir` | `Path` | from config | Directory to write output files |
| `--output-format` | `json\|csv\|both` | `both` | Export format |
| `--resume` | flag | False | Skip images already in output directory |
| `--camera-config` | `Path` | None | Path to camera calibration YAML |
| `--verbose` | flag | False | Enable debug-level log output |
| `--workers` | `int` | `1` | Parallel worker processes (configurable) |

**Stdout**: Progress bar (image N of M) + per-image status lines
**Exit codes**: Same as `measure`

**Example**:
```bash
picmeasure batch ./field_photos/ \
  --pattern "*.jpg" \
  --output-dir ./results/ \
  --resume \
  --workers 4
```

---

### `picmeasure calibrate`

Run only ruler detection/calibration on an image, without branch measurement.
Useful for verifying camera setup before a field session.

```
picmeasure calibrate [OPTIONS] IMAGE
```

**Arguments**:

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `IMAGE` | `Path` | Yes | Input image file path |

**Options**:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--config` | `Path` | `config.toml` | Configuration TOML file |
| `--unit` | `mm\|cm` | from config | Output unit |
| `--camera-config` | `Path` | None | Camera calibration YAML |
| `--verbose` | flag | False | Debug output |

**Stdout (JSON)**:
```json
{
  "detected": true,
  "pixels_per_unit": 12.43,
  "unit": "mm",
  "tick_count": 50,
  "confidence": 0.97,
  "ruler_bbox": [120, 890, 1200, 50],
  "orientation_degrees": 1.2,
  "error_message": null
}
```

---

## Configuration File Contract (`config.toml`)

All sections and keys correspond directly to the `AppConfig` data model.
A minimal valid configuration file:

```toml
[ruler]
known_unit = "mm"
known_mark_spacing = 1.0
min_ruler_coverage = 0.10

[segmentation]
model = "mobile_sam"
model_checkpoint_path = "models/mobile_sam.pt"

[output]
output_dir = "./output"
format = "both"
annotate_image = true

[logging]
level = "INFO"  # DEBUG | INFO | WARNING | ERROR
```

---

## Camera Calibration YAML Contract (`camera_calibration.yaml`)

Compatible with OpenCV camera calibration output:

```yaml
# Camera intrinsic parameters
focal_length_mm: 24.0
sensor_width_mm: 23.5
sensor_height_mm: 15.6
capture_distance_mm: 500.0

# OpenCV distortion coefficients [k1, k2, p1, p2, k3]
distortion_coefficients: [-0.12, 0.08, 0.001, -0.0005, 0.0]

# Optional: full 3x3 intrinsic matrix (overrides focal_length + sensor if provided)
# intrinsic_matrix_path: "camera_K.yml"
```

---

## Output File Contract

### Per-image JSON (`{image_stem}_result.json`)

```json
{
  "image_path": "/absolute/path/to/image.jpg",
  "image_width": 4032,
  "image_height": 3024,
  "timestamp": "2026-04-27T10:23:45Z",
  "output_unit": "mm",
  "camera_params_used": false,
  "processing_time_seconds": 12.4,
  "ruler": {
    "detected": true,
    "pixels_per_unit": 12.43,
    "tick_count": 50,
    "confidence": 0.97,
    "orientation_degrees": 1.2
  },
  "branches": [
    {
      "branch_id": 1,
      "length_units": 145.2,
      "width_mean_units": 8.3,
      "width_min_units": 6.1,
      "width_max_units": 11.4,
      "width_measurements": [6.1, 7.5, 8.3, 9.0, 11.4],
      "unit": "mm",
      "skeleton_point_count": 5
    }
  ],
  "error": null
}
```

### Per-image CSV (`{image_stem}_result.csv`)

```
image_path,branch_id,measurement_type,value,unit,timestamp
/path/image.jpg,1,length,145.2,mm,2026-04-27T10:23:45Z
/path/image.jpg,1,width_mean,8.3,mm,2026-04-27T10:23:45Z
/path/image.jpg,1,width_min,6.1,mm,2026-04-27T10:23:45Z
/path/image.jpg,1,width_max,11.4,mm,2026-04-27T10:23:45Z
```

### Batch summary (`batch_summary.json`)

```json
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "started_at": "2026-04-27T10:00:00Z",
  "completed_at": "2026-04-27T10:45:30Z",
  "total_images": 50,
  "succeeded": 48,
  "failed": 1,
  "skipped": 1,
  "sessions": [ "...see per-image JSON schema above..." ]
}
```
