---
name: technical-architecture-planning
description: Diseña planes técnicos R0, R1 y R2 verificables.
version: 0.1.0
author: Hermes Harness contributors, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [harness, orchestration, safety]
    related_skills: []
---

# Technical Architecture Planning

## Cuándo usarlo
Para cambios de harness, MCP, plugins, skills o integraciones con impacto técnico.

## Clasificación
- **R0:** cambio reversible y acotado; implementación directa, pruebas y ChangeEvent.
- **R1:** dependencias o riesgo operativo; plan del Architect, implementación y pruebas.
- **R2:** cambio crítico; Researcher, Architect, Engineer/Coder, revisión Sol independiente, replay, checkpoint y aprobación.

## Procedimiento
1. Inspecciona contratos, límites y estado actual.
2. Define alcance, no-alcance, dependencias y grafo de ejecución.
3. Documenta riesgos, invariantes, aceptación, observabilidad y rollback.
4. Separa cambios del núcleo concurrente y exige worktree para core.
5. Entrega un plan ejecutable con pruebas primero.

## Verificación
Cada criterio de aceptación tiene una prueba o comprobación reproducible y cada riesgo tiene mitigación y rollback.
