"use client";

import { cn } from "@/lib/utils";
import {
  useCallback,
  useRef,
  useState,
  type HTMLAttributes,
  type PointerEvent,
} from "react";

/**
 * One sliding highlight behind `[data-menu-row]` children.
 * Used by Search, Records Table, and Fine-tune Card.
 */
export default function GlideMenu({
  className,
  highlightClassName,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement> & { highlightClassName?: string }) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<{ top: number; height: number } | null>(null);

  const moveTo = useCallback((row: HTMLElement | null) => {
    const root = rootRef.current;
    if (!root || !row) return;
    setBox({ top: row.offsetTop, height: row.offsetHeight });
  }, []);

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const row = (event.target as HTMLElement).closest<HTMLElement>(
      "[data-menu-row]",
    );
    if (row && rootRef.current?.contains(row)) moveTo(row);
  };

  return (
    <div
      ref={rootRef}
      className={cn("relative", className)}
      onPointerMove={onPointerMove}
      onPointerLeave={() => setBox(null)}
      {...props}
    >
      <span
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-x-0 z-0 transition-[transform,height,opacity] duration-200",
          highlightClassName,
        )}
        style={{
          height: box?.height ?? 0,
          opacity: box ? 1 : 0,
          transform: `translateY(${box?.top ?? 0}px)`,
          transitionTimingFunction: "cubic-bezier(0.16, 1, 0.3, 1)",
        }}
      />
      {children}
    </div>
  );
}
