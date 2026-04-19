import { Badge } from "./ui/badge";
import { cn } from "../lib/utils";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";

const BUCKET_CLASS: Record<string, string> = {
  "Folder only":   "bg-rose-100 text-rose-900 hover:bg-rose-100",
  "Discovered":    "bg-zinc-200 text-zinc-800 hover:bg-zinc-200",
  "In progress":   "bg-sky-100 text-sky-800 hover:bg-sky-100",
  "Drafts ready":  "bg-amber-100 text-amber-900 hover:bg-amber-100",
  "Sent":          "bg-emerald-100 text-emerald-900 hover:bg-emerald-100",
  "Replied":       "bg-emerald-200 text-emerald-900 hover:bg-emerald-200",
};

export function bucketStage(stage: string): string {
  const s = stage.toLowerCase();
  if (s === "folder only") return "Folder only";
  if (/(reply|replied|interview|offer|declined|passed)/.test(s)) return "Replied";
  if (/(sent|emailed|warm-intro requested)/.test(s)) return "Sent";
  if (/draft/.test(s)) return "Drafts ready";
  if (/(contact|tiered|jd ingested|awaiting|target)/.test(s)) return "In progress";
  return "Discovered";
}

export function StageBadge({ stage, className }: { stage: string; className?: string }) {
  const bucket = bucketStage(stage);
  const cls = BUCKET_CLASS[bucket];
  // If the original stage equals the canonical label, no need for a tooltip.
  const showTooltip = stage.trim() !== bucket;

  const badge = (
    <Badge variant="secondary" className={cn(cls, "border-none whitespace-nowrap", className)}>
      {bucket}
    </Badge>
  );

  if (!showTooltip) return badge;

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span>{badge}</span>
        </TooltipTrigger>
        <TooltipContent className="max-w-md">{stage}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
