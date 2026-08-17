import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function ChatComposer({
  value = "",
  placeholder = "Ask the company's memory…",
  className,
}: {
  value?: string;
  placeholder?: string;
  className?: string;
}) {
  return (
    <div className={cn("border-t border-[var(--line)] p-4", className)}>
      <div className="mx-auto flex max-w-2xl gap-2">
        <input
          readOnly
          value={value}
          placeholder={placeholder}
          className="flex-1 rounded-[var(--radius-sm)] border border-[var(--line)] bg-inset px-3.5 py-2.5 text-[15px] text-ink outline-none placeholder:text-muted"
        />
        <Button type="button" disabled={!value.trim()}>
          Ask
        </Button>
      </div>
    </div>
  );
}
