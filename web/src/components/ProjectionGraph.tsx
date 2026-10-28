import React, { useMemo } from 'react';

interface Node {
  id: string;
  label: string;
  probability: number;
  type: string;
}

interface Edge {
  source: string;
  target: string;
  probability: number;
}

interface ProjectionGraphProps {
  nodes: Node[];
  edges: Edge[];
}

export const ProjectionGraph: React.FC<ProjectionGraphProps> = ({ nodes, edges }) => {
  const width = 800;
  const height = 600;

  const layout = useMemo(() => {
    const positions: Record<string, { x: number; y: number }> = {};
    nodes.forEach((node, i) => {
      // Simple layered layout
      const hop = parseInt(node.id.split('_')[1]) || 0;
      positions[node.id] = {
        x: 100 + hop * 200,
        y: 100 + (i % 3) * 150,
      };
    });
    return positions;
  }, [nodes]);

  return (
    <div className="p-4 bg-slate-900 rounded-xl border border-slate-700">
      <h3 className="text-white font-bold mb-4">Projection Path</h3>
      <svg width={width} height={height} className="mx-auto">
        <defs>
          <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="0" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#64748b" />
          </marker>
        </defs>
        {edges.map((edge, i) => {
          const start = layout[edge.source];
          const end = layout[edge.target];
          if (!start || !end) return null;
          return (
            <line
              key={i}
              x1={start.x} y1={start.y} x2={end.x} y2={end.y}
              stroke="#64748b" strokeWidth={2 * edge.probability}
              markerEnd="url(#arrowhead)"
            />
          );
        })}
        {nodes.map((node, i) => {
          const { x, y } = layout[node.id];
          return (
            <g key={node.id} transform={`translate(${x}, ${y})`}>
              <circle
                r={20 + node.probability * 20}
                fill={node.type === 'fact' ? '#3b82f6' : '#8b5cf6'}
                className="transition-all duration-500"
              />
              <text
                textAnchor="middle"
                dy=".3em"
                fill="white"
                fontSize="12"
                fontWeight="bold"
              >
                {node.label}
              </text>
              <text
                textAnchor="middle"
                dy="2.5em"
                fill="#94a3b8"
                fontSize="10"
              >
                {(node.probability * 100).toFixed(1)}%
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
};
