# Frontend

Next.js (App Router) dashboard for Hadrian³. React 19, TypeScript, Tailwind 4,
shadcn-style components on `@base-ui/react`, charts via Recharts.

The UI is currently **German**; the backend, API and documentation are English.

## Running

Normally you want the whole stack:

```bash
docker compose up --build     # from the repository root
```

Standalone against a backend already running on port 8000:

```bash
npm install
npm run dev                   # http://localhost:3000
```

`NEXT_PUBLIC_API_URL` is baked into the bundle at build time. Leaving it empty
makes the browser use the hostname the page was served from, so the same build
works on `localhost` and on a LAN IP without rebuilding. Set it explicitly only
when the API lives on a different host.

## Layout

| Path | Purpose |
| --- | --- |
| `app/systems/` | System list and detail — rules, metrics, R histogram, equity curve |
| `app/trades/` | Trade explorer with server-side filters and pagination |
| `app/dashboard/` | Portfolio-level view across all systems |
| `app/live/` | Live trade journal: ticket lifecycle, execution quality |
| `app/risk/` | Position-size calculator and account balance |
| `app/concepts/` | Concept assignments and the system/concept matrix |
| `lib/api.ts` | Typed fetch client; one function per endpoint |
| `lib/types.ts` | TypeScript types mirroring the API contract |
| `lib/format.ts` | Formatting helpers — deliberately locale-free (see below) |

## Two things worth knowing

**Formatting is deterministic on purpose.** `lib/format.ts` never touches
`Intl`, locales or timezones, and parses ISO-8601 strings by hand rather than
through `Date`. Server and client therefore render identical strings and React
never reports a hydration mismatch. Reach for `formatR`, `formatDateTime` and
friends instead of ad-hoc formatting.

**Metrics are never computed here.** Every figure comes from the API, which
computes it from the persisted trades. Charts derive their series from the trade
list, but no metric is recalculated client-side — one definition, in one place.

## Notes

- Components use `@base-ui/react`, not Radix, so composition uses the `render`
  prop rather than `asChild`.
- `<Select.Root>` needs an `items` prop, otherwise `<Select.Value>` renders the
  raw value instead of the label.
