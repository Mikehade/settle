import { MutationCache, QueryClient } from "@tanstack/react-query";

import { isApiError } from "@/lib/api/errors";
import { notifyError } from "@/lib/notify";

declare module "@tanstack/react-query" {
  interface Register {
    mutationMeta: {
      /** Set when the caller shows the error itself, e.g. inline in a form. */
      silentError?: boolean;
    };
  }
}

export function createQueryClient() {
  return new QueryClient({
    // Queries show their errors where the data would be; failed actions get a toast.
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) => {
        if (!mutation.meta?.silentError) notifyError(error);
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        // A 4xx will fail the same way again; only network and server errors are worth a retry.
        retry: (failureCount, error) =>
          failureCount < 2 && (!isApiError(error) || error.isRetryable),
      },
    },
  });
}

export const queryClient = createQueryClient();
