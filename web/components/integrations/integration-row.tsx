"use client";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { ChevronRight } from "lucide-react";

export function IntegrationRow({
  name,
  logoUrl,
  scope,
  connected,
  identity,
  comingSoon,
  attention,
  onClick,
}: {
  name: string;
  logoUrl: string;
  scope: string;
  connected: boolean;
  identity?: string | null;
  comingSoon?: boolean;
  attention?: string | null;
  onClick: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "flex w-full items-center gap-3 rounded-[var(--radius)] border border-[var(--line)] bg-surface px-4 py-3.5 text-left shadow-[var(--shadow-sm)] transition-colors hover:border-[var(--line-strong)]",
          comingSoon && "opacity-70",
        )}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={logoUrl}
          alt=""
          width={32}
          height={32}
          className="shrink-0"
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium">{name}</p>
            {comingSoon ? (
              <Badge tone="muted">Coming soon</Badge>
            ) : connected ? (
              <Badge tone="ok">Connected</Badge>
            ) : (
              <Badge tone="muted">Not connected</Badge>
            )}
            {identity && <Badge tone="neutral">{identity}</Badge>}
          </div>
          <p className="mt-1 text-sm leading-relaxed text-ink-soft">{scope}</p>
          {attention && (
            <p className="mt-1 text-sm text-accent">{attention}</p>
          )}
        </div>
        <ChevronRight size={16} className="shrink-0 text-muted" />
      </button>
    </li>
  );
}
