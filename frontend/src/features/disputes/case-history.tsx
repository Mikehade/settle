import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime, formatRelative } from "@/lib/format";

import type { CaseEvent } from "./case-detail";

const EVENT_LABELS: Record<CaseEvent["kind"], string> = {
  escalated: "Escalated to you",
  executed: "Settle carried out its decision",
  approved: "You approved, and Settle carried it out",
  acknowledged:
    "You approved. There was nothing for Settle to carry out, so it's yours to resolve in PayPal",
  rejected: "You rejected the recommendation",
};

/** What has happened on a case, newest first. */
export function CaseHistory({ events, now }: { events: CaseEvent[]; now: number }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>History</CardTitle>
      </CardHeader>
      <CardContent>
        <ol className="space-y-4">
          {events.map((event, index) => (
            <li key={index} className="flex gap-3">
              <span
                aria-hidden
                className="mt-1.5 size-1.5 shrink-0 rounded-full bg-muted-foreground/50"
              />
              <div className="min-w-0 space-y-0.5">
                <p className="text-sm">{EVENT_LABELS[event.kind]}</p>
                {/* An escalation's action only repeats its label. */}
                {event.actionTaken && event.kind !== "escalated" && (
                  <p className="text-sm text-muted-foreground">{event.actionTaken}</p>
                )}
                {event.at !== null && (
                  <time
                    dateTime={new Date(event.at).toISOString()}
                    title={formatDateTime(event.at)}
                    className="text-xs text-muted-foreground"
                  >
                    {formatRelative(event.at, now)}
                  </time>
                )}
              </div>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
