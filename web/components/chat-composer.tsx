import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { Square } from "lucide-react";
import type { FormEvent } from "react";

export function ChatComposer({
  value,
  onChange,
  onSubmit,
  onStop,
  placeholder = "Ask the company's memory…",
  disabled = false,
  busy = false,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
  onStop?: () => void;
  placeholder?: string;
  disabled?: boolean;
  busy?: boolean;
  className?: string;
}) {
  return (
    <form
      className={cn("border-t border-[var(--line)] p-4", className)}
      onSubmit={onSubmit}
    >
      <div className="mx-auto flex max-w-2xl gap-2">
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          aria-label="Ask the company's memory"
          className="flex-1"
        />
        {busy && onStop ? (
          <Button type="button" variant="ghost" onClick={onStop}>
            <Square size={14} />
            Stop
          </Button>
        ) : (
          <Button type="submit" disabled={disabled || !value.trim()}>
            Ask
          </Button>
        )}
      </div>
    </form>
  );
}
