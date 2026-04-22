import type { Application, IndexRow, SavedView } from "./types";

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  async getIndex(): Promise<IndexRow[]> {
    return j<IndexRow[]>(await fetch("/api/index"));
  },
  async getApplication(slug: string): Promise<Application> {
    // slug is "<companySlug>/<roleSlug>" — each segment is already a safe slug
    // (a-z0-9_-), so split-then-encodeURIComponent each half to keep the path
    // boundary intact.
    const [companySlug, roleSlug] = slug.split("/");
    if (!companySlug || !roleSlug) {
      throw new Error(`bad slug: ${slug}`);
    }
    return j<Application>(
      await fetch(
        `/api/application/${encodeURIComponent(companySlug)}/${encodeURIComponent(roleSlug)}`
      )
    );
  },
  async open(path: string): Promise<void> {
    const res = await fetch("/api/open", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ path }),
    });
    if (!res.ok) throw new Error(`open failed: ${res.status}`);
  },
  async patchStatus(
    slug: string,
    patch: {
      stage?: string;
      priority?: number | null;
      lastAction?: string;
      nextStep?: string;
    }
  ): Promise<void> {
    const [companySlug, roleSlug] = slug.split("/");
    if (!companySlug || !roleSlug) throw new Error(`bad slug: ${slug}`);
    const res = await fetch(
      `/api/application/${encodeURIComponent(companySlug)}/${encodeURIComponent(roleSlug)}/status`,
      {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(patch),
      }
    );
    if (!res.ok) throw new Error(`patch status failed: ${res.status}`);
  },
  async saveDraft(path: string, content: string): Promise<void> {
    const res = await fetch("/api/draft", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ path, content }),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`save draft failed: ${res.status} ${text}`);
    }
  },
  async listViews(): Promise<SavedView[]> {
    return j<SavedView[]>(await fetch("/api/views"));
  },
  async runView(name: string): Promise<IndexRow[]> {
    return j<IndexRow[]>(await fetch(`/api/views/${encodeURIComponent(name)}`));
  },
};
