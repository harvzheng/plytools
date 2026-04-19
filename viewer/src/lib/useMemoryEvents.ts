import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { MemoryEvent } from "./types";

export function slugFromEventPath(path: string): string | null {
  const m = path.match(/\/applications\/([^/]+)\//);
  return m ? m[1] : null;
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
        if (ev.path.endsWith("/applications/index.md")) {
          void qc.invalidateQueries({ queryKey: ["index"] });
        } else {
          const slug = slugFromEventPath(ev.path);
          if (slug) {
            void qc.invalidateQueries({ queryKey: ["application", slug] });
            void qc.invalidateQueries({ queryKey: ["index"] });
          }
        }
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
