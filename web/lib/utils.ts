import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  const diff = Date.now() - t;
  const abs = Math.abs(diff);
  const mins = Math.round(abs / 60_000);
  if (mins < 1) return diff >= 0 ? "just now" : "in a moment";
  if (mins < 60) return diff >= 0 ? `${mins}m ago` : `in ${mins}m`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return diff >= 0 ? `${hours}h ago` : `in ${hours}h`;
  const days = Math.round(hours / 24);
  return diff >= 0 ? `${days}d ago` : `in ${days}d`;
}
