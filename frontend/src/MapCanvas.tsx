import { useCallback, useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import {
  Camera as CameraIcon,
  Minus,
  Plus,
  Maximize,
  Hand,
  MousePointer2,
  RotateCcw,
  LoaderCircle,
  Layers,
  X,
  Crosshair,
} from "lucide-react";
import { api, message } from "./api";
import {
  clamp,
  editPlacement,
  fitView,
  sectorPath,
  sectorPoint,
  toMap,
  zoomAt,
} from "./geometry";
import type { Camera, Placement, Point, SiteMap, View } from "./types";
import { Snapshot } from "./Snapshot";

type Drag = {
  mode: "pan" | "move" | "aim" | "angle" | "place";
  id: number;
  start: Point;
  view: View;
  original?: Placement;
  moved: boolean;
};
export function MapCanvas({
  map,
  cameras,
  selected,
  onSelect,
  onCount,
  onBusy,
}: {
  map: SiteMap;
  cameras: Camera[];
  selected: number | null;
  onSelect: (id: number | null) => void;
  onCount: (ids: number[]) => void;
  onBusy: (busy: boolean) => void;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState({ width: 1000, height: 700 });
  const [view, setView] = useState<View>({ x: 0, y: 0, scale: 1 });
  const viewRef = useRef(view);
  viewRef.current = view;
  const [placements, setPlacements] = useState<Placement[]>([]);
  const [draft, setDraft] = useState<Placement | null>(null);
  const draftRef = useRef<Placement | null>(null);
  const [loading, setLoading] = useState(true);
  const [imageReady, setImageReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("All changes saved");
  const [panMode, setPanMode] = useState(false);
  const space = useRef(false);
  const [coverage, setCoverage] = useState(true);
  const [hover, setHover] = useState<{
    id: number;
    label: string;
    x: number;
    y: number;
  } | null>(null);
  const drag = useRef<Drag | null>(null);
  const [dragging, setDragging] = useState(false);
  const fitScale = fitView(map, size.width, size.height).scale;
  const setWorking = (value: boolean) => {
    busyRef.current = value;
    setBusy(value);
    onBusy(value);
  };
  useEffect(() => () => onBusy(false), [onBusy]);
  const load = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setError("");
      try {
        const data = await api<Placement[]>(`/maps/${map.id}/placements`, {
          signal,
        });
        if (!signal?.aborted) {
          setPlacements(data);
          onCount(data.map((p) => p.camera_id));
        }
      } catch (e) {
        if (!signal?.aborted) setError(message(e));
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [map.id, onCount],
  );
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);
  useEffect(() => {
    const node = viewport.current!;
    let previous: { width: number; height: number } | null = null;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      if (!width || !height) { setHover(null); return; }
      if (previous) {
        const dx = (width - previous.width) / 2,
          dy = (height - previous.height) / 2;
        setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
      } else setView(fitView(map, width, height));
      previous = { width, height };
      setSize({ width, height });
      setHover(null);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [map]);
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (
        e.code === "Space" &&
        !["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(
          (e.target as HTMLElement).tagName,
        )
      ) {
        e.preventDefault();
        space.current = true;
      }
    };
    const up = (e: KeyboardEvent) => {
      if (e.code === "Space") space.current = false;
    };
    const blur = () => {
      space.current = false;
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", blur);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", blur);
    };
  }, []);
  useEffect(() => {
    const node = viewport.current!;
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      if (drag.current) return;
      const rect = node.getBoundingClientRect();
      const current = viewRef.current;
      const scale = clamp(
        current.scale *
          Math.exp(-event.deltaY * (event.deltaMode === 1 ? 0.035 : 0.0015)),
        fitScale * 0.25,
        fitScale * 32,
      );
      setView(
        zoomAt(
          current,
          { x: event.clientX - rect.left, y: event.clientY - rect.top },
          scale,
        ),
      );
      setHover(null);
    };
    node.addEventListener("wheel", wheel, { passive: false });
    return () => node.removeEventListener("wheel", wheel);
  }, [fitScale]);
  const position = (e: { clientX: number; clientY: number }) => {
    const r = viewport.current!.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  const updateDraft = (p: Placement | null) => {
    draftRef.current = p;
    setDraft(p);
  };
  const start = (e: ReactPointerEvent, mode: Drag["mode"], p?: Placement) => {
    if (
      (e.button !== 0 && e.button !== 1) ||
      loading ||
      !imageReady ||
      busyRef.current ||
      drag.current ||
      error
    )
      return;
    e.preventDefault();
    e.stopPropagation();
    setHover(null);
    if (space.current || e.button === 1 || panMode) mode = "pan";
    if (p && mode !== "pan") onSelect(p.camera_id);
    drag.current = {
      mode,
      id: e.pointerId,
      start: position(e),
      view: viewRef.current,
      original: p,
      moved: false,
    };
    svg.current!.setPointerCapture(e.pointerId);
    setDragging(true);
  };
  const background = (e: ReactPointerEvent) => {
    const p = toMap(position(e), view, map);
    const unplaced =
      selected !== null && !placements.some((p) => p.camera_id === selected);
    start(
      e,
      unplaced && p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1
        ? "place"
        : "pan",
    );
  };
  const move = (e: ReactPointerEvent) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    const current = position(e),
      dx = current.x - d.start.x,
      dy = current.y - d.start.y;
    if (Math.hypot(dx, dy) > 3) d.moved = true;
    if (!d.moved) return;
    if (d.mode === "pan" || d.mode === "place") {
      setView({ ...d.view, x: d.view.x + dx, y: d.view.y + dy });
      return;
    }
    if (!d.original) return;
    const point =
      d.mode === "move"
        ? {
            x: d.original.x + dx / (d.view.scale * map.width),
            y: d.original.y + dy / (d.view.scale * map.height),
          }
        : toMap(current, d.view, map);
    updateDraft(editPlacement(d.original, point, d.mode, map));
  };
  const save = async (p: Placement) => {
    setWorking(true);
    setError("");
    setStatus("Saving placement…");
    try {
      const { x, y, direction, view_angle, view_distance } = p;
      const saved = await api<Placement>(
        `/maps/${map.id}/placements/${p.camera_id}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ x, y, direction, view_angle, view_distance }),
        },
      );
      const next = [
        ...placements.filter((item) => item.camera_id !== p.camera_id),
        saved,
      ];
      setPlacements(next);
      onCount(next.map((p) => p.camera_id));
      setStatus("All changes saved");
    } catch (e) {
      setError(`${message(e)} Reload the map to verify the saved position.`);
      setStatus("Save not confirmed");
    } finally {
      updateDraft(null);
      setWorking(false);
    }
  };
  const end = (e: ReactPointerEvent) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    drag.current = null;
    setDragging(false);
    if (svg.current?.hasPointerCapture(e.pointerId))
      svg.current.releasePointerCapture(e.pointerId);
    if (d.mode === "place" && !d.moved && selected !== null) {
      const point = toMap(position(e), viewRef.current, map);
      const p = {
        camera_id: selected,
        x: clamp(point.x, 0, 1),
        y: clamp(point.y, 0, 1),
        direction: 0,
        view_angle: 90,
        view_distance: 0.12,
      };
      updateDraft(p);
      void save(p);
    } else if (d.moved && draftRef.current) void save(draftRef.current);
  };
  const cancel = () => {
    drag.current = null;
    setDragging(false);
    updateDraft(null);
  };
  const remove = async (id: number) => {
    if (busyRef.current) return;
    setWorking(true);
    setHover(null);
    setError("");
    try {
      await api(`/maps/${map.id}/placements/${id}`, { method: "DELETE" });
      const next = placements.filter((p) => p.camera_id !== id);
      setPlacements(next);
      onCount(next.map((p) => p.camera_id));
      setStatus("Camera removed from map");
    } catch (e) {
      setError(message(e));
    } finally {
      setWorking(false);
    }
  };
  const zoom = (factor: number) => {
    if (drag.current) return;
    setHover(null);
    setView((v) =>
      zoomAt(
        v,
        { x: size.width / 2, y: size.height / 2 },
        clamp(v.scale * factor, fitScale * 0.25, fitScale * 32),
      ),
    );
  };
  const all = [
    ...placements.filter((p) => p.camera_id !== draft?.camera_id),
    ...(draft ? [draft] : []),
  ];
  const chosen = all.find((p) => p.camera_id === selected);
  return (
    <div className="map-editor">
      <div className="map-stage" ref={viewport} data-testid="map-stage">
        <svg
          ref={svg}
          className={`map-svg ${panMode ? "pan" : ""} ${dragging ? "dragging" : ""}`}
          width="100%"
          height="100%"
          onPointerDown={background}
          onPointerMove={move}
          onPointerUp={end}
          onPointerCancel={cancel}
          onLostPointerCapture={() => {
            if (drag.current) cancel();
          }}
          onContextMenu={(e) => e.preventDefault()}
          aria-label={`${map.name} interactive camera map`}
        >
          <g transform={`translate(${view.x} ${view.y}) scale(${view.scale})`}>
            <image
              href={`/maps/${map.id}/image`}
              width={map.width}
              height={map.height}
              onLoad={() => setImageReady(true)}
              onError={() =>
                setError(
                  "The map image could not be loaded. Refresh to try again.",
                )
              }
              data-testid="map-image"
            />
            {coverage &&
              all.map((p) => (
                <g key={p.camera_id} pointerEvents="none">
                  <path
                    d={sectorPath(p, map)}
                    fill={p.camera_id === selected ? "#d6a45c" : "#65a0b4"}
                    fillOpacity={p.camera_id === selected ? 0.4 : 0.25}
                    stroke="#fff"
                    strokeOpacity=".75"
                    strokeWidth="4"
                    vectorEffect="non-scaling-stroke"
                  />
                  <path
                    d={sectorPath(p, map)}
                    fill="none"
                    stroke={p.camera_id === selected ? "#a66b22" : "#377486"}
                    strokeWidth="1.5"
                    vectorEffect="non-scaling-stroke"
                  />
                </g>
              ))}
          </g>
          {all.map((p) => {
            const x = view.x + p.x * map.width * view.scale,
              y = view.y + p.y * map.height * view.scale;
            const camera = cameras.find((c) => c.id === p.camera_id),
              label = camera?.ip || `Camera ${p.camera_id}`;
            const active = p.camera_id === selected;
            return (
              <g key={p.camera_id}>
                <g
                  transform={`translate(${x} ${y})`}
                  role="button"
                  tabIndex={0}
                  aria-label={`Camera ${label}`}
                  data-testid={`marker-${p.camera_id}`}
                  className={`camera-marker ${active ? "selected" : ""}`}
                  onPointerDown={(e) => start(e, "move", p)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") onSelect(p.camera_id);
                  }}
                  onPointerEnter={(e) => {
                    if (!drag.current && !busy)
                      setHover({
                        id: p.camera_id,
                        label,
                        x: e.clientX,
                        y: e.clientY,
                      });
                  }}
                  onPointerLeave={() => setHover(null)}
                  onFocus={(e) => {
                    const r = e.currentTarget.getBoundingClientRect();
                    setHover({ id: p.camera_id, label, x: r.x, y: r.y });
                  }}
                  onBlur={() => setHover(null)}
                >
                  <circle r="19" />
                  <CameraIcon x={-10} y={-10} width={20} height={20} />
                  <rect
                    x="-53"
                    y="27"
                    width="106"
                    height="22"
                    rx="5"
                    className="marker-label-bg"
                  />
                  <text y="42" textAnchor="middle" className="marker-label">
                    {label}
                  </text>
                </g>
                {active &&
                  coverage &&
                  [
                    ["angle", -p.view_angle / 2],
                    ["angle", p.view_angle / 2],
                    ["aim", 0],
                  ].map(([mode, offset], i) => {
                    const point = sectorPoint(p, map, Number(offset));
                    const hx = clamp(
                        view.x + point.x * view.scale,
                        16,
                        size.width - 16,
                      ),
                      hy = clamp(
                        view.y + point.y * view.scale,
                        16,
                        size.height - 16,
                      );
                    return (
                      <g
                        key={i}
                        transform={`translate(${hx} ${hy})`}
                        className={`sector-handle ${mode}`}
                        onPointerDown={(e) =>
                          start(e, mode as "angle" | "aim", p)
                        }
                        data-testid={`handle-${mode}-${i}`}
                      >
                        <title>
                          {mode === "aim"
                            ? "Drag to adjust direction and range"
                            : "Drag to adjust field of view"}
                        </title>
                        <circle r="9" />
                        <circle r="3" fill="currentColor" />
                      </g>
                    );
                  })}
                {active && (
                  <g
                    transform={`translate(${clamp(x + 32, 16, size.width - 16)} ${clamp(y - 30, 16, size.height - 16)})`}
                    className="remove-marker"
                    role="button"
                    tabIndex={0}
                    aria-label="Remove camera from map"
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={() => void remove(p.camera_id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void remove(p.camera_id);
                    }}
                  >
                    <circle r="11" />
                    <X x={-7} y={-7} width={14} height={14} />
                  </g>
                )}
              </g>
            );
          })}
        </svg>
        <div className="canvas-top">
          <span className="canvas-chip">
            <i className="dot" />
            {map.name}
          </span>
          <span className="canvas-chip subtle">
            {map.width.toLocaleString("en-GB")} ×{" "}
            {map.height.toLocaleString("en-GB")}
          </span>
        </div>
        <div className="canvas-tools">
          <button
            className={!panMode ? "active" : ""}
            title="Select and place cameras"
            aria-label="Select tool"
            onClick={() => setPanMode(false)}
          >
            <MousePointer2 size={18} />
          </button>
          <button
            className={panMode ? "active" : ""}
            title="Pan map (or hold Space)"
            aria-label="Pan tool"
            onClick={() => setPanMode(true)}
          >
            <Hand size={18} />
          </button>
          <div className="tool-divider" />
          <button
            className={coverage ? "active" : ""}
            title="Toggle coverage sectors"
            aria-label="Toggle coverage"
            aria-pressed={coverage}
            onClick={() => setCoverage((v) => !v)}
          >
            <Layers size={18} />
          </button>
        </div>
        <div className="zoom-tools">
          <button aria-label="Zoom out" onClick={() => zoom(1 / 1.3)}>
            <Minus size={17} />
          </button>
          <span data-testid="zoom-level">
            {Math.round((view.scale / fitScale) * 100)}%
          </span>
          <button aria-label="Zoom in" onClick={() => zoom(1.3)}>
            <Plus size={17} />
          </button>
          <div className="tool-divider" />
          <button
            aria-label="Fit map"
            title="Fit map"
            onClick={() => {
              setView(fitView(map, size.width, size.height));
              setHover(null);
            }}
          >
            <Maximize size={17} />
          </button>
        </div>
        <div className="canvas-hint">
          {selected !== null && !chosen ? (
            <>
              <Crosshair size={14} /> Click the map to place the selected camera
            </>
          ) : (
            <>
              <MousePointer2 size={14} /> Scroll to zoom <span>·</span> Drag
              background to pan <span>·</span> Hover a camera to preview
            </>
          )}
        </div>
        {(loading || !imageReady) && !error && (
          <div className="canvas-loading">
            <LoaderCircle className="spin" /> Loading workspace…
          </div>
        )}
        {error && (
          <div className="canvas-error" role="alert">
            <span>{error}</span>
            <button
              onClick={() => {
                setImageReady(false);
                void load();
                const image = svg.current?.querySelector("image");
                image?.setAttribute(
                  "href",
                  `/maps/${map.id}/image?t=${Date.now()}`,
                );
              }}
            >
              <RotateCcw size={14} /> Reload map
            </button>
          </div>
        )}
        {hover && (
          <Snapshot
            key={hover.id}
            cameraId={hover.id}
            label={hover.label}
            x={hover.x}
            y={hover.y}
          />
        )}
      </div>
      <div className="canvas-footer">
        <span>
          <i className={`dot ${busy ? "pending" : ""}`} />
          {busy ? "Saving…" : status}
        </span>
        <span>
          {chosen
            ? `${Math.round(chosen.direction)}° direction · ${Math.round(chosen.view_angle)}° field of view`
            : `${placements.length} cameras placed`}{" "}
          <span className="footer-divider">/</span> ONVIF workspace
        </span>
      </div>
    </div>
  );
}
