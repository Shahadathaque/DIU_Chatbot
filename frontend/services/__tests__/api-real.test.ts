import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { REQUEST_TIMEOUT_MS } from "../api";

/**
 * Real-mode API client tests.
 *
 * These tests exercise frontend/services/api.ts against a mocked global
 * `fetch`, proving the real-mode request path: URL construction, JSON request
 * body, backend error-envelope parsing, and timeout/abort behavior. They never
 * require a running FastAPI server, so the frontend test suite stays
 * mock-safe. The existing mock fixtures remain the default for everything else.
 */

// api.ts reads these process env values at module load to decide mode and base
// URL, so stub them and reload the module for every test.
const ORIGINAL_API_URL = "http://api.test:9999";

async function loadRealApi() {
  vi.stubEnv("NEXT_PUBLIC_USE_MOCK_API", "false");
  vi.stubEnv("NEXT_PUBLIC_API_URL", ORIGINAL_API_URL);
  vi.resetModules();
  return await import("../api");
}

function installWindowShim() {
  // api.ts calls window.setTimeout/clearTimeout. Reference globals dynamically
  // so Vitest fake timers (which replace globalThis.setTimeout) take effect.
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      setTimeout: (
        handler: TimerHandler,
        timeout?: number,
        ...args: unknown[]
      ) => globalThis.setTimeout(handler, timeout, ...args),
      clearTimeout: (id?: number) => globalThis.clearTimeout(id),
    },
  });
}

function installFetchMock(
  response: Partial<Response>,
): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(async () => response as Response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  vi.useRealTimers();
  installWindowShim();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("real-mode API client", () => {
  it("builds the request URL from NEXT_PUBLIC_API_URL and the endpoint path", async () => {
    const { sendChatMessage } = await loadRealApi();
    const fetchMock = installFetchMock({
      ok: true,
      status: 200,
      json: async () => ({
        answer: "Answer.",
        sources: [],
        confidence: "high",
        language: "en",
      }),
    });

    await sendChatMessage({ message: "Hello", language: "en" });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${ORIGINAL_API_URL}/api/chat`);
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
  });

  it("sends the request payload as a JSON body", async () => {
    const { checkEligibility } = await loadRealApi();
    const fetchMock = installFetchMock({
      ok: true,
      status: 200,
      json: async () => ({
        status: "insufficient_information",
        reason: "Not enough information.",
      }),
    });

    const payload = {
      program: "cse",
      ssc_gpa: 4.5,
      hsc_gpa: 4.0,
      group: "Science",
      diploma: false,
    };
    await checkEligibility(payload);

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual(payload);
  });

  it("sends conversation history in the chat JSON payload", async () => {
    const { sendChatMessage } = await loadRealApi();
    const fetchMock = installFetchMock({
      ok: true,
      status: 200,
      json: async () => ({
        answer: "Answer.",
        sources: [],
        confidence: "high",
        language: "en",
      }),
    });
    const payload = {
      message: "in BDT",
      language: "en" as const,
      history: [
        { role: "user" as const, content: "What is the tuition fee of CSE?" },
        { role: "assistant" as const, content: "Previous answer." },
      ],
    };

    await sendChatMessage(payload);

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual(payload);
  });

  it("surfaces the backend error-envelope message on a failed request", async () => {
    const { sendChatMessage } = await loadRealApi();
    installFetchMock({
      ok: false,
      status: 422,
      json: async () => ({
        error: {
          code: "validation_error",
          message: "The message is too long.",
          details: [{ field: "message", message: "Too long." }],
        },
      }),
    });

    await expect(
      sendChatMessage({ message: "Hello", language: "en" }),
    ).rejects.toMatchObject({ status: 422, message: "The message is too long." });
  });

  it("falls back to a generic message when the error body has no envelope", async () => {
    const { sendChatMessage } = await loadRealApi();
    installFetchMock({ ok: false, status: 500, json: async () => ({}) });

    await expect(
      sendChatMessage({ message: "Hello", language: "en" }),
    ).rejects.toMatchObject({
      status: 500,
      message: "The admission service is temporarily unavailable.",
    });
  });

  it("falls back to a generic message when the error body is not JSON", async () => {
    const { sendChatMessage } = await loadRealApi();
    installFetchMock({
      ok: false,
      status: 503,
      json: async () => {
        throw new Error("not json");
      },
    });

    await expect(
      sendChatMessage({ message: "Hello", language: "en" }),
    ).rejects.toMatchObject({
      status: 503,
      message: "The admission service is temporarily unavailable.",
    });
  });

  it("aborts the request and reports a timeout when the server is silent", async () => {
    vi.useFakeTimers();
    const { sendChatMessage } = await loadRealApi();

    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init.signal?.addEventListener("abort", () =>
              reject(
                new DOMException("The operation was aborted.", "AbortError"),
              ),
            );
          }),
      ),
    );

    const pending = sendChatMessage({ message: "Hello", language: "en" });
    vi.advanceTimersByTime(REQUEST_TIMEOUT_MS + 1);

    await expect(pending).rejects.toMatchObject({
      message: "The request timed out. Please try again.",
    });
  });

  it("throws a reachability error when fetch rejects without a status", async () => {
    const { sendChatMessage } = await loadRealApi();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    await expect(
      sendChatMessage({ message: "Hello", language: "en" }),
    ).rejects.toMatchObject({
      message:
        "Could not reach the admission service. Check your connection and try again.",
    });
  });

  it("parses streamed chat tokens and the final response event", async () => {
    const { streamChatMessage } = await loadRealApi();
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"token":"Hello ","full":"Hello "}\n\n'));
        controller.enqueue(
          encoder.encode(
            'event: done\ndata: {"response":{"answer":"Hello world.","sources":[],"confidence":"high","language":"en"}}\n\n',
          ),
        );
        controller.close();
      },
    });
    installFetchMock({
      ok: true,
      status: 200,
      body: stream as unknown as ReadableStream<Uint8Array<ArrayBuffer>>,
    });
    const tokens: string[] = [];

    const response = await streamChatMessage(
      { message: "Hello", language: "en" },
      (token) => tokens.push(token),
    );

    expect(tokens).toEqual(["Hello "]);
    expect(response.answer).toBe("Hello world.");
  });
});
