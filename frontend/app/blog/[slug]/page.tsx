import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { admissionGuides, getGuide } from "@/content/guides";
import { createPageMetadata, serializeJsonLd, SITE_NAME, SITE_URL } from "@/lib/site";

export const dynamicParams = false;

interface GuidePageProps {
  params: Promise<{ slug: string }>;
}

export function generateStaticParams() {
  return admissionGuides.map(({ slug }) => ({ slug }));
}

export async function generateMetadata({ params }: GuidePageProps): Promise<Metadata> {
  const { slug } = await params;
  const guide = getGuide(slug);
  if (!guide) return {};
  return createPageMetadata({
    title: guide.title,
    description: guide.description,
    path: `/blog/${guide.slug}`,
    type: "article",
    publishedTime: guide.published,
    modifiedTime: guide.updated,
    keywords: guide.keywords,
  });
}

export default async function GuidePage({ params }: GuidePageProps) {
  const { slug } = await params;
  const guide = getGuide(slug);
  if (!guide) notFound();

  const articleUrl = new URL(`/blog/${guide.slug}`, SITE_URL).toString();
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: guide.title,
    description: guide.description,
    datePublished: guide.published,
    dateModified: guide.updated,
    author: { "@type": "Organization", name: guide.author },
    publisher: { "@type": "Organization", name: SITE_NAME },
    mainEntityOfPage: articleUrl,
  };
  const breadcrumbs = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: SITE_URL.toString() },
      { "@type": "ListItem", position: 2, name: "Admission Guides", item: new URL("/blog", SITE_URL).toString() },
      { "@type": "ListItem", position: 3, name: guide.title, item: articleUrl },
    ],
  };

  return (
    <article className="page-shell py-10 sm:py-14">
      <script dangerouslySetInnerHTML={{ __html: serializeJsonLd(jsonLd) }} type="application/ld+json" />
      <script dangerouslySetInnerHTML={{ __html: serializeJsonLd(breadcrumbs) }} type="application/ld+json" />
      <nav aria-label="Breadcrumb" className="text-sm text-muted">
        <Link className="hover:text-brand" href="/">Home</Link>
        <span aria-hidden="true"> / </span>
        <Link className="hover:text-brand" href="/blog">Guides</Link>
      </nav>
      <header className="mt-8 max-w-4xl">
        <p className="eyebrow">{guide.category}</p>
        <h1 className="text-balance mt-4 text-4xl font-semibold tracking-[-0.05em] sm:text-5xl">
          {guide.title}
        </h1>
        <p className="mt-5 max-w-3xl text-lg leading-8 text-muted">{guide.description}</p>
        <p className="mt-5 text-sm text-muted">
          By {guide.author} · {guide.readingMinutes} min read · <time dateTime={guide.updated}>Last updated {guide.updated}</time>
        </p>
      </header>

      <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="article-prose">
          <aside className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-950">
            Admission information may change. Verify important decisions using the linked official DIU source.
          </aside>
          {guide.sections.map((section) => (
            <section key={section.heading}>
              <h2>{section.heading}</h2>
              {section.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
              {section.bullets ? <ul>{section.bullets.map((item) => <li key={item}>{item}</li>)}</ul> : null}
              {section.links ? (
                <div className="flex flex-wrap gap-3">
                  {section.links.map((link) => <Link className="font-bold text-brand hover:text-brand-dark" href={link.href} key={link.href}>{link.label} →</Link>)}
                </div>
              ) : null}
            </section>
          ))}
        </div>
        <aside className="space-y-5 lg:sticky lg:top-28 lg:self-start">
          <div className="rounded-2xl border border-line bg-white p-5">
            <h2 className="text-sm font-bold">Official sources</h2>
            <ul className="mt-3 space-y-3 text-sm">
              {guide.sources.map((source) => (
                <li key={source.url}><a className="text-brand hover:underline" href={source.url} rel="noopener noreferrer" target="_blank">{source.title} ↗</a></li>
              ))}
            </ul>
          </div>
          <div className="rounded-2xl bg-brand-dark p-5 text-white">
            <h2 className="font-bold">Need a specific answer?</h2>
            <p className="mt-2 text-sm leading-6 text-emerald-50/80">Ask the research assistant and inspect the sources included with its answer.</p>
            <Link className="mt-4 inline-flex rounded-lg bg-white px-4 py-2 text-sm font-bold text-brand-dark" href="/chat">Ask Admission AI</Link>
          </div>
          <nav aria-label="Admission tools" className="rounded-2xl border border-line bg-white p-5">
            <h2 className="text-sm font-bold">Continue your research</h2>
            <div className="mt-3 grid gap-2 text-sm font-semibold text-brand">
              <Link href="/chat">Ask Admission AI →</Link>
              <Link href="/eligibility">Check eligibility →</Link>
              <Link href="/programs">Explore programs →</Link>
            </div>
          </nav>
        </aside>
      </div>

      <section className="mt-14 border-t border-line pt-10">
        <h2 className="text-2xl font-semibold">Related guides</h2>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          {guide.relatedSlugs.map((relatedSlug) => {
            const related = getGuide(relatedSlug);
            return related ? <Link className="rounded-xl border border-line bg-white p-5 font-bold hover:border-emerald-300 hover:text-brand" href={`/blog/${related.slug}`} key={related.slug}>{related.title}</Link> : null;
          })}
        </div>
      </section>
    </article>
  );
}
