"use client";

import { Button, type ButtonProps } from "@/components/beautifului/primitives/button";
import { useCallback, useState } from "react";

export function ClipboardIcon({ size = 12 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <rect x="9" y="9" width="12" height="12" rx="2.5" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

export function CheckIcon({ size = 12 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M20 6L9 17l-5-5" />
    </svg>
  );
}

type CopyButtonProps = Omit<ButtonProps, "onClick" | "children"> & {
  /** String or async resolver (e.g. fetch then copy). */
  text: string | (() => string | Promise<string>);
  label?: string;
  copiedLabel?: string;
  holdMs?: number;
};

export function CopyButton({
  text,
  label = "Copy",
  copiedLabel = "Copied",
  holdMs = 1500,
  variant = "secondary",
  size = "sm",
  ...props
}: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const onCopy = useCallback(() => {
    void (async () => {
      const value = typeof text === "function" ? await text() : text;
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), holdMs);
    })();
  }, [text, holdMs]);

  return (
    <Button
      type="button"
      variant={variant}
      size={size}
      onClick={onCopy}
      {...props}
    >
      {copied ? <CheckIcon /> : <ClipboardIcon />}
      {copied ? copiedLabel : label}
    </Button>
  );
}
