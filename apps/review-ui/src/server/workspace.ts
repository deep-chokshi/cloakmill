import "server-only";
import { cookies } from "next/headers";
import { WorkspaceError, WorkspaceStore } from "@/lib/workspace-store";

const scope = globalThis as typeof globalThis & {
  __cloakmillSampleStore?: WorkspaceStore;
};
const store = (scope.__cloakmillSampleStore ??= new WorkspaceStore());
const cookieName = "cloakmill-sample";

export function sampleMode() {
  return process.env.CLOAKMILL_SAMPLE_MODE === "1";
}
function requireSampleMode() {
  if (!sampleMode())
    throw new WorkspaceError("The workspace backend is not connected.");
}
async function token() {
  return (await cookies()).get(cookieName)?.value;
}

export async function readProjects() {
  return sampleMode() ? store.listProjects(await token()) : [];
}
export async function readProject(id: string) {
  return sampleMode() ? store.getProject(await token(), id) : null;
}
export async function readSources(projectId: string) {
  requireSampleMode();
  return store.listSources(await token(), projectId);
}
export async function readSource(projectId: string, sourceId: string) {
  return sampleMode()
    ? store.getSource(await token(), projectId, sourceId)
    : null;
}
export async function createProject(
  name: string,
  key: string,
  withSamples: boolean,
) {
  requireSampleMode();
  const jar = await cookies();
  let session = jar.get(cookieName)?.value;
  if (!store.hasSession(session)) {
    session = store.createSession();
    jar.set(cookieName, session, {
      httpOnly: true,
      sameSite: "strict",
      path: "/",
      // HTTP is only for the explicitly enabled, loopback sample workspace.
      secure: process.env.CLOAKMILL_HTTPS === "1",
    });
  }
  const project = store.createProject(session!, name, key);
  if (withSamples) store.loadSamples(session, project.id);
  return project;
}
export async function loadSamples(projectId: string) {
  requireSampleMode();
  return store.loadSamples(await token(), projectId);
}
