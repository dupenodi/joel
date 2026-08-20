"use client";

import { cn } from "@/lib/utils";
import Link from "next/link";
import { usePathname } from "next/navigation";

export type SettingsNavItem = {
  href: string;
  label: string;
  adminOnly?: boolean;
};

export const SETTINGS_NAV: SettingsNavItem[] = [
  { href: "/settings/general", label: "General" },
  { href: "/settings/members", label: "Members" },
  { href: "/settings/profile", label: "Profile" },
  { href: "/settings/api-keys", label: "API keys" },
  { href: "/settings/models", label: "Models", adminOnly: true },
  { href: "/settings/email", label: "Email", adminOnly: true },
  { href: "/settings/slack", label: "Slack bot", adminOnly: true },
  { href: "/settings/usage", label: "Usage" },
  { href: "/settings/danger", label: "Danger zone", adminOnly: true },
];

export function SettingsNav({ isAdmin }: { isAdmin: boolean }) {
  const pathname = usePathname();
  const items = SETTINGS_NAV.filter((item) => !item.adminOnly || isAdmin);

  return (
    <nav aria-label="Settings" className="flex flex-col gap-0.5">
      {items.map((item) => {
        const active =
          pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-control px-2.5 py-1.5 text-[13.5px] font-medium transition-colors duration-150",
              active
                ? "bg-hover text-ink"
                : "text-ink-2 hover:bg-hover/70 hover:text-ink",
              item.href === "/settings/danger" && !active && "text-red/80 hover:text-red",
              item.href === "/settings/danger" && active && "bg-red-tint text-red",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

/** Mobile: compact horizontal chips under the settings title. */
export function SettingsNavMobile({ isAdmin }: { isAdmin: boolean }) {
  const pathname = usePathname();
  const items = SETTINGS_NAV.filter((item) => !item.adminOnly || isAdmin);

  return (
    <nav
      aria-label="Settings sections"
      className="flex gap-1 overflow-x-auto pb-1 md:hidden"
    >
      {items.map((item) => {
        const active =
          pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "shrink-0 rounded-full px-3 py-1.5 text-[12.5px] font-medium transition-colors",
              active
                ? "bg-ink text-page"
                : "bg-field text-ink-2 hover:text-ink",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
