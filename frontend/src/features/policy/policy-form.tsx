import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useBlocker } from "@tanstack/react-router";
import { CircleAlert, Info, Loader2, TriangleAlert } from "lucide-react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useNow } from "@/hooks/use-now";
import type { Policy } from "@/lib/api/types";
import { formatDateTime, formatRelative, parseServerTime } from "@/lib/format";
import { applyServerFieldErrors, serverFieldErrors } from "@/lib/forms";

import { policyKeys, savePolicy } from "./api";
import {
  DEFAULT_LIMITS,
  effectiveLimits,
  formatAmount,
  formatPercent,
  LIMITS,
  type LimitKey,
  type PolicyFormValues,
  policySchema,
  RULES_MAX,
  summarize,
  toFormValues,
  toPolicyUpdate,
} from "./policy-model";

const FIELDS = ["rules_text", ...LIMITS.map(({ key }) => key)] as const;

const RULES_PLACEHOLDER = `For example:
- Refund in full when tracking never shows the parcel was shipped.
- For items that arrive damaged, offer a replacement before a refund.
- Never accept a claim on a digital download once it has been downloaded.`;

/** What an empty field means. The accept limit follows the review amount, as it stands now. */
function defaultHint(key: LimitKey, reviewAmount: number) {
  if (key === "auto_accept_max") return `Default: ${formatAmount(reviewAmount)}`;
  if (key === "always_refund_under") return "Default: off";
  const value = DEFAULT_LIMITS[key];
  return `Default: ${key === "confidence_threshold" ? formatPercent(value) : formatAmount(value)}`;
}

/** The fairness policy: plain-English rules for the mediator, and the limits checked in code. */
export function PolicyForm({ policy }: { policy: Policy | null }) {
  const queryClient = useQueryClient();
  const now = useNow();

  const form = useForm<PolicyFormValues>({
    resolver: zodResolver(policySchema),
    defaultValues: toFormValues(policy),
  });
  const { errors, isDirty } = form.formState;
  const values = useWatch({ control: form.control }) as PolicyFormValues;
  const effective = effectiveLimits(values);
  const summary = summarize(effective);

  const save = useMutation({
    mutationFn: savePolicy,
    meta: { silentError: true },
    onSuccess: (saved) => {
      queryClient.setQueryData(policyKeys.all, saved);
      form.reset(toFormValues(saved));
      toast.success("Fairness policy saved", {
        description: "It applies from the next mediation.",
      });
    },
    onError: (error) => applyServerFieldErrors(error, FIELDS, form.setError),
  });

  // Leaving with unsaved changes asks first, in the app and when closing the tab.
  const blocker = useBlocker({
    shouldBlockFn: () => form.formState.isDirty && !save.isPending,
    enableBeforeUnload: () => form.formState.isDirty,
    withResolver: true,
  });

  const onSubmit = form.handleSubmit((submitted) => save.mutate(toPolicyUpdate(submitted)));
  const bannerError =
    save.error && serverFieldErrors(save.error, FIELDS).length === 0 ? save.error : null;
  const savedAt = parseServerTime(policy?.updated_at);
  const rulesLength = values.rules_text.length;

  return (
    <form onSubmit={(event) => void onSubmit(event)} noValidate>
      {!policy && (
        <Alert className="mb-6">
          <Info />
          <AlertTitle>You haven't set a policy yet</AlertTitle>
          <AlertDescription>
            Until you do, the mediator applies ordinary fairness and escalates anything unclear,
            within the default limits below.
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start">
        <div className="min-w-0 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Your rules</CardTitle>
              <CardDescription>
                Written in plain English. The mediator applies them literally and quotes the rule it
                relies on.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Field data-invalid={Boolean(errors.rules_text)}>
                <FieldLabel htmlFor="rules_text" className="sr-only">
                  Your rules
                </FieldLabel>
                <Textarea
                  id="rules_text"
                  rows={8}
                  placeholder={RULES_PLACEHOLDER}
                  className="min-h-48"
                  aria-invalid={Boolean(errors.rules_text)}
                  aria-describedby="rules_text-count"
                  {...form.register("rules_text")}
                />
                <p
                  id="rules_text-count"
                  className={
                    rulesLength > RULES_MAX
                      ? "text-xs text-destructive"
                      : "text-xs text-muted-foreground"
                  }
                >
                  {rulesLength.toLocaleString("en-US")} of {RULES_MAX.toLocaleString("en-US")}{" "}
                  characters
                </p>
                <FieldError errors={[errors.rules_text]} />
              </Field>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Limits</CardTitle>
              <CardDescription>
                Checked in code after the mediator decides, so it can't talk its way past them.
                Leave a field empty to use the default. Amounts are in each dispute's own currency.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {LIMITS.map(({ key, label, description, kind }) => (
                <Field key={key} data-invalid={Boolean(errors[key])}>
                  <FieldLabel htmlFor={key}>{label}</FieldLabel>
                  <div className="relative max-w-48">
                    <Input
                      id={key}
                      inputMode="decimal"
                      autoComplete="off"
                      placeholder={defaultHint(key, effective.reviewAmount)}
                      className={kind === "percent" ? "pr-8" : undefined}
                      aria-invalid={Boolean(errors[key])}
                      aria-describedby={`${key}-description`}
                      {...form.register(key)}
                    />
                    {kind === "percent" && (
                      <span
                        aria-hidden
                        className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-sm text-muted-foreground"
                      >
                        %
                      </span>
                    )}
                  </div>
                  <FieldDescription id={`${key}-description`}>{description}</FieldDescription>
                  <FieldError errors={[errors[key]]} />
                </Field>
              ))}
            </CardContent>
          </Card>
        </div>

        <Card className="lg:sticky lg:top-20">
          <CardHeader>
            <CardTitle>In practice</CardTitle>
            <CardDescription>Settle settles a case without you only when:</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <ul aria-label="When Settle acts alone" className="list-disc space-y-1.5 pl-5 text-sm">
              {summary.rules.map((rule) => (
                <li key={rule}>{rule}</li>
              ))}
            </ul>
            <p className="text-sm text-muted-foreground">
              Anything else comes to you with a recommendation.
            </p>
            {summary.warnings.map((warning) => (
              <p key={warning} className="flex gap-2 text-sm text-warning-strong">
                <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
                {warning}
              </p>
            ))}
          </CardContent>
        </Card>
      </div>

      {bannerError && (
        <Alert variant="destructive" className="mt-6">
          <CircleAlert />
          <AlertTitle>Couldn't save your policy</AlertTitle>
          <AlertDescription>{bannerError.message}</AlertDescription>
        </Alert>
      )}

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t pt-6">
        <p className="text-sm text-muted-foreground">
          {isDirty ? (
            "You have unsaved changes."
          ) : savedAt !== null ? (
            <time dateTime={new Date(savedAt).toISOString()} title={formatDateTime(savedAt)}>
              Saved {formatRelative(savedAt, now)}
            </time>
          ) : (
            "Not saved yet."
          )}
        </p>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={!isDirty || save.isPending}
            onClick={() => form.reset()}
          >
            Discard changes
          </Button>
          <Button type="submit" disabled={!isDirty || save.isPending}>
            {save.isPending && <Loader2 className="animate-spin" />}
            {save.isPending ? "Saving" : "Save policy"}
          </Button>
        </div>
      </div>

      <AlertDialog open={blocker.status === "blocked"}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Leave without saving?</AlertDialogTitle>
            <AlertDialogDescription>
              Your changes to the fairness policy haven't been saved.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => blocker.reset?.()}>Keep editing</AlertDialogCancel>
            <AlertDialogAction onClick={() => blocker.proceed?.()}>Leave</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </form>
  );
}
