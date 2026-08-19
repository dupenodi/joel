import Link from "next/link";

export function LockedChat({
  href = "/integrations",
}: {
  href?: string;
}) {
  return (
    <div className="flex w-full max-w-sm flex-col items-start rounded-card bg-surface p-4 shadow-card">
      <p className="text-[15px] font-semibold text-ink">No memory yet</p>
      <p className="mt-1 text-[14px] leading-relaxed text-ink-2">
        Connect a tool, then come back here.
      </p>
      <Link
        href={href}
        className="mt-3 inline-flex h-8 items-center rounded-control bg-ink px-3 text-[13px] font-medium text-surface transition-transform duration-100 active:scale-[0.96]"
      >
        Connect a tool
      </Link>
    </div>
  );
}
