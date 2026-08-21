export const CHAT_LOADING_MESSAGES = [
  "Searching verified DIU admission information…",
  "This may take a few moments. Please wait while we prepare a source-backed answer.",
  "Thanks for your patience — we’re still checking the relevant DIU information.",
] as const;

export function loadingMessageForElapsed(elapsedMs: number): string {
  if (elapsedMs < 3500) return CHAT_LOADING_MESSAGES[0];
  if (elapsedMs < 9000) return CHAT_LOADING_MESSAGES[1];
  return CHAT_LOADING_MESSAGES[2];
}
