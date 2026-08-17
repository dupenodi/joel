import { Badge } from "@/components/ui/badge";
import type { JobRow } from "@/lib/types";
import { formatRelative } from "@/lib/utils";

export function JobHistoryRow({ job }: { job: JobRow }) {
  const tone =
    job.status === "ok" ? "ok" : job.status === "error" ? "accent" : "partial";

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-[var(--line)] py-2.5 text-sm last:border-0">
      <Badge tone={tone}>{job.status}</Badge>
      <span className="text-ink-soft">{formatRelative(job.started_at)}</span>
      <span className="tabular-nums text-muted">
        +{job.new_count} / ~{job.changed_count} / ={job.unchanged_count}
      </span>
      {job.duration_ms != null && (
        <span className="tabular-nums text-muted">
          {(job.duration_ms / 1000).toFixed(1)}s
        </span>
      )}
      {job.error && (
        <span className="w-full text-accent sm:w-auto">{job.error}</span>
      )}
    </div>
  );
}
