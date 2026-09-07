# Hermes v0.21 Native Migration Implementation Plan

> **For Hermes:** Execute this plan in small, independently verified tasks. Do not perform a production update, restart, plugin enablement, profile deletion, credential migration, or Desktop installation without explicit approval at that phase.

**Goal:** Upgrade the Pi gateway and macOS Hermes Desktop to Hermes v0.21, then replace the fragile custom coordination paths with v0.21-native Bots, Kanban, cron, multi-connection Desktop, and profile-routing APIs while preserving deterministic conservative routing, explicit approvals, privacy, and the Travel Planner Bot.

**Architecture:** Hermes v0.21 becomes the system of record for profile/Bot identity, Bot Chats, Kanban jobs/dependencies, worker dispatch, cron, and Desktop multi-connection. The three custom repositories remain only for narrow domain concerns: Pi-Tou MCP, policy/admission, privacy-preserving observability, and an optional per-message routing advisor. The Pi remains the only control plane; the Mac Desktop is a remote client, not a `hermes peer`. The documented v0.21 `pre_gateway_dispatch` hook cannot select a destination profile, so automatic semantic profile redirection remains disabled until Hermes exposes a supported routing primitive or an equally safe ingress boundary is verified.

**Tech Stack:** Hermes Agent v2026.8.31 (v0.21), Docker/Compose on the Pi host, Hermes Desktop on macOS, Python 3.13, uv, Pydantic 2, SQLite WAL, Hermes native plugins/MCP/Kanban/cron/profile APIs, Hermes Desktop Plugin SDK, pytest, Ruff, mypy, Node syntax checks, Git.

---

## 1. Non-negotiable decisions

1. Pin the Pi image to `nousresearch/hermes-agent:v2026.8.31@sha256:64923faeae267792bf9bf87fe3b4c4869e35004e360c7df01730ad801b74d524`; never deploy a rolling `latest` tag.
2. The gateway is Docker-managed and has been updated to v0.21.0 only from the Pi host Docker context; future updates follow the same tag-plus-digest workflow.
3. The macOS Desktop is updated in the same release window and must continue to be tested against the Pi over both HTTP and WebSocket after future releases.
4. `default` remains the sole user-facing coordinator and only it may promote work between stages.
5. The native v0.21 Kanban board is authoritative for durable multi-agent work. Bot DMs/groups are notification and clarification surfaces, not workflow state.
6. The native v0.21 scheduler/worker dispatcher replaces the custom in-memory dispatcher and delivery transport. Do not repair those transports as a long-term architecture.
7. Any unaddressed message that enters `default` may receive one minimal, closed-schema routing *proposal* before its conversational turn. Generic, ambiguous, malformed, unsupported, commercial, internal, or pre-routed messages remain in `default`. A user opening a Bot directly bypasses this classifier. Do not automatically change `event.source.profile`: v0.21 documents only `skip`, `rewrite`, and `allow` hook directives, not profile redirection.
8. `Travel Planner` stays as a dedicated read-only Bot and is an eligible automatic destination only for an unequivocal travel-planning request. It never books, pays, logs in, or submits on the user's behalf.
9. `coder` is removed with the native `hermes profile delete coder` command after all source routes have been redirected to `engineer`; no archive is retained by explicit user decision.
10. `researcher` absorbs the architecture and planning role; its durable development handoff is `researcher` (research + design + plan) → `engineer` (implementation + tests). `architect-planner` is retired only after canaries verify that replacement.
11. `documentator` remains a separate, dormant Bot until verified durable `ChangeEvent` and delivery semantics exist. Do not merge it during this migration.
12. No custom `harness_submit` full execution MCP endpoint may be exposed until phase, confirmation, target-profile, and durable-state defects are fixed and tested.
13. No commercial action, payment, order submission, booking, or credential entry is enabled by this migration.

---

## 2. Current verified baseline

| Item | Verified state |
|---|---|
| Pi runtime | Hermes `v0.21.0 (2026.8.31)`, Docker install, default gateway running, pinned tag+digest |
| Target | Hermes `v2026.8.31` / v0.21; ARM64 digest `sha256:64923faeae267792bf9bf87fe3b4c4869e35004e360c7df01730ad801b74d524` |
| Pi resources | ~1.8 GiB available RAM, 36 GiB free disk; avoid simultaneous duplicated gateways unless explicitly capacity-tested |
| Effective default runtime | only `hermes-observability` plugin and `pi-tou-repair` MCP currently discovered |
| Auto-router | source quality green but active runtime deployment is absent/drifted; keep disabled during core upgrade |
| Harness MCP bridge | source exists but is not effectively registered; do not enable until remediation tasks pass |
| Current cron | one no-agent observability review job; recent runs succeeded after historic blocked attempts |
| Desktop | Updated in the same release window; future release validation must cover the remote Pi over HTTP and WebSocket |
| Repositories | all clean on `feat/observability-v1`; harness 154 tests, observability 95 tests, auto-router 36 tests; Ruff/mypy green |

**Known source blockers before feature activation:**

- `src/hermes_harness/observability_bridge.py:86-125` permits `full` submissions without the configured phase/confirmation gate.
- `src/hermes_harness/control_plane/policy.py:97-112` validates origin/requested profile rather than the routed destination.
- `src/hermes_harness/dispatcher.py:97-100`, `:216-262` retains execution state in memory and does not persist worker completion transitions.
- `src/hermes_harness/integrations/hermes_kanban.py:35-123` cannot query/read-back/reconcile exact native Kanban tasks.
- `scripts/replay_routing.py:52-67` compares the classifier to itself and computes no real policy violations.
- `plugin-src/hermes-auto-routing/src/hermes_auto_routing/router.py:333-360` mutates `source.profile` pre-authorization and returns `action: allow`.
- `plugin-src/hermes-observability/desktop/plugin.js:6-41`, `:71-74` uses a private Desktop bridge and unscoped cache keys.
- `plugin-src/hermes-observability/src/hermes_observability/sanitizer.py:24-49` needs URL userinfo and bearer/auth-form redaction before v0.21 production use.
- `plugin-src/hermes-observability/src/hermes_observability/storage.py:1024-1053` and `maintenance.py:82-97` need transactionally complete retention/deletion behavior.

---

# Phase A — Immutable recovery point and host admission

### Task 1: Discover the actual Pi Docker deployment

**Objective:** Identify the exact host service, Compose file, image reference, mounts, port mapping, network, restart policy, and data volumes before any update.

**Files:** No repository changes. Record the sanitized result in the operational change record only after user approval.

**Steps:**

1. On the Pi host, locate the container and deployment manifest:
   ```bash
   docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
   docker inspect <container-name>
   docker compose ls
   ```
2. Inspect the rendered deployment without printing environment values:
   ```bash
   docker compose -f <compose-file> config
   docker inspect <container-name> --format '{{json .Mounts}}'
   ```
3. Confirm that the default profile home has exactly one writer and that no second Hermes gateway is attached to the same state directory.
4. Confirm the container uses the expected Pi data mount and uses a stable image tag rather than `latest`.

**Acceptance:** The exact host deployment path, container/service name, mounted data location, current image digest, and restart command are known. No secret values are printed.

**Gate A1:** Requires explicit user approval before snapshot or image pull.

### Task 2: Create and verify a rollback snapshot

**Objective:** Create a restorable, private snapshot before changing the container image or profile/configuration state.

**Files:** Host-managed backup location only; do not copy secrets into repositories.

**Steps:**

1. Stop or quiesce writes only if the chosen snapshot method requires it; otherwise use the host filesystem/volume snapshot facility.
2. Include the Hermes data mount containing:
   - profile homes, session databases and WAL files;
   - `auth.json` and `.env` files;
   - cron state;
   - Kanban database;
   - observability/control-plane databases;
   - installed plugins and Desktop-independent configuration.
3. Generate a manifest containing paths, byte sizes, permissions, timestamp, and checksums, but never values of credentials.
4. Validate the backup is readable and has restrictive permissions.
5. Record the current image digest and the full current `hermes --version` output as rollback metadata.

**Acceptance:** A named snapshot exists, verifies cleanly, and can be restored independently of the running container.

**Gate A2:** Do not update without verified snapshot and known rollback command.

### Task 3: Capture a release baseline

**Objective:** Collect pre-update behavior that later proves whether v0.21 changed configuration, routing, integrations, or safety behavior.

**Files:** Create an ignored/sanitized operational report outside the three source repositories, or attach it to the approved change record.

**Commands:**

```bash
hermes --version
hermes status --all
hermes doctor
hermes security audit
hermes profile list
hermes plugins list --plain --no-bundled
hermes mcp list
hermes cron list
hermes cron runs --limit 20
hermes kanban boards list
hermes kanban list
hermes observe health
hermes observe failures --limit 200
```

**Acceptance:** Results distinguish “works now”, “configured but not active”, and “requires post-update testing”. No logs containing raw prompts, cookies, tokens, or request bodies are exported.

---

# Phase B — Hermes v0.21 core and Desktop upgrade

### Task 4: Prove the pinned ARM64 image before production replacement

**Objective:** Verify that the target image is the expected v0.21 artifact and supports the Pi architecture.

**Files:** Host Compose manifest only, after explicit approval.

**Steps:**

1. Pull the pinned image, never the rolling tag:
   ```bash
   docker pull nousresearch/hermes-agent:v2026.8.31
   docker image inspect nousresearch/hermes-agent:v2026.8.31
   ```
2. Verify the resolved digest is the approved ARM64 digest.
3. Run a one-shot version check against the image when the Compose/container layout permits it:
   ```bash
   docker run --rm --entrypoint hermes nousresearch/hermes-agent:v2026.8.31 --version
   ```
4. Do not attach this one-shot validation container to production data volumes.

**Acceptance:** Target image version and architecture are verified before replacement.

### Task 5: Upgrade the Pi gateway with no feature promotion

**Objective:** Replace the v0.20.5 container with the pinned v0.21 image while preserving the existing data mount and external connectivity.

**Files:** Modify only the discovered host Compose/image declaration. Do not change source repositories in this task.

**Steps:**

1. Change the Compose image reference to:
   ```yaml
   image: nousresearch/hermes-agent:v2026.8.31
   ```
2. Render Compose again and compare mounts, ports, networks, and environment key names against Task 1.
3. Pull and recreate only the Hermes service:
   ```bash
   docker compose -f <compose-file> pull <service-name>
   docker compose -f <compose-file> up -d --force-recreate <service-name>
   ```
4. Do not run `docker compose down -v`.
5. Wait for health/log readiness using the exact service/container identity discovered in Task 1.

**Acceptance:** Exactly one expected default gateway is running on v0.21 against the existing data mount.

**Rollback:** Restore the previous pinned image and snapshot only if the live verification in Task 6 fails or the migration mutates state incompatibly.

### Task 6: Verify v0.21 core before enabling custom features

**Objective:** Confirm that v0.21 preserves base profile/session/configuration state and that the upgrade did not silently widen capability or ingress scope.

**Commands:**

```bash
hermes --version
hermes status --all
hermes doctor
hermes security audit
hermes config check
hermes profile list
hermes plugins list --plain --no-bundled
hermes mcp list
hermes cron list
hermes kanban boards list
hermes observe health
```

**Required checks:**

1. Verify no config migration error, crash loop, malformed profile, missing data directory, or duplicate gateway writer.
2. Verify the external API still requires authentication and remains restricted to the intended Tailscale/VPN perimeter.
3. Verify Pi-Tou MCP still discovers only its approved default tool subset.
4. Verify Telegram remains allowlisted and does not gain new toolsets unexpectedly.
5. Re-run security audit; compare package findings rather than assuming the new image fixed them.
6. Keep `hermes-auto-routing`, `harness_submit`, and any unverified observability “Fix now” path inactive.

**Acceptance:** Core v0.21 is healthy while legacy custom promotion paths remain disabled.

### Task 7: Update Hermes Desktop on macOS and validate the remote Pi

**Objective:** Upgrade the local macOS Desktop application so Bot Mode, multi-connection behavior, and public plugin SDK compatibility match the Pi v0.21 gateway.

**Files:** macOS Hermes Desktop application and local Desktop plugin directory only; do not assume Pi-side plugin installation copies UI code to the Mac.

**Steps:**

1. Record the current Desktop app version and its registered remote gateway connection name/URL; do not print the session token.
2. Install the matching current Hermes Desktop release through the official Desktop update/install path.
3. Open **Settings → Gateways** and confirm the Pi remote gateway remains registered.
4. Use the built-in **Test** action. Require both HTTP and WebSocket success.
5. Confirm the Pi’s profile roster appears in Bot Mode and that canonical chats/sessions remain visible.
6. Confirm no connection is accidentally made primary if it should remain a remote-only entry.
7. Test one read-only prompt to `default`, one existing session resume, and one Bot view. Do not create jobs, alter calendars, or submit browser actions.

**Acceptance:** The upgraded Desktop can read and use the Pi v0.21 backend without losing sessions or silently switching sources.

---

# Phase C — Native v0.21 coordination migration

### Task 8: Define the v0.21-native source-of-truth boundary

**Objective:** Replace custom orchestration ownership with a documented, testable boundary around native Bot, Kanban, cron, and Desktop primitives.

**Files:**

- Modify: `architecture/system.md`
- Modify: `README.md`
- Modify: `config/routing.yaml`
- Modify: `capabilities/agents/default.yaml`
- Create: `contracts/v021-workflow-envelope.schema.json`
- Create: `tests/contracts/test_v021_workflow_envelope.py`

**Step 1: Write failing contract tests**

Require a closed `workflow-envelope-2.0.0` with, at minimum:

```yaml
schema_version: workflow-envelope-2.0.0
trace_id: UUID
job_id: UUID
idempotency_key: string
origin:
  connection_id: string
  profile: default
  session_id: string
target:
  profile: researcher | architect-planner | engineer | browser-operator | travel-planner
  intent: string
policy:
  phase: shadow | read_only | confirmed
  risk_class: string
  model_policy: object
dependencies: []
delivery:
  kanban_task_id: string | null
  bot_chat_id: string | null
```

Tests must reject raw prompt/body/cookie/header fields, an unknown profile, a missing source identity, a destination that is not allowed for the requested intent, or an external side effect without a valid confirmation reference.

**Step 2: Implement the minimal versioned envelope and policy boundary**

Do not implement a parallel dispatcher. The envelope is an admission/audit contract that maps to a native Kanban task or a native profile call.

**Step 3: Document authoritative state**

Document this rule in `architecture/system.md`:

```text
Native Hermes Kanban task + native task links = workflow authority.
The harness may observe/admit/reconcile; it must not shadow-write an independent execution state machine.
```

**Verification:**

```bash
uv run pytest tests/contracts/test_v021_workflow_envelope.py -q
uv run ruff check .
uv run mypy src scripts
```

### Task 9: Move the custom bridge to admission-only mode

**Objective:** Remove the ability of the harness bridge to bypass phases, confirmations, native destination validation, or worker durability.

**Files:**

- Modify: `src/hermes_harness/observability_bridge.py:86-125`
- Modify: `src/hermes_harness/control_plane/phase_policy.py:65-87`
- Modify: `src/hermes_harness/control_plane/policy.py:73-112`
- Modify: `src/hermes_harness/runtime_mcp.py:18-36`
- Modify: `tests/observability/test_bridge.py`
- Modify: `tests/observability/test_full_scope.py`
- Create: `tests/policy/test_destination_admission.py`

**Step 1: Write failing tests**

Add tests that prove:

1. `mode=full` cannot bypass `initial_phase: shadow`.
2. a policy-required confirmation needs a matching single-use grant.
3. policy is evaluated after route resolution, against the actual target profile.
4. an unavailable/non-served target profile is blocked before dispatch.
5. bridge responses report `planned`/`admitted`/`queued` accurately; queue acknowledgement is not completion.

**Step 2: Implement minimal admission behavior**

- Load `config/phase-policy.yaml` at runtime.
- Resolve the native target route before policy evaluation.
- Delete or permanently gate `harness_submit` until it has a valid native Kanban/worker adapter.
- Keep read-only planning as the only initially available bridge action.

**Step 3: Verify**

```bash
uv run pytest tests/observability/test_bridge.py tests/observability/test_full_scope.py tests/policy/test_destination_admission.py -q
uv run pytest tests/policy/test_policy.py tests/policy/test_phase_policy.py tests/confirmations/test_confirmations.py -q
```

### Task 10: Replace custom dispatch/delivery ownership with native Kanban

**Objective:** Stop treating the harness ledger, custom dispatcher, and in-memory delivery state as the execution authority.

**Files:**

- Modify: `src/hermes_harness/dispatcher.py`
- Modify: `src/hermes_harness/integrations/hermes_kanban.py`
- Modify: `src/hermes_harness/delivery.py`
- Modify: `src/hermes_harness/observability_bridge.py:242-253`
- Modify: `src/hermes_harness/control_plane/ledger.py`
- Modify: `tests/dispatcher/test_idempotency.py`
- Modify: `tests/integration/test_kanban_dispatch.py`
- Modify: `tests/integration/test_delivery.py`
- Create: `tests/integration/test_native_kanban_reconciliation.py`

**Step 1: Write failing tests**

Cover these cases:

1. native task creation is idempotent by `idempotency_key`;
2. task is read back after create and its assigned profile/status/dependencies match the envelope;
3. native completion/block/retry transitions update only observational projections, not a competing state machine;
4. a restart reconciles from native Kanban task/link/comment state;
5. delivery receipts distinguish queued, accepted, running, completed, failed, and unknown;
6. a direct tool without an executor returns `not_implemented`, never success.

**Step 2: Implement the thin adapter**

The adapter may create/query/comment/read native tasks with bounded timeout/retry, but cannot infer a task result from stdout parsing alone. It must read back exact native state before acknowledging.

**Step 3: Remove redundant in-memory behavior**

Deprecate in-memory event sequence/activity/delivery claims in favor of native task IDs, native event cursors, and durable idempotency records.

**Verification:**

```bash
uv run pytest tests/dispatcher/test_idempotency.py tests/integration/test_kanban_dispatch.py tests/integration/test_native_kanban_reconciliation.py tests/integration/test_delivery.py -q
```

### Task 11: Replace the vacuous replay gate with v0.21 compatibility replay

**Objective:** Make replay detect actual route, event, profile, and delivery regressions across v0.20.5 and v0.21.

**Files:**

- Modify: `scripts/replay_routing.py:41-67`
- Modify: `tests/replay/test_replay.py`
- Create: `fixtures/replay/v021-routing-expectations.jsonl`
- Create: `fixtures/replay/v021-events.jsonl`
- Create: `tests/replay/test_v021_resume.py`

**Step 1: Write independent expected fixtures**

Include at minimum:

- generic request → default;
- ambiguous request → default;
- unique technical research → researcher;
- explicit profile already assigned → unchanged;
- Bot Chat origin → unchanged unless explicitly eligible;
- cron/internal origin → unchanged;
- unsupported profile → blocked/default;
- Kanban dependency resume after restart;
- unknown event version → explicit failure.

**Step 2: Implement real comparison**

Compare candidate output to versioned expected output, compute actual policy violations, preserve input event IDs/cursors, and emit a machine-readable report with `has_more`/cursor semantics.

**Verification:**

```bash
uv run pytest tests/replay -q
uv run python scripts/replay_routing.py fixtures/replay/v021-routing-expectations.jsonl --log /tmp/hermes-v021-replay.jsonl
```

---

# Phase D — Conservative routing and Desktop composer control

### Task 12: Rebuild auto-routing as a shadow/advisory plugin

**Objective:** Preserve deterministic conservative route proposals without pre-authorisation profile mutation, hook short-circuiting, or an undocumented attempt to redirect a profile.

**Files:**

- Modify: `/opt/data/plugin-src/hermes-auto-routing/src/hermes_auto_routing/router.py:27-360`
- Modify: `/opt/data/plugin-src/hermes-auto-routing/tests/test_router.py`
- Modify: `/opt/data/plugin-src/hermes-auto-routing/tests/test_plugin.py`
- Create: `/opt/data/plugin-src/hermes-auto-routing/tests/test_v021_host_contract.py`
- Modify: `/opt/data/plugin-src/hermes-auto-routing/README.md`

**Step 1: Write failing negative-routing tests**

Require these to remain in `default`:

```text
"Investiga los errores del examen"
"Configura el sistema de pagos"
"Crea un sistema de turnos"
"documentación del viaje"
```

Require a specialist only for an explicit technical object plus a high-signal action, for example:

```text
"Analiza los logs del gateway Hermes y enumera los errores MCP"
```

**Step 2: Implement a pure classifier**

`classify_message()` returns a structured proposal only:

```python
RouteDecision(
    disposition=DEFAULT | AMBIGUOUS | CANDIDATE,
    profile=None | "researcher" | "engineer" | ...,
    intent=None | "technical.research" | ...,
    reason_code="...",
)
```

It must not mutate a gateway event.

**Step 3: Add a guarded gateway adapter**

The verified v0.21 public hook contract has no route-selection action: `pre_gateway_dispatch` supports only `skip`, `rewrite`, and `allow`. Until a supported route-selection API is released and contract-tested, the adapter is shadow/advisory only and must:

1. honor an existing native/Bot/peer/cron profile stamp;
2. validate target against served profiles and effective allowlist;
3. leave unknown or unavailable targets unchanged;
4. return `None`, not `action: allow`, after a valid advisory decision;
5. record only sanitized reason codes and IDs;
6. never rewrite user text into an implicit profile command and never mutate `event.source.profile`.

**Step 4: Test multi-hook and origin behavior**

Test that the router does not suppress later policy hooks and does not route Bot, group, peer, cron, A2A, or internal events unless a future explicit origin policy enables them.

**Verification:**

```bash
cd /opt/data/plugin-src/hermes-auto-routing
uv run pytest -q
uv run ruff check .
uv run mypy
hermes plugins doctor . --ci
```

### Task 13: Spike and build the per-message Composer routing selector

**Objective:** Add a safe Desktop control that selects routing behavior per message instead of toggling global plugin/configuration state.

**Files:**

- Create: `/opt/data/plugin-src/hermes-auto-routing/desktop/plugin.js`
- Create: `/opt/data/plugin-src/hermes-auto-routing/tests/test_desktop_plugin_contract.py`
- Create: `/opt/data/plugin-src/hermes-auto-routing/docs/composer-routing.md`
- Modify: `/opt/data/plugin-src/hermes-auto-routing/plugin.yaml` only if v0.21’s official plugin contract requires Desktop metadata

**Step 1: Architecture spike before implementation**

On an updated macOS Desktop connected to staging, verify the supported v0.21 composer contribution and per-message metadata contract. Use public SDK APIs only:

```text
COMPOSER_AREAS
host.profileRoutes()
host.requestProfile(route, method, params)
host.onEvent(...)
```

**Do not** encode invisible freeform prompt instructions, mutate `config.yaml`, or use private `window.hermesDesktop` bridges.

**Step 2: Write static/API-contract tests**

Require that the plugin:

- imports only `@hermes/plugin-sdk` and React runtime primitives allowed by the SDK;
- feature-detects public APIs;
- does not access `window.hermesDesktop`;
- scopes UI state by connection/profile/session;
- fails closed to `Direct` when the metadata/API contract is unavailable.

**Step 3: Implement the selector**

Expose exactly three immediately safe modes, plus one blocked future mode:

```text
Direct      → default only
Suggest     → classify and show a proposal; user decides
Workflow    → default creates a typed native Kanban workflow
Auto-safe   → unavailable until Hermes publishes and we verify a supported profile-route API
```

The user can request a mode, but cannot force an arbitrary target profile or bypass policy/confirmation.

**Step 4: Live Desktop verification**

Test against the Pi staging gateway:

1. `Direct` leaves an explicit technical prompt in default.
2. `Suggest` presents a proposal but does not dispatch before user selection.
3. `Auto-safe` is visibly unavailable rather than emulating a route through prompt rewriting or source mutation.
4. Ambiguous and nontechnical negatives remain in default.
5. `Workflow` creates a native read-only Kanban task with trace/job IDs.
6. Disconnect/reconnect and switch connection/profile; ensure no stale proposal/cache crosses sources.

---

# Phase E — Observability v0.21 compatibility and privacy

### Task 14: Migrate the Desktop observability plugin to public multi-connection APIs

**Objective:** Ensure ticket reads, mutations, cache entries, and UI state target the exact `(connectionId, profile)` instead of ambient active gateway state.

**Files:**

- Modify: `/opt/data/plugin-src/hermes-observability/desktop/plugin.js:6-41`
- Modify: `/opt/data/plugin-src/hermes-observability/tests/plugin/test_desktop_plugin.py`
- Create: `/opt/data/plugin-src/hermes-observability/tests/plugin/test_multi_connection_desktop.py`

**Step 1: Write failing tests**

Require queries to have cache keys equivalent to:

```javascript
['hermes-observability', 'review-tickets', connectionId, profile]
```

Require all profile-targeted requests to use `host.profileRoutes()` and `host.requestProfile(route, ...)`, with an explicit legacy single-source fallback only when public APIs are absent.

**Step 2: Implement the smallest public-SDK migration**

- Do not access `window.hermesDesktop`.
- Ensure/warm the target agent only through supported SDK surfaces when required.
- Use `host.onEvent` or supported socket replay as an accelerator, retaining bounded polling as fallback.
- Invalidate only the matching connection/profile cache after an event.

**Step 3: Verify Desktop behavior**

```bash
cd /opt/data/plugin-src/hermes-observability
node --check desktop/plugin.js
uv run pytest -q tests/plugin/test_desktop_plugin.py tests/plugin/test_multi_connection_desktop.py
```

### Task 15: Repair observability privacy, retention, and actual completion semantics

**Objective:** Make observability safe before it can send or display review/fix information on v0.21.

**Files:**

- Modify: `/opt/data/plugin-src/hermes-observability/src/hermes_observability/sanitizer.py:24-49`
- Modify: `/opt/data/plugin-src/hermes-observability/src/hermes_observability/dashboard/plugin_api.py:43-89`
- Modify: `/opt/data/plugin-src/hermes-observability/src/hermes_observability/review_contracts.py:299-326`
- Modify: `/opt/data/plugin-src/hermes-observability/src/hermes_observability/storage.py:1024-1053`
- Modify: `/opt/data/plugin-src/hermes-observability/src/hermes_observability/maintenance.py:82-97`
- Create: `/opt/data/plugin-src/hermes-observability/tests/privacy/test_auth_redaction.py`
- Create: `/opt/data/plugin-src/hermes-observability/tests/maintenance/test_review_retention_integrity.py`
- Create: `/opt/data/plugin-src/hermes-observability/tests/api/test_v021_dispatch_state.py`

**Step 1: Write failing privacy tests**

Seed URL userinfo, URL fragments, bearer/basic authorization values, cookies, structured tokens, and exception messages. Assert that none can persist in SQLite, WAL, export, FixDispatch, or Desktop response.

**Step 2: Write retention-integrity tests**

Create real ticket/event links, then test ticket deletion and expired-event retention. Require a transactionally complete cascade, archival policy, or soft deletion—never an `IntegrityError`.

**Step 3: Write completion-state tests**

Require exact states:

```text
queued → delivered → accepted → running → completed | failed | delivery_unknown
```

A queued RPC acknowledgement is not a success toast. Dispatch must carry an explicit native route/profile, request ID, idempotency key, session/job ID, read-only semantics, and sanitized failure state.

**Step 4: Implement and verify**

```bash
cd /opt/data/plugin-src/hermes-observability
uv run pytest -q tests/privacy tests/maintenance tests/api/test_v021_dispatch_state.py
uv run pytest -q
uv run ruff check .
uv run mypy
```

### Task 16: Deploy one immutable observability artifact per intended profile

**Objective:** Eliminate drift, especially the stale `engineer` copy, before enabling the plugin in any v0.21 profile.

**Files:** Profile plugin installation only; no manual copy/paste between profile directories.

**Steps:**

1. Verify source artifact test suite and record full source commit SHA.
2. Install the same exact immutable artifact only in the profiles that require it, initially `default` in staging.
3. Compare hashes for backend and Desktop assets before enablement.
4. Run plugin schema/migration checks on the target profile data copy before opening it against production data.
5. Do not install the plugin into every profile by default; add it only with a documented capability need.

**Acceptance:** No detached/dirty profile plugin copy, no schema mismatch, and no non-default UI code implicitly assumed to run on macOS.

---

# Phase F — Profile and capability simplification

### Task 17: Make `default` an explicit coordinator

**Objective:** Give the only user-facing profile a durable, testable ownership contract.

**Files:**

- Modify: `/opt/data/SOUL.md`
- Modify: `capabilities/agents/default.yaml`
- Modify: `architecture/system.md`
- Modify: `tests/documentation/test_skills_and_souls.py`
- Modify: `scripts/compile_knowledge_packs.py`
- Modify: `knowledge/generated/manifest.json` through its existing generation command

**Required coordinator rules:**

- never executes a specialist mutation by textual request alone;
- owns workflow creation, admission, promotion, cancellation, final synthesis, and memory proposals;
- treats specialist output as evidence, not authority, until verification passes;
- keeps generic/ambiguous requests local;
- requires exact user confirmation for external/actionable effects;
- preserves Travel Planner as explicit read-only Bot, never auto-routed.

**Verification:**

```bash
uv run pytest tests/documentation/test_skills_and_souls.py -q
uv run python scripts/compile_knowledge_packs.py --check
```

### Task 18: Consolidate `coder` into `engineer` safely

**Objective:** Remove duplicate coding routing while preserving workspace boundaries.

**Files:**

- Modify: `/opt/data/profiles/engineer/SOUL.md`
- Modify: `/opt/data/profiles/engineer/config.yaml`
- Modify: `capabilities/agents/engineer.yaml`
- Modify: `config/routing.yaml:20-25`
- Create: `config/workspace-scope-policy.yaml`
- Create: `tests/policy/test_workspace_scope_policy.py`
- Modify: `tests/routing/test_router.py`

**Step 1: Define scopes**

```yaml
hermes-core:
  allowed_roots:
    - /opt/data/hermes-harness
    - /opt/data/plugin-src/hermes-observability
    - /opt/data/plugin-src/hermes-auto-routing
external-project:
  allowed_roots: []  # populated only by an explicit task/workspace declaration
```

**Step 2: Write failing tests**

Require that an engineer job cannot access a root outside its envelope scope, and that `code.*` routes resolve to `engineer` with an explicit `workspace_scope` rather than the deprecated `coder` target.

**Step 3: Migrate conservatively**

1. Stop routing new jobs to `coder`.
2. Update all source mappings and tests to route `code.*` to `engineer` before any profile removal.
3. Execute the already approved native `hermes profile delete coder --yes` command and read back the profile list and absent profile directory.
4. Do not create a profile-specific archive; the verified pre-v0.21 full snapshot remains the only emergency recovery point by explicit user decision.

**Acceptance:** Engineer can perform both scoped work classes, but no job acquires broader filesystem/configuration access by the merge.

### Task 19: Preserve Travel Planner and defer Documentator consolidation

**Objective:** Keep Travel Planner as an isolated optional Bot while avoiding premature loss of the documentation integrity boundary.

**Files:**

- Modify: `/opt/data/profiles/travel-planner/SOUL.md` only if v0.21 capability metadata requires it
- Modify: `/opt/data/profiles/travel-planner/config.yaml` only to ensure the three read-only travel MCP tools remain explicit
- Modify: `/opt/data/profiles/documentator/SOUL.md` only for v0.21 delivery contract compatibility
- Modify: `architecture/system.md`

**Rules:**

- Travel Planner remains visible or user-unhidden in Bot Mode, read-only, no payment/booking, and no automatic router target.
- Documentator remains dormant and receives only verified structured `ChangeEvent` data after Task 10 completion; it is not merged in this release.
- Do not duplicate OAuth/auth files manually. Prefer v0.21 supported shared credential pools for any newly created Bot.

**Acceptance:** Simplification removes no desired travel capability and does not weaken canonical documentation ownership.

### Task 20: Align ingress capabilities with profile least privilege

**Objective:** Prevent specialist profile permissions from widening through Telegram/Bot/other platform inheritance.

**Files:**

- Modify: `/opt/data/profiles/*/config.yaml` only after an explicit per-profile capability review
- Create: `tests/policy/test_profile_platform_toolsets.py`
- Modify: `architecture/system.md`

**Step 1: Write the desired matrix**

- `researcher`: read-only web/file/skills.
- `architect-planner`: read-only project/config inspection and planning.
- `engineer`: scoped file/terminal/code tools only.
- `browser-operator`: browser tools and explicit confirmation path; no shell/file escalation without a separate approved job.
- `travel-planner`: only travel read-only MCP tools.
- `documentator`: documentation-scoped tools.

**Step 2: Test each platform**

Ensure Telegram/Bot/CLI toolsets are no broader than the approved profile capability matrix. A stopped profile is not a reason to accept overbroad ingress.

**Acceptance:** Starting a Bot or profile gateway cannot silently grant it default’s terminal, delegation, cron, or sensitive MCP actions.

---

# Phase G — Controlled promotion and release acceptance

### Task 21: Run the v0.21 acceptance matrix in read-only/shadow mode

**Objective:** Validate the complete Pi/Desktop flow before enabling `auto-safe` routing or any full/custom action.

**Test matrix:**

| Scenario | Expected result |
|---|---|
| Desktop → Pi `default` normal chat | session resumes and response streams |
| Bot Mode roster | core profiles plus Travel Planner visible and correctly scoped |
| Desktop gateway test | HTTP and WebSocket both pass |
| Direct composer mode | remains in `default` |
| Suggest composer mode | proposal only; no implicit dispatch |
| Auto-safe unique research input | one validated `researcher` route |
| Auto-safe ambiguous/nontechnical input | remains `default` |
| Workflow request | native read-only Kanban task and linked trace/job identifiers |
| Pi restart during work | native Kanban task reconciles without duplicate job |
| Cron canary | one read-only review run with visible final state |
| Observability UI | correct `(connectionId, profile)` ticket state; no cross-source cache |
| Browser canary | harmless read-only page only; no login, cart, form or payment action |
| Travel Planner | read-only travel request, no booking or payment tool exposure |
| Telegram | allowlist still applies; no widened specialist tools |

**Required commands:**

```bash
# Harness
cd /opt/data/hermes-harness
uv run pytest -q
uv run ruff check .
uv run mypy src scripts

# Auto-router
cd /opt/data/plugin-src/hermes-auto-routing
uv run pytest -q
uv run ruff check .
uv run mypy

# Observability
cd /opt/data/plugin-src/hermes-observability
uv run pytest -q
uv run ruff check .
uv run mypy
node --check desktop/plugin.js
```

**Acceptance:** All suites pass, the live matrix is recorded with sanitized IDs/results, and there are no crash loops, security audit regressions, privacy canary leaks, duplicate tasks, or cross-connection UI errors.

### Task 22: Promote in narrow stages

**Objective:** Avoid turning on every new feature at once.

**Promotion order:**

1. Core v0.21 + Desktop connectivity only.
2. Bot Mode roster and native Kanban read-only tasks.
3. Routing `Direct` and `Suggest` only.
4. `Workflow` for research → planning only.
5. `Auto-safe` for a single explicit `technical.research` class.
6. Engineer dispatch after confirmation/admission/durability gates pass.
7. Observability “Fix now” only after completion/replay and privacy requirements pass.

Each stage requires a stable observation period, review of trace/task outcomes, and explicit user approval. No automatic promotion.

---

## Rollback procedure

1. Disable only the newly promoted routing/feature surface first; do not erase sessions, Kanban tasks, or traces.
2. If core v0.21 is unhealthy, recreate the previous pinned image using the host Compose file.
3. Restore the verified snapshot only if data migration incompatibility is confirmed; never overwrite newer data before preserving a forensic copy.
4. Keep Desktop connected to the last healthy gateway; if necessary, roll Desktop back only through its supported installer/update path.
5. Record cause, trace/task IDs, exact image versions, and affected feature gate in the sanitized incident report.

---

## Explicit approval gates

| Gate | Requires user approval |
|---|---|
| A1 | Docker/Compose discovery beyond read-only inspection if it affects host access |
| A2 | Snapshot creation and storage location |
| B | Pull/recreate the production Pi container |
| C | macOS Hermes Desktop installation/update |
| D | Enabling any custom plugin, MCP server, profile gateway, or routing mode beyond Direct/Suggest |
| E | Hiding/deprecating or deleting a profile; `coder` deletion requires a separate explicit approval |
| F | Any change to Telegram/ingress toolsets, credentials, or API/network perimeter |
| G | Any workflow that can perform a non-read-only side effect |

## Out of scope for this migration

- Adding a second Hermes server or `hermes peer`.
- Creating or deleting Travel Planner.
- Purchases, bookings, checkout, payment, or browser login automation.
- Moving secrets into repositories or displaying credential values.
- Automatic phase promotion, automatic profile deletion, or automatic rollback.
- Rewriting Hermes core itself.
