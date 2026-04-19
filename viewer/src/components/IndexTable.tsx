import { useMemo, useState } from "react";
import {
  ColumnDef,
  ColumnFiltersState,
  SortingState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import type { IndexRow } from "../lib/types";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { Input } from "./ui/input";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { Button } from "./ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import { StageBadge } from "./StageBadge";
import { ChevronDown, ArrowUpDown } from "lucide-react";

function truncate(s: string, n = 60) {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function relativeTime(isoDate: string): string {
  const d = new Date(isoDate);
  if (isNaN(d.getTime())) return isoDate;
  const diffDays = Math.floor((Date.now() - d.getTime()) / 86_400_000);
  if (diffDays === 0) return "today";
  if (diffDays === 1) return "1d ago";
  if (diffDays < 30) return `${diffDays}d ago`;
  if (diffDays < 365) return `${Math.floor(diffDays / 30)}mo ago`;
  return `${Math.floor(diffDays / 365)}y ago`;
}

export function IndexTable({
  rows,
  selectedSlug,
  onSelect,
}: {
  rows: IndexRow[];
  selectedSlug: string | null;
  onSelect: (slug: string) => void;
}) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: "updated", desc: true },
  ]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const [stageFilter, setStageFilter] = useState<string[]>([]);

  const stages = useMemo(
    () => Array.from(new Set(rows.map((r) => r.stage))).sort(),
    [rows]
  );

  const columns = useMemo<ColumnDef<IndexRow>[]>(() => [
    {
      id: "company",
      accessorKey: "company",
      header: ({ column }) => (
        <Button
          variant="ghost"
          size="sm"
          className="-ml-2"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
        >
          Company <ArrowUpDown className="ml-1 h-3 w-3" />
        </Button>
      ),
    },
    {
      id: "role",
      accessorKey: "role",
      header: "Role",
    },
    {
      id: "stage",
      accessorKey: "stage",
      header: "Stage",
      cell: ({ getValue }) => <StageBadge stage={String(getValue())} />,
      filterFn: (row, id, value: string[]) =>
        value.length === 0 || value.includes(row.getValue(id) as string),
    },
    {
      id: "lastAction",
      accessorKey: "lastAction",
      header: "Last action",
      cell: ({ getValue }) => {
        const v = String(getValue());
        return (
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="text-muted-foreground">{truncate(v, 50)}</span>
              </TooltipTrigger>
              <TooltipContent className="max-w-md">{v}</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        );
      },
    },
    {
      id: "nextStep",
      accessorKey: "nextStep",
      header: "Next",
      cell: ({ getValue }) => {
        const v = String(getValue());
        return (
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="text-muted-foreground">{truncate(v, 50)}</span>
              </TooltipTrigger>
              <TooltipContent className="max-w-md">{v}</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        );
      },
    },
    {
      id: "updated",
      accessorKey: "updated",
      header: ({ column }) => (
        <Button
          variant="ghost"
          size="sm"
          className="-ml-2"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
        >
          Updated <ArrowUpDown className="ml-1 h-3 w-3" />
        </Button>
      ),
      cell: ({ getValue }) => {
        const v = String(getValue());
        return (
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <span>{relativeTime(v)}</span>
              </TooltipTrigger>
              <TooltipContent>{v}</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        );
      },
    },
  ], []);

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting, columnFilters, globalFilter },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    globalFilterFn: "includesString",
  });

  // Keep the stage column filter state synced with the dropdown.
  const stageCol = table.getColumn("stage");
  if (stageCol && stageCol.getFilterValue() !== stageFilter) {
    stageCol.setFilterValue(stageFilter);
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Input
          placeholder="Search…"
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          className="max-w-xs"
        />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">
              Stage <ChevronDown className="ml-1 h-3 w-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuLabel>Filter by stage</DropdownMenuLabel>
            {stages.map((s) => (
              <DropdownMenuCheckboxItem
                key={s}
                checked={stageFilter.includes(s)}
                onCheckedChange={(checked) => {
                  setStageFilter((prev) =>
                    checked ? [...prev, s] : prev.filter((x) => x !== s)
                  );
                }}
              >
                {s}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="ml-auto">
              Columns <ChevronDown className="ml-1 h-3 w-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {table.getAllColumns().map((col) => (
              <DropdownMenuCheckboxItem
                key={col.id}
                checked={col.getIsVisible()}
                onCheckedChange={(v) => col.toggleVisibility(!!v)}
              >
                {col.id}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id}>
                {hg.headers.map((h) => (
                  <TableHead key={h.id}>
                    {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="text-center text-muted-foreground">
                  No applications.
                </TableCell>
              </TableRow>
            ) : (
              table.getRowModel().rows.map((row) => {
                const slug = row.original.slug;
                const isSelected = slug === selectedSlug;
                return (
                  <TableRow
                    key={row.id}
                    data-state={isSelected ? "selected" : undefined}
                    className="cursor-pointer"
                    onClick={() => onSelect(slug)}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    ))}
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
