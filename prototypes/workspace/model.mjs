import { profiles, records, reviewCases, sources } from "./fixtures.mjs";

export function createDemoState({
  empty = false,
  name = "Customer operations",
} = {}) {
  return {
    project: { name, namespace: "birch-demo / customer-ops / research" },
    hasData: !empty,
    scanStatus: empty ? "idle" : "complete",
    decisions: {},
    excludedUnsupported: false,
    profile: "birch",
    revision: 1,
    frozenRevision: null,
    validationRevision: null,
    validationAttempted: false,
    releases: [],
  };
}

export function pendingReviews(state) {
  return reviewCases.filter((item) => !state.decisions[item.id]);
}

export function getBlockers(
  state,
  { includeFreeze = true, includeValidation = true } = {},
) {
  const reasons = [];
  if (!state.hasData) return ["Load the fictional dataset."];
  if (state.scanStatus !== "complete")
    reasons.push("Complete the sample scan.");
  if (pendingReviews(state).length)
    reasons.push(`Resolve ${pendingReviews(state).length} identity decisions.`);
  if (!state.excludedUnsupported)
    reasons.push("Explicitly exclude the unsupported encrypted sample.");
  if (includeFreeze && state.frozenRevision !== state.revision)
    reasons.push("Freeze the current sample mapping.");
  if (includeValidation && state.validationRevision !== state.revision)
    reasons.push("Validate this mapping revision.");
  return reasons;
}

export function canFreeze(state) {
  return (
    getBlockers(state, { includeFreeze: false, includeValidation: false })
      .length === 0
  );
}

export function canExport(state) {
  return getBlockers(state).length === 0;
}

function edited(state, changes) {
  return {
    ...state,
    ...changes,
    revision: state.revision + 1,
    frozenRevision: null,
    validationRevision: null,
    validationAttempted: false,
  };
}

export function transition(state, event) {
  switch (event.type) {
    case "CREATE_PROJECT": {
      const name = String(event.name ?? "").trim();
      if (!name || name.length > 64)
        throw new Error("Choose a project name between 1 and 64 characters.");
      const next = createDemoState({ empty: true, name });
      const slug =
        name
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-|-$/g, "") || "research-pilot";
      next.project.namespace = `birch-demo / ${slug} / research`;
      return next;
    }
    case "LOAD_SAMPLE":
      return edited(state, {
        hasData: true,
        scanStatus: "idle",
        decisions: {},
        excludedUnsupported: false,
      });
    case "START_SCAN":
      return state.hasData && state.scanStatus !== "running"
        ? edited(state, { scanStatus: "running" })
        : state;
    case "FINISH_SCAN":
      return state.scanStatus === "running"
        ? { ...state, scanStatus: "complete" }
        : state;
    case "DECIDE": {
      if (state.scanStatus !== "complete") return state;
      const review = reviewCases.find((item) => item.id === event.caseId);
      if (!review?.choices.some((choice) => choice.value === event.value))
        return state;
      if (state.decisions[event.caseId] === event.value) return state;
      return edited(state, {
        decisions: { ...state.decisions, [event.caseId]: event.value },
      });
    }
    case "REOPEN": {
      if (!state.decisions[event.caseId]) return state;
      const decisions = { ...state.decisions };
      delete decisions[event.caseId];
      return edited(state, { decisions });
    }
    case "EXCLUDE_UNSUPPORTED":
      return state.excludedUnsupported === event.value
        ? state
        : edited(state, { excludedUnsupported: Boolean(event.value) });
    case "SET_PROFILE":
      return profiles[event.value] && event.value !== state.profile
        ? edited(state, { profile: event.value })
        : state;
    case "FREEZE":
      return canFreeze(state)
        ? { ...state, frozenRevision: state.revision }
        : state;
    case "VALIDATE":
      if (!canFreeze(state) || state.frozenRevision !== state.revision)
        return state;
      return {
        ...state,
        validationAttempted: true,
        validationRevision:
          state.decisions.maya === "p017" ? state.revision : null,
      };
    case "PUBLISH": {
      if (
        !canExport(state) ||
        state.releases.some((release) => release.revision === state.revision)
      )
        return state;
      const bundle = createSampleBundle(state);
      const release = {
        id: `sample-${String(state.releases.length + 1).padStart(3, "0")}`,
        revision: state.revision,
        projectName: state.project.name,
        profile: state.profile,
        bundle,
      };
      return { ...state, releases: [release, ...state.releases] };
    }
    case "RESET":
      return createDemoState();
    default:
      return state;
  }
}

export function recordSegments(record, state, synthetic = false) {
  return record.segments.map((segment) => {
    if (typeof segment === "string")
      return { text: segment, entity: null, changed: false, unresolved: false };
    const entity =
      segment.entity === "ambiguous-maya"
        ? state.decisions.maya
        : segment.entity;
    const replacement = entity
      ? profiles[state.profile][entity]?.[segment.attribute]
      : null;
    return {
      text: synthetic && replacement ? replacement : segment.original,
      original: segment.original,
      entity,
      changed: Boolean(
        synthetic && replacement && replacement !== segment.original,
      ),
      unresolved: !entity,
    };
  });
}

export function mentionCount() {
  return records.reduce(
    (total, record) =>
      total +
      record.segments.filter((segment) => typeof segment !== "string").length,
    0,
  );
}

export function createSampleBundle(state) {
  if (!canExport(state))
    throw new Error("Sample release is not ready. Resolve its blockers first.");
  return {
    prototype: true,
    description:
      "Fictional fixture output for UX review; not a production privacy assessment.",
    mappingSnapshot: `demo-map-r${state.revision}`,
    coverage: {
      includedSources: sources
        .filter((source) => source.ready)
        .map((source) => source.name),
      excludedSourceCount: 1,
    },
    records: records.map((record) => ({
      id: record.id,
      source: record.source,
      text: recordSegments(record, state, true)
        .map((segment) => segment.text)
        .join(""),
    })),
  };
}
