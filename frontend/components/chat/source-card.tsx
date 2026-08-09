import { ExternalLinkIcon } from "@/components/ui/icons";
import type { ApiSource } from "@/types/api";

export function SourceCard({ source, index }: { source: ApiSource; index: number }) {
  return (
    <a
      className="group flex items-start gap-3 rounded-xl border border-line bg-canvas/70 p-3 transition hover:border-emerald-300 hover:bg-brand-soft"
      href={source.url}
      rel="noopener noreferrer"
      target="_blank"
    >
      <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-white text-xs font-bold text-brand shadow-sm">
        {index + 1}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5 text-xs font-bold text-ink group-hover:text-brand-dark">
          <span className="truncate">{source.title}</span>
          <ExternalLinkIcon className="shrink-0" size={13} />
        </span>
      </span>
    </a>
  );
}
