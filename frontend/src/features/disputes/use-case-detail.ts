import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { useMediationStore } from "@/features/mediation/store";
import { useNow } from "@/hooks/use-now";

import { disputePreviewQuery, disputeQuery, disputeTrailQuery } from "./api";
import { buildCaseDetail } from "./case-detail";

/**
 * One case, kept current: Settle's record and decision trail once it has mediated the case, the
 * assembled case file before then, and the run streaming here while there is one.
 */
export function useCaseDetail(id: string) {
  const record = useQuery(disputeQuery(id));
  const known = record.data != null;
  // Only one of these is needed: the trail once there is a record, the preview until then.
  const trail = useQuery({ ...disputeTrailQuery(id), enabled: known });
  const preview = useQuery({ ...disputePreviewQuery(id), enabled: record.data === null });
  const run = useMediationStore((state) => state.runs[id]);
  const now = useNow();

  const detail = useMemo(
    () =>
      buildCaseDetail({
        id,
        record: record.data,
        recordFetchedAt: record.dataUpdatedAt,
        preview: preview.data,
        trail: trail.data,
        run,
        now,
      }),
    [id, record.data, record.dataUpdatedAt, preview.data, trail.data, run, now],
  );

  const error = record.error ?? (known ? trail.error : preview.error);
  return {
    detail,
    error,
    /** Settle has never mediated the case, and its case file couldn't be assembled either. */
    notFound: record.data === null && preview.isError,
    isPending: !error && (record.isPending || (known ? trail.isPending : preview.isPending)),
    refetch: () => Promise.all([record.refetch(), known ? trail.refetch() : preview.refetch()]),
  };
}
