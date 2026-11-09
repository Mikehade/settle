import { CircleCheck, CircleDashed, CircleX, LoaderCircle, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { Decision, ReasoningStage } from "@/features/mediation/events";
import {
  isActive,
  type Run,
  type RunStatus,
  type ToolCall,
  UNSTAGED,
} from "@/features/mediation/store";
import { formatDateTime, formatMoney, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

import type { CaseDecision, CaseDetail } from "./case-detail";
import {
  asDisputeType,
  DISPUTE_TYPE_LABELS,
  OUTCOME_LABELS,
  STAGE_LABELS,
  STAGES,
  toolLabel,
} from "./labels";
import { ModelText } from "./model-text";

const PHASE: Record<RunStatus, string> = {
  requested: "Waiting for Settle to start",
  gathering: "Gathering the case from PayPal",
  reasoning: "Reasoning through the case",
  escalated: "Escalated to you",
  resolved: "Carried out",
  failed: "Didn't finish",
};

type StageState = "done" | "streaming" | "pending";

interface StageView {
  stage: ReasoningStage;
  state: StageState;
  text: string;
}

/** "not_received" reads better as the type's label. */
function readable(text: string) {
  const type = asDisputeType(text.trim());
  return type ? DISPUTE_TYPE_LABELS[type] : text;
}

function stagesOfRun(run: Run): StageView[] {
  const active = isActive(run);
  return STAGES.flatMap((stage): StageView[] => {
    const step = run.steps.find((item) => item.stage === stage);
    if (step) return [{ stage, state: "done", text: readable(step.text) }];
    const narration = run.narration[stage];
    if (narration) return [{ stage, state: active ? "streaming" : "done", text: narration }];
    // A finished run that never reached a stage has nothing to say about it.
    return active ? [{ stage, state: "pending", text: "" }] : [];
  });
}

function percent(confidence: number | undefined) {
  return confidence == null ? null : `${Math.round(confidence * 100)}%`;
}

/**
 * The reasoning a recorded decision kept. The model's own words for the last stage aren't stored,
 * and the decision summary under the chain already says what it chose and how sure it was.
 */
function stagesOfDecision(decision: Decision): StageView[] {
  const texts: Record<ReasoningStage, string | undefined> = {
    classify: decision.classification ?? decision.dispute_type,
    weigh: decision.evidence_summary,
    policy: decision.policy_application,
    choose: undefined,
  };
  return STAGES.flatMap((stage) => {
    const text = texts[stage]?.trim();
    return text ? [{ stage, state: "done" as const, text: readable(text) }] : [];
  });
}

const STAGE_ICON: Record<StageState, ReactNode> = {
  done: <CircleCheck className="size-4 text-success" />,
  streaming: <LoaderCircle className="size-4 animate-spin text-info" />,
  pending: <CircleDashed className="size-4 text-muted-foreground/60" />,
};

function ReasoningChain({ stages, preamble }: { stages: StageView[]; preamble?: string }) {
  return (
    <div className="space-y-4">
      {preamble?.trim() && (
        <ModelText text={preamble} className="text-sm leading-relaxed text-muted-foreground" />
      )}
      <ol className="space-y-4" aria-label="Reasoning">
        {stages.map(({ stage, state, text }) => (
          <li key={stage} className="flex gap-3">
            <span className="mt-0.5 shrink-0" aria-hidden>
              {STAGE_ICON[state]}
            </span>
            <div className="min-w-0 space-y-1">
              <p
                className={cn(
                  "text-sm font-medium",
                  state === "pending" && "text-muted-foreground",
                )}
              >
                {STAGE_LABELS[stage]}
                {state === "streaming" && <span className="sr-only"> (in progress)</span>}
              </p>
              {text.trim() && (
                <ModelText text={text} className="text-sm leading-relaxed text-muted-foreground" />
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function describeInput(input: Record<string, unknown>) {
  return Object.entries(input)
    .map(([key, value]) => `${key.replaceAll("_", " ")} ${String(value)}`)
    .join(", ");
}

function ToolList({ tools }: { tools: ToolCall[] }) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground">Checks the mediator ran</p>
      <ul className="space-y-1.5">
        {tools.map((tool, index) => (
          <li key={index} className="flex items-center gap-2 text-sm">
            {tool.ok === null ? (
              <LoaderCircle aria-hidden className="size-3.5 animate-spin text-info" />
            ) : tool.ok ? (
              <CircleCheck aria-hidden className="size-3.5 text-success" />
            ) : (
              <CircleX aria-hidden className="size-3.5 text-destructive" />
            )}
            <span>{toolLabel(tool.name)}</span>
            <span className="truncate text-xs text-muted-foreground">
              {describeInput(tool.input)}
            </span>
            <span className="sr-only">
              {tool.ok === null ? "running" : tool.ok ? "succeeded" : "failed"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function outcomeText(decision: Decision, currency: string) {
  if (!decision.outcome) return "No clear outcome";
  if (decision.outcome === "refund" && decision.refund_amount != null) {
    return `${OUTCOME_LABELS.refund} ${formatMoney(decision.refund_amount, currency)}`;
  }
  return OUTCOME_LABELS[decision.outcome];
}

function DecisionSummary({ latest, currency }: { latest: CaseDecision; currency: string }) {
  const { decision } = latest;
  const confidence = percent(decision.confidence);

  return (
    <section aria-label="Decision" className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="text-base font-medium">{outcomeText(decision, currency)}</p>
        {confidence && <p className="text-sm text-muted-foreground">{confidence} confident</p>}
      </div>

      {decision.gate === "escalate" && (
        <div className="space-y-1 rounded-md border border-warning/30 bg-warning/10 p-3 text-sm">
          <p className="font-medium text-warning-strong">Escalated to you</p>
          {latest.recommendation && <ModelText text={latest.recommendation} />}
          {/* Muted grey is too faint on the warning tint, so this is softened foreground. */}
          {latest.gateReason && <p className="text-foreground/80">Why: {latest.gateReason}</p>}
        </div>
      )}

      {latest.rationale && (
        <ModelText text={latest.rationale} className="text-sm leading-relaxed" />
      )}

      {/* An escalation's action ("Escalated to the seller") only repeats the callout above. */}
      {latest.actionTaken && decision.gate !== "escalate" && (
        <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span>{latest.actionTaken}</span>
          {latest.dryRun && <Badge variant="outline">Dry run</Badge>}
        </p>
      )}
    </section>
  );
}

/** A decision on record: the reasoning it gave, then what it decided and what came of it. */
export function DecisionDetail({ latest, currency }: { latest: CaseDecision; currency: string }) {
  const stages = stagesOfDecision(latest.decision);
  return (
    <div className="space-y-6">
      {stages.length > 0 && (
        <>
          <ReasoningChain stages={stages} />
          <Separator />
        </>
      )}
      <DecisionSummary latest={latest} currency={currency} />
    </div>
  );
}

interface MediationPanelProps {
  detail: CaseDetail;
  now: number;
  /** Shown under the decision: approve and reject, or mediate. */
  footer?: ReactNode;
}

/** The mediator's work on a case: live while it runs, otherwise the latest decision on record. */
export function MediationPanel({ detail, now, footer }: MediationPanelProps) {
  const { run, latest } = detail;
  const currency = detail.caseFile?.currency ?? "USD";
  const stages = run ? stagesOfRun(run) : latest ? stagesOfDecision(latest.decision) : [];

  let description: ReactNode = detail.canMediate
    ? "Settle hasn't mediated this case yet. Mediate to watch it reason through the case here."
    : "Settle hasn't mediated this case.";
  if (run) {
    description = (
      <span className="inline-flex items-center gap-2">
        {detail.live && (
          <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-info" />
        )}
        {PHASE[run.status]}
      </span>
    );
  } else if (latest?.decidedAt != null) {
    description = (
      <time
        dateTime={new Date(latest.decidedAt).toISOString()}
        title={formatDateTime(latest.decidedAt)}
      >
        Decided {formatRelative(latest.decidedAt, now)}
      </time>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Mediation</CardTitle>
        <CardDescription aria-live="polite">{description}</CardDescription>
      </CardHeader>

      {(run || latest) && (
        <CardContent className="space-y-6">
          {run?.interrupted && (
            <p className="text-sm text-muted-foreground">
              The connection dropped during this run, so part of it may be missing here.
            </p>
          )}
          {run?.error && (
            <Alert variant="destructive">
              <TriangleAlert />
              <AlertTitle>The mediation stopped before a decision</AlertTitle>
              <AlertDescription>{run.error}</AlertDescription>
            </Alert>
          )}
          {stages.length > 0 && (
            <ReasoningChain stages={stages} preamble={run?.narration[UNSTAGED]} />
          )}
          {run && run.tools.length > 0 && <ToolList tools={run.tools} />}
          {latest && (
            <>
              <Separator />
              <DecisionSummary latest={latest} currency={currency} />
            </>
          )}
        </CardContent>
      )}

      {footer && <CardFooter className="flex flex-wrap gap-2">{footer}</CardFooter>}
    </Card>
  );
}
