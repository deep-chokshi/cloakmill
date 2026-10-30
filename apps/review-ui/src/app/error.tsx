"use client";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <section className="empty-state" role="alert">
      <h1 tabIndex={-1}>We could not load this workspace.</h1>
      <p>Try again. No successful result has been recorded.</p>
      <button className="button secondary" onClick={reset}>
        Try again
      </button>
    </section>
  );
}
