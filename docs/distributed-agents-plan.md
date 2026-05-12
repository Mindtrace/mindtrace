# Mindtrace Distributed Agents — Implementation & Testing Plan

**Version:** 1.0  
**Date:** 2026-05-02  
**Status:** Working plan (aligned to `distributed-agents-lld.md`, updated for Agents UI in Chiron `mip/`)

---

## 1. Executive Summary

This plan implements the distributed agents system described in `mindtrace/docs/distributed-agents-lld.md` in **phases** that are independently shippable, with a clear **testing strategy** per phase.

Key update versus earlier direction: the **Agents UI** (config + observability + playground) will live in the existing Chiron frontend at:

- `mip/apps/chiron/frontend/` (React + Vite)

The UI will be **available in the Chiron portal by default**, and may be optionally hidden/restricted per portal variant using `VITE_APP_VARIANT` rules.

The distributed runtime remains in the **Mindtrace** repo under the `mindtrace-agents` package.

---

## 2. Goals and Non-goals

### Goals

- **Distributed execution**: Client → Gateway → Queue → Worker(s), with streaming `NativeEvent`s.
- **Stateless workers**: session continuity via Redis history/memory (shared infra).
- **Security**: authenticated access; scoped authorization; allowlist for agent class loading; DLQ for unsafe/invalid tasks.
- **Reliability**: retries (configurable), TTL guards, DLQ semantics, backpressure, circuit breakers.
- **Observability**: spans + metrics + trace propagation (W3C); central collector + OTLP export.
- **Extensibility**: skills and model providers via entry-points.
- **Multi-scope memory**: session (volatile), user (cross-session), project (project-scoped config + knowledge), org (org-wide policies + shared knowledge base). All scopes accessible via REST API and automatically injected into agent context at task start.
- **UI**: Chiron pages for configuration + observability + live streaming playground + memory management.

### Non-goals (v1)

- Immediate migration of existing Chiron/Inspectra “agent job polling” backend flows to the new gateway. We will keep legacy flows until deliberately migrated, but **new Agents pages** will be built against the gateway/collector public APIs.
- Full multi-tenant isolation model unless it already exists in your auth/identity system. (We’ll keep extension points for `tenant_id` later.)

---

## 3. Code Locations (Source of Truth)

### Backend (Mindtrace)

- **Package**: `mindtrace/mindtrace/agents/` (python package `mindtrace-agents`)
- **Unit tests**: `mindtrace/tests/unit/mindtrace/agents/`
- **Integration tests** (new): `mindtrace/tests/integration/mindtrace/agents/`
- **Compose** (new canonical dev env): `mindtrace/tests/docker/agents/docker-compose.agents.yml`  
(exact folder is flexible; pick one stable location and standardize on it)

### UI (MIP / Chiron)

- **Frontend**: `mip/apps/chiron/frontend/`
- **New Agents pages**: `mip/apps/chiron/frontend/src/pages/agents/`
- **New shared client lib**: `mip/apps/chiron/frontend/src/lib/agents-client/`
- **E2E tests** (new): `mip/apps/chiron/frontend/tests/e2e/agents/` (Playwright)

---

## 4. Design Constraints (Decisions We’ll Stick To)

1. **Keep base install lean**: distributed components behind extras.
2. **No pickle across network boundaries**: all queue payloads are JSON/Pydantic models.
3. **One shared queue** by default (no per-worker affinity) + Redis for session state.
4. **Allowlist is a real security boundary**: source-of-truth is file/config (signed later), not “anyone who can write to Redis”.
5. **UI uses public APIs only**: the UI talks to gateway/collector over REST/WS, not directly to Redis/Rabbit/Mongo.

---

## 5. Phased Plan

Each phase lists:

- **What we achieve** (user-visible / system-visible outcomes)
- **Implementation details** (modules / responsibilities)
- **How to test** (unit / integration / e2e)
- **UI deliverables** (Chiron pages)

### Phase 0 — Foundation & cleanup (1–1.5 weeks)

#### What we achieve

- Agent runtime is maintainable: no duplicated control-flow across `run()`, `run_stream_events()`, and `iter()`.
- The system has stable primitives needed for distribution (context fields, deprecation strategy).
- MIP frontend is ready for incremental Agents UI development (Playwright + query tooling).

#### Backend implementation (Mindtrace)

- Refactor `mindtrace/mindtrace/agents/mindtrace/agents/core/base.py`:
  - Extract a shared step/loop engine so the three execution modes (`run`, `run_stream_events`, `iter`) share logic.
  - Make `max_iterations` configurable on `MindtraceAgent` and overridable per call.
- Extend `RunContext` in `mindtrace/mindtrace/agents/mindtrace/agents/_run_context.py`:
  - Add optional fields: `session_id`, `user_id`, `trace_id`, `span_id`, `parent_span_id`.
  - Defaults stay `None` to avoid breaking existing tool signatures.
  - Flow `session_id` from `MindtraceAgent.run()` into `RunContext` automatically so tools can read it via `ctx.session_id` without depending on deps.
- **Hard-deprecate pickle-based RabbitMQ queue (security fix — do not skip):**
  - Rename `RabbitMQTaskQueue` → `_LegacyPickleRabbitMQTaskQueue` and remove it from the public `__init__.py` exports.
  - Any import of the old name raises `ImportError` with a migration message pointing to the new `RabbitMQAgentTaskQueue`.
  - MIP backend must migrate off the pickle queue before Phase 3 is deployed. Treat this as a blocker.
- Fix `AbstractMemoryStore` interface in `agents/memory/_store.py`:
  - Add `namespace: str` as a required constructor argument on the abstract base.
  - Update `InMemoryStore` and `JsonFileStore` to accept and scope keys by namespace.
  - This is a prerequisite for the namespaced memory architecture used in all distributed stores.

#### Backend testing

- **Unit**: prove behavior unchanged for:
  - tool-call ordering
  - history saving logic
  - streaming event sequence shape
  - max-iteration stop behavior
- **Unit**: `RunContext.session_id` / `user_id` propagated into tool calls correctly.
- **Unit**: `AbstractMemoryStore` namespace isolation — two stores with different namespaces do not share keys.
- **Unit**: `ImportError` raised on import of the old pickle queue name.

#### UI implementation (MIP / Chiron)

- Add deps to `mip/apps/chiron/frontend/package.json`:
  - `@playwright/test`
  - `@tanstack/react-query`
- Add Playwright smoke test `tests/e2e/smoke.spec.ts`:
  - builds Chiron variant (default)
  - asserts app loads without console errors
- Add a placeholder `/agents` route group (not linked in nav yet).

---

### Phase 1 — Auth primitives + Redis history/memory + envelope model (2 weeks)

#### What we achieve

- A durable, typed **wire format** exists: `AgentTaskEnvelope`, `AgentRunContext`, `TaskProvenance`.
- Redis-backed session history and short-term memory exist and are test-proven.
- Auth validators work with a fast dev mode and realistic IdP compatibility.
- Chiron UI can browse session history/memory (initially read-only).

#### Backend implementation (Mindtrace)

- `agents/context/propagation.py`
  - `AgentRunContext` (Pydantic): trace identifiers, `session_id`, `user_id`, `**org_id`**, `**project_id**`, baggage, `deps_data` payload.
  - `TaskProvenance`, `AgentTaskEnvelope`.
  - W3C header round-trip helpers (`traceparent`, baggage).
- `agents/auth/`
  - `AuthenticatedPrincipal`, typed `Scope` (enum), `require_scope`.
  - New scopes: `memory:read`, `memory:write`, `project:member`, `project:admin`, `org:member`, `org:admin`.
  - `JWKSValidator`, `HMACAPIKeyValidator`, `WorkerTokenValidator`.
  - `DevJWKSSigner` for fast local tokens and test fixtures.
- `agents/history/redis.py` (extra: `memory-redis`)
- `agents/memory/redis.py` (extra: `memory-redis`)
- `agents/memory/mongo.py` — **text search only in this phase** (extra: `memory-mongo`). Implements per-user, per-project, per-org namespaces. Vector search deferred to Phase 4.
- Session History REST API: `GET /sessions/{session_id}/history`, `DELETE /sessions/{session_id}/history`, `GET /sessions?user_id={user_id}` — registered on the gateway.

#### Backend testing

- **Unit**:
  - JWT validation (valid/expired/bad signature/unknown kid; JWKS refresh)
  - Scope enforcement including new memory/project/org scopes
  - W3C header propagation round-trips
  - `AgentRunContext` serialises/deserialises `org_id` and `project_id` correctly
- **Integration (testcontainers)**:
  - Redis history TTL refresh
  - Redis memory namespace isolation + per-key TTL override
  - MongoMemoryStore: user/project/org namespace isolation; `$text` search returns correct top_k
  - Session history REST endpoint returns messages in insertion order

#### UI implementation (MIP / Chiron)

- Update Chiron nav (`mip/apps/chiron/frontend/src/App.tsx`) to include `/agents/`* in the sidebar and allowlist of routes.
- Add initial pages:
  - `SessionsPage`: list sessions by user; enter a `session_id` manually
  - `SessionDetailPage`: show conversation history + session memory keys/values
  - `UserMemoryPage`: browse/edit user-scoped memory entries
  - `ProjectMemoryPage`: browse/edit project-scoped memory entries (admin-visible by default; configurable)
  - `OrgMemoryPage`: browse/edit org-scoped memory entries (org:admin scope)
- Add `src/lib/agents-client/rest.ts` + `types.ts` skeleton (include `MemoryEntry`, `SessionInfo` types).

#### UI testing

- **E2E (Playwright)**:
  - navigate to Sessions
  - open a seeded session and verify messages render

---

### Phase 2 — Worker + allowlist + local observability (2.5 weeks)

#### What we achieve

- Remote execution works with workers consuming tasks and producing results.
- Allowlist prevents unsafe dynamic imports of arbitrary agent classes.
- Spans exist (initially structured logs), sufficient for first operational debugging.
- Chiron UI can manage allowlist and view workers/agents.

#### Backend implementation (Mindtrace)

- `agents/allowlist/`
  - `MindtraceAllowlistRegistry` where file/config is source-of-truth (Redis may be cache only).
  - `AllowlistViolationError`, enforcement hooks.
- `agents/distributed/registry.py` (Redis-backed: agent defs + live workers + heartbeats)
  - `AgentDefinition` gains `org_id` and `project_id` fields.
  - `MindtraceAgentRegistry.list_agents()` accepts optional `org_id` / `project_id` filters.
- `agents/distributed/worker.py`
  - TTL guard; allowlist check before import; retry policy; concurrency semaphore.
  - Publish streaming events to `Redis Pub/Sub` channel `task:{task_id}`.
  - **Memory injection at task start** — load and inject `inject=true` entries from user, project, and org scopes before calling `agent.run()`. Uses new `MemoryContextBuilder`.
- `agents/distributed/node.py` (if using cluster runtime to manage worker processes)
- `agents/distributed/memory_api.py`
  - CRUD REST endpoints for session, user, project, and org memory scopes.
  - `MemoryContextBuilder` — assembles injected system context block from all scopes, capped at 2 000 tokens.
  - Session history REST endpoints (`GET /sessions/{id}/history` etc.) moved here from gateway.
- `agents/observability/`
  - Span model
  - Agent execution wrapper (avoid relying on worker MRO overriding `run()`)

#### Backend testing

- **Integration**:
  - Submit task → worker executes → result returned.
  - TTL exceeded → DLQ.
  - Allowlist violation → DLQ (no retry).
  - Concurrency cap respected.
  - Memory injection: task with `project_id` set has project memory block in system context; task without `project_id` does not.
  - Memory CRUD API: create user memory entry, retrieve it, delete it; verify 404 after delete.
  - Org memory write requires `org:admin` scope; read requires `org:member`.
- **Stress**: many tasks; no leaked futures/queues; stable memory.

#### UI implementation (MIP / Chiron)

- Add pages:
  - `AgentsListPage` (definitions; shows org/project scope if set)
  - `WorkersPage` (heartbeats)
  - `AllowlistPage` (admin-only operations)
  - `RunsFeedPage` (recent spans / recent tasks)
  - `MemoryPage` — unified memory browser with tabs for Session / User / Project / Org scopes; supports search and inline edit for authorised principals.

---

### Phase 3 — Gateway + WS streaming + backpressure/circuit breakers (2.5 weeks)

#### What we achieve

- External clients use the **Gateway** as the single entry point.
- WebSocket streaming of `NativeEvent`s works end-to-end.
- Backpressure and circuit breakers prevent cascading failures.
- Chiron becomes a real **playground** and the **agent sidebar** uses streaming.

#### Backend implementation (Mindtrace)

- `agents/distributed/gateway.py`
  - WS endpoint `/ws/agents` + REST fallback `/agents/`*
  - authentication + scope-based authorization
  - backpressure (max sessions, queue depth)
  - circuit breakers (prefer shared state in Redis for multi-gateway deployments)
  - result-access control (submitter vs service/admin)
- Queue implementation:
  - add envelope-based `RabbitMQAgentTaskQueue` (durable, DLQ, retry, TTL)
  - legacy pickle queue remains deprecated but intact for a release window

#### Backend testing

- **Integration**:
  - WS happy path: `connected → ack → stream events → response`
  - auth required; invalid scope rejected
  - submitter cannot read another user’s task result
- **Chaos**:
  - Redis down → breaker opens; recovery closes
  - queue depth high → gateway rejects new tasks

#### UI implementation (MIP / Chiron)

- Add `PlaygroundPage`:
  - choose agent, set/auto session, invoke, stream tokens + tool events live
- Implement `src/lib/agents-client/ws.ts` (WS client for streaming protocol).
- **Migrate agent sidebar (Chiron)**:
  - Replace polling (`submitAgentChat` / `getAgentChatStatus` / `getAgentChatResult`) with WebSocket streaming via `src/lib/agents-client/ws.ts`.
  - Pass Chiron app context in `AgentInvokeRequest.metadata`: `project_id` from the active project context, `org_id` from the authenticated user's org. These are mapped to `AgentRunContext.project_id` / `org_id` by the gateway so the worker can inject the right memory.
  - If Inspectra/NeuroForge require different UX, keep variant-specific toggles, but do not block Chiron migration on them.

#### UI testing

- **E2E (Playwright)**:
  - invoke in Playground
  - assert streamed deltas appear before final response

---

### Phase 4 — Collector + metrics + plugins + DLQ ops (2 weeks)

#### What we achieve

- Central collector persists spans + serves metrics + exports OTLP to Jaeger/Tempo.
- Plugin registry discovers skills/providers at worker startup.
- DLQ operations are available for admins.
- Chiron UI is a full config + observability console.

#### Backend implementation (Mindtrace)

- `agents/distributed/collector.py`
  - `POST /spans`, `POST /spans/query`, `GET /metrics/{agent_name}`, `GET /health`
  - Mongo persistence + OTLP export
- `agents/plugins/`
  - Entry-point discovery for skills and providers
  - Async discovery lifecycle
- DLQ admin endpoints (admin scope): inspect / requeue / purge
- `agents/memory/mongo.py` — **add vector search** (`$vectorSearch` aggregation via `EmbeddingProvider` protocol). Prioritise user memory vector search first (cross-session preference retrieval is the highest-frequency query), then project memory, then org memory.

#### Backend testing

- **Integration**:
  - span ingestion + query
  - metrics match ingested spans
  - plugin discovery fixture package loads
- **E2E compose**:
  - gateway+worker+collector+jaeger running
  - a trace/span is visible and linkable

#### UI implementation (MIP / Chiron)

- Add pages:
  - `SpansPage` (search/filter)
  - `TracesPage` (trace tree + link to Jaeger)
  - `MetricsPage` (dashboards)
  - `PluginsPage`
  - `DLQPage` (admin operations)

---

### Phase 5 — Hardening (1.5 weeks)

#### What we achieve

- Production-ready operational posture: rate limiting, durable streaming option, signed allowlist, graceful shutdown.
- Chiron UI adds admin tools and “alerts” UX.

#### Backend implementation (Mindtrace)

- Rate limiting (Redis)
- Optional Redis Streams relay for durable reconnect streaming (configurable)
- Signed allowlist verification (tamper resistance)
- Graceful shutdown & draining behavior across gateway/worker/collector

#### Testing

- rate limit tests
- allowlist tamper tests
- shutdown drain tests
- perf baselines (p95 streaming latency budgets)

#### UI

- admin tools (API key rotation, rate-limit views)
- alerts widget driven by Prometheus/collector metrics

---

## 6. Canonical Dev/Test Environments

### Backend compose (Mindtrace)

Services to maintain (subset per phase):

- `redis`
- `rabbitmq:3-management`
- `mongo`
- (Phase 4+) `jaeger`, `otel-collector`
- (Phase 3+) `gateway`
- (Phase 2+) `node` + `worker`
- (Phase 4+) `collector`
- (Optional, recommended for realism) `keycloak`

### UI dev (MIP / Chiron)

From `mip/apps/chiron/frontend`:

- `VITE_APP_VARIANT=chiron` (default)
- `VITE_AGENTS_GATEWAY_URL=http://localhost:<gateway_port>`
- `VITE_AGENTS_COLLECTOR_URL=http://localhost:<collector_port>`

---

## 7. Acceptance Criteria (Phase Gates)

- **Phase 0**: Refactor complete; all existing `mindtrace-agents` unit tests green; `RunContext.session_id` flows into tool calls; `AbstractMemoryStore` namespace isolation verified; old pickle queue raises `ImportError`; Playwright smoke green.
- **Phase 1**: Redis history/memory integration tests green; `MongoMemoryStore` text search working for user/project/org namespaces; `AgentRunContext` carries `org_id`/`project_id`; session history REST API returns messages; Chiron can browse all memory scopes (read-only).
- **Phase 2**: Worker executes queued tasks; allowlist enforced; DLQ working; memory injection puts project/org context into agent system prompt; memory CRUD API enforces scope-based auth; UI shows agents/workers/allowlist/memory browser.
- **Phase 3**: WS streaming E2E works; Chiron sidebar migrated to WebSocket and passes `project_id`/`org_id` in invoke request; playground streams tokens live; memory injection observable via spans.
- **Phase 4**: Collector persists/query spans; OTLP export works; user memory vector search returns semantically relevant results; UI spans/metrics/traces/DLQ/plugins functional.
- **Phase 5**: Rate limits + signed allowlist + graceful shutdown + perf baseline pass.

---

## 8. Open Decisions (Resolve Early)

1. **Portal deployment model**:
  - Are portal variants (`VITE_APP_VARIANT`) separate images, or runtime configuration of one image?
2. **Auth consolidation**:
  - Will Chiron reuse existing app auth token via a proxy, or maintain separate JWTs for the gateway?
3. **Where TS client types come from**:
  - manual types initially; then generated from Pydantic models in CI.

