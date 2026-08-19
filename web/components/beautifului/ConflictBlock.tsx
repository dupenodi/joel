import type { ConflictPosition } from "@/lib/types";

export function ConflictBlock({
  positions,
  assessment,
}: {
  positions: ConflictPosition[];
  assessment?: string;
}) {
  return (
    <div className="overflow-hidden rounded-card bg-orange-tint/60 shadow-hairline">
      <p className="px-3 pt-2.5 text-[11px] font-medium tracking-[0.04em] text-orange uppercase">
        Conflicted
      </p>
      <div className="grid gap-2 p-3 pt-2 sm:grid-cols-2">
        {positions.map((p, i) => (
          <div
            key={i}
            className="rounded-control bg-surface p-2.5 shadow-hairline"
          >
            <p className="text-[13px] leading-relaxed text-ink">{p.claim}</p>
            <p className="mt-1.5 text-[11.5px] text-ink-3">
              {[p.date, p.source].filter(Boolean).join(" · ") || "unsourced"}
            </p>
          </div>
        ))}
      </div>
      {assessment && (
        <p className="border-t border-line px-3 py-2 text-[12.5px] leading-relaxed text-ink-2">
          <span className="font-medium text-ink">Assessment · </span>
          {assessment}
        </p>
      )}
    </div>
  );
}
