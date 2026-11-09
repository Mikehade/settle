import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { mediation } from "./client";
import type { ConnectionStatus as Status } from "./socket";
import { useMediationStore } from "./store";

/** After this many failed attempts in a row, say plainly that the server can't be reached. */
const UNREACHABLE_AFTER = 3;

function describe({ state, attempt }: Status) {
  switch (state) {
    case "open":
      return { label: "Live", dot: "bg-success" };
    case "connecting":
      return { label: "Connecting", dot: "animate-pulse bg-muted-foreground/40" };
    case "reconnecting":
      return attempt >= UNREACHABLE_AFTER
        ? { label: "Can't reach Settle", dot: "bg-destructive" }
        : { label: "Reconnecting", dot: "animate-pulse bg-warning" };
    case "idle":
      return { label: "Offline", dot: "bg-muted-foreground/40" };
  }
}

/** The state of the live mediation connection, with a way to retry at once when it is down. */
export function ConnectionStatus({ className }: { className?: string }) {
  const connection = useMediationStore((state) => state.connection);
  const { label, dot } = describe(connection);

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <p role="status" className="inline-flex items-center gap-2 text-xs text-muted-foreground">
        <span aria-hidden className={cn("size-1.5 rounded-full", dot)} />
        {label}
      </p>
      {connection.state === "reconnecting" && (
        <Button
          variant="outline"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => mediation.retryNow()}
        >
          Retry now
        </Button>
      )}
    </div>
  );
}
