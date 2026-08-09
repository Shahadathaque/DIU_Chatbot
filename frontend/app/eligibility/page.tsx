import type { Metadata } from "next";
import { EligibilityForm } from "@/components/eligibility/eligibility-form";

export const metadata: Metadata = {
  title: "Eligibility Checker",
  description: "Check DIU admission eligibility through the research backend.",
};

export default function EligibilityPage() {
  return <EligibilityForm />;
}
