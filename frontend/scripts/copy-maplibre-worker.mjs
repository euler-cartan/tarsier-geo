// Vite's static analysis doesn't pick up maplibre-gl's worker loading
// pattern, so the worker file never lands in the build output on its own
// (confirmed empty dist/assets after a normal build) and MapLibre fails
// at runtime with "Worker failed to load." Copying it into public/ makes
// Vite serve/bundle it as a plain static file; main.tsx points MapLibre
// at it via setWorkerUrl(). Run before dev/build, not committed (always
// copied fresh from whatever maplibre-gl version is actually installed).
import { copyFileSync, mkdirSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const here = dirname(fileURLToPath(import.meta.url));
const source = join(here, "..", "..", "node_modules", "maplibre-gl", "dist", "maplibre-gl-worker.mjs");
const destDir = join(here, "..", "public");
const dest = join(destDir, "maplibre-gl-worker.mjs");

mkdirSync(destDir, { recursive: true });
copyFileSync(source, dest);
console.log(`Copied maplibre-gl worker to ${dest}`);
