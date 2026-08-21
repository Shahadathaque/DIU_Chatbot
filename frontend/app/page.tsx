import Link from "next/link";
import {
  ArrowRightIcon,
  ChatIcon,
  CheckIcon,
  ClipboardIcon,
  GraduationIcon,
  ShieldIcon,
  SparkleIcon,
} from "@/components/ui/icons";
import { createPageMetadata } from "@/lib/site";

export const metadata = createPageMetadata({
  title: "Verified DIU Admission Guidance",
  description: "AI-powered admission assistance grounded in verified Daffodil International University information.",
  path: "/",
});

const capabilities = [
  {
    icon: ChatIcon,
    title: "Ask naturally",
    description:
      "Get admission guidance in English, বাংলা, or Banglish through a focused chat experience.",
  },
  {
    icon: ClipboardIcon,
    title: "Check eligibility",
    description:
      "Submit your academic profile for a backend-verified eligibility assessment.",
  },
  {
    icon: GraduationIcon,
    title: "Explore programs",
    description:
      "Browse available degrees and jump to the relevant official admission information.",
  },
];

export default function Home() {
  return (
    <>
      <section className="subtle-grid relative overflow-hidden border-b border-line">
        <div className="absolute -left-24 top-20 size-72 rounded-full bg-emerald-200/30 blur-3xl" />
        <div className="absolute -right-32 bottom-0 size-96 rounded-full bg-yellow-100/60 blur-3xl" />
        <div className="page-shell relative grid min-h-[690px] items-center gap-14 py-16 lg:grid-cols-[1.02fr_.98fr] lg:py-20">
          <div className="max-w-2xl">
            <span className="eyebrow rounded-full border border-emerald-200 bg-white/80 px-3 py-1.5">
              <SparkleIcon size={14} />
              DIU-specific admission intelligence
            </span>
            <h1 className="text-balance mt-7 text-[clamp(2.8rem,7vw,5.4rem)] font-semibold leading-[0.98] tracking-[-0.06em] text-ink">
              DIU Admission
              <span className="block text-brand">AI</span>
            </h1>
            <p className="mt-7 max-w-xl text-base leading-7 text-muted sm:text-lg sm:leading-8">
              AI-powered admission assistance grounded in verified Daffodil International
              University information.
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
              <Link
                className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-brand px-6 py-3 text-sm font-bold text-white shadow-[0_12px_28px_rgba(8,120,63,0.24)] transition hover:-translate-y-0.5 hover:bg-brand-dark"
                href="/chat"
              >
                Ask Admission AI <ArrowRightIcon size={18} />
              </Link>
              <Link
                className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-line bg-white px-6 py-3 text-sm font-bold text-ink transition hover:border-emerald-300 hover:bg-brand-soft"
                href="/eligibility"
              >
                Check my eligibility
              </Link>
              <Link
                className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-line bg-white px-6 py-3 text-sm font-bold text-ink transition hover:border-emerald-300 hover:bg-brand-soft"
                href="/programs"
              >
                Explore programs
              </Link>
            </div>
            <Link className="mt-4 inline-flex text-sm font-bold text-brand hover:text-brand-dark" href="/blog">
              Read admission guides →
            </Link>
            <div className="mt-9 flex flex-wrap gap-x-6 gap-y-3 text-xs font-semibold text-muted">
              {["Official-source citations", "3 language modes", "No sign-up needed"].map(
                (item) => (
                  <span className="flex items-center gap-2" key={item}>
                    <CheckIcon className="text-brand" size={16} />
                    {item}
                  </span>
                ),
              )}
            </div>
          </div>

          <div className="relative mx-auto w-full max-w-[540px]">
            <div className="absolute -inset-4 rounded-[2rem] bg-gradient-to-br from-emerald-200/50 to-yellow-100/40 blur-2xl" />
            <div className="glass-panel relative overflow-hidden rounded-[1.6rem]">
              <div className="flex items-center justify-between border-b border-line px-5 py-4">
                <div className="flex items-center gap-3">
                  <span className="grid size-9 place-items-center rounded-xl bg-brand text-white">
                    <SparkleIcon size={17} />
                  </span>
                  <div>
                    <p className="text-sm font-bold">DIU Admission Assistant</p>
                    <p className="flex items-center gap-1.5 text-[11px] font-medium text-muted">
                      <span className="size-1.5 rounded-full bg-emerald-500" />
                      Ready to help
                    </p>
                  </div>
                </div>
                <span className="rounded-full bg-brand-soft px-2.5 py-1 text-[10px] font-bold text-brand-dark">
                  RESEARCH AI
                </span>
              </div>
              <div className="space-y-4 p-5 sm:p-6">
                <p className="text-xs font-bold uppercase tracking-[0.1em] text-brand">Research with evidence</p>
                {[
                  ["Programs and degree levels", "Distinguish exact program names and undergraduate or postgraduate study."],
                  ["Tuition and admission costs", "Retrieve the matching structured fee evidence for a named program."],
                  ["Requirements and eligibility", "Keep documented admission rules separate from scholarships and waivers."],
                  ["Applications and documents", "Follow current source links and official application channels."],
                ].map(([title, description]) => (
                  <div className="rounded-xl border border-line bg-white p-4 shadow-sm" key={title}>
                    <p className="text-sm font-bold text-ink">{title}</p>
                    <p className="mt-1 text-xs leading-5 text-muted">{description}</p>
                  </div>
                ))}
                <div className="rounded-xl bg-brand-soft p-4 text-xs leading-5 text-brand-dark">
                  Citations appear when compatible evidence is available. Unknown or unsupported facts should remain unknown.
                </div>
              </div>
              <div className="border-t border-line bg-white p-4"><Link className="flex h-12 items-center justify-between rounded-xl border border-line px-4 text-sm font-bold text-brand shadow-sm hover:bg-brand-soft" href="/chat">Ask about DIU admission<span className="grid size-8 place-items-center rounded-lg bg-brand text-white"><ArrowRightIcon size={16} /></span></Link></div>
            </div>
          </div>
        </div>
      </section>

      <section className="page-shell py-20 sm:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <span className="eyebrow">Everything in one place</span>
          <h2 className="text-balance mt-4 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">
            A clearer path from question to application
          </h2>
          <p className="mt-4 text-base leading-7 text-muted">
            Purpose-built tools help prospective students find answers without navigating
            scattered pages.
          </p>
        </div>
        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {capabilities.map((item) => (
            <article
              className="group rounded-2xl border border-line bg-white p-6 shadow-card transition hover:-translate-y-1 hover:border-emerald-200 hover:shadow-soft sm:p-7"
              key={item.title}
            >
              <span className="grid size-12 place-items-center rounded-2xl bg-brand-soft text-brand transition group-hover:bg-brand group-hover:text-white">
                <item.icon size={22} />
              </span>
              <h3 className="mt-6 text-lg font-bold tracking-[-0.02em]">{item.title}</h3>
              <p className="mt-2 text-sm leading-6 text-muted">{item.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="border-y border-line bg-white">
        <div className="page-shell py-16 sm:py-20">
          <div className="max-w-3xl">
            <span className="eyebrow">Admission information you can research</span>
            <h2 className="text-balance mt-4 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">Start with a focused question, then inspect the evidence.</h2>
            <p className="mt-4 text-base leading-7 text-muted">Explore exact program titles, program-specific tuition information, admission documents, deterministic eligibility evidence, and current scholarship or waiver sources.</p>
          </div>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link className="rounded-xl border border-line bg-canvas px-4 py-3 text-sm font-bold hover:border-emerald-300" href="/programs">Programs</Link>
            <Link className="rounded-xl border border-line bg-canvas px-4 py-3 text-sm font-bold hover:border-emerald-300" href="/blog/diu-tuition-fees-guide">Tuition guide</Link>
            <Link className="rounded-xl border border-line bg-canvas px-4 py-3 text-sm font-bold hover:border-emerald-300" href="/blog/diu-admission-requirements-guide">Requirements guide</Link>
            <Link className="rounded-xl border border-line bg-canvas px-4 py-3 text-sm font-bold hover:border-emerald-300" href="/blog/diu-scholarships-waivers-guide">Scholarships and waivers</Link>
          </div>
        </div>
      </section>

      <section className="border-b border-line bg-white">
        <div className="page-shell grid gap-10 py-16 lg:grid-cols-[1fr_auto] lg:items-center">
          <div className="max-w-2xl">
            <span className="eyebrow">
              <ShieldIcon size={15} /> Research transparency
            </span>
            <h2 className="text-balance mt-4 text-3xl font-semibold tracking-[-0.04em]">
              AI guidance with the source still in view.
            </h2>
            <p className="mt-4 text-sm leading-7 text-muted sm:text-base">
              Answers can include links supplied by the research backend, so you can review
              official university information before making a final decision.
            </p>
          </div>
          <Link
            className="inline-flex w-fit items-center gap-2 rounded-xl border border-line bg-canvas px-5 py-3 text-sm font-bold text-ink hover:border-emerald-300"
            href="/chat"
          >
            Try the assistant <ArrowRightIcon size={17} />
          </Link>
        </div>
      </section>

      <section className="page-shell py-20">
        <div className="overflow-hidden rounded-[1.75rem] bg-brand-dark px-6 py-12 text-white shadow-soft sm:px-12 sm:py-14">
          <div className="grid gap-8 lg:grid-cols-[1fr_auto] lg:items-center">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-emerald-200">
                Speak your way
              </p>
              <h2 className="text-balance mt-4 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">
                English. বাংলা. Banglish.
              </h2>
              <p className="mt-4 max-w-xl text-sm leading-7 text-emerald-50/80 sm:text-base">
                Ask in the language that feels most natural. The interface is ready for
                Bangla Unicode and preserves the backend&apos;s original response language.
              </p>
            </div>
            <Link
              className="inline-flex min-h-12 w-fit items-center gap-2 rounded-xl bg-white px-6 py-3 text-sm font-bold text-brand-dark"
              href="/chat"
            >
              এখন প্রশ্ন করুন <ArrowRightIcon size={17} />
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
