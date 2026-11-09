import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";

import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { policyQuery } from "@/features/policy/api";
import { PolicyForm } from "@/features/policy/policy-form";
import { pageTitle } from "@/lib/utils";

export const Route = createFileRoute("/_app/policy")({
  loader: ({ context }) => {
    void context.queryClient.prefetchQuery(policyQuery());
  },
  head: () => ({ meta: [{ title: pageTitle("Fairness policy") }] }),
  component: PolicyPage,
});

function PolicyPage() {
  const policy = useQuery(policyQuery());

  return (
    <>
      <PageHeader
        title="Fairness policy"
        description="The rules the mediator applies, and the limits it can never cross on its own."
      />
      {policy.isPending ? (
        <div aria-busy="true" aria-label="Loading your policy" className="space-y-6">
          <Skeleton className="h-64 w-full rounded-xl" />
          <Skeleton className="h-96 w-full rounded-xl" />
        </div>
      ) : policy.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Couldn't load your policy</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <p>{policy.error.message}</p>
            <Button variant="outline" size="sm" onClick={() => void policy.refetch()}>
              Try again
            </Button>
          </AlertDescription>
        </Alert>
      ) : (
        // Keyed by save time, so a policy saved elsewhere refills the form rather than mixing in.
        <PolicyForm key={policy.data?.updated_at ?? "new"} policy={policy.data} />
      )}
    </>
  );
}
