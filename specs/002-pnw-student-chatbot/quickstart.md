# Quickstart: Validation Guide

## Prerequisites

- Docker Engine with Docker Compose, and an approved generation-provider configuration with no
  application-state retention. Local non-container development also requires Python 3.12 and Node.js 22.
- OIDC test tenant or PNW-approved non-production identity integration, with reviewer, source-owner,
  admin, and conflict-resolver fixtures.
- An approved sample corpus containing campus- and term-specific PNW sources plus active referrals.

## Run locally

The public proxy requires a TLS certificate and private key at
`deploy/certs/fullchain.pem` and `deploy/certs/privkey.pem`. For local development, create
self-signed certificates (browsers will display a trust warning):

```sh
mkdir -p deploy/certs
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout deploy/certs/privkey.pem \
  -out deploy/certs/fullchain.pem \
  -subj "/CN=localhost"
```

Do not use self-signed certificates in production. Mount a trusted certificate and its private key
at those paths on the deployment host; certificate files are excluded from Git and Docker build
contexts.

Start the stack with:

```sh
docker compose -f deploy/compose.yaml up --build
docker compose -f deploy/compose.yaml exec worker python -m app.worker.seed
```

The proxy redirects HTTP to HTTPS, forwards `/api/*` to FastAPI, and sends other paths to the SPA.
Locally, use `https://localhost:8443`; HTTP on port 8080 redirects there.

The `migrate` service must complete successfully before the API and worker become ready; production
uses `deploy/compose.production.yaml` as an overlay and never bind-mounts application source code.

Run unit, contract, integration, end-to-end, and performance suites before release using the project
scripts defined during implementation.

## Validation scenarios

1. Use anonymous chat for an approved parking or registration question. Expect a plain-language
   answer with an official citation, correct term/campus context, and no raw request in logs or DB.
2. Ask a campus-, program-, course-, or term-dependent question without necessary context. Expect
   `clarification_needed`; supply context and verify the citation matches it.
3. Submit unsupported, conflicting, outdated, account-specific, unfamiliar, and uninterpretable
   source cases. Expect a limitation and scoped referral, never an asserted unsupported answer.
4. Authenticate reviewer fixtures. Anonymous access receives 401; an unassigned identity receives
   403; assigned roles may perform only their authorized source/referral actions.
5. Approve a scoped source, ask a supported question, then deliver a changed/withdrawn event. Verify
   the source is immediately disabled, excluded from retrieval, and recorded in the audit trail.
   Reapprove a replacement version and verify the answer becomes available again.
6. Submit prompts containing sample email addresses and student IDs. Verify ingress redaction, no raw
   persistence, and aggregate-only telemetry.
7. Execute the 100-question supported set (100% cited and context-correct), 30-question unsafe set
   (100% safe referral), campus set (≥90% correct answer/follow-up), normal-load test (p95 ≤5 s),
   three-minute task test (≥85%), and usability test (≥80% satisfactory).

The HTTP shapes and response expectations are defined in [openapi.yaml](./contracts/openapi.yaml);
the source state and eligibility rules are in [data-model.md](./data-model.md).
