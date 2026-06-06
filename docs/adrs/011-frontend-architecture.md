# ADR 011 — Frontend architecture: Next.js App Router + client-side React Query

- **Status:** Accepted
- **Date:** 2026-06-06

## Context

Through Week 4 the frontend was two bare pages (a landing page and the voice agent). The backend was feature-complete, but the platform was invisible to anyone who didn't read the OpenAPI docs or curl the API. Week 5 builds the real product UI: auth, collection + document management, streaming text chat with citations and eval, and API-key management. This ADR records the framework-level decisions so later work stays consistent.

## Decisions

### Next.js App Router, all data fetched client-side

We use the App Router but treat pages as **client components** (`"use client"`) that fetch through React Query, rather than React Server Components fetching on the server.

**Why:** auth is a JWT in `localStorage` (see below). Server components can't read `localStorage`, so server-side data fetching would need the token in a cookie and a parallel server-fetch path. Keeping all data access on the client — one `api.ts` module, one auth mechanism — is dramatically simpler for a single-page-feel app. We give up SSR'd first paint; for an authed dashboard that's an acceptable trade.

### React Query for server state, local state for the live stream

- `@tanstack/react-query` owns everything that lives on the server: collections, conversations, documents, eval results, api keys. Caching, invalidation, and `refetchInterval` (used to poll document ingestion status and eval scores) come for free.
- The in-flight streaming answer is **not** React Query — it's local component state driven by `useStreamingQuery`. Streaming tokens mutate too fast and don't belong in a cache; once the turn finalizes, we invalidate the relevant queries.

### SSE over POST via a hand-rolled fetch reader

`POST /api/v1/query/stream` returns Server-Sent Events. The browser `EventSource` API only does GET, so we can't use it. `lib/streamQuery.ts` does `fetch()` with a JSON body, reads `res.body` through a `TextDecoder`, splits on the `\n\n` SSE frame delimiter, and yields typed events. `useStreamingQuery` wraps that generator into `{ streaming, partialAnswer, citations, final, error }` React state, with an `AbortController` so navigating away cancels the stream.

### Tailwind, configured with RGB-channel CSS variables

Tailwind was already a devDependency but never configured. We set it up properly. The dark theme lives as CSS variables, but stored as **RGB channel triples** (`--accent: 96 165 250`) and mapped through `rgb(var(--accent) / <alpha-value>)` in the config — this is what makes opacity modifiers like `bg-accent/10` work. (Storing hex in the variables silently breaks every opacity modifier; we hit that and fixed it.)

### Markdown answers with clickable citations

Answers are markdown with `[n]` citation markers. `AnswerMarkdown` renders via `react-markdown` + `remark-gfm`, strips the qwen3 `<think>…</think>` block, and a custom text renderer replaces `[n]` markers with `CitationChip` buttons that reveal the cited chunk's preview on hover/click. Citations come from the `final` stream event, so the chips are live as soon as the answer completes.

### Auth: JWT in localStorage + client-side route guard

`AuthProvider` hydrates the token from `localStorage` on mount, calls `/auth/me`, and exposes `{user, login, register, logout}`. `RequireAuth` redirects to `/login` when there's no user. API keys (for machine clients) are managed in the UI but the UI itself always authenticates with the user JWT.

## Consequences

- One auth path, one data path, no server/client split to reason about.
- **localStorage JWT is XSS-exposed.** A script injected into the page can read the token. The mitigation (httpOnly cookies + CSRF protection + a refresh-token rotation) is real work and changes the backend auth contract. For a portfolio app with a trusted first-party frontend it's an acceptable, documented trade — see "Revisit when".
- No SSR means a brief "Loading…" on first paint while auth hydrates. Fine for an authed tool; would matter for public marketing pages (we have none).
- The streaming reader is ~40 lines we own, versus pulling an SSE library. It's tied to our exact frame format, which we control.

## Revisit when

- The app is exposed to untrusted users or embeds third-party scripts → move to httpOnly-cookie auth with refresh tokens and CSRF protection (would also unlock RSC data fetching).
- We add public/SEO pages → those become server components.
- Token expiry (24h) starts logging users out mid-session in a way they notice → add silent refresh.

## Out of scope (Week 6+)

- Mobile-responsive layout beyond "doesn't break".
- Embedding the Phoenix trace viewer (we link out).
- Optimistic cache updates beyond invalidation.
- Bumping Next off 15.1.3 (carries a CVE) — a deliberate follow-up, kept separate from this feature.
