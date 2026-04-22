import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { cn } from "../lib/utils";

export function PriorityInput({
  slug,
  value,
  className,
}: {
  slug: string;
  value: number | null;
  className?: string;
}) {
  const qc = useQueryClient();
  const [text, setText] = useState(value === null ? "" : String(value));
  const inputRef = useRef<HTMLInputElement>(null);

  // Keep the input in sync when the underlying value changes from another
  // surface (e.g. the detail pane sets priority while the table cell is visible).
  useEffect(() => {
    setText(value === null ? "" : String(value));
  }, [value]);

  const mutation = useMutation({
    mutationFn: (next: number | null) => api.patchStatus(slug, { priority: next }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["index"] });
      void qc.invalidateQueries({ queryKey: ["application", slug] });
    },
  });

  function commit() {
    const trimmed = text.trim();
    const parsed = trimmed === "" ? null : parseInt(trimmed, 10);
    if (trimmed !== "" && !Number.isFinite(parsed)) {
      setText(value === null ? "" : String(value));
      return;
    }
    if (parsed === value) return;
    mutation.mutate(parsed as number | null);
  }

  return (
    <div
      className={cn(
        "flex h-7 items-center rounded-sm border border-transparent pl-1 text-sm tabular-nums",
        "hover:border-border focus-within:border-ring focus-within:ring-1 focus-within:ring-ring",
        className
      )}
      onClick={(e) => e.stopPropagation()}
    >
      <span
        className={cn(
          "select-none pr-0.5 text-muted-foreground",
          text === "" && "opacity-40"
        )}
      >
        P
      </span>
      <input
        ref={inputRef}
        type="number"
        inputMode="numeric"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            inputRef.current?.blur();
          } else if (e.key === "Escape") {
            setText(value === null ? "" : String(value));
            inputRef.current?.blur();
          }
        }}
        placeholder="—"
        className={cn(
          "h-full w-10 border-none bg-transparent p-0 text-left focus:outline-none",
          "[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
        )}
      />
    </div>
  );
}
