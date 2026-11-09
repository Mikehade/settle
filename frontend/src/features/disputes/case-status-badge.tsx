import type { VariantProps } from "class-variance-authority";

import { Badge, type badgeVariants } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import type { CaseStatus } from "./cases";

const CASE_STATUS: Record<
  CaseStatus,
  { label: string; variant: NonNullable<VariantProps<typeof badgeVariants>["variant"]> }
> = {
  needs_you: { label: "Needs you", variant: "warning" },
  mediating: { label: "Mediating", variant: "info" },
  unfinished: { label: "Didn't finish", variant: "destructive" },
  open: { label: "Open", variant: "outline" },
  resolved: { label: "Resolved", variant: "success" },
  rejected: { label: "Rejected", variant: "muted" },
  closed: { label: "Closed in PayPal", variant: "muted" },
};

interface CaseStatusBadgeProps {
  status: CaseStatus;
  /** Its mediation is streaming to this tab now. */
  live?: boolean;
  className?: string;
}

export function CaseStatusBadge({ status, live = false, className }: CaseStatusBadgeProps) {
  const { label, variant } = CASE_STATUS[status];

  return (
    <Badge variant={variant} className={cn("gap-1.5", className)}>
      {live && <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-current" />}
      {label}
    </Badge>
  );
}
