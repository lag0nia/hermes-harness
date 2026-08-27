---
name: travel-planning
description: Planifica viajes read-only con datos completos y citas.
version: 0.1.0
author: Hermes Harness contributors, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [harness, orchestration, safety]
    related_skills: []
---

# Travel Planning

## Cuándo usarlo
Para `travel.plan`, `travel.search_flights` y `travel.search_stays`.

## Preguntas obligatorias
Viajeros, origen, destino, fechas, presupuesto, flexibilidad, equipaje, alojamiento y restricciones. No uses preferencias personales guardadas.

## Procedimiento
1. Valida que no falten preguntas obligatorias.
2. Usa `plan_trip`, `search_flights` o `search_stays` según intención.
3. Compara opciones sin reservar y conserva proveedor y timestamp.
4. Presenta enlaces, supuestos, exclusiones, equipaje y volatilidad.
5. Para una futura reserva, devuelve handoff a Browser Operator y confirmación exacta.

## Verificación
Confirma que no hubo mutación externa y que cada opción tiene fuente y limitaciones.
