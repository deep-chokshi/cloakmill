# CloakMill roadmap

This is a direction of travel, not a delivery-date commitment. Only checked items are implemented. Every connector or format must declare its supported surfaces and known limitations before it is described as supported.

## Foundation

- [x] Project structure and Python package metadata.
- [x] Product-facing README and synthetic product illustration.
- [x] Apache-2.0 license and contribution guidance.
- [x] Architecture and development documentation.
- [x] Lint, format, package-build, and import CI configuration.

## Step 1: user experience prototype

- [x] Light workspace, dark sidebar, and locally bundled brand typography.
- [x] Clickable overview, sources, discovery, identity review, profiles, preview, validation, and release screens.
- [x] Fictional dataset, ambiguous-identity and shared-account review cases.
- [x] Explicit source exclusions, frozen mapping revisions, illustrative validation, and fictional JSON download.
- [x] Empty, loading, blocked, correction, and reset states.
- [x] Behavioral tests for prototype release gates and invalidation.

This is a sample-only design artifact, separate from the production application. See the [prototype guide](../prototypes/workspace/README.md) and [UX workflow](product/ux-workflow.md).

## First usable pipeline

The UI-first sequence also includes the frontend and API milestones below. These
do not establish implemented privacy processing.

### Step 2: application frontend

- [x] Next.js App Router foundation with the approved visual system and local assets.
- [x] Sample project creation, overview, source inventory and coverage details.
- [x] Server-only sample access, bounded sessions, minimal DTOs and response hardening.
- [x] Behavioral and production-browser tests; frontend CI configuration.
- [ ] Complete identity review, profiles, preview, validation and releases in the app.
- [ ] Qualify the completed UI against the persistent API.

The [frontend guide](../apps/review-ui/README.md) describes the sample-only boundary.
No enterprise sign-in or real data ingestion is available in Step 2A.

### Step 3: persistent API and access controls

- [ ] Customer-local identity provider integration and revocable sessions.
- [ ] Server-enforced tenant/project permissions and audit events.
- [ ] Persistent project/registry storage and authenticated private Python API.
- [ ] Cross-user/tenant access, recovery and deployment verification.

See the [web security design](architecture/web-security.md) for acceptance criteria.

### Processing pipeline

- [ ] Define source records, original locators, evidence, and transformation contracts.
- [ ] Import local folders and JSON/CSV snapshots with an explicit coverage report.
- [ ] Detect known identifiers and rule-based sensitive fields.
- [ ] Resolve identities with strong anchors and abstain on ambiguous matches.
- [ ] Create versioned, namespace-scoped synthetic profiles.
- [ ] Apply deterministic replacements while preserving structured references.
- [ ] Validate privacy findings and record/schema integrity.
- [ ] Export a sealed dataset and non-sensitive release manifest through a CLI.
- [ ] Read Slack and email export packages, including linked attachments.

**Exit criterion:** a synthetic cross-source dataset retains its intended joins and relationships, repeated runs with a frozen mapping snapshot agree, and independent checks reject seeded privacy and integrity failures.

## File fidelity and review

- [ ] Qualify DOCX, XLSX, and PPTX writers by supported feature.
- [ ] Process PDFs and images, including OCR, embedded content, and metadata.
- [ ] Add a local identity-review and release-review interface.
- [ ] Introduce bounded local-model assistance where it improves evaluated accuracy.
- [ ] Replay representative RL tasks against transformed artifacts.

**Exit criterion:** each supported file surface passes reparse/render checks, unsupported content is quarantined, and selected RL tasks remain valid.

## Enterprise operations

- [ ] Add CRM, SQL, and NoSQL snapshot adapters.
- [ ] Add code working-snapshot transformation with language-specific checks.
- [ ] Support incremental imports, affected-artifact regeneration, and release revocation manifests.
- [ ] Produce signed offline installation bundles with model/license inventories.
- [ ] Verify installation and execution with external networking disabled.
- [ ] Add customer-managed keys, role-based review, backups, and recovery tests.
- [ ] Qualify distributed processing using measured customer-representative workloads.

**Exit criterion:** deployment, recovery, access controls, and processing behavior are evaluated in the target offline environment. No scale or compliance claim is implied by this roadmap.
