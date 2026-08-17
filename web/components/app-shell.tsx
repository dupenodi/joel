import { AppNav } from "@/components/app-nav";
import { SystemBanners } from "@/components/system-banners";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-dvh min-h-0 flex-col bg-bg md:flex-row">
      <AppNav />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <SystemBanners />
        <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
