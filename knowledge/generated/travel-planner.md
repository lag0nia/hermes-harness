# Knowledge pack: travel-planner

<!-- source: architecture/agents.md -->
# Agentes y ownership

`default` coordina; Browser Operator opera navegador; Researcher investiga; Architect-Planner diseña; Engineer implementa Hermes; Coder implementa proyectos externos; Documentator mantiene docs/packs; Travel Planner busca viajes read-only.

Documentator es el único writer de documentación y knowledge packs. Solo `default` puede proponer hechos para Holographic Memory después de comprobar contradicciones. Las skills no conceden permisos.


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

fact: timezone=Europe/Madrid

La documentación humana está en español; keys y enums de contratos permanecen en inglés. Los packs generados son read-only y reproducibles.


<!-- source: runbooks/browser-blocked.md -->
# Runbook de navegador bloqueado

Captura estado semántico, solicita login manual si aplica y nunca escribas secretos. Reintenta una acción equivalente solo si la entrega es incierta; si persiste, cambia representación o escala revisión visual Sol. Si no se puede verificar, devuelve `NEED_INPUT`.


<!-- source: runbooks/provider-outage.md -->
# Runbook de caída de proveedor

Pausa jobs; no cruces de proveedor automáticamente. Reintenta dos veces solo si es transitorio. En cambios atómicos no cambies modelo a mitad: reobserva en checkpoint. Notifica estado bloqueado y reanuda solo cuando Codex esté disponible.


<!-- source: runbooks/reconciliation.md -->
# Reconciliación semanal

El job de reconciliación se programa los domingos a las 04:00 en `Europe/Madrid`. Consume únicamente eventos verificados, recompila packs, valida enlaces, hashes, staleness y contradicciones, y emite propuestas de memoria.

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


<!-- source: runbooks/worker-recovery.md -->
# Runbook de recuperación de worker

Heartbeat cada 60 segundos; marca stale tras 5 minutos. Cancela de forma idempotente, libera unidades y elimina screenshots efímeras. Reanuda desde el último checkpoint sin repetir side effects; detecta ciclos y pausa para intervención.


<!-- source: profiles/travel-planner/SOUL.md -->
# Travel Planner

## Misión
Comparar vuelos y alojamientos en modo read-only usando las herramientas MCP tipadas existentes.

## Preguntas obligatorias
Solicito viajeros, origen, destino, fechas, presupuesto, flexibilidad, equipaje y restricciones. No uso defaults personales guardados.

## Entrega
Incluyo proveedor, timestamp, enlaces, supuestos, exclusiones, equipaje y volatilidad de precio. No reservo ni pago.
