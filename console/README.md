# Review console

The human half of the human-in-the-loop: a queue of AI-drafted replies that
a person approves, edits or rejects before anything reaches a customer.

Next.js on Vercel. The API it talks to is the FastAPI service at the repo
root, deployed separately on Render.

## Why it is a backend-for-frontend

The console and the API are on different origins. That rules out the
obvious ways to hold a session:

- a cookie set by the API is third-party to the console, and browsers
  increasingly block those outright;
- a token in the URL leaks into server logs, browser history and the
  `Referer` header;
- `localStorage` hands the token to any XSS on the page.

So the browser only ever talks to this Next.js server. It holds the JWT in
a first-party httpOnly cookie and calls the API server-side, attaching the
token as a bearer header. The token never reaches browser JavaScript, and
**no CORS configuration exists anywhere, because no cross-origin browser
request is ever made**.

Login flow:

```
/login  ->  API /auth/login        (the API holds the WorkOS credentials)
        ->  the customer's IdP
        ->  console /auth/callback (exchanges the code against the API,
                                    server to server, and sets the cookie)
        ->  /queue
```

`SSO_REDIRECT_URI` on the API points WorkOS at the console's callback
rather than the API's own.

## Local development

```bash
cp .env.example .env.local   # then set API_BASE_URL
npm install
npm run dev
```

A real SSO round-trip needs the console reachable at a URL registered in
WorkOS, so `localhost` alone will not complete a login. Either point
`SSO_REDIRECT_URI` at a tunnel (ngrok or similar) and register that URL, or
work against the deployed console.

## Environment variables

| Name | Purpose |
|---|---|
| `API_BASE_URL` | The FastAPI service. Server-side only. |
| `DEFAULT_ORGANIZATION_ID` | Pre-fills the login form. Convenience, not a secret. |

Deliberately **not** prefixed `NEXT_PUBLIC_`: that prefix ships a value into
the browser bundle, which would undo the point of the arrangement above.

The console must never hold `DATABASE_URL`, `JWT_SECRET` or
`WORKOS_API_KEY`. It reaches data only through the API, which is what keeps
those credentials off the frontend host.

## Deployment notes (each of these cost time once)

- **Root Directory must be `console`.** Vercel inspects the repo root, finds
  the Python API and auto-detects the project as FastAPI.
- **Do not import the API's environment variables.** Vercel offers to bring
  in everything it finds in the root `.env.example` - 21 variables including
  the database URL and signing key. The console needs two.
- **`<project>.vercel.app` may belong to somebody else.** It can return 200
  and look like yours. The stable alias is `<project>-<team>.vercel.app`;
  the URL shown right after deploying carries a build hash and changes on
  every push, so registering it with WorkOS breaks SSO at the next commit.
- **Deployment Protection breaks SSO** in a way that looks like an
  application bug: WorkOS returns the browser to the callback, Vercel
  intercepts with its own login, and the single-use authorization code is
  spent.
- **Commit author email must match a GitHub account**, or Vercel blocks the
  deployment before building it. Using the GitHub noreply address
  (`<id>+<login>@users.noreply.github.com`) always matches and keeps a
  personal address out of commit metadata.
- **Preview deployments each get a new origin** that WorkOS has not
  registered, so SSO fails there until the URL is added.

## Styling

Tailwind v4. Theme values live in `@theme` in `app/globals.css`, and
**Tailwind generates the utilities from them**: `--color-brand-600` becomes
`bg-brand-600`. The v3-era `bg-[--color-brand-600]` arbitrary-value syntax
silently produces no CSS at all, which is worth knowing because nothing
warns about it - the class simply has no effect.

v4's preflight also no longer sets `cursor: pointer` on buttons; the base
layer restores it.
