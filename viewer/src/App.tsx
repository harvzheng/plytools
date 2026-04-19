import { useQuery } from "@tanstack/react-query";
import { api } from "./lib/api";
import { useMemoryEvents } from "./lib/useMemoryEvents";

export function App() {
  useMemoryEvents();
  const { data, isLoading, error } = useQuery({
    queryKey: ["index"],
    queryFn: api.getIndex,
  });

  if (isLoading) return <div style={{ padding: 24 }}>Loading…</div>;
  if (error) return <div style={{ padding: 24 }}>Error: {String(error)}</div>;

  return (
    <div style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <h1>plytools viewer</h1>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}
