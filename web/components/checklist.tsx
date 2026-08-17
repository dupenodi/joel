import { cn } from "@/lib/utils";
import { Check } from "lucide-react";

export function Checklist({
  items,
}: {
  items: { key: string; label: string; done: boolean }[];
}) {
  const doneCount = items.filter((i) => i.done).length;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between text-sm">
        <span className="text-ink-soft">Readiness</span>
        <span className="font-medium tabular-nums text-ink">
          {doneCount}/{items.length}
        </span>
      </div>
      <div className="mb-5 h-1.5 overflow-hidden rounded-full bg-inset">
        <div
          className="h-full rounded-full bg-ink transition-[width] duration-500"
          style={{ width: `${(doneCount / items.length) * 100}%` }}
        />
      </div>
      <ul className="space-y-3">
        {items.map((item) => (
          <li key={item.key} className="flex items-center gap-3 text-[15px]">
            <span
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-full border text-xs",
                item.done
                  ? "border-[var(--ok)] bg-[var(--ok-soft)] text-[var(--ok)]"
                  : "border-[var(--line)] text-muted",
              )}
            >
              {item.done ? <Check size={14} strokeWidth={2.5} /> : null}
            </span>
            <span className={item.done ? "text-ink" : "text-muted"}>
              {item.label}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
