import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { MapData } from "../../../shared/api/client";

interface Props {
  data: MapData;
  focus: string;
  onDrillDown: (id: string) => void;
}

interface ViewBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

const PAD = 0.18; // fraction of extent added around the pins

function fitViewBox(points: { x: number; y: number }[]): ViewBox {
  if (points.length === 0) return { x: -10, y: -10, w: 20, h: 20 };
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const extent = Math.max(maxX - minX, maxY - minY, 1);
  const pad = extent * PAD;
  return {
    x: minX - pad,
    y: minY - pad,
    w: maxX - minX + pad * 2,
    h: maxY - minY + pad * 2,
  };
}

/* Whether `nodeId` sits inside `ancestorId`'s subtree (player marker lookup). */
function within(data: MapData, nodeId: string | null, ancestorId: string): boolean {
  let cursor = nodeId;
  while (cursor) {
    if (cursor === ancestorId) return true;
    cursor = data.nodes[cursor]?.parent ?? null;
  }
  return false;
}

export function MapCanvas({ data, focus, onDrillDown }: Props) {
  const { t } = useTranslation();
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragging = useRef<{ px: number; py: number } | null>(null);

  const pins = useMemo(
    () =>
      (data.nodes[focus]?.children ?? [])
        .map((id) => ({ id, node: data.nodes[id] }))
        .filter((p) => p.node && p.node.scale === "outdoor" && p.node.position),
    [data, focus],
  );

  const [view, setView] = useState<ViewBox>(() => fitViewBox(pins.map((p) => p.node.position!)));
  const [fittedFor, setFittedFor] = useState(focus);
  if (fittedFor !== focus) {
    setFittedFor(focus);
    setView(fitViewBox(pins.map((p) => p.node.position!)));
  }

  const visible = new Set(pins.map((p) => p.id));
  const edges = data.edges.filter((e) => visible.has(e.from) && visible.has(e.to));
  const unit = view.w / 100; // scale-invariant sizing for pins and strokes

  const onWheel = (e: React.WheelEvent) => {
    const factor = e.deltaY > 0 ? 1.15 : 1 / 1.15;
    setView((v) => {
      const w = v.w * factor;
      const h = v.h * factor;
      return { x: v.x + (v.w - w) / 2, y: v.y + (v.h - h) / 2, w, h };
    });
  };

  const onPointerDown = (e: React.PointerEvent) => {
    dragging.current = { px: e.clientX, py: e.clientY };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging.current || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const dx = ((e.clientX - dragging.current.px) / rect.width) * view.w;
    const dy = ((e.clientY - dragging.current.py) / rect.height) * view.h;
    dragging.current = { px: e.clientX, py: e.clientY };
    setView((v) => ({ ...v, x: v.x - dx, y: v.y - dy }));
  };

  const onPointerUp = () => {
    dragging.current = null;
  };

  if (pins.length === 0) {
    return (
      <p className="p-6 font-display text-sm" style={{ color: "var(--ink-faded)" }}>
        {t("map.no_pins")}
      </p>
    );
  }

  return (
    <svg
      ref={svgRef}
      role="img"
      aria-label={t("map.canvas_label", { name: data.nodes[focus]?.name })}
      className="h-full w-full cursor-grab touch-none select-none"
      viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
      onWheel={onWheel}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      style={{ background: "var(--parchment-aged)" }}
    >
      {/* parchment grain — ink-subtle, no glow */}
      <defs>
        <filter id="map-grain">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" result="noise" />
          <feColorMatrix in="noise" type="saturate" values="0" />
          <feComponentTransfer>
            <feFuncA type="linear" slope="0.05" />
          </feComponentTransfer>
        </filter>
      </defs>
      <rect
        x={view.x}
        y={view.y}
        width={view.w}
        height={view.h}
        filter="url(#map-grain)"
        fill="currentColor"
        style={{ color: "var(--ink-primary)" }}
      />

      {/* travel edges — dashed ink lines */}
      {edges.map((e, i) => {
        const a = data.nodes[e.from].position!;
        const b = data.nodes[e.to].position!;
        return (
          <line
            key={i}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke="var(--line-strong)"
            strokeWidth={unit * 0.35}
            strokeDasharray={`${unit * 1.2} ${unit * 1.2}`}
          />
        );
      })}

      {/* pins */}
      {pins.map(({ id, node }) => {
        const p = node.position!;
        const isPlayerHere = within(data, data.player_position, id);
        const hasOutdoorChildren = node.children.some(
          (c) => data.nodes[c]?.scale === "outdoor" && data.nodes[c]?.position,
        );
        return (
          <g
            key={id}
            transform={`translate(${p.x} ${p.y})`}
            onClick={() => hasOutdoorChildren && onDrillDown(id)}
            style={{ cursor: hasOutdoorChildren ? "pointer" : "default" }}
          >
            {isPlayerHere && (
              <circle r={unit * 2.2} fill="none" stroke="var(--accent)" strokeWidth={unit * 0.4} />
            )}
            <circle
              r={unit * 1.1}
              fill={node.has_status ? "var(--blood)" : "var(--ink-primary)"}
              stroke="var(--parchment-aged)"
              strokeWidth={unit * 0.3}
            />
            {hasOutdoorChildren && (
              <circle
                r={unit * 1.7}
                fill="none"
                stroke="var(--ink-faded)"
                strokeWidth={unit * 0.2}
              />
            )}
            <text
              y={unit * 4}
              textAnchor="middle"
              className="font-display"
              fill="var(--ink-secondary)"
              fontSize={unit * 3}
            >
              {node.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
