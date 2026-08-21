"use client";

import {
  Filters,
  GraphCanvas,
  GraphControls,
  GraphInspector,
  defaultFilters,
  visibleNodes,
} from "@/components/graph-explorer";
import { GraphSkeleton } from "@/components/skeletons";
import { Button } from "@/components/beautifului/primitives/button";
import { getGraphWorld, getHealth } from "@/lib/api";
import type { GraphSlice, Health } from "@/lib/types";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

export default function GraphPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [slice, setSlice] = useState<GraphSlice | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [hops, setHops] = useState(1);
  const [filters, setFilters] = useState<Filters>(defaultFilters);
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    Promise.all([getHealth().catch(() => null), getGraphWorld().catch(() => null)])
      .then(([h, w]) => {
        if (h) setHealth(h);
        if (w) setSlice(w);
      })
      .finally(() => setLoading(false));
  }, []);

  const shown = useMemo(
    () => (slice ? visibleNodes(slice, filters, focusId, hops) : []),
    [slice, filters, focusId, hops],
  );
  const focusNode = focusId
    ? (slice?.nodes ?? []).find((n) => n.id === focusId)
    : null;

  if (loading) {
    return (
      <div className="min-h-0 flex-1 overflow-hidden p-4">
        <GraphSkeleton />
      </div>
    );
  }

  const broken = health?.hydra && health.hydra !== "ok";
  const empty = !slice || slice.nodes.length === 0;

  return (
    <div className="relative min-h-0 flex-1 overflow-hidden">
      {broken ? (
        <div className="flex h-full items-center justify-center">
          <p className="text-[13px] text-orange">Graph is down — {health?.hydra}</p>
        </div>
      ) : empty ? (
        <div className="flex h-full items-center justify-center px-6">
          <p className="max-w-sm text-center text-[13.5px] leading-relaxed text-ink-2">
            Nothing here yet. Connect a tool on{" "}
            <Link
              href="/integrations"
              className="text-accent-ink underline-offset-2 hover:underline"
            >
              Integrations
            </Link>{" "}
            and let a sync finish.
          </p>
        </div>
      ) : (
        <>
          <div className="absolute inset-0">
            <GraphCanvas
              slice={slice}
              filters={filters}
              selectedId={selectedId}
              focusId={focusId}
              focusHops={hops}
              onSelect={setSelectedId}
              onFocus={(id) => {
                setFocusId(id);
                if (id) setSelectedId(id);
              }}
            />
          </div>

          {/* Top-left: what you're looking at, and how to narrow it. */}
          <div className="pointer-events-none absolute left-3 top-3 flex max-w-[min(30rem,calc(100%-6rem))] flex-col gap-2">
            <div className="pointer-events-auto flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-surface px-2.5 py-1 font-mono text-[10.5px] uppercase tracking-wide text-ink-2 shadow-card">
                {shown.length} of {slice.nodes.length}
              </span>
              <Button
                type="button"
                onClick={() => setShowFilters((v) => !v)}
                className="!h-7 !px-2.5 !text-[12px]"
              >
                {showFilters ? "Hide filters" : "Filters"}
              </Button>
              {focusNode ? (
                <>
                  <span className="rounded-full bg-surface px-2.5 py-1 text-[12px] text-ink shadow-card">
                    {focusNode.label}
                  </span>
                  <div className="flex overflow-hidden rounded-full bg-surface shadow-card">
                    {[1, 2, 3].map((h) => (
                      <button
                        key={h}
                        type="button"
                        onClick={() => setHops(h)}
                        className={
                          "px-2 py-1 font-mono text-[11px] " +
                          (hops === h ? "bg-hover text-ink" : "text-ink-3 hover:text-ink")
                        }
                      >
                        {h}
                      </button>
                    ))}
                  </div>
                  <Button
                    type="button"
                    onClick={() => setFocusId(null)}
                    className="!h-7 !px-2.5 !text-[12px]"
                  >
                    Show all
                  </Button>
                </>
              ) : null}
            </div>

            {showFilters ? (
              <div className="pointer-events-auto rounded-card bg-surface p-3 shadow-overlay">
                <GraphControls slice={slice} filters={filters} onChange={setFilters} />
              </div>
            ) : null}
          </div>

          {/* Bottom-left: the one instruction that isn't discoverable. */}
          <p className="pointer-events-none absolute bottom-3 left-3 font-mono text-[10.5px] text-ink-3">
            click to inspect · double-click to isolate · drag to move
          </p>

          {/* Right: details for whatever is selected. */}
          {selectedId ? (
            <aside className="absolute right-3 top-3 bottom-3 z-10 w-[19rem] overflow-y-auto rounded-card bg-surface p-4 shadow-overlay">
              <button
                type="button"
                onClick={() => setSelectedId(null)}
                aria-label="Close"
                className="float-right -mr-1 -mt-1 size-6 rounded text-ink-3 hover:bg-hover hover:text-ink"
              >
                ×
              </button>
              <GraphInspector
                slice={slice}
                selectedId={selectedId}
                onSelect={setSelectedId}
                onFocus={setFocusId}
              />
            </aside>
          ) : null}
        </>
      )}
    </div>
  );
}
