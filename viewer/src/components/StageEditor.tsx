import { Fragment } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { StageBadge } from "./StageBadge";
import { Button } from "./ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { ChevronDown, Check } from "lucide-react";
import { cn } from "../lib/utils";
import { stagesByBucket } from "../lib/stages";

export function StageEditor({
  slug,
  stage,
  className,
}: {
  slug: string;
  stage: string;
  className?: string;
}) {
  const qc = useQueryClient();

  const mutation = useMutation({
    mutationFn: (next: string) => api.patchStatus(slug, { stage: next }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["index"] });
      void qc.invalidateQueries({ queryKey: ["application", slug] });
    },
  });

  const groups = stagesByBucket();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={cn("h-auto gap-1 px-1 py-0.5", className)}
          onClick={(e) => e.stopPropagation()}
          title="Change stage"
          disabled={mutation.isPending}
        >
          <StageBadge stage={stage} />
          <ChevronDown className="h-3 w-3 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-96 w-64 overflow-auto">
        {groups.map((g, gi) => (
          <Fragment key={g.bucket}>
            {gi > 0 && <DropdownMenuSeparator />}
            <DropdownMenuLabel className="flex items-center gap-2 py-1">
              <StageBadge stage={g.bucket} />
            </DropdownMenuLabel>
            {g.stages.map((s) => (
              <DropdownMenuItem
                key={s.label}
                onSelect={() => {
                  if (s.label !== stage) mutation.mutate(s.label);
                }}
                className="flex items-center justify-between pl-6"
              >
                <span>{s.label}</span>
                {s.label === stage && <Check className="h-3 w-3 text-muted-foreground" />}
              </DropdownMenuItem>
            ))}
          </Fragment>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
