// Adapted from manuelbomi Invoice Audit Assistant a0a0fc5 (MIT); see third_party/licenses.
import {
  Background,
  type Edge,
  Handle,
  type Node,
  Position,
  ReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";

import type { GraphNodeName } from "../api/types";

interface GraphViewProps {
  currentNode: GraphNodeName | null;
  completedNodes: GraphNodeName[];
  isLedgerRun?: boolean;
}

interface NodeData extends Record<string, unknown> {
  label: string;
  active: boolean;
  done: boolean;
  skipped: boolean;
}

function StepNode({ data }: { data: NodeData }) {
  const base =
    "rounded-lg border-2 px-3 py-2 text-sm font-medium shadow-sm min-w-[150px] text-center transition-colors";
  const cls = data.active
    ? `${base} border-brand-500 bg-brand-500 text-white `
    : data.done
      ? `${base} border-brand-300 bg-brand-50 text-brand-800`
      : data.skipped
        ? `${base} border-dashed border-slate-200 bg-slate-50 text-slate-300`
        : `${base} border-slate-300 bg-white text-slate-500`;
  return (
    <div className={cls}>
      <Handle type="target" position={Position.Top} className="!bg-slate-400" />
      {data.label}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-slate-400"
      />
    </div>
  );
}

const nodeTypes = { step: StepNode };

const LAYOUT: Record<GraphNodeName, { x: number; y: number; label: string }> = {
  ingest: { x: 260, y: 0, label: "1. 识别材料" },
  calculate: { x: 260, y: 100, label: "2. 计算指标" },
  evidence: { x: 260, y: 200, label: "3. 核对纪要" },
  analyze: { x: 260, y: 300, label: "4. 分析经营" },
  render: { x: 260, y: 400, label: "5. 生成周报" },
  quality: { x: 260, y: 500, label: "6. 自动质检" },
  human_review: { x: 260, y: 600, label: "7. 人工审核" },
  finalize: { x: 260, y: 700, label: "8. 交付成果" },
};

const MIDDLE_NODES: GraphNodeName[] = [
  "calculate",
  "evidence",
  "analyze",
  "human_review",
];

export function GraphView({
  currentNode,
  completedNodes,
  isLedgerRun,
}: GraphViewProps) {
  const nodes: Node[] = useMemo(
    () =>
      (Object.keys(LAYOUT) as GraphNodeName[]).map((id) => ({
        id,
        type: "step",
        position: { x: LAYOUT[id].x, y: LAYOUT[id].y },
        data: {
          label: LAYOUT[id].label,
          active: currentNode === id,
          done: completedNodes.includes(id) && currentNode !== id,
          skipped: Boolean(isLedgerRun) && MIDDLE_NODES.includes(id),
        } satisfies NodeData,
        draggable: false,
      })),
    [currentNode, completedNodes, isLedgerRun],
  );

  const edgeStyle = (active: boolean) => ({
    stroke: active ? "#265ef2" : "#cbd5e1",
    strokeWidth: active ? 2.5 : 1.5,
  });

  const edges: Edge[] = useMemo(
    () => [
      {
        id: "render-quality",
        source: "render",
        target: "quality",
        style: edgeStyle(completedNodes.includes("quality")),
      },
      {
        id: "quality-review",
        source: "quality",
        target: "human_review",
        style: edgeStyle(completedNodes.includes("human_review")),
      },
      {
        id: "e-ingest-extract",
        source: "ingest",
        target: "calculate",
        style: edgeStyle(completedNodes.includes("calculate")),
        hidden: Boolean(isLedgerRun),
      },
      {
        id: "e-extract-evidence",
        source: "calculate",
        target: "evidence",
        style: edgeStyle(completedNodes.includes("evidence")),
        hidden: Boolean(isLedgerRun),
      },
      {
        id: "e-evidence-analyze",
        source: "evidence",
        target: "analyze",
        style: edgeStyle(completedNodes.includes("analyze")),
        hidden: Boolean(isLedgerRun),
      },
      {
        id: "e-analyze-human",
        source: "analyze",
        target: "render",
        style: edgeStyle(completedNodes.includes("human_review")),
        hidden: Boolean(isLedgerRun),
      },
      {
        id: "e-human-finalize",
        source: "human_review",
        target: "finalize",
        style: edgeStyle(completedNodes.includes("finalize")),
        hidden: Boolean(isLedgerRun),
      },
      {
        id: "e-ingest-finalize-ledger",
        source: "ingest",
        target: "finalize",
        label: "ledger upload (skip review)",
        type: "smoothstep",
        style: { stroke: "#0f766e", strokeWidth: 2 },
        hidden: !isLedgerRun,
      },
    ],
    [completedNodes, isLedgerRun],
  );

  return (
    <div className="h-[590px] w-full rounded-xl border border-slate-200 bg-white">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <Background gap={16} color="#e2e8f0" />
      </ReactFlow>
    </div>
  );
}
