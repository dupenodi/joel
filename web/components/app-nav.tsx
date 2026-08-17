"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandMark } from "@/components/brand-mark";
import {
  Cable,
  MessageSquare,
  Settings,
  UserRound,
} from "lucide-react";
import { cn } from "@/lib/utils";

const links = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/connectors", label: "Connectors", icon: Cable },
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/profile", label: "Profile", icon: UserRound },
] as const;

export function AppNav() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-[var(--nav-w)] shrink-0 flex-col border-r border-[var(--line)] bg-bg px-3 py-5">
      <Link href="/chat" className="mb-8 px-2">
        <BrandMark size={40} withWordmark />
      </Link>

      <nav className="flex flex-1 flex-col gap-1">
        {links.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2.5 rounded-[var(--radius-sm)] px-3 py-2.5 text-sm transition-colors",
                active
                  ? "bg-inset font-medium text-ink"
                  : "text-ink-soft hover:bg-inset/70 hover:text-ink",
              )}
            >
              <Icon size={17} strokeWidth={1.75} />
              {label}
            </Link>
          );
        })}
      </nav>

      <p className="px-2 text-[11px] leading-relaxed text-muted">
        Self-hosted company memory.
        <br />
        One owner. No login.
      </p>
    </aside>
  );
}
