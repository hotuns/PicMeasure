# Tasks: Tree Branch Image Measurement

**Feature Branch**: `001-branch-image-measure`
**Input**: Design documents from `specs/001-branch-image-measure/`
**Prerequisites**: [plan.md](plan.md) (required), [spec.md](spec.md) (required), [data-model.md](data-model.md), [contracts/cli-contract.md](contracts/cli-contract.md), [research.md](research.md), [quickstart.md](quickstart.md)

**Tests**: Per the project constitution (Principle I: Extreme Testing), tests are **MANDATORY** for all user stories. Unit, integration, and end-to-end tests MUST be written before implementation (TDD: RED → GREEN → REFACTOR). Minimum 90% line coverage required.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and directory structure

- [ ] T001 Create `src/` and `tests/` directory structure per implementation plan in [plan.md](plan.md)
- [ ] T002 Create `pyproject.toml` with dependencies (opencv-python-headless, scipy, scikit-image, mobile-sam, typer, pydantic-settings, numpy, pytest, pytest-cov, pytest-regressions, mypy, opencv-stubs, ruff) and tool configuration
- [ ] T003 [P] Create `config.toml.example` with all algorithm defaults per [data-model.md](data-model.md)
- [ ] T004 [P] Create `tests/` subdirectory structure (`unit/`, `integration/`, `e2e/`, `fixtures/images/`, `fixtures/regression/`)
- [ ] T005 Install dependencies and verify environment with `pip install -e .`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T006 [P] Create `AppConfig` and all sub-config pydantic models (`RulerConfig`, `SegmentationConfig`, `CameraConfig`, `OutputConfig`, `LoggingConfig`) in `src/picmeasure/config.py`
- [ ] T007 [P] Create package `src/picmeasure/__init__.py` with version and structured logging setup
- [ ] T008 [P] Write unit tests for config validation in `tests/unit/test_config.py`
- [ ] T009 [P] Create synthetic image fixtures (ruler images, branch images) in `tests/conftest.py`
- [ ] T010 Create `MeasurementPipeline` orchestrator skeleton in `src/picmeasure/pipeline.py`

**Checkpoint**: Foundation ready — user story implementation can now begin in parallel

---

## Phase 3: User Story 1 — Scale Calibration from Ruler (Priority: P1) 🎯 MVP

**Goal**: Detect the physical ruler in an image, compute the pixels-per-unit scale factor, and expose via the `calibrate` CLI command. This is the foundational prerequisite for all measurements.

**Independent Test**: Run `picmeasure calibrate tests/fixtures/images/synthetic_ruler.jpg` and verify JSON output contains `detected: true`, `pixels_per_unit` within ±5% of ground truth, and `confidence > 0.8`.

### Tests for User Story 1 (MANDATORY — write first, ensure RED)

> **NOTE**: These tests MUST fail before implementation begins.

- [ ] T011 [P] [US1] Write unit tests for ruler detection math (Hough lines, peak detection, scale calculation) in `tests/unit/test_ruler_detector.py`
- [ ] T012 [P] [US1] Write integration tests for full ruler detection on synthetic images in `tests/integration/test_calibration_pipeline.py`
- [ ] T013 [P] [US1] Write e2e test for `calibrate` CLI command in `tests/e2e/test_cli_calibrate.py`

### Implementation for User Story 1

- [ ] T014 [P] [US1] Create `RulerDetectionResult` dataclass in `src/picmeasure/ruler/models.py`
- [ ] T015 [US1] Implement `RulerDetector` (Canny → Hough → 1D intensity profile → SciPy `find_peaks`) in `src/picmeasure/ruler/detector.py`
- [ ] T016 [US1] Add `calibrate` command to CLI in `src/picmeasure/cli.py`
- [ ] T017 [US1] Integrate ruler detection stage into `MeasurementPipeline` in `src/picmeasure/pipeline.py`

**Checkpoint**: At this point, `picmeasure calibrate <image>` works end-to-end and all US1 tests pass.

---

## Phase 4: User Story 2 — Tree Branch Dimension Measurement (Priority: P2)

**Goal**: Segment tree branches using MobileSAM, extract centerlines via skeletonization, measure width/length at multiple cross-sections, and expose via the `measure` CLI command.

**Independent Test**: Run `picmeasure measure tests/fixtures/images/synthetic_branch.jpg` and verify JSON/CSV output contains branch dimensions within ±10% of ground truth.

### Tests for User Story 2 (MANDATORY — write first, ensure RED)

> **NOTE**: These tests MUST fail before implementation begins.

- [ ] T018 [P] [US2] Write unit tests for width/length calculations and skeleton analysis in `tests/unit/test_measurer.py`
- [ ] T019 [P] [US2] Write integration tests for full measurement pipeline on synthetic images in `tests/integration/test_measurement_pipeline.py`
- [ ] T020 [P] [US2] Write e2e test for `measure` CLI command in `tests/e2e/test_cli_measure.py`

### Implementation for User Story 2

- [ ] T021 [P] [US2] Create `BranchMask` dataclass in `src/picmeasure/segmentation/models.py`
- [ ] T022 [P] [US2] Create `BranchMeasurement` dataclass in `src/picmeasure/measurement/models.py`
- [ ] T023 [US2] Implement `BranchSegmenter` (MobileSAM wrapper with automatic mask generation) in `src/picmeasure/segmentation/segmenter.py`
- [ ] T024 [US2] Implement `BranchMeasurer` (scikit-image skeletonize + width sampling) in `src/picmeasure/measurement/measurer.py`
- [ ] T025 [US2] Create `MeasurementSession` dataclass in `src/picmeasure/measurement/models.py`
- [ ] T026 [US2] Add `measure` command to CLI in `src/picmeasure/cli.py`
- [ ] T027 [US2] Wire segmentation and measurement stages into `MeasurementPipeline` in `src/picmeasure/pipeline.py`

**Checkpoint**: At this point, `picmeasure measure <image>` produces valid branch dimensions and all US2 tests pass.

---

## Phase 5: User Story 3 — Camera Parameter Input and Correction (Priority: P3)

**Goal**: Accept optional camera intrinsic parameters (focal length, sensor size, distortion coefficients) from YAML, apply OpenCV undistortion and perspective correction to improve measurement accuracy.

**Independent Test**: Run `picmeasure measure <image> --camera-config tests/fixtures/camera_calibration.yaml` and verify measurements are more accurate than without camera params.

### Tests for User Story 3 (MANDATORY — write first, ensure RED)

> **NOTE**: These tests MUST fail before implementation begins.

- [ ] T028 [P] [US3] Write unit tests for camera parameter validation and matrix construction in `tests/unit/test_camera_calibration.py`
- [ ] T029 [P] [US3] Write integration tests for camera correction pipeline in `tests/integration/test_camera_correction.py`

### Implementation for User Story 3

- [ ] T030 [P] [US3] Create `CameraParams` dataclass in `src/picmeasure/camera/calibration.py`
- [ ] T031 [US3] Implement camera parameter loading from YAML and `cv2.undistort` / perspective correction in `src/picmeasure/camera/calibration.py`
- [ ] T032 [US3] Integrate camera correction stage into `MeasurementPipeline` in `src/picmeasure/pipeline.py`

**Checkpoint**: At this point, `--camera-config` improves accuracy and all US3 tests pass.

---

## Phase 6: User Story 4 — Measurement Report Export (Priority: P4)

**Goal**: Export per-image results as JSON and CSV, generate annotated overlay images, and support batch directory processing with `--resume`.

**Independent Test**: Run `picmeasure batch tests/fixtures/images/` and verify output directory contains per-image JSON, CSV, annotated images, and `batch_summary.json`.

### Tests for User Story 4 (MANDATORY — write first, ensure RED)

> **NOTE**: These tests MUST fail before implementation begins.

- [ ] T033 [P] [US4] Write unit tests for JSON exporter output format in `tests/unit/test_json_exporter.py`
- [ ] T034 [P] [US4] Write unit tests for CSV exporter output format in `tests/unit/test_csv_exporter.py`
- [ ] T035 [P] [US4] Write integration tests for batch processing with resume in `tests/integration/test_batch_processing.py`
- [ ] T036 [P] [US4] Write e2e test for `batch` CLI command in `tests/e2e/test_cli_batch.py`

### Implementation for User Story 4

- [ ] T037 [P] [US4] Create `BatchResult` dataclass in `src/picmeasure/measurement/models.py`
- [ ] T038 [P] [US4] Implement JSON exporter per output contract in `src/picmeasure/export/json_exporter.py`
- [ ] T039 [P] [US4] Implement CSV exporter per output contract in `src/picmeasure/export/csv_exporter.py`
- [ ] T040 [US4] Implement image annotator (overlay measurements on original image) in `src/picmeasure/annotation/annotator.py`
- [ ] T041 [US4] Add `batch` command with `--resume` and progress reporting to CLI in `src/picmeasure/cli.py`
- [ ] T042 [US4] Wire export and annotation stages into `MeasurementPipeline` in `src/picmeasure/pipeline.py`

**Checkpoint**: At this point, `picmeasure batch <dir>` works end-to-end and all US4 tests pass.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, documentation, and quality gates across all user stories

- [ ] T043 [P] Create regression test reference data (golden masks, annotated images) in `tests/fixtures/regression/`
- [ ] T044 [P] Add module, class, and function docstrings across all `src/picmeasure/` modules
- [ ] T045 Run full test suite with `pytest --cov=src --cov-report=term-missing` and ensure ≥90% line coverage
- [ ] T046 Validate all `quickstart.md` commands against the implemented CLI
- [ ] T047 [P] Run `mypy src/` strict mode type-checking pass and fix all errors
- [ ] T048 [P] Run `ruff check src/ tests/` and `ruff format src/ tests/` linting/formatting pass

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — **BLOCKS all user stories**
- **User Stories (Phase 3–6)**: All depend on Foundational phase completion
  - User stories can proceed in parallel if team capacity allows
  - Or sequentially in priority order (P1 → P2 → P3 → P4)
- **Polish (Phase 7)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Starts after Foundational. No dependencies on other stories.
- **User Story 2 (P2)**: Starts after Foundational. Integrates with US1 (uses `RulerDetectionResult`) but can be mocked for independent testing.
- **User Story 3 (P3)**: Starts after Foundational. Integrates with US1/US2 but is optional; ruler-only mode works without it.
- **User Story 4 (P4)**: Starts after Foundational. Integrates with all prior stories but export can be tested with mocked sessions.

### Within Each User Story

1. Tests MUST be written and FAIL before implementation (TDD)
2. Models before services
3. Services before CLI integration
4. Core implementation before pipeline wiring
5. Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel (T003, T004)
- All Foundational tasks marked [P] can run in parallel (T006, T007, T008, T009)
- Once Foundational is complete, all four user stories can start in parallel
- All test tasks within a user story marked [P] can run in parallel
- All model/dataclass tasks within a story marked [P] can run in parallel
- All exporter tasks in US4 marked [P] can run in parallel (T038, T039)

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together (TDD — ensure RED first):
Task: "Write unit tests for ruler detection math in tests/unit/test_ruler_detector.py"
Task: "Write integration tests for ruler detection in tests/integration/test_calibration_pipeline.py"
Task: "Write e2e test for calibrate CLI in tests/e2e/test_cli_calibrate.py"

# Launch model creation for User Story 1:
Task: "Create RulerDetectionResult dataclass in src/picmeasure/ruler/models.py"
```

## Parallel Example: User Story 2

```bash
# Launch all tests for User Story 2 together:
Task: "Write unit tests for width/length calculations in tests/unit/test_measurer.py"
Task: "Write integration tests for measurement pipeline in tests/integration/test_measurement_pipeline.py"
Task: "Write e2e test for measure CLI in tests/e2e/test_cli_measure.py"

# Launch model creation for User Story 2 together:
Task: "Create BranchMask dataclass in src/picmeasure/segmentation/models.py"
Task: "Create BranchMeasurement dataclass in src/picmeasure/measurement/models.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1 (Scale Calibration)
4. **STOP and VALIDATE**: Run `picmeasure calibrate` on test images; verify ±5% accuracy
5. Demo / checkpoint

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP: ruler calibration works)
3. Add User Story 2 → Test independently → Deploy/Demo (branch measurement works)
4. Add User Story 3 → Test independently → Deploy/Demo (camera correction improves accuracy)
5. Add User Story 4 → Test independently → Deploy/Demo (batch export workflow complete)
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (ruler detection)
   - Developer B: User Story 2 (segmentation + measurement)
   - Developer C: User Story 4 (export + batch CLI) — can mock pipeline inputs
3. User Story 3 (camera) can be picked up by any developer after US1/US2 are stable
4. Stories integrate at the `MeasurementPipeline` level

---

## Task Summary

| Phase | Story | Task Count | Test Tasks | Impl Tasks |
|-------|-------|-----------|------------|------------|
| Phase 1 | — | 5 | 0 | 5 |
| Phase 2 | — | 5 | 1 | 4 |
| Phase 3 | US1 (P1) | 7 | 3 | 4 |
| Phase 4 | US2 (P2) | 10 | 3 | 7 |
| Phase 5 | US3 (P3) | 5 | 2 | 3 |
| Phase 6 | US4 (P4) | 10 | 4 | 6 |
| Phase 7 | — | 6 | 1 | 5 |
| **Total** | **—** | **48** | **14** | **34** |

- **Parallel tasks**: 26 of 48 tasks are marked [P]
- **MVP scope**: Phase 1 + Phase 2 + Phase 3 (18 tasks) delivers working ruler calibration
- **Full feature**: All phases (48 tasks) delivers complete batch measurement workflow

---

## Notes

- [P] tasks = different files, no dependencies on incomplete work
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Verify tests fail before implementing (TDD RED → GREEN → REFACTOR)
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
- Avoid: vague tasks, same-file conflicts, cross-story dependencies that break independence
