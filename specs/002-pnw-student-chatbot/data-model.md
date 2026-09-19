# Data Model

## Source governance

### Source

Canonical approved-content identity.

| Field | Rules |
|---|---|
| `id` | UUID primary key |
| `canonical_url` | Unique normalized HTTPS URL |
| `title`, `media_type` | Required display and parsing metadata |
| `owner_subject`, `owner_organization` | Required institutional ownership |
| `current_version_id` | References latest fetched version |
| `created_at` | Immutable timestamp |

### SourceVersion

Immutable snapshot of fetched source content.

| Field | Rules |
|---|---|
| `id`, `source_id` | UUID and required source relation |
| `content_fingerprint` | Required content hash; unique per source/version |
| `captured_at`, `change_detected_at`, `withdrawn_at` | Lifecycle timestamps |
| `extracted_content_ref` | Protected extracted-content location |
| `parse_status` | `interpretable` or `uninterpretable`; uninterpretable is ineligible |

### SourceApproval

The retrieval eligibility record for a source version.

| Field | Rules |
|---|---|
| `id`, `source_version_id` | Required relation |
| `status` | `candidate`, `pending_review`, `approved`, `disabled`, `rejected`, `superseded` |
| `approver_subject`, `approved_at` | Required when approved or reapproved |
| `disabled_at`, `disable_reason` | Required when disabled |
| `effective_context` | Campus, college, program, course, academic-term lists and optional effective date range |

Only an `approved` version that is the source’s current version, has interpretable content, and
matches the requested effective context is retrievable.

**Transitions**: `candidate → pending_review → approved`; a change, withdrawal, parse failure,
expiry, or unresolved conflict performs `approved → disabled`; `disabled → pending_review → approved`
requires owner reapproval. `rejected` and `superseded` cannot be reactivated; a replacement version
starts as `candidate`.

### SourceFragment

Citable source portion used for retrieval.

`id`, `source_version_id`, `locator` (page/section/table/attachment), extracted text, extraction
status, lexical-search vector, embedding reference, and display excerpt. Fragments inherit version
eligibility and are never independently approved.

## Referrals and reviewer authorization

### Referral

An active, scoped PNW escalation channel: `id`, category, name, description, URL, email/phone,
campus/term context, `active`, and supporting `source_approval_id`. A referral is displayed only if
it is active and its source approval is eligible.

### UserRoleAssignment

`institutional_subject`, role, active, assigned-at/by. The unique subject/role relationship grants
only one of `reviewer`, `source_owner`, `admin`, or `conflict_resolver`. Requests authenticate through
the institutional identity provider, but authorization is evaluated server-side.

### ReviewerAuditEvent

Append-only, access-controlled evidence of privileged action: actor subject, role, action, target
type/id, timestamp, correlation ID, and before/after lifecycle status/context. It contains no student
question or answer content.

### IngestionJob

Durable worker queue record: `id`, source ID, job type (`fetch`, `parse`, `embed`, `change_check`),
status (`queued`, `claimed`, `completed`, `failed`), attempt count, available-at, claimed-at/by, and
last safe error code. Workers claim records transactionally; job payloads contain only source IDs and
configuration, never student questions.

## Ephemeral student interaction and metrics

### AnswerDecision

Not persisted. A request-scoped object with correlation ID, `supported`/`clarification_needed`/
`referral` outcome, reason, applied context, cited source-version IDs, and referral IDs. Student
prompt and generated prose are intentionally absent from storage.

### TelemetryAggregate

Allow-listed aggregate record: time bucket, outcome/reason count, latency bucket/count, category or
missing-context counter, source-count bucket, and PII-redaction counter. It cannot contain question
text, response text, account identifier, IP address, or a unique conversation identifier.

## Relationships

`Source 1—N SourceVersion 1—N SourceFragment`; `SourceVersion 1—N SourceApproval`; an eligible
approval may support `Referral`; `UserRoleAssignment 1—N ReviewerAuditEvent`. An ephemeral
`AnswerDecision` references eligible `SourceVersion` and `Referral` records only. `Source 1—N
IngestionJob` provides durable ingestion and change detection.
