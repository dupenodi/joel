import { SourceIcon } from "@/components/source-icon";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import type { ToolCall } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Check, CircleSlash, Wrench, X } from "lucide-react";

export function ToolCallCard({ call }: { call: ToolCall }) {
  return (
    <div className="flex items-start gap-2.5 rounded-[var(--radius-sm)] border border-[var(--line)] bg-inset/60 px-3 py-2.5 text-sm">
      <span className="mt-0.5 text-ink-soft">
        {call.status === "running" ? (
          <Spinner size={14} />
        ) : call.status === "done" ? (
          <Check size={14} className="text-[var(--ok)]" />
        ) : call.status === "error" ? (
          <X size={14} className="text-accent" />
        ) : (
          <CircleSlash size={14} className="text-muted" />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Wrench size={13} className="text-muted" />
          <span className="font-medium text-ink">{call.name}</span>
          {call.provider && (
            <span className="inline-flex items-center gap-1 text-xs text-muted">
              <SourceIcon provider={call.provider} size={12} />
              {call.provider}
            </span>
          )}
          <Badge
            tone={
              call.status === "done"
                ? "ok"
                : call.status === "error"
                  ? "accent"
                  : call.status === "running"
                    ? "partial"
                    : "muted"
            }
          >
            {call.status}
          </Badge>
        </div>
        {call.detail && (
          <p className="mt-1 text-xs leading-relaxed text-ink-soft">
            {call.detail}
          </p>
        )}
      </div>
    </div>
  );
}

export function AgentTrace({
  stage,
  rewritten,
  lanes,
  toolCalls,
  className,
}: {
  stage?: string | null;
  rewritten?: string | null;
  lanes?: Array<{ lane: string; hits: number }>;
  toolCalls?: ToolCall[];
  className?: string;
}) {
  if (!stage && !rewritten && !lanes?.length && !toolCalls?.length) return null;

  return (
    <div
      className={cn(
        "space-y-2 rounded-[var(--radius)] border border-[var(--line)] bg-surface p-3",
        className,
      )}
    >
      {stage && (
        <p className="text-xs uppercase tracking-[0.06em] text-muted">
          {stage}
          {stage !== "done" && "…"}
        </p>
      )}
      {rewritten && (
        <p className="text-sm text-ink-soft">
          <span className="text-muted">Rewritten · </span>
          {rewritten}
        </p>
      )}
      {lanes && lanes.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {lanes.map((l) => (
            <Badge key={l.lane} tone={l.hits > 0 ? "ok" : "muted"}>
              {l.lane}
              {l.hits > 0 ? ` · ${l.hits}` : " · 0"}
            </Badge>
          ))}
        </div>
      )}
      {toolCalls?.map((c) => (
        <ToolCallCard key={c.id} call={c} />
      ))}
    </div>
  );
}
