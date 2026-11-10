// Adapted from invoice assistant a0a0fc5, MIT. Persistent replay and Chinese errors added.
import { useEffect, useState } from "react";

import { streamUrl } from "../api/client";
import { completedFromSnapshot, normalizeSnapshot } from "../api/snapshot";
import type {
  GraphNodeName,
  InterruptPayload,
  RunStatus,
  StateSnapshot,
  TraceEventOut,
} from "../api/types";

export interface RunStreamState {
  status: RunStatus | "connecting";
  currentNode: GraphNodeName | null;
  completedNodes: GraphNodeName[];
  snapshot: StateSnapshot;
  trace: TraceEventOut[];
  interrupt: InterruptPayload | null;
  finalStatus: string | null;
  error: string | null;
}

const INITIAL_STATE: RunStreamState = {
  status: "connecting",
  currentNode: null,
  completedNodes: [],
  snapshot: {},
  trace: [],
  interrupt: null,
  finalStatus: null,
  error: null,
};

const TERMINAL_STATUSES = new Set(["completed", "rejected", "error"]);

/**
 * Subscribes to `GET /runs/{id}/stream` (Server-Sent Events) and folds the
 * incoming events into a single state object a component can render
 * directly -- driving both the live GraphView highlighting and the
 * extraction/validation/reconciliation output panels.
 */
export function useRunStream(
  runId: string | null,
  generation = 0,
): RunStreamState {
  const [state, setState] = useState<RunStreamState>(INITIAL_STATE);

  useEffect(() => {
    if (!runId) {
      setState(INITIAL_STATE);
      return;
    }

    setState({ ...INITIAL_STATE, status: "connecting" });
    const source = new EventSource(streamUrl(runId));

    source.addEventListener("node", (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as {
        node: GraphNodeName;
        output: Record<string, unknown>;
        trace: TraceEventOut[];
      };
      setState((prev) => ({
        ...prev,
        status: "running",
        currentNode: data.node,
        completedNodes: completedFromSnapshot(data.output as StateSnapshot),
        snapshot: normalizeSnapshot({
          ...prev.snapshot,
          ...(data.output as StateSnapshot),
        }),
        trace: [...prev.trace, ...data.trace],
      }));
    });

    source.addEventListener("interrupt", (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as InterruptPayload;
      setState((prev) => ({
        ...prev,
        status: "awaiting_human",
        currentNode: "human_review",
        completedNodes: completedFromSnapshot(prev.snapshot),
        interrupt: data,
      }));
    });

    source.addEventListener("done", (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as {
        status: RunStatus;
        final_status: string | null;
      };
      setState((prev) => ({
        ...prev,
        status: data.status,
        finalStatus: data.final_status,
        currentNode: TERMINAL_STATUSES.has(data.status)
          ? "finalize"
          : prev.currentNode,
        completedNodes: completedFromSnapshot({
          ...prev.snapshot,
          status: data.status,
        }),
      }));
      source.close();
    });

    source.addEventListener("replay", (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as {
        status: RunStatus;
        trace: TraceEventOut[];
        state_snapshot: StateSnapshot;
        final_status: string | null;
      };
      setState((prev) => ({
        ...prev,
        status: data.status,
        trace: data.trace,
        error: null,
        snapshot: normalizeSnapshot(data.state_snapshot),
        completedNodes: completedFromSnapshot(data.state_snapshot),
        currentNode:
          data.state_snapshot.status === "paused"
            ? (data.state_snapshot.resume_node ?? null)
            : (data.state_snapshot.current_node ?? null),
        finalStatus: data.final_status,
      }));
    });

    source.addEventListener("error", (evt) => {
      // Only MessageEvents carry a backend-emitted `error` payload; a plain
      // connection failure fires this same listener with no `.data`.
      const data = (evt as MessageEvent).data;
      if (typeof data === "string") {
        const parsed = JSON.parse(data) as { message: string };
        setState((prev) => ({
          ...prev,
          status: "error",
          error: parsed.message,
        }));
        source.close();
      }
    });

    source.onerror = () => {
      setState((prev) =>
        TERMINAL_STATUSES.has(prev.status)
          ? prev
          : {
              ...prev,
              error:
                prev.error ?? "执行流连接中断，正在重连；不会重新提交任务。",
            },
      );
    };

    return () => {
      source.close();
    };
    // `generation` is bumped by callers (e.g. after POST /resume) to force
    // a fresh EventSource connection against the new background task.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, generation]);

  return state;
}
