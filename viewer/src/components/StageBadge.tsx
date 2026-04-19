import { Badge } from "./ui/badge";
import { cn } from "../lib/utils";

// Stage→color mapping lives here so new stages render with a default gray
// badge rather than breaking.
const STAGE_CLASS: Record<string, string> = {
  Discovered: "bg-zinc-200 text-zinc-800 hover:bg-zinc-200",
  "JD ingested": "bg-sky-100 text-sky-800 hover:bg-sky-100",
  "Contacts pulled": "bg-sky-100 text-sky-800 hover:bg-sky-100",
  "Warm-intro requested": "bg-indigo-100 text-indigo-900 hover:bg-indigo-100",
  Draft: "bg-amber-100 text-amber-900 hover:bg-amber-100",
  "Drafts ready": "bg-amber-100 text-amber-900 hover:bg-amber-100",
  Sent: "bg-emerald-100 text-emerald-900 hover:bg-emerald-100",
  Replied: "bg-emerald-200 text-emerald-900 hover:bg-emerald-200",
  Passed: "bg-rose-100 text-rose-900 hover:bg-rose-100",
  "Folder only": "bg-rose-100 text-rose-900 hover:bg-rose-100",
};

export function StageBadge({ stage, className }: { stage: string; className?: string }) {
  const cls = STAGE_CLASS[stage] ?? "bg-zinc-100 text-zinc-700 hover:bg-zinc-100";
  return (
    <Badge variant="secondary" className={cn(cls, "border-none", className)}>
      {stage}
    </Badge>
  );
}
