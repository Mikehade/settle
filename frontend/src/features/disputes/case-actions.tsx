import { useIsMutating, useMutation, useQueryClient } from "@tanstack/react-query";
import { Play, TriangleAlert } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { mediation } from "@/features/mediation/client";
import { useMediationStore } from "@/features/mediation/store";
import { isApiError } from "@/lib/api/errors";
import { formatMoney } from "@/lib/format";

import { disputeKeys, type ReviewAction, reviewDispute } from "./api";
import type { CaseDetail } from "./case-detail";
import { OUTCOME_LABELS } from "./labels";

const reviewKey = (id: string) => [...disputeKeys.all, "review", id] as const;

/** What approving will do, in words the seller can check before money moves. */
function describeApproval(detail: CaseDetail) {
  const decision = detail.latest?.decision;
  const currency = detail.caseFile?.currency ?? "USD";
  const simulated = detail.demo ? " This is a demo dispute, so it is simulated." : "";

  switch (decision?.outcome) {
    case "refund": {
      const amount = decision.refund_amount;
      const money = amount != null ? formatMoney(amount, currency) : null;
      return {
        effect: `Settle will refund ${money ?? "the buyer"}${money ? " to the buyer" : ""} through PayPal.${simulated}`,
        confirm: money ? `Approve and refund ${money}` : "Approve and refund",
      };
    }
    case "reship":
    case "accept":
      return {
        effect: `Settle will carry out "${OUTCOME_LABELS[decision.outcome]}" through PayPal.${simulated}`,
        confirm: "Approve",
      };
    default:
      return {
        effect:
          "The mediator didn't settle on an action, so nothing is sent to PayPal. Approving marks the case resolved, and you resolve it in PayPal yourself.",
        confirm: "Approve",
      };
  }
}

function reviewError(error: unknown, action: ReviewAction) {
  if (isApiError(error) && error.code === "NETWORK_ERROR") {
    return {
      title: "Settle didn't answer",
      // The request may have reached the server: say so rather than invite a second refund.
      message: `There's no way to tell whether your ${action === "approve" ? "approval" : "rejection"} went through. This page refreshes on its own; check the case's status before trying again.`,
    };
  }
  if (isApiError(error) && error.status === 409) {
    return { title: "This case was already acted on", message: error.message };
  }
  return {
    title: action === "approve" ? "Couldn't approve" : "Couldn't reject",
    message: error instanceof Error ? error.message : "Something went wrong.",
  };
}

/** Approve or reject an escalated recommendation, each confirmed first. */
export function ReviewActions({ detail }: { detail: CaseDetail }) {
  const queryClient = useQueryClient();
  // Covers both buttons, and any other view of this case mid-request.
  const reviewing = useIsMutating({ mutationKey: reviewKey(detail.id) }) > 0;
  const review = useMutation({
    mutationKey: reviewKey(detail.id),
    mutationFn: (action: ReviewAction) => reviewDispute(detail.id, action),
    meta: { silentError: true },
    onSuccess: (result, action) => {
      toast.success(action === "approve" ? "Recommendation approved" : "Recommendation rejected", {
        description: result.action_taken || undefined,
      });
    },
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: disputeKeys.all }),
        queryClient.invalidateQueries({ queryKey: ["audit"] }),
      ]),
  });

  // Done: the case is about to refetch as resolved or rejected. Nothing more to press.
  if (review.isSuccess) return null;

  const approval = describeApproval(detail);
  const failure = review.isError ? reviewError(review.error, review.variables) : null;
  const busy = reviewing || review.isPending;

  return (
    <div className="w-full space-y-3">
      <div className="flex flex-wrap gap-2">
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button disabled={busy}>
              {review.isPending && review.variables === "approve" ? "Approving" : "Approve"}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Approve this recommendation?</AlertDialogTitle>
              <AlertDialogDescription>{approval.effect}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => review.mutate("approve")}>
                {approval.confirm}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="outline" disabled={busy}>
              {review.isPending && review.variables === "reject" ? "Rejecting" : "Reject"}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Reject this recommendation?</AlertDialogTitle>
              <AlertDialogDescription>
                Settle won't take any action. The case is marked rejected and left for you to handle
                in PayPal.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => review.mutate("reject")}>Reject</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      {failure && (
        <Alert variant="destructive">
          <TriangleAlert />
          <AlertTitle>{failure.title}</AlertTitle>
          <AlertDescription>{failure.message}</AlertDescription>
        </Alert>
      )}
    </div>
  );
}

/** Starts a mediation streamed to this tab. Needs the live connection, which carries the run. */
export function MediateButton({ id, again = false }: { id: string; again?: boolean }) {
  const online = useMediationStore((state) => state.connection.state === "open");

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        disabled={!online}
        onClick={() => {
          const result = mediation.mediate(id);
          if (!result.ok && result.reason === "offline") {
            toast.error("Not connected to Settle", {
              description: "The mediation runs over the live connection. Try again once it's back.",
            });
          }
        }}
      >
        <Play />
        {again ? "Mediate again" : "Mediate"}
      </Button>
      {!online && <p className="text-xs text-muted-foreground">Waiting for the live connection.</p>}
    </div>
  );
}
