export interface GuideSource {
  title: string;
  url: string;
}

export interface GuideLink {
  label: string;
  href: string;
}

export interface GuideSection {
  heading: string;
  paragraphs: string[];
  bullets?: string[];
  links?: GuideLink[];
}

export interface AdmissionGuide {
  title: string;
  slug: string;
  description: string;
  excerpt: string;
  published: string;
  updated: string;
  author: string;
  category: string;
  keywords: string[];
  readingMinutes: number;
  sources: GuideSource[];
  sections: GuideSection[];
  relatedSlugs: string[];
}

const projectAuthor = "DIU Admission AI Project";
const published = "2026-08-22";

export const admissionGuides: AdmissionGuide[] = [
  {
    title: "Complete Guide to Daffodil International University Admission",
    slug: "complete-diu-admission-guide",
    description:
      "A source-led overview of DIU admission research, from choosing a program to checking documents and applying through official channels.",
    excerpt:
      "Start with the official program catalog, review current requirements and costs, then use DIU’s application channel.",
    published,
    updated: published,
    author: projectAuthor,
    category: "Admission planning",
    keywords: ["DIU admission", "Daffodil International University admission", "DIU admission guide"],
    readingMinutes: 6,
    sources: [
      { title: "DIU admission hub", url: "https://daffodilvarsity.edu.bd/admission" },
      { title: "DIU programs", url: "https://daffodilvarsity.edu.bd/programs" },
      { title: "DIU online admission form", url: "https://pd.daffodilvarsity.edu.bd/admission/online" },
    ],
    sections: [
      {
        heading: "Begin with the program, not the form",
        paragraphs: [
          "Admission planning is clearer when you first identify the exact official program name. DIU publishes a program catalog that groups current offerings by academic area. Program availability is date-sensitive, so confirm the listing before making a final decision.",
          "After choosing a program, use its full name when asking about tuition or admission information. This avoids confusion between undergraduate and postgraduate programs that share a subject.",
        ],
        links: [{ label: "Explore the program directory", href: "/programs" }],
      },
      {
        heading: "Check the evidence in a sensible order",
        paragraphs: [
          "Use official sources to review the program, current tuition information, required documents, application process, and any current notice that applies to your intake.",
        ],
        bullets: [
          "Confirm the exact program and degree level.",
          "Review the official tuition page for the relevant student category.",
          "Check the current document checklist and application instructions.",
          "Use official contact channels when the published evidence is incomplete.",
        ],
      },
      {
        heading: "Use the assistant as a research shortcut",
        paragraphs: [
          "DIU Admission AI retrieves evidence collected from approved DIU sources and shows citations when evidence is available. It is a research project, not an admissions authority, so important decisions should always be verified on the linked official page.",
        ],
        links: [
          { label: "Ask Admission AI", href: "/chat" },
          { label: "Check eligibility evidence", href: "/eligibility" },
        ],
      },
    ],
    relatedSlugs: ["diu-admission-requirements-guide", "how-to-apply-diu-admission"],
  },
  {
    title: "DIU Tuition Fees Guide: Understanding Program Costs",
    slug: "diu-tuition-fees-guide",
    description:
      "Learn how to read DIU’s structured tuition information and verify the correct fee row for a specific program.",
    excerpt:
      "Understand the fields in DIU’s tuition tables and why exact program matching matters before comparing costs.",
    published,
    updated: published,
    author: projectAuthor,
    category: "Tuition and costs",
    keywords: ["DIU tuition fees", "Daffodil University admission cost", "DIU program fees"],
    readingMinutes: 5,
    sources: [
      { title: "DIU tuition fees for local students", url: "https://daffodilvarsity.edu.bd/tuition-fees" },
      { title: "DIU tuition fees for international students", url: "https://daffodilvarsity.edu.bd/int-tuition-fees" },
    ],
    sections: [
      {
        heading: "Match the exact program first",
        paragraphs: [
          "DIU’s tuition information is program-specific. Broad labels can refer to several degrees or specializations, so use the complete program name and confirm whether it is undergraduate or postgraduate.",
          "Local and international tuition information is published separately. Always use the page that matches the applicant category.",
        ],
        links: [{ label: "Browse current program names", href: "/programs" }],
      },
      {
        heading: "What the structured fee row can contain",
        paragraphs: [
          "The verified local tuition table used by this project contains fields for credit hours, duration, the amount payable during admission, average semester fees, total tuition fees, and total program fees. A blank or unavailable field should not be guessed.",
        ],
        bullets: [
          "Compare the official program name before comparing amounts.",
          "Treat displayed figures as date-sensitive.",
          "Do not convert a scholarship or waiver condition into an admission requirement.",
          "Recheck the official page before making a payment decision.",
        ],
      },
      {
        heading: "Ask a precise tuition question",
        paragraphs: [
          "A useful question includes the exact program and the type of cost you need, such as total program fees or the amount payable during admission. The answer should include an official source when verified evidence is available.",
        ],
        links: [{ label: "Ask about a specific program’s tuition", href: "/chat" }],
      },
    ],
    relatedSlugs: ["diu-programs-guide", "diu-scholarships-waivers-guide"],
  },
  {
    title: "DIU Admission Requirements: Documents and Evidence Guide",
    slug: "diu-admission-requirements-guide",
    description:
      "A careful guide to researching DIU admission documents and eligibility without assuming unpublished requirements.",
    excerpt:
      "Separate document preparation from eligibility decisions and use current official evidence for both.",
    published,
    updated: published,
    author: projectAuthor,
    category: "Requirements",
    keywords: ["DIU admission requirements", "DIU admission documents", "DIU eligibility"],
    readingMinutes: 5,
    sources: [
      { title: "DIU admission checklist", url: "https://webbackend.daffodilvarsity.edu.bd/photos/pdf/admission-checklist.pdf" },
      { title: "DIU admission hub", url: "https://daffodilvarsity.edu.bd/admission" },
      { title: "DIU programs", url: "https://daffodilvarsity.edu.bd/programs" },
    ],
    sections: [
      {
        heading: "Documents and eligibility are different questions",
        paragraphs: [
          "A document checklist explains what evidence an applicant may need to provide. Eligibility is a separate decision that depends on verified rules for the selected pathway and program.",
          "This project does not infer GPA or subject thresholds from scholarship tables. When the collected official sources do not provide a required threshold, the eligibility checker returns insufficient information instead of inventing a decision.",
        ],
      },
      {
        heading: "Prepare from the current checklist",
        paragraphs: [
          "Applicant type and degree level can affect the required evidence. Review the current official checklist and keep original academic records consistent with the details entered in the application.",
        ],
        bullets: [
          "Confirm whether the application is undergraduate, postgraduate, or a documented diploma pathway.",
          "Use the exact program name.",
          "Check current official instructions before submission.",
          "Contact DIU when the published checklist does not cover your situation.",
        ],
      },
      {
        heading: "Use deterministic eligibility checking",
        paragraphs: [
          "The project’s eligibility checker applies only collected, explicit rules and reports evidence gaps. The chat assistant can explain that result but cannot override it.",
        ],
        links: [{ label: "Open the eligibility checker", href: "/eligibility" }],
      },
    ],
    relatedSlugs: ["complete-diu-admission-guide", "undergraduate-postgraduate-diu-guide"],
  },
  {
    title: "DIU Programs Guide: Choosing the Right Program",
    slug: "diu-programs-guide",
    description:
      "Use DIU’s official program catalog to compare names, degree levels, faculties, and relevant admission sources.",
    excerpt:
      "A practical way to shortlist programs without confusing similar subjects or degree levels.",
    published,
    updated: published,
    author: projectAuthor,
    category: "Programs",
    keywords: ["DIU programs", "Daffodil University programs", "DIU degree list"],
    readingMinutes: 5,
    sources: [
      { title: "DIU programs", url: "https://daffodilvarsity.edu.bd/programs" },
      { title: "DIU admission hub", url: "https://daffodilvarsity.edu.bd/admission" },
    ],
    sections: [
      {
        heading: "Compare canonical program names",
        paragraphs: [
          "Closely related program names may represent different degrees, specializations, or study levels. Compare the full official title rather than relying only on a subject word or acronym.",
        ],
        bullets: [
          "Check the degree level and faculty.",
          "Distinguish a broad degree from a named specialization.",
          "Use explicit postgraduate wording when searching for a master’s program.",
          "Verify current availability on the official catalog.",
        ],
      },
      {
        heading: "Connect the shortlist to costs and requirements",
        paragraphs: [
          "After shortlisting, research each program’s current tuition evidence and admission information separately. Do not assume that requirements or costs transfer from another program with a similar name.",
        ],
        links: [
          { label: "Explore programs", href: "/programs" },
          { label: "Read the tuition guide", href: "/blog/diu-tuition-fees-guide" },
        ],
      },
      {
        heading: "Ask for evidence, not a recommendation score",
        paragraphs: [
          "The assistant is best used to retrieve verified program information. A personal decision should also consider interests, career goals, finances, and advice from qualified academic or admission staff.",
        ],
        links: [{ label: "Ask about a program", href: "/chat" }],
      },
    ],
    relatedSlugs: ["diu-tuition-fees-guide", "undergraduate-postgraduate-diu-guide"],
  },
  {
    title: "DIU Scholarships and Waivers Guide",
    slug: "diu-scholarships-waivers-guide",
    description:
      "Understand how to verify current DIU scholarship and waiver information without confusing financial aid with admission eligibility.",
    excerpt:
      "Use the current official policy and scholarship pages, and keep financial-aid criteria separate from admission rules.",
    published,
    updated: published,
    author: projectAuthor,
    category: "Financial aid",
    keywords: ["DIU scholarships", "DIU waiver", "DIU financial aid"],
    readingMinutes: 5,
    sources: [
      { title: "DIU scholarships for local students", url: "https://daffodilvarsity.edu.bd/scholarship/diu-scholarship" },
      { title: "DIU financial aid and scholarships", url: "https://financialaid.daffodilvarsity.edu.bd/?app=home" },
      { title: "DIU waiver and tuition fee calculator", url: "https://daffodilvarsity.edu.bd/tuition-fee-calculator" },
    ],
    sections: [
      {
        heading: "Check the current policy, not an old summary",
        paragraphs: [
          "Scholarship and waiver terms are date-sensitive. Use current official pages and policy documents, and confirm the applicable intake or effective period before relying on a condition.",
        ],
      },
      {
        heading: "Keep financial aid separate from admission eligibility",
        paragraphs: [
          "A waiver condition describes financial support; it is not automatically an admission threshold. This project keeps those evidence categories separate so the eligibility engine cannot turn a waiver percentage or condition into an admission decision.",
        ],
        bullets: [
          "Identify the applicant and program category.",
          "Check the effective period and maintenance conditions on the official source.",
          "Confirm calculations through an official DIU channel.",
          "Recheck the policy if your intake changes.",
        ],
      },
      {
        heading: "Retrieve the current source",
        paragraphs: [
          "Ask a focused scholarship or waiver question and follow the cited official source. If the system lacks compatible current evidence, it should say so rather than estimate an award.",
        ],
        links: [{ label: "Ask about scholarships or waivers", href: "/chat" }],
      },
    ],
    relatedSlugs: ["diu-tuition-fees-guide", "diu-admission-requirements-guide"],
  },
  {
    title: "How to Apply for Admission at Daffodil International University",
    slug: "how-to-apply-diu-admission",
    description:
      "A source-backed checklist for researching the DIU application process and using the official online admission channel.",
    excerpt:
      "Choose the program, review current instructions and documents, then apply through DIU’s official channel.",
    published,
    updated: published,
    author: projectAuthor,
    category: "Application process",
    keywords: ["how to apply DIU", "DIU online admission", "Daffodil admission application"],
    readingMinutes: 5,
    sources: [
      { title: "DIU admission flow chart", url: "https://webbackend.daffodilvarsity.edu.bd/photos/pdf/Admission-Flow-Chart19.pdf" },
      { title: "DIU online admission form", url: "https://pd.daffodilvarsity.edu.bd/admission/online" },
      { title: "DIU admission contact", url: "https://daffodilvarsity.edu.bd/admission-contact" },
    ],
    sections: [
      {
        heading: "Prepare before opening the form",
        paragraphs: [
          "First confirm the program, applicant pathway, current document requirements, and applicable cost information. This reduces the chance of entering details for the wrong degree or intake.",
        ],
      },
      {
        heading: "Use only the official application channel",
        paragraphs: [
          "The project registry identifies DIU’s online admission form as the application channel. DIU Admission AI does not collect applicant records, submit forms, or check personal application status.",
        ],
        bullets: [
          "Open the official application page directly.",
          "Enter information that matches your academic records.",
          "Keep confirmation details supplied by the official system.",
          "Use the official admission contact when instructions are unclear.",
        ],
      },
      {
        heading: "Verify changes close to submission",
        paragraphs: [
          "Application instructions and current notices can change. Recheck official pages near the time you submit rather than relying on an older screenshot or summary.",
        ],
        links: [
          { label: "Read the requirements guide", href: "/blog/diu-admission-requirements-guide" },
          { label: "Ask about the application process", href: "/chat" },
        ],
      },
    ],
    relatedSlugs: ["complete-diu-admission-guide", "diu-admission-requirements-guide"],
  },
  {
    title: "DIU Undergraduate vs Postgraduate Admission Guide",
    slug: "undergraduate-postgraduate-diu-guide",
    description:
      "Learn why degree level matters when researching DIU programs, tuition, documents, and eligibility evidence.",
    excerpt:
      "Use explicit degree wording to keep undergraduate and postgraduate evidence separate.",
    published,
    updated: published,
    author: projectAuthor,
    category: "Degree levels",
    keywords: ["DIU undergraduate admission", "DIU postgraduate admission", "DIU masters programs"],
    readingMinutes: 5,
    sources: [
      { title: "DIU programs", url: "https://daffodilvarsity.edu.bd/programs" },
      { title: "DIU admission checklist", url: "https://webbackend.daffodilvarsity.edu.bd/photos/pdf/admission-checklist.pdf" },
      { title: "DIU tuition fees", url: "https://daffodilvarsity.edu.bd/tuition-fees" },
    ],
    sections: [
      {
        heading: "Shared subjects do not mean shared programs",
        paragraphs: [
          "A subject can appear in both bachelor’s and master’s program names. Tuition rows, documents, and other evidence must be matched to the exact degree level rather than transferred between them.",
        ],
      },
      {
        heading: "Write explicit research questions",
        paragraphs: [
          "Include the complete degree or official program name when possible. Degree punctuation such as M.A., M. Pharm., or LL.M. should not change the intended program, but explicit level wording remains the clearest signal.",
        ],
        bullets: [
          "State undergraduate or postgraduate when the subject is ambiguous.",
          "Confirm the exact official title in the program catalog.",
          "Use the matching tuition row.",
          "Review the applicant-specific document pathway.",
        ],
      },
      {
        heading: "Treat missing evidence honestly",
        paragraphs: [
          "If collected official sources do not support a program-specific admission decision, the system should report insufficient information and direct the applicant to an official source.",
        ],
        links: [
          { label: "Explore degree titles", href: "/programs" },
          { label: "Check available eligibility evidence", href: "/eligibility" },
        ],
      },
    ],
    relatedSlugs: ["diu-programs-guide", "diu-admission-requirements-guide"],
  },
];

export function getGuide(slug: string): AdmissionGuide | undefined {
  return admissionGuides.find((guide) => guide.slug === slug);
}
