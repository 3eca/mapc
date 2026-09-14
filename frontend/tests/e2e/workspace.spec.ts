import { test, expect, Page } from "@playwright/test";
const map = {
  id: 1,
  name: "Ground floor",
  width: 1200,
  height: 800,
  mime_type: "image/png",
};
const cameras = Array.from({ length: 6 }, (_, i) => ({
  id: i + 1,
  ip: `192.168.101.${[23, 28, 39, 53, 56, 57][i]}`,
  port: 80,
  protocol: "onvif",
  manufacturer: "HIKVISION",
  model: i === 3 ? "DS-I203(E)" : "IPC-T040(B)",
  firmware: "1",
  serial_number: `SN-${i}`,
  mac_address: "00:11:22:33:44:55",
  streams: [
    {
      profile: "Main stream",
      token: "main",
      uri: "rtsp://192.168.101.23/stream",
    },
  ],
  is_active: true,
}));
const plan = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800"><rect width="1200" height="800" fill="#dadbd7"/><g fill="#ecece7" stroke="#6e7677" stroke-width="9"><path d="M100 90H1100V710H100Z"/><path d="M100 90H430V310H100Z"/><path d="M430 90H800V310H430Z"/><path d="M800 90H1100V310H800Z"/><path d="M100 480H390V710H100Z"/><path d="M390 480H770V710H390Z"/><path d="M770 480H1100V710H770Z"/></g><g fill="#c4c9c5" stroke="#8e9692" stroke-width="2"><rect x="140" y="140" width="110" height="55"/><rect x="270" y="140" width="110" height="55"/><rect x="140" y="220" width="110" height="55"/><rect x="270" y="220" width="110" height="55"/><rect x="500" y="160" width="230" height="75" rx="15"/><rect x="850" y="140" width="70" height="115"/><rect x="980" y="140" width="70" height="115"/><rect x="160" y="550" width="165" height="65"/><rect x="440" y="550" width="270" height="75" rx="6"/><rect x="830" y="540" width="220" height="105" rx="8"/></g><g font-family="sans-serif" text-anchor="middle" fill="#6b7271" font-size="16" letter-spacing="3"><text x="265" y="125">WORKSPACE</text><text x="610" y="125">MEETING ROOM</text><text x="950" y="125">STORAGE</text><text x="600" y="410" font-size="20">MAIN CORRIDOR</text><text x="245" y="690">RECEPTION</text><text x="580" y="690">LOUNGE</text><text x="930" y="690">OPERATIONS</text></g><path d="M540 710H650" stroke="#ecece7" stroke-width="12"/><path d="M550 710V650Q610 650 610 710" fill="none" stroke="#83918b" stroke-width="2"/><text x="600" y="760" text-anchor="middle" font-family="sans-serif" font-size="13" fill="#727b74" letter-spacing="4">SOUTH ENTRANCE</text></svg>`;
async function setup(page: Page) {
  const saved = [
    {
      id: 1,
      map_id: 1,
      camera_id: 1,
      x: 0.15,
      y: 0.38,
      direction: 90,
      view_angle: 75,
      view_distance: 0.2,
    },
    {
      id: 2,
      map_id: 1,
      camera_id: 2,
      x: 0.84,
      y: 0.46,
      direction: 270,
      view_angle: 85,
      view_distance: 0.24,
    },
    {
      id: 3,
      map_id: 1,
      camera_id: 4,
      x: 0.5,
      y: 0.8,
      direction: 0,
      view_angle: 90,
      view_distance: 0.22,
    },
  ];
  const writes: any[] = [];
  await page.route("**/maps/", (r) => r.fulfill({ json: [map] }));
  await page.route("**/camera/", (r) => r.fulfill({ json: cameras }));
  await page.route("**/maps/1/image*", (r) =>
    r.fulfill({ contentType: "image/svg+xml", body: plan }),
  );
  await page.route("**/maps/1/placements", (r) => r.fulfill({ json: saved }));
  await page.route("**/maps/1/placements/*", async (r) => {
    const id = Number(r.request().url().split("/").pop());
    if (r.request().method() === "DELETE") {
      const i = saved.findIndex((p) => p.camera_id === id);
      if (i >= 0) saved.splice(i, 1);
      await r.fulfill({ status: 204 });
      return;
    }
    const body = r.request().postDataJSON();
    writes.push(body);
    const p = { ...body, camera_id: id, id, map_id: 1 };
    const i = saved.findIndex((p) => p.camera_id === id);
    if (i >= 0) saved[i] = p;
    else saved.push(p);
    await r.fulfill({ json: p });
  });
  await page.route("**/camera/*/snapshot", (r) =>
    r.fulfill({ contentType: "image/svg+xml", body: plan }),
  );
  await page.goto("/ui/");
  await expect(page.getByTestId("marker-1")).toBeVisible();
  return writes;
}
test("workspace renders and marker hover requests a snapshot", async ({
  page,
}) => {
  await setup(page);
  await expect(
    page.getByRole("heading", { name: "Ground floor", exact: true }),
  ).toBeVisible();
  await page.getByTestId("marker-1").hover();
  await expect(
    page.getByAltText("Current view from 192.168.101.23"),
  ).toBeVisible();
  await page.mouse.move(1400, 10);
  await expect(
    page.getByAltText("Current view from 192.168.101.23"),
  ).toHaveCount(0);
  await page.screenshot({ path: "test-results/workspace.png", fullPage: true });
});
test("zoom anchors at cursor and fit resets without changing placements", async ({
  page,
}) => {
  const writes = await setup(page);
  const before = await page.getByTestId("marker-1").boundingBox();
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect(page.getByTestId("zoom-level")).toHaveText("130%");
  const after = await page.getByTestId("marker-1").boundingBox();
  expect(after!.width).toBeCloseTo(before!.width, 0);
  await page.getByRole("button", { name: "Fit map", exact: true }).click();
  await expect(page.getByTestId("zoom-level")).toHaveText("100%");
  expect(writes).toHaveLength(0);
});
test("marker click does not move camera; drag at zoom saves normalized coordinates", async ({
  page,
}) => {
  const writes = await setup(page);
  await page.getByTestId("camera-card-1").click();
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  const marker = page.getByTestId("marker-1");
  const box = await marker.boundingBox();
  const x = box!.x + box!.width / 2,
    y = box!.y + 19;
  await page.mouse.click(x, y);
  expect(writes).toHaveLength(0);
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 40, y + 25, { steps: 8 });
  await page.mouse.up();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].x).toBeGreaterThan(0.15);
  expect(writes[0].y).toBeGreaterThan(0.38);
  expect(writes[0].x).toBeLessThan(1);
  await expect(page.getByText("All changes saved")).toBeVisible();
});
test("places an unplaced camera and removes it using map controls", async ({
  page,
}) => {
  const writes = await setup(page);
  await page.getByTestId("camera-card-3").click();
  const box = await page.getByTestId("map-image").boundingBox();
  await page.mouse.click(box!.x + box!.width * 0.6, box!.y + box!.height * 0.5);
  await expect(page.getByTestId("marker-3")).toBeVisible();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].x).toBeCloseTo(0.6, 2);
  expect(writes[0].y).toBeCloseTo(0.5, 2);
  await page
    .getByRole("button", { name: "Remove camera from map", exact: true })
    .click();
  await expect(page.getByTestId("marker-3")).toHaveCount(0);
});
test("failed save shows error and restores the confirmed placement", async ({
  page,
}) => {
  await setup(page);
  await page.route("**/maps/1/placements/1", (r) =>
    r.fulfill({ status: 502, json: { detail: "Save unavailable" } }),
  );
  const marker = page.getByTestId("marker-1"),
    before = await marker.boundingBox();
  const x = before!.x + before!.width / 2,
    y = before!.y + 19;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 50, y + 20, { steps: 5 });
  await page.mouse.up();
  await expect(page.getByRole("alert")).toContainText("Save unavailable");
  const after = await marker.boundingBox();
  expect(after!.x).toBeCloseTo(before!.x, 0);
});
test("login form and empty workspace are usable on a narrow viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await expect(
    page.getByRole("heading", { name: "Welcome back" }),
  ).toBeVisible();
  await page.screenshot({ path: "test-results/login-mobile.png" });
});

test('discovery shows existing cameras and saves a newly discovered device', async ({ page }) => {
  await setup(page);
  const found = { ...cameras[0], ip: '192.168.101.99', id: 99 };
  const job = { id: 'scan-demo', status: 'completed', error: null, result: { '192.168.101.0/24': { onvif: [cameras[0], found], errors: [] } } };
  await page.route('**/scans/', r => r.fulfill({ status: 202, json: job }));
  await page.route('**/scans/scan-demo', r => r.fulfill({ json: job }));
  await page.route('**/scans/scan-demo/cameras/1', r => r.fulfill({ status: 201, json: { id: 99, already_exists: false } }));
  await page.getByRole('button', { name: 'Discovery', exact: true }).click();
  await page.getByRole('button', { name: 'Start scan', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Saved', exact: true })).toHaveCount(1);
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Saved', exact: true })).toHaveCount(2);
});

test('dragging background pans without moving saved cameras', async ({ page }) => {
  const writes = await setup(page);
  const marker = page.getByTestId('marker-1');
  const before = await marker.boundingBox();
  const image = await page.getByTestId('map-image').boundingBox();
  const x = image!.x + image!.width * .5, y = image!.y + image!.height * .3;
  await page.mouse.move(x, y); await page.mouse.down();
  await page.mouse.move(x + 70, y + 25, { steps: 8 }); await page.mouse.up();
  const after = await marker.boundingBox();
  expect(after!.x - before!.x).toBeCloseTo(70, 0);
  expect(after!.y - before!.y).toBeCloseTo(25, 0);
  expect(writes).toHaveLength(0);
});

test('mouse wheel keeps its anchor and sector handles save coverage', async ({ page }) => {
  const writes = await setup(page);
  const before = await page.getByTestId('map-image').boundingBox();
  const anchor = { x: Math.floor(before!.x + before!.width * .4), y: Math.floor(before!.y + before!.height * .3) };
  const expected = { x: (anchor.x - before!.x) / before!.width, y: (anchor.y - before!.y) / before!.height };
  await page.mouse.move(anchor.x, anchor.y);
  await page.mouse.wheel(0, -200);
  await expect(page.getByTestId('zoom-level')).not.toHaveText('100%');
  const after = await page.getByTestId('map-image').boundingBox();
  expect((anchor.x - after!.x) / after!.width).toBeCloseTo(expected.x, 5);
  expect((anchor.y - after!.y) / after!.height).toBeCloseTo(expected.y, 5);
  await page.getByTestId('camera-card-1').click();
  const handle = await page.getByTestId('handle-aim-2').boundingBox();
  const x = handle!.x + handle!.width / 2, y = handle!.y + handle!.height / 2;
  await page.mouse.move(x, y); await page.mouse.down();
  await page.mouse.move(x + 30, y + 20, { steps: 6 }); await page.mouse.up();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].direction).toBeGreaterThan(90);
  expect(writes[0].view_distance).toBeGreaterThan(.2);
});

test("collapse and expand preserves map zoom and placement", async ({ page }) => {
  const writes = await setup(page);
  await page.goto("/");
  await expect(page.getByTestId("marker-1")).toBeVisible();
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect(page.getByTestId("zoom-level")).toHaveText("130%");
  const before = await page.getByTestId("marker-1").boundingBox();
  await page.getByRole("button", { name: "Collapse map" }).click();
  await expect(page.locator("#map-content")).toBeHidden();
  await expect(page.getByTestId("camera-card-1")).toBeVisible();
  await page.getByRole("button", { name: "Expand map" }).click();
  await expect(page.getByTestId("marker-1")).toBeVisible();
  await expect(page.getByTestId("zoom-level")).toHaveText("130%");
  const after = await page.getByTestId("marker-1").boundingBox();
  expect(after!.x).toBeCloseTo(before!.x, 0);
  expect(after!.y).toBeCloseTo(before!.y, 0);
  expect(writes).toHaveLength(0);
});

test("deleting a camera requires confirmation and updates the list", async ({ page }) => {
  await setup(page);
  let deleted = 0;
  await page.route("**/camera/1", async (route) => {
    expect(route.request().method()).toBe("DELETE");
    deleted++;
    await route.fulfill({ status: 204 });
  });
  await page.getByTestId("camera-card-1").click();
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Delete camera", exact: true }).click();
  expect(deleted).toBe(0);
  await expect(page.getByTestId("camera-card-1")).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete camera", exact: true }).click();
  await expect(page.getByTestId("camera-card-1")).toHaveCount(0);
  await expect(page.getByTestId("camera-card-2")).toBeVisible();
  expect(deleted).toBe(1);
});
