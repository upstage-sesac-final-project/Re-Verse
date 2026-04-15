/**
 * Reads tool-registry.json and emits generated/toolRegistry.generated.ts
 *
 * Usage: node scripts/build-tool-registry.mjs
 */

import fs from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const REGISTRY_PATH = path.join(ROOT, "tool-registry.json");
const OUT_PATH = path.join(ROOT, "generated", "toolRegistry.generated.ts");

function invertAliasMap(aliasToCanonical) {
  const out = {};
  for (const [alias, canonical] of Object.entries(aliasToCanonical)) {
    if (!out[canonical]) out[canonical] = [];
    out[canonical].push(alias);
  }
  for (const k of Object.keys(out)) {
    out[k].sort();
  }
  return out;
}

function buildToolToProfile(profileByTool) {
  const map = {};
  for (const profile of Object.keys(profileByTool)) {
    for (const name of profileByTool[profile]) {
      if (map[name] && map[name] !== profile) {
        throw new Error(`Tool "${name}" appears in multiple profiles: ${map[name]} and ${profile}`);
      }
      map[name] = profile;
    }
  }
  return map;
}

function validateRegistry(data) {
  const canonical = new Set(data.canonicalTools);
  for (const [alias, target] of Object.entries(data.aliasToCanonical)) {
    if (!canonical.has(target)) {
      throw new Error(`aliasToCanonical: "${alias}" -> "${target}" but "${target}" is not in canonicalTools`);
    }
    if (alias === target) {
      throw new Error(`aliasToCanonical: "${alias}" must not equal canonical "${target}"`);
    }
  }
  for (const [profile, names] of Object.entries(data.profileByTool)) {
    for (const name of names) {
      if (!canonical.has(name)) {
        throw new Error(`profileByTool.${profile}: "${name}" is not in canonicalTools`);
      }
    }
  }
  const profiled = new Set();
  for (const names of Object.values(data.profileByTool)) {
    for (const n of names) profiled.add(n);
  }
  for (const name of data.canonicalTools) {
    if (!profiled.has(name)) {
      throw new Error(`canonicalTools: "${name}" is not assigned to any profile in profileByTool`);
    }
  }
}

async function main() {
  const raw = await fs.readFile(REGISTRY_PATH, "utf-8");
  const data = JSON.parse(raw);
  validateRegistry(data);

  const canonicalToAliases = invertAliasMap(data.aliasToCanonical);
  const toolToProfile = buildToolToProfile(data.profileByTool);
  const implMap = data.canonicalToImplementationName ?? {};

  const header = `/* eslint-disable */
/**
 * AUTO-GENERATED FILE — do not edit by hand.
 * Source: tool-registry.json
 * Generator: scripts/build-tool-registry.mjs
 * Version: ${data.version}
 */

export type ToolProfile = "core" | "engine" | "generation" | "playtest";

export const REGISTRY_VERSION = ${JSON.stringify(data.version)} as const;

export const CANONICAL_TOOL_NAMES = ${JSON.stringify([...data.canonicalTools].sort(), null, 2)} as const;

export type CanonicalToolName = (typeof CANONICAL_TOOL_NAMES)[number];

export const ALIAS_TO_CANONICAL: Readonly<Record<string, string>> = Object.freeze(${JSON.stringify(data.aliasToCanonical, null, 2)});

export const CANONICAL_TO_ALIASES: Readonly<Record<string, readonly string[]>> = Object.freeze(${JSON.stringify(canonicalToAliases, null, 2)} as Record<string, readonly string[]>);

export const TOOL_PROFILE_BY_NAME: Readonly<Record<string, ToolProfile>> = Object.freeze(${JSON.stringify(toolToProfile, null, 2)});

export const DEFAULT_PROFILE_FLAGS: Readonly<Record<ToolProfile, boolean>> = Object.freeze(${JSON.stringify(data.defaultProfileFlags, null, 2)});

export const CANONICAL_TO_IMPLEMENTATION_NAME: Readonly<Record<string, string>> = Object.freeze(${JSON.stringify(implMap, null, 2)});

/**
 * Resolve alias or canonical name to canonical tool name.
 */
export function resolveCanonicalToolName(name: string): string {
  return ALIAS_TO_CANONICAL[name] ?? name;
}

/**
 * Map registry canonical name to the current server implementation key (if different).
 * Example: create_actor -> add_actor until handlers are renamed.
 */
export function resolveImplementationToolName(name: string): string {
  const canonical = resolveCanonicalToolName(name);
  return CANONICAL_TO_IMPLEMENTATION_NAME[canonical] ?? canonical;
}

/**
 * All names (canonical + aliases) that map to the same canonical tool.
 */
export function allNamesForCanonical(canonical: string): readonly string[] {
  const aliases = CANONICAL_TO_ALIASES[canonical] ?? [];
  return [canonical, ...aliases];
}
`;

  await fs.mkdir(path.dirname(OUT_PATH), { recursive: true });
  await fs.writeFile(OUT_PATH, header, "utf-8");
  console.log(`Wrote ${path.relative(ROOT, OUT_PATH)}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
