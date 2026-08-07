<!--
SYNC IMPACT REPORT
==================
Version change: (none — initial constitution) → 1.0.0
Modified principles: N/A (first ratification)
Added sections:
  - Core Principles (5 principles)
  - Code Quality Standards
  - Development Workflow
  - Governance
Templates reviewed:
  - .specify/templates/plan-template.md ✅ compatible (no changes needed)
  - .specify/templates/spec-template.md ✅ compatible (no changes needed)
  - .specify/templates/tasks-template.md ✅ compatible; note that tests are
    marked OPTIONAL in template but this constitution makes them MANDATORY —
    tasks.md generation MUST treat tests as required, not optional.
  - .specify/templates/commands/ ⚠ no command files found; skip
  - README.md ⚠ no project README found; skip
Deferred TODOs: none
-->

# PicMeasure Constitution

## Core Principles

### I. Extreme Testing Discipline (NON-NEGOTIABLE)

Every module, function, and user-facing behaviour MUST have automated tests.
Tests are written BEFORE implementation (Test-Driven Development):

- The test suite MUST be written and reviewed first; implementation begins only
  after tests are confirmed to FAIL (RED phase).
- All three TDD phases MUST be completed: RED → GREEN → REFACTOR.
- Unit tests, integration tests, and end-to-end tests are ALL required — not
  optional — for every user story.
- Minimum test coverage MUST be 90% line coverage for all source modules.
- Tests MUST cover happy paths, boundary conditions, error conditions, and
  edge cases (e.g., partial occlusion, no ruler detected, invalid parameters).
- A feature is NOT considered done until all tests pass and coverage threshold
  is met.
- Tests themselves MUST include clear docstrings explaining the scenario under
  test.

**Rationale**: This project performs scientific measurements. Incorrect results
are worse than no results. Rigorous automated testing is the primary quality
gate.

### II. Universal Configurability

Every parameter that influences behaviour MUST be externally configurable
without requiring source code changes:

- All thresholds, tolerances, file paths, unit choices, algorithm parameters,
  and performance settings MUST be exposed through a configuration system
  (configuration files or command-line arguments).
- Default values MUST be defined for every parameter and documented.
- Configuration MUST be validated at startup; invalid values MUST produce
  clear, actionable error messages before any processing begins.
- No magic numbers or hard-coded constants are permitted in implementation
  code; all numeric values MUST be named, documented constants drawn from the
  configuration system.

**Rationale**: Field conditions vary widely. Researchers must be able to tune
the system to their specific setup without touching code.

### III. Batch Operation Support

The system MUST be designed from the outset to support processing multiple
images in a single invocation:

- Single-image processing is the minimal unit; batch processing of a directory
  or a list of image files MUST be a first-class, documented mode of operation.
- Batch operations MUST produce per-image result records and a consolidated
  summary report.
- Batch processing MUST be interruptible and resumable; partially completed
  batches MUST NOT leave inconsistent output state.
- Progress reporting MUST be available for batch runs (e.g., "Processing image
  3 of 50").

**Rationale**: Scientific workflows operate on datasets, not individual images.
Batch support makes the tool viable for real research use.

### IV. Mandatory Type Annotations

All Python source code MUST use explicit type annotations throughout:

- Every function signature MUST declare parameter types and return types.
- Every module-level and class-level variable MUST carry a type annotation.
- Type annotations MUST be verified by a static type checker (e.g., mypy or
  pyright) as part of the CI/quality gate — type errors fail the build.
- Use of `Any` type MUST be explicitly justified in an inline comment; blanket
  use of `Any` is prohibited.
- Generic types MUST use the appropriate generic syntax (e.g.,
  `list[str]`, `dict[str, float]`, `Optional[Path]`).

**Rationale**: Image-processing code mixes numeric arrays, paths, optional
values, and domain objects. Type annotations prevent class of bugs that
testing alone may not catch, and make the codebase maintainable by others.

### V. Clear and Thorough Comments

All code MUST be well-commented at every level:

- Every module MUST have a module-level docstring describing its purpose, key
  classes/functions exported, and any non-obvious design decisions.
- Every class MUST have a class docstring describing its responsibility and
  invariants.
- Every public function and method MUST have a docstring that includes:
  purpose, parameter descriptions with types and valid ranges, return value
  description, and any exceptions raised.
- Non-obvious logic MUST include inline comments explaining WHY (not just
  WHAT) the code does what it does.
- Mathematical formulas or algorithm steps MUST be annotated with a reference
  or step-by-step explanation.
- Comments MUST be kept in sync with code; outdated comments are treated as
  bugs.

**Rationale**: Image-processing and computer-vision algorithms are
mathematically dense. Future maintainers and researchers must be able to
understand, verify, and extend the code without reverse-engineering intent.

## Code Quality Standards

- **Linting**: All code MUST pass a linter (e.g., ruff or flake8) with no
  warnings. Linting is enforced in CI.
- **Formatting**: Code MUST be auto-formatted (e.g., black or ruff format)
  before commit; unformatted code fails CI.
- **Dependency management**: All dependencies MUST be pinned to exact versions
  in a lock file. Unpinned dependencies are not permitted.
- **No dead code**: Unused imports, variables, or functions MUST be removed
  before merging. Linting enforces this automatically.
- **Error handling**: All error conditions MUST produce informative messages.
  Silent failures (bare `except: pass`) are prohibited.
- **Logging**: Structured logging MUST be used throughout; print statements
  are prohibited in library/service code. Log levels MUST be configurable.

## Development Workflow

1. **Spec first**: A feature specification (`spec.md`) MUST exist and be
   reviewed before implementation begins.
2. **Write tests (RED)**: Implement all tests for the feature; confirm they
   fail.
3. **Implement (GREEN)**: Write the minimum code to make tests pass.
4. **Refactor (IMPROVE)**: Clean up code, ensure coverage ≥90%, fix type
   errors, ensure comments are complete.
5. **Quality gates**: Linting, formatting, type checking, and test suite MUST
   all pass before a task is marked complete.
6. **Commit**: Each completed task or logical unit is committed separately with
   a descriptive commit message following conventional commits format.
7. **Batch validation**: For any feature touching the processing pipeline,
   validate with a small batch of test images before marking the story done.

## Governance

This constitution supersedes all other coding conventions or informal
agreements on this project. Any practice not covered here defaults to
Python community standards (PEP 8, PEP 484, PEP 257).

**Amendment procedure**:
- Amendments require an explicit update to this file via `/speckit-constitution`
  with written justification.
- Any amendment that removes or weakens a principle requires a written
  explanation of the risk accepted.
- Version MUST be incremented according to semantic versioning rules defined
  in the constitution versioning policy (MAJOR/MINOR/PATCH).

**Compliance review**:
- Constitution compliance MUST be checked at every code review.
- The plan-template `Constitution Check` gate MUST reference the active
  principles from this file.

**Version**: 1.0.0 | **Ratified**: 2026-04-27 | **Last Amended**: 2026-04-27
