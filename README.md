<p align="center">
  <img src="docs/assets/hero.svg" alt="CloakMill — Keep the context. Change the identity. An open-source project for offline enterprise-data pseudonymization." width="100%">
</p>

<p align="center">
  <strong>Building a more useful way to prepare private enterprise data for RL training.</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="docs/assets/license.svg" alt="License: Apache 2.0" height="24"></a>
  &nbsp; <strong>Early development</strong> &nbsp; · &nbsp; <strong>Offline-first design</strong>
</p>

<p align="center">
  <a href="#why-cloakmill">Why CloakMill</a> &nbsp; / &nbsp;
  <a href="#what-were-building">The product</a> &nbsp; / &nbsp;
  <a href="#from-source-to-sanitized-dataset">Architecture</a> &nbsp; / &nbsp;
  <a href="docs/ROADMAP.md">Roadmap</a> &nbsp; / &nbsp;
  <a href="CONTRIBUTING.md">Contribute</a>
</p>

---

## Why CloakMill?

Enterprise data tells a connected story. A person appears in an email, a Slack thread, a spreadsheet, and a customer record. Those connections are what make the data useful for training agents to do real work.

Blanking out every name can break that story.

**CloakMill is being built to replace sensitive identities consistently across a dataset, while preserving the context and relationships that make it useful.**

<p align="center">
  <img src="docs/assets/identity-preview.svg" alt="Illustrative planned behavior: Maya Shah becomes Nora Reed in email, chat, and CRM records. Her email and account references change consistently, while the conversation stays connected." width="100%">
</p>

<p align="center"><sub>Illustrative example using fictional data. The transformation pipeline is not implemented yet.</sub></p>

## What we're building

| | Product goal |
| --- | --- |
| **One person. One consistent identity.** | Keep names, aliases, emails, and linked records aligned across sources. |
| **Context that stays connected.** | Preserve threads, relationships, references, and the workflows agents learn from. |
| **Your data stays with you.** | Run inside customer-controlled, fully offline or air-gapped infrastructure. |
| **Beyond plain text.** | Work toward support for messages, documents, spreadsheets, presentations, images, voice, code, and databases. |
| **Our engine. Your models.** | CloakMill-owned detection and identity logic, with your choice of self-hosted OCR, speech, and language-model APIs. |
| **Repeatable dataset releases.** | Reuse approved mappings and policies across reruns and incremental imports. |
| **Evidence before export.** | Check privacy, file integrity, and RL task usefulness before releasing a dataset. |

These are design goals. See the [roadmap](docs/ROADMAP.md) for implementation status.

## From source to sanitized dataset

**Connect your sources. Discover identities automatically. Review the exceptions.
Export a consistent, verified dataset.** This is the architecture we are building;
the processing capabilities shown below are planned.

<p align="center">
  <img src="docs/assets/platform-architecture.svg" alt="Planned architecture: source collectors feed a customer-controlled pipeline for extraction, automatic detection, identity resolution, consistent replacement, verification and release. Customers choose self-hosted OCR, speech and LLM APIs; humans review grouped exceptions." width="100%">
</p>

| Bring in | Process inside your environment | Receive |
| --- | --- | --- |
| **Slack, Google Workspace, Microsoft 365** exports and planned collectors | Discover people, accounts and sensitive fields across connected records | Consistent synthetic identities across conversations and datasets |
| **S3, Azure Blob, local folders and database snapshots** | Track source coverage, versions and relationships | Qualified native files or structured JSONL/CSV/Parquet datasets |
| **PDF, Word, Excel, PowerPoint and images** | Native extraction plus your selected self-hosted OCR API | Verified derivatives with explicit supported surfaces and exclusions |
| **Voice recordings** | Self-hosted transcription, timing and content analysis | Sanitized transcripts; audio output requires separate media and speaker-identity checks |

**Automatic discovery is the core.** Thousands of repeated mentions should become
connected identities, with supported links resolved by policy. Human review handles
grouped ambiguity and conflicts, alongside sampled audits of automatic decisions.
We will measure detection errors and review workload rather than promise an
unverified automation rate.

**No Presidio dependency. No required cloud AI.** We are building our own detection
and identity engine. You will choose self-hosted model APIs using evaluated presets or
a qualified custom endpoint. Third-party parsers, runtimes and weights remain
replaceable, separately licensed components.

Live cloud collectors operate outside an air gap and produce import packages.
Processing and model APIs stay inside your infrastructure. Synthetic replacement
is the default; policy can also remove sensitive content or exclude an artifact.
Originals and private identity mappings are never training-data output.

→ [Full platform architecture](docs/architecture/overview.md) &nbsp; · &nbsp;
[Connectors and formats](docs/architecture/connectors-and-formats.md) &nbsp; · &nbsp;
[Our detection engine](docs/architecture/discovery-and-identity.md)

→ [Choose self-hosted models](docs/architecture/model-providers.md) &nbsp; · &nbsp;
[Deterministic transformation and verification](docs/architecture/outputs-and-verification.md)

## Built for the people building training data

- **RL data vendors** preparing enterprise datasets for model developers.
- **Enterprise data teams** creating controlled, reusable versions of internal data.
- **Researchers and environment builders** who need realistic, connected worlds for agents.

## Where we are today

**The repository foundation and first Next.js workspace increment are in place.** They include the project structure, visual system, sample projects, source inventory, architecture, development tooling, synthetic examples, and contribution guidelines.

A [clickable workspace prototype](prototypes/workspace/README.md) now explores the complete user journey with fictional data, including identity review, before/after previews, release blockers, and a sample download.

The first product milestone is **offline folders, structured records, and Slack/email export packages**, with consistent identity mapping and verifiable output. Production connectors, transformation, a CLI, and the persistent review application are still ahead. There is no end-user release to install yet.

→ [Follow the roadmap](docs/ROADMAP.md) &nbsp; · &nbsp; [Explore the design](docs/architecture/overview.md)

## Help shape CloakMill

Bring a difficult identity-matching case, a format edge case, an evaluation idea, or a contribution. Use fictional examples when discussing data.

Start with the [contribution guide](CONTRIBUTING.md), [developer setup](docs/development/getting-started.md), or [feature requests](https://github.com/deep-chokshi/cloakmill/issues/new?template=feature_request.yml).

## Open source, by design

Licensed under [Apache 2.0](LICENSE). Built for a community of data, privacy, and ML practitioners. [Licensing details](docs/licensing.md).

<sub>Identity replacement is pseudonymization, not a guarantee of anonymity. Sensitive facts and unique patterns require their own evaluation. CloakMill is in early development and is not ready for production data.</sub>
