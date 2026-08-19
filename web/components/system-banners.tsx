"use client";

import { MemoryBanner } from "@/components/beautifului";
import { getHealth } from "@/lib/api";
import type { Health } from "@/lib/types";
import Link from "next/link";
import { useEffect, useState } from "react";

export function SystemBanners() {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const h = await getHealth();
        if (alive) setHealth(h);
      } catch {
        if (alive) {
          setHealth({
            hydra: "down",
            schema_version: 0,
            sync_enabled: false,
            queue_depth: 0,
            llm_error: "API unreachable",
            index: { sqlite: 0, vectors: 0, graph: 0, consistent: true },
            connectors: [],
          });
        }
      }
    };
    tick();
    const id = setInterval(tick, 12_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  if (!health) return null;

  const reauth = health.connectors.filter((c) => c.status === "needs_reauth");

  return (
    <div className="flex flex-col gap-px">
      {health.llm_error && (
        <MemoryBanner kind="llm">{health.llm_error}</MemoryBanner>
      )}
      {health.hydra === "down" && <MemoryBanner kind="degraded" />}
      {reauth.map((c) => (
        <MemoryBanner
          key={c.provider}
          kind="reauth"
          action={
            <Link
              href="/integrations"
              className="shrink-0 font-medium underline-offset-2 hover:underline"
            >
              Fix it
            </Link>
          }
        >
          {c.provider} needs reconnect.
        </MemoryBanner>
      ))}
    </div>
  );
}
