import { SourceIcon } from "@/components/source-icon";
import type { ToolCall } from "@/lib/types";

export function ToolCallChips({ calls }: { calls: ToolCall[] }) {
  if (calls.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {calls.map((call) => (
        <span
          key={call.id}
          className="inline-flex h-6 items-center gap-1.5 rounded-full bg-inset pr-2 pl-1.5 text-[11.5px] text-ink-2 shadow-hairline"
        >
          <SourceIcon provider={call.provider} size={12} />
          <span className="font-medium text-ink-3">Checked live</span>
          {call.detail && <span className="truncate">{call.detail}</span>}
        </span>
      ))}
    </div>
  );
}
