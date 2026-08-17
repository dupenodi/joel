export function Stat({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-[var(--radius-sm)] bg-inset px-3 py-3">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1 text-lg font-medium tabular-nums text-ink">{value}</dd>
    </div>
  );
}
