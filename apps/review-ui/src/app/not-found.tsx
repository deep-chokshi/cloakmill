import Link from "next/link";
export default function NotFound() {
  return (
    <section className="empty-state">
      <p className="eyebrow">No accessible record</p>
      <h1 tabIndex={-1}>Workspace unavailable</h1>
      <p>
        This route does not exist in your sample session, or the session has
        expired.
      </p>
      <Link href="/" prefetch={false} className="button secondary">
        Return to workspace
      </Link>
    </section>
  );
}
