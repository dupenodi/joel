"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Banner } from "@/components/banner";
import { getHealth } from "@/lib/api";
import type { Health } from "@/lib/types";

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

  return (
    <div className="flex flex-col">
      {health.llm_error && <Banner tone="accent">{health.llm_error}</Banner>}
      {health.hydra === "down" && (
        <Banner tone="warn">
          Relationship search unavailable — HydraDB unreachable.
        </Banner>
      )}
      {health.connectors.some((c) =>
        ["syncing", "backfilling", "distilling", "linking"].includes(c.status),
      ) && (
        <Banner tone="muted">
          Still ingesting — answers may be incomplete.
        </Banner>
      )}
      {health.connectors
        .filter((c) => c.status === "needs_reauth")
        .map((c) => (
          <Banner key={c.provider} tone="accent">
            {c.provider} needs reconnect.{" "}
            <Link href="/connectors" className="underline underline-offset-2">
              Fix it
            </Link>
          </Banner>
        ))}
    </div>
  );
}
