# Step One UX Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task in the current session. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Deliver a polished, locally served clickable workflow that makes Step 1 reviewable without implementing the production platform.

**Architecture:** A static HTML/CSS/JavaScript prototype with authored fictional fixtures, a small explicit workflow model, reusable screen templates, and delegated browser interactions. Keep source data in tab memory, block incomplete sample releases, and separate this artifact from the Python core.

**Tech Stack:** Native JavaScript modules, CSS, semantic HTML, locally bundled OFL fonts, native Node tests, and browser interaction checks.

---

### Task 1: Record the approved scope and visual direction

- [x] Inspect repository instructions, roadmap, architecture, and existing brand visuals.
- [x] Confirm the user's visual preference: light workspace with a dark sidebar.
- [x] Record this scope in `docs/superpowers/specs/2026-10-28-step-one-ux-design.md`.
- [x] Isolate work on `codex/step-one-ux-prototype`.

### Task 2: Define fixtures and workflow behavior

**Files:** `prototypes/workspace/fixtures.mjs`, `prototypes/workspace/model.mjs`, `prototypes/workspace/model.test.mjs`.

- [x] Author twelve fictional records with explicit identity spans, six canonical entities, three covered sources, one unsupported source, and two identity-review cases.
- [x] Write behavior tests before implementing the workflow model: unresolved releases are blocked; reviewed/frozen/validated releases are allowed; source/profile/decision changes invalidate approval; original identities and mapping tables stay out of the sample bundle.
- [x] Run `node --test prototypes/workspace/model.test.mjs` and inspect expected failures before implementing the transitions.
- [x] Implement only the fixture-state transitions and authored sample rendering needed by those contracts.
- [x] Re-run the tests and inspect all results.

### Task 3: Build the complete reviewable UI

**Files:** `prototypes/workspace/index.html`, `styles.css`, `icons.mjs`, `views.mjs`, `app.mjs`, `assets/fonts/`.

- [x] Build the forest navigation rail, light workspace, project header, sample disclosure, and responsive navigation.
- [x] Add overview, sources, discovery, identity review, profiles, preview, validation, and releases screens.
- [x] Implement project creation, sample import/scan, review decisions, source exclusion, profile selection, mapping freeze, previews, illustrative validation, and sample download.
- [x] Handle blank inputs, empty projects, stale timers, reset confirmation, keyboard dialogs, and visible release blockers.
- [x] Bundle original font files and their OFL notices; make no runtime external requests.

### Task 4: Verify, document, and prepare review

**Files:** `prototypes/workspace/README.md`, `docs/product/ux-workflow.md`, `docs/ROADMAP.md`, root `README.md`, `docs/licensing.md`.

- [x] Document the local launch command, sample-only boundary, screen purpose, critical review questions, and deferred production features.
- [x] Run model tests, JavaScript syntax checks, and browser checks for the happy path and blocked/error paths.
- [x] Inspect desktop and mobile screenshots; verify no external runtime requests, missing assets, script errors, or document-wide horizontal overflow.
- [x] Update the roadmap and product introduction to describe the prototype accurately.
- [x] Review the diff and record verification evidence. Keep the repository private and do not merge into main or publish a release.


## Verification record

- Nine native Node behavior tests passed, including release prerequisites, explicit exclusions, revision invalidation, contradictory identity failure, and private-mapping omission from the fictional bundle.
- Full browser journey passed: both reviews, source exclusion, mapping freeze, before/after inspection, illustrative validation, sample release creation, and a twelve-record JSON download.
- Browser checks covered profile invalidation, the incorrect-Maya correction route, a blank-project-name error, an empty project, and the sample scan.
- Forty-eight responsive screen checks passed across eight views at widths 1440, 1280, 980, 768, 390, and 320 pixels. Dense tables scroll within their containers; the document does not overflow horizontally.
- Mobile navigation and Escape-to-dismiss dialog behavior passed. Interrupted scans cannot populate a newly created project, and project names render as text rather than markup.
- Local fonts loaded; browser interaction checks observed no external runtime requests, script errors, or missing resources.
- Desktop and mobile screenshots were inspected. Text contrast issues identified in the reviewed screens were corrected; this is not a claim of a complete accessibility audit.
- Python lint, format, import, package builds, workflow YAML parsing, and local documentation links passed.
- The production frontend/API, persistent storage, actual imports, detection, identity generation, native rewriting, and privacy assessment remain outside Step 1.
