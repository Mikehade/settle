import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { CircleAlert, Clock, Eye, EyeOff, Loader2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { isApiError } from "@/lib/api/errors";
import { applyServerFieldErrors, serverFieldErrors } from "@/lib/forms";

import { signIn } from "./api";

const schema = z.object({
  email: z.email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});

type Values = z.infer<typeof schema>;

const FIELDS = ["email", "password"] as const;

interface LoginFormProps {
  redirectTo: string;
  sessionExpired: boolean;
}

export function LoginForm({ redirectTo, sessionExpired }: LoginFormProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showPassword, setShowPassword] = useState(false);

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });
  const { errors } = form.formState;

  const login = useMutation({
    mutationFn: signIn,
    meta: { silentError: true },
    onSuccess: async () => {
      // Nothing cached under a previous account may leak into this one.
      queryClient.clear();
      await navigate({ href: redirectTo, replace: true });
    },
    onError: (error) => {
      if (applyServerFieldErrors(error, FIELDS, form.setError)) return;
      if (isApiError(error) && error.code === "AUTH_INVALID_CREDENTIALS") {
        form.resetField("password");
        form.setFocus("password");
      }
    },
  });

  const onSubmit = form.handleSubmit((values) => login.mutate(values));
  // Errors the backend tied to a field are shown on that field instead of in the banner.
  const bannerError =
    login.error && serverFieldErrors(login.error, FIELDS).length === 0 ? login.error : null;
  const notice = bannerError ? describeError(bannerError) : sessionExpired ? EXPIRED : null;

  return (
    <form onSubmit={(event) => void onSubmit(event)} noValidate className="space-y-6">
      {notice && (
        <Alert variant={notice.tone === "error" ? "destructive" : "default"}>
          {notice.tone === "error" ? <CircleAlert /> : <Clock />}
          <AlertTitle>{notice.title}</AlertTitle>
          {notice.description && <AlertDescription>{notice.description}</AlertDescription>}
        </Alert>
      )}

      <FieldGroup>
        <Field data-invalid={Boolean(errors.email)}>
          <FieldLabel htmlFor="email">Email</FieldLabel>
          <Input
            id="email"
            type="email"
            autoComplete="username"
            aria-invalid={Boolean(errors.email)}
            {...form.register("email")}
          />
          <FieldError errors={[errors.email]} />
        </Field>

        <Field data-invalid={Boolean(errors.password)}>
          <FieldLabel htmlFor="password">Password</FieldLabel>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              className="pr-10"
              aria-invalid={Boolean(errors.password)}
              {...form.register("password")}
            />
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="absolute top-1/2 right-1 -translate-y-1/2 text-muted-foreground"
              aria-label={showPassword ? "Hide password" : "Show password"}
              aria-pressed={showPassword}
              onClick={() => setShowPassword((shown) => !shown)}
            >
              {showPassword ? <EyeOff /> : <Eye />}
            </Button>
          </div>
          <FieldError errors={[errors.password]} />
        </Field>
      </FieldGroup>

      <Button type="submit" className="w-full" disabled={login.isPending}>
        {login.isPending && <Loader2 className="animate-spin" />}
        {login.isPending ? "Signing in" : "Sign in"}
      </Button>
    </form>
  );
}

interface Notice {
  tone: "error" | "info";
  title: string;
  description?: string;
}

const EXPIRED: Notice = {
  tone: "info",
  title: "Your session expired",
  description: "Sign in again to pick up where you left off.",
};

function describeError(error: Error): Notice {
  if (!isApiError(error))
    return { tone: "error", title: "Sign-in failed", description: error.message };

  switch (error.code) {
    case "AUTH_INVALID_CREDENTIALS":
      return {
        tone: "error",
        title: "That email and password don't match",
        description: "Check both and try again.",
      };
    case "USER_INACTIVE":
      return {
        tone: "error",
        title: "This account is switched off",
        description: "Ask your Settle administrator to turn it back on.",
      };
    case "NETWORK_ERROR":
      return { tone: "error", title: "Can't reach Settle", description: error.message };
    default:
      return {
        tone: "error",
        title: error.message,
        description: error.requestId ? `Reference ${error.requestId}` : undefined,
      };
  }
}
