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
