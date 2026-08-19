import { cn } from "@/lib/utils";

/** Inner header rail. Full-bleed chrome, this width. */
export function AppFrame({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "mx-auto w-full max-w-[var(--app-max)] px-[var(--app-gutter)]",
        className,
      )}
    >
      {children}
    </div>
  );
}

type ContentWidth = "chat" | "page" | "wide";

const WIDTH: Record<ContentWidth, string> = {
  chat: "max-w-[var(--chat-max)]",
  page: "max-w-[var(--page-max)]",
  wide: "max-w-[var(--wide-max)]",
};

/** Centered page column. Same gutter as the header. */
export function ContentFrame({
  width = "page",
  className,
  children,
}: {
  width?: ContentWidth;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "mx-auto w-full px-[var(--app-gutter)]",
        WIDTH[width],
        className,
      )}
    >
      {children}
    </div>
  );
}
