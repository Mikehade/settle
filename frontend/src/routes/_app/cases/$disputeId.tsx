import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, FileQuestion } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { disputeQuery } from "@/features/disputes/api";
import { MediateButton, ReviewActions } from "@/features/disputes/case-actions";
import type { CaseDetail } from "@/features/disputes/case-detail";
import { CaseFileCard, CaseFileCardSkeleton } from "@/features/disputes/case-file-card";
import { CaseHistory } from "@/features/disputes/case-history";
import { CaseStatusBadge } from "@/features/disputes/case-status-badge";
import { DISPUTE_TYPE_LABELS } from "@/features/disputes/labels";
import { MediationPanel } from "@/features/disputes/mediation-panel";
import { useCaseDetail } from "@/features/disputes/use-case-detail";
import { useNow } from "@/hooks/use-now";
import { formatMoney, formatRelative } from "@/lib/format";
import { pageTitle } from "@/lib/utils";

export const Route = createFileRoute("/_app/cases/$disputeId")({
  loader: ({ context, params }) => {
    void context.queryClient.prefetchQuery(disputeQuery(params.disputeId));
  },
  head: ({ params }) => ({ meta: [{ title: pageTitle(params.disputeId) }] }),
  component: CasePage,
});

function CasePage() {
  const { disputeId } = Route.useParams();
  const now = useNow();
  const { detail, isPending, error, notFound, refetch } = useCaseDetail(disputeId);

  let body;
  if (isPending) body = <CaseSkeleton id={disputeId} />;
  else if (notFound || (!error && !detail)) body = <NotFound id={disputeId} />;
  else if (!detail) {
    body = (
      <Alert variant="destructive">
        <AlertTitle>Couldn't load this case</AlertTitle>
        <AlertDescription className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <p>{error?.message}</p>
          <Button variant="outline" size="sm" onClick={() => void refetch()}>
            Try again
          </Button>
        </AlertDescription>
      </Alert>
    );
  } else body = <CaseView detail={detail} now={now} partialError={error} />;

  return (
    <>
      <Link
        to="/cases"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Cases
      </Link>
      {body}
    </>
  );
}

function CaseView({
  detail,
  now,
  partialError,
}: {
  detail: CaseDetail;
  now: number;
  partialError: Error | null;
}) {
  const { caseFile } = detail;
  const amount =
    caseFile?.disputed_amount != null
      ? formatMoney(caseFile.disputed_amount, caseFile.currency ?? "USD")
      : null;
  const facts = [DISPUTE_TYPE_LABELS[detail.type], caseFile?.item_name, amount].filter(Boolean);

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-4 pb-8">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-xl font-semibold tracking-tight break-all">
              {detail.id}
            </h1>
            <CaseStatusBadge status={detail.status} live={detail.live} />
            {detail.demo && (
              <Badge variant="outline" className="text-muted-foreground">
                Demo
              </Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            {facts.join(" · ")}
            {detail.updatedAt !== null && (
              <span>
                {facts.length > 0 && " · "}Updated {formatRelative(detail.updatedAt, now)}
              </span>
            )}
          </p>
        </div>
        {detail.canMediate && (
          <MediateButton id={detail.id} again={detail.status === "unfinished"} />
        )}
      </header>

      {partialError && (
        <Alert variant="destructive" className="mb-6">
          <AlertTitle>Part of this case didn't load</AlertTitle>
          <AlertDescription>{partialError.message}</AlertDescription>
        </Alert>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-6">
          <MediationPanel
            detail={detail}
            now={now}
            footer={detail.awaitingReview ? <ReviewActions detail={detail} /> : undefined}
          />
          {detail.history.length > 0 && <CaseHistory events={detail.history} now={now} />}
        </div>
        <CaseFileCard caseFile={caseFile} />
      </div>
    </>
  );
}

function CaseSkeleton({ id }: { id: string }) {
  return (
    <div aria-busy="true" aria-label="Loading case">
      <div className="space-y-2 pb-8">
        <h1 className="font-mono text-xl font-semibold tracking-tight break-all">{id}</h1>
        <Skeleton className="h-4 w-56" />
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <Skeleton className="h-72 w-full rounded-xl" />
        <CaseFileCardSkeleton />
      </div>
    </div>
  );
}

function NotFound({ id }: { id: string }) {
  return (
    <Empty className="border border-dashed">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <FileQuestion />
        </EmptyMedia>
        <EmptyTitle>No case {id}</EmptyTitle>
        <EmptyDescription>
          Settle can't find this dispute among yours, in PayPal or in the demo cases.
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button variant="outline" asChild>
          <Link to="/cases">Back to cases</Link>
        </Button>
      </EmptyContent>
    </Empty>
  );
}
