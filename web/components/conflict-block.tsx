import type { ConflictPosition } from "@/lib/types";

export function ConflictBlock({
  positions,
  assessment,
}: {
  positions: ConflictPosition[];
  assessment?: string;
}) {
  return (
    <div className="space-y-3 rounded-[var(--radius)] border border-[var(--warn)]/30 bg-[var(--warn-soft)] p-4">
      <p className="text-xs font-medium uppercase tracking-[0.06em] text-[var(--warn)]">
        Conflicted
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {positions.map((p, i) => (
          <div
            key={i}
            className="rounded-[var(--radius-sm)] border border-[var(--line)] bg-surface p-3"
          >
            <p className="text-[15px] leading-relaxed text-ink">{p.claim}</p>
            <p className="mt-2 text-xs text-muted">
              {[p.date, p.source].filter(Boolean).join(" · ") || "unsourced"}
            </p>
          </div>
        ))}
      </div>
      {assessment && (
        <p className="text-sm text-ink-soft">
          <span className="font-medium text-ink">Assessment · </span>
          {assessment}
        </p>
      )}
    </div>
  );
}
