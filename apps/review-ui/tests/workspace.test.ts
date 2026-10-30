import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import test from "node:test";
import {
  parseProjectName,
  SESSION_TTL_MS,
  WorkspaceStore,
} from "../src/lib/workspace-store.ts";

test("project names preserve Unicode, trim whitespace and reject invalid input", () => {
  assert.equal(parseProjectName("  સંશોધન <pilot>  "), "સંશોધન <pilot>");
  for (const value of ["", " \n ", "a".repeat(121), null, {}, "\u0000bad"]) {
    assert.throws(() => parseProjectName(value), /project name/i);
  }
});

test("reads and mutations cannot cross sample sessions even with a known project ID", () => {
  const store = new WorkspaceStore();
  const a = store.createSession();
  const b = store.createSession();
  const project = store.createProject(a, "Research", randomUUID());
  assert.equal(store.getProject(b, project.id), null);
  assert.equal(store.getSource(b, project.id, "directory"), null);
  assert.throws(() => store.loadSamples(b, project.id), /unavailable/i);
  assert.deepEqual(store.listProjects(b), []);
});

test("submission retries and sample loading are idempotent and project-specific", () => {
  const store = new WorkspaceStore();
  const token = store.createSession();
  const key = randomUUID();
  const a = store.createProject(token, "Research", key);
  assert.deepEqual(store.createProject(token, "Research", key), a);
  assert.throws(
    () => store.createProject(token, "Different", key),
    /submission/i,
  );
  const b = store.createProject(token, "Operations", randomUUID());
  assert.deepEqual(
    store.loadSamples(token, a.id),
    store.loadSamples(token, a.id),
  );
  assert.equal(store.getProject(token, a.id)?.sourceCount, 4);
  assert.equal(store.getProject(token, b.id)?.sourceCount, 0);
});

test("minimal DTOs exclude private locators and cannot mutate the backing store", () => {
  const store = new WorkspaceStore();
  const token = store.createSession();
  const project = store.createProject(token, "Original", randomUUID());
  const sources = store.loadSamples(token, project.id);
  const payload = JSON.stringify({ project, sources });
  assert.doesNotMatch(payload, /vault:|privateLocator|sessionToken/);
  project.name = "Changed externally";
  sources[0].name = "Changed externally";
  assert.equal(store.getProject(token, project.id)?.name, "Original");
  assert.equal(
    store.getSource(token, project.id, "directory")?.name,
    "Team directory.csv",
  );
});

test("expired and malformed sessions fail closed, and reads never create sessions", () => {
  let now = 1000;
  const store = new WorkspaceStore(() => now);
  const token = store.createSession();
  const project = store.createProject(token, "Pilot", randomUUID());
  now += SESSION_TTL_MS;
  assert.equal(store.hasSession(token), false);
  assert.equal(store.getProject(token, project.id), null);
  assert.deepEqual(store.listProjects("made-up-token"), []);
  assert.throws(
    () => store.createProject(token, "Pilot", randomUUID()),
    /expired/i,
  );
});

test("session/project limits bound memory and expired sessions free capacity", () => {
  let now = 0;
  const store = new WorkspaceStore(() => now);
  const token = store.createSession();
  for (let i = 0; i < 20; i++)
    store.createProject(token, `Project ${i}`, randomUUID());
  assert.throws(
    () => store.createProject(token, "One too many", randomUUID()),
    /limit/i,
  );
  for (let i = 1; i < 128; i++) store.createSession();
  assert.throws(() => store.createSession(), /capacity/i);
  now += SESSION_TTL_MS;
  assert.equal(store.hasSession(store.createSession()), true);
});

test("untrusted identifiers and invalid submission keys cannot select arbitrary resources", () => {
  const store = new WorkspaceStore();
  const token = store.createSession();
  for (const key of ["", "../../vault", "x".repeat(4096)]) {
    assert.throws(
      () => store.createProject(token, "Pilot", key),
      /submission/i,
    );
  }
  assert.equal(store.getProject(token, "__proto__"), null);
  assert.equal(store.getSource(token, "../../vault", "../secret"), null);
});
