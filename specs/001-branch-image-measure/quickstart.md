# Quickstart: PicMeasure — Tree Branch Image Measurement

**Feature**: 001-branch-image-measure
**Date**: 2026-04-27

---

## Prerequisites

- Python ≥ 3.11
- A physical ruler visible in each photograph
- Images in JPEG, PNG, or TIFF format
- MobileSAM model weights (optional — OpenCV fallback is used when weights are absent)

---

## Installation

```bash
# Clone the repository
git clone <repo-url> picmeasure
cd picmeasure

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate           # Windows

# Install the package and dependencies
pip install -e ".[dev]"

# (Optional) Download MobileSAM model weights (~40 MB) for higher accuracy
# Place weights at the path configured in config.toml:
#   [segmentation]
#   model_checkpoint_path = "models/mobile_sam.pt"
```

---

## Quickstart: Measure a Single Image

```bash
# Measure one image using default config (ruler in mm, output to ./output/)
picmeasure measure photo.jpg

# Specify unit and output directory
picmeasure measure photo.jpg --unit mm --output-dir results/

# Check the results
ls results/
# photo_result.json   photo_result.csv   photo_annotated.jpg
```

---

## Quickstart: Batch Process a Directory

```bash
# Process all JPEG images in a directory
picmeasure batch ./field_photos/ --output-dir ./results/

# Resume an interrupted batch (skip already-processed images)
picmeasure batch ./field_photos/ --output-dir ./results/ --resume

# Watch progress
picmeasure batch ./field_photos/ --workers 4 --verbose
```

---

## Quickstart: Verify Ruler Detection Before Fieldwork

```bash
# Run only calibration (no branch measurement) to check camera setup
picmeasure calibrate test_photo.jpg --unit mm
# Prints: pixels_per_unit, confidence, tick_count
```

---

## Configuration

Copy and edit the default config:

```bash
cp config.toml.example config.toml
# Edit config.toml with your ruler and camera settings
picmeasure measure photo.jpg --config config.toml
```

Key settings in `config.toml`:

```toml
[ruler]
known_unit = "mm"         # Physical unit of your ruler
known_mark_spacing = 1.0  # mm between tick marks (1.0 for standard mm ruler)

[segmentation]
model = "mobile_sam"      # Use "sam" for higher accuracy (slower)

[output]
format = "both"           # "json", "csv", or "both"
output_dir = "./output"
```

---

## Using Camera Calibration

If you have camera intrinsic parameters (improves accuracy for non-ideal angles):

```bash
# Create a camera config YAML
cat > camera.yaml << EOF
focal_length_mm: 24.0
sensor_width_mm: 23.5
distortion_coefficients: [-0.12, 0.08, 0.001, -0.0005, 0.0]
EOF

picmeasure measure photo.jpg --camera-config camera.yaml
```

---

## Reading Results

### JSON result (per image):
```bash
cat results/photo_result.json | python -m json.tool
```

### CSV result (for spreadsheet analysis):
```bash
# Open in Excel/LibreOffice directly, or load with pandas:
python -c "import pandas as pd; print(pd.read_csv('results/photo_result.csv'))"
```

### Batch summary:
```bash
cat results/batch_summary.json | python -m json.tool
```

---

## Running Tests

```bash
# Run full test suite with coverage
pytest --cov=src --cov-report=term-missing

# Run only unit tests (fast)
pytest tests/unit/

# Run integration tests
pytest tests/integration/

# Run type checking
mypy src/
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "No ruler detected" | Ensure ruler covers >10% of image width; check lighting |
| Processing >30s per image | Switch to `model = "mobile_sam"` in config |
| Type errors from mypy | Run `mypy src/` and fix before committing |
| Config validation error | Check error message — it includes the field name and valid range |
| Batch stops mid-run | Re-run with `--resume` to continue from where it stopped |
