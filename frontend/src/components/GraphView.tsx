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
}

interface NodeData extends Record<string, unknown> {
  label: string;
  active: boolean;
  done: boolean;
}

function StepNode({ data }: { data: NodeData }) {
  const base =
    "rounded-lg border-2 px-3 py-2 text-sm font-medium shadow-sm min-w-[150px] text-center transition-colors";
  const cls = data.active
    ? `${base} border-brand-500 bg-brand-500 text-white `
    : data.done
      ? `${base} border-brand-300 bg-brand-50 text-brand-800`
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
  calculate: { x: 260, y: 64, label: "2. 计算指标" },
  evidence: { x: 260, y: 128, label: "3. 核对纪要" },
  analyze: { x: 260, y: 192, label: "4. 分析经营" },
  render: { x: 260, y: 256, label: "5. 生成周报" },
  quality: { x: 260, y: 320, label: "6. 自动质检" },
  human_review: { x: 260, y: 384, label: "7. 人工审核" },
  finalize: { x: 260, y: 448, label: "8. 交付成果" },
};

export function GraphView({ currentNode, completedNodes }: GraphViewProps) {
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
        } satisfies NodeData,
        draggable: false,
      })),
    [currentNode, completedNodes],
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
      },
      {
        id: "e-extract-evidence",
        source: "calculate",
        target: "evidence",
        style: edgeStyle(completedNodes.includes("evidence")),
      },
      {
        id: "e-evidence-analyze",
        source: "evidence",
        target: "analyze",
        style: edgeStyle(completedNodes.includes("analyze")),
      },
      {
        id: "e-analyze-render",
        source: "analyze",
        target: "render",
        style: edgeStyle(completedNodes.includes("render")),
      },
      {
        id: "e-human-finalize",
        source: "human_review",
        target: "finalize",
        style: edgeStyle(completedNodes.includes("finalize")),
      },
    ],
    [completedNodes],
  );

  return (
    <div
      aria-label="任务执行流程图"
      className="h-[560px] w-full rounded-xl border border-slate-200 bg-white"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.1 }}
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
