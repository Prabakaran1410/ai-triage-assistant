import { Alert, buttonStyles, Field, inputStyles } from "@/components/ui";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const defaultOrganizationId = process.env.DEFAULT_ORGANIZATION_ID ?? "";

  return (
    <main className="flex min-h-screen items-center justify-center px-6 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <span
            aria-hidden
            className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-brand-600 text-lg font-bold text-white shadow-sm"
          >
            T
          </span>
          <h1 className="text-xl font-semibold tracking-tight">Triage review console</h1>
          <p className="mt-1.5 text-sm text-muted">
            Replies wait here until a person approves them.
          </p>
        </div>

        <div className="rounded-xl border border-line bg-surface p-6 shadow-[0_1px_3px_rgba(16,24,40,0.06)]">
          {error ? (
            <div className="mb-5">
              <Alert>{error}</Alert>
            </div>
          ) : null}

          <form action="/api/auth/start" method="GET" className="space-y-5">
            <Field
              label="Organisation ID"
              htmlFor="organization_id"
              hint="Each customer has one identity-provider organisation, mapped to their tenant."
            >
              <input
                id="organization_id"
                name="organization_id"
                required
                defaultValue={defaultOrganizationId}
                placeholder="org_..."
                autoComplete="off"
                spellCheck={false}
                className={`${inputStyles} font-mono`}
              />
            </Field>

            <button
              type="submit"
              className={`${buttonStyles.base} ${buttonStyles.primary} w-full`}
            >
              Continue to sign in
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-muted">
          You will be sent to your organisation&rsquo;s identity provider.
        </p>
      </div>
    </main>
  );
}
