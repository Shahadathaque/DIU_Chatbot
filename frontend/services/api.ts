import {
  mockCheckBackendHealth,
  mockCheckEligibility,
  mockGetPrograms,
  mockSendChatMessage,
} from "@/services/mock-api";
import type {
  ChatRequest,
  ChatResponse,
  EligibilityRequest,
  EligibilityResponse,
  HealthResponse,
  ProgramsResponse,
} from "@/types/api";

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);
const REQUEST_TIMEOUT_MS = 15_000;

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
        response.status >= 500
          ? "The admission service is temporarily unavailable."
          : "The request could not be completed.",
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
    : request<HealthResponse>("/health");
}
