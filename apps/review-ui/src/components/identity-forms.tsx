"use client";

import { useActionState, useState } from "react";
import {
  decideIdentityAction,
  excludeUnsupportedAction,
  freezeMappingAction,
  reopenIdentityAction,
  setProfileAction,
} from "@/app/actions";
import type { ReviewCase } from "@/lib/identity-fixtures";

function ActionError({ error }: { error?: string }) {
  if (!error) return null;
  return (
    <p className="form-error" role="alert">
      {error}
    </p>
  );
}

export function ConfirmDecision({
  projectId,
  review,
}: {
  projectId: string;
  review: ReviewCase;
}) {
  const [choice, setChoice] = useState(
    review.choices.find((item) => item.recommended)?.value ??
      review.choices[0]?.value ??
      "",
  );
  const [state, action, pending] = useActionState(
    decideIdentityAction.bind(null, projectId),
    {},
  );
  return (
    <form action={action} className="decision-panel">
      <input type="hidden" name="caseId" value={review.id} />
      <input type="hidden" name="value" value={choice} />
      <fieldset className="candidate-list">
        <legend className="eyebrow">Choose the right connection</legend>
        {review.choices.map((item) => (
          <label
            key={item.value}
            className={`candidate ${choice === item.value ? "selected" : ""}`}
          >
            <input
              type="radio"
              name="choiceDisplay"
              value={item.value}
              checked={choice === item.value}
              onChange={() => setChoice(item.value)}
            />
            <span className="candidate-copy">
              <strong>{item.label}</strong>
              <small>{item.detail}</small>
              {item.recommended && (
                <span className="badge good">Supported by sample evidence</span>
              )}
            </span>
          </label>
        ))}
      </fieldset>
      <div className="decision-actions">
        <small>Nothing is approved until you confirm.</small>
        <button className="button primary" disabled={pending || !choice}>
          {pending
            ? "Confirming…"
            : review.id === "maya"
              ? "Confirm identity"
              : "Confirm separate account"}
        </button>
      </div>
      <ActionError error={state.error} />
    </form>
  );
}

export function ReopenDecision({
  projectId,
  caseId,
  label,
}: {
  projectId: string;
  caseId: string;
  label: string;
}) {
  const [state, action, pending] = useActionState(
    reopenIdentityAction.bind(null, projectId, caseId),
    {},
  );
  return (
    <form action={action}>
      <button className="text-button" disabled={pending}>
        {pending ? "Reopening…" : label} <span aria-hidden="true">↗</span>
      </button>
      <ActionError error={state.error} />
    </form>
  );
}

export function ProfileSelect({
  projectId,
  profileId,
  options,
  disabled,
}: {
  projectId: string;
  profileId: string;
  options: { id: string; label: string }[];
  disabled?: boolean;
}) {
  const [state, action, pending] = useActionState(
    setProfileAction.bind(null, projectId),
    {},
  );
  return (
    <form action={action} className="profile-select-form" key={profileId}>
      <label className="sr-only" htmlFor="profile-select">
        Sample replacement profile
      </label>
      <select
        id="profile-select"
        className="profile-select"
        name="profileId"
        defaultValue={profileId}
        disabled={disabled || pending}
        onChange={(event) => event.currentTarget.form?.requestSubmit()}
      >
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
      <ActionError error={state.error} />
    </form>
  );
}

export function ExcludeUnsupported({
  projectId,
  excluded,
}: {
  projectId: string;
  excluded: boolean;
}) {
  const [state, action, pending] = useActionState(
    excludeUnsupportedAction.bind(null, projectId, !excluded),
    {},
  );
  return (
    <form action={action}>
      <button
        className={`button ${excluded ? "secondary" : "primary"}`}
        disabled={pending}
      >
        {pending
          ? "Updating…"
          : excluded
            ? "Include unavailable sample again"
            : "Exclude unavailable PDF from this revision"}
      </button>
      <ActionError error={state.error} />
    </form>
  );
}

export function FreezeMapping({
  projectId,
  canFreeze,
  frozen,
}: {
  projectId: string;
  canFreeze: boolean;
  frozen: boolean;
}) {
  const [state, action, pending] = useActionState(
    freezeMappingAction.bind(null, projectId),
    {},
  );
  if (frozen) return null;
  return (
    <form action={action}>
      <button className="button primary" disabled={pending || !canFreeze}>
        {pending ? "Freezing…" : "Freeze sample mapping"}{" "}
        <span aria-hidden="true">▣</span>
      </button>
      <ActionError error={state.error} />
    </form>
  );
}
