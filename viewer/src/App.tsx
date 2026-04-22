import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./lib/api";
import { useMemoryEvents } from "./lib/useMemoryEvents";
import { IndexTable } from "./components/IndexTable";
import { DetailPane } from "./components/DetailPane";
import { ConnectionIndicator } from "./components/ConnectionIndicator";

export function App() {
  const conn = useMemoryEvents();
  const [selected, setSelected] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<string | null>(null);

  const indexQuery = useQuery({
    queryKey: ["index"],
    queryFn: api.getIndex,
  });

  const viewQuery = useQuery({
    queryKey: ["view", activeView],
    queryFn: () => api.runView(activeView!),
    enabled: activeView !== null,
  });

  const viewsQuery = useQuery({
    queryKey: ["views"],
    queryFn: api.listViews,
  });

  const data = activeView !== null ? viewQuery.data : indexQuery.data;
  const isLoading = activeView !== null ? viewQuery.isLoading : indexQuery.isLoading;
  const error = activeView !== null ? viewQuery.error : indexQuery.error;

  const selectedRow =
    data && selected ? data.find((r) => r.slug === selected) ?? null : null;

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-baseline gap-4 border-b p-4">
        <h1 className="text-xl font-semibold">plytools viewer</h1>
        <span className="text-sm text-muted-foreground">
          {data ? `${data.length} application${data.length === 1 ? "" : "s"}` : ""}
        </span>
        <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          <ConnectionIndicator connected={conn.connected} staleFor={conn.staleFor} />
          <span>live</span>
        </div>
      </header>
      <div className="flex min-h-0 flex-1">
        <div className="flex-[1.2] overflow-auto border-r p-4">
          {isLoading && <div>Loading…</div>}
          {error && <div className="text-destructive">Error: {String(error)}</div>}
          {data && (
            <IndexTable
              rows={data}
              selectedSlug={selected}
              onSelect={setSelected}
              savedViews={viewsQuery.data ?? []}
              activeView={activeView}
              onViewChange={setActiveView}
            />
          )}
        </div>
        <div className="flex-1 overflow-hidden">
          <DetailPane
            slug={selected}
            company={selectedRow?.company ?? null}
            role={selectedRow?.role ?? null}
          />
        </div>
      </div>
    </div>
  );
}
