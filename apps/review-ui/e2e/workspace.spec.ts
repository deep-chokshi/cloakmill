import { test, expect, type Page } from "@playwright/test";

test("late source navigation cannot replace a subsequently selected project", async ({
  page,
}) => {
  await page.goto("/");
  await create(page, "Project B");
  await page.getByRole("link", { name: "Projects", exact: true }).click();
  await create(page, "Project A");
  let release!: () => void;
  let started!: () => void;
  let fulfilled!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const intercepted = new Promise<void>((resolve) => {
    started = resolve;
  });
  const complete = new Promise<void>((resolve) => {
    fulfilled = resolve;
  });
  await page.route(/\/projects\/[^/]+\/sources\?_rsc=/, async (route) => {
    const response = await route.fetch();
    started();
    await gate;
    await route.fulfill({ response });
    fulfilled();
  });
  await page.getByRole("link", { name: "Sources", exact: true }).click();
  await intercepted;
  await page.getByRole("link", { name: "Projects", exact: true }).click();
  await page
    .getByRole("link")
    .filter({
      has: page.getByRole("heading", { name: "Project B", exact: true }),
    })
    .click();
  release();
  await complete;
  await expect(
    page.getByRole("heading", { name: "Project B", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Source inventory" }),
  ).toHaveCount(0);
});

async function create(page: Page, name: string) {
  await page
    .getByRole("button", { name: "Create sample project", exact: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Project name").fill(name);
  await dialog
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
}

test("create, load samples, inspect coverage, navigate and recover from unknown routes", async ({
  page,
}) => {
  await page.goto("/");
  await create(page, "Research <pilot>");
  await expect(page.getByText("No sources yet", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Sources", exact: true }).click();
  await page
    .getByRole("button", { name: "Load sample sources", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Team directory.csv", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Unavailable", { exact: true })).toBeVisible();
  await page
    .getByRole("link", { name: "Team directory.csv", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Team directory.csv", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "No file has been parsed. CSV ingestion is a later milestone.",
    ),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Team directory.csv", exact: true }),
  ).toBeVisible();
  await page.goBack();
  await page
    .getByRole("link", { name: "Identity review", exact: true })
    .click();
  await expect(
    page.getByText("This step is being built.", { exact: true }),
  ).toBeVisible();
  await page.goto("/projects/not-a-project/overview");
  await expect(
    page.getByRole("heading", { name: "Workspace unavailable" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Return to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Research <pilot>", exact: true }),
  ).toBeVisible();
});

test("form validation, Escape and focus restoration work on mobile without overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const opener = page
    .getByRole("button", { name: "Create sample project", exact: true })
    .first();
  await opener.click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
    "project name",
  );
  const invalidName = "x".repeat(121);
  await page.getByRole("dialog").getByLabel("Project name").fill(invalidName);
  const validationResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      Boolean(response.request().headers()["next-action"]),
  );
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await validationResponse;
  await expect(
    page
      .getByRole("dialog")
      .getByRole("button", { name: "Create project", exact: true }),
  ).toBeEnabled();
  await expect(page.getByRole("dialog").getByRole("alert")).toBeVisible();
  await expect(page.getByRole("dialog").getByLabel("Project name")).toHaveValue(
    invalidName,
  );
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(opener).toBeFocused();
  await create(page, "Mobile pilot");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("dialog", { name: "Workspace navigation" })
    .getByRole("link", { name: "Sources", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Source inventory" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Source inventory" }),
  ).toBeFocused();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("known project IDs cannot expose another browser session and responses omit private fields", async ({
  page,
  browser,
}) => {
  await page.goto("/");
  await create(page, "Private sample A");
  const projectUrl = page.url();
  const other = await browser.newContext();
  const outsider = await other.newPage();
  await outsider.goto(projectUrl);
  await expect(
    outsider.getByRole("heading", { name: "Workspace unavailable" }),
  ).toBeVisible();
  expect(await outsider.content()).not.toContain("Private sample A");
  const response = await page.request.get(projectUrl);
  expect(await response.text()).not.toMatch(
    /vault:\/\/|privateLocator|__cloakmillSampleStore/,
  );
  const cookie = (await page.context().cookies()).find(
    (item) => item.name === "cloakmill-sample",
  );
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe("Strict");
  expect(cookie?.value).toMatch(/^[a-f0-9]{64}$/);
  await other.close();
});

test("production CSP is nonce-based, private pages are not cached, and assets remain local", async ({
  page,
}) => {
  const remote: string[] = [];
  const failures: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).origin !== "http://127.0.0.1:4318")
      remote.push(request.url());
  });
  page.on("pageerror", (error) => failures.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") failures.push(message.text());
  });
  const first = await page.goto("/");
  const firstCsp = first!.headers()["content-security-policy"];
  expect(firstCsp).toContain("frame-ancestors 'none'");
  expect(firstCsp).not.toMatch(/unsafe-eval|unsafe-inline/);
  expect(first!.headers()["x-content-type-options"]).toBe("nosniff");
  expect(first!.headers()["cache-control"]).toContain("no-store");
  const second = await page.reload();
  expect(second!.headers()["content-security-policy"]).not.toBe(firstCsp);
  await create(page, "Network check");
  await page.getByRole("link", { name: "Sources", exact: true }).click();
  await page
    .getByRole("button", { name: "Load sample sources", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Team directory.csv", exact: true }),
  ).toBeVisible();
  expect(remote).toEqual([]);
  expect(failures).toEqual([]);
  expect(
    await page.evaluate(() => ({
      local: localStorage.length,
      session: sessionStorage.length,
    })),
  ).toEqual({ local: 0, session: 0 });
});

test("direct Action replays cannot cross sessions and cross-origin mutations are rejected", async ({
  page,
  browser,
}) => {
  await page.goto("/");
  await create(page, "Action boundary");
  await page.getByRole("link", { name: "Sources", exact: true }).click();
  const actionRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" && Boolean(request.headers()["next-action"]),
  );
  await page
    .getByRole("button", { name: "Load sample sources", exact: true })
    .click();
  const request = await actionRequest;
  const headers = {
    "content-type": request.headers()["content-type"],
    "next-action": request.headers()["next-action"],
    origin: "http://127.0.0.1:4318",
  };
  const other = await browser.newContext();
  const replay = await other.request.post(request.url(), {
    headers,
    data: request.postData()!,
  });
  expect(await replay.text()).toContain("unavailable");
  const crossOrigin = await page.request.post(request.url(), {
    headers: { ...headers, origin: "https://untrusted.example" },
    data: request.postData()!,
  });
  expect(crossOrigin.status()).toBeGreaterThanOrEqual(400);
  await other.close();
});
