# Contributing

Thanks for the interest. AgentStack is a portfolio project, but it's structured for real contributions.

## Setup

```bash
git clone https://github.com/<you>/agentstack.git
cd agentstack
cp .env.example .env
# Set GROQ_API_KEY and TAVILY_API_KEY before running the agent path.

make install
uv run pre-commit install
make up
make migrate
```

## Workflow

1. Open an issue first for anything non-trivial — a one-liner outlining motivation + approach is enough.
2. Branch from `main`. Keep PRs scoped to a single concern.
3. `make lint && make typecheck && make test` must pass locally before opening the PR.
4. PRs land on `main` after one approving review + green CI.

## Code style

- **Comments**: write the WHY, not the WHAT. If the code reads itself, no comment.
- **Imports**: absolute, never relative.
- **Settings**: add to `agentstack.config.Settings`, never read `os.environ` outside that module.
- **DB sessions / LLM clients / vector clients**: go through `infra/`. Never instantiate clients in routes or services directly.
- **Errors**: raise from `agentstack.api.errors`. Don't return ad-hoc error dicts.
- **Tests**: every test gets a marker (`@pytest.mark.unit` or `@pytest.mark.integration`).

See [CLAUDE.md](CLAUDE.md) for the full conventions used by the AI-assisted workflow on this project.

## Adding an ADR

Decisions worth recording: schema changes, library swaps, retrieval strategy changes, prompt format changes. Use the template:

```markdown
# ADR NNN — Short title

- Status: Proposed | Accepted | Superseded
- Date: YYYY-MM-DD

## Context
## Decision
## Rationale
## Consequences
## Revisit when
```

## Releasing

Not applicable yet — pre-1.0.
