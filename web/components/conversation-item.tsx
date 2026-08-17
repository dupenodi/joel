import { cn, formatRelative, navItemTone } from "@/lib/utils";
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
      aria-current={active ? "true" : undefined}
      className={cn(
        "w-full rounded-[var(--radius-sm)] px-3 py-2.5 text-left text-sm transition-colors",
        navItemTone(active),
      )}
    >
      <span className="line-clamp-2">{conversation.title}</span>
      <span className="mt-0.5 block text-xs text-muted">
        {formatRelative(conversation.created_at)}
      </span>
    </button>
  );
}
