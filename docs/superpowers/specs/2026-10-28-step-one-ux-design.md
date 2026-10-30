# Step 1: workspace experience and clickable prototype

Date: 2026-10-28. Scope authorized by the user's request to start Step 1 of the UI-first implementation sequence. Visual direction selected by the user: a light workspace with a dark sidebar, using CloakMill's existing forest-green and lime brand.

## Goal and boundary

Make the complete user journey concrete before building the production frontend or backend. Deliver a locally served, dependency-free browser prototype using fictional fixture data. It must not accept, parse, upload, or make privacy claims about real files. Every screen carries a visible prototype/sample disclosure. The production API, authentication, actual ingestion, entity recognition, file rewriting, and deployment bundle remain later steps.

## Experience

Use an operational workspace rather than a marketing landing page. A dark forest navigation rail frames a warm light canvas, restrained lime actions, compact evidence tables, and deliberate serif headings. Bundle fonts locally with their licenses. Prioritize readable contrast, keyboard focus, semantic controls, mobile navigation, and reduced-motion support.

Screens: overview, sources, discovery, identity review, replacement profiles, before/after preview, validation, and releases. The main path is create a demo project, load fictional samples, run a labeled sample scan, resolve two identity decisions, explicitly exclude an unsupported file, freeze mappings, inspect previews, run illustrative validation, and download a clearly labeled fictional JSON bundle.

The initial project is populated so reviewers immediately see a useful workspace. A new-project action exposes the empty journey. Reset restores the fictional sample state. Data and decisions remain in memory for the tab; no background analytics, external services, or browser storage of datasets.

## Fixtures and interactions

Three covered fictional sources contain twelve fixture records: a directory CSV, a JSON conversation export, and text handoff notes. One encrypted PDF is an unsupported sample with no embedded customer content. Four people, one shared account, and one organization appear across the fixtures. Example domains use `.example`.

Two review decisions illustrate common failures: an ambiguous first name shared by two people, and a shared finance account appearing next to a person's signature. Review actions must distinguish the entities and show the source evidence. A source exclusion is explicit and appears in the release coverage summary.

Approved mapping profiles have two fictional alternatives. Changes to identity decisions, source scope, or the replacement profile invalidate the current frozen snapshot and validation. A historical sample release, once created, retains its original fictional payload.

## Release and state contract

An export is blocked until a sample scan has completed, both identity decisions are resolved, unsupported content is explicitly excluded, the mapping snapshot is frozen, and validation refers to that same revision. Validation cannot be marked successful when prerequisites are missing. Downloaded payloads identify themselves as illustrative fixture output, contain transformed sample records, and omit original-to-synthetic mapping tables and source identities.

The sample renderer uses authored fixture spans rather than suggesting that a general-purpose replacement engine exists. All processing progress and validation results are labeled as sample behavior. Interrupted scans and resets must not let stale timers mutate a newer project.

## Error and accessibility states

Include a blank-project-name error, an empty project, running sample scan, unresolved identity, unsupported-source blocker, invalidated validation after editing, and pre-release empty state. The prototype does not read files dropped on it; it explains the sample-only boundary instead.

Use native dialogs for project creation and reset confirmation, accessible names for icon actions, keyboard navigation, visible focus, and non-color-only status labels. Check desktop and mobile layouts without document-wide horizontal overflow. Dense data tables may scroll within their own containers.

## Repository placement and validation

Store the design under `prototypes/workspace/`, outside the production Python package and future `apps/review-ui/`. Keep the shell, visual tokens, fixtures, workflow model, and screen templates separate. Add a concise local run guide and UX review checklist.

Verify state transitions with meaningful native Node tests: release gating, invalidation, unsupported-source exclusion, and omission of private mappings from the fictional bundle. Browser-check the full happy path, blocked paths, navigation, project creation, reset, keyboard dialogs, download contents, responsive layout, local font loading, and absence of external runtime requests. Use only synthetic data throughout.
