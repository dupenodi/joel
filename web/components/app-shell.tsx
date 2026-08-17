import { AppNav } from "@/components/app-nav";
import { SystemBanners } from "@/components/system-banners";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-full bg-bg">
      <AppNav />
      <div className="flex min-w-0 flex-1 flex-col">
        <SystemBanners />
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  );
}
