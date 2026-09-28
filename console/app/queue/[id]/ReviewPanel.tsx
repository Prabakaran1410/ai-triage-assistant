"use client";

import { useActionState } from "react";

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
      <p className="rounded-md border border-[--color-line] bg-[--color-canvas] px-4 py-3 text-sm text-[--color-muted]">
        Your role can view this queue but not act on it.
      </p>
    );
  }

  const isOpen = OPEN_STATUSES.includes(status);
  const isApproved = APPROVED_STATUSES.includes(status);

  if (!isOpen && !isApproved) {
    return (
      <p className="rounded-md border border-[--color-line] bg-[--color-canvas] px-4 py-3 text-sm text-[--color-muted]">
        This reply is {status.replace(/_/g, " ")}. No further action is possible.
      </p>
    );
  }

  return (
    <form action={formAction} className="space-y-4">
      <div>
        <label htmlFor="final_reply" className="block text-sm font-medium">
          Reply to send
        </label>
        <textarea
          id="final_reply"
          name="final_reply"
          rows={7}
          defaultValue={finalReply ?? draftReply ?? ""}
          className="mt-1 w-full rounded-md border border-[--color-line] bg-white px-3 py-2 text-sm outline-none focus:border-[--color-accent]"
        />
        <p className="mt-1.5 text-xs text-[--color-muted]">
          Editing keeps the model&rsquo;s original draft on the record, so the two can
          be compared later.
        </p>
      </div>

      <div>
        <label htmlFor="note" className="block text-sm font-medium">
          Note <span className="font-normal text-[--color-muted]">(optional)</span>
        </label>
        <input
          id="note"
          name="note"
          className="mt-1 w-full rounded-md border border-[--color-line] bg-white px-3 py-2 text-sm outline-none focus:border-[--color-accent]"
          placeholder="Why you changed or rejected it"
        />
      </div>

      {state?.error ? (
        <p
          role="alert"
          className="rounded-md border border-[--color-warn] bg-[--color-warn-bg] px-3 py-2 text-sm text-[--color-warn]"
        >
          {state.error} &mdash; reload to see the current state.
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {isOpen ? (
          <>
            <button
              type="submit"
              name="action"
              value="approve"
              disabled={pending}
              className="rounded-md bg-[--color-ok] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Approve as drafted
            </button>
            <button
              type="submit"
              name="action"
              value="edit"
              disabled={pending}
              className="rounded-md bg-[--color-accent] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
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
            className="rounded-md bg-[--color-ok] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Send to customer
          </button>
        ) : null}
        <button
          type="submit"
          name="action"
          value="reject"
          disabled={pending}
          className="rounded-md border border-[--color-line] px-4 py-2 text-sm font-medium hover:border-[--color-muted] disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </form>
  );
}
