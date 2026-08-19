export function Stat({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-control bg-inset px-2.5 py-2">
      <dt className="text-[12px] text-ink-3">{label}</dt>
      <dd className="mt-0.5 text-[14px] font-medium tabular-nums text-ink">
        {value}
      </dd>
    </div>
  );
}
