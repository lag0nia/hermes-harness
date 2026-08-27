# Runbook de rollback

Desactiva dispatch especialista con el kill switch, conserva ledger y sesiones, vuelve a `default` directo y reobserva salud. No borres evidencias ni conocimiento. Revierte al checkpoint anterior y registra un ChangeEvent con causa, alcance y verificación.
