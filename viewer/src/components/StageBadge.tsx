import { Badge } from "./ui/badge";
import { cn } from "../lib/utils";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import { bucketOf, type Bucket } from "../lib/stages";

const BUCKET_CLASS: Record<Bucket, string> = {
  "Folder only":   "bg-rose-100 text-rose-900 hover:bg-rose-100",
  "Discovered":    "bg-zinc-200 text-zinc-800 hover:bg-zinc-200",
  "In progress":   "bg-sky-100 text-sky-800 hover:bg-sky-100",
  "Drafts ready":  "bg-amber-100 text-amber-900 hover:bg-amber-100",
  "Applied":       "bg-lime-100 text-lime-900 hover:bg-lime-100",
  "Sent":          "bg-emerald-100 text-emerald-900 hover:bg-emerald-100",
  "Replied":       "bg-emerald-200 text-emerald-900 hover:bg-emerald-200",
  "Rejected":      "bg-neutral-200 text-neutral-500 line-through hover:bg-neutral-200",
};

// Backwards-compatible alias — older imports may still call `bucketStage`.
export const bucketStage = bucketOf;

export function StageBadge({ stage, className }: { stage: string; className?: string }) {
  const bucket = bucketOf(stage);
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
