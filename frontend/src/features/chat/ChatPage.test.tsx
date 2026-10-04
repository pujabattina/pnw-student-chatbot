import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ChatPage from "./ChatPage";

const supportedAnswer = {
  outcome: "supported",
  answer: "Fall registration closes on October 20.",
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

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ChatPage", () => {
  it("sends a student's question to the anonymous chat endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(supportedAnswer));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<ChatPage />);
    await user.type(screen.getByRole("textbox", { name: /your question/i }), "When does Fall registration close?");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/chat/answers",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
        body: JSON.stringify({ question: "When does Fall registration close?" }),
      }),
    );
  });

  it("renders the answer and its official citation", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(supportedAnswer)));
    const user = userEvent.setup();

    render(<ChatPage />);
    await user.type(screen.getByRole("textbox", { name: /your question/i }), "When does registration close?");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByText(supportedAnswer.answer)).toBeInTheDocument();
    const citation = screen.getByRole("link", { name: /registration dates/i });
    expect(citation).toHaveAttribute("href", supportedAnswer.citations[0].url);
  });

  it("shows a loading state while the answer is pending", async () => {
    let resolveRequest: ((response: Response) => void) | undefined;
    const request = new Promise<Response>((resolve) => {
      resolveRequest = resolve;
    });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(request));
    const user = userEvent.setup();

    render(<ChatPage />);
    await user.type(screen.getByRole("textbox", { name: /your question/i }), "Where can I find registration dates?");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(screen.getByRole("status")).toHaveTextContent(/thinking|loading/i);
    resolveRequest?.(jsonResponse(supportedAnswer));
    expect(await screen.findByText(supportedAnswer.answer)).toBeInTheDocument();
  });

  it("shows an unavailable message when the chat service cannot respond", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "Service is temporarily unavailable." }, 503)),
    );
    const user = userEvent.setup();

    render(<ChatPage />);
    await user.type(screen.getByRole("textbox", { name: /your question/i }), "When does registration close?");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByText(/temporarily unavailable|try again/i)).toBeInTheDocument();
  });
});
