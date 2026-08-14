import { describe, expect, it } from "vitest";
import { buildChatRequest } from "../chat-request";

describe("chat request history", () => {
  it("includes the six most recent conversation turns", () => {
    const messages = Array.from({ length: 8 }, (_, index) => ({
      role: index % 2 === 0 ? ("user" as const) : ("assistant" as const),
      content: `turn-${index}`,
    }));

    const request = buildChatRequest("  follow up  ", "en", messages);

    expect(request).toEqual({
      message: "follow up",
      language: "en",
      history: messages.slice(2),
    });
  });

  it("preserves the failed request history when retrying", () => {
    const failed = {
      message: "in BDT",
      language: "en" as const,
      history: [
        { role: "user" as const, content: "What is the tuition fee of CSE?" },
        { role: "assistant" as const, content: "Previous answer." },
      ],
    };

    const retry = buildChatRequest(
      failed.message,
      "bn",
      [{ role: "user", content: "A newer UI turn" }],
      failed,
    );

    expect(retry).toEqual(failed);
  });
});
