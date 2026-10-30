import assert from "node:assert/strict";
import test from "node:test";

import {
  canExport,
  createDemoState,
  createSampleBundle,
  getBlockers,
  transition,
} from "./model.mjs";
import { renderView } from "./views.mjs";

function reviewedState() {
  let state = createDemoState();
  state = transition(state, { type: "DECIDE", caseId: "maya", value: "p017" });
  state = transition(state, {
    type: "DECIDE",
    caseId: "finance",
    value: "shared",
  });
  return transition(state, { type: "EXCLUDE_UNSUPPORTED", value: true });
}

function approvedState() {
  let state = reviewedState();
  state = transition(state, { type: "FREEZE" });
  return transition(state, { type: "VALIDATE" });
}

test("the initial sample cannot be exported with unresolved identity decisions", () => {
  const state = createDemoState();
  assert.equal(canExport(state), false);
  assert.throws(() => createSampleBundle(state), /not ready/i);
  assert.ok(getBlockers(state).some((reason) => /identit/i.test(reason)));
});

test("unsupported content requires an explicit exclusion before a mapping can freeze", () => {
  let state = createDemoState();
  state = transition(state, { type: "DECIDE", caseId: "maya", value: "p017" });
  state = transition(state, {
    type: "DECIDE",
    caseId: "finance",
    value: "shared",
  });
  state = transition(state, { type: "FREEZE" });
  assert.equal(state.frozenRevision, null);
  assert.equal(canExport(transition(state, { type: "VALIDATE" })), false);
});

test("a reviewed mapping must freeze and validate at the current revision", () => {
  const reviewed = reviewedState();
  assert.equal(canExport(reviewed), false);
  const frozen = transition(reviewed, { type: "FREEZE" });
  assert.equal(canExport(frozen), false);
  assert.equal(canExport(transition(frozen, { type: "VALIDATE" })), true);
});

test("identity, profile, and scope changes invalidate an approved sample release", () => {
  const state = approvedState();
  for (const event of [
    { type: "DECIDE", caseId: "maya", value: "p042" },
    { type: "SET_PROFILE", value: "cedar" },
    { type: "EXCLUDE_UNSUPPORTED", value: false },
  ]) {
    const changed = transition(state, event);
    assert.equal(canExport(changed), false);
    assert.equal(changed.frozenRevision, null);
    assert.equal(changed.validationRevision, null);
  }
});

test("a fictional export omits source identities and the mapping registry", () => {
  const bundle = createSampleBundle(approvedState());
  const serialized = JSON.stringify(bundle);
  assert.equal(bundle.prototype, true);
  assert.equal(bundle.records.length, 12);
  assert.equal(bundle.coverage.includedSources.length, 3);
  assert.equal(bundle.coverage.excludedSourceCount, 1);
  for (const original of ["Maya", "Daniel", "Priya", "Acme", "@acme.example"]) {
    assert.equal(
      serialized.includes(original),
      false,
      `unexpected source identity: ${original}`,
    );
  }
  assert.equal("mappings" in bundle, false);
  assert.equal("decisions" in bundle, false);
  assert.ok(serialized.includes("Nora"));
});

test("creating a blank project exposes an empty workflow and rejects empty names", () => {
  const state = transition(createDemoState(), {
    type: "CREATE_PROJECT",
    name: "Research pilot",
  });
  assert.equal(state.hasData, false);
  assert.equal(state.scanStatus, "idle");
  assert.equal(canExport(state), false);
  assert.throws(
    () => transition(state, { type: "CREATE_PROJECT", name: " " }),
    /project name/i,
  );
});

test("a complete fictional import journey can reach a reviewed release", () => {
  let state = transition(createDemoState(), {
    type: "CREATE_PROJECT",
    name: "Research pilot",
  });
  state = transition(state, { type: "LOAD_SAMPLE" });
  state = transition(state, { type: "START_SCAN" });
  assert.equal(state.scanStatus, "running");
  state = transition(state, { type: "FINISH_SCAN" });
  state = transition(state, { type: "DECIDE", caseId: "maya", value: "p017" });
  state = transition(state, {
    type: "DECIDE",
    caseId: "finance",
    value: "shared",
  });
  state = transition(state, { type: "EXCLUDE_UNSUPPORTED", value: true });
  state = transition(state, { type: "FREEZE" });
  state = transition(state, { type: "VALIDATE" });
  state = transition(state, { type: "PUBLISH" });
  assert.equal(state.releases.length, 1);
  assert.equal(state.releases[0].bundle.prototype, true);
  assert.equal(transition(state, { type: "PUBLISH" }).releases.length, 1);
});

test("published fictional payloads remain unchanged when the working profile changes", () => {
  const released = transition(approvedState(), { type: "PUBLISH" });
  const before = JSON.stringify(released.releases[0].bundle);
  const changed = transition(released, { type: "SET_PROFILE", value: "cedar" });
  assert.equal(JSON.stringify(changed.releases[0].bundle), before);
  assert.equal(canExport(changed), false);
});

test("a reviewed but contradictory identity choice fails the sample validation", () => {
  let state = reviewedState();
  state = transition(state, { type: "DECIDE", caseId: "maya", value: "p042" });
  state = transition(state, { type: "FREEZE" });
  state = transition(state, { type: "VALIDATE" });
  assert.equal(state.validationAttempted, true);
  assert.equal(canExport(state), false);
  assert.equal(state.validationRevision, null);
});

test("reopening a case with no decision leaves the revision and approval alone", () => {
  const unreviewed = createDemoState();
  assert.equal(
    transition(unreviewed, { type: "REOPEN", caseId: "maya" }),
    unreviewed,
  );

  const approved = approvedState();
  assert.equal(
    transition(approved, { type: "REOPEN", caseId: "not-a-case" }),
    approved,
  );
  assert.equal(canExport(approved), true);
});

test("validation does not run unless the current revision is frozen", () => {
  const unfrozen = reviewedState();
  assert.equal(transition(unfrozen, { type: "VALIDATE" }), unfrozen);
  assert.equal(unfrozen.validationAttempted, false);

  const edited = transition(approvedState(), { type: "REOPEN", caseId: "maya" });
  assert.equal(transition(edited, { type: "VALIDATE" }), edited);
  assert.equal(edited.validationAttempted, false);
});

test("the overview names the project the user created", () => {
  let state = transition(createDemoState(), {
    type: "CREATE_PROJECT",
    name: "R&D <pilot>",
  });
  state = transition(state, { type: "LOAD_SAMPLE" });
  const html = renderView("overview", state, { scanProgress: 0 });
  assert.match(html, /<dt>Dataset<\/dt><dd>R&amp;D &lt;pilot&gt;<\/dd>/);
  assert.doesNotMatch(html, /Customer operations/);
});
