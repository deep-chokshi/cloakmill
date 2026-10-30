import Link from "next/link";
import { notFound } from "next/navigation";
import { readSource } from "@/server/workspace";

export default async function SourcePage({
  params,
}: {
  params: Promise<{ projectId: string; sourceId: string }>;
}) {
  const { projectId, sourceId } = await params;
  const source = await readSource(projectId, sourceId);
  if (!source) notFound();
  return (
    <>
      <Link
        className="back-link"
        href={`/projects/${projectId}/sources`}
        prefetch={false}
      >
        ← Source inventory
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Source details · {source.format}</p>
          <h1 tabIndex={-1}>{source.name}</h1>
          <p>{source.description}</p>
        </div>
        <span
          className={`badge ${source.coverage === "unavailable" ? "warning" : "good"}`}
        >
          {source.coverage === "unavailable"
            ? "Unavailable"
            : "Sample coverage"}
        </span>
      </div>
      <div className="detail-grid">
        <section className="detail-panel">
          <p className="eyebrow">Declared surfaces</p>
          <h2>What is present</h2>
          {source.surfaces.length ? (
            <ul className="surface-list">
              {source.surfaces.map((surface) => (
                <li key={surface}>{surface}</li>
              ))}
            </ul>
          ) : (
            <p>No readable content is available for this sample.</p>
          )}
          <div className="detail-total">
            <strong>{source.records ?? "—"}</strong>
            <span>
              {source.records === null
                ? "Record count unknown"
                : "Fictional records"}
            </span>
          </div>
        </section>
        <section className="detail-panel limitation">
          <p className="eyebrow">Coverage boundary</p>
          <h2>What to keep in mind</h2>
          <ul>
            {source.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
          <p className="small muted">
            This inventory describes authored samples. It does not certify a
            format parser, connector, or privacy result.
          </p>
        </section>
      </div>
    </>
  );
}
