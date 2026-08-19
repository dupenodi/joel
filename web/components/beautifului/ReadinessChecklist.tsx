export type ReadinessStep = {
  key: string;
  label: string;
  done: boolean;
};

export function ReadinessChecklist({ steps }: { steps: ReadinessStep[] }) {
  const doneCount = steps.filter((s) => s.done).length;
  const percent = steps.length === 0 ? 0 : (doneCount / steps.length) * 100;

  return (
    <div className="w-full max-w-xs">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-[12.5px] text-ink-2">Index</span>
        <span className="font-mono text-[11.5px] text-ink-3 tabular-nums">
          {doneCount}/{steps.length}
        </span>
      </div>
      <div className="mb-3 h-1 overflow-hidden rounded-full bg-line">
        <div
          className="h-full rounded-full bg-ink transition-[width] duration-400"
          style={{
            width: `${percent}%`,
            transitionTimingFunction: "cubic-bezier(0.23, 1, 0.32, 1)",
          }}
        />
      </div>
      <ul className="flex flex-col gap-1.5">
        {steps.map((step) => (
          <li key={step.key} className="flex items-center gap-2">
            <span
              className={`flex size-5 items-center justify-center rounded-full ${
                step.done
                  ? "bg-green-tint text-green"
                  : "bg-field text-ink-3 shadow-hairline"
              }`}
            >
              {step.done ? (
                <svg
                  width="10"
                  height="10"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M20 6L9 17l-5-5" />
                </svg>
              ) : null}
            </span>
            <span
              className={`text-[13px] ${step.done ? "text-ink" : "text-ink-3"}`}
            >
              {step.label}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
