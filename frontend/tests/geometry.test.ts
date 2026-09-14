import { describe, expect, it } from "vitest";
import {
  editPlacement,
  fitView,
  toMap,
  zoomAt,
  sectorPath,
} from "../src/geometry";
const map = {
  id: 1,
  name: "Test",
  width: 2000,
  height: 1000,
  mime_type: "image/png",
};
const p = {
  camera_id: 1,
  x: 0.5,
  y: 0.5,
  direction: 0,
  view_angle: 90,
  view_distance: 0.1,
};
describe("map geometry", () => {
  it("fits the entire image with padding", () => {
    const v = fitView(map, 1000, 600);
    expect(v.scale * map.width).toBeLessThan(1000);
    expect(v.scale * map.height).toBeLessThan(600);
    expect(v.x).toBeGreaterThan(0);
  });
  it("keeps the cursor anchor at the same map coordinate through zoom", () => {
    const v = fitView(map, 1000, 600),
      a = { x: 700, y: 200 };
    const before = toMap(a, v, map),
      after = toMap(a, zoomAt(v, a, v.scale * 8), map);
    expect(after.x).toBeCloseTo(before.x);
    expect(after.y).toBeCloseTo(before.y);
  });
  it("retains precision at different scales and pan offsets", () => {
    for (const scale of [0.25, 1, 8]) {
      const v = { x: -410, y: 57, scale };
      const p = toMap(
        {
          x: v.x + 0.12345 * map.width * scale,
          y: v.y + 0.67891 * map.height * scale,
        },
        v,
        map,
      );
      expect(p.x).toBeCloseTo(0.12345, 10);
      expect(p.y).toBeCloseTo(0.67891, 10);
    }
  });
  it("uses image aspect ratio for direction and field of view", () => {
    const aim = editPlacement(p, { x: 0.6, y: 0.5 }, "aim", map);
    expect(aim.direction).toBe(90);
    expect(aim.view_distance).toBeCloseTo(0.1);
    expect(
      editPlacement(aim, { x: 0.6, y: 0.7 }, "angle", map).view_angle,
    ).toBeCloseTo(90);
  });
  it("clamps placement to image bounds and preserves source state", () => {
    expect(editPlacement(p, { x: 2, y: -1 }, "move", map)).toMatchObject({
      x: 1,
      y: 0,
    });
    expect(p.x).toBe(0.5);
  });
  it("renders full-circle coverage without a degenerate arc", () => {
    expect(sectorPath({ ...p, view_angle: 360 }, map)).toContain("a 200 200");
  });
});
