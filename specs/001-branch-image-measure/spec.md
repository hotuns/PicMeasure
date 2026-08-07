# Feature Specification: Tree Branch Image Measurement

**Feature Branch**: `001-branch-image-measure`
**Created**: 2026-04-27
**Status**: Draft
**Input**: User description: "我要生成一个工程，用Python编码，实现对一个图像中的树枝进行测量，图片中会放置一个标尺作为标记，通过标记和相机的参数进行确认，然后通过图像中进行测量确定树枝的尺寸"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Scale Calibration from Ruler (Priority: P1)

A researcher or field operator photographs a tree branch alongside a physical ruler. The system detects the ruler in the image and uses it to calculate the real-world scale (pixels per unit length). Once calibrated, the system can convert pixel distances to physical measurements (e.g., millimeters or centimeters).

**Why this priority**: Scale calibration is the foundational prerequisite for all measurements. Without accurate scale detection, no measurement is reliable.

**Independent Test**: A user provides a test image containing a ruler and the system reports the detected scale (pixels per mm). This alone delivers value by confirming the ruler is recognized and calibration is complete.

**Acceptance Scenarios**:

1. **Given** an image with a standard ruler visible, **When** the user provides the image to the system, **Then** the system identifies the ruler and calculates a scale factor (real-world length per pixel) with less than 5% error.
2. **Given** an image where the ruler occupies at least 10% of the frame width, **When** calibration is performed, **Then** the system reports the scale factor and confidence level.
3. **Given** an image with no detectable ruler, **When** calibration is attempted, **Then** the system reports a clear error message indicating that no ruler was found.

---

### User Story 2 - Tree Branch Dimension Measurement (Priority: P2)

After scale calibration, the user selects or the system automatically identifies one or more tree branches in the image. The system measures the branch dimensions — primarily diameter/width at specified points and optionally length along visible segments — and reports them in real-world units.

**Why this priority**: This is the core deliverable of the tool. After calibration, the system must produce actual measurements.

**Independent Test**: Given a calibrated image, the user designates a branch segment and receives diameter and length measurements in physical units (mm/cm). Correct result can be verified against manual measurement.

**Acceptance Scenarios**:

1. **Given** a calibrated image and a user-specified branch region, **When** measurement is requested, **Then** the system returns branch diameter and/or length in real-world units (mm or cm).
2. **Given** a branch measurement, **When** the measured value is compared to a ground-truth manual measurement, **Then** the result is within ±10% of the actual dimension.
3. **Given** an image with multiple visible branches, **When** the user selects a specific branch, **Then** only that branch is measured without interference from adjacent branches.

---

### User Story 3 - Camera Parameter Input and Correction (Priority: P3)

For advanced accuracy, the user can provide camera intrinsic parameters (focal length, sensor size, or known capture distance). The system uses these parameters to refine scale calculations, especially when the ruler is not coplanar with the branch or the image has perspective distortion.

**Why this priority**: Camera parameters improve accuracy in non-ideal field conditions but are optional — the ruler-only mode already provides useful measurements for most use cases.

**Independent Test**: A user provides camera parameters alongside the image; the system applies distortion correction and reports an adjusted scale and measurements. Accuracy improvement over uncorrected measurement can be verified.

**Acceptance Scenarios**:

1. **Given** camera intrinsic parameters are provided, **When** measurements are performed, **Then** the system applies perspective correction and the measurements are more accurate than without the parameters.
2. **Given** camera parameters are not provided, **When** measurements are performed, **Then** the system still produces measurements based solely on the ruler reference without error.
3. **Given** invalid camera parameters (e.g., negative focal length), **When** the user submits them, **Then** the system reports a validation error with a clear description of the problem.

---

### User Story 4 - Measurement Report Export (Priority: P4)

After completing measurements, the user can export the results as a structured report (e.g., CSV or JSON) containing branch ID, measured dimensions, scale factor used, and the source image reference.

**Why this priority**: Results must be recordable for downstream scientific or agricultural use. Export capability transforms the tool from interactive to part of a data-collection workflow.

**Independent Test**: A user runs measurements on an image and requests export; the system produces a file with all measurement data that can be opened in a spreadsheet or data analysis tool.

**Acceptance Scenarios**:

1. **Given** a completed measurement session, **When** the user requests an export, **Then** a file is produced containing at minimum: image filename, scale factor, and a list of branch measurements with dimensions in real-world units.
2. **Given** multiple branches measured in one session, **When** exported, **Then** each branch appears as a separate row/record in the output.

---

### Edge Cases

- What happens when the ruler is partially occluded by a branch or leaf?
- How does the system handle very low-contrast images where ruler markings are hard to detect?
- What if the image is rotated or the ruler is at an angle (not horizontal/vertical)?
- What if the branch is partially out of frame?
- What if there are multiple rulers in the same image?
- How does the system handle images with significant motion blur?
- What if the user provides camera parameters that conflict with ruler-derived scale?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept a single image file as input for analysis.
- **FR-002**: System MUST automatically detect the physical ruler present in the image and extract its scale markings to compute a pixels-per-unit calibration factor.
- **FR-003**: System MUST allow the user to specify the unit of measurement (millimeters or centimeters) for output values.
- **FR-004**: System MUST identify tree branch regions within the image, either automatically or via user-guided selection.
- **FR-005**: System MUST measure the width (diameter) of identified branch segments at user-specified or automatically chosen cross-sections.
- **FR-006**: System MUST measure the visible length of identified branch segments.
- **FR-007**: System MUST report all measurements in real-world units based on the computed calibration scale.
- **FR-008**: System MUST accept optional camera intrinsic parameters (focal length, sensor dimensions, capture distance) to improve measurement accuracy through perspective correction.
- **FR-009**: System MUST function correctly when camera parameters are not provided, using ruler-only calibration.
- **FR-010**: System MUST display measurement results overlaid on the original image so users can visually verify which regions were measured.
- **FR-011**: System MUST export measurement results to a structured file format (CSV or JSON) upon user request.
- **FR-012**: System MUST report a clear, human-readable error when the ruler cannot be detected in the provided image.
- **FR-013**: System MUST validate camera parameter inputs and report errors for invalid values.
- **FR-014**: System MUST support processing of common image file formats (JPEG, PNG, TIFF).

### Key Entities *(include if feature involves data)*

- **Image**: The input photograph containing one or more tree branches and a reference ruler. Key attributes: file path, format, resolution, capture metadata.
- **Ruler**: The physical measurement reference in the image. Key attributes: detected position, orientation, unit type, scale markings, computed pixels-per-unit ratio.
- **Branch**: A tree branch segment identified in the image. Key attributes: region bounds, measured width(s) at cross-sections, measured length, confidence score.
- **Measurement Session**: A single run of analysis on one image. Key attributes: source image reference, calibration scale, camera parameters used, list of branch measurements, timestamp.
- **Camera Parameters**: Optional intrinsic properties of the capture device. Key attributes: focal length, sensor width/height, capture distance, distortion coefficients.
- **Measurement Result**: A single quantified branch dimension. Key attributes: branch ID, dimension type (width/length), value, unit, measurement confidence.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Scale calibration from a ruler image produces a scale factor within ±5% of the ground-truth scale under standard imaging conditions (good lighting, ruler clearly visible).
- **SC-002**: Branch dimension measurements are within ±10% of manual ground-truth measurements for branches that are clearly visible and non-occluded.
- **SC-003**: The system processes and returns results for a standard 12-megapixel image in under 30 seconds on a typical desktop computer.
- **SC-004**: Users can complete a full workflow (load image → calibrate → measure → export) in under 5 minutes without prior training.
- **SC-005**: The system correctly reports a calibration failure message in 100% of cases where no ruler is present in the image.
- **SC-006**: At least 80% of clearly visible, non-occluded branches in test images are detected automatically without manual selection.
- **SC-007**: Exported measurement reports contain all required fields (image reference, scale factor, branch measurements with units) and can be successfully opened by standard data tools.

## Assumptions

- The physical ruler placed in the image has standard, evenly spaced, legible markings (e.g., millimeter or centimeter graduations).
- The ruler and the tree branch are approximately in the same plane (coplanar), minimizing perspective-induced measurement error; camera parameters can compensate for non-coplanar cases.
- The image quality is sufficient for automated detection — reasonably sharp, well-lit, and with adequate contrast between the ruler markings and background.
- The tool is intended for use by researchers, agronomists, or field operators with basic computer proficiency; a command-line or simple graphical interface is acceptable.
- Output measurements are intended for scientific recording and reporting, not for real-time or safety-critical applications.
- A single image is processed per session; batch processing of multiple images is out of scope for the initial version.
- The ruler's physical unit (mm or cm) is either automatically identified from image text or specified by the user; automatic OCR of ruler labels is a best-effort feature.
- Mobile or embedded deployment is out of scope; the tool runs on a desktop or laptop computer.
