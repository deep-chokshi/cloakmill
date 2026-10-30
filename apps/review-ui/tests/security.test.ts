import assert from "node:assert/strict";
import test from "node:test";
import { contentSecurityPolicy } from "../src/lib/security.ts";

test("production CSP allows nonce scripts and rejects eval, arbitrary connections and framing", () => {
  const nonce = "dGVzdC1ub25jZS1zeW50aGV0aWM=";
  const csp = contentSecurityPolicy(nonce, false);
  assert.ok(csp.includes(`'nonce-${nonce}'`));
  assert.ok(csp.includes("connect-src 'self'"));
  assert.ok(csp.includes("frame-ancestors 'none'"));
  assert.ok(csp.includes("object-src 'none'"));
  assert.ok(csp.includes("form-action 'self'"));
  assert.doesNotMatch(csp, /unsafe-eval|unsafe-inline|https:|\*/);
});

test("only development permits eval; nonce cannot inject a policy directive", () => {
  assert.match(
    contentSecurityPolicy("dGVzdC1ub25jZS1zeW50aGV0aWM=", true),
    /unsafe-eval/,
  );
  assert.throws(
    () => contentSecurityPolicy("'; script-src *", false),
    /nonce/i,
  );
});
