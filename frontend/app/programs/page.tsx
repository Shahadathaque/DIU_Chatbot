import type { Metadata } from "next";
import { ProgramsExperience } from "@/components/programs/programs-experience";

export const metadata: Metadata = {
  title: "Programs",
  description: "Browse DIU admission-related programs from the research backend.",
};

export default function ProgramsPage() {
  return <ProgramsExperience />;
}
