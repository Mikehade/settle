import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime, formatMoney, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

import { CaseStatusBadge } from "./case-status-badge";
import type { Case } from "./cases";
import { DISPUTE_TYPE_LABELS, OUTCOME_LABELS } from "./labels";

const COLUMNS = {
  amount: "hidden text-right sm:table-cell",
  decision: "hidden md:table-cell",
  updated: "hidden text-right lg:table-cell",
};

function Unknown({ children }: { children: string }) {
  return <span className="sr-only">{children}</span>;
}

function Decision({ item }: { item: Case }) {
  if (item.status !== "resolved") return <Unknown>None yet</Unknown>;
  if (!item.outcome) return <span className="text-muted-foreground">Manual</span>;
  const label = OUTCOME_LABELS[item.outcome];
  if (item.outcome === "refund" && item.refundAmount !== null && item.amount) {
    return (
      <span>
        {label}{" "}
        <span className="tabular-nums">{formatMoney(item.refundAmount, item.amount.currency)}</span>
      </span>
    );
  }
  return <span>{label}</span>;
}

function CaseRow({ item, now }: { item: Case; now: number }) {
  return (
    <TableRow className="relative">
      <TableCell className="w-full max-w-0">
        <div className="flex items-center gap-2">
          <Link
            to="/cases/$disputeId"
            params={{ disputeId: item.id }}
            className="shrink-0 font-mono text-[13px] font-medium outline-none after:absolute after:inset-0 focus-visible:after:ring-[3px] focus-visible:after:ring-ring/50 focus-visible:after:ring-inset"
          >
            {item.id}
          </Link>
          {item.demo && (
            <Badge variant="outline" className="px-1.5 py-0 text-[11px] text-muted-foreground">
              Demo
            </Badge>
          )}
        </div>
        <p className="mt-0.5 flex min-w-0 gap-1.5 text-xs text-muted-foreground">
          <span className="shrink-0">{DISPUTE_TYPE_LABELS[item.type]}</span>
          {item.complaint && (
            <span className="hidden truncate xl:inline">
              <span aria-hidden>· </span>
              {item.complaint}
            </span>
          )}
        </p>
      </TableCell>
      <TableCell>
        <CaseStatusBadge status={item.status} live={item.live} />
      </TableCell>
      <TableCell className={cn(COLUMNS.amount, "tabular-nums")}>
        {item.amount ? (
          formatMoney(item.amount.value, item.amount.currency)
        ) : (
          <Unknown>Not known yet</Unknown>
        )}
      </TableCell>
      <TableCell className={COLUMNS.decision}>
        <Decision item={item} />
      </TableCell>
      <TableCell className={cn(COLUMNS.updated, "text-muted-foreground")}>
        {item.updatedAt !== null ? (
          <time
            dateTime={new Date(item.updatedAt).toISOString()}
            title={formatDateTime(item.updatedAt)}
          >
            {formatRelative(item.updatedAt, now)}
          </time>
        ) : (
          <Unknown>Not yet</Unknown>
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
        <TableHead>Status</TableHead>
        <TableHead className={COLUMNS.amount}>Amount</TableHead>
        <TableHead className={COLUMNS.decision}>Decision</TableHead>
        <TableHead className={COLUMNS.updated}>Updated</TableHead>
      </TableRow>
    </TableHeader>
  );
}

interface CasesTableProps {
  cases: Case[];
  now: number;
  /** Shown in place of the rows when there are none. */
  empty: ReactNode;
  caption?: ReactNode;
}

export function CasesTable({ cases, now, empty, caption }: CasesTableProps) {
  return (
    <div className="rounded-lg border">
      <Table>
        {caption && <TableCaption className="mb-4">{caption}</TableCaption>}
        <Head />
        <TableBody>
          {cases.length > 0 ? (
            cases.map((item) => <CaseRow key={item.id} item={item} now={now} />)
          ) : (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={5} className="h-40 text-center whitespace-normal">
                {empty}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}

export function CasesTableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="rounded-lg border" aria-busy="true" aria-label="Loading cases">
      <Table>
        <Head />
        <TableBody>
          {Array.from({ length: rows }, (_, index) => (
            <TableRow key={index} className="hover:bg-transparent">
              <TableCell className="w-full max-w-0">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="mt-1.5 h-3 w-20" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-5 w-20" />
              </TableCell>
              <TableCell className={COLUMNS.amount}>
                <Skeleton className="ml-auto h-4 w-14" />
              </TableCell>
              <TableCell className={COLUMNS.decision}>
                <Skeleton className="h-4 w-24" />
              </TableCell>
              <TableCell className={COLUMNS.updated}>
                <Skeleton className="ml-auto h-4 w-16" />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
