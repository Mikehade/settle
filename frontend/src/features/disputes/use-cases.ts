import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { useMediationStore } from "@/features/mediation/store";
import { useNow } from "@/hooks/use-now";

import { disputeRecordsQuery, openDisputesQuery } from "./api";
import { buildCases } from "./cases";

/**
 * Every case the seller has, kept current: the two lists refetch whenever a mediation settles, and
 * a mediation under way shows from its first event.
 */
export function useCases() {
  const open = useQuery(openDisputesQuery());
  const records = useQuery(disputeRecordsQuery());
  const runs = useMediationStore((state) => state.runs);
  const now = useNow();

  const cases = useMemo(
    () =>
      buildCases({
        open: open.data,
        records: records.data?.items,
        recordsFetchedAt: records.dataUpdatedAt,
        runs,
        now,
      }),
    [open.data, records.data, records.dataUpdatedAt, runs, now],
  );

  return {
    cases,
    open,
    records,
    /** Some of the history wasn't loaded because there is so much of it. */
    truncated: records.data ? records.data.items.length < records.data.total : false,
    isPending: open.isPending || records.isPending,
    isFetching: open.isFetching || records.isFetching,
    refetch: () => Promise.all([open.refetch(), records.refetch()]),
  };
}
