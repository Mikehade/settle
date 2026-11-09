import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { asOutcome, OUTCOME_LABELS } from "@/features/disputes/labels";
import type { AuditListItem } from "@/lib/api/types";
import { formatDateTime, formatRelative, parseServerTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { resultOf, whatHappened } from "./entries";
import { ResultBadge } from "./result-badge";

const COLUMNS = {
  decision: "hidden sm:table-cell",
  when: "hidden text-right md:table-cell",
};

function Decision({ entry }: { entry: AuditListItem }) {
  const outcome = asOutcome(entry.outcome);
  return (
    <span className="flex items-baseline gap-2">
      {outcome ? (
        <span>{OUTCOME_LABELS[outcome]}</span>
      ) : (
        <span className="text-muted-foreground">No clear outcome</span>
      )}
      <span className="text-xs text-muted-foreground tabular-nums">
        {Math.round(entry.confidence * 100)}%<span className="sr-only"> confident</span>
      </span>
    </span>
  );
}

function EntryRow({ entry, now }: { entry: AuditListItem; now: number }) {
  const at = parseServerTime(entry.created_at);
  const demo = entry.paypal_dispute_id.startsWith("FIXTURE-");

  return (
    <TableRow className="relative">
      <TableCell className="w-full max-w-0">
        <div className="flex items-center gap-2">
          {/* Opens the entry beside the list, keeping the page and filters in the address bar. */}
          <Link
            to="/audit"
            search={(previous) => ({ ...previous, entry: entry.id })}
            replace
            className="shrink-0 font-mono text-[13px] font-medium outline-none after:absolute after:inset-0 focus-visible:after:ring-[3px] focus-visible:after:ring-ring/50 focus-visible:after:ring-inset"
          >
            {entry.paypal_dispute_id}
            <span className="sr-only">
              {at !== null ? `, decision of ${formatDateTime(at)}` : ", decision"}
            </span>
          </Link>
          {demo && (
            <Badge variant="outline" className="px-1.5 py-0 text-[11px] text-muted-foreground">
              Demo
            </Badge>
          )}
        </div>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">{whatHappened(entry)}</p>
      </TableCell>
      <TableCell>
        <ResultBadge result={resultOf(entry)} />
      </TableCell>
      <TableCell className={COLUMNS.decision}>
        <Decision entry={entry} />
      </TableCell>
      <TableCell className={cn(COLUMNS.when, "text-muted-foreground")}>
        {at !== null && (
          <time dateTime={new Date(at).toISOString()} title={formatDateTime(at)}>
            {formatRelative(at, now)}
          </time>
        )}
      </TableCell>
    </TableRow>
  );
}

function Head() {
  return (
    <TableHeader>
      <TableRow className="hover:bg-transparent">
        <TableHead>Case</TableHead>
        <TableHead>Result</TableHead>
        <TableHead className={COLUMNS.decision}>Decision</TableHead>
        <TableHead className={COLUMNS.when}>When</TableHead>
      </TableRow>
    </TableHeader>
  );
}

interface AuditTableProps {
  entries: AuditListItem[];
  now: number;
  /** Shown in place of the rows when there are none. */
  empty: ReactNode;
  /** The next page or filter is loading, while this one stays on show. */
  stale?: boolean;
}

export function AuditTable({ entries, now, empty, stale = false }: AuditTableProps) {
  return (
    <div
      className={cn("rounded-lg border transition-opacity", stale && "opacity-60")}
      aria-busy={stale || undefined}
    >
      <Table>
        <Head />
        <TableBody>
          {entries.length > 0 ? (
            entries.map((entry) => <EntryRow key={entry.id} entry={entry} now={now} />)
          ) : (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={4} className="h-40 text-center whitespace-normal">
                {empty}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}

export function AuditTableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="rounded-lg border" aria-busy="true" aria-label="Loading the audit trail">
      <Table>
        <Head />
        <TableBody>
          {Array.from({ length: rows }, (_, index) => (
            <TableRow key={index} className="hover:bg-transparent">
              <TableCell className="w-full max-w-0">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="mt-1.5 h-3 w-48" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-5 w-20" />
              </TableCell>
              <TableCell className={COLUMNS.decision}>
                <Skeleton className="h-4 w-20" />
              </TableCell>
              <TableCell className={COLUMNS.when}>
                <Skeleton className="ml-auto h-4 w-16" />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
