import Link from "next/link";

import { buttonStyles } from "./ui";

export function AppHeader({ email, role }: { email: string | null; role: string | null }) {
  return (
    <header className="sticky top-0 z-10 border-b border-line bg-surface/85 backdrop-blur-sm">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
        <Link href="/queue" className="flex items-center gap-2.5">
          <span
            aria-hidden
            className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white"
          >
            T
          </span>
          <span className="text-sm font-semibold tracking-tight">Triage review</span>
        </Link>

        {email ? (
          <nav className="flex items-center gap-1">
            {[
              { href: "/queue", label: "Queue" },
              { href: "/knowledge", label: "Knowledge" },
            ].map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="rounded-lg px-3 py-1.5 text-sm font-medium text-ink-soft transition-colors hover:bg-canvas hover:text-ink"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        ) : null}

        {email ? (
          <div className="flex items-center gap-4">
            <div className="text-right leading-tight">
              <p className="text-sm font-medium text-ink">{email}</p>
              <p className="text-xs capitalize text-muted">{role}</p>
            </div>
            <form action="/api/auth/logout" method="POST">
              <button type="submit" className={`${buttonStyles.base} ${buttonStyles.secondary}`}>
                Sign out
              </button>
            </form>
          </div>
        ) : null}
      </div>
    </header>
  );
}
