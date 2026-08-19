"use client";

import { useState } from "react";

export function ReasoningPath({
  paths,
  defaultOpen = false,
}: {
  paths: string[];
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (paths.length === 0) return null;

  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="-mx-1.5 flex w-fit items-center gap-1.5 rounded-control px-1.5 py-1 text-[12.5px] text-ink-2 transition-colors duration-100 hover:bg-hover-2 hover:text-ink"
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="transition-transform duration-200"
          style={{ transform: open ? "rotate(0deg)" : "rotate(-90deg)" }}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
        Reasoning path
        <span className="font-mono text-[11px] text-ink-3 tabular-nums">
          {paths.length}
        </span>
      </button>
      <div
        className="grid transition-[grid-template-rows,opacity] duration-300"
        style={{
          gridTemplateRows: open ? "1fr" : "0fr",
          opacity: open ? 1 : 0,
          transitionTimingFunction: "cubic-bezier(0.23, 1, 0.32, 1)",
        }}
      >
        <div className="overflow-hidden">
          <ul className="mt-1 ml-[5px] space-y-1 border-l border-line py-1 pl-3.5">
            {paths.map((p) => (
              <li
                key={p}
                className="font-mono text-[11.5px] leading-relaxed text-ink-2"
              >
                {p}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
