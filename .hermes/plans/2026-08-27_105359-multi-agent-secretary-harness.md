# Hermes Multi-Agent Secretary Harness Implementation Plan

> **For Hermes:** Implement this plan task-by-task with TDD, isolated worktrees, independent review, checkpoints, and rollback. Do not promote critical changes without user confirmation.

**Goal:** Build a single-interface Hermes secretary that interprets the user's Spanish requests, routes them deterministically to isolated specialist Profiles, enforces typed contracts and permissions, remains responsive during parallel work, and continuously maintains versioned documentation and scoped knowledge packs.

**Architecture:** The `default` profile remains the only user-facing orchestrator. It normalizes natural language into a closed `IntentEnvelope`; a local Control Plane validates that envelope and maps it deterministically to direct tools or a specialist Profile. Specialist work runs through Hermes Kanban workers with per-task reasoning effort, while short direct operations such as calendar and Pi health remain in the orchestrator. Documentation is centralized in this repository and compiled into shared and per-agent read-only knowledge packs.

**Tech Stack:** Python 3.13, `uv`, Pydantic/JSON Schema, SQLite, YAML, Hermes Profiles/Bot Mode, Hermes Kanban, local MCP/plugin integration, pytest, Git worktrees/checkpoints, Mermaid/SVG diagrams, existing Pi-Tou repair/calendar/travel/Uber MCP tools.

---

## 1. Frozen design decisions

### 1.1 User-facing topology

- One user-facing profile: `default`.
- Normal surfaces: Telegram and Hermes Desktop.
- The surfaces use separate sessions in the same profile; shared state lives in the Control Plane ledger, documentation, and orchestrator memory.
- Results return to the originating session.
- Telegram receives additional notifications only for blocked confirmations and critical failures.
- Normal messages show a short job name and state; internal IDs remain hidden unless needed for disambiguation.
- A new message is attached to an active job by context or job ID. If two jobs are plausible, the orchestrator asks which one.

### 1.2 Profiles

Create these Profiles with functional internal names and human-readable Desktop titles:

| Profile | Model | Default effort | Purpose |
|---|---|---:|---|
| `default` | `openai-codex/gpt-5.6-luna` | `medium` | Secretary, intent normalization, calendar, Pi status, coordination |
| `browser-operator` | `openai-codex/gpt-5.6-terra` | `high` | Browser/Uber operations and visual decisions |
| `researcher` | `openai-codex/gpt-5.6-luna` | `medium` | Cited read-only investigation |
| `architect-planner` | `openai-codex/gpt-5.6-luna` | `medium` | Technical plans, dependency graphs, risks, acceptance criteria |
| `engineer` | `openai-codex/gpt-5.6-terra` | `high` | Hermes harness, skills, MCP, plugins, core modifications |
| `coder` | `openai-codex/gpt-5.6-terra` | `high` | General projects outside Hermes; cannot write Hermes/profile paths |
| `documentator` | `openai-codex/gpt-5.6-luna` | `low` | Docs, diagrams, changelog, scoped knowledge packs, memory proposals |
| `travel-planner` | `openai-codex/gpt-5.6-luna` | `medium` | Flight/stay research through existing typed MCP tools |

Escalation rules:

- Luna profiles may rise to `high` for complex work.
- Browser may use Terra `xhigh`; Terra `max` is not a default and requires a policy justification.
- Engineer/Coder may use Terra `xhigh` for complex code.
- Sol is exceptional only: `medium` for independent critical review; `high` for exceptional critical escalation.
- **Sol `max` is prohibited by policy.**
- `*-900k` models may be requested only for Researcher, Engineer, or Coder after an explicit context-size check. Never default to 900k.
- Provider is only `openai-codex`. OpenRouter and other providers are not automatic fallbacks.
- If Codex is unavailable, jobs pause rather than changing provider.

Internal Codex fallback at checkpoints:

- Luna failure on read-only work: retry with Terra at equivalent effort.
- Terra failure on reversible/routine work: Luna `high`.
- Terra failure on critical work: Sol `medium`, exceptionally `high`.
- Sol failure: Terra `high`; pause when the review specifically requires Sol-level independence.
- Never change model in the middle of an atomic side effect. Reobserve state at the next checkpoint.

### 1.3 Auxiliary slots

Configure all auxiliary slots on `openai-codex`:

| Slot | Model/effort |
|---|---|
| compression | Luna `low` |
| vision | Luna `medium` |
| web extract | Luna `low` |
| approval | Luna `medium` |
| title generation | Luna `low` |
| skills hub/search | Luna `low` |
| MCP routing | Luna `medium` |
| triage specifier | Luna `medium` |
| Kanban decomposer | Luna `medium` |
| profile describer | Luna `low` |
| curator | Luna `medium` |

The Browser critical visual auditor is a separate Sol review job, not the general vision slot.

### 1.4 Concurrency and Pi resources

Observed environment during design:

- 4 ARM Cortex-A72 cores.
- Host RAM 3.7 GiB.
- Hermes container cgroup limit 2 GiB.
- Current Hermes-related RSS was roughly 750 MiB before specialist workers.

Scheduler policy:

- Maximum five logical jobs.
- Maximum four capacity units.
- Remote/read-only LLM job: 1 unit.
- Research/Travel multi-search job: 1 unit.
- Documentator: 1 unit.
- Engineer/Coder running tests/build: 2 units.
- Browser with managed Chromium: 3 units.
- Visual auditor: 1 unit.
- Maximum one live browser session.
- Preserve 450–500 MiB cgroup reserve.
- Reduce admissions above 75% cgroup memory or sustained load >2.5.
- Pause non-critical jobs above 85% memory or sustained load >3.5.
- Orchestrator turns, cancellations, and confirmations have priority.
- No global time/step budget while progress is demonstrated.
- Guardrails remain mandatory: heartbeat every 60 seconds, stale worker after 5 minutes, two transient retries, no-op/cycle detection, resource pausing, explicit cancellation.

### 1.5 Memory and documentation

Do not allow workers to independently mutate private `MEMORY.md` stores.

Use four layers:

1. Shared knowledge in `knowledge/shared/`.
2. Agent-scoped read-only packs in `knowledge/agents/<profile>.md`.
3. Job/project state in Control Plane/Kanban/workspaces.
4. Personal/Holographic Memory owned by `default` only.

Documentator consumes verified `CHANGE_EVENT` and `LEARNING_EVENT` records, updates canonical docs, regenerates affected packs, validates contradictions/links, and proposes compact durable facts. The orchestrator probes for contradictions and writes only stable, non-sensitive user/environment facts to Holographic Memory.

Protect conversations, sessions, and memories from automatic deletion. Screenshots are ephemeral and deleted at job completion/failure/cancellation; persist structured redacted logs instead. Keeping a screenshot requires a separate explicit user decision.

Weekly documentation reconciliation: Sunday 04:00 `Europe/Madrid`, plus event-driven updates after verified changes.

### 1.6 Calendar and health

Calendar defaults:

- Timezone: `Europe/Madrid`.
- “Tarea” without time means an all-day VTODO on the stated date.
- An event without a required time becomes all-day; ask only when the requested semantics require a specific time.
- Create without confirmation when unambiguous.
- Modify/delete asks only when destructive or ambiguous.
- Read back the exact VEVENT/VTODO after every write before reporting success.

Pi health:

- On-demand through `pi_health` from any user surface.
- Existing deterministic host watchdog remains no-LLM.
- Check every five minutes.
- Alert by Telegram after two consecutive critical samples, deduplicated by incident fingerprint.
- Essential service-down incidents may alert immediately.
- Send recovery once normal.
- Current host policy remains initially: temperature 70/80 C, memory 90/95%, root disk 80/90%.
- Scheduler separately observes the 2 GiB container cgroup.

### 1.7 Browser and travel

Browser uses the existing managed Chromium/VNC session for Uber Eats and its typed broker tools. The user performs login manually when requested; the agent never types passwords or handles secrets.

Perception/action stack:

1. Service-specific MCP/API when available.
2. Sanitized semantic state/AX/DOM.
3. Screenshot with SOM selectively.
4. Raw pixel coordinates only as fallback.
5. Reobserve and verify after every mutation.

Terra owns the decision. Invoke a Sol visual auditor only before critical actions or when semantic and visual signals conflict.

Confidence calibration starts at:

- Read/reversible exploration: 0.75.
- Local state navigation: 0.85.
- Cart/options: 0.95.
- Persistent submission: 0.97.
- Payment/checkout/reservation: confirmation always plus 0.99 and exact digest match.

A below-threshold action triggers another representation/reobservation, reversible exploration, optional auditor, and finally `NEED_INPUT` through the orchestrator.

No-op policy: one equivalent retry only when delivery was unverifiable; otherwise change strategy or block.

Purchase/reservation confirmation:

- Bound to exact merchant/provider, items/options, amount, destination, and digest.
- A simple “sí” is valid only as a reply to that exact confirmation prompt.
- Expires after 30 minutes.
- Any state/digest change invalidates it immediately and requires a new preview.

Travel v1 is read-only through `plan_trip`, `search_flights`, and `search_stays`. Every travel job asks for travelers, origin, dates, budget, and constraints; no saved personal defaults. Output includes source/provider, timestamp, links, assumptions, exclusions, baggage caveats, and price volatility. Future booking handoff uses Browser Operator and the same confirmation contract.

---

## 2. Repository layout

Create a dedicated Git repository at `/opt/data/hermes-harness`:

```text
/opt/data/hermes-harness/
├── pyproject.toml
├── README.md
├── src/hermes_harness/
│   ├── __init__.py
│   ├── control_plane/
│   │   ├── service.py
│   │   ├── contracts.py
│   │   ├── router.py
│   │   ├── policy.py
│   │   ├── ledger.py
│   │   ├── scheduler.py
│   │   ├── dispatcher.py
│   │   ├── delivery.py
│   │   ├── confirmations.py
│   │   ├── readiness.py
│   │   └── redaction.py
│   ├── integrations/
│   │   ├── hermes_kanban.py
│   │   ├── hermes_profiles.py
│   │   ├── pi_health.py
│   │   └── documentation_events.py
│   └── cli.py
├── contracts/
│   ├── intent-envelope-1.0.0.schema.json
│   ├── job-request-1.0.0.schema.json
│   ├── agent-event-1.0.0.schema.json
│   ├── job-result-1.0.0.schema.json
│   ├── need-input-1.0.0.schema.json
│   ├── confirmation-grant-1.0.0.schema.json
│   ├── change-event-1.0.0.schema.json
│   └── error-1.0.0.schema.json
├── config/
│   ├── routing.yaml
│   ├── model-policy.yaml
│   ├── risk-policy.yaml
│   ├── resource-policy.yaml
│   ├── critical-changes.yaml
│   └── retention-policy.yaml
├── capabilities/agents/
│   ├── default.yaml
│   ├── browser-operator.yaml
│   ├── researcher.yaml
│   ├── architect-planner.yaml
│   ├── engineer.yaml
│   ├── coder.yaml
│   ├── documentator.yaml
│   └── travel-planner.yaml
├── profiles/<profile>/SOUL.md
├── skills/
│   ├── orchestrator-control/SKILL.md
│   ├── technical-architecture-planning/SKILL.md
│   ├── risk-classification/SKILL.md
│   └── travel-planning/SKILL.md
├── knowledge/
│   ├── shared/
│   ├── agents/
│   └── generated/manifest.json
├── architecture/
│   ├── system.md
│   ├── agents.md
│   ├── security-boundaries.md
│   ├── state-machines.md
│   └── diagrams/system.mmd
├── runbooks/
│   ├── rollout.md
│   ├── rollback.md
│   ├── provider-outage.md
│   ├── browser-blocked.md
│   └── worker-recovery.md
├── decisions/
├── changelog/
├── scripts/
│   ├── compile_knowledge_packs.py
│   ├── replay_routing.py
│   ├── readiness_check.py
│   └── verify_permissions.py
└── tests/
    ├── contracts/
    ├── routing/
    ├── policy/
    ├── scheduler/
    ├── dispatcher/
    ├── confirmations/
    ├── replay/
    └── integration/
```

English keys/enums in JSON/YAML contracts; Spanish human-facing documentation and messages.

---

## 3. Contract and state design

### 3.1 Intent catalog v1

Implement closed enum values:

```text
calendar.create_vtodo
calendar.create_event
calendar.update
calendar.delete
calendar.list
pi.health.read
pi.jobs.list
pi.jobs.cancel
browser.research
browser.order.prepare
browser.form.prepare
browser.auth_required
travel.plan
travel.search_flights
travel.search_stays
technical.research
technical.plan
technical.change
technical.review
code.plan
code.change
code.review
docs.reconcile
docs.query
general.answer
general.clarify
```

Luna normalizes user language into this enum. `routing.yaml` maps the valid intent deterministically. Unknown/invalid intent returns `NEED_INPUT`; it never guesses another profile.

### 3.2 Job states

```text
QUEUED → ADMITTED → RUNNING
RUNNING → WAITING_INPUT | WAITING_CONFIRMATION | VERIFYING | BLOCKED
VERIFYING → SUCCEEDED | FAILED_RETRYABLE | FAILED_FINAL | ROLLED_BACK
any non-atomic state → CANCELLED
atomic section + cancel request → VERIFYING → CANCELLED
```

### 3.3 Required identifiers

Every job/event carries:

- `schema_version`
- `job_id`
- optional `parent_job_id`
- `trace_id`
- `origin_profile`
- `origin_session`
- `delivery_target`
- `intent`
- `idempotency_key`
- `risk_class`
- `model_policy`
- `context_references`

Every result carries:

- validated status
- human summary
- structured result
- evidence array
- side-effects array
- verification/read-back
- confidence with grounded signals
- typed error
- artifacts
- documentation impact

Use semantic versioning. Backward-compatible additions are minor versions; breaking changes require a major schema, migration, replay, and coexistence period.

### 3.4 Errors

At minimum:

```text
INVALID_INPUT
UNKNOWN_INTENT
MISSING_REQUIRED_INPUT
AMBIGUOUS_TARGET
CAPABILITY_UNAVAILABLE
PERMISSION_DENIED
CONFIRMATION_REQUIRED
CONFIRMATION_EXPIRED
CONFIRMATION_DIGEST_MISMATCH
AUTHENTICATION_REQUIRED
PROVIDER_UNAVAILABLE
RATE_LIMITED
RESOURCE_PRESSURE
EXTERNAL_STATE_CHANGED
VERIFICATION_FAILED
IDEMPOTENCY_CONFLICT
WORKER_STALE
CYCLE_DETECTED
CANCELLED_BY_USER
ROLLBACK_FAILED
```

---

## 4. Implementation tasks

### Task 1: Bootstrap repository and quality gates

**Files:** create `pyproject.toml`, `README.md`, package skeleton, test skeleton, `.gitignore`.

1. Initialize with `uv` and Python 3.13.
2. Add Pydantic, PyYAML, jsonschema, pytest, pytest-asyncio, hypothesis, and Ruff/mypy as appropriate.
3. Write a smoke test importing `hermes_harness`.
4. Add commands for format, lint, typecheck, unit tests, and full tests.
5. Verify all gates from a clean checkout.
6. Commit the bootstrap.

### Task 2: Implement versioned contracts first

**Files:** `contracts/*.schema.json`, `src/hermes_harness/control_plane/contracts.py`, `tests/contracts/`.

1. Write failing tests for valid and invalid IntentEnvelope, JobRequest, AgentEvent union, JobResult, NeedInput, ConfirmationGrant, ChangeEvent, and typed errors.
2. Add property tests for malformed IDs, unknown enums, oversized text, extra sensitive fields, and schema-version mismatch.
3. Implement models and JSON Schema validation.
4. Add compatibility tests between 1.0.x minor versions.
5. Ensure secrets/password/token/card fields are rejected in events and logs.
6. Commit only after the complete contract suite passes.

### Task 3: Implement deterministic routing and capability manifests

**Files:** `config/routing.yaml`, `capabilities/agents/*.yaml`, `router.py`, `readiness.py`, `tests/routing/`.

1. Encode every intent-to-profile/direct-tool mapping.
2. Encode required skills, allowed tools, model/effort bounds, risk class, and confirmation policy.
3. Make denial the default for unknown intent, missing capability, missing schema, or missing skill/tool.
4. Implement startup readiness checks using tool/skill name and version/hash.
5. Write tests for Spanish paraphrases only at the IntentEnvelope normalization boundary; routing tests consume normalized enums and must be fully deterministic.
6. Add multi-intent splitting and dependency tests.
7. Add a readiness report that never prints secrets.

### Task 4: Implement policy engine

**Files:** `policy.py`, `config/model-policy.yaml`, `risk-policy.yaml`, `critical-changes.yaml`, `retention-policy.yaml`, `tests/policy/`.

1. Enforce `provider == openai-codex`.
2. Enforce Sol effort `<= high` and Sol usage only in allowed review/escalation intents.
3. Enforce 900k allowlist and explicit context-size justification.
4. Enforce critical-change confirmation list:
   - secrets/OAuth/credentials;
   - purchasing/payment confirmation rules;
   - security/permissions;
   - network/API/gateway exposure;
   - root broker;
   - deletion of data/memory/conversations;
   - destructive DB/schema migration;
   - disabling audit/rollback/tests;
   - Sol above high;
   - all-profile changes;
   - conflicted core update/rebase.
5. Preserve conversation/session/memory no-delete invariant.
6. Test policy bypass attempts through nested jobs and modified payloads.

### Task 5: Implement ledger, idempotency, cancellation, and confirmations

**Files:** `ledger.py`, `confirmations.py`, `tests/confirmations/`, `tests/dispatcher/test_idempotency.py`.

1. Create SQLite schema with WAL, migrations, foreign keys, origin/delivery mapping, immutable event log, current-state projection, and Kanban task reference.
2. Implement atomic job creation by idempotency key.
3. Implement state machine transition validation.
4. Implement cancel semantics: immediate outside atomic sections; finish/read-back current atomic action then cancel.
5. Implement confirmation digest over exact operation, target, amount, options, address/destination, and external-state version.
6. Enforce 30-minute expiry and immediate invalidation on digest/state change.
7. Test duplicate Telegram deliveries, process restart, stale confirmation, modified cart, and repeated callback.

### Task 6: Integrate Hermes Kanban as worker execution bus

**Files:** `integrations/hermes_kanban.py`, `dispatcher.py`, `tests/integration/test_kanban_dispatch.py`.

1. Use Kanban for every specialist Profile job; keep direct calendar/Pi operations outside Kanban.
2. Create tasks assigned to the exact Profile and set per-task `reasoning_effort` using Kanban’s native override.
3. Store `kanban_task_id` in Control Plane, not duplicated task state.
4. Translate Kanban worker progress/comments/completion/block events into AgentEvent contracts.
5. Use native 60-second worker activity heartbeat and reclaim after 5 minutes.
6. Verify jobs survive gateway/process restart.
7. Keep `message_agent` out of the control path; allow it only for human/ad-hoc Bot communication.
8. Test `NEED_INPUT`, user reply routing, cancellation, stale worker, and resumption from checkpoint.

### Task 7: Implement adaptive resource scheduler

**Files:** `scheduler.py`, `config/resource-policy.yaml`, `tests/scheduler/`.

1. Read cgroup memory current/max, load averages, worker inventory, and browser-session state.
2. Implement capacity units and maximums from section 1.4.
3. Reserve orchestrator/confirmation capacity.
4. Pause and resume by priority without cancelling jobs.
5. Add hysteresis so jobs do not flap near thresholds.
6. Write synthetic pressure tests and a live read-only diagnostics command.

### Task 8: Implement surface delivery and progress UX

**Files:** `delivery.py`, integration adapters, `tests/integration/test_delivery.py`.

1. Deliver start, blocked/waiting, material milestones for long work, and terminal state.
2. Return normal results to origin session.
3. Send Telegram extra only for blocked confirmations and critical failures.
4. Hide IDs normally; reveal short ID for ambiguity/status/debugging.
5. Deduplicate outbound messages and preserve role alternation.
6. Test Desktop-origin, Telegram-origin, disconnected origin, duplicate callback, and later status query from the other surface.

### Task 9: Create Profiles, SOUL files, and least-privilege toolsets

**Files:** `profiles/<name>/SOUL.md`, `capabilities/agents/*.yaml`; actual profile config via `hermes profile` and `hermes config`, not manual secret edits.

1. Create seven specialist Profiles.
2. Share only the central Codex OAuth pool.
3. Disable independent worker memory writes.
4. Set exact model/effort defaults.
5. Remove blocked toolsets from each agent schema, not merely from prompts.
6. Add Control Plane enforcement as a second layer.
7. Verify Coder cannot access Hermes/profile/config paths.
8. Verify Architect-Planner is read-only for source code.
9. Verify Documentator can write only docs/knowledge/changelog areas.
10. Verify Browser sees only browser/Uber/vision capabilities and never credentials.
11. Run `hermes config check` for every Profile without displaying secrets.

### Task 10: Create and map skills

**Files:** `skills/*/SKILL.md`, agent manifests, skill tests/lint.

1. Author `orchestrator-control` for intent normalization, clarification, job linking, and result synthesis.
2. Author `technical-architecture-planning` for R0/R1/R2 technical plans.
3. Author `risk-classification` with the frozen critical-change list.
4. Author `travel-planning` around real MCP schemas and mandatory questions.
5. Reuse existing skills:
   - `pi-tou-calendar` on default;
   - `uber-eats-cart`, `computer-use`, `browser-automation` on Browser;
   - `grounded-citations`, `blocked-page-recovery`, `arxiv` on Researcher;
   - `hermes-agent`, `hermes-architecture`, systematic debugging, TDD, skill authoring, and code review on Engineer;
   - coding/TDD/debugging/GitHub skills on Coder;
   - diagrams and technical docs skills on Documentator.
6. Skills encode procedure, not authorization. Tests prove policy still blocks forbidden tools.

### Task 11: Browser Operator implementation and evaluation

**Files:** browser capability manifest, `architecture/browser-operator.md`, replay fixtures, browser tests.

1. Wrap existing managed Uber MCP session and semantic tools.
2. Implement Observe–Decide–Act–Verify–Recover event checkpoints.
3. Invalidate DOM/SOM refs after state mutation.
4. Implement grounded confidence signals and calibrated risk thresholds.
5. Add one-equivalent-retry no-op guard and state-cycle fingerprints.
6. Add `NEED_INPUT` mediation through the orchestrator.
7. Add Sol review job only for critical/conflicting visual state.
8. Delete screenshots on every terminal path, including crash recovery.
9. Keep structured redacted trajectory logs only.
10. Run mock storefront tests, then Uber read-only state, restaurant search, menu inspection, cart planning, checkout preview, confirmation expiry, and cancel tests. Never execute a real purchase during testing.

### Task 12: Technical change pipeline

**Files:** pipeline config, Architect/Engineer/Coder manifests, tests.

Implement risk-based pipeline:

- R0: Engineer or Coder directly → tests → ChangeEvent → Documentator.
- R1: Architect-Planner → Engineer/Coder → tests → Documentator.
- R2: Researcher → Architect-Planner → Engineer/Coder → independent Sol medium review → replay/shadow → checkpoint → promotion → Documentator.

Rules:

- Engineer owns harness, skills, MCP/plugins, and core Hermes modifications.
- Coder owns external projects and is denied Hermes/profile paths.
- Core changes occur in a branch/worktree, are recorded as a patch queue, and are rebased/tested after Hermes updates.
- User confirms all critical changes before promotion.
- Non-critical changes may promote automatically after tests, independent Sol medium review where required, replay, checkpoint, health check, and rollback readiness.

### Task 13: Documentation and scoped knowledge packs

**Files:** architecture/runbooks/decisions/changelog/knowledge, `compile_knowledge_packs.py`, tests.

1. Define source-vs-generated ownership.
2. Implement event scope classification: shared, agent-specific, project-specific, user-memory proposal.
3. Generate read-only packs for every Profile.
4. Validate links, schema references, manifest hashes, staleness, and contradictions.
5. Produce Mermaid system, sequence, state-machine, and security-boundary diagrams.
6. Emit memory proposals; only `default` may probe contradictions and write Holographic Memory.
7. Add Sunday 04:00 Europe/Madrid reconciliation cron with continuity and a no-delete policy.
8. Ensure routine job output is delivered appropriately; health alerts remain host-side, not through TUI-only cron delivery.

### Task 14: Health watchdog adjustment

**Existing file:** `/opt/data/mcp-dev/pi-tou-repair/health_alert.py`.

1. Add tests for two consecutive critical samples, immediate essential-service failure, dedupe, changed fingerprint, reminders, and recovery.
2. Preserve sanitized report validation and secret handling.
3. Change alert state to track consecutive critical observations.
4. Do not alert warnings under the chosen user policy.
5. Verify the root-owned timer runs every five minutes.
6. Promote broker/host changes through its independent approval mechanism where root is required.
7. Send a test notification only after explicit user approval.

### Task 15: Historical replay and shadow rollout

**Files:** `scripts/replay_routing.py`, `tests/replay/fixtures/`, `runbooks/rollout.md`.

1. Export only user-message text needed for routing tests; redact secrets and never mutate/delete source sessions.
2. Build expected-label fixtures covering Spanish, spelling errors, multiple intents, follow-ups, cancellations, calendar ambiguity, browser purchases, travel, and technical self-improvement.
3. Require zero policy violations and agreed routing precision/recall threshold before shadow.
4. Run 24-hour shadow mode: generate/log route decisions but leave current execution path authoritative.
5. Review false routes and update only schema/rules/normalization skill through tested changes.
6. Activate stages:
   - read-only Researcher/Travel/Pi/docs;
   - direct unambiguous calendar create;
   - isolated Engineer/Coder changes;
   - Browser prepare/preview without checkout;
   - confirmation-bound operations.
7. Provide a single kill switch to disable specialist dispatch and revert to `default` direct behavior.

### Task 16: Full acceptance suite and operational handoff

Acceptance must prove:

- Contract validation and semantic version migration.
- Deterministic enum-to-profile routing.
- Least-privilege tools absent from blocked agent schemas.
- Control Plane defense against forged/nested payloads.
- Idempotency under duplicate messages and retries.
- Atomic cancellation and side-effect read-back.
- Confirmation digest/expiry/state invalidation.
- Resource scheduler and one-browser limit.
- Worker heartbeat, stale recovery, and cycle guard.
- Restart durability.
- Codex internal fallback policy and Sol max prohibition.
- No provider-crossing fallback.
- Screenshot deletion on success/failure/cancel/crash recovery.
- Coder/Engineer filesystem separation.
- Documentation event flow and knowledge-pack regeneration.
- No deletion of conversations/sessions/memory.
- 24-hour shadow report accepted by the user.
- Rollback from every activation stage.

After acceptance, Documentator publishes the initial architecture baseline and the orchestrator reports the final active profiles, models, toolsets, contracts, and rollback command without exposing credentials.

---

## 5. Critical risks and mitigations

1. **Self-modifying policy engine:** independent Sol medium review, test/replay, atomic promotion, checkpoint, health check, rollback; user confirmation for frozen critical list.
2. **Natural-language ambiguity:** Luna may normalize language, but routing after enum is deterministic; invalid/unknown intent asks rather than guesses.
3. **Provider outage:** no cross-provider fallback; pause cleanly with persisted state.
4. **Pi memory pressure:** capacity units, cgroup-aware admission, one browser, orchestrator reserve, hysteresis.
5. **Duplicate external actions:** idempotency key, pre/post read-back, atomic sections, digest-bound confirmation.
6. **Browser prompt injection/visual ambiguity:** typed broker tools first, sanitized semantic state, selective vision, confidence thresholds, Sol review only when justified, user confirmation for persistent effects.
7. **Knowledge divergence:** Documentator-owned canonical docs and generated packs; workers cannot write private memory.
8. **Hermes core update conflict:** tracked patch queue/worktrees, documented divergence, rebase and full acceptance suite.
9. **Notification storms:** event milestones only, dedupe fingerprints, origin delivery, Telegram escalation policy.
10. **Unlimited-duration jobs:** no arbitrary timeout, but no-op/cycle guard, heartbeat/stale reclaim, two transient retries, resource pause, and explicit cancellation.

---

## 6. Rollback strategy

- Before any config/profile/core promotion: export config, create checkpoint, and record hashes.
- Control Plane deployments use atomic versioned directories plus `current` symlink or equivalent release pointer.
- SQLite migrations require backups and tested down/forward recovery; destructive migration is critical and user-approved.
- Profiles are enabled one activation stage at a time.
- Kill switch disables dispatch while preserving ledger/jobs for inspection.
- Browser checkout confirmation capability can be disabled independently.
- Core Hermes patches remain in a reversible branch/patch queue.
- No rollback process may delete user conversations, sessions, or memories.

---

## 7. Definition of done

The architecture is complete only when:

- All Profiles exist with the approved model/effort and minimal schemas.
- `default` remains the only required human interface.
- Telegram/Desktop session-origin routing works.
- Every initial intent has a deterministic route and readiness status.
- All contracts validate and are versioned.
- Kanban specialist workers survive restart and report structured events.
- Browser and technical side effects are confirmation/idempotency protected.
- Scheduler respects the Pi’s 2 GiB cgroup and five-job/four-unit limits.
- Health watchdog behavior matches the approved critical-only policy.
- Knowledge packs and weekly reconciliation work.
- Historical replay, full acceptance tests, 24-hour shadow, staged activation, and rollback drills pass.
- The user reviews and approves the shadow report and every critical promotion.
