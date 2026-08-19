type Series = { color: string; values: number[] };

export function Sparkline({
  series,
  grid = false,
}: {
  series: Series[];
  grid?: boolean;
}) {
  const width = 320;
  const height = 166;
  const pad = { top: 22, right: 8, bottom: 22, left: 8 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const all = series.flatMap((s) => s.values);
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1;

  const pathFor = (values: number[]) =>
    values
      .map((v, i) => {
        const x = pad.left + (i / Math.max(values.length - 1, 1)) * innerW;
        const y = pad.top + (1 - (v - min) / span) * innerH;
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ");

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-full w-full"
      aria-hidden
    >
      {grid &&
        [0.25, 0.5, 0.75].map((t) => (
          <line
            key={t}
            x1={pad.left}
            x2={width - pad.right}
            y1={pad.top + innerH * t}
            y2={pad.top + innerH * t}
            stroke="var(--line)"
            strokeWidth="1"
          />
        ))}
      {series.map((s) => (
        <path
          key={s.color}
          d={pathFor(s.values)}
          fill="none"
          stroke={s.color}
          strokeWidth="2.25"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      ))}
    </svg>
  );
}
