import type { JobRow } from "@/lib/types";
import { formatRelative } from "@/lib/utils";

function pullDelta(job: JobRow): string {
  if (job.status === "running") return "In progress";
  const bits: string[] = [];
  if (job.new_count > 0) bits.push(`${job.new_count} new`);
  if (job.changed_count > 0) bits.push(`${job.changed_count} updated`);
  if (bits.length === 0) return job.status === "ok" ? "Nothing new" : "";
  return bits.join(", ");
}

export function LastPull({
  jobs,
  docCount,
}: {
  jobs: JobRow[];
  docCount: number;
}) {
  const latest = jobs[0] ?? null;
  const earlier = jobs.slice(1, 5);
  const failed = latest?.status === "error";

  return (
    <div className="rounded-[var(--radius-sm)] bg-inset px-3 py-2.5">
      <p className="text-[13px] font-medium tabular-nums text-ink">
        {docCount === 0
          ? "Nothing in memory yet"
          : `${docCount.toLocaleString()} ${docCount === 1 ? "doc" : "docs"} in memory`}
      </p>
      {latest ? (
        <p className={`mt-0.5 text-[12.5px] ${failed ? "text-red" : "text-ink-2"}`}>
          {latest.status === "running"
            ? "Pulling now…"
            : latest.status === "cancelled"
              ? `Cancelled ${formatRelative(latest.started_at)}`
            : failed
              ? `Last pull failed ${formatRelative(latest.started_at)}`
              : `Last pull ${formatRelative(latest.started_at)}`}
          {latest.status !== "running" && latest.status !== "cancelled" && pullDelta(latest)
            ? ` · ${pullDelta(latest)}`
            : ""}
        </p>
      ) : (
        <p className="mt-0.5 text-[12.5px] text-ink-3">No pulls yet</p>
      )}
      {failed && latest.error && (
        <p className="mt-1.5 text-[12.5px] leading-snug text-red">{latest.error}</p>
      )}
      {earlier.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer select-none text-[12.5px] text-ink-3 hover:text-ink">
            Earlier pulls
          </summary>
          <ul className="mt-1.5 space-y-1 border-t border-line pt-1.5">
            {earlier.map((job) => (
              <li
                key={job.id}
                className="flex flex-wrap items-baseline gap-x-2 text-[12.5px] text-ink-2"
              >
                <span className={job.status === "error" ? "text-red" : ""}>
                  {job.status === "running"
                    ? "Running"
                    : job.status === "cancelled"
                      ? `Cancelled · ${formatRelative(job.started_at)}`
                    : job.status === "error"
                      ? `Failed · ${formatRelative(job.started_at)}`
                      : formatRelative(job.started_at)}
                </span>
                {job.status !== "running" && job.status !== "cancelled" && pullDelta(job) && (
                  <span className="text-ink-3">{pullDelta(job)}</span>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
