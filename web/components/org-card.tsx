import { Surface } from "@/components/surface";

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
    <Surface elevation="hard" className="flex items-center gap-3 p-4">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={logoUrl}
        alt=""
        width={40}
        height={40}
        className="rounded-[10px] bg-inset"
      />
      <div className="min-w-0">
        <p className="truncate font-medium text-ink">{name}</p>
        <p className="truncate text-sm text-muted">{domain}</p>
      </div>
    </Surface>
  );
}
