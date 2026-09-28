import Link from "next/link";

import { AppHeader } from "@/components/AppHeader";
import { buttonStyles, StatusBadge } from "@/components/ui";
import { apiFetch, type QueuePage } from "@/lib/api";
import { getSessionToken, readClaims } from "@/lib/session";

const FILTERS = [
  { label: "Needs review", status: "needs_review" },
  { label: "Draft ready", status: "draft_ready" },
  { label: "Approved", status: "approved" },
  { label: "Edited", status: "edited" },
  { label: "Sent", status: "sent" },
  { label: "All", status: "" },
];

/** A coloured edge on the card, so the queue is scannable without reading. */
const ACCENT: Record<string, string> = {
  needs_review: "before:bg-hold",
  draft_ready: "before:bg-brand-500",
  approved: "before:bg-go",
  edited: "before:bg-go",
  sent: "before:bg-go",
  rejected: "before:bg-stop",
};

function formatTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default async function QueueListPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; cursor?: string }>;
}) {
  const { status = "needs_review", cursor } = await searchParams;

  const query = new URLSearchParams();
  if (status) query.set("status", status);
  if (cursor) query.set("cursor", cursor);
  const page = await apiFetch<QueuePage>(`/events?${query.toString()}`);

  const token = await getSessionToken();
  const user = token ? readClaims(token) : null;

  return (
    <>
      <AppHeader email={user?.email ?? null} role={user?.role ?? null} />

      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Review queue</h1>
            <p className="mt-1 text-sm text-muted">
              Nothing reaches a customer until someone here approves it.
            </p>
          </div>
          <p className="text-sm text-muted">
            {page.items.length} {page.items.length === 1 ? "item" : "items"}
          </p>
        </div>

        <nav
          aria-label="Filter by status"
          className="mt-6 flex flex-wrap gap-1.5 rounded-xl border border-line bg-surface p-1.5"
        >
          {FILTERS.map((filter) => {
            const active = status === filter.status;
            return (
              <Link
                key={filter.label}
                href={filter.status ? `/queue?status=${filter.status}` : "/queue?status="}
                aria-current={active ? "page" : undefined}
                className={`rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors ${
                  active
                    ? "bg-brand-600 text-white"
                    : "text-ink-soft hover:bg-canvas hover:text-ink"
                }`}
              >
                {filter.label}
              </Link>
            );
          })}
        </nav>

        {page.items.length === 0 ? (
          <div className="mt-6 rounded-xl border border-dashed border-line-strong bg-surface px-6 py-16 text-center">
            <p className="text-sm font-medium text-ink">Nothing in this view</p>
            <p className="mt-1 text-sm text-muted">
              Replies appear here as messages are triaged.
            </p>
          </div>
        ) : (
          <ul className="mt-6 space-y-2.5">
            {page.items.map((item) => (
              <li key={item.id}>
                <Link
                  href={`/queue/${item.id}`}
                  className={`group relative block overflow-hidden rounded-xl border border-line bg-surface py-4 pl-6 pr-5 transition-all before:absolute before:inset-y-0 before:left-0 before:w-1 hover:border-line-strong hover:shadow-[0_2px_8px_rgba(16,24,40,0.06)] ${
                    ACCENT[item.status] ?? "before:bg-line-strong"
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <p className="text-sm font-medium leading-relaxed text-ink group-hover:text-brand-700">
                      {item.message}
                    </p>
                    <StatusBadge status={item.status} />
                  </div>

                  <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                    <span className="rounded bg-canvas px-1.5 py-0.5 font-medium text-ink-soft">
                      {item.intent ?? "unclassified"}
                    </span>
                    <span>
                      confidence {item.confidence === null ? "n/a" : item.confidence.toFixed(2)}
                    </span>
                    <span>&middot;</span>
                    <span>{item.channel}</span>
                    <span>&middot;</span>
                    <span>{formatTime(item.created_at)}</span>
                  </div>

                  {item.escalation_reason ? (
                    <p className="mt-2 text-xs text-hold">Held: {item.escalation_reason}</p>
                  ) : null}
                </Link>
              </li>
            ))}
          </ul>
        )}

        {page.next_cursor ? (
          <Link
            href={`/queue?status=${status}&cursor=${encodeURIComponent(page.next_cursor)}`}
            className={`${buttonStyles.base} ${buttonStyles.secondary} mt-6`}
          >
            Show older
          </Link>
        ) : null}
      </main>
    </>
  );
}
