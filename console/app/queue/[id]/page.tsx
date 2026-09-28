import Link from "next/link";

import { apiFetch, type EventDetail } from "@/lib/api";
import { getSessionToken, readClaims } from "@/lib/session";

import { ReviewPanel } from "./ReviewPanel";

const REVIEWER_ROLES = new Set(["admin", "reviewer"]);

export default async function EventPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const event = await apiFetch<EventDetail>(`/events/${id}`);

  const token = await getSessionToken();
  const user = token ? readClaims(token) : null;
  const canReview = user ? REVIEWER_ROLES.has(user.role) : false;

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <Link href="/queue" className="text-sm text-[--color-muted] underline hover:no-underline">
        &larr; Back to queue
      </Link>

      <div className="mt-4 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-6">
          <section className="rounded-lg border border-[--color-line] bg-[--color-surface] p-5">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-[--color-muted]">
              Customer message
            </h2>
            <p className="mt-2 text-sm">{event.message}</p>
          </section>

          <section className="rounded-lg border border-[--color-line] bg-[--color-surface] p-5">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-[--color-muted]">
              Draft reply
            </h2>
            <ReviewPanel
              eventId={event.id}
              status={event.status}
              draftReply={event.draft_reply}
              finalReply={event.final_reply}
              canReview={canReview}
            />
          </section>

          <section className="rounded-lg border border-[--color-line] bg-[--color-surface] p-5">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-[--color-muted]">
              History
            </h2>
            <ol className="mt-3 space-y-3">
              {event.audit.map((entry, index) => (
                <li key={index} className="border-l-2 border-[--color-line] pl-3 text-sm">
                  <p>
                    <span className="font-medium">{entry.action}</span>
                    {entry.from_status ? (
                      <span className="text-[--color-muted]">
                        {" "}
                        &middot; {entry.from_status} &rarr; {entry.to_status}
                      </span>
                    ) : null}
                  </p>
                  <p className="text-xs text-[--color-muted]">
                    {entry.actor_email ?? "system"} &middot;{" "}
                    {new Date(entry.created_at).toLocaleString()}
                  </p>
                  {typeof entry.detail?.note === "string" ? (
                    <p className="mt-1 text-xs italic">{entry.detail.note}</p>
                  ) : null}
                </li>
              ))}
            </ol>
          </section>
        </div>

        <aside className="space-y-6">
          <section className="rounded-lg border border-[--color-line] bg-[--color-surface] p-5">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-[--color-muted]">
              Decision
            </h2>
            <dl className="mt-3 space-y-2 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-[--color-muted]">Status</dt>
                <dd>{event.status.replace(/_/g, " ")}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-[--color-muted]">Intent</dt>
                <dd>{event.intent ?? "unclassified"}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-[--color-muted]">Confidence</dt>
                <dd>{event.confidence === null ? "n/a" : event.confidence.toFixed(2)}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-[--color-muted]">Model</dt>
                <dd className="font-mono text-xs">{event.model ?? "none"}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-[--color-muted]">Latency</dt>
                <dd>{event.latency_ms === null ? "n/a" : `${event.latency_ms} ms`}</dd>
              </div>
            </dl>
            {event.escalation_reason ? (
              <p className="mt-3 rounded-md border border-[--color-warn] bg-[--color-warn-bg] px-3 py-2 text-xs text-[--color-warn]">
                Escalated: {event.escalation_reason}
              </p>
            ) : null}
          </section>

          <section className="rounded-lg border border-[--color-line] bg-[--color-surface] p-5">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-[--color-muted]">
              Sources cited
            </h2>
            {event.citations.length === 0 ? (
              <p className="mt-2 text-sm text-[--color-muted]">
                None. A reply with no source is escalated rather than sent.
              </p>
            ) : (
              <ul className="mt-3 space-y-3">
                {event.citations.map((citation) => (
                  <li key={citation.source_id} className="text-sm">
                    <p className="font-medium">{citation.title}</p>
                    <p className="text-xs text-[--color-muted]">
                      {citation.source_id} &middot; updated{" "}
                      {new Date(citation.updated_at).toLocaleDateString()}
                    </p>
                    <p className="mt-1 text-xs">{citation.excerpt}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>
      </div>
    </main>
  );
}
