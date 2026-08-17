export function ReasoningPath({ paths }: { paths: string[] }) {
  return (
    <details className="text-sm text-ink-soft">
      <summary className="cursor-pointer hover:text-ink">Reasoning path</summary>
      <ul className="mt-2 space-y-1 border-l border-[var(--line)] pl-3 font-mono text-xs">
        {paths.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ul>
    </details>
  );
}
