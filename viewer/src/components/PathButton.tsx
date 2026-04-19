import { useState } from "react";
import { Button } from "./ui/button";
import { Check, Copy, ExternalLink } from "lucide-react";
import { api } from "../lib/api";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";

export function PathButton({
  label,
  icon,
  path,
}: {
  label: string;
  icon: React.ReactNode;
  path: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(path);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (e) {
      console.error(e);
    }
  }

  async function open() {
    try {
      await api.open(path);
    } catch (e) {
      console.error(e);
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm">
          {icon}
          <span className="ml-1">{label}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[420px] p-3">
        <div className="font-mono text-xs break-all rounded bg-muted/60 px-2 py-2 mb-3 select-all">
          {path}
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={copy} className="flex-1">
            {copied ? <Check className="mr-1 h-3 w-3" /> : <Copy className="mr-1 h-3 w-3" />}
            {copied ? "Copied" : "Copy path"}
          </Button>
          <Button size="sm" variant="outline" onClick={open} className="flex-1">
            <ExternalLink className="mr-1 h-3 w-3" /> Try open
          </Button>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
