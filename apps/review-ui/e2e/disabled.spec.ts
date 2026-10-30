import { test, expect } from "@playwright/test";

test("default production start exposes no sample data or mutation UI", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Workspace is not connected." }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Create sample project" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Explore sample workspace" }),
  ).toHaveCount(0);
  await page.goto("/projects/not-a-project/sources");
  await expect(
    page.getByRole("heading", { name: "Workspace unavailable" }),
  ).toBeVisible();
  expect(await page.context().cookies()).toEqual([]);
});
