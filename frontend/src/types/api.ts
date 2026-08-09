export type Language = "en" | "bn" | "banglish";

export type Source = {
  title: string;
  url: string;
};

export type ChatRequest = {
  message: string;
  language: Language;
};

export type ChatResponse = {
  answer: string;
  sources?: Source[];
  confidence?: "high" | "medium" | "low";
};

export type EligibilityRequest = {
  program: string;
  ssc_gpa: number;
  hsc_gpa: number;
  group: string;
  diploma_status?: string;
};

export type EligibilityResponse = {
  status: "eligible" | "not_eligible" | "insufficient_information";
  reason: string;
  source?: string;
};

export type Program = {
  name: string;
  faculty?: string;
  degree?: string;
  requirements?: string;
  admission_url?: string;
};
