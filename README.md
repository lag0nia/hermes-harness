# Hermes Harness

A typed, auditable local control plane for a multi-agent Hermes deployment.
The harness turns user requests into closed intent contracts, applies routing and
risk policies, dispatches specialist work, and keeps execution state durable and
reviewable.

## What this repository contains

- **Typed contracts** for intents, jobs, errors, confirmations, delivery, and
  observability events.
- **Deterministic routing** from the `default` orchestrator to specialist
  profiles. Generic and ambiguous requests stay on the default path.
- **Policy and safety controls** for capability checks, risk classes,
  confirmations, idempotency, cancellation, verification, and rollback.
- **Execution components** for the dispatcher, scheduler, Kanban workers,
  delivery progress, and restart-safe state.
- **Integration boundaries** for MCP tools, browser operations, health checks,
  and the observability plugin.
- **Profiles and capability manifests** under `profiles/` and
  `capabilities/agents/`.
- **Documentation and generated knowledge packs** under `architecture/`,
  `docs/`, `knowledge/`, and `runbooks/`.
- **Tests and review helpers** covering contracts, routing, policy decisions,
  dispatch, persistence, and observability review flows.

This is an integration/control-plane component, not a replacement for the
Hermes Agent runtime. It is intended to be connected to a Hermes gateway and
its served profiles.

## Repository layout

```text
src/hermes_harness/             Python control-plane implementation
config/                         Routing and observability policy
capabilities/                   Least-privilege capability manifests
profiles/                       Specialist profile definitions
architecture/ docs/ runbooks/   Design and operational documentation
knowledge/                      Canonical and generated knowledge packs
scripts/                        Maintenance and review utilities
tests/                          Unit and integration tests
var/                            Local runtime state (ignored by Git)
```

## Quick start

Requirements: Python 3.13 and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest -q
uv run ruff check .
uv run mypy
```

To format the code during development:

```bash
uv run ruff format .
```

To rebuild the generated knowledge packs after changing their sources:

```bash
uv run python scripts/compile_knowledge_packs.py
```

## Using the control plane

A normal integration loads the versioned configuration, serves the profiles
that are explicitly allowed by the gateway, and sends inbound requests through
the control-plane contracts before dispatching work. The main implementation
areas are:

- `hermes_harness.control_plane.contracts` for closed, validated data models;
- `hermes_harness.control_plane.message_router` for conservative content
  routing;
- `hermes_harness.dispatcher` and the scheduler modules for execution;
- `config/routing.yaml` and `capabilities/agents/` for the deployment policy.

For a small local routing check:

```bash
uv run python -c \
  'from hermes_harness.control_plane.message_router import classify_message; print(classify_message("Inspect the error logs"))'
```

The gateway remains responsible for validating that a routed profile is served
and enabled. Routing does not grant capabilities by itself.

## Configuration and privacy

Versioned configuration uses portable paths and keeps runtime state under
`var/`. Installation-specific roots can be supplied by the deployment layer;
do not hard-code host paths in source or documentation.

`.env` is reserved for local secrets and credentials and is ignored by Git.
`.env.example` contains only empty, generic placeholders. Put non-secret paths,
schedules, and policy settings in deployment configuration rather than in
`.env`. Never commit API keys, tokens, cookies, authentication files, or local
SQLite databases.

The control plane is designed around least privilege: sensitive fields are
rejected by the contracts, irreversible actions require policy and/or explicit
confirmation, and normal routing does not expose the original message in its
route directive.

## Contributing

Please add or update tests with behavior changes and run the complete local
quality gate before opening a pull request:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy
```

Keep generated knowledge packs reproducible and update their source files
before regenerating them. Review the relevant security and operational
runbooks before enabling external side effects.
