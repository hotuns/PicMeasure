# Research: Tree Branch Image Measurement

**Feature**: 001-branch-image-measure
**Date**: 2026-04-27
**Status**: Complete — all NEEDS CLARIFICATION resolved

---

## 1. Ruler Detection and Scale Calibration

**Decision**: OpenCV with Hough Line Transform + SciPy 1D peak detection

**Rationale**:
- OpenCV is the industry standard for low-level feature extraction in Python
- Pillow handles only basic image I/O; scikit-image's contour approach is
  less robust to noise than a 1D intensity profile approach
- SciPy's `find_peaks` is more robust to lighting variation than 2D contour
  detection for evenly spaced ruler tick marks

**Approach**:
1. Canny edge detection to find ruler boundaries
2. Probabilistic Hough Line Transform to identify the ruler long axis
3. Extract 1D intensity profile along ruler axis
4. Apply `scipy.signal.find_peaks` to locate tick mark positions
5. Compute pixels-per-unit from mean inter-tick spacing

**Alternatives considered**:
- Pillow: Insufficient for sub-pixel feature extraction — rejected
- scikit-image contours only: Too sensitive to background noise — rejected
- Template matching: Fails when ruler is at an angle — rejected as primary
  method (kept as fallback)

---

## 2. Branch Segmentation

**Decision**: MobileSAM (Segment Anything Model, lightweight variant) for
segmentation mask; scikit-image `skeletonize` for centerline extraction and
width measurement

**Rationale**:
- Traditional OpenCV contour detection fails on natural backgrounds with
  texture noise and overlapping foliage — not acceptable for field use
- SAM provides state-of-the-art zero-shot segmentation and runs offline
- MobileSAM is significantly faster than the full SAM model (suitable for
  <30s per image target) and runs on CPU
- scikit-image skeleton gives medial axis for accurate width measurement
  at multiple cross-sections

**Approach**:
1. User provides a point prompt or bounding box on the branch; system runs
   MobileSAM to generate binary mask
2. `skeletonize` extracts centerline from mask
3. Width at each skeleton point = 2 × distance from skeleton pixel to
   nearest mask boundary pixel
4. Length = arc length of the skeleton in pixels × calibration scale

**Alternatives considered**:
- OpenCV contours alone: Insufficient for natural backgrounds — rejected
- Full SAM model: Too slow (>30s target) without GPU — rejected as default
  (MobileSAM is the default; full SAM is configurable)
- Watershed segmentation: Requires manual seed points; less user-friendly — rejected

---

## 3. Camera Parameter Handling and Perspective Correction

**Decision**: OpenCV (`cv2.undistort`, `cv2.getPerspectiveTransform`,
`cv2.warpPerspective`)

**Rationale**:
- OpenCV is the absolute standard for photogrammetry and camera calibration
  in Python
- Handles both lens distortion (radial/tangential coefficients) and
  homography-based perspective correction

**Approach**:
1. Camera intrinsic matrix (K) and distortion coefficients (D) stored in a
   user-provided YAML camera calibration file or as CLI parameters
2. `cv2.undistort` removes lens distortion before any measurement
3. If ruler and branch are non-coplanar, `cv2.getPerspectiveTransform` and
   `cv2.warpPerspective` apply planar correction using the ruler plane
4. Ruler-only mode (no camera params): measurements proceed without
   undistortion; calibration report includes a coplanarity assumption warning

**Alternatives considered**:
- Custom homography implementation: Unnecessary, OpenCV is battle-tested — rejected

---

## 4. Configuration Management

**Decision**: `pydantic-settings` with TOML configuration file

**Rationale**:
- Type validation and range checking are critical for scientific accuracy
- `pydantic-settings` provides automatic TOML/YAML loading with strict type
  enforcement and environment variable overrides
- `dynaconf` is overkill for a single-purpose CLI tool
- `configparser`/`tomllib` lack automatic type validation

**Config file format**: TOML (`config.toml`)
- All algorithm thresholds, tolerances, paths, and unit preferences
  configurable
- Default `config.toml` shipped with the project; users override by
  supplying `--config path/to/config.toml`
- Configuration validated at startup; invalid values produce actionable errors
  before processing begins

**Alternatives considered**:
- dynaconf: Over-engineered for this scope — rejected
- configparser: No type validation — rejected
- CLI-only parameters: Insufficient for complex nested config — rejected as
  primary mechanism (CLI can override individual config values)

---

## 5. CLI Framework

**Decision**: Typer

**Rationale**:
- Built on Click but uses Python type annotations natively
- Handles batch processing naturally via `List[Path]` arguments
- Easier to maintain than argparse; more pythonic than raw Click
- Integrates cleanly with pydantic-settings for config layering

**Batch processing design**:
- `picmeasure measure <image> [<image> ...]` — one or more images
- `picmeasure batch --input-dir DIR [--pattern "*.jpg"]` — directory mode
- `--resume` flag to skip already-processed images in batch mode

**Alternatives considered**:
- argparse: No type annotation integration — rejected
- Click: Typer is strictly better with type hints — rejected

---

## 6. Testing Strategy

**Decision**: pytest + pytest-regressions + synthetic test images

**Rationale**:
- Testing "fuzzy" image algorithms requires regression-based comparison,
  not bit-for-bit equality
- IoU (Intersection over Union) for mask comparison; SSIM for visual
  similarity
- Synthetic test images (generated with known ground truth) allow precise
  acceptance testing (ruler at known scale, branches at known dimensions)

**Testing layers**:
| Layer | What is tested | Tool |
|-------|---------------|------|
| Unit | Math functions, scale calculation, width extraction | pytest |
| Integration | Pipeline stages on synthetic images | pytest + fixture images |
| End-to-end | Full CLI invocation on test image set | pytest + subprocess |
| Regression | Output masks and annotated images | pytest-regressions |
| Coverage | ≥90% line coverage enforced | pytest-cov |

**Ground truth fixtures**:
- Synthetic ruler images with known pixel spacing
- Synthetic branch images with known widths and lengths
- Real reference images with manually-measured ground truth stored in
  `tests/fixtures/ground_truth.json`

**Alternatives considered**:
- Bit-for-bit image comparison: Too brittle for floating-point CV algorithms — rejected
- Manual-only testing: Not repeatable — rejected

---

## 7. Static Type Checking

**Decision**: mypy with `numpy.typing` stubs and `opencv-stubs`

**Rationale**:
- OpenCV's `cv2` has poor typing support; `opencv-stubs` (PyPI) provides
  type stubs for the most common functions
- NumPy provides `numpy.typing.NDArray[np.float64]` for typed array signatures
- mypy strict mode enforced in CI

**Type annotation patterns**:
- Image arrays: `npt.NDArray[np.uint8]` for BGR images,
  `npt.NDArray[np.float64]` for computed metrics
- Optional camera params: `Optional[CameraParams]` (Pydantic model)
- Return types always explicit; no bare `Any` without justification

**Alternatives considered**:
- pyright: Also viable; mypy chosen for wider ecosystem adoption
- No type checking: Rejected by constitution — not an option

---

## 8. Export Formats

**Decision**: Both JSON and CSV, user-selectable

**Rationale**:
- JSON: Best for hierarchical data (image → branches → measurement points)
- CSV: Required for scientific interoperability (R, Excel, pandas)
- Both formats produced by default; `--output-format json|csv|both`

**JSON structure**: Nested (image metadata → branch list → measurement list)
**CSV structure**: Flat (one row per measurement; image and branch IDs repeated)

**Summary report**: For batch runs, a `batch_summary.json` consolidates
all per-image results and includes aggregate statistics.

**Alternatives considered**:
- JSON only: Loses scientific interoperability — rejected
- CSV only: Cannot represent hierarchical data cleanly — rejected

---

## Resolved Clarifications

| Originally unclear | Resolution |
|-------------------|------------|
| Batch processing scope (spec said out of scope) | Constitution Principle III mandates batch support; batch mode is IN SCOPE |
| Segmentation approach | MobileSAM (configurable to full SAM) |
| Config format | TOML via pydantic-settings |
| CLI tool | Typer |
| Type checking | mypy |
| Export formats | Both JSON and CSV |
