import { ApiClientError, postJson } from "./client";

export type Campus = "Hammond" | "Westville";

export interface QuestionContext {
  campus?: Campus | null;
  college?: string | null;
  program?: string | null;
  course?: string | null;
  academicTerm?: string | null;
}

export interface ChatRequest {
  question: string;
  context?: QuestionContext | null;
}

export interface Citation {
  sourceId: string;
  title: string;
  url: string;
  locator?: string | null;
}

export interface Referral {
  name: string;
  url?: string | null;
  email?: string | null;
  phone?: string | null;
}

export interface SupportedAnswer {
  outcome: "supported";
  answer: string;
  citations: [Citation, ...Citation[]];
  appliedContext: QuestionContext;
}

export type MissingContextField = "campus" | "program" | "course" | "academicTerm";

export interface ClarificationNeeded {
  outcome: "clarification_needed";
  question: string;
  missingFields: MissingContextField[];
}

export type ReferralReason =
  | "unsupported"
  | "conflicting"
  | "outdated"
  | "account_specific"
  | "uninterpretable"
  | "timeout";

export interface ReferralOutcome {
  outcome: "referral";
  limitation: string;
  reason: ReferralReason;
  referrals: Referral[];
}

export type ChatOutcome = SupportedAnswer | ClarificationNeeded | ReferralOutcome;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseMissingContextField(value: unknown): MissingContextField | null {
  switch (value) {
    case "campus":
    case "program":
    case "course":
    case "academicTerm":
      return value;
    default:
      return null;
  }
}

function parseReferralReason(value: unknown): ReferralReason | null {
  switch (value) {
    case "unsupported":
    case "conflicting":
    case "outdated":
    case "account_specific":
    case "uninterpretable":
    case "timeout":
      return value;
    default:
      return null;
  }
}

function isOptionalString(value: unknown): value is string | null | undefined {
  return value === undefined || value === null || typeof value === "string";
}

function parseQuestionContext(value: unknown): QuestionContext | null {
  if (!isRecord(value)) return null;
  if (
    (value.campus !== undefined &&
      value.campus !== null &&
      value.campus !== "Hammond" &&
      value.campus !== "Westville") ||
    !isOptionalString(value.college) ||
    !isOptionalString(value.program) ||
    !isOptionalString(value.course) ||
    !isOptionalString(value.academicTerm)
  ) {
    return null;
  }

  return {
    campus: value.campus,
    college: value.college,
    program: value.program,
    course: value.course,
    academicTerm: value.academicTerm,
  };
}

function parseCitation(value: unknown): Citation | null {
  if (!isRecord(value)) return null;
  if (
    typeof value.sourceId !== "string" ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      value.sourceId,
    ) ||
    typeof value.title !== "string" ||
    typeof value.url !== "string" ||
    !isOptionalString(value.locator)
  ) {
    return null;
  }

  try {
    const url = new URL(value.url);
    if (url.protocol !== "https:" && url.protocol !== "http:") return null;
  } catch {
    return null;
  }

  return {
    sourceId: value.sourceId,
    title: value.title,
    url: value.url,
    locator: value.locator,
  };
}

function parseReferral(value: unknown): Referral | null {
  if (
    !isRecord(value) ||
    typeof value.name !== "string" ||
    !isOptionalString(value.url) ||
    !isOptionalString(value.email) ||
    !isOptionalString(value.phone)
  ) {
    return null;
  }
  if (value.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value.email)) return null;
  if (value.url) {
    try {
      const url = new URL(value.url);
      if (url.protocol !== "https:" && url.protocol !== "http:") return null;
    } catch {
      return null;
    }
  }

  return {
    name: value.name,
    url: value.url,
    email: value.email,
    phone: value.phone,
  };
}

export function parseChatOutcome(value: unknown): ChatOutcome {
  if (!isRecord(value)) {
    throw new ApiClientError("The chat service returned an invalid response.");
  }

  if (value.outcome === "supported" && typeof value.answer === "string") {
    const citations: Citation[] = [];
    if (Array.isArray(value.citations)) {
      for (const candidate of value.citations) {
        const citation = parseCitation(candidate);
        if (citation === null) {
          citations.length = 0;
          break;
        }
        citations.push(citation);
      }
    }
    const appliedContext = parseQuestionContext(value.appliedContext);
    const [firstCitation, ...remainingCitations] = citations;
    if (firstCitation !== undefined && appliedContext !== null) {
      return {
        outcome: "supported",
        answer: value.answer,
        citations: [firstCitation, ...remainingCitations],
        appliedContext,
      };
    }
  }

  if (value.outcome === "clarification_needed" && typeof value.question === "string") {
    const missingFields: MissingContextField[] = [];
    if (Array.isArray(value.missingFields)) {
      for (const candidate of value.missingFields) {
        const field = parseMissingContextField(candidate);
        if (field === null) {
          missingFields.length = 0;
          break;
        }
        missingFields.push(field);
      }
    }
    if (Array.isArray(value.missingFields) && missingFields.length === value.missingFields.length) {
      return {
        outcome: "clarification_needed",
        question: value.question,
        missingFields,
      };
    }
  }

  if (
    value.outcome === "referral" &&
    typeof value.limitation === "string" &&
    parseReferralReason(value.reason) !== null
  ) {
    const referrals: Referral[] = [];
    let validReferrals = Array.isArray(value.referrals);
    if (Array.isArray(value.referrals)) {
      for (const candidate of value.referrals) {
        const referral = parseReferral(candidate);
        if (referral === null) {
          validReferrals = false;
          break;
        }
        referrals.push(referral);
      }
    }
    const reason = parseReferralReason(value.reason);
    if (validReferrals && reason !== null) {
      return {
        outcome: "referral",
        limitation: value.limitation,
        reason,
        referrals,
      };
    }
  }

  throw new ApiClientError("The chat service returned an invalid response.");
}

export async function submitChatQuestion(request: ChatRequest): Promise<ChatOutcome> {
  const response = await postJson("/api/v1/chat/answers", request);
  return parseChatOutcome(response);
}
