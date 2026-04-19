import { cn } from "../lib/utils";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";

export function ConnectionIndicator({
  connected,
  staleFor,
}: {
  connected: boolean;
  staleFor: number;
}) {
  const amber = !connected && staleFor > 3000;
  const color = connected ? "bg-emerald-500" : amber ? "bg-amber-500" : "bg-zinc-300";
  const label = connected
    ? "Live reload connected"
    : amber
      ? `Disconnected (${Math.floor(staleFor / 1000)}s)`
      : "Connecting…";

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className={cn("inline-block h-2 w-2 rounded-full", color)} aria-label={label} />
        </TooltipTrigger>
        <TooltipContent>{label}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
