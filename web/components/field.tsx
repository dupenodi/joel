import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { cloneElement, isValidElement, useId, type ReactElement } from "react";

type FieldChildProps = {
  id?: string;
  "aria-invalid"?: boolean;
  "aria-describedby"?: string;
};

export function Field({
  label,
  hint,
  error,
  htmlFor,
  children,
  className,
}: {
  label: string;
  hint?: string;
  error?: string;
  htmlFor?: string;
  children: React.ReactNode;
  className?: string;
}) {
  const generatedId = useId();
  const noteId = useId();
  const fieldId = htmlFor ?? generatedId;
  const hasNote = Boolean(error || hint);

  const child = isValidElement(children)
    ? cloneElement(children as ReactElement<FieldChildProps>, {
        id: (children as ReactElement<FieldChildProps>).props.id ?? fieldId,
        "aria-invalid": error ? true : undefined,
        "aria-describedby": hasNote ? noteId : undefined,
      })
    : children;

  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={fieldId}>{label}</Label>
      {child}
      {hasNote && (
        <p id={noteId} className={cn("text-xs", error ? "text-accent" : "text-muted")}>
          {error ?? hint}
        </p>
      )}
    </div>
  );
}
