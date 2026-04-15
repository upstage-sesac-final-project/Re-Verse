/**
 * Verify integration_MCP works standalone (without sibling MCP repos).
 */
import fs from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");

async function read(file) {
  return fs.readFile(file, "utf-8");
}

async function main() {
  const checks = [];

  const pkg = JSON.parse(await read(path.join(ROOT, "package.json")));
  const deps = { ...(pkg.dependencies ?? {}), ...(pkg.devDependencies ?? {}) };
  const forbidden = Object.values(deps).filter((v) => typeof v === "string" && (v.startsWith("file:../") || v.startsWith("link:../")));
  checks.push({
    name: "no_relative_file_deps",
    ok: forbidden.length === 0,
    details: forbidden,
  });

  const entry = await read(path.join(ROOT, "index.ts"));
  checks.push({
    name: "entry_no_sibling_import",
    ok: !entry.includes("../rpgmaker-mz-mcp") && !entry.includes("../-rpgmaker-mz-mcp") && !entry.includes("../MCP-Maker"),
  });

  const map = await read(path.join(ROOT, "mcpToolMap.ts"));
  checks.push({
    name: "toolmap_internal_imports_only",
    ok: !map.includes("../rpgmaker-mz-mcp") && !map.includes("../-rpgmaker-mz-mcp") && !map.includes("../MCP-Maker"),
  });

  const allOk = checks.every((c) => c.ok);
  const out = { generatedAt: new Date().toISOString(), ok: allOk, checks };
  const outPath = path.join(ROOT, "merger", "standalone-validation.json");
  await fs.mkdir(path.dirname(outPath), { recursive: true });
  await fs.writeFile(outPath, JSON.stringify(out, null, 2), "utf-8");
  console.log(`Wrote ${path.relative(ROOT, outPath)}`);
  console.log(JSON.stringify(out, null, 2));
  if (!allOk) process.exitCode = 1;
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
