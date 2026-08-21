import { describe, expect, it } from "vitest";
import { CHAT_LOADING_MESSAGES, loadingMessageForElapsed } from "@/services/chat-loading";

describe("chat loading messages", () => {
  it("progresses at the intended thresholds", () => {
    expect(loadingMessageForElapsed(0)).toBe(CHAT_LOADING_MESSAGES[0]);
    expect(loadingMessageForElapsed(3499)).toBe(CHAT_LOADING_MESSAGES[0]);
    expect(loadingMessageForElapsed(3500)).toBe(CHAT_LOADING_MESSAGES[1]);
    expect(loadingMessageForElapsed(8999)).toBe(CHAT_LOADING_MESSAGES[1]);
    expect(loadingMessageForElapsed(9000)).toBe(CHAT_LOADING_MESSAGES[2]);
  });
});
