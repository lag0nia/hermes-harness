# Observability runbook

## Alcance aprobado

La primera activación usa el modo completo para las capacidades no comerciales.
No se ejecutan compras, pagos, checkout, cambios reales de carrito ni reservas
finales. La protección de secretos y datos personales sigue activa.

Esta entrega no incluye:

- una prueba E2E real desde Desktop;
- una prueba de rollback o apagado;
- una revisión independiente de seguridad;
- pruebas por CLI o Telegram;
- una espera de 24 horas;
- una fase previa de solo observar o solo consultar.

## Routing automático de mensajes

El primer tramo de routing de contenido está preparado para el gateway
`default`. Hermes debe tener el multiplexado de perfiles activo y una lista de
perfiles servidos explícita. La configuración actual limita el routing
automático a `researcher` y `engineer`:

```yaml
gateway:
  multiplex_profiles: true
  multiplex_profile_allowlist: [researcher, engineer]
```

El plugin `hermes-auto-routing` usa el hook oficial
`pre_gateway_dispatch`. Solo fija un perfil cuando una única regla
determinista coincide. Las preguntas genéricas, las coincidencias ambiguas y
los perfiles ya asignados permanecen en el perfil actual (`default`). El
plugin no recibe ni persiste credenciales, cookies o historial completo.

Ejemplos:

- diagnóstico de logs o errores → `researcher`;
- cambio o revisión inequívoca de código/configuración → `engineer`;
- cualquier otro mensaje → `default`.

La escalada condicional `researcher → engineer` todavía debe ejecutarse como
un job tipado del control plane: `engineer` solo se crea si el investigador
marca un posible defecto del sistema. No se debe llamar a ambos perfiles por
defecto.

## Comprobaciones locales

En el harness:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src scripts
```

En el plugin:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy
/opt/hermes/bin/hermes plugins doctor . --ci
```

## Estado y consultas

La base de datos de observabilidad debe estar en un directorio local privado.
Las consultas están limitadas a 200 eventos por página. Las exportaciones son
manuales, sanitizadas y se guardan en `var/exports/` con permisos `0600`.

```bash
hermes observe health
hermes observe doctor
hermes observe failures --limit 200
hermes observe trace <TRACE_ID> --limit 200
hermes observe diagnose <TRACE_ID>
```

## Incidentes y retención

Marcar un incidente necesita un motivo. Las trazas normales se conservan 30
días y las trazas marcadas como incidentes 180 días.

```bash
hermes observe incident mark <TRACE_ID> --reason "reason"
hermes observe retention run
hermes observe export --trace <TRACE_ID>
hermes observe export --from-date 2026-08-27T00:00:00+00:00 \
  --to-date 2026-08-28T00:00:00+00:00
```

La purga exige primero una vista previa y después la frase exacta que devuelve
esa vista previa. Nunca se expone como herramienta del modelo.

```bash
hermes observe purge preview --trace <TRACE_ID>
hermes observe purge execute --trace <TRACE_ID> \
  --preview-digest <DIGEST> \
  --confirm 'PURGE <DIGEST> EVENTS <COUNT>'
```

## Fallos esperados

- Si falla una escritura normal, la operación continúa y el contador de pérdida
  aparece en `health`.
- Si falla una auditoría crítica, la operación con cambio externo se bloquea.
- La explicación usa `gpt-5.6-luna` con `xhigh`; si la llamada falla o la
  respuesta estructurada no supera la validación, se reintenta la misma
  explicación con `gpt-5.6-terra`, también con `xhigh`.
- Si Luna y Terra fallan, se devuelve el diagnóstico determinista.
- Si el estado externo cambió antes de verificarlo, el trabajo termina como
  fallido y no se repite automáticamente una mutación.

## Instalación preparada

La instalación debe usar un commit Git de 40 caracteres y quedar desactivada
hasta comprobar la versión en cada perfil. No se guardan credenciales ni se
copian cookies durante este paso.
