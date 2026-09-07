# Guía operativa y migración nativa a Hermes v0.21

> Estado: la Pi ejecuta Hermes Agent v0.21.0 (`v2026.8.31`) con imagen Docker fijada por digest. Esta guía describe el uso objetivo y el plan de adaptación del sistema propio. No habilita rutas ni efectos nuevos por sí misma.

## Estado verificado de la plataforma

- La Pi ejecuta `nousresearch/hermes-agent:v2026.8.31@sha256:64923faeae267792bf9bf87fe3b4c4869e35004e360c7df01730ad801b74d524`.
- Los datos de Hermes siguen montados desde `/srv/hermes`; existe un snapshot privado y verificado anterior a la actualización.
- El gateway, la configuración v39, las bases SQLite/WAL, los perfiles, el MCP Pi-Tou, el cron de observabilidad y el board Kanban `default` están saludables.
- Permanecen disponibles `default`, `browser-operator`, `documentator`, `engineer`, `researcher` y `travel-planner`. `coder` se retiró y sus rutas se resolvieron en `engineer`; `architect-planner` se integra completamente en `researcher`.
- Solo `hermes-observability` está habilitado como plugin del gateway. El auto-router y el bridge de ejecución propio no se promocionan todavía.
- La auditoría de la release oficial detecta dependencias vulnerables en `aiohttp 3.14.1` y `tornado 6.5.7`. No se parchearán dentro de la imagen: se revisará la siguiente release oficial y se repetirá el proceso de tag+digest.

## Modelo mental de Hermes v0.21

| Necesidad | Primitive nativo que debe usarse | No usar como sustituto |
|---|---|---|
| Conversación personal normal | Chat del perfil `default` | Un perfil por cada tarea puntual |
| Especialista persistente | Perfil/Bot | Un subagente genérico llamado con el nombre del perfil |
| Trabajo durable, largo o con varias etapas | Kanban | Estado de ejecución en memoria, hilos de chat o un outbox propio |
| Rutina periódica | Cron | Un loop manual o scheduler propio |
| Comunicación humana, aclaraciones y recibos | Bot Chats, menciones y grupos | Estado autoritativo de un workflow |
| Routing y autorización | Control Plane tipado y reglas versionadas | Un hook de texto que cambie directamente el perfil |
| UI Desktop | SDK público, plugin local y backend remoto explícito | Puentes privados o caches globales |

## Contrato de capacidades y roles

La matriz de `capabilities/agents/*.yaml` es el contrato de admisión del autorouter y del Control Plane. No confunde tres cosas:

- **Capability:** clase de trabajo que el perfil puede resolver.
- **Toolset:** schemas visibles en la sesión; afectan contexto, latencia y coste.
- **Autorización:** permiso efectivo para una llamada, condicionado por fase, riesgo, scope, confirmación e idempotencia.

Todos los perfiles comparten capacidades de respuesta, aclaración, resumen, contexto de sesión y skills. Las superficies de impacto alto (`terminal`, escritura, ejecución de código, navegador interactivo, delegación, cron, mutaciones Kanban y MCP externo) se declaran como condicionales: no se activan por mencionarlas en el prompt. Las acciones de credenciales, pagos, compras, reservas finales y borrado de conversaciones están denegadas para toda la flota.

| Perfil | Rol | Modo | Efecto permitido |
|---|---|---|---|
| `default` | Coordinación, admisión y síntesis final | `coordinator` | Workflow y calendario conforme a policy |
| `researcher` | Investigación, arquitectura y planificación | `read_only` | Ninguno; entrega evidencia y plan |
| `engineer` | Implementación y pruebas | `controlled_change` | Workspace y tests dentro del scope |
| `browser-operator` | Observación y preparación web | `browser_prepare` | Interacción web reversible autorizada |
| `travel-planner` | Comparación de viajes | `read_only` | Ninguno; solo búsquedas tipadas |
| `documentator` | Documentación y knowledge packs | `documentation_write` | Actualizaciones documentales verificadas |

El router ahora rechaza en carga cualquier ruta cuyo destino no declare la intención en `supported_intents`. La descripción de `profile.yaml` sirve para la UI; el `SOUL.md` explica el rol al modelo; ninguno de los dos sustituye la autorización del Control Plane.

## Uso diario resumido

### 1. Conversación simple: `default` coordina y Telegram puede delegar lo seguro

Puedes abrir cualquier Bot individualmente cuando sabes cuál quieres. En Desktop, si el mensaje entra en `default` sin destino, `default` se lo queda. En Telegram —también si el mensaje procede de un audio transcrito— `default` ejecuta una decisión local y determinista: no es un segundo prompt al modelo.

- Una petición cotidiana, genérica o ambigua se queda en `default`.
- Una única petición fuerte de viaje puede pasar a `travel-planner`; una petición de investigación/plan técnico a `researcher`; una consulta documental a `documentator`.
- Los cambios de código, operaciones de navegador, acciones comerciales, mensajes internos y cualquier mezcla ambigua se quedan en `default` y requieren tratamiento explícito.
- Para hablar directamente con la memoria separada de un Bot, selecciónalo en Desktop o indícalo explícitamente: `@travel-planner Planea un viaje a Lisboa`.
- El selector debe coincidir con la tarea: `Hazlo con Travel Planner: implementa este router` se bloquea para aclaración, nunca se reenvía silenciosamente a Engineer.
- Mantén las aprobaciones de acciones peligrosas activas.
- Usa una sesión normal para trabajo efímero; usa el Bot Chat de `default` para una relación persistente.

### 2. Bots: especialistas con identidad persistente

En Desktop, **Bots** es una vista de perfiles; no es un segundo sistema de agentes. Cada Bot tiene sus propias sesiones, memoria, habilidades, credenciales y cron.

- `Travel Planner` continúa como Bot dedicado y de solo lectura; solo se usa cuando lo pides explícitamente, y no puede reservar, pagar ni enviar acciones comerciales sin confirmación posterior.
- `researcher` es el perfil de investigación, arquitectura y planificación; `engineer` queda como especialista de implementación.
- Un Bot puede ocultarse en Desktop sin detener sus rutinas ni borrar su chat.
- No se debe crear un perfil nuevo para una traducción, una búsqueda o una tarea de un único paso: se usa una habilidad, una delegación puntual o el perfil `default`.

### 3. Kanban: la fuente de verdad para trabajo multiagente

Usa Kanban cuando haya dependencias, reintentos, varios agentes, una duración prolongada o necesidad de auditoría. La fila Kanban es la fuente de verdad; los chats son el lugar de conversación y notificación.

Flujo objetivo:

1. `default` normaliza la solicitud en un `IntentEnvelope`.
2. El Control Plane valida destino, riesgo, modelo, permisos e idempotencia.
3. Se crea una tarea Kanban con `trace_id`, `job_id`, destino y dependencia explícitos.
4. El worker de perfil real ejecuta la etapa y actualiza el estado con las herramientas Kanban.
5. Solo `default` entrega al usuario la síntesis final verificable o una solicitud de decisión; un especialista entrega evidencia al workflow, no respuestas finales competidoras.

Para desarrollo complejo la secuencia inicial será:

```text
researcher (investigación + plan) → engineer
```

La siguiente etapa solo se crea cuando la anterior aporta evidencia suficiente. No hay fan-out por defecto.

### 4. Desktop y conexión remota

Desktop puede registrar la Pi como un gateway remoto y conserva sus conexiones de forma persistente.

- En **Settings → Gateways**, la conexión remota debe apuntar a la Pi por la red Tailscale/VPN.
- La prueba de conexión debe aprobar HTTP y WebSocket.
- Mantén la Pi como fuente de las sesiones remotas: actualizar la aplicación macOS no borra sesiones almacenadas en `/srv/hermes`.
- Los plugins de Desktop se instalan en el Mac; instalar un plugin backend en la Pi no despliega automáticamente su JavaScript en macOS.

### 5. Entrada de `default`: reglas diferentes por canal

Desktop mantiene el modo directo: una petición sin selector sigue en `default`. Telegram usa una decisión local de entrada para los casos seguros, sin mini-prompt LLM ni segunda llamada al modelo. La decisión no muta el perfil del evento; produce una propuesta que el Control Plane valida antes de crear Kanban.

| Forma de uso | Comportamiento |
|---|---|
| Bot abierto manualmente | Hablas directamente con su memoria y sesiones separadas. |
| `@travel-planner ...` o `Hazlo con Travel Planner: ...` | El Control Plane valida selector e intención y crea la etapa Kanban solo si ambos coinciden. |
| Telegram: viaje inequívoco | `default` propone `travel-planner`; el Control Plane valida y delega. |
| Telegram: genérico, ambiguo o de riesgo | Se queda en `default`; no se delega. |
| Desktop: entrada sin selector | Se queda en `default`; no se clasifica automáticamente. |
| Workflow explícito | `default` crea tareas Kanban con etapas y dependencias verificables. |

Reglas no negociables:

- La allowlist cerrada contiene `researcher`, `engineer`, `travel-planner`, `browser-operator` y `documentator`.
- Dos selectores, un selector desconocido o una intención incompatible fallan cerrados y vuelven a `default` para aclaración.
- La validación se repite en el dispatcher contra el perfil destino efectivo; un cliente no puede fabricar una delegación a otro perfil.
- `pre_gateway_dispatch` no muta `event.source.profile`: la API pública v0.21 solo admite `skip`, `rewrite` o `allow`.
- Un botón Desktop solo solicita una acción; no puede saltarse fases, confirmaciones ni idempotencia.

## Backlog de adaptación del sistema propio

### Fase 1 — Corregir límites de seguridad del harness

**Repositorio:** `hermes-harness`

1. Corregir `ObservabilityBridge` para que `full` no ignore `PhasePolicy` ni confirmaciones de un solo uso.
2. Validar política contra el destino enrutado efectivo, no solo contra `origin_profile` o `requested_profile`.
3. Desactivar definitivamente el dispatcher y el outbox propios como sistema de ejecución. Conservar el harness para admisión, política, trazas, evidencia y sanitización.
4. Convertir el adaptador Kanban en integración de lectura, reconciliación e idempotencia con el estado nativo. Los workers deben usar las herramientas Kanban nativas, no tratar una salida CLI como confirmación suficiente.
5. Sustituir el replay autorreferencial por fixtures con decisiones esperadas, casos denegados, ambigüedad, idempotencia y handoffs.

**Criterio de aceptación:** no se expone `harness_submit` de ejecución hasta que todos los tests de fase, confirmación, perfil destino, reintento y recuperación sean verdes.

### Fase 2 — Decisión de entrada Telegram y delegación explícita

**Repositorio:** `hermes-auto-routing`

1. Mantener el plugin de auto-routing de hook deshabilitado y no mutar nunca `source.profile` en `pre_gateway_dispatch`.
2. En Telegram y solo desde `default`, aplicar reglas locales cerradas para una única intención segura: viajes → `travel-planner`, investigación/plan técnico → `researcher`, consulta documental → `documentator`.
3. Mantener Desktop en modo directo y respetar siempre un selector explícito de perfil.
4. Hacer que el dispatcher repita la comprobación `delegation_profile == destination` antes de crear Kanban.
5. Emitir una decisión versionada y sanitizada con `trace_id`, selector, motivo y destino validado.
6. Mantener en `default` cualquier petición genérica, ambigua, interna o con riesgo de efectos; no se reenvía mediante reescritura de texto.

**Criterio de aceptación:** un mensaje de Desktop sin selector nunca cambia de perfil; una petición inequívoca de viaje por Telegram puede llegar a `travel-planner` tras validación; una coincidencia única no crea duplicados al reintentar; el destino debe estar servido y permitido antes de crear una tarea.

### Fase 3 — Migrar observabilidad al SDK público Desktop

**Repositorio:** `hermes-observability`

1. Reemplazar `window.hermesDesktop`, `bridge.api` y rutas privadas por APIs públicas del SDK (`host` y `ctx.rest`).
2. Scope de cache y consultas por `(connectionId, profile)` para no mostrar tickets de otra gateway/perfil.
3. Instalar deliberadamente la mitad Desktop en el Mac y la mitad backend en la Pi; activar ambas y comprobarlas en UI viva.
4. Cambiar **Fix now**: debe crear una solicitud idempotente para `default`/Kanban, no ejecutar una mutación directa.
5. Añadir redacción de URL con userinfo y credenciales bearer/autorización; completar retención transaccional antes de habilitar limpieza automática.

**Criterio de aceptación:** la UI muestra el estado real `queued`, `running`, `blocked`, `succeeded` o `failed`; cambiar de gateway no reutiliza datos de otra conexión; ningún ticket o log expone secretos.

### Fase 4 — Simplificar perfiles sin borrar prematuramente

| Perfil actual | Decisión |
|---|---|
| `default` | Mantener como única entrada humana y coordinador. |
| `researcher` | Investigación, arquitectura y planificación; absorbe completamente el papel de `architect-planner`. |
| `engineer` | Mantener como implementador y revisor. |
| `browser-operator` | Mantener aislado para operaciones de navegador, con confirmación para envío/comercio. |
| `travel-planner` | Mantener como Bot dedicado de solo lectura; es destino permitido solo para planificación de viaje inequívoca. |
| `coder` | Retirado; todas las rutas `code.*` apuntan a `engineer`. |
| `documentator` | Mantener como perfil/Bot para la futura automatización documental. |

### Fase 5 — Promoción gradual

1. Shadow: clasificar entradas de canal y registrar, sin cambiar de perfil.
2. Travel canary: permitir solo peticiones inequívocas de planificación de viaje hacia `travel-planner`.
3. Workflow: habilitar la cadena `researcher → engineer` en un repositorio de prueba.
4. Tras pasar los tests de rutas, verificar que `researcher` cubre investigación y planificación y que ningún flujo sigue dirigiéndose a perfiles retirados.

Cada promoción debe contar con logs sanitizados, `trace_id`, `job_id`, pruebas de reintento y una vista visible en Desktop.

## Operación y seguridad

- Para producción usa siempre una imagen Docker con **tag + digest**; no `latest`.
- Antes de actualizar, crea snapshot privado, verificable y restaurable de los datos persistentes.
- No metas secretos en repositorios, tickets, rutas Desktop, handoffs o memoria compartida.
- No conviertas una habilidad en autorización: la autorización vive en el Control Plane.
- Las acciones comerciales, pagos, envíos y login de usuario requieren confirmación explícita y siguen fuera de esta migración.
- No ejecutes dos procesos Hermes contra el mismo profile home.

## Referencias oficiales

- [Bot Mode](https://hermes-agent.nousresearch.com/docs/user-guide/bot-mode)
- [Kanban](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban)
- [Profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles)
- [Desktop multi-connection](https://hermes-agent.nousresearch.com/docs/user-guide/multi-connection-desktop)
- [Desktop Plugin SDK](https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk)
- [Updating Hermes](https://hermes-agent.nousresearch.com/docs/getting-started/updating)
