import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { type ReactNode, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { disputeTrailQuery } from "@/features/disputes/api";
import { fromEntry } from "@/features/disputes/case-detail";
import { CaseFileFacts } from "@/features/disputes/case-file-card";
import { DecisionDetail } from "@/features/disputes/mediation-panel";
import type { CaseFile } from "@/features/mediation/events";
import type { AuditEntry, AuditListItem } from "@/lib/api/types";
import { formatDateTime, parseServerTime } from "@/lib/format";

import { approvedBySeller, engineLabel, resultOf } from "./entries";
import { ResultBadge } from "./result-badge";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="space-y-3">
      <h3 className="text-sm font-medium">{title}</h3>
      {children}
    </section>
  );
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1 py-2">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm break-words">{children}</dd>
    </div>
  );
}

/** The full entry: what Settle saw, how it reasoned, what it did, and what PayPal said back. */
function EntryRecord({ entry }: { entry: AuditEntry }) {
  // An entry recorded before the mediator assembled anything has an empty case file.
  const caseFile =
    typeof entry.case_file.dispute_id === "string"
      ? (entry.case_file as unknown as CaseFile)
      : null;

  return (
    <div className="space-y-8">
      <Section title="How Settle decided">
        <DecisionDetail latest={fromEntry(entry)} currency={caseFile?.currency ?? "USD"} />
      </Section>

      {caseFile && (
        <Section title="What Settle saw">
          <CaseFileFacts caseFile={caseFile} />
        </Section>
      )}

      <Section title="Record">
        <dl className="divide-y">
          <Detail label="Decided by">{engineLabel(entry.engine)}</Detail>
          {entry.served_by && (
            <Detail label="Model">
              <span className="font-mono text-xs">{entry.served_by}</span>
            </Detail>
          )}
          <Detail label="Entry">
            <span className="font-mono text-xs">{entry.id}</span>
          </Detail>
          <Detail label="PayPal result">
            <pre className="mt-1 overflow-x-auto rounded-md bg-muted p-3 font-mono text-xs whitespace-pre-wrap">
              {JSON.stringify(entry.paypal_result, null, 2)}
            </pre>
          </Detail>
        </dl>
      </Section>
    </div>
  );
}

function EntryRecordSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading the decision" className="space-y-3">
      {Array.from({ length: 6 }, (_, index) => (
        <Skeleton key={index} className="h-4 w-full" />
      ))}
    </div>
  );
}

/** The full record of one entry. The list row says which; the dispute's trail holds the rest. */
function EntryBody({ row }: { row: AuditListItem }) {
  const trail = useQuery(disputeTrailQuery(row.paypal_dispute_id));
  const entry = trail.data?.find((item) => item.id === row.id);

  if (trail.isPending) return <EntryRecordSkeleton />;
  if (trail.isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Couldn't load this decision</AlertTitle>
        <AlertDescription className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <p>{trail.error.message}</p>
          <Button variant="outline" size="sm" onClick={() => void trail.refetch()}>
            Try again
          </Button>
        </AlertDescription>
      </Alert>
    );
  }
  if (!entry) {
    return <p className="text-sm text-muted-foreground">This decision is no longer on record.</p>;
  }
  return <EntryRecord entry={entry} />;
}

interface EntrySheetProps {
  /** The row to show, or `undefined` to close. */
  entry: AuditListItem | undefined;
  onClose: () => void;
}

export function EntrySheet({ entry, onClose }: EntrySheetProps) {
  // Keeps the last entry on show while the sheet slides closed.
  const [shown, setShown] = useState(entry);
  if (entry && entry !== shown) setShown(entry);

  const at = parseServerTime(shown?.created_at);

  return (
    <Sheet open={entry !== undefined} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-xl">
        {shown && (
          <>
            <SheetHeader className="border-b pr-12">
              <SheetTitle>
                Decision on <span className="font-mono">{shown.paypal_dispute_id}</span>
              </SheetTitle>
              <SheetDescription>
                {at !== null ? formatDateTime(at) : "Date not recorded"}
              </SheetDescription>
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <ResultBadge result={resultOf(shown)} />
                {approvedBySeller(shown) && <Badge variant="outline">Approved by you</Badge>}
                {shown.paypal_dispute_id.startsWith("FIXTURE-") && (
                  <Badge variant="outline" className="text-muted-foreground">
                    Demo
                  </Badge>
                )}
              </div>
            </SheetHeader>
            {/* Focusable, so the record can be scrolled from the keyboard: it holds no controls. */}
            <div
              role="region"
              aria-label="Decision record"
              tabIndex={0}
              className="min-h-0 flex-1 overflow-y-auto p-4 outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:ring-inset"
            >
              <EntryBody key={shown.id} row={shown} />
            </div>
            <SheetFooter className="border-t sm:flex-row sm:justify-end">
              <Button variant="outline" asChild>
                <Link to="/cases/$disputeId" params={{ disputeId: shown.paypal_dispute_id }}>
                  Open case
                  <ArrowRight />
                </Link>
              </Button>
            </SheetFooter>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
