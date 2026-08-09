// Provisional frontend types based on the master prompt.
// Reconcile these with contracts/api-contract.md when that shared contract is added.

export type Language = "en" | "bn" | "banglish";
export type Confidence = "high" | "medium" | "low";

export interface ApiSource {
  title: string;
  url: string;
  excerpt?: string;
}

export interface ChatRequest {
  message: string;
  language: Language;
}

export interface ChatResponse {
  answer: string;
  sources?: ApiSource[];
  confidence?: Confidence;
}

export interface EligibilityRequest {
  program: string;
  ssc_gpa: number;
  hsc_gpa: number;
  group: "Science" | "Business Studies" | "Humanities" | "Other";
  diploma_status?: boolean;
  additional_subject_result?: string;
}

export type EligibilityStatus =
  | "eligible"
  | "not_eligible"
  | "insufficient_information";

export interface EligibilityResponse {
  status: EligibilityStatus;
  reason: string;
  source?: ApiSource | string;
}

export interface Program {
  id: string;
  name: string;
  short_name?: string;
  faculty?: string;
  degree?: string;
  summary?: string;
  admission_requirements?: string;
  admission_url?: string;
}

export interface ProgramsResponse {
  programs: Program[];
}

export interface HealthResponse {
  status: string;
}
