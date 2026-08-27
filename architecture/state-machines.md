# Máquinas de estado

Un job sigue `RECEIVED → VALIDATED → CLASSIFIED → DISPATCHED → RUNNING → VERIFYING → SUCCEEDED`; también puede terminar en `NEED_INPUT`, `CANCELLED`, `FAILED` o `PAUSED`.

Cada side effect usa Observe–Decide–Act–Verify–Recover. Una referencia DOM/SOM queda inválida tras mutar estado. Un reintento equivalente es el máximo permitido si la entrega fue no verificable.
