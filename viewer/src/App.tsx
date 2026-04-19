import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./lib/api";
import { useMemoryEvents } from "./lib/useMemoryEvents";
import { IndexTable } from "./components/IndexTable";

export function App() {
  useMemoryEvents();
  const [selected, setSelected] = useState<string | null>(null);
  const { data, isLoading, error } = useQuery({
    queryKey: ["index"],
    queryFn: api.getIndex,
  });

  return (
    <div className="flex h-screen flex-col gap-4 p-6">
      <header className="flex items-baseline gap-4">
        <h1 className="text-xl font-semibold">plytools viewer</h1>
        <span className="text-sm text-muted-foreground">
          {data ? `${data.length} application${data.length === 1 ? "" : "s"}` : ""}
        </span>
      </header>
      {isLoading && <div>Loading…</div>}
      {error && <div className="text-destructive">Error: {String(error)}</div>}
      {data && (
        <IndexTable
          rows={data}
          selectedSlug={selected}
          onSelect={setSelected}
        />
      )}
    </div>
  );
}
