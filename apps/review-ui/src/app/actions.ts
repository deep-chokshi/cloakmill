"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { ActionResult } from "@/lib/contracts";
import { parseProjectName, WorkspaceError } from "@/lib/workspace-store";
import { createProject, loadSamples } from "@/server/workspace";

function safeError(error: unknown): ActionResult {
  return {
    error:
      error instanceof WorkspaceError
        ? error.message
        : "The request could not be completed. Please try again.",
  };
}

export async function createProjectAction(
  _state: ActionResult,
  data: FormData,
): Promise<ActionResult> {
  let id: string;
  try {
    const name = parseProjectName(data.get("name"));
    const key = data.get("submissionKey");
    const samples = data.get("samples");
    if (
      typeof key !== "string" ||
      !/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(key)
    ) {
      throw new WorkspaceError(
        "Invalid submission. Reopen the form and try again.",
      );
    }
    if (samples !== null && samples !== "true")
      throw new WorkspaceError("Invalid sample selection.");
    id = (await createProject(name, key, samples === "true")).id;
  } catch (error) {
    return safeError(error);
  }
  revalidatePath("/", "layout");
  redirect(`/projects/${id}/overview`);
}

export async function loadSamplesAction(
  projectId: string,
  _state: ActionResult,
): Promise<ActionResult> {
  try {
    if (typeof projectId !== "string" || projectId.length > 64)
      throw new WorkspaceError("This project is unavailable.");
    await loadSamples(projectId);
  } catch (error) {
    return safeError(error);
  }
  revalidatePath("/", "layout");
  return {};
}
