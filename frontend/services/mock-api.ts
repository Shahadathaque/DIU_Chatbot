import type {
  ChatRequest,
  ChatResponse,
  EligibilityRequest,
  EligibilityResponse,
  HealthResponse,
  ProgramsResponse,
  SourcesResponse,
} from "@/types/api";

const MOCK_DELAY_MS = 700;

function wait(ms = MOCK_DELAY_MS) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const chatAnswers: Record<ChatRequest["language"], ChatResponse> = {
  en: {
    answer:
      "For a complete DIU admission application, students commonly need academic certificates and transcripts, recent photographs, and identity documents. Exact requirements can vary by applicant type and program, so review the official admission page before submitting.",
    confidence: "high",
    language: "en",
    sources: [
      {
        title: "DIU Admission Information",
        url: "https://daffodilvarsity.edu.bd/admission",
      },
    ],
  },
  bn: {
    answer:
      "ডিআইইউতে ভর্তির জন্য সাধারণত একাডেমিক সনদ ও ট্রান্সক্রিপ্ট, সাম্প্রতিক ছবি এবং পরিচয়পত্র প্রয়োজন হয়। আবেদনকারীর ধরন ও প্রোগ্রাম অনুযায়ী সঠিক তালিকা ভিন্ন হতে পারে, তাই জমা দেওয়ার আগে অফিসিয়াল ভর্তি তথ্য যাচাই করুন।",
    confidence: "high",
    language: "bn",
    sources: [
      {
        title: "ডিআইইউ ভর্তি তথ্য",
        url: "https://daffodilvarsity.edu.bd/admission",
      },
    ],
  },
  banglish: {
    answer:
      "DIU admission-er jonno shadharonoto academic certificate o transcript, recent photograph, ebong identity document proyojon hoy. Applicant type o program onujayi exact requirement change hote pare, tai submit korar age official admission page verify korun.",
    confidence: "high",
    language: "banglish",
    sources: [
      {
        title: "DIU Admission Information",
        url: "https://daffodilvarsity.edu.bd/admission",
      },
    ],
  },
};

export async function mockSendChatMessage(
  request: ChatRequest,
): Promise<ChatResponse> {
  await wait();
  return chatAnswers[request.language];
}

export async function mockCheckEligibility(
  request: EligibilityRequest,
): Promise<EligibilityResponse> {
  await wait(900);
  // Controlled demonstration fixture only. This does not implement eligibility rules.
  // Request is accepted for API-shape parity with the real endpoint.
  void request;
  return {
    status: "insufficient_information",
    reason:
      "Your GPA information was received, but the research backend needs program-specific subject results before it can provide a final eligibility status.",
    source: {
      title: "DIU Admission Eligibility",
      url: "https://daffodilvarsity.edu.bd/admission",
    },
  };
}

export async function mockGetPrograms(): Promise<ProgramsResponse> {
  await wait(550);
  // Temporary display fixtures; factual details intentionally remain minimal.
  return {
    programs: [
      {
        id: "cse",
        name: "Computer Science and Engineering",
        faculty: "Faculty of Science and Information Technology",
        degree: "Undergraduate",
        admission_url: "https://daffodilvarsity.edu.bd/department/cse",
      },
      {
        id: "swe",
        name: "Software Engineering",
        faculty: "Faculty of Science and Information Technology",
        degree: "Undergraduate",
        admission_url: "https://daffodilvarsity.edu.bd/department/swe",
      },
      {
        id: "bba",
        name: "Business Administration",
        faculty: "Faculty of Business and Entrepreneurship",
        degree: "Undergraduate",
        admission_url: "https://daffodilvarsity.edu.bd/",
      },
      {
        id: "eee",
        name: "Electrical and Electronic Engineering",
        faculty: "Faculty of Engineering",
        degree: "Undergraduate",
        admission_url: "https://daffodilvarsity.edu.bd/",
      },
      {
        id: "civil",
        name: "Civil Engineering",
        faculty: "Faculty of Engineering",
        degree: "Undergraduate",
        admission_url: "https://daffodilvarsity.edu.bd/",
      },
      {
        id: "english",
        name: "English",
        faculty: "Faculty of Humanities and Social Sciences",
        degree: "Undergraduate",
        admission_url: "https://daffodilvarsity.edu.bd/",
      },
    ],
  };
}

export async function mockCheckBackendHealth(): Promise<HealthResponse> {
  await wait(200);
  return { status: "ok" };
}

export async function mockGetSources(): Promise<SourcesResponse> {
  await wait(250);
  return {
    sources: [
      {
        id: "mock-admission-source",
        title: "DIU Admission Information",
        url: "https://daffodilvarsity.edu.bd/admission",
      },
    ],
  };
}
