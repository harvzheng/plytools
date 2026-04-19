import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { MemoryEvent } from "./types";

export function slugFromEventPath(path: string): string | null {
  const m = path.match(/\/applications\/([^/]+)\//);
  return m ? m[1] : null;
}

export function useMemoryEvents() {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [lastDropAt, setLastDropAt] = useState<number | null>(null);

  useEffect(() => {
    const es = new EventSource("/api/events");
    es.onopen = () => setConnected(true);
    es.onerror = () => {
      setConnected(false);
      setLastDropAt(Date.now());
      // EventSource auto-reconnects; no manual logic needed.
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

  return { connected, lastDropAt };
}
