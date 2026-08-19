import { BrandMark } from "@/components/brand-mark";

export function AuthScreen({
  kicker,
  title,
  children,
}: {
  kicker?: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto flex min-h-dvh max-w-[var(--page-max)] flex-col justify-center px-[var(--app-gutter)] py-16">
      <header className="mb-8 space-y-4">
        <BrandMark size={28} withWordmark />
        {kicker ? <p className="text-[12px] text-ink-3">{kicker}</p> : null}
        <h1 className="text-[15px] font-semibold tracking-tight text-ink">{title}</h1>
      </header>
      {children}
    </div>
  );
}
