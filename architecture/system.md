# Arquitectura del Hermes Harness

El perfil `default` es la única superficie de usuario. Normaliza mensajes a `IntentEnvelope`; el Control Plane valida, clasifica riesgo y enruta a herramientas directas o a un especialista aislado. El ledger y Kanban conservan estado; los resultados regresan a la sesión de origen.

## Invariantes
- Máximo cinco jobs, cuatro unidades y un navegador vivo.
- Ningún worker escribe memoria privada.
- Toda mutación externa se relee y verifica.
- El proveedor no cambia automáticamente durante una incidencia.

Ver también [agentes](architecture/agents.md), [límites de seguridad](architecture/security-boundaries.md) y [estados](architecture/state-machines.md).
