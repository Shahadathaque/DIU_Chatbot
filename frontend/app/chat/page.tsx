import type { Metadata } from "next";
import { ChatExperience } from "@/components/chat/chat-experience";

export const metadata: Metadata = {
  title: "Ask the Admission AI",
  description: "Ask DIU admission questions in English, Bangla, or Banglish.",
};

export default function ChatPage() {
  return <ChatExperience />;
}
