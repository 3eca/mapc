import type { Placement, Point, SiteMap, View } from "./types";
export const clamp = (n: number, min: number, max: number) =>
  Math.max(min, Math.min(max, n));
export function fitView(map: SiteMap, width: number, height: number): View {
  const scale = Math.max(
    0.00001,
    Math.min((width - 96) / map.width, (height - 96) / map.height),
  );
  return {
    scale,
    x: (width - map.width * scale) / 2,
    y: (height - map.height * scale) / 2,
  };
}
export function zoomAt(view: View, anchor: Point, scale: number): View {
  return {
    scale,
    x: anchor.x - ((anchor.x - view.x) * scale) / view.scale,
    y: anchor.y - ((anchor.y - view.y) * scale) / view.scale,
  };
}
export function toMap(point: Point, view: View, map: SiteMap): Point {
  return {
    x: (point.x - view.x) / (view.scale * map.width),
    y: (point.y - view.y) / (view.scale * map.height),
  };
}
export function editPlacement(
  p: Placement,
  point: Point,
  mode: "move" | "aim" | "angle",
  map: SiteMap,
): Placement {
  if (mode === "move")
    return { ...p, x: clamp(point.x, 0, 1), y: clamp(point.y, 0, 1) };
  const dx = (point.x - p.x) * map.width,
    dy = (point.y - p.y) * map.height;
  const direction = ((Math.atan2(dx, -dy) * 180) / Math.PI + 360) % 360;
  if (mode === "aim")
    return {
      ...p,
      direction,
      view_distance: clamp(Math.hypot(dx, dy) / map.width, 0.001, 2),
    };
  const delta = ((direction - p.direction + 540) % 360) - 180;
  return { ...p, view_angle: clamp(Math.abs(delta) * 2, 1, 360) };
}
export function sectorPath(p: Placement, map: SiteMap) {
  const x = p.x * map.width,
    y = p.y * map.height,
    r = p.view_distance * map.width;
  const a = sectorPoint(p, map, -p.view_angle / 2),
    b = sectorPoint(p, map, p.view_angle / 2);
  if (p.view_angle >= 359.99)
    return `M ${x - r} ${y} a ${r} ${r} 0 1 0 ${r * 2} 0 a ${r} ${r} 0 1 0 ${-r * 2} 0`;
  return `M ${x} ${y} L ${a.x} ${a.y} A ${r} ${r} 0 ${p.view_angle > 180 ? 1 : 0} 1 ${b.x} ${b.y} Z`;
}
export function sectorPoint(p: Placement, map: SiteMap, offset = 0): Point {
  const a = ((p.direction + offset) * Math.PI) / 180,
    r = p.view_distance * map.width;
  return {
    x: p.x * map.width + r * Math.sin(a),
    y: p.y * map.height - r * Math.cos(a),
  };
}
