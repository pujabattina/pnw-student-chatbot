# Research: PNW Student Information Chatbot

## FastAPI service and durable worker

**Decision**: Build the API with Python 3.12, FastAPI, Pydantic schemas, SQLAlchemy 2.x
`AsyncSession`, asyncpg, and Alembic migrations. Run source fetching, parsing, chunking, embedding,
and change detection as a separate worker service, using transactionally claimed PostgreSQL ingestion
jobs. Routes only enqueue durable work; they do not use in-process background tasks for ingestion.

**Rationale**: Async request handling suits concurrent database and generation-provider calls, while
a durable worker keeps long-running ingestion out of the five-second answer path and survives API
restarts. FastAPI specifically distinguishes small background tasks from heavier work, and its
container guide recommends building an application image from the official Python image. [FastAPI
async](https://fastapi.tiangolo.com/async/), [FastAPI containers](https://fastapi.tiangolo.com/deployment/docker/)

**Alternatives considered**: Synchronous data access is simpler but less suitable for the I/O-heavy
API. In-process `BackgroundTasks` cannot provide durable, retryable ingestion; an external queue is
deferred until measured workload exceeds a PostgreSQL-backed queue.

## React client and browser boundary

**Decision**: Build a TypeScript React SPA with Vite. Serve the resulting static assets from the
same HTTPS origin as the API: the reverse proxy sends `/api/*` to FastAPI and all other application
paths to the SPA. Reviewer login uses a backend-owned OIDC authorization-code flow with PKCE and
secure, HttpOnly, SameSite session cookies; React only requests display state from `/api/v1/auth/me`.

**Rationale**: A static SPA is sufficient for anonymous chat and avoids a second frontend server
runtime. The same-origin proxy avoids browser CORS and token-storage risk, while FastAPI remains the
only authority for reviewer roles.

**Alternatives considered**: Next.js was replaced by the requested React/FastAPI split. Browser-held
OIDC tokens expose privileged credentials to XSS; a separate-origin SPA adds cookie/CORS complexity.

## Docker Compose deployment

**Decision**: Use separate Compose services for `proxy`, `frontend` static build, `api`, `worker`,
one-shot `migrate`, and internal-only `db` (PostgreSQL with pgvector and a named volume). The proxy is
the sole published 80/443 service. Production uses a Compose override with no source mounts, pinned
images, secrets supplied at runtime, health checks, restart policies, and non-root API/worker users.

**Rationale**: This supplies repeatable local and single-host deployment, keeps the database off the
public network, and prevents API/worker startup before migration and database readiness. Docker
recommends a production-specific Compose override and removing source bind mounts. [Docker Compose
production](https://docs.docker.com/compose/how-tos/production/)

**Alternatives considered**: Exposing all services directly expands the attack surface. Kubernetes is
not justified for the first-release scale, but Compose services map cleanly to a future orchestrator.

## Governed hybrid retrieval

**Decision**: Store normalized source/version/chunk metadata, PostgreSQL full-text search, and
pgvector embeddings together in PostgreSQL. Query only chunks that are current, approved, active,
and effective for the supplied campus/program/course/term context; combine lexical and semantic
matches, then apply a relevance/coverage threshold before generation.

**Rationale**: Exact course codes, policy identifiers, and campus names benefit from lexical search,
while natural-language questions benefit from embeddings. Keeping approval and retrieval eligibility
in one transactional store lets a disabled source disappear immediately from results. pgvector
supports exact and approximate nearest-neighbor search, and PostgreSQL provides native full-text
search. [pgvector](https://github.com/pgvector/pgvector), [PostgreSQL text search](https://www.postgresql.org/docs/current/textsearch.html)

**Alternatives considered**: Hosted file/vector search was rejected for the initial release because
approval lifecycle and chunking control would be split from the system of record. A dedicated vector
database is deferred until load testing demonstrates PostgreSQL is insufficient.

## Generation provider and privacy

**Decision**: Put model invocation behind a small provider adapter. Production may invoke only a
university-approved provider with no retained application state and an approved data-processing
arrangement; configure the client not to store application state. Do not send source-management
audits or telemetry content to the provider.

**Rationale**: The feature prohibits raw-question retention, while preserving the ability to replace
the model provider without changing the safety workflow. OpenAI documents that Responses application
state is retained by default unless controls are used, so the deployment approval is a hard release
gate. [OpenAI data controls](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint)

**Alternatives considered**: A directly coupled hosted provider risks a data-retention mismatch.
Self-hosted generation is deferred: it raises operational cost and requires performance validation.

## Reviewer authentication and authorization

**Decision**: Use the PNW institutional identity provider via OIDC for reviewer routes, validate
issuer/audience/signature/expiry, and enforce application-side, deny-by-default RBAC. Roles are
`reviewer`, `source_owner`, `admin`, and `conflict_resolver`; every mutation is audited.

**Rationale**: This fulfills institutional sign-in and attributable approval without new local
credentials. Server-side authorization avoids trusting client-side role claims alone. [NIST federation
guidance](https://pages.nist.gov/800-63-4/sp800-63c/Federation/), [OWASP authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)

**Alternatives considered**: Local accounts introduce a new credential lifecycle; shared access and
client-only roles cannot provide attributable, least-privilege approval.

## Source lifecycle and safe failure

**Decision**: Snapshot every fetched source version with a fingerprint. A detected content change,
withdrawal, parse failure, expiry, or unresolved conflict atomically disables the current approval
for retrieval. Only owner re-approval of the new version can reactivate it. On source, retrieval, or
generation timeout, return a safe referral instead of an unsupported answer.

**Rationale**: This fail-closed design implements the “current approved source” guarantee and keeps
an audit trail without reusing stale content.

**Alternatives considered**: Continuing to use a source until periodic review or auto-approving a
URL-stable change could present altered policy as approved.

## Privacy-safe observability

**Decision**: Redact at request ingress before logging or telemetry. Emit allow-listed aggregate
counts and latency buckets only; exclude prompts, transcripts, IP addresses, identifiers, and
free-text errors. Keep reviewer/source audit events separate from student telemetry.

**Rationale**: Aggregate metrics prove response-time and safety outcomes without retaining student
content. [NIST Privacy Framework](https://www.nist.gov/privacy-framework/privacy-framework)

**Alternatives considered**: Encrypted raw logs still violate the no-retention requirement; no
telemetry prevents reliable SLA and safety monitoring.

## Five-second response budget

**Decision**: Pre-index approved content. Use one bounded retrieval-and-generation pass with strict
deadlines: validation/redaction ≤150 ms, retrieval ≤500 ms, optional rerank ≤400 ms, generation
≤3,000 ms, render/egress ≤300 ms; reserve the remainder and refer safely when a deadline expires.

**Rationale**: Synchronous crawling, parsing, embedding, and multi-step agent chains cannot meet
the stated p95. Per-stage aggregate latency exposes regressions without recording questions.

**Alternatives considered**: Streaming improves perceived responsiveness but does not satisfy
time-to-complete; live web search risks unapproved or stale sources.
