"use client";

import { useEffect, useState } from "react";

export function StreamText({
  text,
  ms = 18,
  onProgress,
  onDone,
}: {
  text: string;
  ms?: number;
  onProgress?: () => void;
  onDone?: () => void;
}) {
  const [count, setCount] = useState(0);
  const done = count >= text.length;

  useEffect(() => {
    if (done) {
      onDone?.();
      return;
    }
    const t = setTimeout(() => {
      setCount((c) => c + 1);
      onProgress?.();
    }, ms);
    return () => clearTimeout(t);
  }, [count, done, ms, onDone, onProgress]);

  return (
    <>
      {text.slice(0, count)}
      {!done && (
        <span
          className="ml-0.5 inline-block h-3 w-[2px] translate-y-0.5 rounded-full bg-ink"
          style={{ animation: "caret-blink 900ms step-end infinite" }}
        />
      )}
    </>
  );
}
