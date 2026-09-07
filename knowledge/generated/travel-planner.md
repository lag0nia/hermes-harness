# Knowledge pack: travel-planner

<!-- source: architecture/agents.md -->
# Agentes y ownership

`default` es el único coordinador y la única superficie genérica de usuario. `researcher` investiga, diseña y planifica; `engineer` implementa y prueba; `browser-operator` observa y prepara acciones web; `travel-planner` compara viajes en read-only; `documentator` mantiene documentación canónica.

## Contrato común

Todos los perfiles pueden responder, aclarar, resumir, recuperar contexto de sesión y usar skills. Esta capacidad funcional común no implica que todos vean todos los schemas ni que una skill conceda autorización.

Las capacidades de escritura, terminal, ejecución de código, navegador interactivo, delegación, cron, mutación Kanban y MCP externo son capacidades condicionadas. Solo se activan cuando el Control Plane valida perfil efectivo, intención, fase, riesgo, confirmación e idempotencia. El `SOUL.md` orienta el comportamiento; el contrato y la política hacen cumplir los límites.

| Perfil | Rol operativo | Efectos permitidos | Límites principales |
|---|---|---|---|
| `default` | Coordinación, admisión, workflow y síntesis final | Admitir/promover workflow y calendarizar tras policy | No delegación implícita; no borra conversaciones |
| `researcher` | Investigación, arquitectura y planificación | Ninguno; entrega evidencia y plan | Read-only; no código, perfiles, memoria ni docs canónicas |
| `engineer` | Implementación y verificación | Cambios en workspace y pruebas dentro del scope | No credenciales, pagos ni mutación de producción |
| `browser-operator` | Observación y preparación web | Interacción reversible autorizada | No credenciales, pagos, compras, reservas ni shell |
| `travel-planner` | Comparación de vuelos, estancias e itinerarios | Ninguno | Read-only; no comandos, login, reserva ni pago |
| `documentator` | Documentación, diagramas, changelog y knowledge packs | Actualizaciones documentales verificadas | No código, contratos, políticas ni perfiles activos |

`coder` y `architect-planner` están retirados. Sus rutas se resuelven en `engineer` y `researcher`, respectivamente. Documentator es el único writer de documentación y knowledge packs. Solo `default` puede crear o promover etapas Kanban, resolver conflictos entre especialistas y proponer hechos para Holographic Memory después de comprobar contradicciones.


<!-- source: architecture/bot-communication-contract.md -->
# Contrato determinista de comunicación entre Bots

## Propósito

Evitar bucles, trabajos duplicados y respuestas contradictorias. Hermes Kanban nativo es la fuente de verdad para ejecución durable. Los Bot Chats, menciones y grupos son canales de conversación; no cambian por sí mismos el estado de un workflow.

## Ownership

| Acción | Único propietario |
|---|---|
| Admitir una petición genérica | `default` |
| Convertir una petición en workflow | `default` |
| Crear o promover etapas Kanban | `default` |
| Ejecutar una etapa | worker asignado a esa tarea Kanban |
| Cambiar el estado de una etapa | worker asignado o coordinador autorizado |
| Resolver desacuerdo entre especialistas | `default` o usuario mediante `NEED_INPUT` |
| Entregar respuesta final de workflow | `default` a la sesión de origen |

Un Bot abierto manualmente puede responder su conversación directa. Si ese Bot necesita un workflow con varias etapas, debe devolver el control a `default`; no crea una cadena libre de otros Bots.

## Primitiva obligatoria por necesidad

| Necesidad | Primitiva | No usar |
|---|---|---|
| Trabajo de varias etapas, reintentos o dependencias | Kanban nativo | DMs, grupos, outbox o dispatcher propio |
| Handoff | tarea hija con dependencia explícita, comentario y adjunto Kanban | título compartido, `trace_id` solo o un DM |
| Progreso | estado, heartbeat y comentario Kanban | mensajes periódicos de Bot |
| Falta de información | `kanban_block(kind=needs_input)` y pregunta canónica a `default` | esperar silenciosamente o reintentar sin datos |
| Aviso corto o recibo | `message_agent`/mención | estado autoritativo |
| Rutina periódica | Cron como disparador y Kanban como ejecución durable | cron como coordinador conversacional |
| Política, auditoría y métricas | hooks observadores/directivas acotadas | hook como cola de trabajo |

## Pipeline canónico

```text
usuario
  → default (admisión y riesgo)
  → tarea Kanban: researcher (investigación + diseño + plan)
  → tarea Kanban dependiente: engineer (implementación + pruebas)
  → resultado y evidencia verificables
  → default (síntesis única a la sesión de origen)
```

`Travel Planner`, `Documentator` y `Browser Operator` pueden ser assignees de etapas únicas cuando el usuario los solicita explícitamente y el Control Plane lo admite. Travel Planner no puede reservar, pagar, iniciar sesión ni enviar acciones comerciales.

## Envelope mínimo de handoff

Todo handoff durable debe incluir, como comentario estructurado o resultado de tarea:

```text
schema_version
trace_id
job_id
parent_job_id (si existe)
task_id
origin_profile
origin_session
assignee
idempotency_key
phase
status
summary
limitations
evidence_refs
next_state
```

El mensaje interno incluye además `origin=internal`, `hop_count` y `reply_to`. El texto íntegro del usuario, secretos, cookies, credenciales y cuerpos de herramientas no se copian a observabilidad.

## Invariantes exigibles

1. Cada entrada tiene un `trace_id` inmutable y un `request_id` o `job_id` estable.
2. Cada etapa con efectos tiene una clave de idempotencia única y reutilizable en reintentos.
3. `default` es el único perfil que convierte una petición de usuario en dispatch especialista.
4. El clasificador solo propone; la política valida el destino efectivo contra una allowlist versionada.
5. Mensajes explícitamente dirigidos, internos o de cron no pasan de nuevo por el clasificador genérico.
6. `hop_count` tiene un límite; un mensaje que lo supera termina en bloqueo, nunca en reenvío.
7. Una tarea tiene un único assignee y una única transición terminal aceptada.
8. Una dependencia es siempre un enlace Kanban explícito y acíclico.
9. Un especialista aporta evidencia; para workflows solo `default` produce la respuesta final.
10. Si hay resultados incompatibles, se preservan ambos y el workflow queda en `NEED_INPUT`/conflicto. No se inventa un compromiso silencioso.
11. Un timeout de entrega no prueba que el trabajo haya fallado: se consulta primero la tarea canónica.
12. Un resultado de herramienta externa no es éxito hasta releer el estado de destino.

## Límites de DMs, menciones y grupos

`message_agent` es asíncrono y fire-and-forget. Una mención es una interfaz para el mismo tipo de comunicación, no un handoff durable. Los grupos permiten deliberación humana visible, pero su orden de participación no es determinista. Por ello:

- no son fuente de verdad de estado;
- no disparan auto-respuestas de todos los Bots;
- no contienen reintentos ni dependencias;
- si están vinculados a una tarea, referencian `trace_id`, `job_id` y `task_id`;
- solo `default` puede llevar una conclusión del grupo a un cambio de workflow.

## Entrada y delegación

Hay dos caminos deliberadamente distintos:

- **Desktop o Bot abierto manualmente:** la conversación se queda en el perfil elegido. Si entra en `default` sin selector, `default` responde; no se clasifica automáticamente.
- **Telegram, incluido un audio ya transcrito:** `default` hace una decisión local, determinista y cerrada antes de responder. No es otro prompt al modelo y no añade una segunda llamada de inferencia. Solo puede delegar una coincidencia única, fuerte y de bajo riesgo: planificación/búsqueda de viajes a `travel-planner`, investigación o planificación técnica a `researcher` y consulta documental a `documentator`. Las peticiones genéricas, ambiguas, comerciales, internas, de navegador con interacción o de cambios de código se quedan en `default`.

El Control Plane aplica estas guardas antes de crear una tarea:

1. Reconoce como máximo un selector explícito de una allowlist cerrada; el selector explícito gana a cualquier regla de Telegram.
2. Comprueba que el texto expresa una única intención compatible con el perfil.
3. Comprueba que la plataforma es Telegram y que el mensaje entra por `default` antes de aplicar la decisión automática.
4. Verifica que `delegation_profile` coincide con el destino efectivo de la intención antes de crear Kanban.
5. Aplica política, riesgo e idempotencia; una decisión de entrada nunca ejecuta por sí misma una mutación.

Sin selector en Desktop, el resultado es `default`. En Telegram, una coincidencia única permitida produce una propuesta de delegación; dos candidatos, una intención desconocida o un perfil incompatible producen `AMBIGUOUS` y `default` conserva la conversación. No hay redirección mutando `event.source.profile`, ni reescritura del texto como comando de perfil. `pre_gateway_dispatch` solo ofrece `skip`, `rewrite` y `allow`, por lo que no es el mecanismo de selección de perfil.

Los mensajes de un especialista, Bot Chat, grupo, cron, A2A o sistema no vuelven a pasar por esta decisión: solo `default` puede iniciar una nueva etapa. El especialista devuelve evidencia estructurada al Kanban y nunca una respuesta final competidora. Abrir un Bot manualmente sigue siendo la forma nativa de hablar directamente con su memoria separada.

## Referencias

- [Bot Mode](https://hermes-agent.nousresearch.com/docs/user-guide/bot-mode)
- [Kanban](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban)
- [Cron Jobs](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron)
- `/opt/hermes/tools/bot_mode_dm.py`
- `/opt/hermes/tools/kanban_tools.py`
- `/opt/hermes/hermes_cli/kanban_db.py`
- `/opt/hermes/gateway/run.py`


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

Los contratos y el Control Plane son la segunda barrera tras los manifests. Engineer solo puede tocar las rutas incluidas en el scope del trabajo; no obtiene acceso implícito a perfiles ni configuración fuera de ese scope. Browser no ve credenciales y el usuario realiza login manualmente. Compras, reservas, pagos y promociones R2 requieren digest exacto y confirmación expirable.

Se guardan logs estructurados redactados; screenshots son efímeras y se eliminan en todo camino terminal.


<!-- source: architecture/state-machines.md -->
# Máquinas de estado

Un job sigue `RECEIVED → VALIDATED → CLASSIFIED → DISPATCHED → RUNNING → VERIFYING → SUCCEEDED`; también puede terminar en `NEED_INPUT`, `CANCELLED`, `FAILED` o `PAUSED`.

Cada side effect usa Observe–Decide–Act–Verify–Recover. Una referencia DOM/SOM queda inválida tras mutar estado. Un reintento equivalente es el máximo permitido si la entrega fue no verificable.


<!-- source: architecture/system.md -->
# Arquitectura del Hermes Harness

El perfil `default` es la única superficie genérica de usuario y el único dueño de admisión, promoción de etapas y síntesis final de workflows. Normaliza mensajes a `IntentEnvelope`; el Control Plane valida destino efectivo, intención soportada por el perfil, riesgo, modelo, permisos e idempotencia. Kanban nativo conserva el estado de ejecución; los resultados verificados regresan a la sesión de origen exclusivamente desde `default`. Los Bot Chats son conversación y aclaración, no estado de ejecución.

## Capas de capacidad

1. **Capacidad semántica:** lo que el perfil sabe resolver según su rol.
2. **Toolset visible:** schemas que Hermes expone en la sesión y que determinan contexto, latencia y coste.
3. **Autorización:** política de fase, riesgo, confirmación, scope e idempotencia aplicada por el Control Plane.

La configuración evita dos errores opuestos: un perfil inútil por falta de herramientas y una flota con todos los schemas activos en todos los turnos. Todos comparten respuesta, aclaración, resumen, contexto y skills. Las superficies caras o de impacto alto se mantienen condicionadas; las acciones sensibles siguen bloqueadas aunque el modelo las solicite.

## Invariantes

- Máximo cinco jobs, cuatro unidades y un navegador vivo.
- Ningún worker escribe memoria privada.
- Toda mutación externa se relee y verifica.
- El proveedor no cambia automáticamente durante una incidencia.
- Un mensaje interno nunca vuelve al clasificador genérico; `trace_id`, `job_id`, `hop_count` e idempotencia son obligatorios para cualquier handoff durable.
- Una tarea Kanban tiene un único assignee y una única respuesta final de `default`; las dependencias explícitas sustituyen cadenas de DMs.
- Ningún perfil contiene credenciales ni habilita checkout, pago, compra o reserva final.

La matriz ejecutable está en `capabilities/agents/*.yaml`: cada manifest declara `role`, `mode`, `supported_intents`, capacidades baseline/conditional/denied, toolsets permanentes y gates de confirmación. `config/routing.yaml` solo puede apuntar a una intención declarada por el manifest de destino.

Ver también [agentes](architecture/agents.md), [contrato de comunicación](architecture/bot-communication-contract.md), [límites de seguridad](architecture/security-boundaries.md) y [estados](architecture/state-machines.md).


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


<!-- source: profiles/travel-planner/SOUL.md -->
# Travel Planner

## Rol
Soy el planificador de viajes read-only para comparar vuelos, alojamientos e itinerarios.

## Capacidades
Puedo responder, aclarar, resumir, recuperar contexto y usar skills. Uso las búsquedas MCP tipadas existentes, comparo opciones y explico precio, equipaje, enlaces, supuestos y volatilidad. Las capacidades generales condicionadas existen en el contrato, pero terminal, archivos, código, navegador interactivo, delegación, cron y cualquier acción externa permanecen desactivados en este modo.

## Método
No convierto una búsqueda general en un cuestionario. Si falta un dato no bloqueante, comparo alternativas con un supuesto conservador y lo declaro. Solo pregunto por un dato imprescindible o antes de cualquier login, reserva, pago o dato personal.

## Límites
No ejecuto comandos, no modifico archivos, no reservo, no compro y no pago. Soy un perfil dedicado y solo read-only: no se me selecciona como sustituto genérico ni como destino automático fuera de una ruta validada.
