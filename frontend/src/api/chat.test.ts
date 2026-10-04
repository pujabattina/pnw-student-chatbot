import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiClientError } from "./client";
import { parseChatOutcome, submitChatQuestion } from "./chat";

const supported = {
  outcome: "supported",
  answer: "Registration closes on October 20.",
  citations: [
    {
      sourceId: "2e07f31e-3942-4bf3-95f2-90c0c8aa8f47",
      title: "Registration dates",
      url: "https://www.pnw.edu/registration/dates",
      locator: "Fall 2026 dates",
    },
  ],
  appliedContext: { academicTerm: "Fall 2026" },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("parseChatOutcome", () => {
  it("parses supported answers with citations and context", () => {
    expect(parseChatOutcome(supported)).toEqual(supported);
  });

  it("parses clarification outcomes and validates requested fields", () => {
    expect(
      parseChatOutcome({
        outcome: "clarification_needed",
        question: "Which campus?",
        missingFields: ["campus"],
      }),
    ).toEqual({
      outcome: "clarification_needed",
      question: "Which campus?",
      missingFields: ["campus"],
    });

    expect(() =>
      parseChatOutcome({
        outcome: "clarification_needed",
        question: "What context?",
        missingFields: ["studentId"],
      }),
    ).toThrow(ApiClientError);
  });

  it("parses referral outcomes with allowed reasons", () => {
    expect(
      parseChatOutcome({
        outcome: "referral",
        limitation: "I cannot access personal records.",
        reason: "account_specific",
        referrals: [{ name: "Registrar", url: "https://www.pnw.edu/registrar" }],
      }),
    ).toMatchObject({ outcome: "referral", reason: "account_specific" });
  });

  it("rejects malformed citations, URLs, and unknown outcomes", () => {
    expect(() =>
      parseChatOutcome({
        ...supported,
        citations: [{ ...supported.citations[0], url: "javascript:alert(1)" }],
      }),
    ).toThrow(ApiClientError);
    expect(() => parseChatOutcome({ outcome: "unknown" })).toThrow(ApiClientError);
  });
});

describe("submitChatQuestion", () => {
  it("posts to the versioned anonymous chat endpoint and parses the response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(supported), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const outcome = await submitChatQuestion({
      question: "When does registration close?",
      context: { academicTerm: "Fall 2026" },
    });

    expect(outcome).toEqual(supported);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/chat/answers",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        body: JSON.stringify({
          question: "When does registration close?",
          context: { academicTerm: "Fall 2026" },
        }),
      }),
    );
  });

  it("maps throttled and unavailable HTTP responses to safe errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "internal text" }), {
          status: 429,
          headers: { "X-Correlation-ID": "request-id" },
        }),
      ),
    );

    await expect(submitChatQuestion({ question: "Question" })).rejects.toMatchObject({
      name: "ApiClientError",
      status: 429,
      correlationId: "request-id",
      message: "Too many requests. Please wait a moment and try again.",
    });
  });

  it("reports transport and invalid JSON failures without exposing response content", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("private network detail")));
    await expect(submitChatQuestion({ question: "Question" })).rejects.toThrow(
      "Unable to reach the chat service.",
    );

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("private response body", { status: 200 })),
    );
    await expect(submitChatQuestion({ question: "Question" })).rejects.toThrow(
      "The chat service returned an invalid response.",
    );
  });
});
