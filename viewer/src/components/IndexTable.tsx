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
import type { IndexRow, SavedView } from "../lib/types";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { Input } from "./ui/input";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { Button } from "./ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import { bucketStage } from "./StageBadge";
import { StageEditor } from "./StageEditor";
import { PriorityInput } from "./PriorityInput";
import { cityTags, CITY_ORDER } from "../lib/cityTags";
import { ChevronDown, ArrowUpDown, ListOrdered, BookOpen } from "lucide-react";

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
  savedViews,
  activeView,
  onViewChange,
}: {
  rows: IndexRow[];
  selectedSlug: string | null;
  onSelect: (slug: string) => void;
  // savedViews: the list from GET /api/views. To add views, POST to /api/views
  // with { name, sql, description? }. The four seeded views are a good template.
  savedViews: SavedView[];
  activeView: string | null;
  onViewChange: (name: string | null) => void;
}) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: "updated", desc: true },
  ]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const [stageFilter, setStageFilter] = useState<string[]>([]);
  const [cityFilter, setCityFilter] = useState<string[]>([]);

  const stages = useMemo(() => {
    const buckets = new Set<string>(rows.map((r) => bucketStage(r.stage)));
    // Display in canonical order so the dropdown isn't alphabetical
    const order = ["Folder only", "Discovered", "In progress", "Drafts ready", "Applied", "Sent", "Replied", "Rejected"];
    return order.filter((b) => buckets.has(b));
  }, [rows]);

  const cities = useMemo(() => {
    const buckets = new Set<string>();
    for (const r of rows) for (const t of cityTags(r.location)) buckets.add(t);
    return CITY_ORDER.filter((b) => buckets.has(b));
  }, [rows]);

  const slugCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of rows) m.set(r.slug, (m.get(r.slug) ?? 0) + 1);
    return m;
  }, [rows]);

  const columns = useMemo<ColumnDef<IndexRow>[]>(() => [
    {
      id: "priority",
      accessorKey: "priority",
      header: ({ column }) => (
        <Button
          variant="ghost"
          size="sm"
          className="-ml-2"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
        >
          # <ArrowUpDown className="ml-1 h-3 w-3" />
        </Button>
      ),
      cell: ({ row }) => (
        <PriorityInput slug={row.original.slug} value={row.original.priority} />
      ),
      // Keep blanks at the end regardless of direction — priority 1 is "most
      // important" and an un-ranked row should never bubble above a ranked one.
      sortingFn: (a, b) => {
        const av = a.original.priority;
        const bv = b.original.priority;
        if (av === null && bv === null) return 0;
        if (av === null) return 1;
        if (bv === null) return -1;
        return av - bv;
      },
      sortDescFirst: false,
    },
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
      cell: ({ row, getValue }) => (
        <StageEditor slug={row.original.slug} stage={String(getValue())} />
      ),
      filterFn: (row, id, value: string[]) => {
        if (value.length === 0) return true;
        return value.includes(bucketStage(row.getValue(id) as string));
      },
    },
    {
      id: "lastAction",
      accessorKey: "lastAction",
      header: "Last action",
      cell: ({ getValue }) => (
        <span className="text-muted-foreground">{truncate(String(getValue()), 50)}</span>
      ),
    },
    {
      id: "nextStep",
      accessorKey: "nextStep",
      header: "Next",
      cell: ({ getValue }) => (
        <span className="text-muted-foreground">{truncate(String(getValue()), 50)}</span>
      ),
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
    {
      id: "location",
      accessorKey: "location",
      header: "Location",
      cell: ({ getValue }) => (
        <span className="text-muted-foreground">{truncate(String(getValue() ?? ""), 40)}</span>
      ),
      // Empty selection → show all. Otherwise the row passes when any of
      // its cityTags is in the selected set.
      filterFn: (row, id, value: string[]) => {
        if (value.length === 0) return true;
        const tags = cityTags(String(row.getValue(id) ?? ""));
        return tags.some((t) => value.includes(t));
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
    // Location is useful for filtering but noisy in the main table.
    // Off by default; toggleable via the Columns menu.
    initialState: { columnVisibility: { location: false } },
  });

  // Keep column filter state synced with each dropdown.
  const stageCol = table.getColumn("stage");
  if (stageCol && stageCol.getFilterValue() !== stageFilter) {
    stageCol.setFilterValue(stageFilter);
  }
  const locationCol = table.getColumn("location");
  if (locationCol && locationCol.getFilterValue() !== cityFilter) {
    locationCol.setFilterValue(cityFilter);
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
        {/* Views dropdown — "Default" reverts to the full index query.
            To add new views, POST to /api/views with { name, sql, description? }. */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant={activeView !== null ? "default" : "outline"}
              size="sm"
            >
              <BookOpen className="mr-1 h-3 w-3" />
              {activeView ?? "Views"}
              <ChevronDown className="ml-1 h-3 w-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuLabel>Saved views</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() => onViewChange(null)}
              className={activeView === null ? "font-semibold" : ""}
            >
              Default
            </DropdownMenuItem>
            {savedViews.map((v) => (
              <TooltipProvider key={v.name} delayDuration={300}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <DropdownMenuItem
                      onSelect={() => onViewChange(v.name)}
                      className={activeView === v.name ? "font-semibold" : ""}
                    >
                      {v.name}
                    </DropdownMenuItem>
                  </TooltipTrigger>
                  {v.description && (
                    <TooltipContent side="right">{v.description}</TooltipContent>
                  )}
                </Tooltip>
              </TooltipProvider>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <Button
          variant={sorting[0]?.id === "priority" ? "default" : "outline"}
          size="sm"
          onClick={() =>
            setSorting(
              sorting[0]?.id === "priority"
                ? [{ id: "updated", desc: true }]
                : [{ id: "priority", desc: false }]
            )
          }
          title="Toggle priority sort"
        >
          <ListOrdered className="mr-1 h-3 w-3" /> Priority
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">
              Stage{stageFilter.length > 0 ? ` (${stageFilter.length})` : ""} <ChevronDown className="ml-1 h-3 w-3" />
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
            <Button variant="outline" size="sm">
              City{cityFilter.length > 0 ? ` (${cityFilter.length})` : ""} <ChevronDown className="ml-1 h-3 w-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuLabel>Filter by city</DropdownMenuLabel>
            {cities.map((c) => (
              <DropdownMenuCheckboxItem
                key={c}
                checked={cityFilter.includes(c)}
                onCheckedChange={(checked) => {
                  setCityFilter((prev) =>
                    checked ? [...prev, c] : prev.filter((x) => x !== c)
                  );
                }}
              >
                {c}
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
                const isDup = (slugCounts.get(slug) ?? 0) > 1;
                return (
                  <TableRow
                    key={row.id}
                    data-state={isSelected ? "selected" : undefined}
                    className={`cursor-pointer ${isDup ? "border-l-2 border-l-amber-400" : ""}`}
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
