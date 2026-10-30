# Next.js frontend foundation implementation plan

> For agentic workers: execute inline using executing-plans and test-driven-development.

**Goal:** Implement Step 2A with the approved workspace appearance and a server-only,
session-isolated fictional data source.

**Architecture:** Next.js App Router reads through a server-only DAL. Validated
Server Actions mutate a bounded sample store. Minimal DTOs cross the render boundary.
The Python processing API, SSO and persistent storage remain Step 3.

**Tech stack:** Next.js 16.4.3, React 19.3.1, TypeScript, CSS, ESLint, Node tests,
Playwright. Existing Python/prototype tooling remains independent.

## 1. Reproducible frontend tooling

- [x] Create `apps/review-ui/package.json`, lockfile, TypeScript/Next/ESLint config;
  pin dependencies and keep dev/start on loopback port 4318.
- [x] Add ignore rules for dependencies, Next output and browser artifacts.
- [x] Keep telemetry disabled in developer/build/test commands.

## 2. Write failing behavioral contracts

Files: `apps/review-ui/tests/workspace.test.ts`,
`apps/review-ui/src/lib/workspace-store.ts`.

- [x] Test trimmed Unicode names and rejection of blank/oversized/non-string input.
- [x] Test creating two sessions; a project from A must be unavailable in B.
- [x] Test duplicate submission keys and repeated sample loading are idempotent.
- [x] Test time expiry and store limits with an injected clock.
- [x] Test returned DTOs cannot mutate store state and omit internal source paths.
- [x] Run `npm test`; observe the missing implementation failure. Implement the
  pure store, rerun until all assertions pass.

The concrete acceptance shape is:

```ts
const store = new WorkspaceStore(() => now);
const a = store.createSession();
const b = store.createSession();
const project = store.createProject(a, "Research pilot", crypto.randomUUID());
assert.equal(store.getProject(b, project.id), null);
assert.deepEqual(store.loadSamples(a, project.id), store.loadSamples(a, project.id));
now += SESSION_TTL_MS;
assert.equal(store.getProject(a, project.id), null);
```

## 3. Server boundary and browser contract

Files: `src/server/workspace.ts`, `src/app/actions.ts`, `src/proxy.ts`,
`tests/security.test.ts`, `e2e/workspace.spec.ts`.

- [x] Write browser tests for creation, empty/sample source states, detail pages,
  direct routes, form errors, two isolated contexts and unknown IDs.
- [x] Add production-response checks for CSP nonce variation, cache policy,
  cookie properties, absence of external requests and no browser dataset storage.
- [x] Implement DAL with `server-only`; read opaque sessions from HttpOnly cookies.
  Check sample mode on every store entry point. Return controlled errors only.
- [x] Implement validated Actions, dynamic reads, bounded sample sessions and a
  strict nonce CSP. Avoid sensitive client props and arbitrary redirects/proxies.

## 4. Approved workspace UI

Files: `src/app/layout.tsx`, routed pages and errors, `src/components/`, styles/fonts.

- [x] Build the dark forest sidebar, warm canvas, lime actions and bundled fonts.
- [x] Add project creation/selection, overview, source inventory/detail; other
  workflow routes explain their upcoming implementation.
- [x] Use native dialogs, pending states, persistent announcements, mobile drawer
  focus containment, active links, route focus, empty/error/not-found recovery.
- [x] Run browser tests and inspect desktop/mobile screenshots. Exercise input
  escaping and reset/cancel behavior through visible controls.

## 5. CI and verification

- [x] Add frontend CI: locked install, lint, type checking, Node tests, production
  build and Chromium browser tests. Add npm Dependabot updates targeting develop.
- [x] Run `npm run check`, `npm run build`, `npm run test:e2e`, `npm run test:disconnected`, and dependency audit.
- [x] Run existing prototype tests, `make check`, `make build` and diff checks.
- [x] Check `next dev` via the next-dev-loop skill and inspect the running UI.
- [x] Document commands, precise security controls and remaining enterprise gates.
- [x] Review all changes; do not merge or deploy. Report local verification
  independently from hosted CI.

## Local evidence — 2026-10-30

- Frontend lint, formatting and TypeScript checks passed; nine Node behavioral
  tests cover validation, sample session isolation, expiry, idempotency and CSP.
- The standalone production build passed. Six sample browser scenarios and one
  default-disconnected scenario passed. The form validation scenario first
  reproduced an erased invalid name; a controlled input now preserves that value.
- Existing prototype tests: 12 passed. `make check`, `make build` and actionlint
  passed. Dependency audit reported no known vulnerabilities at inspection time.
- Next dev diagnostics reported no compilation/runtime errors. Desktop/mobile
  previews were inspected; automated accessibility scans reported no violations
  after label contrast adjustments. This is not an accessibility certification.
- The new frontend CI job has not run on GitHub yet. No merge, release or deployment
  is part of this local implementation.
