import { EligibilityForm } from "@/components/eligibility/eligibility-form";
import { createPageMetadata } from "@/lib/site";

export const metadata = createPageMetadata({
  title: "DIU Admission Eligibility Checker",
  description: "Check DIU admission eligibility using deterministic rules supported by collected official evidence.",
  path: "/eligibility",
});

export default function EligibilityPage() {
  return <EligibilityForm />;
}
