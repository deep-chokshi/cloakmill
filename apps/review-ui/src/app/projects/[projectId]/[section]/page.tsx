import Link from "next/link";
import { notFound } from "next/navigation";
import { IdentityReview } from "@/components/identity-review";
import { LoadSamples } from "@/components/project-form";
import { ProfilesPanel } from "@/components/profiles-panel";
import { stages } from "@/lib/contracts";
import { readMapping, readProject, readSources } from "@/server/workspace";

export default async function ProjectPage({
  params,
  searchParams,
}: {
  params: Promise<{ projectId: string; section: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { projectId, section } = await params;
  const query = await searchParams;
  const stage = stages.find((item) => item.id === section);
  const project = await readProject(projectId);
  if (!project || !stage) notFound();
  const sources = await readSources(projectId);
  const covered = sources.filter((source) => source.coverage === "sample");

  if (section === "identities" || section === "profiles") {
    const mapping = await readMapping(projectId);
    if (!mapping) notFound();
    if (section === "identities") {
      const tab = query.tab === "all" ? "all" : "review";
      const selectedId =
        typeof (tab === "all" ? query.entity : query.case) === "string"
          ? ((tab === "all" ? query.entity : query.case) as string)
          : undefined;
      return (
        <IdentityReview
          projectId={projectId}
          projectName={project.name}
          mapping={mapping}
          tab={tab}
          selectedId={selectedId}
        />
      );
    }
    return (
      <ProfilesPanel
        projectId={projectId}
        projectName={project.name}
        mapping={mapping}
      />
    );
  }

  if (section === "overview")
    return (
      <>
        <div className="page-heading">
          <div>
            <p className="eyebrow">Project overview</p>
            <h1 tabIndex={-1}>{project.name}</h1>
            <p>
              Your source inventory is the first step toward a consistent
              dataset.
            </p>
          </div>
          <span className="badge subtle">FICTIONAL WORKSPACE</span>
        </div>
        <div className="stats-grid">
          <div>
            <p>Sources in scope</p>
            <strong>{sources.length.toString().padStart(2, "0")}</strong>
            <small>Authored sample inventory</small>
          </div>
          <div>
            <p>Sample records</p>
            <strong>
              {sources
                .reduce((sum, source) => sum + (source.records ?? 0), 0)
                .toString()
                .padStart(2, "0")}
            </strong>
            <small>Across declared surfaces</small>
          </div>
          <div>
            <p>Coverage gaps</p>
            <strong>
              {sources
                .filter((source) => source.coverage === "unavailable")
                .length.toString()
                .padStart(2, "0")}
            </strong>
            <small>Visible before processing</small>
          </div>
        </div>
        <section className="next-step">
          <div>
            <p className="eyebrow">Your next step</p>
            <h2>
              {sources.length
                ? "Review identities and freeze profiles."
                : "No sources yet"}
            </h2>
            <p>
              {sources.length
                ? "Inspect coverage, resolve authored sample exceptions, then freeze a fictional mapping revision."
                : "Start with fictional sources to explore the inventory. Real file ingestion comes in a later step."}
            </p>
          </div>
          <Link
            className="button primary"
            href={
              sources.length
                ? `/projects/${projectId}/identities`
                : `/projects/${projectId}/sources`
            }
            prefetch={false}
          >
            {sources.length ? "Open identity review" : "Add sample sources"}{" "}
            <span aria-hidden="true">↗</span>
          </Link>
        </section>
        <section className="section-block">
          <div className="section-heading">
            <h2>From context to release</h2>
            <span className="muted small">The intended journey</span>
          </div>
          <div className="journey-grid">
            {[
              "Scope sources",
              "Review identities",
              "Freeze replacements",
              "Verify a release",
            ].map((title, i) => (
              <div key={title}>
                <span className={i <= 2 ? "step active-step" : "step"}>
                  {i + 1}
                </span>
                <h3>{title}</h3>
                <p>
                  {i <= 2
                    ? "Available with samples"
                    : "Coming in a later increment"}
                </p>
              </div>
            ))}
          </div>
        </section>
      </>
    );
  if (section === "sources")
    return (
      <>
        <div className="page-heading">
          <div>
            <p className="eyebrow">Scope before processing</p>
            <h1 tabIndex={-1}>Source inventory</h1>
            <p>
              Know what is present, what is covered, and what needs another
              path.
            </p>
          </div>
          {!sources.length && <LoadSamples projectId={projectId} />}
        </div>
        <div className="notice">
          <span aria-hidden="true">ⓘ</span>
          <p>
            Sample metadata only. Local folders, files, and export connectors
            are not connected yet.
          </p>
        </div>
        {sources.length ? (
          <section className="table-panel">
            <div className="table-title">
              <h2>Project sources</h2>
              <span>
                {covered.length} sample surfaces ·{" "}
                {sources.length - covered.length} unavailable
              </span>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Format</th>
                    <th>Records</th>
                    <th>Coverage</th>
                    <th>
                      <span className="sr-only">Details</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sources.map((source) => (
                    <tr key={source.id}>
                      <td>
                        <Link
                          prefetch={false}
                          href={`/projects/${projectId}/sources/${source.id}`}
                          className="source-name"
                        >
                          {source.name}
                        </Link>
                        <small>{source.description}</small>
                      </td>
                      <td>
                        <span className="format-tag">{source.format}</span>
                      </td>
                      <td>{source.records ?? "Unknown"}</td>
                      <td>
                        <span
                          className={`badge ${source.coverage === "unavailable" ? "warning" : "good"}`}
                        >
                          {source.coverage === "unavailable"
                            ? "Unavailable"
                            : "Sample coverage"}
                        </span>
                      </td>
                      <td aria-hidden="true">↗</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : (
          <section className="empty-state">
            <span className="empty-symbol" aria-hidden="true">
              ▤
            </span>
            <h2>No sources yet</h2>
            <p>
              Load the fictional directory, conversations, notes, and
              unavailable PDF sample using the action above.
            </p>
          </section>
        )}
      </>
    );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">{project.name}</p>
          <h1 tabIndex={-1}>{stage.label}</h1>
        </div>
        <span className="badge subtle">PLANNED</span>
      </div>
      <section className="empty-state">
        <span className="empty-symbol" aria-hidden="true">
          {stage.glyph}
        </span>
        <h2>This step is being built.</h2>
        <p>
          The approved design includes this stage. Identity review and
          replacement profiles are available with authored samples; preview,
          validation, and releases land in a later increment. No privacy engine
          has run.
        </p>
        <Link
          className="button secondary"
          href={`/projects/${projectId}/profiles`}
          prefetch={false}
        >
          Return to profiles <span aria-hidden="true">↗</span>
        </Link>
      </section>
    </>
  );
}
