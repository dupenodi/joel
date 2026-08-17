import { AnswerBadge } from "@/components/status-pill";
import { CitationChip } from "@/components/citation-chip";
import { ConflictBlock } from "@/components/conflict-block";
import { ReasoningPath } from "@/components/reasoning-path";
import { ToolCallCard } from "@/components/tool-call";
import { Chip } from "@/components/ui/chip";
import { cn } from "@/lib/utils";
import type { Message } from "@/lib/types";

export function MessageBubble({ message }: { message: Message }) {
  if (message.role === "user") {
    return (
      <div className="ml-auto max-w-2xl">
        <div className="rounded-[var(--radius)] bg-inset px-4 py-3 text-[15px] text-ink">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl space-y-3">
      {message.status && <AnswerBadge status={message.status} />}
      {message.status === "absent" ? (
        <p className="font-display text-lg font-semibold tracking-tight text-accent">
          {message.content || "Not in the company's memory."}
        </p>
      ) : (
        <p className="text-[15px] leading-relaxed whitespace-pre-wrap text-ink">
          {message.content}
        </p>
      )}
      {message.conflicts?.map((c, i) => (
        <ConflictBlock
          key={i}
          positions={c.positions}
          assessment={c.assessment}
        />
      ))}
      {message.not_found && message.not_found.length > 0 && (
        <p className="text-sm text-[var(--partial)]">
          <strong>Not found:</strong> {message.not_found.join(" · ")}
        </p>
      )}
      {message.tool_calls && message.tool_calls.length > 0 && (
        <div className="space-y-2">
          {message.tool_calls.map((c) => (
            <ToolCallCard key={c.id} call={c} />
          ))}
        </div>
      )}
      {message.citations && message.citations.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {message.citations.map((c) => (
            <CitationChip key={c.doc_id} citation={c} />
          ))}
        </div>
      )}
      {message.reasoning_path && message.reasoning_path.length > 0 && (
        <ReasoningPath paths={message.reasoning_path} />
      )}
      {message.lanes && message.lanes.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {message.lanes.map((lane) => (
            <Chip key={lane} className="text-[10px] uppercase tracking-wider">
              {lane}
            </Chip>
          ))}
        </div>
      )}
    </div>
  );
}

export function MessageList({
  messages,
  className,
}: {
  messages: Message[];
  className?: string;
}) {
  return (
    <div className={cn("space-y-6", className)}>
      {messages.map((m, i) => (
        <MessageBubble key={m.id ?? `${m.role}-${i}`} message={m} />
      ))}
    </div>
  );
}
