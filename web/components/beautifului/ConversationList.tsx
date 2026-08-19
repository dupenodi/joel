"use client";

export type ConversationRow = {
  id: string;
  title: string;
  when: string;
};

export function ConversationList({
  items,
  activeId,
  onSelect,
}: {
  items: ConversationRow[];
  activeId?: string;
  onSelect?: (id: string) => void;
}) {
  return (
    <div className="flex w-full max-w-64 flex-col gap-px">
      {items.map((item) => {
        const active = item.id === activeId;
        return (
          <button
            key={item.id}
            type="button"
            aria-current={active ? "true" : undefined}
            onClick={() => onSelect?.(item.id)}
            className={`rounded-control px-2.5 py-2 text-left transition-colors duration-150 ${
              active ? "bg-hover text-ink" : "text-ink-2 hover:bg-hover hover:text-ink"
            }`}
          >
            <span className="block truncate text-[13px] font-medium leading-tight">
              {item.title}
            </span>
            <span className="mt-0.5 block text-[11.5px] text-ink-3">{item.when}</span>
          </button>
        );
      })}
    </div>
  );
}
