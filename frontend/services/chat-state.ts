import type { ChatRole } from "@/types/api";

interface ChatStateMessage {
  id: string;
  role: ChatRole;
  content: string;
}

export function removeMessageById<T extends ChatStateMessage>(
  messages: T[],
  id: string,
): T[] {
  return messages.filter((message) => message.id !== id);
}

export function isRenderableAssistantMessage(
  message: ChatStateMessage,
): boolean {
  return message.role === "assistant" && message.content.trim().length > 0;
}
