import { AppHeader } from "@/components/AppHeader";
import { apiFetch } from "@/lib/api";
import { getSessionToken, readClaims } from "@/lib/session";

import { KnowledgeManager, type Source } from "./KnowledgeManager";

export default async function KnowledgePage() {
  const { sources } = await apiFetch<{ sources: Source[] }>("/knowledge");

  const token = await getSessionToken();
  const user = token ? readClaims(token) : null;
  const canManage = user?.role === "admin";

  return (
    <>
      <AppHeader email={user?.email ?? null} role={user?.role ?? null} />

      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight">Knowledge base</h1>
          <p className="mt-1 text-sm text-muted">
            Replies may only state what these documents say. Anything not covered here
            is held for a person rather than guessed at.
          </p>
        </div>

        <KnowledgeManager sources={sources} canManage={canManage} />
      </main>
    </>
  );
}
