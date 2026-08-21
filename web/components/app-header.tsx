"use client";

import { AccountMenu } from "@/components/account-menu";
import { AppFrame } from "@/components/app-frame";
import { WorkspaceSwitcher } from "@/components/workspace-switcher";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLayoutEffect, useRef, useState } from "react";

const TABS: { href: string; label: string; preview?: boolean }[] = [
  { href: "/", label: "Chat" },
  { href: "/integrations", label: "Integrations" },
  { href: "/graph", label: "Graph", preview: true },
];

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
        <WorkspaceSwitcher />

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
                aria-label={tab.preview ? `${tab.label} (preview)` : tab.label}
                aria-current={active ? "page" : undefined}
                title={tab.preview ? `${tab.label} · preview` : undefined}
                onMouseEnter={() => setHovered(tab.href)}
                onFocus={() => setHovered(tab.href)}
                onBlur={() => setHovered(null)}
                onClick={(event) => {
                  if (tab.href !== "/" || pathname !== "/") return;
                  if (new URLSearchParams(window.location.search).has("c")) {
                    event.preventDefault();
                  }
                }}
                className={cn(
                  "relative z-10 flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-full px-3.5 text-[14px] font-medium transition-colors duration-150",
                  active ? "text-ink" : "text-ink-2 hover:text-ink",
                )}
              >
                {tab.label}
                {tab.preview && (
                  <span className="text-[10px] font-medium tracking-wide text-ink-3 uppercase">
                    Preview
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        <AccountMenu />
      </AppFrame>
    </header>
  );
}
