import { describe, expect, it } from "vitest";
import {
  isRenderableAssistantMessage,
  removeMessageById,
} from "../chat-state";

describe("chat UI state", () => {
  it("removes a failed streaming placeholder", () => {
    const messages = [
      { id: "user", role: "user" as const, content: "Question" },
      { id: "pending", role: "assistant" as const, content: "" },
    ];

    expect(removeMessageById(messages, "pending")).toEqual([messages[0]]);
  });

  it("does not render an empty assistant message as an answer", () => {
    expect(
      isRenderableAssistantMessage({
        id: "pending",
        role: "assistant",
        content: "   ",
      }),
    ).toBe(false);
    expect(
      isRenderableAssistantMessage({
        id: "answer",
        role: "assistant",
        content: "Grounded answer",
      }),
    ).toBe(true);
  });
});
