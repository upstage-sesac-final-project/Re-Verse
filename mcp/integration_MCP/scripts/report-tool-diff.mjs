/**
 * Compare integration registry against baseline inventory.
 * Emits PASS/DIFF/ENV-BLOCKED classification report.
 */
import fs from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const BASELINE_PATH = path.join(ROOT, "merger", "compat-baseline.json");

async function readJson(file) {
  return JSON.parse(await fs.readFile(file, "utf-8"));
}

function classifyRows(rows) {
  const out = [];
  for (const row of rows) {
    const inAnyOrigin =
      row.sources.mcp1_hyphen_rpgmaker ||
      row.sources.mcp2_rpgmaker_extended ||
      row.sources.mcp3_base_reference ||
      row.sources.mcp4_mcp_maker;
    if (!inAnyOrigin) continue;

    let status = "PASS";
    let reason = "covered";
    if (!row.inRegistry) {
      status = "DIFF";
      reason = "missing from integration registry";
    } else if (
      row.canonical === "generate_asset" ||
      row.canonical === "generate_asset_batch" ||
      row.canonical === "describe_asset" ||
      row.canonical === "run_playtest" ||
      row.canonical === "inspect_game_state"
    ) {
      status = "ENV-BLOCKED";
      reason = "requires external runtime/API/browser policy";
    }
    out.push({ name: row.name, canonical: row.canonical, status, reason });
  }
  return out.sort((a, b) => a.name.localeCompare(b.name));
}

async function main() {
  const baseline = await readJson(BASELINE_PATH);
  const classifications = classifyRows(baseline.coverage.rows);
  const summary = {
    pass: classifications.filter((r) => r.status === "PASS").length,
    diff: classifications.filter((r) => r.status === "DIFF").length,
    envBlocked: classifications.filter((r) => r.status === "ENV-BLOCKED").length,
  };
  const payload = {
    generatedAt: new Date().toISOString(),
    summary,
    classifications,
  };
  const outPath = path.join(ROOT, "merger", "tool-diff-report.json");
  await fs.writeFile(outPath, JSON.stringify(payload, null, 2), "utf-8");
  console.log(`Wrote ${path.relative(ROOT, outPath)}`);
  console.log(JSON.stringify(summary, null, 2));
  if (summary.diff > 0) process.exitCode = 1;
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
