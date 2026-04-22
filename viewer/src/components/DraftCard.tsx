import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ParsedDraft } from "../lib/types";
import { api } from "../lib/api";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Separator } from "./ui/separator";
import { ChevronDown, ChevronRight, Copy, Check, Pencil, Save, X } from "lucide-react";
import { PathButton } from "./PathButton";
import { slugFromEventPath } from "../lib/useMemoryEvents";

function chipsFromFrontmatter(fm: Record<string, unknown>) {
  const chips: Array<{ key: string; label: string }> = [];
  const s = (v: unknown) => (typeof v === "string" ? v : undefined);
  if (s(fm.persona)) chips.push({ key: "persona", label: `persona: ${fm.persona}` });
  if (s(fm.variant)) chips.push({ key: "variant", label: `variant: ${fm.variant}` });
  if (s(fm.target)) chips.push({ key: "target", label: `target: ${fm.target}` });
  const oid = s(fm.originSessionId);
  if (oid) chips.push({ key: "origin", label: `origin: ${oid.slice(0, 8)}` });
  return chips;
}

export function DraftCard({
  draft,
}: {
  draft: ParsedDraft;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(true);
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(draft.raw);
  const chips = chipsFromFrontmatter(draft.frontmatter);

  // Reset the edit buffer whenever the underlying file changes on disk (e.g.
  // an external edit comes in while the card is collapsed but not in edit mode).
  useEffect(() => {
    if (!editing) setText(draft.raw);
  }, [draft.raw, editing]);

  const save = useMutation({
    mutationFn: (next: string) => api.saveDraft(draft.path, next),
    onSuccess: () => {
      setEditing(false);
      const slug = slugFromEventPath(draft.path);
      if (slug) void qc.invalidateQueries({ queryKey: ["application", slug] });
    },
  });

  async function copy() {
    try {
      await navigator.clipboard.writeText(draft.body);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (e) {
      console.error(e);
    }
  }

  return (
    <div className="rounded-md border">
      <div className="flex items-center gap-2 p-3">
        <button
          className="flex flex-1 items-center gap-2 text-left"
          onClick={() => setOpen((o) => !o)}
        >
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          <span className="font-mono text-sm">{draft.name}</span>
          <div className="ml-2 flex flex-wrap gap-1">
            {chips.map((c) => (
              <Badge key={c.key} variant="secondary">{c.label}</Badge>
            ))}
          </div>
        </button>
        {editing ? (
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setText(draft.raw);
                setEditing(false);
              }}
              disabled={save.isPending}
            >
              <X className="mr-1 h-3 w-3" /> Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => save.mutate(text)}
              disabled={save.isPending || text === draft.raw}
            >
              <Save className="mr-1 h-3 w-3" /> {save.isPending ? "Saving…" : "Save"}
            </Button>
          </>
        ) : (
          <>
            <Button variant="outline" size="sm" onClick={copy}>
              {copied ? <Check className="mr-1 h-3 w-3" /> : <Copy className="mr-1 h-3 w-3" />}
              {copied ? "Copied" : "Copy draft"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setOpen(true);
                setEditing(true);
              }}
            >
              <Pencil className="mr-1 h-3 w-3" /> Edit
            </Button>
            <PathButton label="Editor" icon={<Pencil className="h-3 w-3" />} path={draft.path} />
          </>
        )}
      </div>
      {open && (
        <>
          <Separator />
          <div className="p-3">
            {editing ? (
              <>
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  className="h-80 w-full resize-y rounded-sm border border-input bg-background p-2 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-ring"
                  spellCheck={false}
                />
                {save.error && (
                  <div className="mt-2 text-xs text-destructive">
                    {String(save.error)}
                  </div>
                )}
              </>
            ) : (
              <div className="prose prose-sm max-w-none prose-headings:mt-4 prose-headings:mb-2 prose-p:my-2">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{draft.body}</ReactMarkdown>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
