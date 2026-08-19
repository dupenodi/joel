"use client";

import { ContentFrame } from "@/components/app-frame";
import { PageHeader } from "@/components/page-header";
import { GraphSkeleton } from "@/components/skeletons";
import { Stat } from "@/components/stat";
import { getHealth, getProfile, listConnectors } from "@/lib/api";
import type { ConnectorCard, Health, Profile } from "@/lib/types";
import { formatRelative } from "@/lib/utils";
import Link from "next/link";
import { useEffect, useState } from "react";

export default function GraphPage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [cards, setCards] = useState<ConnectorCard[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getProfile(), getHealth(), listConnectors()])
      .then(([p, h, list]) => {
        setProfile(p);
        setHealth(h);
        setCards(list.filter((c) => c.id));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="min-h-0 flex-1 overflow-y-auto py-8">
        <ContentFrame width="wide">
          <PageHeader
            title="Graph"
            description="People and decisions linked across tools. Ask from Home — this is the map."
          />
          <GraphSkeleton />
        </ContentFrame>
      </div>
    );
  }

  const hydra = health?.hydra ?? "down";
  const entities = profile?.corpus.entities ?? 0;
  const graph = profile?.corpus.index.graph ?? 0;
  const names = cards.map((c) => c.label || c.provider);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto py-8">
      <ContentFrame width="wide">
        <PageHeader
          title="Graph"
          description="People and decisions linked across tools. Ask from Home — this is the map."
        />

        <div className="rounded-card bg-surface p-5 shadow-card">
          <Constellation nodes={names} hydraOk={hydra === "ok"} />
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Stat label="Hydra" value={hydra === "ok" ? "live" : "down"} />
          <Stat label="Docs" value={profile?.corpus.docs ?? 0} />
          <Stat label="Artifacts" value={profile?.corpus.artifacts ?? 0} />
          <Stat label="Entities" value={entities} />
          <Stat label="Graph nodes" value={graph} />
          <Stat
            label="Index"
            value={profile?.corpus.index.consistent ? "consistent" : "drift"}
          />
        </dl>
        <p className="mt-2 font-mono text-[12px] text-ink-3">
          SQLite {profile?.corpus.index.sqlite ?? 0} · vectors{" "}
          {profile?.corpus.index.vectors ?? 0} · graph {graph}
          {profile?.corpus.oldest_doc
            ? ` · oldest ${formatRelative(profile.corpus.oldest_doc)}`
            : ""}
        </p>

        <p className="mt-4 text-[13px] leading-relaxed text-ink-2">
          Relationship search{" "}
          {hydra === "ok" ? "is available" : "is paused while Hydra is down"}.
          Try{" "}
          <Link href="/" className="text-accent-ink underline-offset-2 hover:underline">
            /who-knows
          </Link>{" "}
          in chat.
        </p>
      </ContentFrame>
    </div>
  );
}

function Constellation({
  nodes,
  hydraOk,
}: {
  nodes: string[];
  hydraOk: boolean;
}) {
  const labels = nodes.slice(0, 8);
  const dim = labels.length === 0;

  return (
    <div className="relative mx-auto aspect-[1.6] w-full max-w-lg">
      <svg viewBox="0 0 400 250" className="h-full w-full" aria-hidden>
        {labels.map((_, i) => {
          const { x, y } = ring(i, labels.length);
          return (
            <line
              key={`e-${i}`}
              x1="200"
              y1="125"
              x2={x}
              y2={y}
              stroke="var(--line-strong)"
              strokeWidth="1"
            />
          );
        })}
        {labels.map((name, i) => {
          const { x, y } = ring(i, labels.length);
          return (
            <g key={name} transform={`translate(${x} ${y})`} opacity={dim ? 0.4 : 1}>
              <circle r="5.5" fill="var(--accent)" />
              <text
                y="18"
                textAnchor="middle"
                fill="var(--ink-2)"
                style={{ fontSize: 11 }}
              >
                {name}
              </text>
            </g>
          );
        })}
        <g transform="translate(200 125)">
          <circle r="16" fill="var(--ink)" />
          <circle r="5" fill="var(--page)" />
        </g>
      </svg>
      {dim && (
        <p className="absolute inset-x-0 bottom-2 text-center text-[12.5px] text-ink-3">
          Connect a tool and the graph grows from here.
        </p>
      )}
      {!hydraOk && (
        <p className="absolute inset-x-0 bottom-0 text-center text-[12px] text-orange">
          Graph search is down.
        </p>
      )}
    </div>
  );
}

function ring(index: number, total: number) {
  const angle = (Math.PI * 2 * index) / total - Math.PI / 2;
  return {
    x: 200 + Math.cos(angle) * 92,
    y: 125 + Math.sin(angle) * 72,
  };
}
