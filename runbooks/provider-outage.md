# Runbook de caída de proveedor

Pausa jobs; no cruces de proveedor automáticamente. Reintenta dos veces solo si es transitorio. En cambios atómicos no cambies modelo a mitad: reobserva en checkpoint. Notifica estado bloqueado y reanuda solo cuando Codex esté disponible.
