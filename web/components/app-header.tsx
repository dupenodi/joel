"use client";

import { AppFrame } from "@/components/app-frame";
import { BrandMark } from "@/components/brand-mark";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLayoutEffect, useRef, useState } from "react";

const TABS: { href: string; label: string; iconOnly?: boolean }[] = [
  { href: "/", label: "Home", iconOnly: true },
  { href: "/integrations", label: "Integrations" },
  { href: "/graph", label: "Graph" },
];

function HomeIcon({ active }: { active: boolean }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={active ? 2.2 : 1.9}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M4 11.5 12 4l8 7.5" />
      <path d="M6.5 10.5V20h11V10.5" />
    </svg>
  );
}

function tabIsActive(pathname: string, href: string) {
  return href === "/"
    ? pathname === "/"
    : pathname === href || pathname.startsWith(`${href}/`);
}

export function AppHeader() {
  const pathname = usePathname();
  const [hovered, setHovered] = useState<string | null>(null);
  const [box, setBox] = useState<{
    left: number;
    top: number;
    width: number;
    height: number;
  } | null>(null);
  const navRef = useRef<HTMLElement>(null);
  const itemRefs = useRef<Record<string, HTMLAnchorElement | null>>({});

  const activeHref =
    TABS.find((tab) => tabIsActive(pathname, tab.href))?.href ?? "/";

  useLayoutEffect(() => {
    const container = navRef.current;
    const target = itemRefs.current[hovered ?? activeHref];
    if (!container || !target) return;

    const containerRect = container.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    setBox({
      left: targetRect.left - containerRect.left,
      top: targetRect.top - containerRect.top,
      width: targetRect.width,
      height: targetRect.height,
    });
  }, [hovered, activeHref]);

  return (
    <header className="shrink-0 border-b border-line bg-page">
      <AppFrame className="grid h-[var(--header-h)] grid-cols-[1fr_auto_1fr] items-center">
        <Link
          href="/"
          className="justify-self-start rounded-control py-1 hover:opacity-80"
        >
          <BrandMark size={26} withWordmark />
        </Link>

        <nav
          ref={navRef}
          aria-label="Primary"
          onMouseLeave={() => setHovered(null)}
          className="relative flex max-w-full items-center gap-0.5 overflow-x-auto rounded-full bg-field p-0.5 shadow-hairline"
        >
          <span
            aria-hidden
            className="pointer-events-none absolute rounded-full bg-surface shadow-hairline"
            style={{
              left: box?.left ?? 0,
              top: box?.top ?? 0,
              width: box?.width ?? 0,
              height: box?.height ?? 0,
              opacity: box ? 1 : 0,
              transition:
                "left 220ms cubic-bezier(0.23,1,0.32,1), top 220ms cubic-bezier(0.23,1,0.32,1), width 220ms cubic-bezier(0.23,1,0.32,1), height 220ms cubic-bezier(0.23,1,0.32,1), opacity 150ms ease",
            }}
          />
          {TABS.map((tab) => {
            const active = tabIsActive(pathname, tab.href);
            return (
              <Link
                key={tab.href}
                ref={(el) => {
                  itemRefs.current[tab.href] = el;
                }}
                href={tab.href}
                aria-label={tab.label}
                aria-current={active ? "page" : undefined}
                title={tab.iconOnly ? tab.label : undefined}
                onMouseEnter={() => setHovered(tab.href)}
                onFocus={() => setHovered(tab.href)}
                onBlur={() => setHovered(null)}
                className={cn(
                  "relative z-10 flex h-8 shrink-0 items-center justify-center rounded-full text-[14px] font-medium transition-colors duration-150",
                  tab.iconOnly ? "w-8" : "px-3.5",
                  active ? "text-ink" : "text-ink-2 hover:text-ink",
                )}
              >
                {tab.iconOnly ? <HomeIcon active={active} /> : tab.label}
              </Link>
            );
          })}
        </nav>

        <Link
          href="/settings"
          aria-label="This install"
          title="This workspace"
          className={cn(
            "justify-self-end flex size-9 items-center justify-center rounded-control text-ink-2 transition-colors duration-150 hover:bg-hover hover:text-ink",
            pathname === "/settings" && "bg-hover text-ink",
          )}
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden
          >
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </Link>
      </AppFrame>
    </header>
  );
}
