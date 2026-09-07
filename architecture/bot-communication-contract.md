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
