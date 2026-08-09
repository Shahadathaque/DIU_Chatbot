// Shared API types aligned with contracts/api-contract.md.

export type Language = "en" | "bn" | "banglish";
export type Confidence = "high" | "medium" | "low";

export interface ApiSource {
  title: string;
  url: string;
}

export interface ChatRequest {
  message: string;
  language: Language;
}

export interface ChatResponse {
  answer: string;
  sources: ApiSource[];
  confidence: Confidence;
  language: Language;
}

export interface EligibilityRequest {
  program: string;
  ssc_gpa?: number;
  hsc_gpa?: number;
  group?: string;
  diploma: boolean;
}

export type EligibilityStatus =
  | "eligible"
  | "not_eligible"
  | "insufficient_information";

export interface EligibilityResponse {
  status: EligibilityStatus;
  reason: string;
  source?: ApiSource;
}

export interface Program {
  id: string;
  name: string;
  faculty?: string;
  degree?: string;
  admission_url?: string;
}

export interface ProgramsResponse {
  programs: Program[];
}

export interface HealthResponse {
  status: "ok";
}

export interface SourceRecord {
  id: string;
  title: string;
  url: string;
  retrieved_at?: string;
}

export interface SourcesResponse {
  sources: SourceRecord[];
}
