# Reconciliación semanal

El job de reconciliación se programa los domingos a las 04:00 en `Europe/Madrid`. Consume únicamente eventos verificados, recompila packs, valida enlaces, hashes, staleness y contradicciones, y emite propuestas de memoria.

La política es de continuidad y no-borrado: no elimina sesiones, conversaciones, memorias ni fuentes. Screenshots siguen siendo efímeras según el runbook de recuperación.
