import Link from "next/link";
import { AdmissionLogoIcon, ExternalLinkIcon } from "@/components/ui/icons";

export function Footer() {
  return (
    <footer className="mt-auto border-t border-line bg-white">
      <div className="page-shell grid gap-8 py-10 sm:grid-cols-[1fr_auto] sm:items-end">
        <div>
          <div className="flex items-center gap-2 text-sm font-bold text-ink">
            <span className="grid size-8 place-items-center rounded-lg bg-brand text-white">
              <AdmissionLogoIcon size={18} />
            </span>
            DIU Admission AI
          </div>
          <p className="mt-3 max-w-xl text-sm leading-6 text-muted">
            An independent research project for source-grounded DIU admission support. It
            is not an official university service; verify important details with DIU.
          </p>
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-3 text-sm font-semibold text-muted">
          <Link className="hover:text-brand" href="/chat">Ask AI</Link>
          <Link className="hover:text-brand" href="/eligibility">Eligibility</Link>
          <Link className="hover:text-brand" href="/programs">Programs</Link>
          <Link className="hover:text-brand" href="/blog">Admission Guides</Link>
          <a
            className="inline-flex items-center gap-1.5 hover:text-brand"
            href="https://www.linkedin.com/in/shahadat-haque-fardin-77b084356/"
            rel="noopener noreferrer"
            target="_blank"
          >
            Shahadat on LinkedIn <ExternalLinkIcon size={14} />
          </a>
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
