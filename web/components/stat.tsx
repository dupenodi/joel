/**
 * Renders one dt/dd pair. Must be used inside a <dl>. The wrapping <div> is
 * valid per the HTML dl content model (a <dl> may contain one or more <div>s,
 * each grouping a dt/dd pair) as long as every group in that <dl> is grouped
 * the same way.
 */
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
