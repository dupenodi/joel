export function OrgCard({
  name,
  domain,
  logoUrl,
}: {
  name: string;
  domain: string;
  logoUrl: string;
}) {
  return (
    <div className="flex items-center gap-2.5 rounded-card bg-surface p-3 shadow-card">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={logoUrl}
        alt=""
        width={32}
        height={32}
        className="rounded-control bg-inset"
      />
      <div className="min-w-0">
        <p className="truncate text-[13px] font-medium text-ink">{name}</p>
        <p className="truncate text-[12px] text-ink-3">{domain}</p>
      </div>
    </div>
  );
}
