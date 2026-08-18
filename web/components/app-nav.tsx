"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { BrandMark } from "@/components/brand-mark";
import { IconButton } from "@/components/ui/icon-button";
import { MobileDrawer } from "@/components/ui/drawer";
import {
  Cable,
  Menu,
  MessageSquare,
  Settings,
  UserRound,
  X,
} from "lucide-react";
import { cn, navItemTone } from "@/lib/utils";

const links = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/connectors", label: "Integrations", icon: Cable },
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/profile", label: "Profile", icon: UserRound },
] as const;

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <nav className="flex flex-1 flex-col gap-1">
      {links.map(({ href, label, icon: Icon }) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            className={cn(
              "flex items-center gap-2.5 rounded-[var(--radius-sm)] px-3 py-2.5 text-sm transition-colors",
              navItemTone(active),
            )}
          >
            <Icon size={17} strokeWidth={1.75} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

export function AppNav() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <div className="flex w-full items-center justify-between border-b border-[var(--line)] bg-bg px-4 py-3 md:hidden">
        <Link href="/chat" className="flex items-center">
          <BrandMark size={32} withWordmark />
        </Link>
        <IconButton
          aria-label="Open menu"
          aria-expanded={open}
          onClick={() => setOpen(true)}
        >
          <Menu size={20} />
        </IconButton>
      </div>

      <aside className="hidden h-full w-[var(--nav-w)] shrink-0 flex-col border-r border-[var(--line)] bg-bg px-3 py-5 md:flex">
        <Link href="/chat" className="mb-8 px-2">
          <BrandMark size={40} withWordmark />
        </Link>
        <NavLinks />
        <p className="px-2 text-[11px] leading-relaxed text-muted">
          Self-hosted company memory.
          <br />
          One owner. No login.
        </p>
      </aside>

      <MobileDrawer open={open} onClose={() => setOpen(false)} label="Navigation">
        <div className="flex items-center justify-between border-b border-[var(--line)] px-4 py-3">
          <BrandMark size={32} withWordmark />
          <IconButton aria-label="Close menu" onClick={() => setOpen(false)}>
            <X size={20} />
          </IconButton>
        </div>
        <div className="flex flex-1 flex-col px-3 py-5">
          <NavLinks onNavigate={() => setOpen(false)} />
          <p className="px-2 text-[11px] leading-relaxed text-muted">
            Self-hosted company memory.
            <br />
            One owner. No login.
          </p>
        </div>
      </MobileDrawer>
    </>
  );
}
