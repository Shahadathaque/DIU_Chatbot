import { ProgramsExperience } from "@/components/programs/programs-experience";
import { createPageMetadata } from "@/lib/site";

export const metadata = createPageMetadata({
  title: "DIU Programs",
  description: "Browse Daffodil International University programs available through the verified-source research catalog.",
  path: "/programs",
});

export default function ProgramsPage() {
  return <ProgramsExperience />;
}
