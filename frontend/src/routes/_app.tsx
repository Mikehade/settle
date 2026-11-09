import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";

import { AppSidebar } from "@/components/app-sidebar";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { currentUserQuery } from "@/features/auth/api";
import { useSessionLifecycle } from "@/features/auth/use-session-lifecycle";
import { ConnectionStatus } from "@/features/mediation/connection-status";
import { useMediationConnection } from "@/features/mediation/use-mediation-connection";
import { isUnauthorized } from "@/lib/api/errors";
import { getActiveSession, useSessionStore } from "@/lib/session";

/** Every signed-in screen sits under this layout; it is the only place access is checked. */
export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ context, location }) => {
    const toSignIn = (expired: boolean) =>
      redirect({
        to: "/login",
        search: { redirect: location.href, reason: expired ? "expired" : undefined },
      });

    if (!getActiveSession()) throw toSignIn(useSessionStore.getState().endReason === "expired");

    try {
      await context.queryClient.ensureQueryData(currentUserQuery());
    } catch (error) {
      if (isUnauthorized(error)) throw toSignIn(true);
      throw error;
    }
  },
  component: AppLayout,
});

function AppLayout() {
  useSessionLifecycle();
  useMediationConnection();

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/80">
          <SidebarTrigger className="-ml-1" />
          <div className="ml-auto">
            <ConnectionStatus />
          </div>
        </header>
        <div className="flex-1 px-4 py-8 sm:px-8">
          <div className="mx-auto w-full max-w-6xl">
            <Outlet />
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
