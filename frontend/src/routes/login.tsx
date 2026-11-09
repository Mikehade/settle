import { createFileRoute, redirect } from "@tanstack/react-router";

import { Logo } from "@/components/logo";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LoginForm } from "@/features/auth/login-form";
import { safeRedirect } from "@/features/auth/redirect";
import { getActiveSession } from "@/lib/session";
import { pageTitle } from "@/lib/utils";

interface LoginSearch {
  redirect?: string;
  reason?: "expired";
}

// A plain parser rather than a zod schema: route options load with the entry bundle, and the two
// fields here do not justify shipping zod to every visitor before they reach a form.
function parseSearch(search: Record<string, unknown>): LoginSearch {
  return {
    redirect: typeof search.redirect === "string" ? search.redirect : undefined,
    reason: search.reason === "expired" ? "expired" : undefined,
  };
}

export const Route = createFileRoute("/login")({
  validateSearch: parseSearch,
  beforeLoad: ({ search }) => {
    if (getActiveSession()) throw redirect({ href: safeRedirect(search.redirect) });
  },
  head: () => ({ meta: [{ title: pageTitle("Sign in") }] }),
  component: LoginPage,
});

function LoginPage() {
  const search = Route.useSearch();

  return (
    <main className="flex min-h-svh items-center justify-center bg-muted/40 px-4 py-12">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex items-center gap-2.5 px-1">
          <Logo className="size-7" />
          <span className="text-sm font-semibold tracking-tight">Settle</span>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>
              <h1 className="text-xl">Sign in</h1>
            </CardTitle>
            <CardDescription>
              Use the account your Settle administrator set up for you.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <LoginForm
              redirectTo={safeRedirect(search.redirect)}
              sessionExpired={search.reason === "expired"}
            />
          </CardContent>
        </Card>

        <p className="px-1 text-xs text-muted-foreground">
          Settle mediates PayPal disputes under your fairness policy and escalates anything outside
          it to you.
        </p>
      </div>
    </main>
  );
}
