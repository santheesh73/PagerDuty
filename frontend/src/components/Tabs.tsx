import { useRef, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface TabItem<K extends string> {
  key: K;
  label: ReactNode;
  count?: number;
}

/** WAI-ARIA tabs: arrow keys move between tabs, the active one is the only tab stop. */
export function Tabs<K extends string>({
  items,
  value,
  onChange,
  label,
  className,
}: {
  items: TabItem<K>[];
  value: K;
  onChange: (key: K) => void;
  label: string;
  className?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const move = (index: number) => {
    const next = (index + items.length) % items.length;
    refs.current[next]?.focus();
    onChange(items[next]!.key);
  };
  return (
    <div
      role="tablist"
      aria-label={label}
      className={cn("flex gap-1 overflow-x-auto border-b border-border", className)}
    >
      {items.map((item, index) => {
        const selected = item.key === value;
        return (
          <button
            key={item.key}
            ref={(el) => {
              refs.current[index] = el;
            }}
            role="tab"
            type="button"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.key)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight") move(index + 1);
              if (e.key === "ArrowLeft") move(index - 1);
            }}
            className={cn(
              "-mb-px inline-flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors",
              selected
                ? "border-accent text-text"
                : "border-transparent text-muted hover:border-border-strong hover:text-text",
            )}
          >
            {item.label}
            {item.count !== undefined && (
              <span
                className={cn(
                  "tabular rounded-full px-1.5 text-xs",
                  selected ? "bg-accent-soft text-accent" : "bg-surface-2 text-muted",
                )}
              >
                {item.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
