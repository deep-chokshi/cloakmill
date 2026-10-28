import {
  entities,
  profiles,
  records,
  reviewCases,
  sources,
} from "./fixtures.mjs";
import {
  canExport,
  canFreeze,
  getBlockers,
  mentionCount,
  pendingReviews,
  recordSegments,
} from "./model.mjs";
import { icon } from "./icons.mjs";

export const navigation = [
  { id: "overview", label: "Overview", icon: "grid" },
  { id: "sources", label: "Sources", icon: "folder" },
  { id: "discovery", label: "Discovery", icon: "scan" },
  { id: "identities", label: "Identity review", icon: "people" },
  { id: "profiles", label: "Replacement profiles", icon: "sliders" },
  { id: "preview", label: "Preview", icon: "split" },
  { id: "validation", label: "Validation", icon: "shield" },
  { id: "releases", label: "Releases", icon: "box" },
];

export const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        character
      ],
  );
const badge = (label, kind = "neutral") =>
  `<span class="badge ${kind}">${escape(label)}</span>`;
const button = (
  label,
  action,
  {
    kind = "primary",
    glyph = "",
    disabled = false,
    attributes = "",
    small = false,
  } = {},
) =>
  `<button class="button ${kind}${small ? " small" : ""}" data-action="${action}" ${disabled ? "disabled" : ""} ${attributes}>${glyph ? icon(glyph) : ""}${escape(label)}</button>`;
const go = (label, view, options = {}) =>
  button(label, "navigate", {
    ...options,
    attributes: `data-view="${view}" ${options.attributes || ""}`,
  });
const textGo = (label, view) =>
  `<button class="text-button" data-action="navigate" data-view="${view}">${escape(label)}${icon("arrow", "small")}</button>`;
const heading = (eyebrow, title, description, actions = "") =>
  `<header class="page-heading"><div><span class="eyebrow">${escape(eyebrow)}</span><h1>${escape(title)}</h1><p>${escape(description)}</p></div>${actions ? `<div class="button-row">${actions}</div>` : ""}</header>`;
const blockers = (reasons) =>
  reasons.length
    ? `<ul class="blocker-list">${reasons.map((reason) => `<li>${icon("warning")}${escape(reason)}</li>`).join("")}</ul>`
    : "";
const avatar = (entity) =>
  `<span class="avatar ${entity.kind === "Shared account" ? "account" : entity.kind === "Organization" ? "organization" : ""}">${escape(entity.initials)}</span>`;
const person = (entity, detail = entity.email || entity.role) =>
  `<div class="person-cell">${avatar(entity)}<span><strong>${escape(entity.name)}</strong><small>${escape(detail)}</small></span></div>`;
const noData = (title = "A little data goes a long way.") =>
  `<div class="panel empty-state"><div class="drop-icon">${icon("folder", "large")}</div><h2>${escape(title)}</h2><p>Load the fictional sample dataset to explore the workflow. This prototype never reads private files.</p>${go("Add sample sources", "sources", { glyph: "plus" })}</div>`;
const noScan = () =>
  `<div class="panel empty-state"><div class="drop-icon">${icon("scan", "large")}</div><h2>Let's see who's in the data.</h2><p>Run a sample scan to reveal the authored identities and review decisions in this fictional dataset.</p>${go("Open discovery", "discovery", { glyph: "scan" })}</div>`;

export function nextStep(state) {
  if (!state.hasData) return { view: "sources", label: "Add sample sources" };
  if (state.scanStatus !== "complete")
    return { view: "discovery", label: "Run sample scan" };
  if (pendingReviews(state).length)
    return { view: "identities", label: "Review identities" };
  if (!state.excludedUnsupported)
    return { view: "sources", label: "Review source coverage" };
  if (state.frozenRevision !== state.revision)
    return { view: "profiles", label: "Review replacement profiles" };
  if (state.validationRevision !== state.revision)
    return { view: "preview", label: "Inspect the preview" };
  return { view: "releases", label: "Create sample release" };
}

function sourceStatus(source, state) {
  return source.ready
    ? badge("Covered in sample", "green")
    : badge(
        state.excludedUnsupported ? "Explicitly excluded" : "Needs a decision",
        state.excludedUnsupported ? "neutral" : "amber",
      );
}

function sourceTable(state, detailed = false) {
  return `<div class="table-wrap"><table class="data-table"><thead><tr><th>Source</th>${detailed ? "<th>Coverage</th>" : "<th>Records</th>"}<th>Status</th>${detailed ? "<th>Action</th>" : ""}</tr></thead><tbody>${sources.map((source) => `<tr><td><div class="source-cell"><span class="file-icon ${source.ready ? "" : "warning"}">${icon(source.icon)}</span><span class="source-name">${escape(source.name)}<small>${escape(source.kind)}</small></span></div></td><td>${detailed ? `<span class="muted">${escape(source.coverage)}</span>` : source.ready ? source.records : "—"}</td><td>${sourceStatus(source, state)}</td>${detailed ? `<td>${!source.ready ? button(state.excludedUnsupported ? "Restore to scope" : "Exclude from release", "exclude", { kind: "secondary", small: true, attributes: `data-value="${!state.excludedUnsupported}"` }) : `<button class="text-button" data-action="inspect-source" data-source="${source.id}">Inspect${icon("chevron", "small")}</button>`}</td>` : ""}</tr>`).join("")}</tbody></table></div>`;
}

function workflow(state) {
  const reviewed =
    state.hasData &&
    state.scanStatus === "complete" &&
    !pendingReviews(state).length &&
    state.excludedUnsupported;
  const stages = [
    ["Sources", "sources", state.hasData],
    ["Discovery", "discovery", state.scanStatus === "complete"],
    ["Review", "identities", reviewed],
    ["Profiles", "profiles", state.frozenRevision === state.revision],
    ["Validate", "validation", state.validationRevision === state.revision],
    [
      "Release",
      "releases",
      state.releases.some((release) => release.revision === state.revision),
    ],
  ];
  const current = stages.findIndex((stage) => !stage[2]);
  return `<div class="workflow" aria-label="Sample dataset workflow">${stages.map(([label, view, done], index) => `<button class="step ${done ? "done" : current === index ? "current" : ""}" data-action="navigate" data-view="${view}"><span class="step-number">${done ? icon("check") : String(index + 1).padStart(2, "0")}</span><span>${label}</span></button>`).join("")}</div>`;
}

function overview(state) {
  const next = nextStep(state);
  const scanned = state.scanStatus === "complete";
  return `${heading("Project workspace / fictional sample", state.project.name, "A consistent new identity for a connected working world.", button("New project", "new-project", { kind: "secondary", glyph: "plus" }) + go(next.label, next.view, { glyph: "arrow" }))}
  ${state.hasData ? `<div class="summary-line"><div class="summary-item">${icon("folder")}<strong>3</strong><span>covered sources</span></div><span class="summary-separator"></span><div class="summary-item">${icon("people")}<strong>${scanned ? entities.length : "—"}</strong><span>canonical entities</span></div><span class="summary-separator"></span><div class="summary-item">${icon("link")}<strong>${scanned ? mentionCount() : "—"}</strong><span>identity mentions</span></div><div class="summary-item">${badge("Fictional dataset", "green")}</div></div>` : ""}
  ${workflow(state)}
  ${state.hasData && scanned && pendingReviews(state).length ? `<div class="attention">${icon("warning")}<div class="attention-copy"><h2>A little human judgment goes a long way.</h2><p>${pendingReviews(state).length} identity decisions need your attention before this sample can be released.</p></div>${go("Open identity review", "identities", { glyph: "arrow" })}</div>` : state.hasData && canExport(state) ? `<div class="success-note gap-top">${icon("check")}<div><strong>The sample is ready for a release.</strong><p>Your review, coverage decisions, and illustrative validation are complete.</p></div></div>` : ""}
  ${
    !state.hasData
      ? noData("Your next dataset starts here.")
      : `<div class="grid-main"><div><section class="panel"><div class="panel-header"><div><h2>Your source material</h2><p>Keep the relationships. Give the identities a fresh start.</p></div>${textGo("View sources", "sources")}</div>${sourceTable(state)}<div class="table-foot"><span>12 fictional records · 1 unsupported sample</span>${badge("Read-only source fixtures")}</div></section><section class="panel gap-top"><div class="panel-header"><h2>Sample activity</h2>${badge("This tab only")}</div><div class="activity"><div class="activity-item"><span class="activity-marker"></span><div><p>${state.frozenRevision === state.revision ? "Replacement mapping frozen" : scanned ? "Sample discovery is ready for review" : "Sample sources added"}</p><small>${state.frozenRevision === state.revision ? `demo-map-r${state.revision}` : "Authored sample results, ready to explore"}</small></div><time>Demo event</time></div><div class="activity-item"><span class="activity-marker"></span><div><p>Coverage needs an explicit decision</p><small>${state.excludedUnsupported ? "Encrypted PDF excluded from this release" : "Encrypted PDF cannot be inspected"}</small></div><time>Demo event</time></div></div></section></div><div><section class="panel"><div class="panel-header"><h2>Make it release-ready</h2><span class="eyebrow">Your next steps</span></div><div class="checklist">${[
          [
            "Review the identities",
            "Separate the two Mayas and the shared finance account.",
            "identities",
            scanned && !pendingReviews(state).length,
            "Review matches",
          ],
          [
            "Decide what's in scope",
            "The encrypted sample needs an explicit exclusion.",
            "sources",
            state.excludedUnsupported,
            "Review coverage",
          ],
          [
            "Approve the replacements",
            "One coherent profile, everywhere it appears.",
            "profiles",
            state.frozenRevision === state.revision,
            "Explore profiles",
          ],
          [
            "Check the result",
            "Inspect changes before creating a sample release.",
            "preview",
            state.validationRevision === state.revision,
            "Open preview",
          ],
        ]
          .map(
            ([title, copy, view, done, label], index) =>
              `<div class="action-row"><span class="action-number ${done ? "done" : ""}">${done ? icon("check") : index + 1}</span><div class="action-copy"><strong>${title}</strong><p>${copy}</p>${done ? badge("Complete", "green") : textGo(label, view)}</div></div>`,
          )
          .join(
            "",
          )}</div></section><section class="panel gap-top"><div class="panel-header no-border"><h2>Project details</h2></div><dl class="compact-metadata"><div><dt>Dataset</dt><dd>Customer operations</dd></div><div><dt>Mode</dt><dd>Fictional sample</dd></div><div><dt>Mapping profile</dt><dd>${state.profile === "birch" ? "Birch" : "Cedar"}</dd></div><div><dt>Revision</dt><dd>r${state.revision}</dd></div></dl></section></div></div>`
  }`;
}

function sourceView(state) {
  return `${heading("Project / source material", "Start with the source.", "See what's included, what's covered, and what needs a decision.", state.hasData ? go("Open discovery", "discovery", { glyph: "scan" }) : "")}
  ${state.hasData ? `<section class="panel"><div class="panel-header"><div><h2>Source inventory</h2><p>Three readable fixtures. One encrypted sample.</p></div>${badge("4 sample files")}</div>${sourceTable(state, true)}<div class="table-foot"><span>${state.excludedUnsupported ? "3 included · 1 explicitly excluded" : "3 covered · 1 blocking source decision"}</span><span>All content is fictional</span></div></section><div class="note ${state.excludedUnsupported ? "" : "amber"} gap-top">${icon(state.excludedUnsupported ? "check" : "warning")}${state.excludedUnsupported ? "The encrypted sample is explicitly excluded and will be counted in the sample release manifest." : "The encrypted PDF cannot be inspected. It stays out of the sample release until you explicitly exclude it. Nothing is silently treated as covered."}</div>` : `<section class="dropzone" data-dropzone><div class="drop-icon">${icon("upload", "large")}</div><h2>Bring a little sample data.</h2><p>Explore a directory, a conversation export, and handoff notes connected by the same identities.</p>${button("Load fictional sample", "load-sample", { glyph: "plus" })}<small>CSV · JSON · TXT sample fixtures. No real-file import.</small></section>`}
  <div class="section-top gap-top"><div><h2>A growing source library</h2><p>Planned product connectors; unavailable in this prototype.</p></div></div><div class="connector-grid">${[
    ["message", "Slack exports"],
    ["file", "Email packages"],
    ["table", "Database snapshots"],
    ["folder", "Document folders"],
  ]
    .map(
      ([glyph, name]) =>
        `<div class="connector-tile">${icon(glyph)}<strong>${name}</strong><small>Planned connector</small></div>`,
    )
    .join(
      "",
    )}</div><div class="note gap-top">Offline ingestion will use customer-provided export packages. This prototype uses only its bundled fictional records.</div>`;
}

function discovery(state, ui) {
  const scanned = state.scanStatus === "complete";
  return `${heading("Project / discovery", "Know who's in the data.", "Find identity references before deciding how they fit together.", state.hasData ? button(scanned ? "Run sample scan again" : "Run sample scan", "scan", { kind: scanned ? "secondary" : "primary", glyph: "scan", disabled: state.scanStatus === "running" }) : "")}
  ${!state.hasData ? noData() : state.scanStatus === "running" ? `<div class="panel scan-progress" role="status" aria-live="polite"><div class="spinner"></div><h2>Exploring the fictional sample…</h2><p>This short animation demonstrates processing feedback. It does not scan real files.</p><progress max="100" value="${ui.scanProgress}" aria-label="Sample scan progress"></progress><div class="scan-phase"><span>${ui.scanProgress < 40 ? "Reading sample inventory" : ui.scanProgress < 80 ? "Loading authored identity observations" : "Preparing review decisions"}</span><span>${ui.scanProgress}%</span></div></div>` : !scanned ? `<div class="panel empty-state"><div class="drop-icon">${icon("scan", "large")}</div><h2>Ready to explore.</h2><p>The fictional dataset is loaded. Run the sample scan to populate identities and their evidence.</p>${button("Run sample scan", "scan", { glyph: "scan" })}</div>` : `<div class="summary-line"><div class="summary-item"><strong>${entities.length}</strong><span>canonical entities</span></div><div class="summary-item"><strong>${mentionCount()}</strong><span>identity mentions</span></div><div class="summary-item"><strong>${pendingReviews(state).length}</strong><span>review decisions</span></div>${badge("Authored sample observations", "green")}</div><div class="attention">${icon("people")}<div class="attention-copy"><h2>${pendingReviews(state).length ? "The ambiguous bits are worth a closer look." : "The identity decisions are reviewed."}</h2><p>${pendingReviews(state).length ? "A shared first name and a shared mailbox need a human decision." : "You can continue to replacement profiles and freeze the sample mapping."}</p></div>${go(pendingReviews(state).length ? "Review identities" : "Review profiles", pendingReviews(state).length ? "identities" : "profiles", { glyph: "arrow" })}</div><section class="panel"><div class="panel-header"><h2>Observed identities</h2>${badge("6 sample entities")}</div><div class="table-wrap"><table class="data-table"><thead><tr><th>Entity</th><th>Type</th><th>Sources</th><th>Evidence</th></tr></thead><tbody>${entities.map((entity) => `<tr><td>${person(entity)}</td><td>${badge(entity.kind)}</td><td>${entity.sources.length} sources</td><td><button class="text-button" data-action="inspect-entity" data-entity="${entity.id}">Inspect${icon("chevron", "small")}</button></td></tr>`).join("")}</tbody></table></div></section>`}`;
}

function evidence(record, state) {
  return `<div class="evidence-block"><div class="evidence-caption"><span>${escape(sources.find((source) => source.id === record.source).name)}</span><span>${escape(record.locator)}</span></div><div class="evidence-text">${recordSegments(
    record,
    state,
  )
    .map((segment) =>
      segment.original
        ? `<mark class="${segment.unresolved ? "unresolved" : ""}">${escape(segment.text)}</mark>`
        : escape(segment.text),
    )
    .join("")}</div></div>`;
}

function identities(state, ui) {
  const header = heading(
    "Project / identity review",
    "A name isn't an identity.",
    "Use the evidence to keep people, accounts, and organizations correctly connected.",
  );
  if (!state.hasData) return header + noData();
  if (state.scanStatus !== "complete") return header + noScan();
  const tabs = `<div class="tabs" role="group" aria-label="Identity view"><button aria-pressed="${ui.identityTab === "review"}" class="tab ${ui.identityTab === "review" ? "active" : ""}" data-action="identity-tab" data-tab="review">Needs review<span class="tab-count">${pendingReviews(state).length}</span></button><button aria-pressed="${ui.identityTab === "all"}" class="tab ${ui.identityTab === "all" ? "active" : ""}" data-action="identity-tab" data-tab="all">All identities<span class="tab-count">${entities.length}</span></button></div>`;
  if (ui.identityTab === "all") {
    const entity =
      entities.find((item) => item.id === ui.entityId) || entities[0];
    const replacement = profiles[state.profile][entity.id];
    return (
      header +
      tabs +
      `<div class="review-layout"><div class="panel entity-list">${entities.map((item) => `<button class="entity-row ${item.id === entity.id ? "selected" : ""}" data-action="select-entity" data-entity="${item.id}" aria-pressed="${item.id === entity.id}">${person(item, item.kind)}${icon("chevron")}</button>`).join("")}</div><section class="panel review-detail"><div class="entity-detail-heading">${avatar(entity)}<div><h2>${escape(entity.name)}</h2><p>${escape(entity.role)} · ${escape(entity.kind)}</p></div></div><div class="gap-top"><span class="eyebrow">Known sample aliases</span><div class="alias-list">${entity.aliases.map((alias) => badge(alias)).join("")}</div></div><div class="gap-top"><span class="eyebrow">Linked source evidence</span>${entity.sources.map((id) => `<div class="attribute-row"><strong>${escape(sources.find((source) => source.id === id).name)}</strong><span>Source-anchored fixture</span></div>`).join("")}</div><div class="success-note gap-top">${icon("spark")}<div><strong>${escape(replacement.name)}</strong><p>Replacement profile · ${escape(replacement.email || "Organization identity")}</p></div></div>${entity.id === "p017" || entity.id === "p042" ? `<div class="gap-top"><button class="text-button" data-action="reopen" data-case="maya">Revisit the ambiguous first name${icon("arrow", "small")}</button></div>` : ""}</section></div>`
    );
  }
  const pending = pendingReviews(state);
  if (!pending.length)
    return (
      header +
      tabs +
      `<div class="panel empty-state"><div class="drop-icon">${icon("check", "large")}</div><h2>Everyone has their place.</h2><p>Both sample identity decisions are resolved. Review source coverage, then approve your replacement profiles.</p><div class="button-row">${go(state.excludedUnsupported ? "Review replacement profiles" : "Review source coverage", state.excludedUnsupported ? "profiles" : "sources", { glyph: "arrow" })}<button class="button secondary" data-action="identity-tab" data-tab="all">Explore all identities</button></div></div>`
    );
  const selected = pending.find((item) => item.id === ui.caseId) || pending[0];
  const chosen = ui.choices[selected.id];
  return (
    header +
    tabs +
    `<div class="review-layout"><div class="review-list">${pending.map((item) => `<button class="review-card ${selected.id === item.id ? "selected" : ""}" data-action="select-case" data-case="${item.id}" aria-pressed="${selected.id === item.id}">${badge(item.kind, "amber")}<strong>${escape(item.title)}</strong><p>${item.id === "maya" ? "One short name, two distinct people." : "A forwarded signature can create a false link."}</p><span class="review-card-footer"><span>${item.id === "maya" ? "2 candidate identities" : "1 account boundary"}</span>${icon("chevron")}</span></button>`).join("")}<div class="note">Every decision affects the replacement profile. Changes invalidate any current mapping approval and validation.</div></div><section class="panel review-detail"><span class="eyebrow">Identity decision / ${selected.id === "maya" ? "01" : "02"}</span><h2>${escape(selected.title)}</h2><p>${escape(selected.explanation)}</p>${evidence(
      records.find((record) => record.id === selected.recordId),
      state,
    )}<span class="eyebrow">Choose the right connection</span><div class="candidate-list">${selected.choices.map((choice) => `<button class="candidate ${chosen === choice.value ? "selected" : ""}" data-action="choose-candidate" data-case="${selected.id}" data-value="${choice.value}" aria-pressed="${chosen === choice.value}"><span class="person-cell">${choice.value === "shared" ? `<span class="avatar account">FA</span>` : avatar(entities.find((entity) => entity.id === choice.value))}<span><strong>${escape(choice.label)}</strong><small>${escape(choice.detail)}</small>${choice.recommended ? badge("Supported by sample evidence", "green") : ""}</span></span><span class="radio-mark" aria-hidden="true"></span></button>`).join("")}</div><div class="decision-footer"><small>Nothing is approved until you confirm.</small>${button(selected.id === "maya" ? "Confirm identity" : "Confirm separate account", "confirm-review", { glyph: "check", disabled: !chosen, attributes: `data-case="${selected.id}"` })}</div></section></div>`
  );
}

function profileView(state) {
  const header = heading(
    "Project / replacement profiles",
    "New identities. Same connections.",
    "Review a coherent sample profile before freezing the mapping for this revision.",
  );
  if (!state.hasData) return header + noData();
  if (state.scanStatus !== "complete") return header + noScan();
  const frozen = state.frozenRevision === state.revision;
  return (
    header +
    `<div class="grid-main"><section class="panel"><div class="panel-header"><div><h2>Your replacement profile</h2><p>All values below are authored fictional examples.</p></div><label class="sr-only" for="profile-select">Sample replacement profile</label><select id="profile-select" class="profile-select" data-change="profile">${Object.entries(
      profiles,
    )
      .map(
        ([id, profile]) =>
          `<option value="${id}" ${state.profile === id ? "selected" : ""}>${escape(profile.label)}</option>`,
      )
      .join(
        "",
      )}</select></div><div class="table-wrap"><table class="data-table profile-table"><thead><tr><th>Source identity</th><th></th><th>Replacement identity</th></tr></thead><tbody>${entities.map((entity) => `<tr><td>${person(entity)}</td><td>${icon("arrow", "small")}</td><td><div class="replacement-name">${escape(profiles[state.profile][entity.id].name)}</div><div class="replacement-email">${escape(profiles[state.profile][entity.id].email || "Organization profile")}</div></td></tr>`).join("")}</tbody></table></div></section><div><section class="panel panel-body"><span class="eyebrow">Mapping namespace</span><p class="muted gap-top">Keep this project's replacement identities consistent within its recipient scope.</p><div class="namespace-field gap-top">${escape(state.project.namespace)}</div><div class="attribute-row gap-top"><span>People and aliases</span><strong>Replace together</strong></div><div class="attribute-row"><span>Email addresses</span><strong>Reserved domains</strong></div><div class="attribute-row"><span>Shared accounts</span><strong>Keep separate</strong></div><div class="attribute-row"><span>Sample dates / record IDs</span><strong>Preserve</strong></div></section><div class="note gap-top">These presets demonstrate profile choices. A production policy editor and identity generator belong to later steps.</div></div></div><div class="freeze-panel"><div><h3>${frozen ? "This sample mapping is frozen." : "Make this mapping the reference point."}</h3><p>${frozen ? `demo-map-r${state.revision} · Editing a decision or profile will invalidate it.` : "Resolve identity and source decisions before freezing this revision."}</p>${!canFreeze(state) ? blockers(getBlockers(state, { includeFreeze: false, includeValidation: false })) : ""}</div>${frozen ? go("Inspect before / after", "preview", { glyph: "split" }) : button("Freeze sample mapping", "freeze", { glyph: "lock", disabled: !canFreeze(state) })}</div>`
  );
}

function preview(state, ui) {
  const header = heading(
    "Project / before and after",
    "The context stays intact.",
    "Follow the same identity through the source and its authored replacement.",
    state.hasData && state.scanStatus === "complete"
      ? go("Open validation", "validation", { glyph: "shield" })
      : "",
  );
  if (!state.hasData) return header + noData();
  if (state.scanStatus !== "complete") return header + noScan();
  const source =
    sources.find((item) => item.id === ui.previewSource && item.ready) ||
    sources[1];
  const choices = records.filter((record) => record.source === source.id);
  const selected =
    choices.find((record) => record.id === ui.recordId) || choices[0];
  const references = [
    ...new Set(
      recordSegments(selected, state)
        .map((segment) => segment.entity)
        .filter(Boolean),
    ),
  ];
  const code = (synthetic) =>
    `<div class="diff-code ${synthetic ? "synthetic" : ""} ${ui.highlights ? "" : "no-highlights"}">${recordSegments(
      selected,
      state,
      synthetic,
    )
      .map((segment) =>
        segment.original
          ? `<mark class="${segment.unresolved ? "unresolved" : ""}">${escape(segment.text)}</mark>`
          : escape(segment.text),
      )
      .join("")}</div>`;
  return (
    header +
    `<div class="toolbar"><label class="sr-only" for="preview-source">Preview source</label><select id="preview-source" class="profile-select" data-change="preview-source">${sources
      .filter((item) => item.ready)
      .map(
        (item) =>
          `<option value="${item.id}" ${source.id === item.id ? "selected" : ""}>${escape(item.name)}</option>`,
      )
      .join(
        "",
      )}</select><div class="button-row">${badge(state.frozenRevision === state.revision ? `Frozen · r${state.revision}` : "Working preview", state.frozenRevision === state.revision ? "green" : "amber")}${button(ui.highlights ? "Hide highlights" : "Show highlights", "toggle-highlights", { kind: "secondary", glyph: "eye", small: true })}</div></div><div class="preview-layout"><div class="record-list"><div class="record-list-heading">${choices.length} sample records</div>${choices.map((record) => `<button class="record-choice ${selected.id === record.id ? "selected" : ""}" data-action="select-record" data-record="${record.id}" aria-pressed="${selected.id === record.id}">${icon(source.icon)}<span><strong>${escape(record.title)}</strong><small>${escape(record.locator)}</small></span></button>`).join("")}</div><div><section class="panel"><div class="panel-header"><div><h2>${escape(selected.title)}</h2><p>${escape(source.name)} · ${escape(selected.locator)}</p></div>${badge("Fictional fixture")}</div><div class="diff-grid"><div class="diff-pane"><div class="diff-heading"><strong>Original sample</strong><span>Read-only</span></div>${code(false)}</div><div class="diff-pane"><div class="diff-heading"><strong>Replacement sample</strong><span>${state.profile === "birch" ? "Birch" : "Cedar"} profile</span></div>${code(true)}</div></div><div class="diff-bottom"><div class="legend"><span><i class="legend-dot"></i>Original identity</span><span><i class="legend-dot green"></i>Replacement</span></div><span>Structure and account references stay connected</span></div></section><section class="panel gap-top"><div class="panel-header no-border"><h2>Identity references in this record</h2></div><div class="reference-list">${references.map((id) => `<button class="reference-chip" data-action="inspect-entity" data-entity="${id}">${icon("link")}${escape(entities.find((entity) => entity.id === id)?.name || id)}${icon("arrow")}</button>`).join("")}</div></section>${pendingReviews(state).length ? `<div class="note amber gap-top">${icon("warning")}Unresolved mentions retain their original sample text. Complete identity review before freezing or exporting.</div>` : ""}</div></div>`
  );
}

function validation(state, ui) {
  const header = heading(
    "Project / validation",
    "Confidence needs evidence.",
    "Walk through the illustrative release checks for the current sample revision.",
  );
  if (!state.hasData) return header + noData();
  const passed = state.validationRevision === state.revision;
  const contradictory =
    state.validationAttempted && state.decisions.maya === "p042";
  const eligible = canFreeze(state) && state.frozenRevision === state.revision;
  const checks = [
    [
      "Identity decisions",
      contradictory
        ? "The chosen Maya conflicts with the invoice-thread participants. Revisit this identity."
        : "The short-name mention and shared mailbox have explicit review decisions.",
      !pendingReviews(state).length && !contradictory,
    ],
    [
      "Source coverage",
      "Three covered sample sources; the encrypted PDF must be explicitly excluded.",
      state.excludedUnsupported,
    ],
    [
      "Consistent replacements",
      "The same frozen sample profile is used across linked identity mentions.",
      state.frozenRevision === state.revision,
    ],
    [
      "Connected task context",
      "The fictional account AC-104 stays linked across the handoff and invoice thread.",
      state.frozenRevision === state.revision && !contradictory,
    ],
  ];
  return (
    header +
    `<div class="grid-main"><div><section class="panel"><div class="panel-header"><div><h2>Sample release checks</h2><p>Illustrative checkpoints, not a real privacy assessment.</p></div>${badge(`Revision r${state.revision}`)}</div>${checks.map(([title, copy, ready]) => `<div class="validation-row"><span class="validation-symbol ${passed ? "pass" : state.validationAttempted && !ready ? "blocked" : ""}">${icon(passed ? "check" : state.validationAttempted && !ready ? "warning" : "shield")}</span><div><h3>${title}</h3><p>${copy}</p>${contradictory && title === "Identity decisions" ? `<div class="gap-top"><button class="text-button" data-action="reopen" data-case="maya">Revisit the identity${icon("arrow", "small")}</button></div>` : ""}</div>${badge(passed ? "Sample passed" : state.validationAttempted && !ready ? "Needs attention" : ready ? "Ready to check" : "Not ready", passed ? "green" : state.validationAttempted && !ready ? "amber" : "neutral")}</div>`).join("")}</section><div class="note gap-top">The production platform will need independent detection, format verification, and task replay. These results demonstrate the review experience using fixed fictional data.</div></div><section class="panel validation-summary">${icon(passed ? "check" : "shield", "large")}<h2>${passed ? "Ready for a sample release." : contradictory ? "One link needs another look." : "A final look before release."}</h2><p>${passed ? "The illustrative checks are complete for this frozen revision. The sample bundle excludes original-to-synthetic mappings." : contradictory ? "A completed review can still be wrong. Reopen the ambiguous name and use the thread evidence to correct it." : "Freeze your reviewed mapping and make source coverage explicit before running these sample checks."}</p>${passed ? go("Create sample release", "releases", { glyph: "arrow" }) : button(ui.validating ? "Running sample checks…" : "Run sample validation", "validate", { glyph: "shield", disabled: !eligible || ui.validating })}${!passed && !contradictory ? blockers(getBlockers(state, { includeValidation: false })) : ""}<div class="note gap-top">All validation outcomes are illustrative. Zero observed issues here is not a guarantee of anonymity.</div></section></div>`
  );
}

function releases(state) {
  const header = heading(
    "Project / dataset releases",
    "Ready to leave the workspace.",
    "Create a clearly labeled sample bundle from a reviewed, frozen revision.",
    canExport(state) &&
      !state.releases.some((release) => release.revision === state.revision)
      ? button("Create sample release", "publish", { glyph: "box" })
      : "",
  );
  if (!state.releases.length)
    return (
      header +
      `<div class="grid-main"><section class="panel empty-state"><div class="drop-icon">${icon("box", "large")}</div><h2>Your first release belongs here.</h2><p>${canExport(state) ? "The fictional dataset is ready. Create its sample release, then download the resulting JSON bundle." : "Complete the identity and coverage decisions, freeze the mapping, and run sample validation."}</p>${canExport(state) ? button("Create sample release", "publish", { glyph: "plus" }) : go(nextStep(state).label, nextStep(state).view, { glyph: "arrow" })}</section><section class="panel panel-body"><h2>Release readiness</h2>${canExport(state) ? `<div class="success-note gap-top">${icon("check")}<p>All illustrative release gates are complete.</p></div>` : blockers(getBlockers(state))}<div class="note gap-top">Downloads contain only the fictional transformed records and coverage metadata. The private mapping registry is excluded.</div></section></div>`
    );
  return (
    header +
    state.releases
      .map(
        (release) =>
          `<section class="panel gap-top"><div class="release-card"><span class="release-icon">${icon("box", "large")}</span><div class="release-copy"><h2>${escape(release.id)} ${badge("Fictional output", "green")}</h2><p>${escape(release.projectName)} · JSON sample bundle</p><div class="release-meta"><span>Created in this tab</span><span>demo-map-r${release.revision}</span>${badge(release.revision === state.revision ? "Current revision" : "Earlier snapshot")}</div></div>${button("Download sample bundle", "download", { glyph: "download", attributes: `data-release="${release.id}"` })}</div><div class="release-details"><div><span>Included sources</span><strong>${release.bundle.coverage.includedSources.length} fictional files</strong></div><div><span>Explicit exclusions</span><strong>${release.bundle.coverage.excludedSourceCount} encrypted sample</strong></div><div><span>Output records</span><strong>${release.bundle.records.length} transformed fixtures</strong></div></div></section>`,
      )
      .join("") +
    `<div class="note gap-top">This is a real download of authored fictional output, not the result of an implemented enterprise-data processing engine.</div>`
  );
}

export function renderView(view, state, ui) {
  const renderers = {
    overview,
    sources: sourceView,
    discovery,
    identities,
    profiles: profileView,
    preview,
    validation,
    releases,
  };
  return (renderers[view] || overview)(state, ui);
}
