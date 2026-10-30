"use client";

import { useActionState, useRef, useState } from "react";
import { createProjectAction, loadSamplesAction } from "@/app/actions";

function ProjectForm({
  submissionKey,
  onCancel,
}: {
  submissionKey: string;
  onCancel: () => void;
}) {
  const [state, action, pending] = useActionState(createProjectAction, {});
  const [name, setName] = useState("");
  return (
    <form action={action} noValidate>
      <p className="eyebrow">A new starting point</p>
      <h2 id="project-dialog-title">Create a sample project</h2>
      <p>Give this workspace a name. Use fictional information only.</p>
      <label htmlFor="project-name">Project name</label>
      <input
        id="project-name"
        name="name"
        value={name}
        onChange={(event) => setName(event.target.value)}
        autoFocus
        autoComplete="off"
        aria-describedby={state.error ? "project-error" : "project-hint"}
        aria-invalid={Boolean(state.error)}
      />
      <input type="hidden" name="submissionKey" value={submissionKey} />
      <p id="project-hint" className="muted small">
        1–120 characters. Samples expire after two hours or a server restart.
      </p>
      {state.error && (
        <p id="project-error" role="alert" className="form-error">
          {state.error}
        </p>
      )}
      <div className="dialog-actions">
        <button
          className="button secondary"
          type="button"
          onClick={onCancel}
          disabled={pending}
        >
          Cancel
        </button>
        <button className="button primary" disabled={pending}>
          {pending ? "Creating…" : "Create project"}
        </button>
      </div>
    </form>
  );
}

export function CreateProject() {
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const [key, setKey] = useState("");
  function close() {
    dialog.current?.close();
    opener.current?.focus();
  }
  return (
    <>
      <button
        ref={opener}
        className="button primary"
        onClick={() => {
          setKey(crypto.randomUUID());
          dialog.current?.showModal();
        }}
      >
        Create sample project
      </button>
      <dialog
        ref={dialog}
        className="project-dialog"
        aria-labelledby="project-dialog-title"
        onClose={() => opener.current?.focus()}
      >
        {key && <ProjectForm key={key} submissionKey={key} onCancel={close} />}
      </dialog>
    </>
  );
}

export function ExploreSample({ submissionKey }: { submissionKey: string }) {
  const [state, action, pending] = useActionState(createProjectAction, {});
  return (
    <form action={action}>
      <input type="hidden" name="name" value="Birch review workspace" />
      <input type="hidden" name="submissionKey" value={submissionKey} />
      <input type="hidden" name="samples" value="true" />
      <button className="button secondary" disabled={pending}>
        {pending ? "Opening…" : "Explore sample workspace"}{" "}
        <span aria-hidden="true">↗</span>
      </button>
      {state.error && (
        <p role="alert" className="form-error">
          {state.error}
        </p>
      )}
    </form>
  );
}

export function LoadSamples({ projectId }: { projectId: string }) {
  const [state, action, pending] = useActionState(
    loadSamplesAction.bind(null, projectId),
    {},
  );
  return (
    <form action={action}>
      <button className="button primary" disabled={pending}>
        {pending ? "Loading samples…" : "Load sample sources"}{" "}
        <span aria-hidden="true">＋</span>
      </button>
      {state.error && (
        <p className="form-error" role="alert">
          {state.error}
        </p>
      )}
    </form>
  );
}
