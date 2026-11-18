import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import test from "node:test";
import {
  applyMappingMutation,
  canFreeze,
  createEmptyMapping,
  createReadyMapping,
  freezeBlockers,
  isFrozen,
  pendingReviews,
} from "../src/lib/identity-model.ts";
import { WorkspaceStore } from "../src/lib/workspace-store.ts";

test("authored identity fixtures expose API-shaped DTOs without private locators", () => {
  const mapping = createReadyMapping("Birch <pilot>");
  assert.equal(mapping.status, "ready");
  assert.equal(pendingReviews(mapping).length, 2);
  assert.match(mapping.namespace, /^sample-ns \//);
  const payload = JSON.stringify(mapping);
  assert.doesNotMatch(payload, /vault:|privateLocator|mappingVault|secret/i);
  assert.ok(mapping.entities.every((entity) => entity.sourceIds.length > 0));
  assert.ok(mapping.profiles.some((profile) => profile.id === "birch"));
});

test("freeze stays blocked until identity decisions and unsupported exclusion are resolved", () => {
  let mapping = createReadyMapping("Ops");
  assert.deepEqual(freezeBlockers(mapping), [
    "Resolve 2 identity decisions.",
    "Explicitly exclude the unavailable encrypted PDF sample from this revision.",
  ]);
  assert.equal(canFreeze(mapping), false);

  mapping = applyMappingMutation(mapping, {
    type: "DECIDE",
    caseId: "maya",
    value: "p017",
  });
  mapping = applyMappingMutation(mapping, {
    type: "DECIDE",
    caseId: "finance",
    value: "shared",
  });
  assert.deepEqual(freezeBlockers(mapping), [
    "Explicitly exclude the unavailable encrypted PDF sample from this revision.",
  ]);

  mapping = applyMappingMutation(mapping, {
    type: "EXCLUDE_UNSUPPORTED",
    value: true,
  });
  assert.deepEqual(freezeBlockers(mapping), []);
  assert.equal(canFreeze(mapping), true);

  mapping = applyMappingMutation(mapping, { type: "FREEZE" });
  assert.equal(isFrozen(mapping), true);
  assert.equal(mapping.snapshotRef, `sample-map-r${mapping.revision}`);
});

test("profile changes and reopened decisions invalidate a frozen sample mapping", () => {
  let mapping = createReadyMapping("Invalidate");
  mapping = applyMappingMutation(mapping, {
    type: "DECIDE",
    caseId: "maya",
    value: "p017",
  });
  mapping = applyMappingMutation(mapping, {
    type: "DECIDE",
    caseId: "finance",
    value: "shared",
  });
  mapping = applyMappingMutation(mapping, {
    type: "EXCLUDE_UNSUPPORTED",
    value: true,
  });
  const frozen = applyMappingMutation(mapping, { type: "FREEZE" });
  assert.equal(isFrozen(frozen), true);

  const switched = applyMappingMutation(frozen, {
    type: "SET_PROFILE",
    profileId: "cedar",
  });
  assert.equal(isFrozen(switched), false);
  assert.equal(switched.snapshotRef, null);
  assert.equal(switched.profileId, "cedar");
  assert.ok(switched.revision > frozen.revision);

  const refrozen = applyMappingMutation(switched, { type: "FREEZE" });
  const reopened = applyMappingMutation(refrozen, {
    type: "REOPEN",
    caseId: "maya",
  });
  assert.equal(isFrozen(reopened), false);
  assert.equal(
    pendingReviews(reopened).some((item) => item.id === "maya"),
    true,
  );
});

test("empty mapping cannot freeze and rejects mutations until samples are loaded", () => {
  const empty = createEmptyMapping("Empty");
  assert.equal(empty.status, "empty");
  assert.equal(canFreeze(empty), false);
  assert.equal(applyMappingMutation(empty, { type: "FREEZE" }).status, "empty");

  const store = new WorkspaceStore();
  const token = store.createSession();
  const project = store.createProject(token, "Empty", randomUUID());
  assert.equal(store.getMapping(token, project.id)?.status, "empty");
  assert.throws(
    () => store.mutateMapping(token, project.id, { type: "FREEZE" }),
    /load sample sources/i,
  );
});

test("workspace store persists review, freeze, and invalidation across reads", () => {
  const store = new WorkspaceStore();
  const token = store.createSession();
  const project = store.createProject(token, "Review store", randomUUID());
  store.loadSamples(token, project.id);

  store.mutateMapping(token, project.id, {
    type: "DECIDE",
    caseId: "maya",
    value: "p017",
  });
  store.mutateMapping(token, project.id, {
    type: "DECIDE",
    caseId: "finance",
    value: "shared",
  });
  store.mutateMapping(token, project.id, {
    type: "EXCLUDE_UNSUPPORTED",
    value: true,
  });
  const frozen = store.mutateMapping(token, project.id, { type: "FREEZE" });
  assert.equal(isFrozen(frozen), true);

  const outsider = store.createSession();
  assert.equal(store.getMapping(outsider, project.id), null);

  const invalidated = store.mutateMapping(token, project.id, {
    type: "SET_PROFILE",
    profileId: "cedar",
  });
  assert.equal(isFrozen(invalidated), false);
  assert.equal(store.getMapping(token, project.id)?.profileId, "cedar");

  const payload = JSON.stringify(store.getMapping(token, project.id));
  assert.doesNotMatch(payload, /vault:\/\/|privateLocator/);
});

test("invalid identity choices and blocked freezes fail closed with clear errors", () => {
  const store = new WorkspaceStore();
  const token = store.createSession();
  const project = store.createProject(token, "Fail closed", randomUUID());
  store.loadSamples(token, project.id);

  assert.throws(
    () =>
      store.mutateMapping(token, project.id, {
        type: "DECIDE",
        caseId: "maya",
        value: "not-an-entity",
      }),
    /not available/i,
  );
  assert.throws(
    () => store.mutateMapping(token, project.id, { type: "FREEZE" }),
    /blockers|before freezing/i,
  );
  assert.throws(
    () =>
      store.mutateMapping(token, project.id, {
        type: "SET_PROFILE",
        profileId: "oak",
      }),
    /not available/i,
  );
});
