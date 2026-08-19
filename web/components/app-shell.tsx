import { AppHeader } from "@/components/app-header";
import { AuthGate } from "@/components/auth-gate";
import { SystemBanners } from "@/components/system-banners";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <div className="flex h-dvh min-h-0 flex-col bg-page">
        <AppHeader />
        <SystemBanners />
        <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
          {children}
        </main>
      </div>
    </AuthGate>
  );
}
