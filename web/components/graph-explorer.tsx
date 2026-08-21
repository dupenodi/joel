"use client";

import type { GraphEdge, GraphNode, GraphNodeKind, GraphSlice } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

// 16:9 layout space. The SVG scales to fit its container, so a viewBox that
// disagrees with the viewport's shape letterboxes — bands of dead page down
// both sides of a "full page" graph. Ring radii key off min(W, H), so
// widening this changes how much room the layout has, not how big it draws.
const W = 1280;
const H = 720;
const CX = W / 2;
const CY = H / 2;
const MIN_K = 0.2;
const MAX_K = 8;

/* ------------------------------------------------------------------ *
 * Palette
 *
 * Literal colours, not theme tokens: the ink/surface tokens invert
 * between light and dark, and a node's meaning must not. Every value is
 * mid-tone so it holds contrast against both page backgrounds.
 * ------------------------------------------------------------------ */

export const SOURCE_COLOR: Record<string, string> = {
  gmail: "#e5534b",
  github: "#7d8590",
  slack: "#8a63d2",
  notion: "#9b8f84",
  googledrive: "#4285f4",
  confluence: "#3b7bd8",
  jira: "#3b7bd8",
  fireflies: "#d4763b",
};
const SOURCE_FALLBACK = "#6b7280";

export const ETYPE_COLOR: Record<string, string> = {
  PERSON: "#4f83f1",
  TEAM: "#7b61ff",
  ORGANIZATION: "#5b4bc4",
  CUSTOMER: "#c2308f",
  PROJECT: "#12a594",
  PRODUCT: "#1a8f7a",
  SERVICE: "#0e8a6e",
  POLICY: "#c2571f",
  METRIC: "#b0851f",
  INCIDENT: "#d4453b",
  EVENT: "#a8553d",
  LOCATION: "#6b7f8e",
};
const ENTITY_FALLBACK = "#6b7280";

function sourceColor(t: string | null | undefined) {
  return SOURCE_COLOR[t ?? ""] ?? SOURCE_FALLBACK;
}

function nodeColor(n: GraphNode): string {
  if (n.kind === "entity") return ETYPE_COLOR[n.etype ?? ""] ?? ENTITY_FALLBACK;
  return sourceColor(n.source_type);
}

/* ------------------------------------------------------------------ *
 * Layout
 * ------------------------------------------------------------------ */

/** Where each layer sits, as a fraction of the canvas radius.
 *
 * The graph is a funnel, not a soup: raw connectors on the outside,
 * distilled meaning in the middle. Encoding that as a radius per layer
 * means position carries information before a single edge is read —
 * anything near the centre is knowledge, anything at the rim is plumbing.
 * A pure spring layout loses that: it optimises for edge length and
 * happily buries Gmail between two entities. */
const LAYER_RADIUS: Record<GraphNodeKind, number> = {
  source: 1.0,
  container: 0.74,
  doc: 0.5,
  entity: 0.18,
};

const LAYER_ORDER: GraphNodeKind[] = ["source", "container", "doc", "entity"];

export const LAYER_LABEL: Record<GraphNodeKind, string> = {
  source: "Sources",
  container: "Repos & channels",
  doc: "Documents",
  entity: "Entities",
};

type SimNode = {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  pinned: boolean;
  kind: GraphNodeKind;
  /** Target distance from centre, in px. */
  ring: number;
  links: number;
};

type Link = { s: number; t: number; kind: string };

export type Filters = {
  layers: Record<GraphNodeKind, boolean>;
  sources: Set<string>;
  etypes: Set<string>;
};

export function defaultFilters(): Filters {
  return {
    layers: { source: true, container: true, doc: true, entity: true },
    sources: new Set(),
    etypes: new Set(),
  };
}

/** A node survives filtering if its layer is on, its source is not filtered
 * out, and (for entities) its type is not filtered out. Empty filter sets
 * mean "no restriction" rather than "nothing".
 *
 * `focusId` narrows to one node's neighborhood, walked `hops` deep. This is
 * what replaced the search box: the whole graph is already loaded, so
 * "show me around X" is a traversal of data in hand, not a query someone
 * has to type the right name into. You get there by clicking the thing you
 * can already see.
 */
export function visibleNodes(
  slice: GraphSlice,
  f: Filters,
  focusId?: string | null,
  hops = 1,
): GraphNode[] {
  const passes = (n: GraphNode) => {
    if (!f.layers[n.kind]) return false;
    if (f.sources.size && n.kind !== "entity") {
      if (!f.sources.has(n.source_type ?? "")) return false;
    }
    if (f.etypes.size && n.kind === "entity") {
      if (!f.etypes.has(n.etype ?? "")) return false;
    }
    return true;
  };

  if (!focusId) return slice.nodes.filter(passes);

  // Breadth-first from the focus. Filters still apply, so isolating a node
  // inside a filtered view stays consistent with what was on screen.
  const adjacency = new Map<string, string[]>();
  for (const e of slice.edges) {
    (adjacency.get(e.source) ?? adjacency.set(e.source, []).get(e.source)!).push(e.target);
    (adjacency.get(e.target) ?? adjacency.set(e.target, []).get(e.target)!).push(e.source);
  }
  const keep = new Set<string>([focusId]);
  let frontier = [focusId];
  for (let h = 0; h < hops; h += 1) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const nb of adjacency.get(id) ?? []) {
        if (!keep.has(nb)) {
          keep.add(nb);
          next.push(nb);
        }
      }
    }
    frontier = next;
    if (!frontier.length) break;
  }
  return slice.nodes.filter((n) => keep.has(n.id) && (n.id === focusId || passes(n)));
}

function seed(
  nodes: GraphNode[],
  edges: GraphEdge[],
  previous?: Map<string, { x: number; y: number; pinned: boolean }>,
) {
  const R = Math.min(W, H) / 2;
  const perLayer = new Map<GraphNodeKind, number>();
  for (const n of nodes) perLayer.set(n.kind, (perLayer.get(n.kind) ?? 0) + 1);
  const seen = new Map<GraphNodeKind, number>();

  const sims: SimNode[] = nodes.map((n) => {
    const total = perLayer.get(n.kind) ?? 1;
    const i = seen.get(n.kind) ?? 0;
    seen.set(n.kind, i + 1);
    const ring = LAYER_RADIUS[n.kind] * R;
    // A node that was already on screen keeps its position. Filtering is a
    // change of what you are looking at, not a different graph — re-seeding
    // from scratch threw the layout in the air on every chip toggle, so you
    // lost your place and had to re-find everything you had just located.
    const prior = previous?.get(n.id);
    if (prior) {
      return {
        id: n.id,
        x: prior.x,
        y: prior.y,
        vx: 0,
        vy: 0,
        pinned: prior.pinned,
        kind: n.kind,
        ring,
        links: 0,
      };
    }
    // Spread each layer evenly around its ring to start. Deterministic, so
    // the same graph opens the same way every time.
    const angle = (i / Math.max(total, 1)) * Math.PI * 2 - Math.PI / 2;
    return {
      id: n.id,
      x: CX + Math.cos(angle) * (ring || 40),
      y: CY + Math.sin(angle) * (ring || 40),
      vx: 0,
      vy: 0,
      pinned: false,
      kind: n.kind,
      ring,
      links: 0,
    };
  });

  const index = new Map(sims.map((s, i) => [s.id, i]));
  const links: Link[] = [];
  for (const e of edges) {
    const s = index.get(e.source);
    const t = index.get(e.target);
    if (s == null || t == null || s === t) continue;
    links.push({ s, t, kind: e.kind });
    sims[s].links += 1;
    sims[t].links += 1;
  }
  return { sims, index, links };
}

/** Repulsion falls off with distance and is clamped to REPEL_RANGE, so only
 * nearby pairs ever matter. A uniform grid at that cell size finds them
 * without testing all n², which is what made a few hundred nodes stutter:
 * at 250 nodes the all-pairs loop is ~31k distance tests *per tick*, and
 * there are several ticks per animation frame. */
const REPEL_RANGE = 300;

function tick(sims: SimNode[], links: Link[], alpha: number) {
  const cell = REPEL_RANGE;
  const buckets = new Map<number, number[]>();
  const keyOf = (x: number, y: number) =>
    ((Math.floor(x / cell) + 4096) << 13) ^ (Math.floor(y / cell) + 4096);
  for (let i = 0; i < sims.length; i += 1) {
    const k = keyOf(sims[i].x, sims[i].y);
    const b = buckets.get(k);
    if (b) b.push(i);
    else buckets.set(k, [i]);
  }

  for (let i = 0; i < sims.length; i += 1) {
    const gx = Math.floor(sims[i].x / cell);
    const gy = Math.floor(sims[i].y / cell);
    for (let ox = -1; ox <= 1; ox += 1) {
      for (let oy = -1; oy <= 1; oy += 1) {
        const b = buckets.get(((gx + ox + 4096) << 13) ^ (gy + oy + 4096));
        if (!b) continue;
        for (const j of b) {
          if (j <= i) continue; // each pair once
          let dx = sims[j].x - sims[i].x;
          let dy = sims[j].y - sims[i].y;
          let d2 = dx * dx + dy * dy;
          if (d2 === 0) {
            dx = (i % 7) - 3;
            dy = (j % 7) - 3;
            d2 = dx * dx + dy * dy || 1;
          }
          if (d2 > REPEL_RANGE * REPEL_RANGE) continue;
          const d = Math.sqrt(d2);
          const force = (2200 / d2) * alpha;
          const fx = (dx / d) * force;
          const fy = (dy / d) * force;
          sims[i].vx -= fx;
          sims[i].vy -= fy;
          sims[j].vx += fx;
          sims[j].vy += fy;
        }
      }
    }
  }

  for (const l of links) {
    const a = sims[l.s];
    const b = sims[l.t];
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const d = Math.sqrt(dx * dx + dy * dy) || 1;
    // Structural edges (a repo to its documents) only need to keep things
    // near each other; a typed claim is a real statement of relatedness and
    // pulls harder.
    const ontology = l.kind === "ontology";
    const rest = ontology ? 105 : 150;
    const stiffness = (ontology ? 0.05 : 0.02) * alpha;
    const pull = (d - rest) * stiffness;
    const fx = (dx / d) * pull;
    const fy = (dy / d) * pull;
    a.vx += fx;
    a.vy += fy;
    b.vx -= fx;
    b.vy -= fy;
  }

  for (const s of sims) {
    if (s.pinned) {
      s.vx = 0;
      s.vy = 0;
      continue;
    }
    // Radial constraint: hold each node near its layer's ring while letting
    // springs move it freely *along* that ring. This is what keeps the
    // funnel readable under a force layout instead of collapsing it.
    const dx = s.x - CX;
    const dy = s.y - CY;
    const d = Math.sqrt(dx * dx + dy * dy) || 1;
    const pull = (s.ring - d) * 0.055 * alpha;
    s.vx += (dx / d) * pull;
    s.vy += (dy / d) * pull;

    s.vx *= 0.85;
    s.vy *= 0.85;
    s.x += s.vx;
    s.y += s.vy;
  }
}

function radiusOf(n: GraphNode): number {
  if (n.kind === "source") return 20;
  if (n.kind === "container") return 12;
  if (n.kind === "doc") return 5;
  return 7 + Math.min(n.degree ?? 0, 9) * 1.5;
}

function truncate(s: string, max: number) {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

/* ------------------------------------------------------------------ *
 * Canvas
 * ------------------------------------------------------------------ */

export function GraphCanvas({
  slice,
  filters,
  selectedId,
  focusId,
  focusHops = 1,
  onSelect,
  onFocus,
}: {
  slice: GraphSlice;
  filters: Filters;
  selectedId: string | null;
  focusId?: string | null;
  focusHops?: number;
  onSelect: (id: string | null) => void;
  onFocus?: (id: string | null) => void;
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const [, setFrame] = useState(0);

  const nodes = useMemo(
    () => visibleNodes(slice, filters, focusId, focusHops),
    [slice, filters, focusId, focusHops],
  );
  const nodeIds = useMemo(() => new Set(nodes.map((n) => n.id)), [nodes]);
  const edges = useMemo(
    () => slice.edges.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target)),
    [slice, nodeIds],
  );

  // Positions survive re-seeding (filter toggles, isolate/expand) so the
  // layout stays where the eye left it.
  const placedRef = useRef(new Map<string, { x: number; y: number; pinned: boolean }>());
  const [seedNonce, setSeedNonce] = useState(0);
  const { sims, index, links } = useMemo(
    () => seed(nodes, edges, placedRef.current),
    // `seedNonce` is the reset button's handle on this memo: clearing
    // remembered positions has no effect unless the seed actually re-runs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [nodes, edges, seedNonce],
  );
  const simsRef = useRef(sims);
  simsRef.current = sims;

  const alphaRef = useRef(1);
  const rafRef = useRef<number | null>(null);
  const panRef = useRef<{ px: number; py: number; vx: number; vy: number } | null>(null);
  const dragRef = useRef<{ i: number; moved: boolean } | null>(null);
  const viewRef = useRef(view);
  viewRef.current = view;

  const run = useCallback(() => {
    if (rafRef.current != null) return;
    const step = () => {
      for (let n = 0; n < 2; n += 1) tick(simsRef.current, links, alphaRef.current);
      alphaRef.current = Math.max(0, alphaRef.current - 0.012);
      // Remember where everything landed, so a filter change re-seeds from
      // the current picture instead of scattering it.
      const placed = placedRef.current;
      for (const s of simsRef.current) {
        placed.set(s.id, { x: s.x, y: s.y, pinned: s.pinned });
      }
      setFrame((f) => f + 1);
      if (alphaRef.current > 0.02 || dragRef.current) {
        rafRef.current = requestAnimationFrame(step);
      } else {
        rafRef.current = null;
      }
    };
    rafRef.current = requestAnimationFrame(step);
  }, [links]);

  const settledOnce = useRef(false);
  useEffect(() => {
    // Full heat on first layout; a gentle nudge afterwards. Re-running a
    // cold simulation on every filter toggle is what made the graph feel
    // like it was fighting the user.
    alphaRef.current = settledOnce.current ? 0.25 : 1;
    settledOnce.current = true;
    run();
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [sims, run]);

  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const active = hoverId ?? selectedId;
  const neighbours = useMemo(() => {
    if (!active) return null;
    const set = new Set<string>([active]);
    for (const e of edges) {
      if (e.source === active) set.add(e.target);
      else if (e.target === active) set.add(e.source);
    }
    return set;
  }, [active, edges]);

  const toGraph = useCallback((clientX: number, clientY: number) => {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const rect = svg.getBoundingClientRect();
    const vx = ((clientX - rect.left) / rect.width) * W;
    const vy = ((clientY - rect.top) / rect.height) * H;
    const { x, y, k } = viewRef.current;
    return { x: (vx - x - CX) / k + CX, y: (vy - y - CY) / k + CY };
  }, []);

  function onWheel(event: ReactWheelEvent<SVGSVGElement>) {
    event.preventDefault();
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const vx = ((event.clientX - rect.left) / rect.width) * W;
    const vy = ((event.clientY - rect.top) / rect.height) * H;
    setView((v) => {
      const k = Math.min(MAX_K, Math.max(MIN_K, v.k * (event.deltaY < 0 ? 1.12 : 1 / 1.12)));
      const gx = (vx - v.x - CX) / v.k + CX;
      const gy = (vy - v.y - CY) / v.k + CY;
      return { k, x: vx - CX - (gx - CX) * k, y: vy - CY - (gy - CY) * k };
    });
  }

  function onPointerDown(event: ReactPointerEvent<SVGSVGElement>) {
    if (dragRef.current) return;
    panRef.current = { px: event.clientX, py: event.clientY, vx: view.x, vy: view.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: ReactPointerEvent<SVGSVGElement>) {
    const drag = dragRef.current;
    if (drag) {
      const p = toGraph(event.clientX, event.clientY);
      const n = simsRef.current[drag.i];
      n.x = p.x;
      n.y = p.y;
      n.vx = 0;
      n.vy = 0;
      drag.moved = true;
      alphaRef.current = Math.max(alphaRef.current, 0.3);
      run();
      return;
    }
    const pan = panRef.current;
    if (!pan) return;
    setView((v) => ({
      ...v,
      x: pan.vx + (event.clientX - pan.px),
      y: pan.vy + (event.clientY - pan.py),
    }));
  }

  function endPointer(event: ReactPointerEvent<SVGSVGElement>) {
    const drag = dragRef.current;
    if (drag) {
      // Hand-placed nodes stay put; springing back would undo the work.
      simsRef.current[drag.i].pinned = true;
      if (!drag.moved) onSelect(null);
      dragRef.current = null;
    }
    panRef.current = null;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function reset() {
    for (const s of simsRef.current) s.pinned = false;
    // Reset means "lay this out again from nothing", so remembered
    // positions have to go too or the old layout is simply re-settled.
    placedRef.current.clear();
    settledOnce.current = false;
    setView({ x: 0, y: 0, k: 1 });
    setSeedNonce((n) => n + 1);
  }

  if (nodes.length === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center p-8">
        <p className="max-w-sm text-center text-[13.5px] leading-relaxed text-ink-2">
          Nothing matches these filters. Turn a layer back on, or clear the
          source filter.
        </p>
      </div>
    );
  }

  // Edge labels become noise at low zoom and when there are many; show them
  // only where they can actually be read.
  const labelEdges = view.k > 0.75;
  const showDocLabels = view.k > 1.6;

  return (
    <div className="relative h-full w-full">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="h-full w-full touch-none select-none"
        style={{ cursor: panRef.current ? "grabbing" : "grab" }}
        role="img"
        aria-label={`Knowledge graph: ${nodes.length} nodes, ${edges.length} relations`}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endPointer}
        onPointerCancel={endPointer}
        onPointerLeave={() => setHoverId(null)}
      >
        <defs>
          <marker
            id="ge-arrow"
            viewBox="0 0 8 8"
            refX="7"
            refY="4"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M 0 1 L 8 4 L 0 7 z" fill="var(--line-strong)" />
          </marker>
        </defs>

        <g
          transform={`translate(${view.x} ${view.y}) translate(${CX} ${CY}) scale(${view.k}) translate(${-CX} ${-CY})`}
        >
          {edges.map((e) => {
            const a = simsRef.current[index.get(e.source) ?? -1];
            const b = simsRef.current[index.get(e.target) ?? -1];
            if (!a || !b) return null;
            const reversed = e.predicate === "REVERSED";
            const ontology = e.kind === "ontology";
            const structural = e.kind === "feeds" || e.kind === "contains";
            const dim = neighbours
              ? !(neighbours.has(e.source) && neighbours.has(e.target))
              : false;

            const srcNode = nodeById.get(e.source);
            const stroke = reversed
              ? "var(--red)"
              : ontology
                ? "var(--line-strong)"
                : structural
                  ? sourceColor(srcNode?.source_type)
                  : "var(--line)";
            const width = reversed ? 1.8 : ontology ? 1.4 : e.kind === "feeds" ? 1.6 : 0.6;
            const opacity = dim
              ? 0.05
              : reversed || ontology
                ? 0.95
                : e.kind === "feeds"
                  ? 0.5
                  : 0.22;
            return (
              <g key={e.id} opacity={opacity}>
                <line
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke={stroke}
                  strokeWidth={width}
                  strokeDasharray={reversed ? "5 3" : undefined}
                  markerEnd={ontology && !reversed ? "url(#ge-arrow)" : undefined}
                />
                {(ontology || reversed) && labelEdges && !dim ? (
                  <text
                    x={(a.x + b.x) / 2}
                    y={(a.y + b.y) / 2 - 4}
                    textAnchor="middle"
                    fill={reversed ? "var(--red)" : "var(--ink-3)"}
                    style={{ fontSize: 8, letterSpacing: 0.2 }}
                    className="pointer-events-none font-mono"
                  >
                    {e.predicate}
                    {e.corroborations && e.corroborations > 1
                      ? ` ×${e.corroborations}`
                      : ""}
                  </text>
                ) : null}
              </g>
            );
          })}

          {nodes.map((n) => {
            const i = index.get(n.id);
            if (i == null) return null;
            const s = simsRef.current[i];
            const selected = n.id === selectedId;
            const dim = neighbours ? !neighbours.has(n.id) : false;
            const r = radiusOf(n);
            const color = nodeColor(n);
            const superseded = n.validity === "superseded";
            const showLabel =
              n.kind === "source" ||
              n.kind === "container" ||
              n.kind === "entity" ||
              selected ||
              hoverId === n.id ||
              showDocLabels;

            return (
              <g
                key={n.id}
                transform={`translate(${s.x} ${s.y})`}
                opacity={dim ? 0.12 : 1}
                style={{ cursor: "pointer" }}
                onPointerEnter={() => setHoverId(n.id)}
                onPointerLeave={() => setHoverId(null)}
                onPointerDown={(event) => {
                  event.stopPropagation();
                  dragRef.current = { i, moved: false };
                  s.pinned = true;
                  svgRef.current?.setPointerCapture(event.pointerId);
                }}
                onPointerUp={(event) => {
                  if (dragRef.current && !dragRef.current.moved) {
                    event.stopPropagation();
                    onSelect(n.id);
                  }
                }}
                onDoubleClick={(event) => {
                  event.stopPropagation();
                  // Double-click isolates: the graph collapses to this
                  // node's neighborhood. Traversal, not search.
                  onFocus?.(focusId === n.id ? null : n.id);
                }}
              >
                <title>{n.label}</title>
                {n.kind === "source" ? (
                  <>
                    <circle
                      r={r}
                      fill={color}
                      fillOpacity={0.16}
                      stroke={color}
                      strokeWidth={selected ? 3 : 2}
                    />
                    <text
                      textAnchor="middle"
                      y={4}
                      fill={color}
                      style={{ fontSize: 11, fontWeight: 700 }}
                      className="pointer-events-none"
                    >
                      {n.doc_count ?? ""}
                    </text>
                  </>
                ) : n.kind === "container" ? (
                  <rect
                    x={-r}
                    y={-r * 0.62}
                    width={r * 2}
                    height={r * 1.24}
                    rx={3}
                    fill="var(--surface)"
                    stroke={color}
                    strokeWidth={selected ? 2.6 : 1.6}
                  />
                ) : n.kind === "doc" ? (
                  <rect
                    x={-r}
                    y={-r}
                    width={r * 2}
                    height={r * 2}
                    rx={1.5}
                    fill="var(--surface)"
                    stroke={selected ? "var(--ink)" : color}
                    strokeWidth={selected ? 2.2 : 1.1}
                    strokeDasharray={superseded ? "2 2" : undefined}
                    opacity={superseded ? 0.6 : 1}
                  />
                ) : (
                  <circle
                    r={r}
                    fill={color}
                    fillOpacity={n.unnamed ? 0.25 : 0.9}
                    stroke={selected ? "var(--ink)" : color}
                    strokeWidth={selected ? 2.5 : 1}
                    strokeDasharray={n.unnamed ? "2 2" : undefined}
                  />
                )}
                {showLabel ? (
                  <text
                    y={r + (n.kind === "source" ? 15 : 11)}
                    textAnchor="middle"
                    fill="var(--ink)"
                    style={{
                      fontSize: n.kind === "source" ? 12 : n.kind === "doc" ? 9 : 10,
                      fontWeight: n.kind === "source" ? 700 : selected ? 700 : 500,
                      paintOrder: "stroke",
                      stroke: "var(--page)",
                      strokeWidth: 3.5,
                      strokeLinejoin: "round",
                    }}
                    className="pointer-events-none"
                  >
                    {truncate(n.label, n.kind === "doc" ? 30 : 22)}
                  </text>
                ) : null}
              </g>
            );
          })}
        </g>
      </svg>

      <div className="pointer-events-none absolute right-2 top-2 flex flex-col items-end gap-1">
        <div className="pointer-events-auto flex overflow-hidden rounded-md border border-line bg-surface shadow-card">
          <ZoomBtn label="Zoom in" onClick={() => setView((v) => ({ ...v, k: Math.min(MAX_K, v.k * 1.25) }))}>
            +
          </ZoomBtn>
          <ZoomBtn label="Zoom out" onClick={() => setView((v) => ({ ...v, k: Math.max(MIN_K, v.k / 1.25) }))}>
            −
          </ZoomBtn>
          <ZoomBtn label="Reset layout" onClick={reset}>
            ⟲
          </ZoomBtn>
        </div>
        <span className="font-mono text-[10px] text-ink-3">
          {Math.round(view.k * 100)}%
        </span>
      </div>
    </div>
  );
}

function ZoomBtn({
  children,
  label,
  onClick,
}: {
  children: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="h-7 w-7 border-r border-line text-[13px] leading-none text-ink-2 last:border-r-0 hover:bg-page hover:text-ink"
    >
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ *
 * Controls
 * ------------------------------------------------------------------ */

export function GraphControls({
  slice,
  filters,
  onChange,
}: {
  slice: GraphSlice;
  filters: Filters;
  onChange: (f: Filters) => void;
}) {
  const counts = useMemo(() => {
    const layer: Record<string, number> = {};
    const source: Record<string, number> = {};
    const etype: Record<string, number> = {};
    for (const n of slice.nodes) {
      layer[n.kind] = (layer[n.kind] ?? 0) + 1;
      if (n.kind === "source" && n.source_type) {
        source[n.source_type] = n.doc_count ?? 0;
      }
      if (n.kind === "entity" && n.etype) etype[n.etype] = (etype[n.etype] ?? 0) + 1;
    }
    return { layer, source, etype };
  }, [slice]);

  function toggleLayer(kind: GraphNodeKind) {
    onChange({
      ...filters,
      layers: { ...filters.layers, [kind]: !filters.layers[kind] },
    });
  }
  function toggleSet(key: "sources" | "etypes", value: string) {
    const next = new Set(filters[key]);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    onChange({ ...filters, [key]: next });
  }

  const etypes = Object.keys(counts.etype).sort();
  const sources = Object.keys(counts.source).sort();

  return (
    <div className="space-y-2.5">
      <Row label="Layers">
        {LAYER_ORDER.map((kind) => (
          <Chip
            key={kind}
            on={filters.layers[kind]}
            onClick={() => toggleLayer(kind)}
            count={counts.layer[kind] ?? 0}
          >
            {LAYER_LABEL[kind]}
          </Chip>
        ))}
      </Row>

      {sources.length > 0 ? (
        <Row label="Sources">
          {sources.map((s) => (
            <Chip
              key={s}
              on={filters.sources.size === 0 || filters.sources.has(s)}
              dot={sourceColor(s)}
              onClick={() => toggleSet("sources", s)}
              count={counts.source[s]}
            >
              {s}
            </Chip>
          ))}
          {filters.sources.size > 0 ? (
            <button
              type="button"
              onClick={() => onChange({ ...filters, sources: new Set() })}
              className="text-[11px] text-ink-3 underline-offset-2 hover:text-ink hover:underline"
            >
              clear
            </button>
          ) : null}
        </Row>
      ) : null}

      {etypes.length > 0 ? (
        <Row label="Entity types">
          {etypes.map((t) => (
            <Chip
              key={t}
              on={filters.etypes.size === 0 || filters.etypes.has(t)}
              dot={ETYPE_COLOR[t] ?? ENTITY_FALLBACK}
              onClick={() => toggleSet("etypes", t)}
              count={counts.etype[t]}
            >
              {t.toLowerCase()}
            </Chip>
          ))}
          {filters.etypes.size > 0 ? (
            <button
              type="button"
              onClick={() => onChange({ ...filters, etypes: new Set() })}
              className="text-[11px] text-ink-3 underline-offset-2 hover:text-ink hover:underline"
            >
              clear
            </button>
          ) : null}
        </Row>
      ) : null}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="mr-0.5 w-[86px] shrink-0 font-mono text-[10px] uppercase tracking-wide text-ink-3">
        {label}
      </span>
      {children}
    </div>
  );
}

function Chip({
  children,
  on,
  dot,
  count,
  onClick,
}: {
  children: React.ReactNode;
  on: boolean;
  dot?: string;
  count?: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      className={cn(
        "flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11.5px] transition-colors",
        on
          ? "border-line-strong bg-surface text-ink"
          : "border-line bg-transparent text-ink-3 opacity-60 hover:opacity-100",
      )}
    >
      {dot ? (
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ background: dot, opacity: on ? 1 : 0.4 }}
        />
      ) : null}
      {children}
      {count != null ? (
        <span className="font-mono text-[10px] text-ink-3">{count}</span>
      ) : null}
    </button>
  );
}

/* ------------------------------------------------------------------ *
 * Inspector
 * ------------------------------------------------------------------ */

export function GraphInspector({
  slice,
  selectedId,
  onSelect,
  onFocus,
}: {
  slice: GraphSlice | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onFocus?: (id: string) => void;
}) {
  const nodeById = useMemo(
    () => new Map((slice?.nodes ?? []).map((n) => [n.id, n])),
    [slice],
  );
  const node = selectedId ? nodeById.get(selectedId) : null;

  if (!node) return null;

  const incident = (slice?.edges ?? []).filter(
    (e) => e.source === node.id || e.target === node.id,
  );
  const other = (e: GraphEdge) => (e.source === node.id ? e.target : e.source);
  const claims = incident.filter(
    (e) => e.kind === "ontology" || e.predicate === "REVERSED",
  );
  const docs = incident.filter((e) => e.kind === "mentions" || e.kind === "authored");
  const children = incident.filter(
    (e) => (e.kind === "feeds" || e.kind === "contains") && e.source === node.id,
  );

  // Where this node sits in the provenance chain, walked upward.
  const trail: GraphNode[] = [];
  if (node.kind === "doc" || node.kind === "container") {
    const containerEdge = incident.find(
      (e) => e.kind === "contains" && e.target === node.id,
    );
    const container =
      node.kind === "container"
        ? node
        : containerEdge
          ? nodeById.get(containerEdge.source)
          : undefined;
    const source = node.source_type
      ? nodeById.get(`source::${node.source_type}`)
      : undefined;
    if (source) trail.push(source);
    if (container && container.id !== node.id) trail.push(container);
  }

  return (
    <div className="space-y-3">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-wide text-ink-3">
          {node.kind === "entity"
            ? node.etype ?? "entity"
            : node.kind === "source"
              ? "connector"
              : node.kind === "container"
                ? "repo / channel"
                : node.artifact_class || node.source_type || "document"}
        </p>
        <h2 className="mt-0.5 text-[15px] font-semibold leading-snug text-ink">
          {node.label}
        </h2>
        {onFocus ? (
          <button
            type="button"
            onClick={() => onFocus(node.id)}
            className="mt-1 text-[12px] text-accent-ink underline-offset-2 hover:underline"
          >
            Isolate
          </button>
        ) : null}
        {node.doc_count != null ? (
          <p className="mt-0.5 text-[12px] text-ink-2">
            {node.doc_count.toLocaleString()} docs
          </p>
        ) : null}
        {node.timestamp ? (
          <p className="mt-0.5 font-mono text-[11px] text-ink-3">
            {node.timestamp.slice(0, 10)}
          </p>
        ) : null}
        {node.validity === "superseded" ? (
          <p className="mt-1 text-[12px] text-ink-3">superseded</p>
        ) : null}
      </div>

      {trail.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1 border-t border-line pt-2.5">
          {trail.map((t) => (
            <span key={t.id} className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => onSelect(t.id)}
                className="rounded-full bg-inset px-2 py-0.5 text-[11.5px] text-ink hover:bg-hover"
              >
                {t.label}
              </button>
              <span className="text-ink-3">›</span>
            </span>
          ))}
          <span className="text-[11.5px] font-medium text-ink-2">{node.label}</span>
        </div>
      ) : null}

      {claims.length > 0 ? (
        <Section title={`${claims.length} claim${claims.length === 1 ? "" : "s"}`}>
          <ul className="space-y-2">
            {claims.map((e) => {
              const neighbor = nodeById.get(other(e));
              const outgoing = e.source === node.id;
              return (
                <li key={e.id} className="text-[12.5px] leading-snug text-ink-2">
                  <span
                    className={cn(
                      "font-mono text-[11px]",
                      e.predicate === "REVERSED" ? "text-red" : "text-ink-3",
                    )}
                  >
                    {outgoing ? "" : "← "}
                    {e.predicate}
                    {outgoing ? " →" : ""}
                  </span>{" "}
                  <button
                    type="button"
                    onClick={() => neighbor && onSelect(neighbor.id)}
                    className="underline-offset-2 hover:text-ink hover:underline"
                  >
                    {neighbor?.label ?? other(e)}
                  </button>
                  {e.corroborations && e.corroborations > 1 ? (
                    <span className="ml-1 text-[11px] text-ink-3">
                      ({e.corroborations} sources)
                    </span>
                  ) : null}
                  {e.ctx ? (
                    <span className="mt-0.5 block text-[12px] text-ink-3">{e.ctx}</span>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </Section>
      ) : null}

      {docs.length > 0 ? (
        <Section title={`${docs.length} document${docs.length === 1 ? "" : "s"}`}>
          <ul className="space-y-1">
            {docs.slice(0, 12).map((e) => {
              const neighbor = nodeById.get(other(e));
              return (
                <li key={e.id} className="truncate text-[12px]">
                  <button
                    type="button"
                    onClick={() => neighbor && onSelect(neighbor.id)}
                    className="truncate text-ink-2 underline-offset-2 hover:text-ink hover:underline"
                  >
                    {neighbor?.label ?? other(e)}
                  </button>
                </li>
              );
            })}
          </ul>
        </Section>
      ) : null}

      {children.length > 0 ? (
        <Section
          title={`${children.length} ${node.kind === "source" ? "container" : "document"}${
            children.length === 1 ? "" : "s"
          } here`}
        >
          <ul className="space-y-1">
            {children.slice(0, 12).map((e) => {
              const neighbor = nodeById.get(other(e));
              return (
                <li key={e.id} className="truncate text-[12px]">
                  <button
                    type="button"
                    onClick={() => neighbor && onSelect(neighbor.id)}
                    className="truncate text-ink-2 underline-offset-2 hover:text-ink hover:underline"
                  >
                    {neighbor?.label ?? other(e)}
                  </button>
                </li>
              );
            })}
          </ul>
        </Section>
      ) : null}

      {node.url ? (
        <a
          href={node.url}
          target="_blank"
          rel="noreferrer"
          className="inline-block text-[13px] text-accent-ink underline-offset-2 hover:underline"
        >
          Open source
        </a>
      ) : null}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-line pt-2.5">
      <p className="mb-1.5 font-mono text-[10px] uppercase tracking-wide text-ink-3">
        {title}
      </p>
      {children}
    </div>
  );
}
