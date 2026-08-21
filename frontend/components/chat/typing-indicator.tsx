"use client";

import { useEffect, useState } from "react";
import { SparkleIcon } from "@/components/ui/icons";
import { loadingMessageForElapsed } from "@/services/chat-loading";

export function TypingIndicator() {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const startedAt = Date.now();
    const interval = window.setInterval(() => setElapsed(Date.now() - startedAt), 500);
    return () => window.clearInterval(interval);
  }, []);

  return (
    <div className="flex items-end gap-3" aria-atomic="true" aria-live="polite" role="status">
      <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-brand text-white">
        <SparkleIcon size={15} />
      </span>
      <div className="flex min-h-11 items-center gap-3 rounded-2xl rounded-bl-md border border-line bg-white px-4 py-2.5 shadow-sm">
        <span className="flex gap-1.5" aria-hidden="true">
          {[0, 1, 2].map((item) => (
            <span className="size-1.5 animate-bounce rounded-full bg-brand" key={item} style={{ animationDelay: `${item * 130}ms` }} />
          ))}
        </span>
        <span className="text-xs font-semibold text-muted">{loadingMessageForElapsed(elapsed)}</span>
      </div>
    </div>
  );
}
