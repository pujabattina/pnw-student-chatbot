# Implementation Plan: PNW Student Information Chatbot

**Branch**: `002-pnw-student-chatbot` | **Date**: 2026-09-19 | **Spec**: [spec.md](./spec.md)

## Goal

Build a simple PNW chatbot that gives cited answers from approved sources. If it cannot answer
safely, it asks for missing context or sends the student to the right PNW office.

## Stack

| Part | Choice | Purpose |
|---|---|---|
| Frontend | React + Vite + TypeScript | Student chat and reviewer screens |
| Backend | FastAPI + Python 3.12 | REST API, safety rules, and source review |
| Database | PostgreSQL 16 + pgvector | Sources, citations, roles, and search |
| Background work | Python worker | Imports and re-indexes approved sources |
| Deployment | Docker Compose | Runs the app locally and on one server |

## Architecture

```text
Student or reviewer
        |
        v
HTTPS reverse proxy
   |                |
   v                v
React frontend    FastAPI API -----------------> Approved model provider
                      |
                      v
              PostgreSQL + pgvector
                      ^
                      |
              Source-import worker
```

### How it works

1. A student submits an anonymous question through the React frontend.
2. FastAPI removes personal details from telemetry, checks whether context is missing, and searches
   only active, approved sources that match the campus and term.
3. The API returns one of three results: a cited answer, a short follow-up question, or a safe
   referral. It never accesses student records.
4. Reviewers sign in through PNW identity services to add, review, approve, or disable sources.
5. The worker fetches approved source updates. A changed or withdrawn source is disabled until its
   owner approves the new version.

## Important Rules

- Student chat is anonymous. Do not store raw questions, answers, IP addresses, or student records.
- Reviewer access uses PNW sign-in and roles. All source changes are audited.
- Only approved, current, and context-matching sources can support an answer.
- If sources conflict, are missing, are stale, or the API times out, return a referral rather than
  guessing.
- At least 95% of normal requests must complete within five seconds.

## Project Structure

```text
frontend/                         # React application
└── src/
    ├── features/chat/            # Anonymous student chat
    ├── features/review/          # Reviewer screens
    ├── api/                      # FastAPI client
    └── components/               # Shared UI

backend/                          # FastAPI application
├── app/
│   ├── api/                      # Routes and request/response models
│   ├── auth/                     # PNW sign-in and roles
│   ├── chat/                     # Retrieval, answers, and referrals
│   ├── corpus/                   # Sources, approvals, and citations
│   ├── db/                       # Database models and migrations
│   ├── telemetry/                # Redacted aggregate metrics
│   └── worker/                   # Source update jobs
└── tests/                        # Unit, API, and database tests

deploy/
├── compose.yaml                  # Local Docker services
├── compose.production.yaml       # Production settings
├── api.Dockerfile
├── frontend.Dockerfile
└── proxy/                        # HTTPS and routing configuration

specs/002-pnw-student-chatbot/
├── plan.md                       # This overview
├── research.md                   # Key technology decisions
├── data-model.md                 # Database and lifecycle details
├── quickstart.md                 # End-to-end validation guide
└── contracts/openapi.yaml         # API agreement
```

## Docker Services

| Service | Responsibility |
|---|---|
| `proxy` | The only public service; provides HTTPS and routes traffic |
| `frontend` | Builds and serves the React application |
| `api` | Runs FastAPI and the chat/reviewer API |
| `worker` | Processes source imports and change checks |
| `migrate` | Runs database migrations once before the API starts |
| `db` | Stores PostgreSQL and pgvector data on a named volume |

The database is internal only. Production uses `compose.production.yaml` to remove code mounts,
provide secrets at runtime, and enable restart and health-check settings.

## Testing and Acceptance

- Backend: pytest for safety, source lifecycle, and authorization rules.
- Frontend: Vitest/React Testing Library for chat and reviewer behavior.
- End-to-end: Playwright against Docker Compose.
- Performance: a normal question mix must meet the five-second p95 target.
- Acceptance: follow the 100 supported-question, 30 unsafe-question, campus-context, privacy, and
  source-change scenarios in [quickstart.md](./quickstart.md).

## Constitution Check

The project constitution is an unratified placeholder, so it has no enforceable gates. This plan
still follows the feature's privacy, safety, and testability requirements.

**Result**: PASS.
