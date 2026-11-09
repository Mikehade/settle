import { createFileRoute } from "@tanstack/react-router";
import { Inbox, RefreshCw, Search } from "lucide-react";
import { type ReactNode, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { disputeRecordsQuery, openDisputesQuery } from "@/features/disputes/api";
import {
  CASE_FILTERS,
  type CaseFilter,
  countByFilter,
  matchesFilter,
  matchesQuery,
} from "@/features/disputes/cases";
import { CasesTable, CasesTableSkeleton } from "@/features/disputes/cases-table";
import { useCases } from "@/features/disputes/use-cases";
import { useNow } from "@/hooks/use-now";
import { cn, pageTitle } from "@/lib/utils";

interface CasesSearch {
  filter?: Exclude<CaseFilter, "all">;
  q?: string;
}

// A plain parser, like the sign-in route's: two optional fields don't need a schema library.
function parseSearch(search: Record<string, unknown>): CasesSearch {
  const filter = CASE_FILTERS.find((value) => value !== "all" && value === search.filter);
  const q = typeof search.q === "string" && search.q.trim() ? search.q : undefined;
  return { filter: filter === "all" ? undefined : filter, q };
}

export const Route = createFileRoute("/_app/cases/")({
  validateSearch: parseSearch,
  // Start both requests as the route loads, without holding the page back for them.
  loader: ({ context }) => {
    void context.queryClient.prefetchQuery(openDisputesQuery());
    void context.queryClient.prefetchQuery(disputeRecordsQuery());
  },
  head: () => ({ meta: [{ title: pageTitle("Cases") }] }),
  component: CasesPage,
});

const FILTER_LABELS: Record<CaseFilter, string> = {
  all: "All",
  needs_you: "Needs you",
  open: "Open",
  closed: "Closed",
};

const EMPTY_FILTER: Record<CaseFilter, string> = {
  all: "No cases.",
  needs_you: "Nothing needs you right now.",
  open: "No open cases.",
  closed: "No closed cases yet.",
};

function CasesPage() {
  const { filter = "all", q = "" } = Route.useSearch();
  const navigate = Route.useNavigate();
  const now = useNow();
  const { cases, open, records, truncated, isPending, isFetching, refetch } = useCases();

  const setSearch = (next: CasesSearch) =>
    navigate({ search: (previous) => ({ ...previous, ...next }), replace: true });

  const counts = countByFilter(cases);
  const visible = cases.filter((item) => matchesFilter(item, filter) && matchesQuery(item, q));
  const failed = [open, records].filter((query) => query.isError);

  return (
    <>
      <PageHeader
        title="Cases"
        description="Disputes from PayPal and where each one stands. Anything waiting on you comes first."
        actions={
          <Button variant="outline" size="sm" disabled={isFetching} onClick={() => void refetch()}>
            <RefreshCw className={cn(isFetching && "animate-spin")} />
            Refresh
          </Button>
        }
      />

      {isPending ? (
        <CasesTableSkeleton />
      ) : (
        <div className="space-y-4">
          {open.isError && (
            <LoadAlert
              title="Couldn't load open disputes from PayPal"
              error={open.error}
              onRetry={() => void open.refetch()}
            >
              {records.isError ? null : "Showing the cases Settle has already handled."}
            </LoadAlert>
          )}
          {records.isError && (
            <LoadAlert
              title="Couldn't load the cases Settle has handled"
              error={records.error}
              onRetry={() => void records.refetch()}
            >
              {open.isError ? null : "Showing open disputes only, without their history."}
            </LoadAlert>
          )}

          {cases.length === 0 && failed.length === 0 && <NoCases />}

          {cases.length > 0 && (
            <Tabs
              value={filter}
              onValueChange={(value) =>
                void setSearch({
                  filter: value === "all" ? undefined : (value as CasesSearch["filter"]),
                })
              }
              className="gap-4"
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="overflow-x-auto">
                  <TabsList className="w-full sm:w-fit">
                    {CASE_FILTERS.map((value) => (
                      <TabsTrigger
                        key={value}
                        value={value}
                        className="gap-1 px-1.5 text-[13px] sm:gap-1.5 sm:px-2.5 sm:text-sm"
                      >
                        {FILTER_LABELS[value]}{" "}
                        <span
                          className={cn(
                            "rounded px-1 text-xs tabular-nums",
                            value === "needs_you" && counts.needs_you > 0
                              ? "bg-warning/15 text-warning-strong"
                              : "text-muted-foreground",
                          )}
                        >
                          {counts[value]}
                        </span>
                      </TabsTrigger>
                    ))}
                  </TabsList>
                </div>
                <SearchField
                  value={q}
                  onChange={(value) => void setSearch({ q: value.trim() ? value : undefined })}
                />
              </div>

              {CASE_FILTERS.map((value) => (
                <TabsContent key={value} value={value}>
                  <CasesTable
                    cases={visible}
                    now={now}
                    caption={
                      truncated && records.data
                        ? `Showing the latest ${records.data.items.length.toLocaleString("en-US")} of ${records.data.total.toLocaleString("en-US")} cases Settle has handled.`
                        : undefined
                    }
                    empty={
                      q ? (
                        <div className="space-y-2">
                          <p className="text-muted-foreground">No cases match “{q}”.</p>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void setSearch({ q: undefined })}
                          >
                            Clear search
                          </Button>
                        </div>
                      ) : (
                        <p className="text-muted-foreground">{EMPTY_FILTER[value]}</p>
                      )
                    }
                  />
                </TabsContent>
              ))}
            </Tabs>
          )}
        </div>
      )}
    </>
  );
}

/**
 * The search box, typed into freely while the address bar follows along. It adopts the address
 * bar's query only when that changes from elsewhere, such as "Clear search".
 */
function SearchField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [text, setText] = useState(value);
  const [adopted, setAdopted] = useState(value);
  if (value !== adopted) {
    setAdopted(value);
    if (value.trim() !== text.trim()) setText(value);
  }

  return (
    <div className="relative sm:w-72">
      <Search
        aria-hidden
        className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
      />
      <Input
        type="search"
        aria-label="Search cases"
        placeholder="Search by id, type or complaint"
        className="pl-8"
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          onChange(event.target.value);
        }}
      />
    </div>
  );
}

interface LoadAlertProps {
  title: string;
  error: Error;
  onRetry: () => void;
  children?: ReactNode;
}

function LoadAlert({ title, error, onRetry, children }: LoadAlertProps) {
  return (
    <Alert variant="destructive">
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <p>
          {error.message} {children}
        </p>
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      </AlertDescription>
    </Alert>
  );
}

function NoCases() {
  return (
    <Empty className="border border-dashed">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Inbox />
        </EmptyMedia>
        <EmptyTitle>No disputes yet</EmptyTitle>
        <EmptyDescription>
          When a buyer opens a dispute in PayPal, it appears here and Settle starts working on it.
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}
