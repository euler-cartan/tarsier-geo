// Keep frontend test runs away from a real Tarsier data folder.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const real = (target) => {
  let current = path.resolve(target);
  const rest = [];
  while (!fs.existsSync(current) && path.dirname(current) !== current) {
    rest.unshift(path.basename(current));
    current = path.dirname(current);
  }
  const joined = path.join(fs.existsSync(current) ? fs.realpathSync.native(current) : current, ...rest);
  return process.platform === "win32" ? joined.toLowerCase() : joined;
};
const inside = (child, parent) => child === parent || child.startsWith(parent + path.sep);

const root = real(process.env.TARSIER_QA_TEMP_ROOT ?? os.tmpdir());
const base = process.platform === "win32"
  ? process.env.APPDATA ?? path.join(os.homedir(), "AppData", "Roaming")
  : process.env.XDG_DATA_HOME ?? path.join(os.homedir(), ".local", "share");
const appDefault = real(path.join(base, "tarsier-geo"));
const raw = process.env.TARSIER_HOME?.trim();

if (raw) {
  const target = real(raw);
  if (!path.isAbsolute(raw) || inside(target, appDefault)) throw new Error("TARSIER_HOME cannot be the app's real data folder.");
  if (target === root || !inside(target, root)) throw new Error("TARSIER_HOME must be a folder inside the temporary directory, or unset.");
} else if (process.env.VITEST) {
  process.env.TARSIER_HOME = fs.mkdtempSync(path.join(root, "tarsier-test-"));
}
