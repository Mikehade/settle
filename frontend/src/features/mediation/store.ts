import { create } from "zustand";

import type { CaseFile, Decision, ExecutionResult, ReasoningStage, ServerEvent } from "./events";
import { type ConnectionStatus, IDLE } from "./socket";

/**
 * Where one mediation is.
 * - `requested`: this tab asked; the server has not started yet.
 * - `gathering`: the server is assembling the case file.
 * - `reasoning`: the mediator is working through the case.
 * - `escalated`: the guardrails handed it to the seller, who must approve or reject.
 * - `resolved`: the decision was carried out (a dry run for demo disputes).
 * - `failed`: it ended without a decision, or the server refused to start it.
 */
export type RunStatus =
  "requested" | "gathering" | "reasoning" | "escalated" | "resolved" | "failed";

export interface ToolCall {
  name: string;
  input: Record<string, unknown>;
  /** `null` until the tool returns. */
  ok: boolean | null;
}

/** Narration the model streamed before it marked its first stage, or without marking any. */
export const UNSTAGED = "other";
export type NarrationKey = ReasoningStage | typeof UNSTAGED;

export interface Run {
  disputeId: string;
  status: RunStatus;
  /** Started from this tab, rather than from another tab or by the PayPal webhook. */
  startedHere: boolean;
  caseFile: CaseFile | null;
  /** The stages of the reasoning chain that are complete, in the order they finished. */
  steps: { stage: ReasoningStage; text: string }[];
  /** The narration as it streams, by the stage it belongs to. */
  narration: Partial<Record<NarrationKey, string>>;
  tools: ToolCall[];
  decision: Decision | null;
  escalation: { recommendation: string | null; gateReason: string | null } | null;
  execution: ExecutionResult | null;
  /** The closing explanation. Its arrival ends the run. */
  explanation: { rationale: string; actionTaken: string } | null;
  /** Why it failed. Only a failed run has one. */
  error: string | null;
  /** The connection dropped while it was under way, so some of its trace may be missing. */
  interrupted: boolean;
  startedAt: number;
  updatedAt: number;
}

export interface MediationState {
  connection: ConnectionStatus;
  /** The runs this tab has seen, latest per dispute. */
  runs: Record<string, Run>;
}

export const initialMediationState: MediationState = { connection: IDLE, runs: {} };

/** Live mediation state for this tab. Change it only through the mediation client. */
export const useMediationStore = create<MediationState>()(() => initialMediationState);

const ACTIVE: ReadonlySet<RunStatus> = new Set(["requested", "gathering", "reasoning"]);

/** Still working towards a decision. */
export function isActive(run: Run | undefined) {
  return run !== undefined && ACTIVE.has(run.status);
}

/** Nothing more will arrive for it: it was explained, or it failed. */
export function isFinished(run: Run | undefined) {
  return run === undefined || run.explanation !== null || run.status === "failed";
}

function newRun(disputeId: string, now: number, startedHere: boolean): Run {
  return {
    disputeId,
    status: "gathering",
    startedHere,
    caseFile: null,
    steps: [],
    narration: {},
    tools: [],
    decision: null,
    escalation: null,
    execution: null,
    explanation: null,
    error: null,
    interrupted: false,
    startedAt: now,
    updatedAt: now,
  };
}

function setRun(state: MediationState, run: Run): MediationState {
  return { ...state, runs: { ...state.runs, [run.disputeId]: run } };
}

/**
 * Applies a step forward to a dispute's run. Joins a run already under way (after a reconnect, or
 * one started elsewhere) by starting a record of it from here, and starts afresh after a finished
 * one. A run this tab requested keeps that it started here.
 */
function advance(
  state: MediationState,
  disputeId: string,
  now: number,
  change: (run: Run) => Partial<Run>,
): MediationState {
  const current = state.runs[disputeId];
  const run = current && !isFinished(current) ? current : newRun(disputeId, now, false);
  return setRun(state, { ...run, ...change(run), updatedAt: now });
}

/** Past gathering once anything of the mediator's own arrives. */
const reasoning = (run: Run): RunStatus => (isActive(run) ? "reasoning" : run.status);

/** Folds one server event into the state. Pure, so it is tested without a socket. */
export function applyServerEvent(
  state: MediationState,
  event: ServerEvent,
  now = Date.now(),
): MediationState {
  switch (event.event) {
    case "case.detected": {
      const disputeId = event.data.dispute_id;
      const current = state.runs[disputeId];
      // The start of a run. Only one this tab requested carries on; anything else starts over.
      if (current?.status === "requested") {
        return setRun(state, { ...current, status: "gathering", updatedAt: now });
      }
      return setRun(state, newRun(disputeId, now, false));
    }

    case "case.gathering": {
      const caseFile = event.data.case_file;
      return advance(state, event.data.dispute_id, now, (run) =>
        caseFile
          ? { caseFile, status: "reasoning" }
          : { status: isActive(run) ? "gathering" : run.status },
      );
    }

    case "case.reasoning_step": {
      const { stage, text } = event.data;
      return advance(state, event.data.dispute_id, now, (run) => ({
        status: reasoning(run),
        // A stage completes once; replace rather than repeat it if the server ever resends one.
        steps: [...run.steps.filter((step) => step.stage !== stage), { stage, text }],
      }));
    }

    case "case.token": {
      const key: NarrationKey = event.data.stage ?? UNSTAGED;
      return advance(state, event.data.dispute_id, now, (run) => ({
        status: reasoning(run),
        narration: { ...run.narration, [key]: (run.narration[key] ?? "") + event.data.text },
      }));
    }

    case "case.tool_call": {
      const { name, input } = event.data;
      return advance(state, event.data.dispute_id, now, (run) => ({
        status: reasoning(run),
        tools: [...run.tools, { name: name ?? "unknown", input, ok: null }],
      }));
    }

    case "case.tool_result": {
      const name = event.data.name ?? "unknown";
      return advance(state, event.data.dispute_id, now, (run) => {
        const index = run.tools.findLastIndex((tool) => tool.name === name && tool.ok === null);
        if (index === -1) return {};
        return { tools: run.tools.with(index, { ...run.tools[index]!, ok: event.data.ok }) };
      });
    }

    case "case.decision":
      return advance(state, event.data.dispute_id, now, () => ({ decision: event.data.decision }));

    case "case.escalated": {
      const { recommendation, gate_reason: gateReason, decision } = event.data;
      return advance(state, event.data.dispute_id, now, () => ({
        status: "escalated",
        escalation: { recommendation, gateReason },
        decision,
      }));
    }

    case "case.executed": {
      const { dispute_id: disputeId, result, decision } = event.data;
      const run = state.runs[disputeId];
      // Not part of a run under way here: another client approved the case. The lists refetch.
      if (!run || !isActive(run)) return state;
      return setRun(state, {
        ...run,
        status: "resolved",
        execution: result,
        decision: decision ?? run.decision,
        updatedAt: now,
      });
    }

    case "case.explained": {
      const { dispute_id: disputeId, rationale, action_taken: actionTaken, decision } = event.data;
      const run = state.runs[disputeId];
      // Not the end of a run under way here: another client rejected the case.
      if (!run || isFinished(run)) return state;
      return setRun(state, {
        ...run,
        explanation: { rationale, actionTaken },
        decision: decision ?? run.decision,
        updatedAt: now,
      });
    }

    case "case.error": {
      const { dispute_id: disputeId, error } = event.data;
      return disputeId ? failRun(state, disputeId, error, now) : state;
    }

    // The chat lane is a stub on the backend, and `connection.*` is handled by the socket.
    case "agent.message":
    case "agent.typing":
    case "connection.ready":
    case "connection.error":
      return state;
  }
}

/** This tab asked the server to mediate `disputeId`. */
export function requestRun(state: MediationState, disputeId: string, now = Date.now()) {
  return setRun(state, { ...newRun(disputeId, now, true), status: "requested" });
}

/** Ends an unfinished run as failed. Does nothing to one that already finished. */
export function failRun(
  state: MediationState,
  disputeId: string,
  error: string,
  now = Date.now(),
): MediationState {
  const run = state.runs[disputeId];
  if (!run || isFinished(run)) return state;
  return setRun(state, { ...run, status: "failed", error, updatedAt: now });
}

/** The connection dropped. The server keeps going, so the runs under way may still finish. */
export function markDropped(state: MediationState): MediationState {
  let next = state;
  for (const run of Object.values(state.runs)) {
    if (!isFinished(run)) next = setRun(next, { ...run, interrupted: true });
  }
  return next;
}
