import type {
  ChatRequest,
  ChatResponse,
  EligibilityRequest,
  EligibilityResponse,
  Program,
} from "@/types/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const USE_MOCK_API = process.env.NEXT_PUBLIC_USE_MOCK_API !== "false";

const mockSources = [
  {
    title: "DIU Admission Information",
    url: "https://daffodilvarsity.edu.bd/admission",
  },
];

function delay(milliseconds = 550) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
    signal: AbortSignal.timeout(10000),
  });

  if (!response.ok) {
    throw new Error(`Backend request failed (${response.status})`);
  }

  return response.json() as Promise<T>;
}

export async function sendChatMessage(payload: ChatRequest): Promise<ChatResponse> {
  if (USE_MOCK_API) {
    await delay();
    const isBangla = payload.language === "bn";
    return {
      answer: isBangla
        ? "DIU admission সম্পর্কে তথ্যের জন্য official admission page দেখুন। আপনি program, eligibility বা documents সম্পর্কে জিজ্ঞেস করতে পারেন।"
        : "DIU admission support is ready. Ask about programs, eligibility, documents, scholarships, or how to apply. This demo response is coming from the frontend mock layer.",
      sources: mockSources,
      confidence: "medium",
    };
  }

  return request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function checkEligibility(
  payload: EligibilityRequest,
): Promise<EligibilityResponse> {
  if (USE_MOCK_API) {
    await delay(650);
    return {
      status: "insufficient_information",
      reason:
        "The eligibility rule engine is not connected in mock mode. Connect the FastAPI backend for an official assessment.",
      source: "https://daffodilvarsity.edu.bd/admission",
    };
  }

  return request<EligibilityResponse>("/api/eligibility", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getPrograms(): Promise<Program[]> {
  if (USE_MOCK_API) {
    await delay(400);
    return [
      { name: "Computer Science and Engineering", degree: "B.Sc.", faculty: "FSIT" },
      { name: "Software Engineering", degree: "B.Sc.", faculty: "FSIT" },
      { name: "Business Administration", degree: "BBA", faculty: "FBE" },
    ];
  }

  return request<Program[]>("/api/programs");
}

export async function checkBackendHealth(): Promise<boolean> {
  if (USE_MOCK_API) return true;
  try {
    await request("/health");
    return true;
  } catch {
    return false;
  }
}

export const apiMode = USE_MOCK_API ? "mock" : "real";
