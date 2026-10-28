# CloakMill roadmap

This is a direction of travel, not a delivery-date commitment. Only checked items are implemented. Every connector or format must declare its supported surfaces and known limitations before it is described as supported.

## Foundation

- [x] Project structure and Python package metadata.
- [x] Product-facing README and synthetic product illustration.
- [x] Apache-2.0 license and contribution guidance.
- [x] Architecture and development documentation.
- [x] Lint, format, package-build, and import CI configuration.

## First usable pipeline

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
