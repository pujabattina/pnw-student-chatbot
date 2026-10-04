---

description: "Executable implementation tasks for the PNW Student Information Chatbot"
---

# Tasks: PNW Student Information Chatbot

**Input**: Design documents from `/specs/002-pnw-student-chatbot/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/openapi.yaml`, and `quickstart.md`

**Tests**: Tests are included because the specification and implementation plan explicitly require backend, frontend, contract, end-to-end, privacy, lifecycle, and performance validation.

**Organization**: Tasks are grouped by user story so every increment is independently testable.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the runnable monorepo, development tooling, and local deployment baseline.

- [X] T001 Create the React/Vite, FastAPI, test, and deployment directory structure in `frontend/`, `backend/`, and `deploy/`
- [X] T002 Initialize the Python 3.12 FastAPI application and locked dependencies for FastAPI, Pydantic, SQLAlchemy 2.x, asyncpg, Alembic, pgvector support, pytest, and HTTP test clients in `backend/pyproject.toml`
- [X] T003 [P] Initialize the Node 22 React/TypeScript/Vite application and test dependencies in `frontend/package.json`
- [X] T004 [P] Configure Python linting, formatting, type checking, and pytest defaults in `backend/pyproject.toml`
- [X] T005 [P] Configure TypeScript, ESLint, Vite, Vitest, and React Testing Library in `frontend/tsconfig.json`, `frontend/eslint.config.js`, `frontend/vite.config.ts`, and `frontend/src/test/setup.ts`
- [X] T006 Create developer environment templates, secret-name documentation, and generated-file exclusions in `.env.example`, `backend/.env.example`, `frontend/.env.example`, and `.gitignore`
- [X] T007 Create development and production Compose service topology for proxy, frontend build, api, worker, one-shot migrate, and internal-only pgvector database in `deploy/compose.yaml` and `deploy/compose.production.yaml`
- [X] T008 [P] Create non-root API/worker and frontend build images in `deploy/api.Dockerfile` and `deploy/frontend.Dockerfile`
- [X] T009 [P] Configure the sole public HTTPS reverse proxy to send `/api/*` to FastAPI and SPA routes to the frontend in `deploy/proxy/nginx.conf`
- [X] T010 [P] Add CI commands for backend, frontend, contract, end-to-end, and performance suites in `.github/workflows/ci.yml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the shared persistence, security, source-governance, observability, and API foundations that every story requires.

**⚠️ CRITICAL**: Complete this phase before any user-story work.

- [X] T011 Configure typed application settings, startup validation for provider/OIDC/worker secrets, database connection lifecycle, and request deadlines in `backend/app/core/config.py`, `backend/app/core/database.py`, and `backend/app/main.py`
- [X] T012 Create the Alembic migration environment and initial PostgreSQL/pgvector extension migration in `backend/alembic.ini`, `backend/alembic/env.py`, and `backend/alembic/versions/0001_initial_schema.py`
- [X] T013 Model `Source` with “UUID primary key”, “Unique normalized HTTPS URL”, required display/parsing metadata and ownership, current-version reference, and immutable creation timestamp in `backend/app/db/models/source.py`
- [X] T014 [P] Model `SourceVersion` and `SourceFragment`, including “Required content hash; unique per source/version”, parse status “`interpretable` or `uninterpretable`; uninterpretable is ineligible”, protected content reference, locators, lexical vectors, and embedding references in `backend/app/db/models/source_version.py` and `backend/app/db/models/source_fragment.py`
- [X] T015 [P] Model `SourceApproval` with status enum “`candidate`, `pending_review`, `approved`, `disabled`, `rejected`, `superseded`”, required approval/disable fields, and effective-context lists/date range in `backend/app/db/models/source_approval.py`
- [X] T016 [P] Model referrals, reviewer roles, append-only privileged audit events, and transactional ingestion jobs with only source/configuration payloads in `backend/app/db/models/referral.py`, `backend/app/db/models/reviewer.py`, and `backend/app/db/models/ingestion_job.py`
- [X] T017 Define shared Pydantic request/outcome/error schemas matching the chat, citation, referral, source, and change-event shapes in `backend/app/api/schemas/chat.py`, `backend/app/api/schemas/review.py`, and `backend/app/api/schemas/errors.py`
- [X] T018 Create API router registration, health/readiness endpoint, standardized validation errors, and safe 503 handling in `backend/app/api/router.py`, `backend/app/api/routes/health.py`, and `backend/app/api/error_handlers.py`
- [X] T019 Implement ingress PII redaction, allow-listed aggregate-only telemetry, latency buckets, correlation IDs, and logging filters that exclude prompts, responses, IPs, identifiers, and free-text errors in `backend/app/telemetry/redaction.py`, `backend/app/telemetry/aggregates.py`, and `backend/app/telemetry/logging.py`
- [X] T020 Implement backend-owned OIDC authorization-code-with-PKCE session handling, issuer/audience/signature/expiry validation, secure HttpOnly SameSite cookies, and deny-by-default server-side RBAC in `backend/app/auth/oidc.py`, `backend/app/auth/session.py`, and `backend/app/auth/rbac.py`
- [X] T021 Create protected reviewer audit writer and role dependencies for `reviewer`, `source_owner`, `admin`, and `conflict_resolver` in `backend/app/corpus/audit.py` and `backend/app/auth/dependencies.py`
- [X] T022 Implement source eligibility queries that return only current, approved, interpretable versions matching effective campus/college/program/course/academic-term context in `backend/app/corpus/eligibility.py`
- [X] T023 Implement atomic approval lifecycle transitions—candidate to review to approved; changed/withdrawn/parse failure/expiry/conflict to disabled; disabled to review to approved only after owner reapproval—in `backend/app/corpus/lifecycle.py`
- [X] T024 Implement durable PostgreSQL job enqueue and transactional worker claiming/retry with safe error codes in `backend/app/worker/queue.py` and `backend/app/worker/runner.py`
- [X] T025 Add source/reviewer factory fixtures and database isolation fixtures in `backend/tests/conftest.py` and `backend/tests/factories.py`
- [X] T026 [P] Add migration, eligibility, lifecycle, telemetry-redaction, and RBAC unit tests in `backend/tests/unit/test_models.py`, `backend/tests/unit/test_eligibility.py`, `backend/tests/unit/test_lifecycle.py`, `backend/tests/unit/test_telemetry.py`, and `backend/tests/unit/test_rbac.py`

**Checkpoint**: Migrations, source eligibility, privacy protections, authentication primitives, auditing, and durable jobs are ready for story work.

---

## Phase 3: User Story 1 - Receive a Grounded University Answer (Priority: P1) 🎯 MVP

**Goal**: Anonymous students receive a concise, cited answer only when a current, approved PNW source supports it.

**Independent Test**: Seed approved parking, registration, standing, appeal, integrity, graduate-program, prerequisite, and contact sources; submit representative anonymous questions; verify each response has an approved citation and the cited term/context is current.

### Tests for User Story 1

- [X] T027 [P] [US1] Add OpenAPI contract tests for anonymous `POST /api/v1/chat/answers`, 400, 429, and 503 responses in `backend/tests/contract/test_chat_answers.py`
- [X] T028 [P] [US1] Add retrieval and citation unit tests covering lexical/semantic ranking, only approved current fragments, and relevant section/table/PDF locators in `backend/tests/unit/test_retrieval.py`
- [X] T029 [P] [US1] Add API integration tests proving supported answers cite an eligible source and term-specific expired sources are excluded in `backend/tests/integration/test_supported_answers.py`
- [X] T030 [P] [US1] Add anonymous chat component tests for sending a question, rendering answer text, citations, loading, and unavailable states in `frontend/src/features/chat/ChatPage.test.tsx`
- [X] T031 [US1] Create the approved generation-provider adapter with no application-state retention configuration and bounded invocation timeout in `backend/app/chat/provider.py`
- [X] T032 [P] [US1] Implement hybrid lexical and pgvector fragment retrieval with relevance/coverage thresholds in `backend/app/chat/retrieval.py`
- [X] T033 [P] [US1] Implement citation assembly from eligible source fragments, preserving source title, canonical URL, and locator in `backend/app/chat/citations.py`
- [X] T034 [US1] Implement grounded-answer decision logic that emits supported prose only from retrieved coverage and otherwise delegates safe outcomes in `backend/app/chat/decision.py`
- [X] T035 [US1] Implement the anonymous `POST /chat/answers` route with 4,000-character validation, ingress redaction before telemetry, rate limiting, correlation-only request state, and bounded stage deadlines in `backend/app/api/routes/chat.py`
- [X] T036 [US1] Add the typed frontend API client and discriminated chat outcome parsing in `frontend/src/api/client.ts` and `frontend/src/api/chat.ts`
- [X] T037 [US1] Build the accessible anonymous question form, citation links, answer rendering, error state, and no-login entry point in `frontend/src/features/chat/ChatPage.tsx` and `frontend/src/features/chat/ChatPage.module.css`
- [X] T038 [US1] Wire the anonymous chat page into the application route and shared layout in `frontend/src/App.tsx` and `frontend/src/components/AppShell.tsx`
- [X] T039 [US1] Implement source fetch, protected extraction, parsing, section/table/PDF/attachment fragment creation, chunking, and embedding jobs in `backend/app/worker/fetch.py`, `backend/app/worker/parse.py`, and `backend/app/worker/embed.py`
- [X] T040 [US1] Add approved representative corpus seed data and worker seed entry point in `backend/app/worker/seed.py` and `backend/tests/fixtures/approved_corpus.json`
- [ ] T041 [US1] Add a Playwright MVP journey that verifies an anonymous supported answer and clickable approved citation in `frontend/e2e/grounded-answer.spec.ts`

**Checkpoint**: A student can anonymously obtain a current, approved-source-backed answer with citations.

---

## Phase 4: User Story 2 - Receive Context-Relevant Academic Guidance (Priority: P2)

**Goal**: Students get a source-backed academic answer for supplied campus/program/course/term context, or a targeted follow-up when that context is missing.

**Independent Test**: Submit Hammond/Westville and program/course/term questions with and without required context; verify a focused clarification is returned before ambiguity can lead to an answer and that supplied context selects only matching catalog sources.

### Tests for User Story 2

- [ ] T042 [P] [US2] Add contract tests for `clarification_needed`, allowed `missingFields`, and constrained `QuestionContext` values in `backend/tests/contract/test_chat_context.py`
- [ ] T043 [P] [US2] Add context policy unit tests for campus, college, program, course, and academic-term ambiguity in `backend/tests/unit/test_context.py`
- [ ] T044 [P] [US2] Add integration tests for Hammond/Westville disambiguation, prerequisite summaries, and unlisted programs in `backend/tests/integration/test_contextual_answers.py`
- [ ] T045 [P] [US2] Add React tests for context controls and rendering/following a focused clarification prompt in `frontend/src/features/chat/ContextPrompt.test.tsx`
- [ ] T046 [US2] Implement missing-context and campus-divergence detection with focused clarification questions in `backend/app/chat/context.py`
- [ ] T047 [US2] Extend retrieval filtering and answer validation to bind applied campus, college, program, course, and term context to citations in `backend/app/chat/retrieval.py` and `backend/app/chat/decision.py`
- [ ] T048 [US2] Extend the chat request route to return a `clarification_needed` outcome before model invocation when material context is absent in `backend/app/api/routes/chat.py`
- [ ] T049 [US2] Build context input controls, missing-field prompt UI, and resubmission behavior in `frontend/src/features/chat/ContextPrompt.tsx` and `frontend/src/features/chat/ChatPage.tsx`
- [ ] T050 [US2] Add Playwright campus/program/course/term flows for clarification then context-correct citation in `frontend/e2e/context-guidance.spec.ts`

**Checkpoint**: Context-dependent guidance either asks exactly for needed context or provides a matching approved citation.

---

## Phase 5: User Story 3 - Receive a Safe Referral (Priority: P3)

**Goal**: Unsupported, conflicting, outdated, account-specific, or unsafe questions receive a clear limitation and a scoped PNW referral instead of a guess.

**Independent Test**: Submit unsupported, account-specific, conflicting, expired, uninterpretable, and timeout cases; verify no asserted answer is returned and each response carries the applicable limitation/reason and active eligible referral when available.

### Tests for User Story 3

- [ ] T051 [P] [US3] Add contract tests for `referral` outcomes and the six allowed reasons—unsupported, conflicting, outdated, account_specific, uninterpretable, timeout—in `backend/tests/contract/test_referral_outcomes.py`
- [ ] T052 [P] [US3] Add unit tests for account-specific detection, conflicts, stale/uninterpretable evidence, generation/retrieval timeouts, and referral selection in `backend/tests/unit/test_safe_referral.py`
- [ ] T053 [P] [US3] Add integration tests proving unsupported and personal-record questions never yield supported answers in `backend/tests/integration/test_safe_referrals.py`
- [ ] T054 [P] [US3] Add React tests that display limitations, reason-appropriate referral contacts, and no unsupported answer prose in `frontend/src/features/chat/ReferralCard.test.tsx`
- [ ] T055 [US3] Implement account-specific/action-request classification, evidence-conflict detection, and fail-closed referral decisions in `backend/app/chat/safety.py` and `backend/app/chat/decision.py`
- [ ] T056 [US3] Implement active, eligible, context-scoped referral selection backed by a source approval in `backend/app/corpus/referrals.py`
- [ ] T057 [US3] Extend chat timeout/error paths to produce the safe `referral` contract response and aggregate-only reason telemetry in `backend/app/api/routes/chat.py` and `backend/app/telemetry/aggregates.py`
- [ ] T058 [US3] Build limitation and referral-contact display components in `frontend/src/features/chat/ReferralCard.tsx` and `frontend/src/features/chat/ChatPage.tsx`
- [ ] T059 [US3] Add Playwright unsafe-question journeys for account-specific, unsupported, conflicting, outdated, and timeout responses in `frontend/e2e/safe-referral.spec.ts`

**Checkpoint**: Unsafe and unsupported requests consistently fail closed with a clear, appropriate referral.

---

## Phase 6: Reviewer Source Governance (Supports All User Stories)

**Purpose**: Deliver the authenticated source and referral operations that govern the corpus used by all chat outcomes.

- [ ] T060 [P] Add contract tests for `/auth/me`, all `/review/sources` operations, `/review/referrals`, and worker change events in `backend/tests/contract/test_review_api.py` and `backend/tests/contract/test_change_events.py`
- [ ] T061 [P] Add authorization integration tests for anonymous 401, unassigned 403, role-specific access, and audited mutations in `backend/tests/integration/test_reviewer_authorization.py`
- [ ] T062 [P] Add source lifecycle integration tests for change/withdrawal immediate disable, retrieval exclusion, audit evidence, and owner reapproval in `backend/tests/integration/test_source_lifecycle.py`
- [ ] T063 [P] Add reviewer frontend tests for display-only auth state, source status/context, approval controls, and disabled-source state in `frontend/src/features/review/ReviewPage.test.tsx`
- [ ] T064 Implement `/auth/me` and reviewer source/referral routes with server-side role dependencies, validation, and append-only auditing in `backend/app/api/routes/auth.py` and `backend/app/api/routes/review.py`
- [ ] T065 Implement worker-key authenticated change-event route that atomically disables current approval and records the event in `backend/app/api/routes/internal.py`
- [ ] T066 Implement scheduled source change-check jobs for fingerprints, withdrawal, parse failures, expiry, and unresolved conflicts in `backend/app/worker/change_check.py`
- [ ] T067 Implement typed reviewer API calls that rely on backend cookies and never expose OIDC tokens to the browser in `frontend/src/api/review.ts` and `frontend/src/api/auth.ts`
- [ ] T068 Build authenticated reviewer source list/detail, effective-context, approval, disable, and referral management screens in `frontend/src/features/review/ReviewPage.tsx`, `frontend/src/features/review/SourceDetail.tsx`, and `frontend/src/features/review/ReferralEditor.tsx`
- [ ] T069 Add Playwright reviewer flows for 401/403 behavior, authorized approval, changed-source disablement, and reapproval in `frontend/e2e/reviewer-governance.spec.ts`

**Checkpoint**: Authorized institutional reviewers can govern the only sources and referrals the chat uses, with auditable lifecycle changes.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Validate release gates across all stories and harden deployment/documentation.

- [ ] T070 [P] Add privacy regression tests proving prompts with email addresses and student IDs are redacted before logs/telemetry and never persisted in `backend/tests/integration/test_privacy.py`
- [ ] T071 [P] Add a 100-question supported corpus evaluation asserting 100% relevant approved citations and term/campus correctness in `backend/tests/evaluation/supported_questions.json` and `backend/tests/evaluation/test_supported_set.py`
- [ ] T072 [P] Add a 30-question unsafe evaluation asserting 100% safe-referral behavior in `backend/tests/evaluation/unsafe_questions.json` and `backend/tests/evaluation/test_unsafe_set.py`
- [ ] T073 [P] Add normal-load performance testing that verifies p95 supported-or-referral completion is at most five seconds in `backend/tests/performance/chat_load.py`
- [ ] T074 Add Docker health checks, migration dependency gates, production secret wiring, pinned images, restart policies, and no source bind mounts in `deploy/compose.yaml` and `deploy/compose.production.yaml`
- [ ] T075 Add accessibility review checks and keyboard/screen-reader coverage for chat, citations, clarification, referral, and reviewer interfaces in `frontend/src/features/chat/accessibility.test.tsx` and `frontend/src/features/review/accessibility.test.tsx`
- [ ] T076 Document local startup, approved-provider release gate, OIDC fixtures, test commands, 3-minute task study, usability test, and production deployment in `README.md` and `specs/002-pnw-student-chatbot/quickstart.md`
- [ ] T077 Run and record the full quickstart validation matrix in `specs/002-pnw-student-chatbot/validation-report.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 has no dependencies.
- Phase 2 depends on Phase 1 and blocks all story phases.
- US1 depends on Phase 2 and is the MVP.
- US2 depends on the US1 chat/retrieval foundation to add context decisions.
- US3 depends on the US1 chat outcome path and can proceed alongside US2 after the shared US1 decision path is complete.
- Reviewer governance can begin after Phase 2; its lifecycle validation must complete before release.
- Polish depends on the desired stories and reviewer governance.

### User Story Dependency Graph

```text
Setup → Foundational → US1 (MVP) → US2
                       ├────────→ US3
                       └────────→ Reviewer Governance
US2 + US3 + Reviewer Governance → Polish / Release validation
```

### Parallel Opportunities

- T003–T005, T008–T010 can proceed concurrently after the directory structure exists.
- T013–T016 and T026 are separate model/test files after migrations and can be split among developers.
- Within each story, all `[P]` test tasks can run in parallel before implementations.
- US2, US3, and reviewer governance can be staffed in parallel after US1’s shared chat decision path is established.

## Parallel Execution Examples

### User Story 1

```text
Task: "Add OpenAPI contract tests in backend/tests/contract/test_chat_answers.py"
Task: "Add retrieval and citation unit tests in backend/tests/unit/test_retrieval.py"
Task: "Add anonymous chat component tests in frontend/src/features/chat/ChatPage.test.tsx"
```

### User Story 2

```text
Task: "Add context policy unit tests in backend/tests/unit/test_context.py"
Task: "Add contextual API integration tests in backend/tests/integration/test_contextual_answers.py"
Task: "Add context prompt React tests in frontend/src/features/chat/ContextPrompt.test.tsx"
```

### User Story 3

```text
Task: "Add referral contract tests in backend/tests/contract/test_referral_outcomes.py"
Task: "Add safe-referral unit tests in backend/tests/unit/test_safe_referral.py"
Task: "Add referral React tests in frontend/src/features/chat/ReferralCard.test.tsx"
```

## Implementation Strategy

### MVP First

1. Complete Phases 1 and 2.
2. Complete Phase 3 (US1).
3. Seed the approved corpus and run T027–T030 and T041.
4. Demonstrate anonymous cited answers before adding context/referral refinements.

### Incremental Delivery

1. Deliver US1 for grounded answers.
2. Deliver US2 for campus/program/course/term safety.
3. Deliver US3 for safe failure and referrals.
4. Deliver reviewer governance and lifecycle controls before using the system beyond controlled evaluation.
5. Complete release-quality privacy, corpus, performance, usability, and deployment validation.

## Notes

- `[P]` indicates different files with no dependency on another incomplete task in the same phase.
- Every user-story task carries its `[US#]` label; setup, foundational, reviewer-governance, and polish tasks intentionally do not.
- The placeholder constitution is unratified and imposes no additional gates; feature privacy, safety, and testing requirements remain mandatory.
