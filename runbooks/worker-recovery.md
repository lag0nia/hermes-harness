# Runbook de recuperación de worker

Heartbeat cada 60 segundos; marca stale tras 5 minutos. Cancela de forma idempotente, libera unidades y elimina screenshots efímeras. Reanuda desde el último checkpoint sin repetir side effects; detecta ciclos y pausa para intervención.
