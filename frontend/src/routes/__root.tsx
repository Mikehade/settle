import type { QueryClient } from "@tanstack/react-query";
import { createRootRouteWithContext, HeadContent, Link, Outlet } from "@tanstack/react-router";
import { lazy, Suspense } from "react";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

export interface RouterContext {
  queryClient: QueryClient;
}

const showDevtools = import.meta.env.DEV && import.meta.env.MODE !== "test";
const Devtools = showDevtools ? lazy(() => import("@/app/devtools")) : () => null;

export const Route = createRootRouteWithContext<RouterContext>()({
  head: () => ({ meta: [{ title: "Settle" }] }),
  component: RootLayout,
  notFoundComponent: NotFound,
});

function RootLayout() {
  return (
    <TooltipProvider delayDuration={300}>
      <HeadContent />
      <Outlet />
      <Toaster position="bottom-right" />
      <Suspense>
        <Devtools />
      </Suspense>
    </TooltipProvider>
  );
}

function NotFound() {
  return (
    <main className="mx-auto flex min-h-svh max-w-md flex-col justify-center gap-3 px-6">
      <p className="font-mono text-xs text-muted-foreground">404</p>
      <h1 className="text-xl font-semibold tracking-tight">Page not found</h1>
      <p className="text-sm text-muted-foreground">
        The page you asked for does not exist or has moved.
      </p>
      <Link to="/" className="text-sm font-medium underline underline-offset-4">
        Back to start
      </Link>
    </main>
  );
}
