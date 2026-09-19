# Feature Specification: PNW Student Information Chatbot

**Feature Branch**: `002-pnw-student-chatbot`

**Created**: 2026-09-15

**Status**: Draft

**Input**: Stakeholder, student-interview, and initial-corpus findings for a Purdue University
Northwest (PNW) chatbot that helps students find accurate general university information.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Receive a Grounded University Answer (Priority: P1)

A PNW student asks a general question about a university policy, rule, deadline, procedure,
program, course, service, or contact and receives a direct, plain-language answer backed by a
current approved PNW source.

**Why this priority**: Students currently search several pages, external search results, emails,
and staff contacts to find answers. A reliable answer with its official source is the core value.

**Independent Test**: Ask representative questions about paying or appealing parking tickets,
registration and add/drop dates, academic standing, grade appeals, academic integrity, graduate
programs, prerequisites, and university contacts. Verify every answer against its cited approved
source.

**Acceptance Scenarios**:

1. **Given** approved PNW information supports a student's general question, **When** the student
   submits the question, **Then** the chatbot gives a clear answer and links to the relevant
   official source.
2. **Given** a student asks about an academic deadline, **When** an active source identifies the
   applicable term, **Then** the chatbot states that term with the deadline and does not present a
   deadline from another or expired term as current.
3. **Given** the answer is in a relevant linked document or page section, **When** that material is
   approved and available, **Then** the chatbot uses the applicable information rather than only
   sending the student through a chain of links.

---

### User Story 2 - Receive Context-Relevant Academic Guidance (Priority: P2)

A student asking about programs, courses, prerequisites, or availability receives a source-backed
answer appropriate to their campus, college, program, course, and term context, or is asked for
the context that is required to answer safely.

**Why this priority**: Interviews identify confusion between the Hammond and Westville campuses,
colleges, offerings, and multi-level course prerequisites.

**Independent Test**: Ask campus- and program-dependent questions with and without campus,
program, course, or term context. Verify that the chatbot either asks a focused follow-up or gives
an answer matching the relevant official catalog or PNW source.

**Acceptance Scenarios**:

1. **Given** a question has a different answer for Hammond and Westville, **When** the student has
   not identified a campus, **Then** the chatbot asks which campus applies before answering.
2. **Given** a student provides the needed campus, program, course, and term context, **When** they
   ask about a listed prerequisite, offering, or program, **Then** the chatbot supplies a
   source-backed summary for that context.
3. **Given** a student asks whether a degree program exists, **When** approved program information
   does not list that program, **Then** the chatbot does not infer availability and directs the
   student to the applicable official program information or office.

---

### User Story 3 - Receive a Safe Referral (Priority: P3)

A student whose question is unsupported, conflicting, account-specific, or requires an official
decision receives a clear statement that the chatbot cannot provide a reliable answer and is
directed to an appropriate PNW office, advisor, or support channel.

**Why this priority**: Stakeholders explicitly require the chatbot not to give incorrect policy
information, while student interviews show that registration errors, degree planning, and similar
personal issues need human help.

**Independent Test**: Submit unsupported, ambiguous, conflicting-source, and account-specific
questions. Verify that the chatbot avoids inventing an answer and provides a relevant referral.

**Acceptance Scenarios**:

1. **Given** no reliable approved source supports an answer, **When** the student asks the
   question, **Then** the chatbot explicitly says it cannot provide a reliable answer and refers
   the student to an appropriate PNW office, advisor, or support channel.
2. **Given** a student asks the chatbot to resolve a personal registration error, determine degree
   completion, or make another account-specific decision, **When** the chatbot lacks the student's
   official record or decision authority, **Then** it does not make a determination and gives a
   safe referral.
3. **Given** approved sources conflict or are outdated, **When** the chatbot cannot determine an
   authoritative current answer, **Then** it identifies the limitation and refers the student
   instead of choosing or combining unsupported information.

### Edge Cases

- A source gives a deadline without an academic term, or the term is no longer active.
- A linked page, PDF, table, expandable section, or attachment cannot be interpreted reliably.
- A question includes an unfamiliar registration error, campus, course, program, or policy name.
- A student asks for an action on their personal academic, financial, housing, disciplinary,
  parking, or registration record.
- A question involves a sudden room change, individual advising decision, or other information not
  supported by the approved general-information corpus.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST accept natural-language questions from students about general PNW
  policies, rules, deadlines, procedures, programs, courses, services, and contacts.
- **FR-002**: The system MUST provide a concise plain-language answer only when current approved
  university information reliably supports that answer.
- **FR-003**: The system MUST identify and link to at least one relevant approved official PNW
  source with every supported answer.
- **FR-004**: The system MUST distinguish active, superseded, and term-specific approved
  information before presenting a policy, rule, procedure, or deadline as current.
- **FR-005**: The system MUST ask for campus context before answering when approved information
  differs between Hammond and Westville.
- **FR-006**: The system MUST ask a focused follow-up question when missing program, course,
  campus, academic-term, or other context would materially change the answer.
- **FR-007**: The system MUST provide source-backed summaries of program information and course
  prerequisites only when the applicable official information supports the summary.
- **FR-008**: The system MUST state that it cannot provide a reliable answer and provide an
  appropriate referral when no reliable supported answer is available.
- **FR-009**: The system MUST NOT present unsupported information as official PNW policy, rule,
  deadline, or procedure.
- **FR-010**: The system MUST NOT decide, change, or represent an individual student's record,
  eligibility, enrollment, degree progress, financial aid, discipline, housing status, parking
  account, or other account-specific matter; it MUST provide a safe referral instead.
- **FR-011**: The system MUST identify conflicting or insufficient approved information as
  unresolved rather than selecting or synthesizing an answer without a reliable basis.
- **FR-012**: The system MUST use only source material whose subject-matter owner has approved it
  for the answer corpus and can identify whether it is active, superseded, and term- or
  campus-specific.
- **FR-013**: Authorized university reviewers MUST be able to review each source available to the
  chatbot, its approval status, owner, effective context, and active or superseded status.
- **FR-014**: The system MUST associate referrals with an appropriate PNW office, advisor, or
  support channel for the student's question category when that information is available in the
  approved corpus.

### Key Entities *(include if feature involves data)*

- **Student Question**: A natural-language request with optional context such as campus, college,
  program, course, academic term, and an error message.
- **Approved Source**: An official PNW webpage, catalog entry, policy, PDF, table, attachment, or
  linked university document approved for use; includes its owner, link, approval status, effective
  context, and active or superseded status.
- **Supported Answer**: A plain-language response tied to one or more Approved Sources, including
  the supporting links and applicable campus, program, course, and term context.
- **Referral**: A response that explains why a reliable answer is unavailable or inappropriate and
  identifies an appropriate PNW office, advisor, or support channel.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a pre-launch review set of at least 100 representative supported questions, 100%
  of answers cite at least one relevant approved official source.
- **SC-002**: In that review set, 100% of policy, rule, deadline, and procedure answers match the
  cited approved source and its applicable campus and term context.
- **SC-003**: In a test set of at least 30 unsupported, conflicting, outdated, or account-specific
  questions, 100% of responses avoid an unsupported answer and provide a clear limitation plus an
  appropriate referral.
- **SC-004**: At least 85% of participating students can obtain a source-backed answer or an
  appropriate referral for a representative general-information task within three minutes, without
  separately navigating PNW webpages.
- **SC-005**: At least 80% of participating students rate answer clarity and source usefulness as
  satisfactory or better in usability testing.
- **SC-006**: At least 90% of campus-dependent questions in the representative review set either
  receive a campus-appropriate answer or prompt for campus before an answer is provided.

## Assumptions

- The first release serves students seeking general university information and excludes personal
  records, authenticated actions, and individualized advising or case decisions.
- Official PNW webpages, current catalog entries, approved policy documents, and official PNW PDFs
  are candidate sources; only material approved under FR-012 may support answers.
- Initial high-value topics are parking and fees, registration and academic schedules, academic
  standing and appeals, financial-aid deadlines, academic integrity, accessibility, programs,
  prerequisites, and university contacts.
- The Dean of Students Office resolves source conflicts that the office owning the subject matter
  cannot resolve.
- The approved corpus must preserve information contained in relevant linked pages, document
  sections, tables, PDFs, and attachments so answers remain grounded in applicable material.

## Out of Scope

- Changing a student's registration, schedule, room, financial aid, academic record, degree audit,
  parking account, or other university account.
- Providing individualized legal, medical, financial, disciplinary, or academic-advising decisions.
- Treating third-party search results, student reports, uncited content, or unapproved PNW
  materials as official university guidance.
