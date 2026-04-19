import type { Application, IndexRow } from "./types";

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  async getIndex(): Promise<IndexRow[]> {
    return j<IndexRow[]>(await fetch("/api/index"));
  },
  async getApplication(slug: string): Promise<Application> {
    return j<Application>(await fetch(`/api/application/${encodeURIComponent(slug)}`));
  },
  async open(path: string): Promise<void> {
    const res = await fetch("/api/open", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ path }),
    });
    if (!res.ok) throw new Error(`open failed: ${res.status}`);
  },
};
