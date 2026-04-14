/**
 * Compares tool-registry.json canonical names + aliases against index.ts toolMap keys.
 * Usage: node scripts/audit-tool-coverage.mjs
 */

import fs from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");

const REGISTRY = JSON.parse(await fs.readFile(path.join(ROOT, "tool-registry.json"), "utf-8"));
const TOOL_MAP_FILE = await fs.readFile(path.join(ROOT, "mcpToolMap.ts"), "utf-8");

const implKeys = new Set();
for (const line of TOOL_MAP_FILE.split("\n")) {
  const m = /^\s{4}([a-z0-9_]+):/.exec(line);
  if (m) implKeys.add(m[1]);
}

function resolveImpl(canonical) {
  const map = REGISTRY.canonicalToImplementationName ?? {};
  return map[canonical] ?? canonical;
}

function callableCanonical(name) {
  const c = REGISTRY.aliasToCanonical[name] ?? name;
  const impl = resolveImpl(c);
  return implKeys.has(impl);
}

const canonical = REGISTRY.canonicalTools;
const implemented = [];
const notImplemented = [];

for (const c of canonical) {
  const ok = callableCanonical(c);
  if (ok) implemented.push(c);
  else notImplemented.push(c);
}

const out = {
  generatedAt: new Date().toISOString(),
  registryVersion: REGISTRY.version,
  summary: {
    canonicalTotal: canonical.length,
    implementationKeysInIndex: implKeys.size,
    canonicalCallable: implemented.length,
    canonicalPending: notImplemented.length,
  },
  implementationKeys: [...implKeys].sort(),
  canonicalImplemented: implemented.sort(),
  canonicalPending: notImplemented.sort(),
};

await fs.mkdir(path.join(ROOT, "merger"), { recursive: true });
const outPath = path.join(ROOT, "merger", "implementation-status.json");
await fs.writeFile(outPath, JSON.stringify(out, null, 2), "utf-8");
console.log(JSON.stringify(out.summary, null, 2));
console.log(`Wrote ${path.relative(ROOT, outPath)}`);
