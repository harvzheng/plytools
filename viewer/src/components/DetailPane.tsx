import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Application } from "../lib/types";
import { api } from "../lib/api";
import { StageBadge } from "./StageBadge";
import { Button } from "./ui/button";
import { Separator } from "./ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { FolderOpen } from "lucide-react";

function OpenFolderButton({ slug: _slug }: { slug: string }) {
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={async () => {
        try {
          // The folder path is resolved server-side by deriving it from the slug
          // and the memory dir. The client just passes a relative-looking path
          // that the server joins to memoryDir and validates via realpath.
          // But /api/open expects an absolute path inside memoryDir, so the
          // server can't reconstruct it without a path. We therefore store the
          // memoryDir alongside the app payload — see /api/application. Since
          // we don't expose memoryDir to the client, we use a sentinel: the
          // server accepts a "slug-relative" path of the form "applications/<slug>".
          // (See api.ts — but for safety we pass an absolute path.)
          // Simpler: call /api/open with a path computed from one of the known
          // file paths returned by the detail payload. Here we use the status
          // or first draft path — but those aren't returned either. For v1
          // we skip this button and rely on per-file Open-in-editor inside
          // Drafts cards. The button stays for parity but does nothing unless
          // a known file is available.
          console.warn("Open folder not yet wired — use per-draft Open in editor.");
        } catch (e) {
          console.error(e);
        }
      }}
      disabled
      title="Use per-draft 'Open in editor' buttons for now"
    >
      <FolderOpen className="mr-1 h-3 w-3" />
      Open folder
    </Button>
  );
}

function FieldGrid({ fields }: { fields: Record<string, string> }) {
  const entries = Object.entries(fields);
  if (entries.length === 0) return null;
  return (
    <dl className="grid grid-cols-[120px_1fr] gap-x-4 gap-y-1 text-sm">
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-foreground">{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Markdown({ source }: { source: string }) {
  return (
    <div className="prose prose-sm max-w-none prose-headings:mt-4 prose-headings:mb-2 prose-p:my-2 prose-li:my-0 prose-table:text-sm">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{source}</ReactMarkdown>
    </div>
  );
}

export function DetailPane({ slug }: { slug: string | null }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["application", slug],
    queryFn: () => api.getApplication(slug!),
    enabled: !!slug,
  });

  if (!slug) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        Select an application
      </div>
    );
  }
  if (isLoading) return <div className="p-4">Loading…</div>;
  if (error) return <div className="p-4 text-destructive">Error: {String(error)}</div>;
  if (!data) return null;

  const app: Application = data;
  const company = app.status.fields["Stage"]
    ? app.slug // status file may not carry company; fall back to slug
    : app.slug;
  const stage = app.status.fields["Stage"] ?? "Unknown";

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b p-4">
        <div className="flex-1">
          <div className="text-sm text-muted-foreground">{company}</div>
          <div className="flex items-center gap-2">
            <StageBadge stage={stage} />
          </div>
        </div>
        <OpenFolderButton slug={app.slug} />
      </div>
      <Tabs defaultValue="overview" className="flex flex-1 flex-col overflow-hidden">
        <TabsList className="m-4 self-start">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="jd">JD</TabsTrigger>
          <TabsTrigger value="contacts">Contacts</TabsTrigger>
          <TabsTrigger value="drafts">Drafts ({app.drafts.length})</TabsTrigger>
        </TabsList>
        <div className="flex-1 overflow-auto px-4 pb-4">
          <TabsContent value="overview">
            {Object.keys(app.status.fields).length > 0 ? (
              <FieldGrid fields={app.status.fields} />
            ) : (
              <Markdown source={app.status.markdown} />
            )}
            <Separator className="my-4" />
            <Markdown source={app.status.markdown} />
          </TabsContent>
          <TabsContent value="jd">
            <FieldGrid fields={app.jd.fields} />
            <Separator className="my-4" />
            <Markdown source={app.jd.markdown} />
          </TabsContent>
          <TabsContent value="contacts">
            <Markdown source={app.contacts.markdown} />
          </TabsContent>
          <TabsContent value="drafts">
            <div className="text-sm text-muted-foreground">
              Drafts list comes in Task 11.
            </div>
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
