import type { GraphNodeName, StateSnapshot } from "./types";

export function completedFromSnapshot(raw: StateSnapshot): GraphNodeName[] {
  const s = normalizeSnapshot(raw);
  const done: Partial<Record<GraphNodeName, boolean>> = {
    ingest: !!s.sales,
    calculate: !!s.metrics,
    evidence: !!s.minutes?.sources?.length,
    news: !!s.news?.status,
    analyze: !!s.draft,
    render: !!s.artifact,
    quality: s.quality?.passed === true,
    human_review: s.status === "approved" || s.status === "completed",
    finalize: s.status === "completed",
  };
  return (Object.keys(done) as GraphNodeName[]).filter((key) => done[key]);
}

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
