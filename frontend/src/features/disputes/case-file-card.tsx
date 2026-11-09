import type { ReactNode } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { CaseFile } from "@/features/mediation/events";
import { formatMoney } from "@/lib/format";

import { reasonLabel, TRACKING_LABELS } from "./labels";

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2 text-sm">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-right break-words">{children}</dd>
    </div>
  );
}

function Statement({ who, text, empty }: { who: string; text?: string; empty: string }) {
  return (
    <figure className="space-y-1.5">
      <figcaption className="text-xs font-medium text-muted-foreground">{who}</figcaption>
      {text?.trim() ? (
        <blockquote className="border-l-2 pl-3 text-sm leading-relaxed whitespace-pre-line">
          {text}
        </blockquote>
      ) : (
        <p className="text-sm text-muted-foreground">{empty}</p>
      )}
    </figure>
  );
}

/** The facts the mediator reasons over: what was bought, what each side says, and the evidence. */
export function CaseFileFacts({ caseFile }: { caseFile: CaseFile }) {
  const currency = caseFile.currency ?? "USD";
  const money = (value: number | null | undefined) =>
    value == null ? null : formatMoney(value, currency);
  const tracking = caseFile.tracking_status ? TRACKING_LABELS[caseFile.tracking_status] : null;
  const shipment = [caseFile.tracking_carrier, caseFile.tracking_number].filter(Boolean).join(" ");

  return (
    <div className="space-y-6">
      <dl className="divide-y">
        {caseFile.item_name && <Fact label="Item">{caseFile.item_name}</Fact>}
        {money(caseFile.disputed_amount) && (
          <Fact label="Disputed">
            <span className="tabular-nums">{money(caseFile.disputed_amount)}</span>
          </Fact>
        )}
        {caseFile.item_value != null && caseFile.item_value !== caseFile.disputed_amount && (
          <Fact label="Item value">
            <span className="tabular-nums">{money(caseFile.item_value)}</span>
          </Fact>
        )}
        {caseFile.reason_code && <Fact label="Reason">{reasonLabel(caseFile.reason_code)}</Fact>}
        {tracking && (
          <Fact label="Tracking">
            {tracking}
            {shipment && <span className="block text-xs text-muted-foreground">{shipment}</span>}
          </Fact>
        )}
        {caseFile.prior_refunds != null && (
          <Fact label="Already refunded">
            <span className="tabular-nums">{money(caseFile.prior_refunds)}</span>
          </Fact>
        )}
        {caseFile.transaction_id && (
          <Fact label="Transaction">
            <span className="font-mono text-xs">{caseFile.transaction_id}</span>
          </Fact>
        )}
        {(caseFile.buyer_message_count != null || caseFile.seller_message_count != null) && (
          <Fact label="Messages">
            {caseFile.buyer_message_count ?? 0} from the buyer, {caseFile.seller_message_count ?? 0}{" "}
            from you
          </Fact>
        )}
      </dl>
      <Statement who="The buyer says" text={caseFile.buyer_complaint} empty="Nothing in writing." />
      <Statement
        who="You said"
        text={caseFile.seller_response}
        empty="You haven't responded yet."
      />
    </div>
  );
}

export function CaseFileCard({ caseFile }: { caseFile: CaseFile | null }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Case file</CardTitle>
        <CardDescription>
          {caseFile
            ? "What the mediator sees."
            : "Assembled from PayPal when Settle starts on the case."}
        </CardDescription>
      </CardHeader>
      {caseFile && (
        <CardContent>
          <CaseFileFacts caseFile={caseFile} />
        </CardContent>
      )}
    </Card>
  );
}

export function CaseFileCardSkeleton() {
  return (
    <Card aria-hidden>
      <CardHeader>
        <Skeleton className="h-5 w-24" />
      </CardHeader>
      <CardContent className="space-y-3">
        {Array.from({ length: 5 }, (_, index) => (
          <Skeleton key={index} className="h-4 w-full" />
        ))}
      </CardContent>
    </Card>
  );
}
