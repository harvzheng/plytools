import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { MemoryEvent } from "./types";

export function slugFromEventPath(path: string): string | null {
  // Matches applications/<company>/<role>/... — the composite slug is
  // "<company>/<role>" so query-key invalidation targets just the affected
  // role instead of sweeping every role under a company.
  const m = path.match(/\/applications\/([^/]+)\/([^/]+)\//);
  return m ? `${m[1]}/${m[2]}` : null;
}

export interface ConnectionState {
  connected: boolean;
  staleFor: number; // ms since last drop, 0 when connected
}

export function useMemoryEvents(): ConnectionState {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [lastDropAt, setLastDropAt] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const es = new EventSource("/api/events");
    es.onopen = () => {
      setConnected(true);
      setLastDropAt(null);
    };
    es.onerror = () => {
      setConnected(false);
      setLastDropAt((prev) => prev ?? Date.now());
    };
    es.onmessage = (raw) => {
      try {
        const ev: MemoryEvent = JSON.parse(raw.data);
        const slug = slugFromEventPath(ev.path);
        void qc.invalidateQueries({
          predicate: (q) =>
            q.queryKey[0] === "index" ||
            q.queryKey[0] === "view" ||
            (q.queryKey[0] === "application" && q.queryKey[1] === slug),
        });
      } catch {
        // ignore malformed events
      }
    };
    return () => es.close();
  }, [qc]);

  useEffect(() => {
    if (connected) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [connected]);

  const staleFor = !connected && lastDropAt ? now - lastDropAt : 0;
  return { connected, staleFor };
}
