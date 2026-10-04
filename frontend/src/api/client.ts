export class ApiClientError extends Error {
  readonly status: number | undefined;
  readonly correlationId: string | undefined;

  constructor(message: string, status?: number, correlationId?: string) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.correlationId = correlationId;
  }
}

export async function postJson(path: string, body: unknown): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch {
    throw new ApiClientError("Unable to reach the chat service.");
  }

  const correlationId = response.headers.get("X-Correlation-ID") ?? undefined;
  if (!response.ok) {
    const message =
      response.status === 429
        ? "Too many requests. Please wait a moment and try again."
        : response.status >= 500
          ? "The chat service is temporarily unavailable. Please try again."
          : "The chat request could not be processed.";
    throw new ApiClientError(message, response.status, correlationId);
  }

  try {
    return await response.json();
  } catch {
    throw new ApiClientError(
      "The chat service returned an invalid response.",
      response.status,
      correlationId,
    );
  }
}
