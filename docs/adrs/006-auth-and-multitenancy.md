# ADR 006 — Auth model: email/password JWT + per-user collections

- **Status:** Accepted
- **Date:** 2026-05-30
- **Supersedes:** the original "API key only" decision in CLAUDE.md.

## Context

AgentStack is intended to be used by multiple end users, each uploading their own documents and chatting with them. The initial scaffold authenticated callers with shared API keys and had no `users` table, no per-user ownership, and no conversation grouping. That is a single-tenant tool, not a multi-user platform.

We need:

- Identity per end user (email + name).
- Strict data isolation: a user can only see and query their own collections / documents / conversations.
- Persistent chat history grouped into conversations (sidebar UX, conversation memory in Week 3).
- Machine-to-machine auth (CLI, CI, scripts) without forcing the operator to extract a JWT.

## Decision

1. **Users**: new `users` table (id, email unique, name, password_hash, is_active, is_admin). Passwords hashed with **argon2id** via `argon2-cffi`.
2. **Sessions**: stateless **JWT (HS256)** bearer tokens. Default TTL 24h. No refresh tokens in v1 — re-login if expired.
3. **Machine clients**: API keys remain, but **each API key belongs to a user** (`api_keys.user_id` FK). The key inherits the user's data scope.
4. **Auth middleware** accepts either `Authorization: Bearer <jwt>` or `X-API-Key: <key>` and resolves both to a single `request.state.user_id`. Routes use one dependency, `CurrentUserDep`, regardless of which method authenticated.
5. **Isolation**: every resource is per-user:
   - `collections.owner_id` (NOT NULL FK to users)
   - `collections` unique constraint changed from global `name` to `(owner_id, name)` — two users can both have a collection called "papers".
   - `documents` ownership flows through `collection_id` — no separate `uploaded_by` column.
   - `query_logs.user_id` and `query_logs.conversation_id` added.
6. **Conversations**: new `conversations` table (id, user_id, collection_id optional, title, summary). Every `/query` either attaches to an existing conversation owned by the caller or stands alone (`conversation_id=NULL`).
7. **Dev bootstrap**: on startup in `APP_ENV=dev`, a `dev@agentstack.local` user is created (idempotent) and the `DEV_API_KEY` is bound to it. This means `make up` still yields a working API without a manual register step.

## Rationale

- **Email/password over OAuth**: the user has no Google/GitHub OAuth app registered. Email/password is one configuration knob (`JWT_SECRET_KEY`) and zero external dependencies — fits the "one command up" goal.
- **argon2id over bcrypt**: industry default in 2026, GPU-resistant, the `argon2-cffi` library has a tiny API. PyJWT for tokens because it's the canonical implementation and lighter than `python-jose`.
- **JWT over server sessions**: the API is otherwise stateless. Adding a session table would need cleanup jobs.
- **API key kept**: scripts, the load test, and CI all need a fixed credential. Forcing JWT means logging in before every script run — annoying for tooling. Tying API keys to a user keeps the data-isolation guarantees intact.
- **owner_id required (not nullable)**: a collection without an owner is unreachable through the auth-gated API. Making it required is enforceable at the DB level.
- **Documents inherit ownership from the collection**: simpler than a separate `uploaded_by`. We don't need attribution within a private collection. If we add workspaces later, we'd add `uploaded_by` then.

## Consequences

- The existing API contract changed: every non-public endpoint requires auth. Old "no auth in dev" shortcut is gone — `DEV_API_KEY` works but only because the bootstrap binds it to a user.
- The Alembic migration **0001** has been amended (the original scaffold was uncommitted; nothing had been applied yet, so editing 0001 is safe). Going forward, new migrations are additive — no more 0001 edits.
- Tests that exercise multi-user behavior require a live DB. Pure unit tests for JWT and password hashing don't.

## Non-goals (still)

- Email verification.
- OAuth providers.
- Refresh tokens.
- Per-user encryption-at-rest.
- Workspaces / team membership / sharing.

## Revisit when

- A user asks for a "share this collection with X" UX — add workspaces (ADR-TBD).
- We move to a managed/multi-region deployment — JWT secrets should rotate via JWKS, and we'd revisit HS256 → RS256.
