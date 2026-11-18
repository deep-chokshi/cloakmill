import {
  namespaceForProject,
  sampleEntities,
  sampleProfilePresets,
  sampleReviewCases,
  type ProfilePreset,
  type ReviewCase,
  type SampleEntity,
} from "./identity-fixtures.ts";

/** Browser-safe mapping workspace DTO aligned with planned freeze/snapshot contracts. */
export type MappingWorkspace = {
  status: "empty" | "ready";
  namespace: string;
  revision: number;
  frozenRevision: number | null;
  profileId: string;
  decisions: Record<string, string>;
  excludedUnsupported: boolean;
  snapshotRef: string | null;
  entities: SampleEntity[];
  reviewCases: ReviewCase[];
  profiles: ProfilePreset[];
};

export type MappingMutation =
  | { type: "DECIDE"; caseId: string; value: string }
  | { type: "REOPEN"; caseId: string }
  | { type: "SET_PROFILE"; profileId: string }
  | { type: "EXCLUDE_UNSUPPORTED"; value: boolean }
  | { type: "FREEZE" };

export function createEmptyMapping(projectName: string): MappingWorkspace {
  return {
    status: "empty",
    namespace: namespaceForProject(projectName),
    revision: 1,
    frozenRevision: null,
    profileId: "birch",
    decisions: {},
    excludedUnsupported: false,
    snapshotRef: null,
    entities: [],
    reviewCases: [],
    profiles: [],
  };
}

export function createReadyMapping(projectName: string): MappingWorkspace {
  return {
    status: "ready",
    namespace: namespaceForProject(projectName),
    revision: 1,
    frozenRevision: null,
    profileId: "birch",
    decisions: {},
    excludedUnsupported: false,
    snapshotRef: null,
    entities: structuredClone(sampleEntities),
    reviewCases: structuredClone(sampleReviewCases),
    profiles: structuredClone(sampleProfilePresets),
  };
}

export function pendingReviews(mapping: MappingWorkspace): ReviewCase[] {
  if (mapping.status !== "ready") return [];
  return mapping.reviewCases.filter((item) => !mapping.decisions[item.id]);
}

export function freezeBlockers(mapping: MappingWorkspace): string[] {
  if (mapping.status !== "ready") {
    return ["Load sample sources to prepare the authored identity graph."];
  }
  const pending = pendingReviews(mapping).length;
  const reasons: string[] = [];
  if (pending)
    reasons.push(
      `Resolve ${pending} identity decision${pending === 1 ? "" : "s"}.`,
    );
  if (!mapping.excludedUnsupported) {
    reasons.push(
      "Explicitly exclude the unavailable encrypted PDF sample from this revision.",
    );
  }
  return reasons;
}

export function canFreeze(mapping: MappingWorkspace): boolean {
  return freezeBlockers(mapping).length === 0;
}

export function isFrozen(mapping: MappingWorkspace): boolean {
  return (
    mapping.frozenRevision !== null &&
    mapping.frozenRevision === mapping.revision
  );
}

function bump(mapping: MappingWorkspace, changes: Partial<MappingWorkspace>) {
  return {
    ...mapping,
    ...changes,
    revision: mapping.revision + 1,
    frozenRevision: null,
    snapshotRef: null,
  };
}

export function applyMappingMutation(
  mapping: MappingWorkspace,
  mutation: MappingMutation,
): MappingWorkspace {
  if (mapping.status !== "ready") return mapping;

  switch (mutation.type) {
    case "DECIDE": {
      const review = mapping.reviewCases.find(
        (item) => item.id === mutation.caseId,
      );
      if (!review?.choices.some((choice) => choice.value === mutation.value)) {
        return mapping;
      }
      if (mapping.decisions[mutation.caseId] === mutation.value) return mapping;
      return bump(mapping, {
        decisions: {
          ...mapping.decisions,
          [mutation.caseId]: mutation.value,
        },
      });
    }
    case "REOPEN": {
      if (!mapping.decisions[mutation.caseId]) return mapping;
      const decisions = { ...mapping.decisions };
      delete decisions[mutation.caseId];
      return bump(mapping, { decisions });
    }
    case "SET_PROFILE": {
      if (
        !mapping.profiles.some((profile) => profile.id === mutation.profileId)
      ) {
        return mapping;
      }
      if (mapping.profileId === mutation.profileId) return mapping;
      return bump(mapping, { profileId: mutation.profileId });
    }
    case "EXCLUDE_UNSUPPORTED": {
      if (mapping.excludedUnsupported === mutation.value) return mapping;
      return bump(mapping, { excludedUnsupported: mutation.value });
    }
    case "FREEZE": {
      if (!canFreeze(mapping)) return mapping;
      if (isFrozen(mapping)) return mapping;
      return {
        ...mapping,
        frozenRevision: mapping.revision,
        snapshotRef: `sample-map-r${mapping.revision}`,
      };
    }
    default:
      return mapping;
  }
}

/** Public DTO clone — never expose internal Map references. */
export function mappingDto(mapping: MappingWorkspace): MappingWorkspace {
  return {
    status: mapping.status,
    namespace: mapping.namespace,
    revision: mapping.revision,
    frozenRevision: mapping.frozenRevision,
    profileId: mapping.profileId,
    decisions: { ...mapping.decisions },
    excludedUnsupported: mapping.excludedUnsupported,
    snapshotRef: mapping.snapshotRef,
    entities: structuredClone(mapping.entities),
    reviewCases: structuredClone(mapping.reviewCases),
    profiles: structuredClone(mapping.profiles),
  };
}
