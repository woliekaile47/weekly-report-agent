import type { StateSnapshot } from "./types";

/** LangGraph clears derived results with {} after changed inputs or before generation. */
export function normalizeSnapshot(state: StateSnapshot): StateSnapshot {
  return {
    ...state,
    draft:
      typeof state.draft?.summary === "string" &&
      Array.isArray(state.draft.anomalies) &&
      Array.isArray(state.draft.actions)
        ? state.draft
        : undefined,
    metrics:
      state.metrics?.total && Array.isArray(state.metrics.groups)
        ? state.metrics
        : undefined,
    sales: state.sales?.mapping ? state.sales : undefined,
    artifact: state.artifact?.file ? state.artifact : undefined,
    quality: Array.isArray(state.quality?.checks) ? state.quality : undefined,
  };
}
