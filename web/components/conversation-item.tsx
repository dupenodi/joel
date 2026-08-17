import { cn } from "@/lib/utils";
import type { Conversation } from "@/lib/types";

export function ConversationItem({
  conversation,
  active,
  onClick,
}: {
  conversation: Conversation;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full rounded-[var(--radius-sm)] px-3 py-2.5 text-left text-sm transition-colors",
        active
          ? "bg-inset font-medium text-ink"
          : "text-ink-soft hover:bg-inset/70 hover:text-ink",
      )}
    >
      <span className="line-clamp-2">{conversation.title}</span>
    </button>
  );
}
