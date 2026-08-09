import { ExternalLinkIcon, GraduationIcon } from "@/components/ui/icons";
import type { Program } from "@/types/api";

export function ProgramCard({ program }: { program: Program }) {
  return (
    <article className="flex h-full flex-col rounded-2xl border border-line bg-white p-6 shadow-card transition hover:-translate-y-0.5 hover:border-emerald-200 hover:shadow-soft">
      <div className="flex items-start justify-between gap-3">
        <span className="grid size-11 place-items-center rounded-2xl bg-brand-soft text-brand">
          <GraduationIcon size={20} />
        </span>
        {program.short_name ? (
          <span className="rounded-full bg-canvas px-2.5 py-1 text-[10px] font-bold tracking-[0.08em] text-muted">
            {program.short_name}
          </span>
        ) : null}
      </div>

      <h2 className="mt-5 text-lg font-bold tracking-[-0.02em] text-ink">
        {program.name}
      </h2>

      <div className="mt-2 space-y-1 text-xs font-semibold text-muted">
        {program.faculty ? <p>{program.faculty}</p> : null}
        {program.degree ? <p>{program.degree}</p> : null}
      </div>

      {program.summary ? (
        <p className="mt-4 flex-1 text-sm leading-6 text-muted">{program.summary}</p>
      ) : null}

      {program.admission_requirements ? (
        <p className="mt-4 rounded-xl bg-canvas px-3 py-2 text-xs leading-5 text-ink">
          <span className="font-bold">Requirements: </span>
          {program.admission_requirements}
        </p>
      ) : null}

      {program.admission_url ? (
        <a
          className="mt-5 inline-flex items-center gap-1.5 text-sm font-bold text-brand hover:text-brand-dark"
          href={program.admission_url}
          rel="noopener noreferrer"
          target="_blank"
        >
          View official program page
          <ExternalLinkIcon size={14} />
        </a>
      ) : null}
    </article>
  );
}
