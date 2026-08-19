import { ChatSurface } from "@/components/chat-surface";
import { ChatBootSkeleton } from "@/components/skeletons";
import { Suspense } from "react";

export default function HomePage() {
  return (
    <Suspense fallback={<ChatBootSkeleton />}>
      <ChatSurface />
    </Suspense>
  );
}
