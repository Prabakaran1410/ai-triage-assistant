export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const defaultOrganizationId = process.env.DEFAULT_ORGANIZATION_ID ?? "";

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <div className="rounded-xl border border-[--color-line] bg-[--color-surface] p-8 shadow-sm">
        <h1 className="text-xl font-semibold">Triage review console</h1>
        <p className="mt-2 text-sm text-[--color-muted]">
          Sign in with your organisation&rsquo;s identity provider.
        </p>

        {error ? (
          <p
            role="alert"
            className="mt-5 rounded-md border border-[--color-warn] bg-[--color-warn-bg] px-3 py-2 text-sm text-[--color-warn]"
          >
            {error}
          </p>
        ) : null}

        <form action="/api/auth/start" method="GET" className="mt-6 space-y-4">
          <div>
            <label
              htmlFor="organization_id"
              className="block text-sm font-medium text-[--color-ink]"
            >
              Organisation ID
            </label>
            <input
              id="organization_id"
              name="organization_id"
              required
              defaultValue={defaultOrganizationId}
              placeholder="org_..."
              className="mt-1 w-full rounded-md border border-[--color-line] bg-white px-3 py-2 font-mono text-sm outline-none focus:border-[--color-accent]"
            />
            <p className="mt-1.5 text-xs text-[--color-muted]">
              Each customer has one WorkOS organisation, mapped to their tenant.
            </p>
          </div>

          <button
            type="submit"
            className="w-full rounded-md bg-[--color-accent] px-4 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            Continue to sign in
          </button>
        </form>
      </div>
    </main>
  );
}
