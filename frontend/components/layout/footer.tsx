import Link from "next/link";
import { ExternalLinkIcon, SparkleIcon } from "@/components/ui/icons";

export function Footer() {
  return (
    <footer className="mt-auto border-t border-line bg-white">
      <div className="page-shell grid gap-8 py-10 sm:grid-cols-[1fr_auto] sm:items-end">
        <div>
          <div className="flex items-center gap-2 text-sm font-bold text-ink">
            <span className="grid size-8 place-items-center rounded-lg bg-brand text-white">
              <SparkleIcon size={16} />
            </span>
            DIU Admission AI
          </div>
          <p className="mt-3 max-w-xl text-sm leading-6 text-muted">
            A domain-specific university research project exploring fine-tuned language
            models and retrieval-augmented generation for admission support.
          </p>
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-3 text-sm font-semibold text-muted">
          <Link className="hover:text-brand" href="/chat">Ask AI</Link>
          <Link className="hover:text-brand" href="/eligibility">Eligibility</Link>
          <Link className="hover:text-brand" href="/programs">Programs</Link>
          <a
            className="inline-flex items-center gap-1.5 hover:text-brand"
            href="https://daffodilvarsity.edu.bd/"
            rel="noopener noreferrer"
            target="_blank"
          >
            Official DIU <ExternalLinkIcon size={14} />
          </a>
        </div>
      </div>
    </footer>
  );
}
