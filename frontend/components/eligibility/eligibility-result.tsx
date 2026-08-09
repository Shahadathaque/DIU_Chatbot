import { CheckIcon, ExternalLinkIcon, WarningIcon } from "@/components/ui/icons";
import type { EligibilityResponse } from "@/types/api";

const statusCopy = {
  eligible: {
    label: "Eligible",
    tone: "border-emerald-200 bg-emerald-50 text-emerald-950",
    icon: CheckIcon,
  },
  not_eligible: {
    label: "Not Eligible",
    tone: "border-red-200 bg-red-50 text-red-950",
    icon: WarningIcon,
  },
  insufficient_information: {
    label: "Insufficient Information",
    tone: "border-amber-200 bg-amber-50 text-amber-950",
    icon: WarningIcon,
  },
} as const;

export function EligibilityResult({ result }: { result: EligibilityResponse }) {
  const status = statusCopy[result.status];
  const Icon = status.icon;
  const source =
    typeof result.source === "string"
      ? { title: result.source, url: undefined }
      : result.source;

  return (
    <article className={`rounded-[1.5rem] border p-6 sm:p-8 ${status.tone}`}>
      <div className="flex items-center gap-3">
        <span className="grid size-10 place-items-center rounded-xl bg-white/80">
          <Icon size={20} />
        </span>
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.1em] opacity-70">
            Backend result
          </p>
          <h2 className="text-xl font-bold tracking-[-0.03em]">{status.label}</h2>
        </div>
      </div>

      <p className="mt-5 text-sm leading-7">{result.reason}</p>

      {source ? (
        <div className="mt-6 rounded-xl border border-black/5 bg-white/70 p-4">
          <p className="text-[11px] font-bold uppercase tracking-[0.1em] opacity-60">
            Source
          </p>
          {source.url ? (
            <a
              className="mt-2 inline-flex items-center gap-1.5 text-sm font-bold hover:underline"
              href={source.url}
              rel="noopener noreferrer"
              target="_blank"
            >
              {source.title}
              <ExternalLinkIcon size={14} />
            </a>
          ) : (
            <p className="mt-2 text-sm font-bold">{source.title}</p>
          )}
        </div>
      ) : (
        <p className="mt-5 text-xs font-medium opacity-70">
          No source was provided with this eligibility result.
        </p>
      )}
    </article>
  );
}
