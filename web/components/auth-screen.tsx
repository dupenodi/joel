import { BrandMark } from "@/components/brand-mark";
import { WorkspaceAvatar } from "@/components/settings/workspace-avatar";

export function AuthScreen({
  kicker,
  title,
  children,
  workspace,
}: {
  kicker?: string;
  title: string;
  children: React.ReactNode;
  workspace?: { name: string; domain: string; logoUrl?: string };
}) {
  return (
    <div className="mx-auto flex min-h-dvh max-w-[var(--page-max)] flex-col justify-center px-[var(--app-gutter)] py-16">
      <header className="mb-8 space-y-4">
        <BrandMark size={28} withWordmark />
        {workspace ? (
          <div className="flex items-center gap-3 rounded-card bg-surface p-3 shadow-card">
            <WorkspaceAvatar
              name={workspace.name}
              logoUrl={workspace.logoUrl}
              size={40}
            />
            <div className="min-w-0">
              <p className="truncate text-[14px] font-semibold text-ink">
                {workspace.name}
              </p>
              <p className="truncate text-[12.5px] text-ink-3">
                {workspace.domain}
              </p>
            </div>
          </div>
        ) : kicker ? (
          <p className="text-[12px] text-ink-3">{kicker}</p>
        ) : null}
        <h1 className="text-[15px] font-semibold tracking-tight text-ink">
          {title}
        </h1>
      </header>
      {children}
    </div>
  );
}
