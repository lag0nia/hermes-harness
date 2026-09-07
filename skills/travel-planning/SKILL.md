---
name: travel-planning
description: Planifica viajes read-only con supuestos explícitos y citas.
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

## Peticiones generales y datos incompletos

No hagas un cuestionario antes de una búsqueda general. Extrae los datos disponibles
y continúa si hay suficiente información para comparar opciones. Completa lo que falte
con supuestos conservadores, indícalos en la respuesta y ofrece alternativas cuando
el dato pueda cambiar mucho el resultado.

Usa las preferencias guardadas del perfil cuando sean pertinentes y no contradigan la
petición. Pregunta solo si el dato es imprescindible para producir una búsqueda útil,
o si el usuario solicita reservar, pagar, iniciar sesión o introducir datos personales.

## Procedimiento
1. Extrae viajeros, origen, destino, periodo, presupuesto y restricciones; marca lo que sea supuesto.
2. Usa `plan_trip`, `search_flights` o `search_stays` según intención.
3. Compara opciones sin reservar y conserva proveedor y timestamp.
4. Presenta enlaces, supuestos, exclusiones, equipaje y volatilidad.
5. Para una futura reserva, devuelve handoff a Browser Operator y confirmación exacta.

## Verificación
Confirma que no hubo mutación externa y que cada opción tiene fuente y limitaciones.
