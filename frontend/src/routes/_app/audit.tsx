import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { ChevronDown, RefreshCw, ScrollText } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { auditPageQuery } from "@/features/audit/api";
import { AuditTable, AuditTableSkeleton } from "@/features/audit/audit-table";
import { EntrySheet } from "@/features/audit/entry-sheet";
import { asOutcome, OUTCOME_LABELS } from "@/features/disputes/labels";
import type { Gate, Outcome } from "@/features/mediation/events";
import { useNow } from "@/hooks/use-now";
import type { PageMeta } from "@/lib/api/envelope";
import { cn, pageTitle } from "@/lib/utils";

interface AuditSearch {
  gate?: Gate;
  outcome?: Outcome;
  /** From 2; the first page leaves it out. */
  page?: number;
  /** The entry open beside the list. */
  entry?: string;
}

// A plain parser, like the cases list's: a few optional fields don't need a schema library.
function parseSearch(search: Record<string, unknown>): AuditSearch {
  const gate = search.gate === "execute" || search.gate === "escalate" ? search.gate : undefined;
  const outcome = typeof search.outcome === "string" ? asOutcome(search.outcome) : null;
  const page = Number(search.page);
  const entry = typeof search.entry === "string" && search.entry ? search.entry : undefined;
  return {
    gate,
    outcome: outcome ?? undefined,
    page: Number.isInteger(page) && page > 1 ? page : undefined,
    entry,
  };
}

export const Route = createFileRoute("/_app/audit")({
  validateSearch: parseSearch,
  // Opening an entry changes the address too, but shouldn't load the list again.
  loaderDeps: ({ search: { gate, outcome, page } }) => ({ gate, outcome, page }),
  loader: ({ context, deps }) => {
    void context.queryClient.prefetchQuery(auditPageQuery(deps));
  },
  head: () => ({ meta: [{ title: pageTitle("Audit trail") }] }),
  component: AuditPage,
});

type GateFilter = Gate | "all";

const GATE_FILTERS: { value: GateFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "execute", label: "Carried out" },
  { value: "escalate", label: "Sent to you" },
];

const OUTCOMES = Object.keys(OUTCOME_LABELS) as Outcome[];

function AuditPage() {
  const { gate, outcome, page = 1, entry } = Route.useSearch();
  const navigate = Route.useNavigate();
  const now = useNow();
  const list = useQuery(auditPageQuery({ gate, outcome, page }));

  const setSearch = (next: AuditSearch) =>
    navigate({ search: (previous) => ({ ...previous, ...next }), replace: true });
  // A new filter starts again from the first page.
  const setFilter = (next: Pick<AuditSearch, "gate" | "outcome">) =>
    void setSearch({ ...next, page: undefined });

  const entries = list.data?.items ?? [];
  const filtered = gate !== undefined || outcome !== undefined;
  const open = entry ? entries.find((item) => item.id === entry) : undefined;

  return (
    <>
      <PageHeader
        title="Audit trail"
        description="Every decision Settle made on your disputes, and every approval it carried out, newest first."
        actions={
          <Button
            variant="outline"
            size="sm"
            disabled={list.isFetching}
            onClick={() => void list.refetch()}
          >
            <RefreshCw className={cn(list.isFetching && "animate-spin")} />
            Refresh
          </Button>
        }
      />

      {list.isPending ? (
        <AuditTableSkeleton />
      ) : list.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Couldn't load the audit trail</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <p>{list.error.message}</p>
            <Button variant="outline" size="sm" onClick={() => void list.refetch()}>
              Try again
            </Button>
          </AlertDescription>
        </Alert>
      ) : entries.length === 0 && !filtered && page === 1 ? (
        <NoDecisions />
      ) : (
        <Tabs
          value={gate ?? "all"}
          onValueChange={(value) =>
            setFilter({ gate: value === "all" ? undefined : (value as Gate) })
          }
          className="gap-4"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <TabsList className="w-full sm:w-fit">
              {GATE_FILTERS.map(({ value, label }) => (
                <TabsTrigger key={value} value={value} className="px-2.5">
                  {label}
                </TabsTrigger>
              ))}
            </TabsList>
            <OutcomeFilter value={outcome} onChange={(value) => setFilter({ outcome: value })} />
          </div>

          {GATE_FILTERS.map(({ value }) => (
            <TabsContent key={value} value={value} className="space-y-4">
              <AuditTable
                entries={entries}
                now={now}
                stale={list.isPlaceholderData}
                empty={
                  page > 1 ? (
                    <div className="space-y-2">
                      <p className="text-muted-foreground">There's nothing on page {page}.</p>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void setSearch({ page: undefined })}
                      >
                        Go to the first page
                      </Button>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <p className="text-muted-foreground">No decisions match these filters.</p>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setFilter({ gate: undefined, outcome: undefined })}
                      >
                        Clear filters
                      </Button>
                    </div>
                  )
                }
              />
              <Pager
                meta={list.data.meta}
                shown={entries.length}
                onPage={(next) => void setSearch({ page: next > 1 ? next : undefined })}
              />
            </TabsContent>
          ))}
        </Tabs>
      )}

      <EntrySheet entry={open} onClose={() => void setSearch({ entry: undefined })} />
    </>
  );
}

function OutcomeFilter({
  value,
  onChange,
}: {
  value: Outcome | undefined;
  onChange: (value: Outcome | undefined) => void;
}) {
  const label = value ? OUTCOME_LABELS[value] : "Any decision";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          aria-label={`Decision: ${label}`}
          className="self-start sm:self-auto"
        >
          {label}
          <ChevronDown className="text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuLabel>Decision</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuRadioGroup
          value={value ?? "any"}
          onValueChange={(next) => onChange(asOutcome(next) ?? undefined)}
        >
          <DropdownMenuRadioItem value="any">Any decision</DropdownMenuRadioItem>
          {OUTCOMES.map((item) => (
            <DropdownMenuRadioItem key={item} value={item}>
              {OUTCOME_LABELS[item]}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Pager({
  meta,
  shown,
  onPage,
}: {
  meta: PageMeta;
  shown: number;
  onPage: (page: number) => void;
}) {
  if (meta.total === 0) return null;
  const first = (meta.page - 1) * meta.pageSize + 1;
  const count = (value: number) => value.toLocaleString("en-US");
  const noun = meta.total === 1 ? "decision" : "decisions";

  return (
    <nav aria-label="Pages" className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-muted-foreground">
        {meta.totalPages > 1 && shown > 0
          ? `${count(first)} to ${count(first + shown - 1)} of ${count(meta.total)} ${noun}`
          : `${count(meta.total)} ${noun}`}
      </p>
      {meta.totalPages > 1 && (
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={meta.page <= 1}
            onClick={() => onPage(Math.min(meta.page - 1, meta.totalPages))}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={meta.page >= meta.totalPages}
            onClick={() => onPage(meta.page + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </nav>
  );
}

function NoDecisions() {
  return (
    <Empty className="border border-dashed">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <ScrollText />
        </EmptyMedia>
        <EmptyTitle>No decisions yet</EmptyTitle>
        <EmptyDescription>
          When Settle mediates a case, its decision is recorded here: what it saw, how it reasoned,
          and what it did through PayPal.
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}
