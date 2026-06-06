# AgentStack — Frontend

Next.js (App Router) UI for AgentStack: auth, streaming text chat with citations + eval, document/collection management, API-key management, and the voice agent.

## Run

```bash
cd frontend
npm install
cp .env.example .env.local   # set NEXT_PUBLIC_API_URL if the API isn't on :8000
npm run dev                  # http://localhost:3000
```

The API must be running (`make up` in the repo root). `NEXT_PUBLIC_API_URL` defaults to `http://localhost:8000`.

## Routes

| Route | What |
|---|---|
| `/login` | Register / sign in (JWT) |
| `/chat` | Empty state — pick a collection, start a chat |
| `/chat/[conversationId]` | Streaming chat: markdown answers, clickable `[n]` citations, per-answer eval bars, intent/cache/latency chips |
| `/settings/collections` | Create collections, drag-drop upload docs, watch ingestion status, delete docs/collections |
| `/settings/api-keys` | Mint machine keys (shown once), revoke |
| `/voice` | Streaming voice agent (mic → ASR → agent → TTS) with barge-in |

## Stack

- **Next.js 15** App Router, all pages client components.
- **Tailwind** (dark theme via RGB-channel CSS variables → opacity modifiers work).
- **@tanstack/react-query** for server state (collections, conversations, documents, eval, keys); polling for ingestion status + async eval.
- **react-markdown + remark-gfm** for answers; custom renderer turns `[n]` into citation chips.
- Streaming chat uses a hand-rolled SSE-over-POST reader (`lib/streamQuery.ts`) since `EventSource` can't POST.

See [ADR-011](../docs/adrs/011-frontend-architecture.md) for the architecture rationale.

## Scripts

```bash
npm run dev        # dev server
npm run build      # production build (also typechecks)
npm run typecheck  # tsc --noEmit
npm run lint       # next lint
```

## Layout

```
src/
  app/
    layout.tsx                  Providers (React Query + Auth)
    page.tsx                    redirect → /chat or /login
    login/                      auth
    chat/                       shell + thread
    settings/{collections,api-keys}/
    voice/                      voice agent
  components/                   Sidebar, ChatThread, MessageBubble, CitationChip,
                                EvalBadge, DocumentUpload/List, AuthProvider, …
  hooks/useStreamingQuery.ts    streaming chat state
  lib/
    api.ts                      typed API client + token storage
    streamQuery.ts              SSE-over-POST reader
    queryClient.ts              React Query client
    voice/                      voice WS client + recorder worklet
```

## Notes

- Auth is a JWT in `localStorage` with a client-side route guard — simple, but XSS-exposed. Trade-offs in ADR-011.
- Next is pinned at 15.1.3 which carries a CVE; bumping within 15.x is a recommended follow-up.
