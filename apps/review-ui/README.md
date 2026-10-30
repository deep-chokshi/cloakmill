# CloakMill review workspace

Step 2A of the application frontend: Next.js App Router, TypeScript, local fonts,
project creation, source inventory and coverage details. All records are fictional.
The remaining workflow screens are explicit planned states.

## Run locally

Node 22.23.2 is used in CI (the package supports Node 22.13+ through 24).

```bash
cd apps/review-ui
npm ci
npm run dev
```

Open http://127.0.0.1:4318. Development explicitly enables the sample store. Create
a sample project or select **Explore sample workspace**. Projects are separated by
an opaque browser-session cookie, held in bounded server memory, and expire after
two hours or a server restart. Multiple tabs in the same browser share the session.
Use fictional names only. Real file ingestion and enterprise sign-in are absent.

## Verify the production bundle

```bash
npm run check
npm run build
npm exec playwright install chromium
npm run test:e2e
npm run test:disconnected
```

The build copies static assets into Next's standalone output. `npm run start:sample`
runs that bundle on loopback with fictional data. `npm start` leaves the sample
backend disabled unless `CLOAKMILL_SAMPLE_MODE=1` is explicitly set; it shows a
not-connected state. Both commands listen on 127.0.0.1:4318. Do not run them at the
same time as the development server or browser tests.

`npm run format` formats code; `npm run format:check` verifies it. Lint uses the
official Next plugin, React Hooks and TypeScript plugins compatible with ESLint 10.
The umbrella Next preset currently includes legacy plugins with older peer ranges,
so it is not used. Browser accessibility checks supplement those lint rules.

## Boundaries implemented here

- Server Components read through `src/server/workspace.ts`, marked `server-only`.
- Server Actions validate names, identifiers and submission keys. Every resource
  lookup is scoped to the cookie's sample session. Source loads and project-form
  retries within a session are idempotent.
- DTOs contain display fields; private source locators and session tokens are not
  returned to components. No arbitrary upstream HTTP proxy or filesystem reader exists.
- Dynamic responses have per-request nonce CSP, same-origin connections, framing
  restrictions, no-store caching, nosniff and no-referrer headers. Production CSP
  permits neither unsafe-inline nor unsafe-eval scripts. Dev permits eval for React
  debugging and the loopback HMR connection.
- Fonts and assets are local. Telemetry is disabled by the run/build scripts and CI.
- The sample cookie is HttpOnly and SameSite=Strict. `CLOAKMILL_HTTPS=1` adds Secure
  for TLS environments. Plain HTTP cookies are a loopback sample-only exception.

These are tested foundation controls, not enterprise authentication. Server Actions
are visible/callable HTTP endpoints. Any returned HTML, RSC data, JavaScript or
JSON can be inspected by the browser user. Hidden server code cannot prevent users
from copying data they are authorized to view.

## Before private enterprise data

Read [the web security design](../../docs/architecture/web-security.md). SSO/MFA,
RBAC, tenant/project authorization backed by a real identity provider, persistent
sessions, authenticated private Python APIs, audit retention, TLS ingress, customer
keys, recovery, ingestion isolation and offline installation qualification remain
unimplemented. This single-process sample store is deliberately not distributed
storage or an authentication service.

Next.js 16.4.3 and React 19.3.1 were the stable releases verified on 2026-10-30.
Review the [announced November 3 security update](https://nextjs.org/blog/upcoming-nextjs-security-release-november-2026)
before production deployment. A dependency audit with zero findings is not proof
that the application or framework has no vulnerabilities.
