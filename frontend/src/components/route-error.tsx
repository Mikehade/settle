import { useRouter, type ErrorComponentProps } from "@tanstack/react-router";
import { OctagonAlert, WifiOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { isApiError } from "@/lib/api/errors";

/** Shown when a route fails to load: what went wrong, a reference to report, and a retry. */
export function RouteError({ error, reset }: ErrorComponentProps) {
  const router = useRouter();
  const apiError = isApiError(error) ? error : null;
  const offline = apiError?.code === "NETWORK_ERROR";
  const Icon = offline ? WifiOff : OctagonAlert;
  const message = error instanceof Error ? error.message : "An unexpected error occurred.";

  return (
    <div role="alert" className="mx-auto flex max-w-md flex-col items-start gap-4 px-6 py-24">
      <span className="flex size-10 items-center justify-center rounded-lg bg-muted">
        <Icon className="size-5 text-muted-foreground" />
      </span>
      <div className="space-y-1.5">
        <h1 className="text-lg font-semibold tracking-tight">
          {offline ? "Can't reach Settle" : "Something went wrong"}
        </h1>
        <p className="text-sm text-muted-foreground">{message}</p>
        {apiError?.requestId && (
          <p className="font-mono text-xs text-muted-foreground">Reference {apiError.requestId}</p>
        )}
      </div>
      <Button
        variant="outline"
        onClick={() => {
          reset();
          void router.invalidate();
        }}
      >
        Try again
      </Button>
    </div>
  );
}
