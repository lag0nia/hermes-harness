# Hermes Harness

Plano de control local, tipado y auditable para el secretario multiagente Hermes.

## Desarrollo

Requiere Python 3.13 y `uv`.

```bash
uv sync
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest -q
uv run pytest
```
