"use client";

import { useActionState, useState } from "react";

import { Alert, buttonStyles, Field, inputStyles } from "@/components/ui";

import { removeSource, saveSource } from "./actions";

export type Source = {
  source_id: string;
  title: string;
  chunk_count: number;
  characters: number;
  updated_at: string;
};

function AddDocumentForm() {
  const [state, formAction, pending] = useActionState(saveSource, null);

  return (
    <form action={formAction} className="space-y-4">
      <Field label="Title" htmlFor="title" hint="Shown to reviewers as the source of a citation.">
        <input
          id="title"
          name="title"
          required
          placeholder="Returns policy"
          className={inputStyles}
        />
      </Field>

      <Field
        label="Text"
        htmlFor="content"
        hint="Paste the policy, FAQ or guide. Long documents are split automatically."
      >
        <textarea
          id="content"
          name="content"
          required
          rows={10}
          placeholder="Unused items can be returned within 60 days of purchase..."
          className={`${inputStyles} resize-y leading-relaxed`}
        />
      </Field>

      {state?.error ? <Alert>{state.error}</Alert> : null}
      {state?.message ? (
        <p className="rounded-lg border border-go-line bg-go-tint px-3.5 py-2.5 text-sm text-go">
          {state.message}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={pending}
        className={`${buttonStyles.base} ${buttonStyles.primary}`}
      >
        {pending ? "Indexing..." : "Add to knowledge base"}
      </button>
    </form>
  );
}

function DeleteButton({ sourceId, title }: { sourceId: string; title: string }) {
  const action = removeSource.bind(null, sourceId);
  const [state, formAction, pending] = useActionState(action, null);
  const [confirming, setConfirming] = useState(false);

  if (!confirming) {
    return (
      <button
        type="button"
        onClick={() => setConfirming(true)}
        className="text-sm text-muted underline-offset-4 hover:text-stop hover:underline"
      >
        Remove
      </button>
    );
  }

  return (
    <form action={formAction} className="flex items-center gap-2">
      {/* Deleting stops every future reply being grounded in this, so it
          asks first rather than acting on a stray click. */}
      <span className="text-xs text-muted">Remove &ldquo;{title}&rdquo;?</span>
      <button
        type="submit"
        disabled={pending}
        className="text-sm font-medium text-stop underline-offset-4 hover:underline disabled:opacity-50"
      >
        {pending ? "Removing..." : "Yes"}
      </button>
      <button
        type="button"
        onClick={() => setConfirming(false)}
        className="text-sm text-muted underline-offset-4 hover:underline"
      >
        Cancel
      </button>
      {state?.error ? <span className="text-xs text-stop">{state.error}</span> : null}
    </form>
  );
}

export function KnowledgeManager({
  sources,
  canManage,
}: {
  sources: Source[];
  canManage: boolean;
}) {
  const totalChunks = sources.reduce((sum, s) => sum + s.chunk_count, 0);

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
      <section className="rounded-xl border border-line bg-surface shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
        <div className="flex items-baseline justify-between border-b border-line px-5 py-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted">
            Documents
          </h2>
          <p className="text-xs text-muted">
            {sources.length} {sources.length === 1 ? "document" : "documents"} &middot;{" "}
            {totalChunks} retrievable {totalChunks === 1 ? "piece" : "pieces"}
          </p>
        </div>

        {sources.length === 0 ? (
          <p className="px-5 py-12 text-center text-sm text-muted">
            Nothing indexed yet. Until something is here, every reply will be held for
            review with no sources to cite.
          </p>
        ) : (
          <ul className="divide-y divide-line">
            {sources.map((source) => (
              <li key={source.source_id} className="flex items-start justify-between gap-4 px-5 py-4">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-ink">{source.title}</p>
                  <p className="mt-0.5 font-mono text-xs text-muted">{source.source_id}</p>
                  <p className="mt-1 text-xs text-muted">
                    {source.chunk_count} {source.chunk_count === 1 ? "piece" : "pieces"} &middot;{" "}
                    {source.characters.toLocaleString()} characters &middot; updated{" "}
                    {new Date(source.updated_at).toLocaleDateString()}
                  </p>
                </div>
                {canManage ? (
                  <DeleteButton sourceId={source.source_id} title={source.title} />
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl border border-line bg-surface shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
        <h2 className="border-b border-line px-5 py-3 text-xs font-semibold uppercase tracking-wider text-muted">
          Add a document
        </h2>
        <div className="p-5">
          {canManage ? (
            <AddDocumentForm />
          ) : (
            <div className="rounded-lg border border-line bg-canvas px-4 py-3">
              <p className="text-sm font-medium text-ink">View only</p>
              <p className="mt-0.5 text-sm text-muted">
                Changing the knowledge base changes what every future reply is grounded
                in, so it is an admin action.
              </p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
