import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Application } from "../lib/types";
import { api } from "../lib/api";
import { StageBadge } from "./StageBadge";
import { Separator } from "./ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { FolderOpen } from "lucide-react";
import { DraftCard } from "./DraftCard";
import { PathButton } from "./PathButton";

function OpenFolderButton({ dir }: { dir: string }) {
  return <PathButton label="Folder" icon={<FolderOpen className="h-3 w-3" />} path={dir} />;
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

export function DetailPane({
  slug,
  company,
}: {
  slug: string | null;
  company: string | null;
}) {
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
  const stage = app.status.fields["Stage"] ?? "Unknown";

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b p-4">
        <div className="flex-1">
          <div className="text-sm text-muted-foreground">{company ?? app.slug}</div>
          <div className="flex items-center gap-2">
            <StageBadge stage={stage} />
          </div>
        </div>
        <OpenFolderButton dir={app.dir} />
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
            {app.drafts.length === 0 ? (
              <div className="text-sm text-muted-foreground">No drafts yet.</div>
            ) : (
              <div className="flex flex-col gap-3">
                {app.drafts.map((d) => (
                  <DraftCard key={d.name} draft={d} />
                ))}
              </div>
            )}
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
