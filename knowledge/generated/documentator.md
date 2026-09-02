# Knowledge pack: documentator

<!-- source: architecture/agents.md -->
# Agentes y ownership

`default` coordina; Browser Operator opera navegador; Researcher investiga; Architect-Planner diseña; Engineer implementa Hermes; Coder implementa proyectos externos; Documentator mantiene docs/packs; Travel Planner busca viajes read-only.

Documentator es el único writer de documentación y knowledge packs. Solo `default` puede proponer hechos para Holographic Memory después de comprobar contradicciones. Las skills no conceden permisos.


<!-- source: architecture/browser-operator.md -->
# Browser Operator

The Browser Operator is an injectable Observe–Decide–Act–Verify–Recover machine. Its
adapter exposes only sanitized semantic observations, actions, verification, screenshot
capture, and screenshot deletion; it has no browser, network, credential, or commerce
implementation.

* DOM/SOM references from an observation are invalidated after every mutation.
* Confidence below the configured threshold produces `NEED_INPUT` without acting.
* An unverifiable delivery receives at most one equivalent retry; repeated state
  fingerprints produce `NEED_INPUT` rather than a no-op loop.
* Critical actions and semantic/visual conflicts require the injected independent Sol
  review callback. Sol is requested at medium effort by the change pipeline.
* Screenshots are temporary evidence and are deleted in success, failure, cancellation,
  and crash recovery paths. Persistent evidence is structured, fingerprinted, and
  redacted logs only.

Fixtures use a fake adapter and never contact a real browser or storefront.


<!-- source: architecture/security-boundaries.md -->
# Límites de seguridad

Los contratos y el Control Plane son la segunda barrera tras los manifests. Coder no puede tocar rutas Hermes, perfiles ni configuración. Browser no ve credenciales y el usuario realiza login manualmente. Compras, reservas, pagos y promociones R2 requieren digest exacto y confirmación expirable.

Se guardan logs estructurados redactados; screenshots son efímeras y se eliminan en todo camino terminal.


<!-- source: architecture/state-machines.md -->
# Máquinas de estado

Un job sigue `RECEIVED → VALIDATED → CLASSIFIED → DISPATCHED → RUNNING → VERIFYING → SUCCEEDED`; también puede terminar en `NEED_INPUT`, `CANCELLED`, `FAILED` o `PAUSED`.

Cada side effect usa Observe–Decide–Act–Verify–Recover. Una referencia DOM/SOM queda inválida tras mutar estado. Un reintento equivalente es el máximo permitido si la entrega fue no verificable.


<!-- source: architecture/system.md -->
# Arquitectura del Hermes Harness

El perfil `default` es la única superficie de usuario. Normaliza mensajes a `IntentEnvelope`; el Control Plane valida, clasifica riesgo y enruta a herramientas directas o a un especialista aislado. El ledger y Kanban conservan estado; los resultados regresan a la sesión de origen.

## Invariantes
- Máximo cinco jobs, cuatro unidades y un navegador vivo.
- Ningún worker escribe memoria privada.
- Toda mutación externa se relee y verifica.
- El proveedor no cambia automáticamente durante una incidencia.

Ver también [agentes](architecture/agents.md), [límites de seguridad](architecture/security-boundaries.md) y [estados](architecture/state-machines.md).


<!-- source: knowledge/shared/ownership.md -->
# Ownership de conocimiento

Documentator compila fuentes verificadas y es el único writer de docs/packs. Workers emiten eventos, no mutan memoria privada. `default` puede proponer hechos estables y no sensibles para Holographic Memory tras comprobar contradicciones.


<!-- source: knowledge/shared/policy.md -->
# Conocimiento compartido

fact: timezone=deployment-configured

La documentación humana está en español; keys y enums de contratos permanecen en inglés. Los packs generados son read-only y reproducibles.


<!-- source: runbooks/browser-blocked.md -->
# Runbook de navegador bloqueado

Captura estado semántico, solicita login manual si aplica y nunca escribas secretos. Reintenta una acción equivalente solo si la entrega es incierta; si persiste, cambia representación o escala revisión visual Sol. Si no se puede verificar, devuelve `NEED_INPUT`.


<!-- source: runbooks/provider-outage.md -->
# Runbook de caída de proveedor

Pausa jobs; no cruces de proveedor automáticamente. Reintenta dos veces solo si es transitorio. En cambios atómicos no cambies modelo a mitad: reobserva en checkpoint. Notifica estado bloqueado y reanuda solo cuando Codex esté disponible.


<!-- source: runbooks/reconciliation.md -->
# Reconciliación semanal

El job de reconciliación se programa según la configuración de despliegue y la zona horaria configurada. Consume únicamente eventos verificados, recompila packs, valida enlaces, hashes, staleness y contradicciones, y emite propuestas de memoria.

La política es de continuidad y no-borrado: no elimina sesiones, conversaciones, memorias ni fuentes. Screenshots siguen siendo efímeras según el runbook de recuperación.


<!-- source: runbooks/rollback.md -->
# Runbook de rollback

Desactiva dispatch especialista con el kill switch, conserva ledger y sesiones, vuelve a `default` directo y reobserva salud. No borres evidencias ni conocimiento. Revierte al checkpoint anterior y registra un ChangeEvent con causa, alcance y verificación.


<!-- source: runbooks/rollout.md -->
# Runbook de rollout

1. Ejecuta contratos, políticas, compilación de packs y replay.
2. Activa primero lectura (Researcher, Travel, Pi y docs), luego calendario inequívoco.
3. Observa 24 horas en shadow antes de side effects.
4. Promueve solo con checkpoint, health check y rollback listo.

Cualquier violación de permisos detiene la promoción.


<!-- source: runbooks/task-15-replay-shadow.md -->
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


<!-- source: runbooks/worker-recovery.md -->
# Runbook de recuperación de worker

Heartbeat cada 60 segundos; marca stale tras 5 minutos. Cancela de forma idempotente, libera unidades y elimina screenshots efímeras. Reanuda desde el último checkpoint sin repetir side effects; detecta ciclos y pausa para intervención.


<!-- source: profiles/documentator/SOUL.md -->
# Documentator

## Misión
Mantener documentación canónica, diagramas, changelog y knowledge packs acotados a partir de eventos verificados.

## Ownership
Soy el único writer de `architecture/`, `runbooks/`, `decisions/`, `changelog/` y `knowledge/`. Compilo packs read-only, valido links, hashes y contradicciones.

## Límites
No altero código concurrente, contratos, políticas ni perfiles activos. Solo `default` puede proponer/escribir Holographic Memory tras sondear contradicciones.
