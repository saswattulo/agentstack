# frontend/

Next.js 15 (App Router) UI for AgentStack. Implemented in Week 4.

## Planned features

- Collections list + create
- Drag-and-drop document upload with progress polling
- Streaming chat (SSE → `POST /api/v1/query/stream`)
- Inline citation popovers showing the source chunk
- Trace viewer: pull from `/api/v1/query/{id}` → link out to Phoenix
- Eval dashboard: per-query scores from `/api/v1/eval/aggregate`

## Quickstart (once implemented)

```bash
cd frontend
pnpm install
pnpm dev
# UI at http://localhost:3000, talking to API at http://localhost:8000
```

## Stack target

- Next.js 15 (App Router, React 19)
- TypeScript strict
- Tailwind CSS + shadcn/ui
- `@tanstack/react-query` for server state
- `eventsource-parser` for SSE
