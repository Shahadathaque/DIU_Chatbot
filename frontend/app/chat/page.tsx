import { ChatExperience } from "@/components/chat/chat-experience";
import { createPageMetadata } from "@/lib/site";

export const metadata = createPageMetadata({
  title: "Ask the Admission AI",
  description: "Ask DIU admission questions in English, Bangla, or Banglish and review source citations supplied with the answer.",
  path: "/chat",
});

export default function ChatPage() {
  return <ChatExperience />;
}
