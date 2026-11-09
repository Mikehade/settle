import { toast } from "sonner";

import { isApiError } from "@/lib/api/errors";

/** Shows a failure as a toast. API errors carry the request ID so a report can be traced. */
export function notifyError(error: unknown) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  const requestId = isApiError(error) ? error.requestId : null;

  toast.error(message, {
    description: requestId ? `Reference ${requestId}` : undefined,
    action: requestId
      ? { label: "Copy", onClick: () => void navigator.clipboard.writeText(requestId) }
      : undefined,
  });
}
