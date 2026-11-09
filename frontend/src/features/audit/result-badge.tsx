import { Badge } from "@/components/ui/badge";

import type { EntryResult } from "./entries";

const RESULT: Record<
  EntryResult,
  { label: string; title: string; variant: "success" | "info" | "warning" | "destructive" }
> = {
  carried_out: {
    label: "Carried out",
    title: "Passed your guardrails and was sent to PayPal.",
    variant: "success",
  },
  dry_run: {
    label: "Dry run",
    title: "Passed your guardrails, but was simulated. Nothing was sent to PayPal.",
    variant: "info",
  },
  sent_to_you: {
    label: "Sent to you",
    title: "Your guardrails sent it to you to approve or reject.",
    variant: "warning",
  },
  failed: {
    label: "Couldn't carry out",
    title: "Passed your guardrails, but PayPal didn't accept it, so it came to you.",
    variant: "destructive",
  },
};

export function ResultBadge({ result }: { result: EntryResult }) {
  const { label, title, variant } = RESULT[result];
  return (
    <Badge variant={variant} title={title}>
      {label}
    </Badge>
  );
}
