"use client";

import { ConnectorStatus } from "@/components/beautifului/ConnectorStatus";
import LoadingState from "@/components/beautifului/LoadingState";
import { isSyncing } from "@/lib/connectors";
import type { ConnectorStatus as Status } from "@/lib/types";
import { formatRelative } from "@/lib/utils";

export function IntegrationTile({
  name,
  logoUrl,
  status,
  identity,
  comingSoon,
  attention,
  docCount,
  lastSyncAt,
  syncStartedAt,
  onClick,
}: {
  name: string;
  logoUrl: string;
  status: Status;
  identity?: string | null;
  comingSoon?: boolean;
  attention?: string | null;
  docCount?: number;
  lastSyncAt?: string | null;
  syncStartedAt?: string | null;
  onClick: () => void;
}) {
  const connected = status !== "pending_auth" && status !== "coming_soon";
  const syncing = isSyncing(status);

  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex flex-col items-start rounded-card bg-surface p-4 text-left shadow-card transition-[background-color,box-shadow] duration-150 hover:bg-hover hover:shadow-raised ${
        comingSoon ? "opacity-55" : ""
      }`}
    >
      <div className="flex w-full items-start justify-between gap-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={logoUrl}
          alt=""
          width={36}
          height={36}
          className="size-9 shrink-0 rounded-[8px]"
        />
        <ConnectorStatus status={comingSoon ? "coming_soon" : status} />
      </div>
      <p className="mt-3 text-[15px] font-semibold tracking-tight text-ink">
        {name}
      </p>
      {identity && (
        <p className="mt-0.5 truncate text-[12.5px] text-ink-2">{identity}</p>
      )}
      {syncing ? (
        <div className="mt-2">
          <LoadingState label={`Syncing ${name}`} startedAt={syncStartedAt} />
          {docCount != null && docCount > 0 && (
            <p className="mt-1 text-[12.5px] text-ink-3">
              {docCount.toLocaleString()} {docCount === 1 ? "doc" : "docs"}
            </p>
          )}
        </div>
      ) : attention ? (
        <p className="mt-1 line-clamp-2 text-[12.5px] text-red">{attention}</p>
      ) : connected && docCount != null ? (
        <p className="mt-1 text-[12.5px] text-ink-3">
          {docCount} docs
          {lastSyncAt ? ` · ${formatRelative(lastSyncAt)}` : ""}
        </p>
      ) : (
        <p className="mt-1 text-[12.5px] text-ink-3">
          {comingSoon ? "Coming soon" : "Not connected"}
        </p>
      )}
    </button>
  );
}
