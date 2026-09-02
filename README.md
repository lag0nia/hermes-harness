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

## Configuración local

La configuración versionada usa rutas relativas y estado local bajo `var/`, de modo que el repositorio no depende de rutas de una máquina concreta. Si una instalación necesita raíces externas, la capa de despliegue puede proporcionar overrides de entorno o de configuración; no se deben guardar ajustes no sensibles en `.env`.

`.env` queda reservado para secretos o credenciales locales y está ignorado por Git. El archivo `.env.example` solo documenta placeholders vacíos, nunca contiene credenciales reales.
