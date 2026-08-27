---
name: risk-classification
description: Clasifica riesgos y exige controles de promoción.
version: 0.1.0
author: Hermes Harness contributors, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [harness, orchestration, safety]
    related_skills: []
---

# Risk Classification

## Matriz
- **R0:** lectura o cambio local reversible, sin side effect externo.
- **R1:** cambios con dependencias, permisos, persistencia o impacto operativo limitado.
- **R2:** credenciales, pagos, reservas, promoción de core, borrado destructivo o cambios críticos.

## Lista crítica congelada
Cambios de proveedor/modelo, autorización, rutas Hermes/perfiles, contratos, scheduler concurrente, checkout/pago/reserva, retención/borrado, salud/alertas y promoción a producción son R2.

## Procedimiento
1. Identifica side effects, datos sensibles, reversibilidad y blast radius.
2. Eleva al nivel más alto aplicable; nunca lo rebajes por conveniencia.
3. Aplica gates: pruebas, replay, revisión independiente, checkpoint y confirmación cuando corresponda.
4. Detén ante cambio de digest/estado durante confirmación.

## Verificación
El registro contiene nivel, razones, controles requeridos, aprobador y rollback.
