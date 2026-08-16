"use client";

import { useEffect, useRef, useState } from "react";
import { SourceCard } from "@/components/chat/source-card";
import { SuggestedQuestions } from "@/components/chat/suggested-questions";
import { TypingIndicator } from "@/components/chat/typing-indicator";
import {
  ChatIcon,
  RefreshIcon,
  SendIcon,
  ShieldIcon,
  SparkleIcon,
  WarningIcon,
} from "@/components/ui/icons";
import {
  ApiError,
  isMockMode,
  sendChatMessage,
  streamChatMessage,
} from "@/services/api";
import { buildChatRequest } from "@/services/chat-request";
import {
  isRenderableAssistantMessage,
  removeMessageById,
} from "@/services/chat-state";
import type {
  ApiSource,
  ChatRequest,
  ChatRole,
  Confidence,
  Language,
} from "@/types/api";

interface Message {
  id: string;
  role: ChatRole;
  content: string;
  sources?: ApiSource[];
  confidence?: Confidence;
}

const languageLabels: Record<Language, string> = {
  en: "English",
  bn: "বাংলা",
  banglish: "Banglish",
};

function createId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function ChatExperience() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [language, setLanguage] = useState<Language>("en");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failedRequest, setFailedRequest] = useState<ChatRequest | null>(null);
  const scrollAnchorRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isLoading, error]);

  async function submitMessage(message: string, isRetry = false) {
    const trimmed = message.trim();
    if (!trimmed || isLoading) return;

    const request = buildChatRequest(
      trimmed,
      language,
      messages,
      isRetry ? failedRequest : null,
    );

    if (!isRetry) {
      setMessages((current) => [
        ...current,
        { id: createId(), role: "user", content: trimmed },
      ]);
    }
    setInput("");
    setError(null);
    setFailedRequest(null);
    setIsLoading(true);

    let pendingAssistantId: string | null = null;

    try {
      if (!isMockMode) {
        const assistantId = createId();
        pendingAssistantId = assistantId;
        setMessages((current) => [
          ...current,
          { id: assistantId, role: "assistant", content: "" },
        ]);
        const response = await streamChatMessage(request, (_token, full) => {
          setMessages((current) =>
            current.map((item) =>
              item.id === assistantId ? { ...item, content: full } : item,
            ),
          );
        });
        setMessages((current) =>
          current.map((item) =>
            item.id === assistantId
              ? {
                  ...item,
                  content: response.answer,
                  sources: response.sources,
                  confidence: response.confidence,
                }
              : item,
          ),
        );
      } else {
        const response = await sendChatMessage(request);
        setMessages((current) => [
          ...current,
          {
            id: createId(),
            role: "assistant",
            content: response.answer,
            sources: response.sources,
            confidence: response.confidence,
          },
        ]);
      }
    } catch (requestError) {
      if (pendingAssistantId) {
        const failedAssistantId = pendingAssistantId;
        setMessages((current) =>
          removeMessageById(current, failedAssistantId),
        );
      }
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Something went wrong while getting an answer.",
      );
      setFailedRequest(request);
    } finally {
      setIsLoading(false);
      window.setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }

  function resetConversation() {
    setMessages([]);
    setError(null);
    setFailedRequest(null);
    setInput("");
    textareaRef.current?.focus();
  }

  return (
    <div className="page-shell py-6 sm:py-9">
      <div className="grid min-h-[720px] overflow-hidden rounded-[1.5rem] border border-line bg-white shadow-soft lg:grid-cols-[300px_1fr]">
        <aside className="hidden border-r border-line bg-[#f4f8f5] p-6 lg:flex lg:flex-col">
          <span className="grid size-11 place-items-center rounded-2xl bg-brand text-white shadow-[0_8px_20px_rgba(8,120,63,0.2)]">
            <ChatIcon size={21} />
          </span>
          <h1 className="mt-5 text-xl font-bold tracking-[-0.03em]">Admission assistant</h1>
          <p className="mt-2 text-sm leading-6 text-muted">
            Ask about requirements, costs, documents, scholarships, dates, or the
            application process.
          </p>
          <div className="mt-7 rounded-2xl border border-emerald-100 bg-white p-4">
            <div className="flex items-center gap-2 text-xs font-bold text-brand-dark">
              <ShieldIcon size={15} />
              Answer transparency
            </div>
            <p className="mt-2 text-xs leading-5 text-muted">
              Source links appear only when the backend provides them.
            </p>
          </div>
          <div className="mt-auto pt-8">
            <div className="flex items-center gap-2 text-xs font-semibold text-muted">
              <span
                className={`size-2 rounded-full ${isMockMode ? "bg-amber-400" : "bg-emerald-500"}`}
              />
              {isMockMode ? "Using demo responses" : "Connected to research API"}
            </div>
          </div>
        </aside>

        <section className="flex min-h-[720px] min-w-0 flex-col" aria-label="Chat">
          <div className="flex min-h-[68px] items-center justify-between gap-3 border-b border-line px-4 sm:px-6">
            <div>
              <h1 className="text-sm font-bold lg:hidden">Admission assistant</h1>
              <p className="hidden text-xs text-muted sm:block lg:block">
                Ask a DIU admission question
              </p>
            </div>
            <div className="flex items-center gap-2">
              <label className="sr-only" htmlFor="chat-language">
                Response language
              </label>
              <select
                className="h-10 rounded-xl border border-line bg-white px-3 text-xs font-bold text-ink"
                id="chat-language"
                onChange={(event) => setLanguage(event.target.value as Language)}
                value={language}
              >
                {Object.entries(languageLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <button
                className="inline-flex h-10 items-center gap-2 rounded-xl border border-line px-3 text-xs font-bold text-muted hover:bg-canvas hover:text-ink disabled:opacity-40"
                disabled={messages.length === 0 && !error}
                onClick={resetConversation}
                type="button"
              >
                <RefreshIcon size={15} />
                <span className="hidden sm:inline">New chat</span>
              </button>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto bg-canvas/50 px-4 py-6 sm:px-7 sm:py-8">
            <div className="mx-auto max-w-3xl">
              {messages.length === 0 && !isLoading ? (
                <div className="flex min-h-[410px] flex-col justify-center py-8">
                  <span className="grid size-12 place-items-center rounded-2xl bg-brand-soft text-brand">
                    <SparkleIcon size={23} />
                  </span>
                  <h2 className="text-balance mt-6 text-2xl font-semibold tracking-[-0.04em] sm:text-3xl">
                    What would you like to know about DIU admission?
                  </h2>
                  <p className="mt-3 max-w-xl text-sm leading-6 text-muted">
                    Ask in English, Bangla, or Banglish. Try one of these common questions
                    to begin.
                  </p>
                  <div className="mt-7">
                    <SuggestedQuestions
                      disabled={isLoading}
                      onSelect={(question) => submitMessage(question)}
                    />
                  </div>
                </div>
              ) : (
                <div className="space-y-7" aria-live="polite">
                  {messages.map((message) =>
                    message.role === "user" ? (
                      <div className="flex justify-end" key={message.id}>
                        <div className="max-w-[88%] rounded-2xl rounded-br-md bg-brand px-4 py-3 text-sm leading-6 text-white sm:max-w-[75%]">
                          {message.content}
                        </div>
                      </div>
                    ) : isRenderableAssistantMessage(message) ? (
                      <div className="flex items-start gap-3" key={message.id}>
                        <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-brand text-white">
                          <SparkleIcon size={15} />
                        </span>
                        <div className="min-w-0 max-w-[calc(100%-2.75rem)] sm:max-w-[85%]">
                          <div className="rounded-2xl rounded-tl-md border border-line bg-white px-4 py-4 text-sm leading-7 text-ink shadow-sm sm:px-5">
                            <div className="whitespace-pre-wrap">{message.content}</div>
                          </div>
                          {message.sources?.length ? (
                            <div className="mt-3">
                              <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
                                Sources provided by the assistant
                              </p>
                              <div className="grid gap-2 sm:grid-cols-2">
                                {message.sources.map((source, index) => (
                                  <SourceCard
                                    index={index}
                                    key={`${source.url}-${index}`}
                                    source={source}
                                  />
                                ))}
                              </div>
                            </div>
                          ) : (
                            <p className="mt-2 text-[11px] font-medium text-muted">
                              No source citation was provided with this answer.
                            </p>
                          )}
                        </div>
                      </div>
                    ) : null,
                  )}
                  {isLoading ? <TypingIndicator /> : null}
                  {error ? (
                    <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900" role="alert">
                      <div className="flex items-start gap-3">
                        <WarningIcon className="mt-0.5 shrink-0" size={18} />
                        <div>
                          <p className="font-bold">Answer unavailable</p>
                          <p className="mt-1 leading-6 text-red-800">{error}</p>
                          {failedRequest ? (
                            <button
                              className="mt-3 rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-bold hover:bg-red-100"
                              onClick={() => submitMessage(failedRequest.message, true)}
                              type="button"
                            >
                              Try again
                            </button>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  ) : null}
                  <div ref={scrollAnchorRef} />
                </div>
              )}
            </div>
          </div>

          <div className="border-t border-line bg-white p-3 sm:p-5">
            <form
              className="mx-auto max-w-3xl"
              onSubmit={(event) => {
                event.preventDefault();
                submitMessage(input);
              }}
            >
              <div className="flex items-end gap-2 rounded-2xl border border-line bg-white p-2 shadow-[0_6px_24px_rgba(18,46,33,0.08)] focus-within:border-emerald-400">
                <label className="sr-only" htmlFor="chat-input">
                  Your admission question
                </label>
                <textarea
                  className="max-h-32 min-h-11 flex-1 resize-none bg-transparent px-3 py-3 text-sm leading-5 text-ink outline-none placeholder:text-slate-400"
                  disabled={isLoading}
                  id="chat-input"
                  maxLength={2000}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      submitMessage(input);
                    }
                  }}
                  placeholder="Ask about admission, requirements, fees..."
                  ref={textareaRef}
                  rows={1}
                  value={input}
                />
                <button
                  aria-label="Send message"
                  className="grid size-11 shrink-0 place-items-center rounded-xl bg-brand text-white transition hover:bg-brand-dark disabled:cursor-not-allowed disabled:bg-slate-300"
                  disabled={isLoading || !input.trim()}
                  type="submit"
                >
                  <SendIcon size={18} />
                </button>
              </div>
              <p className="mt-2 text-center text-[10px] leading-4 text-muted">
                AI can make mistakes. Confirm important details with official DIU sources.
              </p>
            </form>
          </div>
        </section>
      </div>
    </div>
  );
}
