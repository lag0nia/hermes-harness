# Task 15 — replay y shadow (preparación software)

Este runbook describe únicamente el harness offline. No exporta, muta ni borra
sesiones reales y no cambia configuración viva.

## Secuencia segura

1. Ejecutar `uv run pytest tests/replay -q`.
2. Ejecutar el replay con `uv run python scripts/replay_routing.py fixtures/replay/fixtures/spanish_cases.jsonl --log /tmp/task-15-shadow.jsonl`.
3. Verificar `policy_violations == 0`, que `authoritative_path` sea siempre `legacy`
y revisar divergencias antes de promover.
4. Ante una divergencia o violación, accionar el único `KillSwitch`: primero
`rollback_to("read_only")`; si procede, `trip("<motivo>")`. No habilitar promoción
desde el replay.

## Pendiente operacional

La ventana de observación de **24 horas sigue pendiente operacional**. Este
artefacto no la inicia, no la simula y no la da por cumplida. Requiere una
aprobación/checkpoint operativo posterior, con health check y rollback listo.
