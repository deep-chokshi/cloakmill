import Link from "next/link";
import type { Route } from "next";
import { LoadSamples } from "@/components/project-form";
import { ConfirmDecision, ReopenDecision } from "@/components/identity-forms";
import {
  isFrozen,
  pendingReviews,
  type MappingWorkspace,
} from "@/lib/identity-model";

function kindLabel(kind: string) {
  if (kind === "person") return "Person";
  if (kind === "shared_account") return "Shared account";
  if (kind === "organization") return "Organization";
  return kind;
}

export function IdentityReview({
  projectId,
  projectName,
  mapping,
  tab,
  selectedId,
}: {
  projectId: string;
  projectName: string;
  mapping: MappingWorkspace;
  tab: "review" | "all";
  selectedId?: string;
}) {
  const frozen = isFrozen(mapping);
  const pending = pendingReviews(mapping);
  const base = `/projects/${projectId}/identities`;

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">{projectName} · identity review</p>
          <h1 tabIndex={-1}>A name isn&apos;t an identity.</h1>
          <p>
            Use authored sample evidence to keep people, accounts, and
            organizations correctly connected.
          </p>
        </div>
        <span className="badge subtle">FICTIONAL SAMPLE</span>
      </div>
      <div className="notice">
        <span aria-hidden="true">ⓘ</span>
        <p>
          Authored sample exceptions only. No live discovery engine or
          enterprise identity provider is connected. Resolving or reopening a
          decision invalidates any frozen sample mapping.
        </p>
      </div>
      {mapping.status !== "ready" ? (
        <section className="empty-state">
          <span className="empty-symbol" aria-hidden="true">
            ♧
          </span>
          <h2>No identity graph yet</h2>
          <p>
            Load the fictional sources first. The sample identity exceptions are
            authored fixtures shaped like planned domain contracts—not engine
            output.
          </p>
          <LoadSamples projectId={projectId} />
        </section>
      ) : (
        <>
          <div className="tabs" role="group" aria-label="Identity view">
            <Link
              prefetch={false}
              href={`${base}?tab=review` as Route}
              className={`tab ${tab === "review" ? "active" : ""}`}
              aria-current={tab === "review" ? "page" : undefined}
            >
              Needs review
              <span className="tab-count">{pending.length}</span>
            </Link>
            <Link
              prefetch={false}
              href={`${base}?tab=all` as Route}
              className={`tab ${tab === "all" ? "active" : ""}`}
              aria-current={tab === "all" ? "page" : undefined}
            >
              All identities
              <span className="tab-count">{mapping.entities.length}</span>
            </Link>
          </div>
          {frozen && (
            <div className="notice success-notice">
              <span aria-hidden="true">✓</span>
              <p>
                Sample mapping {mapping.snapshotRef} is frozen at revision r
                {mapping.revision}. Changing a decision will invalidate it.
              </p>
            </div>
          )}
          {tab === "all" ? (
            <AllIdentities
              projectId={projectId}
              mapping={mapping}
              selectedId={selectedId}
            />
          ) : pending.length === 0 ? (
            <section className="empty-state">
              <span className="empty-symbol" aria-hidden="true">
                ✓
              </span>
              <h2>Everyone has their place.</h2>
              <p>
                Both sample identity decisions are resolved. Exclude unsupported
                coverage if needed, then freeze replacement profiles.
              </p>
              <div className="button-row">
                <Link
                  className="button primary"
                  href={`/projects/${projectId}/profiles`}
                  prefetch={false}
                >
                  Review replacement profiles <span aria-hidden="true">↗</span>
                </Link>
                <Link
                  className="button secondary"
                  href={`${base}?tab=all` as Route}
                  prefetch={false}
                >
                  Explore all identities
                </Link>
              </div>
            </section>
          ) : (
            <ReviewQueue
              projectId={projectId}
              mapping={mapping}
              selectedId={selectedId}
            />
          )}
        </>
      )}
    </>
  );
}

function ReviewQueue({
  projectId,
  mapping,
  selectedId,
}: {
  projectId: string;
  mapping: MappingWorkspace;
  selectedId?: string;
}) {
  const pending = pendingReviews(mapping);
  const selected =
    pending.find((item) => item.id === selectedId) ?? pending[0]!;
  return (
    <div className="review-layout">
      <div className="review-list">
        {pending.map((item) => (
          <Link
            key={item.id}
            prefetch={false}
            href={`/projects/${projectId}/identities?tab=review&case=${item.id}`}
            className={`review-card ${item.id === selected.id ? "selected" : ""}`}
            aria-current={item.id === selected.id ? "page" : undefined}
          >
            <span className="badge warning">{item.kind}</span>
            <strong>{item.title}</strong>
            <p>{item.summary}</p>
            <span className="review-card-footer">
              <span>
                {item.choices.length} candidate
                {item.choices.length === 1 ? "" : "s"}
              </span>
              <span aria-hidden="true">↗</span>
            </span>
          </Link>
        ))}
        <p className="note">
          Every decision affects the replacement profile. Changes invalidate any
          current sample mapping freeze.
        </p>
      </div>
      <section className="panel review-detail">
        <p className="eyebrow">
          Identity decision / {selected.id === "maya" ? "01" : "02"}
        </p>
        <h2>{selected.title}</h2>
        <p>{selected.explanation}</p>
        <div className="evidence-block">
          <p className="eyebrow">Sample evidence</p>
          <p className="muted small">{selected.evidenceLabel}</p>
          <pre className="evidence-text">{selected.evidenceText}</pre>
        </div>
        <ConfirmDecision
          key={selected.id}
          projectId={projectId}
          review={selected}
        />
      </section>
    </div>
  );
}

function AllIdentities({
  projectId,
  mapping,
  selectedId,
}: {
  projectId: string;
  mapping: MappingWorkspace;
  selectedId?: string;
}) {
  const entity =
    mapping.entities.find((item) => item.id === selectedId) ??
    mapping.entities[0]!;
  const profile = mapping.profiles.find(
    (item) => item.id === mapping.profileId,
  );
  const replacement = profile?.replacements[entity.id];
  return (
    <div className="review-layout">
      <div className="panel entity-list">
        {mapping.entities.map((item) => (
          <Link
            key={item.id}
            prefetch={false}
            href={`/projects/${projectId}/identities?tab=all&entity=${item.id}`}
            className={`entity-row ${item.id === entity.id ? "selected" : ""}`}
            aria-current={item.id === entity.id ? "page" : undefined}
          >
            <span className="avatar" aria-hidden="true">
              {item.initials}
            </span>
            <span>
              <strong>{item.name}</strong>
              <small>
                {kindLabel(item.kind)} · {item.role}
              </small>
            </span>
          </Link>
        ))}
      </div>
      <section className="panel review-detail">
        <div className="entity-detail-heading">
          <span className="avatar large" aria-hidden="true">
            {entity.initials}
          </span>
          <div>
            <h2>{entity.name}</h2>
            <p>
              {entity.role} · {kindLabel(entity.kind)}
            </p>
          </div>
        </div>
        <div className="gap-top">
          <p className="eyebrow">Known sample aliases</p>
          <div className="alias-list">
            {entity.aliases.map((alias) => (
              <span key={alias} className="badge subtle">
                {alias}
              </span>
            ))}
          </div>
        </div>
        <div className="gap-top">
          <p className="eyebrow">Linked source evidence</p>
          {entity.sourceIds.map((id) => (
            <div key={id} className="attribute-row">
              <strong>{id}</strong>
              <span>Source-anchored fixture</span>
            </div>
          ))}
        </div>
        {replacement && (
          <div className="success-note gap-top">
            <div>
              <strong>{replacement.name}</strong>
              <p>
                Replacement profile ·{" "}
                {replacement.email || "Organization identity"}
              </p>
            </div>
          </div>
        )}
        {(entity.id === "p017" || entity.id === "p042") &&
          mapping.decisions.maya && (
            <div className="gap-top">
              <ReopenDecision
                projectId={projectId}
                caseId="maya"
                label="Revisit the ambiguous first name"
              />
            </div>
          )}
        {entity.id === "a003" && mapping.decisions.finance && (
          <div className="gap-top">
            <ReopenDecision
              projectId={projectId}
              caseId="finance"
              label="Revisit the shared-account boundary"
            />
          </div>
        )}
      </section>
    </div>
  );
}
