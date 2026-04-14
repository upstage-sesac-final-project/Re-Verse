/**
 * Build tool/schema baseline across the 4 source MCP projects.
 * Output: merger/compat-baseline.json
 */
import fs from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "merger", "compat-baseline.json");

const SOURCES = {
  integration_MCP: path.join(ROOT),
  mcp1_hyphen_rpgmaker: path.resolve(ROOT, "../-rpgmaker-mz-mcp"),
  mcp2_rpgmaker_extended: path.resolve(ROOT, "../rpgmaker-mz-mcp"),
  mcp3_base_reference: path.resolve(ROOT, "../RPGMakerMZ_MCP"),
  mcp4_mcp_maker: path.resolve(ROOT, "../MCP-Maker"),
};

const TOOL_NAME_PATTERNS = [
  /name\s*:\s*["']([a-z0-9_]+)["']\s*,\s*description\s*:/g,
  /case\s+["']([a-z0-9_]+)["']\s*:/g,
  /server\.tool\s*\(\s*["']([a-z0-9_]+)["']/g,
];
const TOOL_PREFIX_RE = /^(get|list|read|write|search|create|update|delete|add|set|check|scan|install|generate|implement|extract|run|inspect|undo|show|register|execute|analyze|autonomous)_/;

async function listFilesRecursive(dir) {
  const out = [];
  async function walk(current) {
    let entries = [];
    try {
      entries = await fs.readdir(current, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (entry.name === "node_modules" || entry.name === "dist" || entry.name.startsWith(".")) continue;
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        await walk(full);
      } else if (entry.isFile() && (entry.name.endsWith(".ts") || entry.name.endsWith(".json"))) {
        out.push(full);
      }
    }
  }
  await walk(dir);
  return out;
}

function collectToolNames(text) {
  const names = new Set();
  for (const re of TOOL_NAME_PATTERNS) {
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(text)) !== null) {
      names.add(m[1]);
    }
  }
  return [...names].filter((n) => TOOL_PREFIX_RE.test(n));
}

async function scanSource(sourcePath) {
  const files = await listFilesRecursive(sourcePath);
  const names = new Set();
  const byFile = {};
  for (const file of files) {
    const text = await fs.readFile(file, "utf-8").catch(() => "");
    if (!text) continue;
    const found = collectToolNames(text);
    if (found.length > 0) {
      for (const n of found) names.add(n);
      byFile[path.relative(sourcePath, file)] = found.sort();
    }
  }
  return { toolNames: [...names].sort(), filesWithTools: byFile };
}

async function readRegistry() {
  const registryPath = path.join(ROOT, "tool-registry.json");
  const raw = await fs.readFile(registryPath, "utf-8");
  const data = JSON.parse(raw);
  return {
    canonicalTools: [...data.canonicalTools].sort(),
    aliases: data.aliasToCanonical ?? {},
    profiles: data.profileByTool ?? {},
  };
}

function buildCoverageMatrix(scans, registry) {
  const allNames = new Set();
  for (const source of Object.values(scans)) {
    for (const n of source.toolNames) allNames.add(n);
  }
  for (const n of registry.canonicalTools) allNames.add(n);

  const canonicalSet = new Set(registry.canonicalTools);
  const aliasMap = registry.aliases;
  const rows = [...allNames]
    .sort()
    .map((name) => {
      const canonical = aliasMap[name] ?? name;
      return {
        name,
        canonical,
        inRegistry: canonicalSet.has(canonical),
        sources: Object.fromEntries(
          Object.entries(scans).map(([k, v]) => [k, v.toolNames.includes(name)])
        ),
      };
    });

  const missingFromRegistry = rows
    .filter((r) => !r.inRegistry && Object.values(r.sources).some(Boolean))
    .map((r) => r.name);

  return {
    rows,
    summary: {
      totalNamesObserved: rows.length,
      registryCanonicalCount: registry.canonicalTools.length,
      missingFromRegistry,
    },
  };
}

async function main() {
  const scans = {};
  for (const [key, src] of Object.entries(SOURCES)) {
    scans[key] = await scanSource(src);
  }
  const registry = await readRegistry();
  const coverage = buildCoverageMatrix(scans, registry);

  const payload = {
    generatedAt: new Date().toISOString(),
    sources: Object.fromEntries(Object.entries(SOURCES).map(([k, v]) => [k, path.relative(ROOT, v)])),
    scans,
    registry,
    coverage,
  };

  await fs.mkdir(path.dirname(OUT), { recursive: true });
  await fs.writeFile(OUT, JSON.stringify(payload, null, 2), "utf-8");
  console.log(`Wrote ${path.relative(ROOT, OUT)}`);
  console.log(
    JSON.stringify(
      {
        totalObserved: coverage.summary.totalNamesObserved,
        registryCanonical: coverage.summary.registryCanonicalCount,
        missingFromRegistry: coverage.summary.missingFromRegistry.length,
      },
      null,
      2
    )
  );
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
