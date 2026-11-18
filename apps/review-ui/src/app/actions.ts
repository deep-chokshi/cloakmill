"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { ActionResult } from "@/lib/contracts";
import type { MappingMutation } from "@/lib/identity-model";
import { parseProjectName, WorkspaceError } from "@/lib/workspace-store";
import { createProject, loadSamples, mutateMapping } from "@/server/workspace";

function safeError(error: unknown): ActionResult {
  return {
    error:
      error instanceof WorkspaceError
        ? error.message
        : "The request could not be completed. Please try again.",
  };
}

function assertProjectId(projectId: unknown): string {
  if (typeof projectId !== "string" || projectId.length > 64)
    throw new WorkspaceError("This project is unavailable.");
  return projectId;
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
    await loadSamples(assertProjectId(projectId));
  } catch (error) {
    return safeError(error);
  }
  revalidatePath("/", "layout");
  return {};
}

async function mappingAction(
  projectId: string,
  mutation: MappingMutation,
): Promise<ActionResult> {
  try {
    await mutateMapping(assertProjectId(projectId), mutation);
  } catch (error) {
    return safeError(error);
  }
  revalidatePath("/", "layout");
  return {};
}

export async function decideIdentityAction(
  projectId: string,
  _state: ActionResult,
  data: FormData,
): Promise<ActionResult> {
  const caseId = data.get("caseId");
  const value = data.get("value");
  if (
    typeof caseId !== "string" ||
    caseId.length > 64 ||
    typeof value !== "string" ||
    value.length > 64
  ) {
    return { error: "That identity choice is not available." };
  }
  return mappingAction(projectId, { type: "DECIDE", caseId, value });
}

export async function reopenIdentityAction(
  projectId: string,
  caseId: string,
  _state: ActionResult,
): Promise<ActionResult> {
  if (typeof caseId !== "string" || caseId.length > 64) {
    return { error: "That identity decision could not be reopened." };
  }
  return mappingAction(projectId, { type: "REOPEN", caseId });
}

export async function setProfileAction(
  projectId: string,
  _state: ActionResult,
  data: FormData,
): Promise<ActionResult> {
  const profileId = data.get("profileId");
  if (typeof profileId !== "string" || profileId.length > 64) {
    return { error: "That sample profile preset is not available." };
  }
  return mappingAction(projectId, { type: "SET_PROFILE", profileId });
}

export async function excludeUnsupportedAction(
  projectId: string,
  value: boolean,
  _state: ActionResult,
): Promise<ActionResult> {
  return mappingAction(projectId, {
    type: "EXCLUDE_UNSUPPORTED",
    value: Boolean(value),
  });
}

export async function freezeMappingAction(
  projectId: string,
  _state: ActionResult,
): Promise<ActionResult> {
  return mappingAction(projectId, { type: "FREEZE" });
}
