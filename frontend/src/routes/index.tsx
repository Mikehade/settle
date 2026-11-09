import { createFileRoute, redirect } from "@tanstack/react-router";

import { DEFAULT_SIGNED_IN_PATH } from "@/features/auth/redirect";

export const Route = createFileRoute("/")({
  beforeLoad: () => {
    throw redirect({ to: DEFAULT_SIGNED_IN_PATH });
  },
});
