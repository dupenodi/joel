import { notFound } from "next/navigation";
import { ChatSim } from "./sim-client";

/**
 * Chat UX simulation — web thread + Slack-bot twin of the same answer.
 * Dev-only so fixture data never ships.
 */
export default function ChatSimPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }
  return <ChatSim />;
}
