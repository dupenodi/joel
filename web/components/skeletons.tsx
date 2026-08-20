"use client";

import { ContentFrame } from "@/components/app-frame";
import PromptBar from "@/components/beautifului/PromptBar";
import { Bone } from "@/components/beautifului/primitives/bone";
import { BrandMark } from "@/components/brand-mark";
import { INTEGRATIONS } from "@/lib/integrations";

function Status({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div role="status" aria-label={label} aria-busy="true" className={className}>
      {children}
    </div>
  );
}

export function FieldBone({ className }: { className?: string }) {
  return (
    <div className={className}>
      <Bone className="h-3 w-16" />
      <Bone className="mt-1.5 h-9 w-full" />
    </div>
  );
}

export function OnboardingSkeleton() {
  return (
    <Status label="Loading setup" className="min-h-full">
      <div className="mx-auto flex min-h-full max-w-[var(--page-max)] flex-col justify-center px-[var(--app-gutter)] py-16">
        <header className="mb-8 space-y-4">
          <BrandMark size={28} withWordmark />
          <Bone className="h-3 w-40" />
        </header>
        <section className="space-y-5">
          <Bone className="h-[15px] w-56" />
          <FieldBone />
          <FieldBone />
          <Bone className="h-9 w-[5.5rem]" rounded="full" />
        </section>
      </div>
    </Status>
  );
}

export function ChatBootSkeleton() {
  return (
    <Status label="Loading home" className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <ContentFrame
          width="chat"
          className="flex h-full min-h-full flex-col justify-center overflow-visible py-10"
        >
          <div className="mb-6 flex flex-col items-center">
            <BrandMark size={148} />
            <Bone className="mt-7 h-8 w-48" />
            <Bone className="mt-2.5 h-4 w-56" />
          </div>
        </ContentFrame>
      </div>
      <div className="shrink-0 pb-5">
        <ContentFrame width="chat">
          <PromptBar tall disabled placeholder="Ask a question" />
        </ContentFrame>
      </div>
    </Status>
  );
}

export function ChatThreadSkeleton() {
  return (
    <Status label="Loading conversation">
      <ContentFrame width="chat" className="flex flex-col gap-5 py-8">
        <div className="flex justify-end pl-10">
          <Bone className="h-10 w-[min(100%,16rem)]" rounded="card" />
        </div>
        <div className="flex w-full flex-col gap-2">
          <Bone className="h-4 w-full max-w-[28rem]" />
          <Bone className="h-4 w-[88%] max-w-[24rem]" />
          <Bone className="h-4 w-[64%] max-w-[18rem]" />
        </div>
        <div className="flex justify-end pl-10">
          <Bone className="h-10 w-[min(100%,12rem)]" rounded="card" />
        </div>
        <div className="flex w-full flex-col gap-2">
          <Bone className="h-4 w-full max-w-[26rem]" />
          <Bone className="h-4 w-[72%] max-w-[20rem]" />
        </div>
      </ContentFrame>
    </Status>
  );
}

export function IntegrationTileSkeleton() {
  return (
    <div className="flex flex-col items-start rounded-card bg-surface p-4 shadow-card">
      <div className="flex w-full items-start justify-between gap-3">
        <Bone className="size-9 shrink-0 rounded-[8px]" />
        <Bone className="h-5.5 w-[4.75rem]" rounded="full" />
      </div>
      <Bone className="mt-3 h-[15px] w-24" />
      <Bone className="mt-1.5 h-3 w-32" />
    </div>
  );
}

export function IntegrationGridSkeleton() {
  return (
    <Status label="Loading integrations">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {INTEGRATIONS.map((def) => (
          <IntegrationTileSkeleton key={def.id} />
        ))}
      </div>
    </Status>
  );
}

export function PauseToggleSkeleton() {
  return (
    <div
      className="inline-flex h-5 items-center gap-2.5"
      role="status"
      aria-label="Loading sync"
    >
      <Bone className="h-3.5 w-14" />
      <Bone className="h-5 w-9" rounded="full" />
    </div>
  );
}

export function ChannelListSkeleton() {
  return (
    <Status label="Loading channels">
      <div className="space-y-2">
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="flex items-center gap-2">
            <Bone className="size-4" rounded="control" />
            <Bone className="h-3.5" style={{ width: `${48 + (i % 4) * 10}%` }} />
          </div>
        ))}
      </div>
    </Status>
  );
}

export function LastPullSkeleton() {
  return (
    <div
      className="rounded-[var(--radius-sm)] bg-inset px-3 py-2.5"
      role="status"
      aria-label="Loading pulls"
    >
      <Bone className="h-3.5 w-40" />
      <Bone className="mt-2 h-3 w-48" />
    </div>
  );
}

export function SettingsSkeleton() {
  return (
    <Status label="Loading this install">
      <div className="space-y-6">
        <section className="rounded-card bg-surface p-5 shadow-card">
          <div className="mb-4">
            <h2 className="text-[11px] font-medium tracking-[0.04em] text-ink-3 uppercase">
              You
            </h2>
            <p className="mt-1 text-[13px] leading-relaxed text-ink-2">
              Shown on Home.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <FieldBone className="min-w-48 flex-1" />
            <Bone className="h-8 w-14" rounded="full" />
          </div>
        </section>
        <section className="rounded-card bg-surface p-5 shadow-card">
          <div className="mb-4">
            <h2 className="text-[11px] font-medium tracking-[0.04em] text-ink-3 uppercase">
              Models
            </h2>
            <p className="mt-1 text-[13px] leading-relaxed text-ink-2">
              Base URL, API key, and which model each stage uses.
            </p>
          </div>
          <div className="space-y-3">
            <FieldBone />
            <FieldBone />
            <div className="grid gap-3 sm:grid-cols-2">
              {Array.from({ length: 5 }, (_, i) => (
                <FieldBone key={i} />
              ))}
            </div>
            <FieldBone />
          </div>
          <Bone className="mt-4 h-9 w-16" rounded="full" />
        </section>
      </div>
    </Status>
  );
}

function StatBone() {
  return (
    <div className="rounded-control bg-inset px-2.5 py-2">
      <Bone className="h-3 w-12" />
      <Bone className="mt-1.5 h-4 w-10" />
    </div>
  );
}

export function GraphSkeleton() {
  return (
    <Status label="Loading graph">
      <div className="rounded-card bg-surface p-5 shadow-card">
        <div className="relative mx-auto aspect-[1.6] w-full max-w-lg">
          <svg viewBox="0 0 400 250" className="h-full w-full" aria-hidden>
            {[0, 1, 2, 3, 4, 5].map((i) => {
              const angle = (Math.PI * 2 * i) / 6 - Math.PI / 2;
              const x = 200 + Math.cos(angle) * 92;
              const y = 125 + Math.sin(angle) * 72;
              return (
                <g key={i}>
                  <line
                    x1="200"
                    y1="125"
                    x2={x}
                    y2={y}
                    stroke="var(--line)"
                    strokeWidth="1"
                  />
                  <circle cx={x} cy={y} r="5.5" fill="var(--field)" />
                </g>
              );
            })}
            <circle cx="200" cy="125" r="16" fill="var(--field)" />
          </svg>
        </div>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
        {Array.from({ length: 6 }, (_, i) => (
          <StatBone key={i} />
        ))}
      </dl>
      <Bone className="mt-2 h-3 w-72" />
    </Status>
  );
}
