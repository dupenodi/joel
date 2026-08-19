export function NotFoundCallout({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <p className="text-[12.5px] leading-relaxed text-orange">
      <span className="font-medium">Not found · </span>
      {items.join(" · ")}
    </p>
  );
}

export function AbsentAnswer({
  children = "Not in the company's memory.",
}: {
  children?: string;
}) {
  return (
    <p className="text-[15px] font-semibold tracking-tight text-ink">{children}</p>
  );
}
