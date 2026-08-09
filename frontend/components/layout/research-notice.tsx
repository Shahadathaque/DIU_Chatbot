import { ShieldIcon } from "@/components/ui/icons";

export function ResearchNotice() {
  return (
    <aside className="border-b border-emerald-100 bg-emerald-50/75" aria-label="Research disclaimer">
      <div className="page-shell flex min-h-9 items-center justify-center gap-2 py-2 text-center text-xs font-medium leading-5 text-emerald-900">
        <ShieldIcon className="hidden shrink-0 sm:block" size={15} />
        <p>
          Research prototype — verify final admission information through official DIU
          sources.
        </p>
      </div>
    </aside>
  );
}
