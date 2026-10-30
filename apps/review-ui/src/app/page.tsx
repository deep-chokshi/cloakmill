import { randomUUID } from "node:crypto";
import Link from "next/link";
import { ExploreSample } from "@/components/project-form";
import { readProjects, sampleMode } from "@/server/workspace";

export default async function Page() {
  const projects = await readProjects();
  if (!sampleMode())
    return (
      <section className="empty-state">
        <p className="eyebrow">Connection required</p>
        <h1 tabIndex={-1}>Workspace is not connected.</h1>
        <p>
          The persistent backend and enterprise sign-in are not configured. No
          customer data can be processed here.
        </p>
      </section>
    );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Your starting point</p>
          <h1 tabIndex={-1}>A workspace for every dataset.</h1>
          <p>
            Keep source coverage, identity decisions, and releases together.
          </p>
        </div>
        <span className="page-number">01 / WORKSPACE</span>
      </div>
      <section className="welcome-panel">
        <div>
          <span className="badge">START WITH CONTEXT</span>
          <h2>
            Meet the workspace.
            <br />
            <em>Follow the evidence.</em>
          </h2>
          <p>
            Explore a fictional cross-source dataset and see how coverage
            becomes a clear first decision.
          </p>
          <ExploreSample submissionKey={randomUUID()} />
        </div>
        <div className="source-illustration" aria-hidden="true">
          <div className="illustration-label">ONE CONNECTED WORKSPACE</div>
          <div className="paper-card">
            <span>CSV</span>Team directory<i>4 fictional records</i>
          </div>
          <div className="paper-card">
            <span>JSON</span>Conversations<i>5 fictional records</i>
          </div>
          <div className="paper-card">
            <span>TXT</span>Project handoff<i>3 fictional records</i>
          </div>
          <div className="illustration-foot">
            Original context. Deliberate decisions.
          </div>
        </div>
      </section>
      <section className="section-block">
        <div className="section-heading">
          <h2>
            Your projects <span className="count">{projects.length}</span>
          </h2>
          <p>Available in this sample session</p>
        </div>
        {projects.length ? (
          <div className="project-grid">
            {projects.map((project) => (
              <Link
                prefetch={false}
                key={project.id}
                href={`/projects/${project.id}/overview`}
                className="project-card"
              >
                <div className="card-top">
                  <span className="project-symbol" aria-hidden="true">
                    ◫
                  </span>
                  <span className="badge subtle">SAMPLE</span>
                </div>
                <h3>{project.name}</h3>
                <p>{project.sourceCount} sources in scope</p>
                <span className="card-link">
                  Open workspace <span aria-hidden="true">↗</span>
                </span>
              </Link>
            ))}
          </div>
        ) : (
          <div className="empty-projects">
            <span className="empty-symbol" aria-hidden="true">
              ◫
            </span>
            <div>
              <h3>No projects yet</h3>
              <p>
                Create a sample project above, or explore the fictional
                workspace.
              </p>
            </div>
          </div>
        )}
      </section>
      <p className="boundary-note">
        Samples are held in server memory for two hours. A server restart clears
        them. No uploads or real connections are enabled.
      </p>
    </>
  );
}
