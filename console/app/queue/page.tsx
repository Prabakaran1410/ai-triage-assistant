import Link from "next/link";

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

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "needs_review"
      ? "bg-[--color-warn-bg] text-[--color-warn]"
      : status === "sent" || status === "approved"
        ? "bg-[--color-ok-bg] text-[--color-ok]"
        : "bg-[--color-canvas] text-[--color-muted]";
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${tone}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

export default async function QueuePage({
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
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-xl font-semibold">Review queue</h1>
          <p className="mt-1 text-sm text-[--color-muted]">
            Replies wait here until a person approves them.
          </p>
        </div>
        {user ? (
          <form action="/api/auth/logout" method="POST" className="text-sm">
            <span className="text-[--color-muted]">
              {user.email} &middot; {user.role}
            </span>
            <button type="submit" className="ml-3 underline hover:no-underline">
              Sign out
            </button>
          </form>
        ) : null}
      </header>

      <nav className="mt-6 flex flex-wrap gap-2">
        {FILTERS.map((filter) => {
          const active = status === filter.status;
          return (
            <Link
              key={filter.label}
              href={filter.status ? `/queue?status=${filter.status}` : "/queue?status="}
              className={`rounded-md border px-3 py-1.5 text-sm ${
                active
                  ? "border-[--color-accent] bg-[--color-accent] text-white"
                  : "border-[--color-line] bg-[--color-surface] hover:border-[--color-muted]"
              }`}
            >
              {filter.label}
            </Link>
          );
        })}
      </nav>

      {page.items.length === 0 ? (
        <p className="mt-10 rounded-lg border border-dashed border-[--color-line] bg-[--color-surface] px-6 py-12 text-center text-sm text-[--color-muted]">
          Nothing here.
        </p>
      ) : (
        <ul className="mt-6 divide-y divide-[--color-line] overflow-hidden rounded-lg border border-[--color-line] bg-[--color-surface]">
          {page.items.map((item) => (
            <li key={item.id}>
              <Link href={`/queue/${item.id}`} className="block px-5 py-4 hover:bg-[--color-canvas]">
                <div className="flex items-start justify-between gap-4">
                  <p className="text-sm font-medium">{item.message}</p>
                  <StatusBadge status={item.status} />
                </div>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[--color-muted]">
                  <span>{item.intent ?? "unclassified"}</span>
                  <span>
                    confidence{" "}
                    {item.confidence === null ? "n/a" : item.confidence.toFixed(2)}
                  </span>
                  <span>{item.channel}</span>
                  <span>{new Date(item.created_at).toLocaleString()}</span>
                </div>
                {item.escalation_reason ? (
                  <p className="mt-1.5 text-xs text-[--color-warn]">
                    Escalated: {item.escalation_reason}
                  </p>
                ) : null}
              </Link>
            </li>
          ))}
        </ul>
      )}

      {page.next_cursor ? (
        <Link
          href={`/queue?status=${status}&cursor=${encodeURIComponent(page.next_cursor)}`}
          className="mt-6 inline-block rounded-md border border-[--color-line] bg-[--color-surface] px-4 py-2 text-sm hover:border-[--color-muted]"
        >
          Older
        </Link>
      ) : null}
    </main>
  );
}
