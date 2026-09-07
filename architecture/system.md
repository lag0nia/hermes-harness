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
