# BrewOps

Telemetry app for the office coffee machines. Python with FastAPI, data in SQLite.

Run it with `uv run start` and open http://localhost:8123. The code is in `src/brewops/`.

## Docs

Read the relevant doc before working in that area — don't guess.

- [docs/architecture.md](docs/architecture.md) — layers, request flow, how the pieces connect
- [docs/ingestion.md](docs/ingestion.md) — CSV inbox vs. manual UI entry, file/validation rules
- [docs/testing.md](docs/testing.md) — running the app, running/writing tests
- [docs/conventions.md](docs/conventions.md) — timestamps, drink_type key, where SQL lives, the health-aggregate pattern
- [docs/reference/schema.md](docs/reference/schema.md) — tables, columns, seeded reference data
- [docs/reference/api.md](docs/reference/api.md) — every endpoint, request/response shapes

## Git commits

Do not add Co-Authored-By or "Generated with Claude Code" attribution lines to commits or PRs.
