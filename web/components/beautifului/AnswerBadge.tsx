import type { AnswerStatus } from "@/lib/types";

const COPY: Record<
  AnswerStatus,
  { label: string; className: string }
> = {
  answered: {
    label: "Answered",
    className: "bg-green-tint text-green",
  },
  partial: {
    label: "Partial",
    className: "bg-orange-tint text-orange",
  },
  conflicted: {
    label: "Conflicted",
    className: "bg-orange-tint text-orange",
  },
  absent: {
    label: "Not in memory",
    className: "bg-field text-ink-3",
  },
};

export function AnswerBadge({ status }: { status: AnswerStatus }) {
  const s = COPY[status];
  return (
    <span
      className={`inline-flex h-5.5 items-center rounded-full px-2 text-[11.5px] font-medium ${s.className}`}
    >
      {s.label}
    </span>
  );
}
