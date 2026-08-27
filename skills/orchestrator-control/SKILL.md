---
name: orchestrator-control
description: Controla el enrutamiento y la síntesis segura.
version: 0.1.0
author: Hermes Harness contributors, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [harness, orchestration, safety]
    related_skills: []
---

# Orchestrator Control

Normaliza solicitudes en un `IntentEnvelope` cerrado y coordina especialistas sin duplicar autorización del Control Plane.

## Cuándo usarlo
- Mensajes con intención, seguimiento, cancelación o ambigüedad.
- Síntesis de resultados de varios jobs.

## Procedimiento
1. Extrae una sola intención o marca múltiples intenciones explícitamente.
2. Pide solo los campos obligatorios que falten; no inventes defaults sensibles.
3. Valida esquema, riesgo, permisos e idempotencia antes de despachar.
4. Enlaza seguimientos por contexto; pregunta si hay dos jobs plausibles.
5. Resume estado y resultado en español, ocultando IDs internos salvo desambiguación.

## Reglas
`NEED_INPUT` vuelve siempre al orquestador. Las skills describen procedimiento, nunca autorización. Operaciones críticas requieren confirmación exacta.

## Verificación
Comprueba que el envelope es válido, el destinatario es determinista y el resultado tiene estado, supuestos y siguiente paso.
