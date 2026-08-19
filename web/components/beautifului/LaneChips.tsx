export function LaneChips({ lanes }: { lanes: string[] }) {
  if (lanes.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {lanes.map((lane) => (
        <span
          key={lane}
          className="inline-flex h-5 items-center rounded-[5px] bg-inset px-1.5 font-mono text-[10.5px] tracking-[0.02em] text-ink-2 shadow-hairline"
        >
          {lane}
        </span>
      ))}
    </div>
  );
}
