import Link from "next/link";
import { admissionGuides } from "@/content/guides";
import { createPageMetadata } from "@/lib/site";

export const metadata = createPageMetadata({
  title: "DIU Admission Guides",
  description:
    "Source-backed guides to DIU programs, tuition, requirements, scholarships, eligibility, and the admission process.",
  path: "/blog",
});

export default function BlogPage() {
  return (
    <div className="page-shell py-12 sm:py-16">
      <header className="max-w-3xl">
        <span className="eyebrow">Admission research library</span>
        <h1 className="text-balance mt-4 text-4xl font-semibold tracking-[-0.05em] sm:text-5xl">
          DIU admission guides
        </h1>
        <p className="mt-5 text-base leading-8 text-muted">
          Practical, source-backed explanations for researching Daffodil International
          University admission. Policies and costs can change, so every guide points back
          to official DIU evidence.
        </p>
      </header>

      <div className="mt-12 grid gap-5 md:grid-cols-2">
        {admissionGuides.map((guide) => (
          <article className="rounded-2xl border border-line bg-white p-6 shadow-card" key={guide.slug}>
            <p className="text-xs font-bold uppercase tracking-[0.1em] text-brand">
              {guide.category}
            </p>
            <h2 className="mt-3 text-xl font-semibold tracking-[-0.03em]">
              <Link className="hover:text-brand" href={`/blog/${guide.slug}`}>
                {guide.title}
              </Link>
            </h2>
            <p className="mt-3 text-sm leading-6 text-muted">{guide.excerpt}</p>
            <div className="mt-5 flex items-center justify-between gap-3 text-xs text-muted">
              <span>{guide.readingMinutes} min read</span>
              <time dateTime={guide.updated}>Updated {guide.updated}</time>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
