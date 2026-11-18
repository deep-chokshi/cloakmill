import { randomBytes, randomUUID } from "node:crypto";
import type { Project, Source } from "./contracts.ts";
import {
  applyMappingMutation,
  createEmptyMapping,
  createReadyMapping,
  mappingDto,
  type MappingMutation,
  type MappingWorkspace,
} from "./identity-model.ts";

export const SESSION_TTL_MS = 2 * 60 * 60 * 1000;
export class WorkspaceError extends Error {}

export function parseProjectName(input: unknown): string {
  if (typeof input !== "string")
    throw new WorkspaceError("Enter a project name.");
  const name = input.trim();
  if (!name || [...name].length > 120 || /[\p{Cc}\p{Cf}]/u.test(name)) {
    throw new WorkspaceError(
      "Use a project name of 1–120 characters, without control characters.",
    );
  }
  return name;
}

type StoredProject = Project & {
  sources: Source[];
  mapping: MappingWorkspace;
};
type Session = {
  expiresAt: number;
  projects: Map<string, StoredProject>;
  submissions: Map<string, string>;
};

// Authored metadata only. Private locators deliberately never enter the DTO.
const samples: (Source & { privateLocator: string })[] = [
  {
    id: "directory",
    name: "Team directory.csv",
    format: "CSV",
    records: 4,
    coverage: "sample",
    description: "A fictional directory that anchors people to their accounts.",
    surfaces: ["Four authored person records", "Fictional account identifiers"],
    limitations: [
      "No file has been parsed. CSV ingestion is a later milestone.",
    ],
    privateLocator: "vault://synthetic-only/directory",
  },
  {
    id: "messages",
    name: "Operations conversations.json",
    format: "JSON",
    records: 5,
    coverage: "sample",
    description:
      "Fictional conversations with shared names and account references.",
    surfaces: [
      "Five authored conversation records",
      "Fictional source relationships",
    ],
    limitations: [
      "No Slack connector or real identity discovery is connected.",
    ],
    privateLocator: "vault://synthetic-only/messages",
  },
  {
    id: "handoff",
    name: "Project handoff.txt",
    format: "TXT",
    records: 3,
    coverage: "sample",
    description: "Fictional handoff notes for the cross-source review journey.",
    surfaces: ["Three authored text records"],
    limitations: ["No text detection or transformation has run."],
    privateLocator: "vault://synthetic-only/handoff",
  },
  {
    id: "encrypted",
    name: "Encrypted archive.pdf",
    format: "PDF",
    records: null,
    coverage: "unavailable",
    description: "An unavailable sample illustrates an explicit coverage gap.",
    surfaces: [],
    limitations: [
      "Encrypted contents are unavailable.",
      "No PDF file is embedded or read.",
    ],
    privateLocator: "vault://synthetic-only/encrypted",
  },
];

function projectDto(project: StoredProject): Project {
  return {
    id: project.id,
    name: project.name,
    sourceCount: project.sources.length,
    createdAt: project.createdAt,
  };
}

function sampleSources(): Source[] {
  return samples.map((source) => ({
    id: source.id,
    name: source.name,
    format: source.format,
    records: source.records,
    coverage: source.coverage,
    description: source.description,
    surfaces: [...source.surfaces],
    limitations: [...source.limitations],
  }));
}

export class WorkspaceStore {
  #sessions = new Map<string, Session>();
  #now: () => number;
  constructor(now: () => number = Date.now) {
    this.#now = now;
  }

  #prune() {
    for (const [token, session] of this.#sessions) {
      if (session.expiresAt <= this.#now()) this.#sessions.delete(token);
    }
  }
  #session(token: string | undefined) {
    this.#prune();
    return token ? this.#sessions.get(token) : undefined;
  }
  #project(token: string | undefined, projectId: string) {
    return this.#session(token)?.projects.get(projectId);
  }
  createSession(): string {
    this.#prune();
    if (this.#sessions.size >= 128)
      throw new WorkspaceError(
        "Sample capacity reached. Try again after sessions expire.",
      );
    const token = randomBytes(32).toString("hex");
    this.#sessions.set(token, {
      expiresAt: this.#now() + SESSION_TTL_MS,
      projects: new Map(),
      submissions: new Map(),
    });
    return token;
  }
  hasSession(token: string | undefined) {
    return Boolean(this.#session(token));
  }
  listProjects(token: string | undefined): Project[] {
    return [...(this.#session(token)?.projects.values() ?? [])].map(projectDto);
  }
  getProject(token: string | undefined, id: string): Project | null {
    const project = this.#project(token, id);
    return project ? projectDto(project) : null;
  }
  createProject(token: string, input: unknown, submissionKey: string): Project {
    const name = parseProjectName(input);
    if (!/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(submissionKey)) {
      throw new WorkspaceError(
        "Invalid submission. Refresh the page and try again.",
      );
    }
    const session = this.#session(token);
    if (!session)
      throw new WorkspaceError(
        "This sample session has expired. Return to the workspace.",
      );
    const previous = session.submissions.get(submissionKey);
    if (previous) {
      const project = session.projects.get(previous)!;
      if (project.name !== name)
        throw new WorkspaceError(
          "This submission was already used. Reopen the form.",
        );
      return projectDto(project);
    }
    if (session.projects.size >= 20)
      throw new WorkspaceError(
        "Sample project limit reached for this session.",
      );
    const project: StoredProject = {
      id: randomUUID(),
      name,
      sourceCount: 0,
      createdAt: new Date(this.#now()).toISOString(),
      sources: [],
      mapping: createEmptyMapping(name),
    };
    session.projects.set(project.id, project);
    session.submissions.set(submissionKey, project.id);
    return projectDto(project);
  }
  listSources(token: string | undefined, projectId: string): Source[] {
    return structuredClone(this.#project(token, projectId)?.sources ?? []);
  }
  getSource(
    token: string | undefined,
    projectId: string,
    sourceId: string,
  ): Source | null {
    return (
      this.listSources(token, projectId).find(
        (source) => source.id === sourceId,
      ) ?? null
    );
  }
  loadSamples(token: string | undefined, projectId: string): Source[] {
    const project = this.#project(token, projectId);
    if (!project)
      throw new WorkspaceError(
        "This sample project is unavailable. Return to the workspace.",
      );
    if (!project.sources.length) {
      project.sources = sampleSources();
      project.mapping = createReadyMapping(project.name);
    }
    return structuredClone(project.sources);
  }
  getMapping(
    token: string | undefined,
    projectId: string,
  ): MappingWorkspace | null {
    const project = this.#project(token, projectId);
    return project ? mappingDto(project.mapping) : null;
  }
  mutateMapping(
    token: string | undefined,
    projectId: string,
    mutation: MappingMutation,
  ): MappingWorkspace {
    const project = this.#project(token, projectId);
    if (!project)
      throw new WorkspaceError(
        "This sample project is unavailable. Return to the workspace.",
      );
    if (project.mapping.status !== "ready") {
      throw new WorkspaceError(
        "Load sample sources before reviewing identities or profiles.",
      );
    }
    const next = applyMappingMutation(project.mapping, mutation);
    if (mutation.type === "FREEZE" && next.frozenRevision !== next.revision) {
      throw new WorkspaceError(
        "Resolve identity and coverage blockers before freezing this sample mapping.",
      );
    }
    if (
      mutation.type === "DECIDE" &&
      next.decisions[mutation.caseId] !== mutation.value
    ) {
      throw new WorkspaceError("That identity choice is not available.");
    }
    if (
      mutation.type === "SET_PROFILE" &&
      next.profileId !== mutation.profileId
    ) {
      throw new WorkspaceError("That sample profile preset is not available.");
    }
    if (mutation.type === "REOPEN" && next.decisions[mutation.caseId]) {
      throw new WorkspaceError("That identity decision could not be reopened.");
    }
    project.mapping = next;
    return mappingDto(project.mapping);
  }
}
