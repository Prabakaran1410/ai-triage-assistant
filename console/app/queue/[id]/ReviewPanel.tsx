"use client";

import { useActionState } from "react";

import { Alert, buttonStyles, Field, inputStyles } from "@/components/ui";

import { reviewAction } from "./actions";

const OPEN_STATUSES = ["needs_review", "draft_ready"];
const APPROVED_STATUSES = ["approved", "edited"];

export function ReviewPanel({
  eventId,
  status,
  draftReply,
  finalReply,
  canReview,
}: {
  eventId: string;
  status: string;
  draftReply: string | null;
  finalReply: string | null;
  canReview: boolean;
}) {
  const action = reviewAction.bind(null, eventId);
  const [state, formAction, pending] = useActionState(action, null);

  if (!canReview) {
    return (
      <div className="rounded-lg border border-line bg-canvas px-4 py-3">
        <p className="text-sm font-medium text-ink">View only</p>
        <p className="mt-0.5 text-sm text-muted">
          Your role can read this queue but not act on it.
        </p>
      </div>
    );
  }

  const isOpen = OPEN_STATUSES.includes(status);
  const isApproved = APPROVED_STATUSES.includes(status);

  if (!isOpen && !isApproved) {
    return (
      <div className="rounded-lg border border-line bg-canvas px-4 py-3">
        <p className="text-sm text-muted">
          This reply is <span className="font-medium text-ink">{status.replace(/_/g, " ")}</span>.
          No further action is possible.
        </p>
      </div>
    );
  }

  return (
    <form action={formAction} className="space-y-4">
      <Field
        label="Reply to send"
        htmlFor="final_reply"
        hint="Editing keeps the model's original draft on the record, so the two can be compared later."
      >
        <textarea
          id="final_reply"
          name="final_reply"
          rows={8}
          defaultValue={finalReply ?? draftReply ?? ""}
          className={`${inputStyles} resize-y leading-relaxed`}
        />
      </Field>

      <Field label="Note (optional)" htmlFor="note">
        <input
          id="note"
          name="note"
          placeholder="Why you changed or rejected it"
          className={inputStyles}
        />
      </Field>

      {state?.error ? <Alert>{state.error} &mdash; reload to see the current state.</Alert> : null}

      <div className="flex flex-wrap gap-2 border-t border-line pt-4">
        {isOpen ? (
          <>
            <button
              type="submit"
              name="action"
              value="approve"
              disabled={pending}
              className={`${buttonStyles.base} ${buttonStyles.affirm}`}
            >
              Approve as drafted
            </button>
            <button
              type="submit"
              name="action"
              value="edit"
              disabled={pending}
              className={`${buttonStyles.base} ${buttonStyles.primary}`}
            >
              Save edit
            </button>
          </>
        ) : null}

        {isApproved ? (
          <button
            type="submit"
            name="action"
            value="send"
            disabled={pending}
            className={`${buttonStyles.base} ${buttonStyles.affirm}`}
          >
            Send to customer
          </button>
        ) : null}

        <button
          type="submit"
          name="action"
          value="reject"
          disabled={pending}
          className={`${buttonStyles.base} ${buttonStyles.secondary} ml-auto`}
        >
          Reject
        </button>
      </div>
    </form>
  );
}
