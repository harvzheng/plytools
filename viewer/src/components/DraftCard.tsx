import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ParsedDraft } from "../lib/types";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Separator } from "./ui/separator";
import { ChevronDown, ChevronRight, Copy, Check, Pencil } from "lucide-react";
import { PathButton } from "./PathButton";

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
  const [open, setOpen] = useState(true);
  const [copied, setCopied] = useState(false);
  const chips = chipsFromFrontmatter(draft.frontmatter);

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
        <Button variant="outline" size="sm" onClick={copy}>
          {copied ? <Check className="mr-1 h-3 w-3" /> : <Copy className="mr-1 h-3 w-3" />}
          {copied ? "Copied" : "Copy draft"}
        </Button>
        <PathButton label="Editor" icon={<Pencil className="h-3 w-3" />} path={draft.path} />
      </div>
      {open && (
        <>
          <Separator />
          <div className="p-3">
            <div className="prose prose-sm max-w-none prose-headings:mt-4 prose-headings:mb-2 prose-p:my-2">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{draft.body}</ReactMarkdown>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
