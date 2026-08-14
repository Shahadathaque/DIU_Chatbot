import type { ChatRequest, ChatTurn, Language } from "@/types/api";

const MAX_HISTORY_TURNS = 6;

type HistoryMessage = Pick<ChatTurn, "role" | "content">;

export function buildChatRequest(
  message: string,
  language: Language,
  messages: HistoryMessage[],
  retryRequest?: ChatRequest | null,
): ChatRequest {
  const trimmed = message.trim();
  if (retryRequest) {
    return { ...retryRequest, message: trimmed };
  }
  return {
    message: trimmed,
    language,
    history: messages.slice(-MAX_HISTORY_TURNS).map(({ role, content }) => ({
      role,
      content,
    })),
  };
}
