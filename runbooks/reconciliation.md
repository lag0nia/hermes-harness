# Reconciliación semanal

El job de reconciliación se programa según la configuración de despliegue y la zona horaria configurada. Consume únicamente eventos verificados, recompila packs, valida enlaces, hashes, staleness y contradicciones, y emite propuestas de memoria.

La política es de continuidad y no-borrado: no elimina sesiones, conversaciones, memorias ni fuentes. Screenshots siguen siendo efímeras según el runbook de recuperación.
