# Plan de migración: `default` como front door único y subagentes dinámicos

## Objetivo

Migrar de perfiles especialistas obligatorios a un único agente visible (`default`) que ejecuta el trabajo normal, carga skills bajo demanda, delega subtareas efímeras nativas cuando aportan valor y usa Kanban solo para trabajo durable, recuperable o multi-etapa.

## Contexto actual y supuestos

### Hechos verificados

- La Pi ejecuta Hermes Agent **v0.21.0** y el Desktop ya está actualizado.
- Los perfiles actuales son `default`, `researcher`, `engineer`, `browser-operator`, `travel-planner` y `documentator`.
- Los canarios de los perfiles, incluido un smoke test web de `travel-planner`, han terminado correctamente tras renovar los OAuth individuales. Los fallos anteriores de `engineer` eran tokens Codex expirados, no una prueba de que Kanban o las tools estuvieran rotas.
- La configuración actual de `default` en CLI contiene:

  ```json
  ["clarify", "file", "kanban", "session_search", "skills", "todo", "vision", "web"]
  ```

  Le faltan, entre otros, `terminal` y `delegation`. Por eso una sesión nueva de `default` no podía ejecutar `git clone` ni crear un subagente y respondía pidiendo que el usuario entrase manualmente en Engineer.
- Hermes v0.21 incorpora `delegate_task`: crea un hijo con contexto aislado, hereda las tools habilitadas del padre, devuelve un resumen al padre y no requiere que el usuario abra otro perfil.
- Un hijo de `delegate_task` no es propietario de una ejecución Kanban y Hermes impide que mutile el tablero Kanban. Esto es deseable: la delegación efímera y Kanban tienen responsabilidades distintas.
- `kanban` debe aparecer explícitamente en el toolset: el comodín `all` no lo activa.
- Cambiar el modelo principal en cada mensaje invalida la caché de prompt y es caro. La selección automática del modelo principal se aplaza a una fase posterior y, si se hace, será por sesión/tarea, no por turno.

### Problema que se corrige

La arquitectura actual convierte los perfiles en una interfaz obligatoria para el usuario. Esto contradice el comportamiento esperado: si el usuario dice «clona este repositorio», `default` debe hacerlo —o pedir una confirmación si procede—, no pedir que el usuario abra `engineer` y repita la petición.

### Decisiones de producto para Fase 1

1. **`default` será el único front door normal** en Desktop, CLI y mensajería.
2. Los perfiles especialistas no se seleccionarán automáticamente ni serán parte del flujo habitual del usuario.
3. Las skills seguirán disponibles desde `default` y se cargarán bajo demanda; no se inyectarán todas en el contexto de cada turno.
4. `default` trabajará directamente cuando la tarea sea corta o tenga una sola línea de ejecución.
5. `default` utilizará `delegate_task` para subtareas independientes, limitadas y autocontenidas.
6. Kanban se reservará para trabajo que deba sobrevivir a una sesión, tener dependencias, reintentos, auditoría o varias etapas.
7. Los perfiles actuales se conservarán temporalmente para rollback, bots manuales y compatibilidad durable. `travel-planner` se conserva como bot manual, pero `default` también podrá planificar viajes usando skills y web.
8. Más tools disponibles no equivalen a permiso para efectos externos: siguen siendo obligatorias las confirmaciones antes de compras, reservas, pagos, login, envío de mensajes, cambios irreversibles o uso de credenciales.
9. No se borrará historial de conversaciones ni se copiarán, mostrarán o registrarán secretos.
10. La selección automática del modelo del `default` y el tuning de compresión/Lean quedan explícitamente fuera de esta fase.

## Arquitectura propuesta

`default` pasa a ser un agente generalista con una matriz explícita de tools, skills progresivas y una política pequeña de ejecución. Para cada trabajo decide entre **directo**, **delegación efímera nativa** o **Kanban durable**; esa decisión describe la forma de ejecutar, no el nombre de un especialista.

El harness conservará un control plane determinista y auditable, pero dejará de enrutar al usuario a `researcher`, `engineer`, etc. Su función será validar el modo de ejecución, los efectos y las confirmaciones. La llamada nativa a `delegate_task` la hace el modelo `default`; el harness solo genera/valida el contrato de esa subtarea y registra telemetría segura.

```text
Usuario (Desktop / CLI / Telegram)
                 |
                 v
             default
        /        |          \
       /         |           \
  directo   delegate_task     Kanban durable
  una tarea  hijos aislados    recuperación/reintentos
             y acotados        dependencias/auditoría
       \         |           /
        \--------v----------/
           síntesis final
           siempre default
```

### Matriz de decisión

| Caso | Modo | Ejemplo | Regla principal |
|---|---|---|---|
| Respuesta, consulta web, edición pequeña o comando único en workspace | `direct` | `git clone` solicitado expresamente | `default` lo ejecuta; pide confirmación si hay efecto externo o falta dato crítico. |
| Investigación por fuentes, inspección de UI, comparación de APIs, chequeo focalizado | `ephemeral_delegation` | dos fuentes oficiales y capturas de una UI | 1–2 hijos con objetivo, contexto y criterio de aceptación completos; padre sintetiza. |
| Trabajo largo, recuperable, con reintentos, varias fases o dependencias | `durable_kanban` | investigación + implementación + validación nocturna | crea una tarea durable con trazabilidad; la identidad interna del worker no se expone al usuario. |
| Falta una decisión, destino o autorización crítica | `need_input` | comprar, reservar, introducir una credencial, borrar producción | preguntar y no ejecutar. |

### Reglas obligatorias para `delegate_task`

Cada hijo deberá recibir siempre:

- objetivo concreto y resultado esperado;
- contexto mínimo suficiente, sin copiar conversaciones completas ni secretos;
- qué tools puede usar y qué no puede hacer;
- criterio de aceptación verificable;
- límite de subtareas, tiempo y alcance de workspace;
- instrucción de devolver hallazgos/ficheros/resultados al padre.

Los hijos serán read-only por defecto. No podrán realizar pagos, reservas, autenticación, envío de mensajes, entrada de credenciales ni mutaciones externas sin una autorización explícita del padre que ya haya obtenido la confirmación del usuario.

## Estado final deseado

### Matriz de tools en producción

No usar `all`: es menos auditable, puede incorporar plugins futuros sin revisión y no activa Kanban. Usar listas explícitas y comprobarlas tras cada cambio.

| Plataforma de `default` | Toolsets Fase 1 | Observación |
|---|---|---|
| CLI y Desktop que resuelva al toolset CLI | `browser`, `clarify`, `code_execution`, `computer_use`, `cronjob`, `delegation`, `file`, `kanban`, `memory`, `session_search`, `skills`, `terminal`, `todo`, `vision`, `web` | Habilita trabajo normal y delegación. Browser/computer-use solo se usan si el backend real está configurado. |
| Telegram | `clarify`, `code_execution`, `delegation`, `file`, `kanban`, `memory`, `session_search`, `skills`, `terminal`, `todo`, `vision`, `web` | Misma interfaz `default`; se omiten inicialmente browser/computer-use/cronjob por falta de una UI local fiable. Las acciones con efecto siguen requiriendo confirmación. |
| Hijos de `delegate_task` | Heredan los toolsets del padre | El prompt del hijo restringe el alcance. La política conserva las confirmaciones y el hijo no puede mutar Kanban. |
| Kanban durable | `kanban` explícito + toolsets del worker validado | Usar `default` como assignee solo si el canario lo confirma; si no, usar un único worker interno de compatibilidad, no un especialista visible. |

## Plan de implementación y despliegue

> **Regla de ejecución:** todos los comandos de esta sección se ejecutarán después de aprobar este plan, nunca durante su redacción. Los comandos host con `sudo docker ...` los ejecuta el operador en la Pi; el agente no asume acceso sudo ni imprime archivos de autenticación.
>
> **Regla TDD:** en cada bloque de código, escribir primero el test indicado, ejecutar el comando y confirmar el fallo esperado; implementar el cambio mínimo; volver a ejecutar hasta verde; hacer el commit indicado antes de continuar.

### 0. Congelar el estado y crear un punto de retorno

#### 0.1 Registrar versiones y matriz efectiva sin revelar secretos

Ejecutar en la Pi:

```bash
sudo docker exec hermes sh -lc 'set -eu; H=/opt/hermes/.venv/bin/hermes; HERMES_HOME=/opt/data "$H" --version; HERMES_HOME=/opt/data "$H" config get platform_toolsets.cli --json; HERMES_HOME=/opt/data "$H" config get platform_toolsets.telegram --json; HERMES_HOME=/opt/data "$H" config get platform_toolsets.desktop --json || true; HERMES_HOME=/opt/data "$H" config get delegation --json || true; HERMES_HOME=/opt/data "$H" profile list'
```

Resultado esperado:

- versión `v0.21.x`;
- la lista actual de tools de `default` queda registrada;
- si `platform_toolsets.desktop` no existe, el comando no falla por el `|| true` y se documenta qué toolset consume realmente Desktop;
- no debe aparecer contenido de `auth.json`, `.env` ni tokens.

Guardar la salida saneada en `docs/acceptance/2026-09-single-front-door-baseline.md` dentro del repositorio, eliminando cualquier dato sensible antes de guardar.

#### 0.2 Respaldar la configuración runtime antes de tocarla

Ejecutar en la Pi:

```bash
sudo docker exec hermes sh -lc 'set -eu; ts=$(date -u +%Y%m%dT%H%M%SZ); dst=/opt/data/backups/single-front-door-$ts; mkdir -p "$dst"; test -f /opt/data/config.yaml; test -f /opt/data/SOUL.md; cp -a /opt/data/config.yaml /opt/data/SOUL.md "$dst"/; printf "BACKUP=%s\n" "$dst"'
```

Resultado esperado: una única línea `BACKUP=/opt/data/backups/single-front-door-<UTC>`. No mostrar el contenido de los backups.

#### 0.3 Capturar el estado de Kanban sin limpiarlo

Los cinco trabajos `blocked` históricos son evidencia útil del fallo de OAuth previo. No borrarlos ni reescribirlos.

```bash
sudo docker exec hermes sh -lc 'set -eu; /opt/hermes/.venv/bin/hermes kanban stats'
```

Resultado esperado: estadísticas actuales; el comando termina con código 0.

Commit de esta fase (solo documentación saneada):

```bash
git add docs/acceptance/2026-09-single-front-door-baseline.md && git commit -m "docs(acceptance): record single-front-door baseline"
```

---

### 1. Hacer tres probes nativos antes de diseñar integraciones sobre supuestos

#### 1.1 Probar delegación nativa desde una conversación `default`

En Desktop, abrir una sesión nueva de `default` y enviar literalmente:

```text
Sin modificar archivos, sin iniciar sesión y sin llamar a Kanban: usa delegate_task para delegar una única subtarea que explique en una frase qué resultado debe devolver. Después resume esa frase aquí. No cambies de perfil ni me pidas abrir otro perfil.
```

Criterio de aceptación:

- aparece una delegación/hijo o su resultado en la misma conversación `default`;
- la respuesta final vuelve a `default`;
- no aparece una instrucción de abrir Engineer/Researcher;
- no se crea una tarea Kanban.

Registrar únicamente identificadores de sesión/traza y la conclusión en `docs/acceptance/2026-09-native-delegation-probe.md`; no guardar transcript ni datos privados.

Si falla porque `delegation` aún no está habilitado, es el fallo esperado previo al cambio de runtime; continuar con el trabajo de repositorio y repetir este probe tras el despliegue.

#### 1.2 Probar si `default` puede ser assignee Kanban durable

Crear un canario inocuo y autocontenido:

```bash
sudo docker exec hermes sh -lc 'set -euo pipefail; H=/opt/hermes/.venv/bin/hermes; PY=/opt/hermes/.venv/bin/python; T=$(HERMES_HOME=/opt/data "$H" kanban create "Canario durable default assignee" --body "No uses herramientas externas ni modifiques archivos. Finaliza llamando a kanban_complete con summary exactamente DEFAULT_DURABLE_OK; si no puedes, llama a kanban_block." --assignee default --workspace scratch --max-runtime 120 --max-retries 1 --created-by migration-single-front-door --idempotency-key migration-single-front-door-default-assignee-1 --initial-status running --json | "$PY" -c "import json,sys; print(json.load(sys.stdin)[\"id\"])" ); printf "TASK_ID=%s\n" "$T"; sleep 90; HERMES_HOME=/opt/data "$H" kanban show "$T" --json'
```

Resultado esperado preferido: estado `done` y `latest_summary` exactamente `DEFAULT_DURABLE_OK`.

Decisión bloqueante:

- **Si pasa:** `durable_assignee: default` será la configuración Fase 1.
- **Si no pasa:** no forzar perfiles de cara al usuario. Crear después un único `durable-worker` interno de compatibilidad y documentar el fallo antes de continuar. No reutilizar automáticamente `engineer`, `researcher`, etc. como routing visible.

#### 1.3 Verificar qué modelo y concurrencia admite delegación

No cambiar aún ningún valor. Consultar las claves y modelos de forma segura:

```bash
sudo docker exec hermes sh -lc 'set -eu; H=/opt/hermes/.venv/bin/hermes; HERMES_HOME=/opt/data "$H" config get delegation --json || true; HERMES_HOME=/opt/data "$H" model --help | sed -n "1,160p"; HERMES_HOME=/opt/data "$H" tools list | sed -n "1,220p"'
```

Resultado esperado:

- `tools list` incluye `delegate_task` una vez que el toolset esté habilitado;
- se identifica la sintaxis efectiva de `delegation.model` y el límite de concurrencia para esta versión;
- no se imprime el estado completo de providers ni credenciales.

No elegir todavía un modelo infantil barato solo por coste: se decidirá tras medir calidad y latencia con el mismo proveedor permitido.

---

### 2. Introducir un contrato de modo de ejecución sin nombres de perfiles

#### 2.1 Añadir tests rojos del planificador de ejecución

Crear `tests/control_plane/test_execution_plan.py` con este contenido completo:

```python
from hermes_harness.control_plane.contracts import Intent, IntentEnvelope
from hermes_harness.control_plane.execution import ExecutionMode, ExecutionPlanner


def envelope(**execution: object) -> IntentEnvelope:
    return IntentEnvelope(
        intent=Intent.GENERAL_ANSWER,
        source_text="Tarea de prueba sin datos sensibles",
        parameters={"execution": execution},
    )


def test_default_work_stays_direct_and_has_no_profile() -> None:
    plan = ExecutionPlanner(durable_assignee="default", max_ephemeral_children=2).plan(envelope())

    assert plan.mode is ExecutionMode.DIRECT
    assert plan.durable_assignee is None
    assert plan.child_count == 0
    assert plan.reason_code == "default_direct"


def test_independent_work_becomes_bounded_ephemeral_delegation() -> None:
    plan = ExecutionPlanner(durable_assignee="default", max_ephemeral_children=2).plan(
        envelope(isolate=True, independent_subtasks=8)
    )

    assert plan.mode is ExecutionMode.EPHEMERAL_DELEGATION
    assert plan.child_count == 2
    assert plan.read_only_child is True
    assert plan.durable_assignee is None
    assert plan.reason_code == "isolated_subtasks"


def test_resumable_work_becomes_durable_and_uses_only_internal_assignee() -> None:
    plan = ExecutionPlanner(durable_assignee="default", max_ephemeral_children=2).plan(
        envelope(requires_resume=True)
    )

    assert plan.mode is ExecutionMode.DURABLE_KANBAN
    assert plan.durable_assignee == "default"
    assert plan.child_count == 0
    assert plan.reason_code == "durable_requested"


def test_need_input_wins_over_all_execution_modes() -> None:
    plan = ExecutionPlanner(durable_assignee="default", max_ephemeral_children=2).plan(
        envelope(needs_user_input=True, durable=True, isolate=True)
    )

    assert plan.mode is ExecutionMode.NEED_INPUT
    assert plan.durable_assignee is None
    assert plan.child_count == 0
    assert plan.reason_code == "needs_user_input"
```

Ejecutar:

```bash
uv run pytest tests/control_plane/test_execution_plan.py -q
```

Resultado esperado antes de implementar: fallo de importación indicando que `hermes_harness.control_plane.execution` no existe.

#### 2.2 Implementar el contrato mínimo en `src/hermes_harness/control_plane/execution.py`

Crear el archivo con este contenido completo. Ajustar únicamente el import de `IntentEnvelope` si el módulo existente lo exporta desde otra ruta; no duplicar el modelo.

```python
"""Deterministic execution-shape planning without specialist-profile routing."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from hermes_harness.control_plane.contracts import IntentEnvelope


class ExecutionMode(StrEnum):
    DIRECT = "direct"
    EPHEMERAL_DELEGATION = "ephemeral_delegation"
    DURABLE_KANBAN = "durable_kanban"
    NEED_INPUT = "need_input"


class ExecutionHints(BaseModel):
    """Explicit, validated hints supplied by the admission layer.

    This model intentionally has no `profile` field. A named profile is an
    implementation detail of a durable worker, never a user-facing route.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    needs_user_input: bool = False
    isolate: bool = False
    independent_subtasks: int = Field(default=0, ge=0)
    durable: bool = False
    has_dependencies: bool = False
    requires_resume: bool = False
    read_only_child: bool = True


class ExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: ExecutionMode
    child_count: int = Field(ge=0)
    read_only_child: bool
    durable_assignee: str | None
    reason_code: str


class ExecutionPlanner:
    def __init__(self, *, durable_assignee: str, max_ephemeral_children: int) -> None:
        if not durable_assignee:
            raise ValueError("durable_assignee must be non-empty")
        if max_ephemeral_children < 1:
            raise ValueError("max_ephemeral_children must be at least one")
        self._durable_assignee = durable_assignee
        self._max_ephemeral_children = max_ephemeral_children

    def plan(self, envelope: IntentEnvelope) -> ExecutionPlan:
        raw_hints = envelope.parameters.get("execution", {})
        hints = ExecutionHints.model_validate(raw_hints)

        if hints.needs_user_input:
            return ExecutionPlan(
                mode=ExecutionMode.NEED_INPUT,
                child_count=0,
                read_only_child=True,
                durable_assignee=None,
                reason_code="needs_user_input",
            )

        if hints.durable or hints.has_dependencies or hints.requires_resume:
            return ExecutionPlan(
                mode=ExecutionMode.DURABLE_KANBAN,
                child_count=0,
                read_only_child=True,
                durable_assignee=self._durable_assignee,
                reason_code="durable_requested",
            )

        if hints.isolate or hints.independent_subtasks:
            return ExecutionPlan(
                mode=ExecutionMode.EPHEMERAL_DELEGATION,
                child_count=min(max(hints.independent_subtasks, 1), self._max_ephemeral_children),
                read_only_child=hints.read_only_child,
                durable_assignee=None,
                reason_code="isolated_subtasks",
            )

        return ExecutionPlan(
            mode=ExecutionMode.DIRECT,
            child_count=0,
            read_only_child=True,
            durable_assignee=None,
            reason_code="default_direct",
        )
```

Ejecutar de nuevo:

```bash
uv run pytest tests/control_plane/test_execution_plan.py -q
uv run ruff check src/hermes_harness/control_plane/execution.py tests/control_plane/test_execution_plan.py
uv run mypy src/hermes_harness/control_plane/execution.py
```

Resultado esperado: todos terminan con código 0. Si `IntentEnvelope.parameters` no es un `dict` Pydantic-compatible, adaptar solo la lectura `raw_hints` y añadir un test de regresión; no introducir heurísticas de lenguaje natural.

Commit:

```bash
git add src/hermes_harness/control_plane/execution.py tests/control_plane/test_execution_plan.py && git commit -m "feat(control-plane): add profile-free execution planner"
```

#### 2.3 Declarar la política de ejecución fuente de verdad

Crear `config/execution-policy.yaml`:

```yaml
version: 1
user_visible_profile: default
automatic_named_profile_routing: false
durable_assignee: default
max_ephemeral_children: 2
child_defaults:
  read_only: true
  inherit_parent_toolsets: true
  allow_kanban_mutation: false
rules:
  - when: needs_user_input
    mode: need_input
  - when_any: [durable, has_dependencies, requires_resume]
    mode: durable_kanban
  - when_any: [isolate, independent_subtasks]
    mode: ephemeral_delegation
  - when: otherwise
    mode: direct
```

Añadir `tests/control_plane/test_execution_policy_config.py` para comprobar:

- versión exactamente `1`;
- `user_visible_profile == "default"`;
- `automatic_named_profile_routing is False`;
- `max_ephemeral_children == 2`;
- `allow_kanban_mutation is False`;
- `durable_assignee` no está vacío.

Ejecutar primero el test rojo y luego:

```bash
uv run pytest tests/control_plane/test_execution_policy_config.py -q
```

Resultado esperado verde: `1 passed`.

Commit:

```bash
git add config/execution-policy.yaml tests/control_plane/test_execution_policy_config.py && git commit -m "config: define single-front-door execution policy"
```

---

### 3. Sustituir el routing de perfiles por planificación de ejecución

#### 3.1 Reescribir los tests del router de mensajes antes del código

Modificar `tests/routing/test_message_router.py` para reemplazar las expectativas de `SPECIALIST` por estas reglas:

1. «Clona `git@github.com:lag0nia/study-workspace.git`…» queda en `default` y se marca como trabajo directo con `terminal`; nunca produce `engineer`.
2. «Investiga tres fuentes oficiales independientes…» produce una solicitud de delegación efímera, no `researcher`.
3. Una petición explícita al bot manual «abre Travel Planner» puede preservar la selección manual de bot, pero esa selección no se activa desde un mensaje genérico.
4. Desktop, CLI y Telegram no reescriben automáticamente un mensaje a un perfil especialista.
5. Cuando falta autorización crítica, la salida es `need_input`, no una delegación.

Ejecutar:

```bash
uv run pytest tests/routing/test_message_router.py -q
```

Resultado esperado inicial: los tests fallan porque `message_router.py` aún usa `RouteDisposition.SPECIALIST`, alias de perfiles y candidatos Telegram.

#### 3.2 Refactorizar `src/hermes_harness/control_plane/message_router.py`

Aplicar estas modificaciones concretas:

- Eliminar `_PROFILE_ALIASES`, `_specialist_candidates` y toda regla que asigne automáticamente `researcher`, `engineer`, `browser-operator`, `travel-planner` o `documentator`.
- Retirar `RouteDisposition.SPECIALIST`; conservar únicamente resultados que representen admisión normal, petición de aclaración y selección manual de bot.
- Añadir un campo `execution_hints: dict[str, object]` al objeto de decisión o, si ya hay `parameters`, rellenar `parameters["execution"]` con el contrato de `ExecutionHints`.
- Para un mensaje ordinario devolver `profile="default"` solamente como identidad visible, no como delegación; el modo será decidido por `ExecutionPlanner`.
- Tratar `@engineer`, `@travel-planner`, etc. como una selección manual explícita de bot temporal. No permitir que esta ruta se dispare por palabras sueltas como «código», «viaje» o «investiga».
- Mantener la detección de secretos y los límites existentes.

Añadir pruebas de regresión para que la decisión serializada no contenga un campo `delegation_profile` para rutas `direct` ni `ephemeral_delegation`.

Ejecutar:

```bash
uv run pytest tests/routing/test_message_router.py -q
uv run ruff check src/hermes_harness/control_plane/message_router.py tests/routing/test_message_router.py
```

Resultado esperado: todos verdes y ninguna aserción de specialist routing restante.

Commit:

```bash
git add src/hermes_harness/control_plane/message_router.py tests/routing/test_message_router.py && git commit -m "refactor(routing): stop automatic specialist-profile routing"
```

#### 3.3 Reemplazar la configuración de routing obsoleta

Actualizar `config/message-routing.yaml` para que tenga este contenido:

```yaml
schema_version: execution-routing-1.0.0
policy:
  user_visible_profile: default
  automatic_named_profile_routing: false
  named_profile_selection: manual_only
  default_execution_policy: config/execution-policy.yaml
```

Actualizar `config/routing.yaml` a formato versión 2. La estructura mínima debe separar capacidad de herramienta de identidad de perfil:

```yaml
version: 2
default_profile: default
execution_policy: config/execution-policy.yaml
direct_tools:
  terminal: [technical.change, code.change, general.answer]
  web: [technical.research, travel.plan, general.answer]
  file: [technical.change, code.change, docs.reconcile, general.answer]
  delegation: [technical.research, technical.plan, browser.research, travel.plan]
durable_workers:
  default:
    supported_intents: [technical.research, technical.plan, technical.change, code.change, code.review, docs.reconcile, general.answer]
```

Antes de fijar los valores finales, contrastar los valores exactos de `Intent` en `src/hermes_harness/control_plane/contracts.py`. Si algún literal de la lista no existe, usar el literal real del enum y añadirlo al test de carga; no inventar intents nuevos en esta migración.

Actualizar `src/hermes_harness/control_plane/router.py` para validar:

- el formato `version: 2`;
- que `default_profile` es `default`;
- que las routes directas no requieren profile de destino;
- que solo `durable_workers` requiere un assignee validado;
- que una capacidad pedida pertenece a la lista de tools permitidas;
- que no hay rutas automáticas a perfiles especialistas.

Ejecutar:

```bash
uv run pytest tests/routing -q
uv run python scripts/replay_routing.py --help
```

Resultado esperado: tests verdes y el script muestra ayuda sin traceback.

---

### 4. Adaptar dispatcher, Kanban y política sin abrir una vía insegura en MCP

#### 4.1 Cambiar los tests de dispatcher a modos de ejecución

Modificar `tests/integration/test_kanban_dispatch.py` para cubrir exactamente:

- `direct` no crea tarea Kanban;
- `ephemeral_delegation` devuelve una especificación de delegación y no crea tarea Kanban;
- `durable_kanban` crea una única tarea con `assignee == "default"` si el probe 1.2 pasó;
- el payload durable conserva `trace_id`, `job_id`, `idempotency_key`, `skills` y modelo explícito cuando se proporcionan;
- ningún test espera la cadena fija `researcher -> engineer`;
- el input no puede elegir libremente un profile interno diferente de los aprobados por política.

Ejecutar:

```bash
uv run pytest tests/integration/test_kanban_dispatch.py -q
```

Resultado esperado inicial: fallos por `PROFILE_BY_INTENT`, `DEVELOPMENT_WORKFLOW` y `delegation_profile` existentes.

#### 4.2 Añadir una especificación segura de delegación

En `src/hermes_harness/dispatcher.py`, añadir un dataclass inmutable `DelegationRequest` con estos campos exactos:

```python
@dataclass(frozen=True)
class DelegationRequest:
    job_id: str
    trace_id: str
    goal: str
    context: str
    acceptance_criteria: tuple[str, ...]
    required_toolsets: tuple[str, ...]
    workspace_path: str | None
    child_count: int
    read_only: bool
    model_hint: str | None
```

Reglas de implementación:

- `goal`, `context` y criterios pasan por los validadores existentes `reject_sensitive`/`reject_sensitive_text` antes de construir el dataclass.
- `context` debe ser un resumen estructurado y acotado; nunca se serializa una conversación completa.
- `child_count` llega del `ExecutionPlan` y no supera `max_ephemeral_children`.
- Esta clase **no** invoca procesos ni llama a Kanban. Es el contrato que el agente `default` convierte en una llamada nativa `delegate_task`.

Modificar `Dispatcher.dispatch()` así:

- llamar a `ExecutionPlanner.plan(envelope)` al inicio;
- `DIRECT`: devolver el resultado directo actual sin Kanban;
- `EPHEMERAL_DELEGATION`: devolver `DelegationRequest` y emitir `execution.planned` con `mode=ephemeral_delegation`;
- `DURABLE_KANBAN`: construir `KanbanTask` usando exclusivamente `plan.durable_assignee` y mantener la lectura exacta post-creación;
- `NEED_INPUT`: devolver una decisión de aclaración y no crear tarea ni hijo;
- borrar `PROFILE_BY_INTENT` y `DEVELOPMENT_WORKFLOW`.

No añadir un endpoint MCP de ejecución completa. `src/hermes_harness/mcp_server.py` debe continuar exponiendo solo las operaciones seguras ya cubiertas por `tests/integration/test_mcp_server.py`.

Ejecutar:

```bash
uv run pytest tests/integration/test_kanban_dispatch.py tests/integration/test_mcp_server.py tests/integration/test_runtime_mcp.py -q
```

Resultado esperado: todos verdes; `harness_submit` sigue ausente del servidor MCP.

Commit:

```bash
git add src/hermes_harness/dispatcher.py tests/integration/test_kanban_dispatch.py tests/integration/test_mcp_server.py tests/integration/test_runtime_mcp.py && git commit -m "refactor(dispatcher): plan direct ephemeral and durable work"
```

#### 4.3 Cambiar política de perfiles a política de efectos y modo

Modificar `tests/policy/test_policy.py` primero para exigir:

- una tarea `direct` o `ephemeral_delegation` no necesita `requested_profile`;
- un durable solo permite `durable_assignee` incluido en la política;
- borrar protegido, pago/reserva, credenciales y efectos críticos siguen requiriendo confirmación o se rechazan;
- el modelo principal de `default` no cambia por mensaje;
- un modelo de hijo solo puede llegar como `model_hint` autorizado por la política.

Refactorizar `src/hermes_harness/control_plane/policy.py`:

- evaluar `ExecutionPlan.mode`, alcance de efecto y confirmación, no el perfil visible;
- conservar validación de provider/model/effort, pero mover la allowlist de modelos desde perfiles especialistas a dos grupos: `main_default` y `delegated_child`;
- aceptar el assignee solo cuando `mode == DURABLE_KANBAN`;
- preservar todas las denegaciones de secretos, pagos, borrados protegidos y cambios críticos.

Actualizar `config/model-policy.yaml` sin modificar el modelo principal activo:

```yaml
version: 2
provider: openai-codex
main_default:
  allowed_models: [gpt-5.6-luna-900k, gpt-5.6-terra-900k]
  automatic_per_message_switching: false
delegated_child:
  allowed_models: [gpt-5.6-luna, gpt-5.6-terra]
  require_explicit_model_hint: false
durable_worker:
  allowed_assignees: [default]
  allowed_models: [gpt-5.6-luna, gpt-5.6-terra, gpt-5.6-terra-900k]
```

Antes de guardar esta configuración, verificar con `hermes model` qué nombres admite realmente el provider de la Pi. Si `gpt-5.6-terra-900k` no es un nombre admitido por Hermes en esa instalación, retirar solo ese literal y documentar la decisión; no usar un nombre inventado.

Ejecutar:

```bash
uv run pytest tests/policy/test_policy.py -q
uv run ruff check src/hermes_harness/control_plane/policy.py tests/policy/test_policy.py
uv run mypy
```

Resultado esperado: código 0 en los tres comandos.

Commit:

```bash
git add src/hermes_harness/control_plane/policy.py config/model-policy.yaml tests/policy/test_policy.py && git commit -m "refactor(policy): authorize execution modes instead of specialist profiles"
```

---

### 5. Convertir `default` en el agente principal en manifiestos, SOUL y documentación

#### 5.1 Crear la fuente de identidad de `default`

Crear `profiles/default/SOUL.md` con el siguiente contenido:

```markdown
# Default — front door único

Eres el agente principal visible para el usuario. Resuelves trabajo normal directamente; no obligas al usuario a abrir perfiles especialistas para clonar repositorios, investigar, editar un workspace, navegar o ejecutar comandos autorizados.

## Forma de trabajar

1. Comprende el objetivo, el workspace y los efectos antes de actuar.
2. Carga las skills necesarias bajo demanda. La existencia de una skill no obliga a cargarla si no aporta valor.
3. Ejecuta directamente las tareas simples y de una sola línea de trabajo.
4. Usa `delegate_task` solo para subtareas independientes, acotadas y autocontenidas. Cada hijo recibe objetivo, contexto mínimo, restricciones y criterio de aceptación. Los hijos devuelven hallazgos; tú sintetizas la respuesta final.
5. Usa Kanban únicamente para trabajo durable: reintentos, dependencias, varias etapas, recuperación o auditoría. Nunca pidas al usuario que entre en un perfil para que una tarea normal pueda continuar.
6. Los perfiles nombrados son bots/manuales o compatibilidad interna, no el router automático de la conversación.

## Seguridad y autorización

- Tener una tool no es autorización para usarla.
- Pide confirmación clara antes de compras, reservas, pagos, envío de mensajes, login, entrada de credenciales, cambios irreversibles o efectos externos no solicitados inequívocamente.
- No expongas ni copies credenciales, tokens, cookies ni secretos a prompts de hijos, logs o resúmenes.
- No borres conversaciones ni historial.
- Mantén los cambios de archivos y comandos dentro del workspace acordado; informa de resultados verificables.

## Síntesis

La respuesta final pertenece a `default`: explica qué se hizo, qué se verificó, qué no se hizo y cualquier decisión que requiera al usuario.
```

#### 5.2 Actualizar `capabilities/agents/default.yaml`

Cambiar los campos de rol a:

```yaml
role: Agente principal visible y ejecutor generalista.
description: Resuelve trabajo normal directamente, usa skills bajo demanda y delega subtareas nativas acotadas sin obligar al usuario a cambiar de perfil.
mode: primary
role_constraints:
  denied_effects:
    - payment
    - purchase
    - booking
    - credential_entry
    - credential_exposure
    - conversation_deletion
  confirmation_required:
    - external_mutation
    - authentication
    - payment
    - purchase
    - booking
    - irreversible_change
```

Cambiar la política de toolsets de fuente a:

```yaml
tool_policy:
  permanent_toolsets:
    - browser
    - clarify
    - code_execution
    - computer_use
    - cronjob
    - delegation
    - file
    - kanban
    - memory
    - session_search
    - skills
    - terminal
    - todo
    - vision
    - web
  task_gated_toolsets: []
```

Mantener la lista explícita de capacidades/effects, ampliándola a la unión de los intents ya presentes en los manifiestos especialistas. No duplicar literalmente sus roles ni añadir nuevos intents no existentes en `Intent`.

Cambiar los manifiestos y SOULs de:

- `capabilities/agents/researcher.yaml`
- `capabilities/agents/engineer.yaml`
- `capabilities/agents/browser-operator.yaml`
- `capabilities/agents/travel-planner.yaml`
- `capabilities/agents/documentator.yaml`
- `profiles/researcher/SOUL.md`
- `profiles/engineer/SOUL.md`
- `profiles/browser-operator/SOUL.md`
- `profiles/travel-planner/SOUL.md`
- `profiles/documentator/SOUL.md`

para indicar expresamente: «bot manual o worker de compatibilidad; no destino automático de una conversación `default`». Conservar sus límites de seguridad y especialidad. `travel-planner` seguirá siendo un bot preservado.

#### 5.3 Actualizar documentación y knowledge packs

Actualizar:

- `README.md`
- `architecture/system.md`
- `architecture/agents.md`
- `docs/hermes-v021-operator-guide.md`

Deben dejar de decir «default coordinador-only», «no delegación implícita» o «default → especialistas» como flujo obligatorio. Deben describir la tabla de decisión de este plan y la diferencia entre hijos efímeros y Kanban durable.

Actualizar los tests/documentación existentes:

- `tests/documentation/test_skills_and_souls.py`
- `tests/documentation/test_knowledge_packs.py`
- `scripts/compile_knowledge_packs.py` si la enumeración de perfiles es estática.

Ciclo TDD:

```bash
uv run pytest tests/documentation/test_skills_and_souls.py tests/documentation/test_knowledge_packs.py -q
uv run python scripts/compile_knowledge_packs.py
uv run pytest tests/documentation/test_skills_and_souls.py tests/documentation/test_knowledge_packs.py -q
```

Resultado esperado: tests verdes y compilación sin traceback. Revisar el diff generado y confirmar que no introduce credenciales ni copias de conversaciones.

Commit:

```bash
git add profiles/default/SOUL.md capabilities/agents README.md architecture docs profiles tests/documentation scripts/compile_knowledge_packs.py && git commit -m "docs(agents): make default the primary autonomous front door"
```

---

### 6. Actualizar replay, observabilidad y contratos de no filtración

#### 6.1 Sustituir fixtures que codifican perfiles por fixtures de modo

Modificar `scripts/replay_routing.py` y sus fixtures/tests asociados para que los resultados comparen:

```json
{
  "intent": "technical.research",
  "mode": "ephemeral_delegation",
  "reason_code": "isolated_subtasks",
  "user_visible_profile": "default"
}
```

No comparar `researcher`, `engineer` ni listas de perfiles candidatos para una ruta automática.

Ejecutar:

```bash
uv run python scripts/replay_routing.py --fixtures tests/fixtures/routing --output /tmp/execution-routing-replay.json
uv run pytest tests/replay -q
```

Resultado esperado: el JSON de salida contiene `mode` y `reason_code`; los tests pasan.

#### 6.2 Añadir telemetría mínima y segura

En `src/hermes_harness/dispatcher.py` reutilizar el emisor existente para producir solo estos eventos:

- `execution.planned`: `trace_id`, `job_id`, `intent`, `mode`, `reason_code`, `child_count`;
- `delegation.requested`: los mismos identificadores y `read_only`;
- `durable.queued`: los mismos identificadores y el assignee interno;
- `execution.needs_input`: `trace_id`, `intent`, `reason_code`.

Prohibiciones:

- no registrar `goal`, `context`, cuerpo de conversación, credenciales, rutas de tokens ni valores de tools;
- no almacenar texto del prompt del hijo como atributo de observabilidad;
- no emitir nombre de perfiles especialistas en rutas directas/efímeras.

Añadir una prueba que introduzca una cadena con apariencia de token en `source_text` y confirme que ni el evento ni el JSON serializado la contienen.

Ejecutar:

```bash
uv run pytest tests/integration/test_runtime_mcp.py tests/integration/test_kanban_dispatch.py tests/policy/test_policy.py -q
```

Resultado esperado: todos verdes y la prueba de no filtración pasa.

Commit:

```bash
git add scripts/replay_routing.py tests src/hermes_harness/dispatcher.py && git commit -m "feat(observability): trace execution mode without routing profiles"
```

---

### 7. Validación completa del repositorio antes de producción

Ejecutar desde `/opt/data/hermes-harness`:

```bash
uv run pytest -q && uv run ruff check . && uv run mypy && uv run python scripts/compile_knowledge_packs.py
```

Resultado esperado: cuatro comandos correctos; no warnings convertidos en errores y ningún cambio no revisado tras compilar knowledge packs.

Ejecutar además:

```bash
git status --short && git log --oneline -6
```

Resultado esperado: árbol limpio tras hacer los commits de cada slice, y commits pequeños con el orden de este plan.

Crear `docs/acceptance/2026-09-single-front-door-test-report.md` con:

- hash de la versión candidata;
- resultado de pytest/ruff/mypy/compilación;
- resultado de cada probe;
- decisión de assignee durable;
- modelo principal que **se mantuvo** sin cambio;
- incidencias conocidas, sin secretos.

Commit:

```bash
git add docs/acceptance/2026-09-single-front-door-test-report.md && git commit -m "docs(acceptance): record single-front-door validation"
```

---

### 8. Despliegue gradual en la Pi

#### 8.1 Preflight de la configuración runtime

Antes de escribir, confirmar que los nombres de toolsets son reconocidos:

```bash
sudo docker exec hermes sh -lc 'set -eu; H=/opt/hermes/.venv/bin/hermes; HERMES_HOME=/opt/data "$H" tools list | grep -E "(^|[[:space:]])(delegation|terminal|kanban|skills|web|file|browser|computer_use)([[:space:]]|$)"'
```

Resultado esperado: aparecen como mínimo `delegation`, `terminal`, `kanban`, `skills`, `web` y `file`. Si falta uno, detener el despliegue y documentar la diferencia de versión; no escribir un toolset desconocido.

#### 8.2 Copiar el SOUL revisado al runtime de `default`

Tras haber hecho el backup 0.2 y revisado el diff:

```bash
sudo docker exec hermes sh -lc 'set -eu; test -f /opt/data/hermes-harness/profiles/default/SOUL.md; install -m 600 /opt/data/hermes-harness/profiles/default/SOUL.md /opt/data/SOUL.md; test -s /opt/data/SOUL.md'
```

Resultado esperado: sin salida y código 0. La ruta correcta del profile `default` runtime es `/opt/data/SOUL.md`, no `/opt/data/profiles/default/SOUL.md`.

#### 8.3 Aplicar la matriz explícita de CLI/Desktop

Aplicar primero CLI, que es el valor que los datos actuales ya muestran para `default`:

```bash
sudo docker exec hermes sh -lc 'set -eu; H=/opt/hermes/.venv/bin/hermes; HERMES_HOME=/opt/data "$H" config set platform_toolsets.cli "[\"browser\",\"clarify\",\"code_execution\",\"computer_use\",\"cronjob\",\"delegation\",\"file\",\"kanban\",\"memory\",\"session_search\",\"skills\",\"terminal\",\"todo\",\"vision\",\"web\"]"; HERMES_HOME=/opt/data "$H" config get platform_toolsets.cli --json'
```

Resultado esperado exacto: la lista JSON explícita anterior, incluido `delegation`, `terminal` y `kanban`.

Para Desktop:

1. si el preflight 0.1 prueba que Desktop usa `platform_toolsets.cli`, no hacer una segunda escritura;
2. si identifica una clave específica y documentada —por ejemplo `platform_toolsets.desktop`—, aplicar exactamente la misma lista sustituyendo solo la clave;
3. verificar con `config get` y una conversación nueva de Desktop; no asumir que una clave desconocida funciona.

#### 8.4 Aplicar la matriz Telegram conservadora

```bash
sudo docker exec hermes sh -lc 'set -eu; H=/opt/hermes/.venv/bin/hermes; HERMES_HOME=/opt/data "$H" config set platform_toolsets.telegram "[\"clarify\",\"code_execution\",\"delegation\",\"file\",\"kanban\",\"memory\",\"session_search\",\"skills\",\"terminal\",\"todo\",\"vision\",\"web\"]"; HERMES_HOME=/opt/data "$H" config get platform_toolsets.telegram --json'
```

Resultado esperado: JSON con `delegation`, `terminal` y `kanban`, sin `browser`, `computer_use` ni `cronjob` en esta primera promoción.

#### 8.5 Configurar delegación solo tras el probe de modelo

Si el probe 1.3 confirma que las claves son válidas, empezar con dos hijos como máximo:

```bash
sudo docker exec hermes sh -lc 'set -eu; H=/opt/hermes/.venv/bin/hermes; HERMES_HOME=/opt/data "$H" config set delegation.max_concurrent_children 2; HERMES_HOME=/opt/data "$H" config get delegation --json'
```

Resultado esperado: JSON con concurrencia máxima `2`.

No fijar `delegation.model` en este paso hasta que una tabla de medida (calidad, latencia, tokens, errores) compare `gpt-5.6-luna` y `gpt-5.6-terra` para hijos. Hasta entonces el hijo hereda el modelo del padre o el comportamiento nativo documentado.

#### 8.6 Reiniciar y comprobar salud

```bash
sudo docker restart hermes && sleep 10 && sudo docker inspect --format 'status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' hermes && sudo docker exec hermes sh -lc 'set -eu; H=/opt/hermes/.venv/bin/hermes; HERMES_HOME=/opt/data "$H" status --all; HERMES_HOME=/opt/data "$H" config get platform_toolsets.cli --json; HERMES_HOME=/opt/data "$H" config get platform_toolsets.telegram --json; HERMES_HOME=/opt/data "$H" config check'
```

Resultado esperado:

- `status=running`;
- `status --all` informa gateway running;
- ambas matrices contienen sus toolsets esperados;
- `config check` termina con código 0;
- no se muestra ningún token.

---

### 9. Canarios de aceptación en vivo

Ejecutar los canarios en este orden. Detener la promoción ante el primer fallo funcional o de seguridad.

#### 9.1 Canario de skills progresivas

En una sesión nueva `default`:

```text
Lista las skills disponibles sin cargar más de una. Explica en una frase qué skill elegirías para una tarea de desarrollo. No modifiques nada.
```

Resultado esperado: puede listar/buscar skills y cargar, como máximo, una cuando sea necesaria; no afirma que todas estén preinyectadas.

#### 9.2 Canario de ejecución directa sin cambio de perfil

En Desktop `default`:

```text
En el workspace scratch, crea un archivo temporal con el texto DIRECT_OK, léelo para verificarlo y elimínalo. No uses Kanban ni delegues. Resume los tres resultados.
```

Resultado esperado:

- usa `file` o `terminal` directamente desde `default`;
- no pide abrir Engineer;
- el archivo no existe al terminar;
- la respuesta enumera creación, verificación y limpieza.

#### 9.3 Canario de delegación efímera read-only

En Desktop `default`:

```text
Sin iniciar sesión, sin modificar archivos y sin usar Kanban, delega dos subtareas independientes: una debe resumir qué exige una buena delegación y la otra debe enumerar sus límites de seguridad. Devuélveme una síntesis con dos viñetas y di cuántos hijos usaste.
```

Resultado esperado:

- máximo dos hijos;
- no hay cambio de perfil visible ni petición de abrir un perfil;
- el padre sintetiza;
- `kanban stats` no incrementa tareas por este canario.

Verificar este último punto:

```bash
sudo docker exec hermes sh -lc '/opt/hermes/.venv/bin/hermes kanban stats'
```

#### 9.4 Caso real objetivo: clonación solicitada desde `default`

Este paso tiene efecto de red y de escritura. Pedir confirmación al usuario inmediatamente antes si no está vigente; comprobar que el destino no contiene material que vaya a sobrescribirse.

Tras confirmación, enviar a `default`:

```text
Clona git@github.com:lag0nia/study-workspace.git en /opt/data/work/study-workspace. Si el directorio ya existe y no está vacío, detente y dime qué contiene. Verifica git remote -v, lee README y resume la estructura inicial. No muestres credenciales ni tokens.
```

Resultado esperado:

- `default` ejecuta o pide una aclaración/confirmación concreta si hay colisión, SSH host-key o autorización faltante;
- nunca responde «entra en Engineer»;
- si clona correctamente, verifica remoto, README y estructura;
- no imprime private keys, tokens ni contenido de `auth.json`.

Si falla por SSH, investigar la llave/montaje/known_hosts como incidencia de Git, no reintroducir perfiles como workaround.

#### 9.5 Canario Kanban durable

Crear desde `default` una tarea que requiera recuperación y comprobar el resultado según el probe 1.2. El body debe exigir `kanban_complete` con summary exacto `DURABLE_DEFAULT_OK` y no usar herramientas externas.

Resultado esperado:

- una tarea durable con assignee interno `default` (o el único worker interno aprobado por la decisión 1.2);
- el usuario ve que `default` inició y sintetizó el trabajo, no que fue enviado a un “especialista”;
- el run termina `done` y summary `DURABLE_DEFAULT_OK`.

#### 9.6 Regresión manual de Travel Planner

Abrir manualmente el bot `travel-planner` y repetir una consulta pública read-only. Resultado esperado: continúa pudiendo usar web y no realiza autenticación, reservas ni compras. Esto protege la conservación del bot mientras deja de ser una dependencia del flujo normal.

#### 9.7 Evidencia de observabilidad

Consultar salud y eventos con el método ya instalado, filtrando por identificadores de canario y verificando:

- existen `execution.planned`/`delegation.requested`/`durable.queued` donde corresponda;
- no se ven secretos, cuerpos completos de prompts o datos de OAuth;
- no hay routing automático a specialist profiles.

Guardar resultados saneados en `docs/acceptance/2026-09-single-front-door-live.md`.

---

### 10. Rollback operativo

Aplicar rollback si falla una de estas condiciones:

- `default` vuelve a pedir cambiar de perfil para una tarea que tiene tool/capacidad autorizada;
- una delegación puede crear/mutar Kanban sin ser durable;
- aparece un secreto en logs, prompt o respuesta;
- se pierde la confirmación antes de una acción de efecto externo;
- gateway no recupera salud tras reinicio.

Con la ruta `BACKUP` producida en 0.2, restaurar solo la configuración y SOUL runtime:

```bash
sudo docker exec hermes sh -lc 'set -eu; src=/opt/data/backups/single-front-door-REEMPLAZAR_UTC; test -f "$src/config.yaml"; test -f "$src/SOUL.md"; cp -a "$src/config.yaml" /opt/data/config.yaml; cp -a "$src/SOUL.md" /opt/data/SOUL.md' && sudo docker restart hermes
```

Después comprobar:

```bash
sudo docker exec hermes sh -lc 'set -eu; H=/opt/hermes/.venv/bin/hermes; HERMES_HOME=/opt/data "$H" status --all; HERMES_HOME=/opt/data "$H" config check'
```

Resultado esperado: gateway running y `config check` correcto. No borrar perfiles, auth ni historial durante un rollback.

## Tests y validación: resumen obligatorio

| Área | Red | Green | Verificación final |
|---|---|---|---|
| Planificador de ejecución | `tests/control_plane/test_execution_plan.py` falla por módulo inexistente | crear `execution.py` | pytest + ruff + mypy focalizados |
| Política YAML | nuevo test de `execution-policy.yaml` falla | añadir YAML | `1 passed` |
| Routing | tests dejan de esperar specialists | retirar routing automático | `pytest tests/routing -q` |
| Dispatcher | tests de modo fallan con `PROFILE_BY_INTENT` | `DelegationRequest` + dispatch por plan | tests integración/MCP verdes |
| Policy | tests de efectos/modos fallan | policy sin profile visible | pytest policy + mypy |
| Docs/SOUL | tests de knowledge packs fallan con default nuevo | actualizar documentación y compilar | tests docs + compilador |
| Producción | canarios previos al cambio fallan por falta de tools | matriz explícita + SOUL runtime | direct, delegation, Kanban, Travel y telemetría |

Antes de producción, la definición de terminado es:

- [ ] suite, ruff, mypy y compilador de knowledge packs en verde;
- [ ] `default` tiene `terminal`, `delegation` y `kanban` explícitos donde procede;
- [ ] un comando/edición normal no exige abrir un perfil especialista;
- [ ] el hijo efímero vuelve a `default`, es acotado y no muta Kanban;
- [ ] Kanban durable tiene un assignee validado y no expone su identidad como requisito al usuario;
- [ ] los efectos sensibles siguen solicitando confirmación;
- [ ] no hay secretos en la evidencia ni observabilidad;
- [ ] rollback probado documentalmente y backup disponible.

## Riesgos, tradeoffs y mitigaciones

### Más tools en `default`

**Riesgo:** mayor superficie de error del modelo.

**Mitigación:** toolsets explícitos, scopes de workspace, SOUL claro, `clarify` ante ambigüedad y la política actual de confirmaciones. No usar `all` ni conceder plugins implícitos.

### Subagentes “spam” y consumo de tokens/CPU

**Riesgo:** delegar indiscriminadamente aumenta latencia, coste y ruido.

**Mitigación:** `max_ephemeral_children: 2` inicialmente; solo para trabajo independiente; el hijo devuelve resumen, no transcript; medir antes de subir a 3. La delegación no se usa para una tarea trivial que `default` puede resolver en un turno.

### Hijos con contexto aislado

**Riesgo:** un hijo carece de detalles y entrega resultados pobres.

**Mitigación:** contrato obligatorio de `goal`, `context`, restricciones y criterio de aceptación. Nunca pasar chat completo ni secretos.

### Kanban requiere assignee

**Riesgo:** la versión instalada podría no aceptar `default` como worker durable.

**Mitigación:** probe 1.2 previo. Si falla, un único worker interno de compatibilidad, sin volver a perfiles especialistas como interfaz de usuario. Esta decisión se documenta antes del despliegue.

### Browser/computer-use no listo en la Pi

**Riesgo:** una tool habilitada no tiene backend/CDP/configuración operativa.

**Mitigación:** habilitarla en la matriz Desktop/CLI solo si Hermes reconoce el toolset; tratar backend ausente como bloqueo claro; no intentar browser/computer-use desde Telegram en Fase 1.

### Git SSH

**Riesgo:** el clone real puede fallar por clave SSH, known_hosts o permisos de filesystem.

**Mitigación:** eso se investiga como requisito de Git/host, manteniendo el comportamiento correcto de `default`; no es motivo para obligar a cambiar de profile.

### Migration de config upstream

**Riesgo:** un update de Hermes puede cambiar nombres de claves/toolsets.

**Mitigación:** usar `hermes config get/set/check`, no editar YAML runtime a mano; hacer preflight de tools; mantener backup y rollback.

## Preguntas abiertas que deben resolverse con probes, no con suposiciones

1. ¿El Desktop remoto usa `platform_toolsets.cli` o una clave propia? Resolver con el preflight 0.1 y un canario de conversación nueva.
2. ¿Puede `default` ser `--assignee default` para Kanban en v0.21 de esta Pi? Resolver con 1.2.
3. ¿Qué modelo concreto ofrece mejor relación calidad/latencia para hijos con la suscripción actual? Medir antes de configurar `delegation.model`.
4. ¿Qué backend browser/computer-use está realmente instalado y operativo en la Pi? No prometer navegación visual hasta canario específico.
5. ¿La política de Telegram permite comandos de terminal tras confirmación en el canal real? Validar con un canario de archivo temporal antes de ampliar acciones externas.

## Fase 2 explícitamente aplazada

### Selección de modelo por sesión/tarea

No implementar un cambio automático del modelo principal por mensaje. Cuando Fase 1 sea estable durante un periodo observado:

1. definir una clasificación determinista de **creación de sesión** (no de turno) basada en modalidad solicitada, límite de coste y complejidad declarada;
2. conservar `/model` como override manual;
3. seleccionar el modelo del hijo mediante `delegation.model` o `model_hint` validado, no mediante cambio del padre a mitad de conversación;
4. medir tokens, latencia, errores y calidad de canarios antes de promover un router;
5. añadir rollback inmediato al modelo principal fijo actual.

### Compresión y Lean

Cambiar Lean no se considera solución automática para la compresión. La compresión usa slots auxiliares y debe diagnosticarse por separado: revisar eventos de compresión, configuración del modelo auxiliar, tamaño de contexto, errores del provider y tasas de éxito. Cualquier cambio se probará en una sesión de prueba y no se mezclará con esta migración de arquitectura.

### Retirada de perfiles legacy

No borrar perfiles en Fase 1. Tras al menos 30 días de telemetría estable, cero regresiones de front door y un plan de export/rollback, evaluar si se reducen a `default`, `travel-planner` manual y, solo si es imprescindible, un worker durable interno.
