import Link from "next/link";
import { LoadSamples } from "@/components/project-form";
import {
  ExcludeUnsupported,
  FreezeMapping,
  ProfileSelect,
} from "@/components/identity-forms";
import {
  canFreeze,
  freezeBlockers,
  isFrozen,
  type MappingWorkspace,
} from "@/lib/identity-model";

function kindLabel(kind: string) {
  if (kind === "person") return "Person";
  if (kind === "shared_account") return "Shared account";
  if (kind === "organization") return "Organization";
  return kind;
}

export function ProfilesPanel({
  projectId,
  projectName,
  mapping,
}: {
  projectId: string;
  projectName: string;
  mapping: MappingWorkspace;
}) {
  const frozen = isFrozen(mapping);
  const blockers = freezeBlockers(mapping);
  const eligible = canFreeze(mapping);
  const profile = mapping.profiles.find(
    (item) => item.id === mapping.profileId,
  );

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">{projectName} · replacement profiles</p>
          <h1 tabIndex={-1}>New identities. Same connections.</h1>
          <p>
            Review a coherent sample profile before freezing the mapping for
            this revision.
          </p>
        </div>
        <span className={`badge ${frozen ? "good" : "subtle"}`}>
          {frozen ? `FROZEN · r${mapping.revision}` : "FICTIONAL SAMPLE"}
        </span>
      </div>
      <div className="notice">
        <span aria-hidden="true">ⓘ</span>
        <p>
          All replacement values are authored fictional examples. Freezing
          creates a sample mapping snapshot reference only—it is not a privacy
          guarantee and does not connect a live assignment engine.
        </p>
      </div>
      {mapping.status !== "ready" ? (
        <section className="empty-state">
          <span className="empty-symbol" aria-hidden="true">
            ⇄
          </span>
          <h2>No profiles to review</h2>
          <p>
            Load sample sources to populate the authored entity graph and
            namespace-scoped replacement presets.
          </p>
          <LoadSamples projectId={projectId} />
        </section>
      ) : (
        <>
          <div className="profiles-layout">
            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>Your replacement profile</h2>
                  <p>All values below are authored fictional examples.</p>
                </div>
                <ProfileSelect
                  projectId={projectId}
                  profileId={mapping.profileId}
                  options={mapping.profiles.map((item) => ({
                    id: item.id,
                    label: item.label,
                  }))}
                />
              </div>
              <div className="table-scroll">
                <table className="profile-table">
                  <thead>
                    <tr>
                      <th>Source identity</th>
                      <th>
                        <span className="sr-only">Maps to</span>
                      </th>
                      <th>Replacement identity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mapping.entities.map((entity) => {
                      const replacement = profile?.replacements[entity.id];
                      return (
                        <tr key={entity.id}>
                          <td>
                            <div className="person-cell">
                              <span className="avatar" aria-hidden="true">
                                {entity.initials}
                              </span>
                              <span>
                                <strong>{entity.name}</strong>
                                <small>{kindLabel(entity.kind)}</small>
                              </span>
                            </div>
                          </td>
                          <td aria-hidden="true">→</td>
                          <td>
                            <div className="replacement-name">
                              {replacement?.name ?? "—"}
                            </div>
                            <div className="replacement-email">
                              {replacement?.email || "Organization profile"}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
            <div className="profiles-side">
              <section className="panel panel-body">
                <p className="eyebrow">Mapping namespace</p>
                <p className="muted gap-top">
                  Keep this project&apos;s replacement identities consistent
                  within its recipient scope.
                </p>
                <div className="namespace-field gap-top">
                  {mapping.namespace}
                </div>
                <div className="attribute-row gap-top">
                  <span>People and aliases</span>
                  <strong>Replace together</strong>
                </div>
                <div className="attribute-row">
                  <span>Email addresses</span>
                  <strong>Reserved domains</strong>
                </div>
                <div className="attribute-row">
                  <span>Shared accounts</span>
                  <strong>Keep separate</strong>
                </div>
                <div className="attribute-row">
                  <span>Sample dates / record IDs</span>
                  <strong>Preserve</strong>
                </div>
              </section>
              <p className="note gap-top">
                These presets demonstrate profile choices. A production policy
                editor and identity generator belong to later steps.
              </p>
              <section className="panel panel-body gap-top">
                <p className="eyebrow">Unsupported coverage</p>
                <p className="muted">
                  {mapping.excludedUnsupported
                    ? "The encrypted PDF sample is excluded from this revision."
                    : "Exclude the unavailable encrypted PDF before freezing."}
                </p>
                <div className="gap-top">
                  <ExcludeUnsupported
                    projectId={projectId}
                    excluded={mapping.excludedUnsupported}
                  />
                </div>
              </section>
            </div>
          </div>
          <div className="freeze-panel">
            <div>
              <h3>
                {frozen
                  ? "This sample mapping is frozen."
                  : "Make this mapping the reference point."}
              </h3>
              <p>
                {frozen
                  ? `${mapping.snapshotRef} · Editing a decision or profile will invalidate it.`
                  : "Resolve identity and source decisions before freezing this revision."}
              </p>
              {!frozen && blockers.length > 0 && (
                <ul className="blocker-list">
                  {blockers.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              )}
            </div>
            <div className="freeze-actions">
              {frozen ? (
                <Link
                  className="button secondary"
                  href={`/projects/${projectId}/preview`}
                  prefetch={false}
                >
                  Preview is planned next <span aria-hidden="true">↗</span>
                </Link>
              ) : (
                <FreezeMapping
                  projectId={projectId}
                  canFreeze={eligible}
                  frozen={frozen}
                />
              )}
              {!frozen && !mapping.decisions.maya && (
                <Link
                  className="button secondary"
                  href={`/projects/${projectId}/identities`}
                  prefetch={false}
                >
                  Open identity review
                </Link>
              )}
            </div>
          </div>
        </>
      )}
    </>
  );
}
