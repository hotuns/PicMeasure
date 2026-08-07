# Data Model: Tree Branch Image Measurement

**Feature**: 001-branch-image-measure
**Date**: 2026-04-27
**Source**: spec.md (Key Entities) + research.md decisions

---

## Core Entities

### `AppConfig`

Top-level configuration loaded from `config.toml`. All algorithm parameters
and behavioural settings live here. Validated at startup via pydantic-settings.

```
AppConfig
├── ruler: RulerConfig
├── segmentation: SegmentationConfig
├── camera: CameraConfig (optional defaults)
├── output: OutputConfig
└── logging: LoggingConfig
```

**Key fields**:
- `output_unit: Literal["mm", "cm"]` — measurement unit for all outputs
- `image_formats: list[str]` — accepted extensions (default: jpg, jpeg, png, tiff, tif)
- `processing_timeout_seconds: int` — max seconds per image (default: 30)
- `batch_resume: bool` — skip already-processed images in batch mode

---

### `RulerConfig`

Controls ruler detection algorithm parameters.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `canny_threshold_low` | `int` | `50` | Lower Canny edge threshold |
| `canny_threshold_high` | `int` | `150` | Upper Canny edge threshold |
| `hough_threshold` | `int` | `100` | Hough line accumulator threshold |
| `hough_min_line_length` | `int` | `100` | Minimum line length in pixels |
| `hough_max_line_gap` | `int` | `10` | Maximum gap between line segments |
| `peak_min_distance` | `int` | `5` | Minimum pixel distance between tick marks |
| `peak_prominence` | `float` | `0.1` | Minimum peak prominence for tick detection |
| `known_unit` | `Literal["mm","cm"]` | `"mm"` | Physical unit of ruler markings |
| `known_mark_spacing` | `float` | `1.0` | Physical distance between tick marks |
| `min_ruler_coverage` | `float` | `0.10` | Min fraction of frame width ruler must cover |

---

### `SegmentationConfig`

Controls branch segmentation algorithm parameters.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model` | `Literal["mobile_sam","sam"]` | `"mobile_sam"` | SAM model variant |
| `model_checkpoint_path` | `Path` | `models/mobile_sam.pt` | Model weights file |
| `points_per_side` | `int` | `32` | SAM automatic grid points |
| `pred_iou_thresh` | `float` | `0.88` | SAM IoU prediction threshold |
| `stability_score_thresh` | `float` | `0.95` | SAM mask stability threshold |
| `min_branch_area_pixels` | `int` | `500` | Minimum mask area to consider a branch |
| `width_sample_interval` | `int` | `5` | Skeleton pixels between width measurements |

---

### `CameraConfig`

Optional camera calibration parameters.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `focal_length_mm` | `Optional[float]` | `None` | Lens focal length in mm |
| `sensor_width_mm` | `Optional[float]` | `None` | Camera sensor width in mm |
| `sensor_height_mm` | `Optional[float]` | `None` | Camera sensor height in mm |
| `capture_distance_mm` | `Optional[float]` | `None` | Distance to subject plane in mm |
| `distortion_coefficients` | `Optional[list[float]]` | `None` | OpenCV k1,k2,p1,p2[,k3] |
| `intrinsic_matrix_path` | `Optional[Path]` | `None` | Path to YAML intrinsic matrix file |

---

### `OutputConfig`

Controls output file generation.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `output_dir` | `Path` | `./output` | Directory for result files |
| `format` | `Literal["json","csv","both"]` | `"both"` | Export format |
| `annotate_image` | `bool` | `True` | Save annotated image overlay |
| `annotation_line_color` | `tuple[int,int,int]` | `(0,255,0)` | BGR color for overlaid lines |
| `annotation_font_scale` | `float` | `0.6` | OpenCV font scale for labels |

---

### `RulerDetectionResult`

Output of the ruler detection stage.

| Field | Type | Description |
|-------|------|-------------|
| `detected` | `bool` | Whether a ruler was found |
| `pixels_per_unit` | `Optional[float]` | Calibration factor (pixels per output unit) |
| `ruler_bbox` | `Optional[tuple[int,int,int,int]]` | Ruler bounding box (x,y,w,h) |
| `orientation_degrees` | `Optional[float]` | Ruler angle from horizontal |
| `tick_count` | `Optional[int]` | Number of detected tick marks |
| `confidence` | `Optional[float]` | Confidence score [0.0, 1.0] |
| `error_message` | `Optional[str]` | Human-readable error if not detected |

---

### `BranchMask`

Binary segmentation mask for a single branch.

| Field | Type | Description |
|-------|------|-------------|
| `branch_id` | `int` | Sequential ID within the image (1-based) |
| `mask` | `npt.NDArray[np.bool_]` | 2D boolean mask (H × W) |
| `bbox` | `tuple[int,int,int,int]` | Bounding box (x,y,w,h) |
| `area_pixels` | `int` | Total mask area in pixels |
| `confidence` | `float` | SAM IoU confidence score |

---

### `BranchMeasurement`

Measured dimensions for one branch, in real-world units.

| Field | Type | Description |
|-------|------|-------------|
| `branch_id` | `int` | ID linking to BranchMask |
| `length_units` | `float` | Visible length in output unit (mm or cm) |
| `width_measurements` | `list[float]` | Width (diameter) at each sampled point |
| `width_mean_units` | `float` | Mean width across all sample points |
| `width_min_units` | `float` | Minimum width |
| `width_max_units` | `float` | Maximum width |
| `unit` | `Literal["mm","cm"]` | Output unit |
| `skeleton_point_count` | `int` | Number of skeleton points measured |

---

### `CameraParams`

Validated camera intrinsic parameters (derived from `CameraConfig`).

| Field | Type | Description |
|-------|------|-------------|
| `intrinsic_matrix` | `npt.NDArray[np.float64]` | 3×3 camera matrix K |
| `distortion_coefficients` | `npt.NDArray[np.float64]` | OpenCV distortion vector |
| `is_identity` | `bool` | True when no calibration provided |

---

### `MeasurementSession`

Complete result of processing one image.

| Field | Type | Description |
|-------|------|-------------|
| `image_path` | `Path` | Absolute path to source image |
| `image_width` | `int` | Image width in pixels |
| `image_height` | `int` | Image height in pixels |
| `timestamp` | `str` | ISO 8601 processing timestamp |
| `ruler_result` | `RulerDetectionResult` | Calibration outcome |
| `camera_params_used` | `bool` | Whether camera params were applied |
| `branches` | `list[BranchMeasurement]` | All branch measurements |
| `processing_time_seconds` | `float` | Wall-clock processing time |
| `output_unit` | `Literal["mm","cm"]` | Unit used for all measurements |
| `error` | `Optional[str]` | Top-level error if session failed |

---

### `BatchResult`

Summary of a batch processing run across multiple images.

| Field | Type | Description |
|-------|------|-------------|
| `batch_id` | `str` | UUID for this batch run |
| `started_at` | `str` | ISO 8601 batch start timestamp |
| `completed_at` | `str` | ISO 8601 batch completion timestamp |
| `total_images` | `int` | Total images submitted |
| `succeeded` | `int` | Images processed successfully |
| `failed` | `int` | Images that produced errors |
| `skipped` | `int` | Images skipped due to --resume |
| `sessions` | `list[MeasurementSession]` | Per-image results |

---

## Entity Relationships

```
AppConfig ──────────────────── configures all pipeline stages
    │
    ├── RulerConfig ────────── RulerDetector → RulerDetectionResult
    ├── SegmentationConfig ─── BranchSegmenter → list[BranchMask]
    ├── CameraConfig ──────── CameraParams (validated)
    └── OutputConfig ──────── ExportWriter

MeasurementSession
    ├── RulerDetectionResult (1:1)
    └── list[BranchMeasurement] (1:N, one per detected branch)
        └── references BranchMask (same branch_id)

BatchResult
    └── list[MeasurementSession] (1:N, one per input image)
```

---

## State Transitions

### MeasurementSession states

```
PENDING → LOADING_IMAGE → CALIBRATING → SEGMENTING → MEASURING → EXPORTING → DONE
                                                                             ↘ ERROR
```

At each transition, if a critical failure occurs (e.g., ruler not found),
the session moves to ERROR with a populated `error` field. Non-critical
failures (e.g., a single branch measurement failed) are recorded at the
`BranchMeasurement` level, not at the session level.
