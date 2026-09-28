import Link from "next/link";

import { AppHeader } from "@/components/AppHeader";
import { Card, StatusBadge } from "@/components/ui";
import { apiFetch, type EventDetail } from "@/lib/api";
import { getSessionToken, readClaims } from "@/lib/session";

import { ReviewPanel } from "./ReviewPanel";

const REVIEWER_ROLES = new Set(["admin", "reviewer"]);

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="text-sm font-medium text-ink">{value}</dd>
    </div>
  );
}

export default async function EventPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const event = await apiFetch<EventDetail>(`/events/${id}`);

  const token = await getSessionToken();
  const user = token ? readClaims(token) : null;
  const canReview = user ? REVIEWER_ROLES.has(user.role) : false;

  return (
    <>
      <AppHeader email={user?.email ?? null} role={user?.role ?? null} />

      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link
            href="/queue"
            className="text-sm text-muted underline-offset-4 transition-colors hover:text-ink hover:underline"
          >
            &larr; Back to queue
          </Link>
          <StatusBadge status={event.status} />
        </div>

        <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <div className="space-y-5">
            <Card title="Customer message">
              <p className="text-sm leading-relaxed text-ink">{event.message}</p>
            </Card>

            <Card title="Draft reply">
              <ReviewPanel
                eventId={event.id}
                status={event.status}
                draftReply={event.draft_reply}
                finalReply={event.final_reply}
                canReview={canReview}
                customerEmail={event.customer_email}
              />
            </Card>

            <Card title="History">
              <ol className="space-y-4">
                {event.audit.map((entry, index) => (
                  <li key={index} className="relative pl-5">
                    <span
                      aria-hidden
                      className="absolute left-0 top-1.5 h-2 w-2 rounded-full bg-brand-500"
                    />
                    {index < event.audit.length - 1 ? (
                      <span
                        aria-hidden
                        className="absolute left-[3px] top-4 h-full w-px bg-line"
                      />
                    ) : null}
                    <p className="text-sm font-medium capitalize text-ink">
                      {entry.action}
                      {entry.from_status ? (
                        <span className="font-normal text-muted">
                          {" "}
                          &middot; {entry.from_status.replace(/_/g, " ")} &rarr;{" "}
                          {entry.to_status?.replace(/_/g, " ")}
                        </span>
                      ) : null}
                    </p>
                    <p className="mt-0.5 text-xs text-muted">
                      {entry.actor_email ?? "system"} &middot;{" "}
                      {new Date(entry.created_at).toLocaleString()}
                    </p>
                    {typeof entry.detail?.note === "string" ? (
                      <p className="mt-1.5 rounded-md bg-canvas px-2.5 py-1.5 text-xs italic text-ink-soft">
                        {entry.detail.note}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ol>
            </Card>
          </div>

          <aside className="space-y-5">
            <Card title="Decision">
              <dl className="divide-y divide-line">
                <Detail label="Intent" value={event.intent ?? "unclassified"} />
                <Detail
                  label="Confidence"
                  value={event.confidence === null ? "n/a" : event.confidence.toFixed(2)}
                />
                <Detail label="Channel" value={event.channel} />
                <Detail
                  label="Reply to"
                  value={event.customer_email ?? "no address"}
                />
                <Detail label="Model" value={event.model ?? "none"} />
                <Detail
                  label="Latency"
                  value={event.latency_ms === null ? "n/a" : `${event.latency_ms} ms`}
                />
              </dl>
              {event.escalation_reason ? (
                <div className="mt-4 rounded-lg border border-hold-line bg-hold-tint px-3.5 py-2.5">
                  <p className="text-xs font-semibold uppercase tracking-wide text-hold">
                    Held for review
                  </p>
                  <p className="mt-1 text-sm text-hold">{event.escalation_reason}</p>
                </div>
              ) : null}
            </Card>

            <Card title={`Sources cited (${event.citations.length})`}>
              {event.citations.length === 0 ? (
                <p className="text-sm text-muted">
                  None. A reply with no source is held back rather than sent.
                </p>
              ) : (
                <ul className="space-y-4">
                  {event.citations.map((citation) => (
                    <li key={citation.source_id}>
                      <p className="text-sm font-medium text-ink">{citation.title}</p>
                      <p className="mt-0.5 font-mono text-xs text-muted">
                        {citation.source_id} &middot; updated{" "}
                        {new Date(citation.updated_at).toLocaleDateString()}
                      </p>
                      <p className="mt-1.5 border-l-2 border-line pl-3 text-xs leading-relaxed text-ink-soft">
                        {citation.excerpt}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </aside>
        </div>
      </main>
    </>
  );
}
