import { defineConfig } from "vite";
export default defineConfig(({ command }) => ({
  base: command === "build" ? "/ui/" : "/",
  build: { outDir: "../src/mapc/static/app", emptyOutDir: true },
  server: {
    proxy: Object.fromEntries(
      ["/auth", "/camera", "/maps", "/scans"].map((path) => [
        path,
        "http://127.0.0.1:8080",
      ]),
    ),
  },
}));
