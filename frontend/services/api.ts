import {
  mockCheckBackendHealth,
  mockCheckEligibility,
  mockGetPrograms,
  mockGetSources,
  mockSendChatMessage,
} from "@/services/mock-api";
import type {
  ChatRequest,
  ChatResponse,
  EligibilityRequest,
  EligibilityResponse,
  HealthResponse,
  ProgramsResponse,
  SourcesResponse,
} from "@/types/api";

// NEXT_PUBLIC_API_URL is injected at build time for browser bundles. Keep a
// localhost fallback so mock/local development still works without setup.
const API_URL = (
  process.env.NEXT_PUBLIC_API_URL?.trim() || "http://localhost:8000"
).replace(/\/+$/, "");
export const REQUEST_TIMEOUT_MS = 90_000;
export const STREAM_REQUEST_TIMEOUT_MS = 120_000;

export const isMockMode = process.env.NEXT_PUBLIC_USE_MOCK_API !== "false";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (
      body &&
      typeof body === "object" &&
      "error" in body &&
      (body as { error?: { message?: unknown } }).error &&
      typeof (body as { error: { message?: unknown } }).error.message === "string"
    ) {
      return (body as { error: { message: string } }).error.message;
    }
  } catch {
    // Fall through to the generic message when the body is not JSON.
  }
  return response.status >= 500
    ? "The admission service is temporarily unavailable."
    : "The request could not be completed.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new ApiError(
        await extractErrorMessage(response),
        response.status,
      );
    }

    try {
      return (await response.json()) as T;
    } catch {
      throw new ApiError("The service returned an unreadable response.");
    }
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("The request timed out. Please try again.");
    }
    throw new ApiError(
      "Could not reach the admission service. Check your connection and try again.",
    );
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function sendChatMessage(
  payload: ChatRequest,
): Promise<ChatResponse> {
  const response = isMockMode
    ? await mockSendChatMessage(payload)
    : await request<ChatResponse>("/api/chat", {
        method: "POST",
        body: JSON.stringify(payload),
      });

  if (!response.answer?.trim()) {
    throw new ApiError("The assistant returned an empty answer. Please try again.");
  }
  return response;
}

export async function streamChatMessage(
  payload: ChatRequest,
  onToken: (token: string, full: string) => void,
): Promise<ChatResponse> {
  if (isMockMode) return sendChatMessage(payload);

  const controller = new AbortController();
  const timeout = window.setTimeout(
    () => controller.abort(),
    STREAM_REQUEST_TIMEOUT_MS,
  );
  try {
    const response = await fetch(`${API_URL}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new ApiError(await extractErrorMessage(response), response.status);
    }
    if (!response.body) throw new ApiError("The service returned no stream.");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let completed: ChatResponse | null = null;

    const consume = (block: string) => {
      let event = "message";
      const dataLines: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (!dataLines.length) return;
      const data = JSON.parse(dataLines.join("\n")) as {
        token?: string;
        full?: string;
        response?: ChatResponse;
        error?: { message?: string };
      };
      if (event === "error") {
        throw new ApiError(
          data.error?.message || "The admission service was interrupted. Please try again.",
        );
      }
      if (data.token) onToken(data.token, data.full ?? data.token);
      if (event === "done" && data.response) completed = data.response;
    };

    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) consume(block);
      if (done) break;
    }
    if (buffer.trim()) consume(buffer);
    const finalResponse = completed as ChatResponse | null;
    if (!finalResponse || !finalResponse.answer?.trim()) {
      throw new ApiError("The assistant returned an incomplete answer.");
    }
    return finalResponse;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("The request timed out. Please try again.");
    }
    throw new ApiError("Could not reach the admission service. Check your connection and try again.");
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function checkEligibility(
  payload: EligibilityRequest,
): Promise<EligibilityResponse> {
  const response = isMockMode
    ? await mockCheckEligibility(payload)
    : await request<EligibilityResponse>("/api/eligibility", {
        method: "POST",
        body: JSON.stringify(payload),
      });

  if (!response.status || !response.reason?.trim()) {
    throw new ApiError("The eligibility service returned an incomplete result.");
  }
  return response;
}

export async function getPrograms(): Promise<ProgramsResponse> {
  const response = isMockMode
    ? await mockGetPrograms()
    : await request<ProgramsResponse>("/api/programs");

  if (!Array.isArray(response.programs)) {
    throw new ApiError("The program service returned an invalid list.");
  }
  return response;
}

export function checkBackendHealth(): Promise<HealthResponse> {
  return isMockMode
    ? mockCheckBackendHealth()
    : request<HealthResponse>("/api/live");
}

export async function getSources(): Promise<SourcesResponse> {
  const response = isMockMode
    ? await mockGetSources()
    : await request<SourcesResponse>("/api/sources");

  if (!Array.isArray(response.sources)) {
    throw new ApiError("The source service returned an invalid list.");
  }
  return response;
}
