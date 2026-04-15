import fs from "fs/promises";
import path from "path";
import { validateProjectPath, getFilesRecursively } from "../../utils/validation.js";
import { readDataJson } from "./jsonFile.js";
import { HandlerResponse } from "../../types/index.js";

type ProjectArgs = { projectPath: string };

function jsonText(data: unknown): HandlerResponse {
    return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
}

const META_DIR = ".integration_mcp";

async function ensureMetaDir(projectPath: string): Promise<string> {
    const dir = path.join(projectPath, META_DIR);
    await fs.mkdir(dir, { recursive: true });
    return dir;
}

async function readJsonFile<T>(file: string, fallback: T): Promise<T> {
    try {
        const raw = await fs.readFile(file, "utf-8");
        return JSON.parse(raw) as T;
    } catch {
        return fallback;
    }
}

async function writeJsonFile(file: string, value: unknown): Promise<void> {
    await fs.mkdir(path.dirname(file), { recursive: true });
    await fs.writeFile(file, JSON.stringify(value, null, 2), "utf-8");
}

export async function list_projects(args: { directory?: string }): Promise<HandlerResponse> {
    const root = args.directory ? path.resolve(args.directory) : path.join(process.env.HOME ?? ".", "Documents");
    const projects: { path: string; name: string }[] = [];
    try {
        const stack = [root];
        while (stack.length > 0) {
            const dir = stack.pop()!;
            let names: string[];
            try {
                names = await fs.readdir(dir);
            } catch {
                continue;
            }
            for (const name of names) {
                if (name.startsWith(".")) continue;
                const full = path.join(dir, name);
                let st;
                try {
                    st = await fs.stat(full);
                } catch {
                    continue;
                }
                if (st.isDirectory()) stack.push(full);
                else if (name === "game.rmmzproject") {
                    projects.push({ path: dir, name: path.basename(dir) });
                }
            }
        }
    } catch (e: unknown) {
        return jsonText({ error: String(e), scanned: root, projects: [] });
    }
    return jsonText({ scanned: root, projects });
}

export async function generate_project_context(
    args: ProjectArgs & { includeMaps?: boolean; includeEvents?: boolean; includePlugins?: boolean }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const incMaps = args.includeMaps !== false;
    const incEv = args.includeEvents !== false;
    const incPl = args.includePlugins !== false;
    const chunks: string[] = [];
    try {
        const sys = await readDataJson<Record<string, unknown>>(args.projectPath, "System.json");
        chunks.push(`## System\n${JSON.stringify(sys, null, 2).slice(0, 4000)}`);
    } catch {
        chunks.push("## System\n(unreadable)");
    }
    if (incMaps) {
        try {
            const infos = await readDataJson<unknown[]>(args.projectPath, "MapInfos.json");
            chunks.push(`## MapInfos (${infos.length} entries)\n${JSON.stringify(infos, null, 2).slice(0, 6000)}`);
        } catch {
            chunks.push("## MapInfos\n(unreadable)");
        }
    }
    if (incEv && incMaps) {
        chunks.push("## Events\n(Map event bodies omitted for size; use get_map / get_map_event tools.)");
    }
    if (incPl) {
        try {
            const plugPath = path.join(args.projectPath, "js", "plugins.js");
            const txt = await fs.readFile(plugPath, "utf-8");
            chunks.push(`## plugins.js (truncated)\n${txt.slice(0, 4000)}`);
        } catch {
            chunks.push("## plugins.js\n(unreadable)");
        }
    }
    return jsonText({ summary: chunks.join("\n\n") });
}

export async function analyze_project_structure(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const dataFiles = await getFilesRecursively(path.join(args.projectPath, "data")).catch(() => []);
    const imgFiles = await getFilesRecursively(path.join(args.projectPath, "img")).catch(() => []);
    return jsonText({
        dataJsonCount: dataFiles.filter((f) => f.endsWith(".json")).length,
        imgFileCount: imgFiles.length,
        sampleDataFiles: dataFiles.filter((f) => f.endsWith(".json")).slice(0, 30),
    });
}

export async function extract_game_design_patterns(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    return jsonText({
        note: "Heuristic summary only.",
        hints: [
            "Use search_events and search_map_events to find dialogue-heavy maps.",
            "Use get_database_info for entity counts.",
        ],
    });
}

export async function create_project(args: { projectPath: string; gameTitle: string }): Promise<HandlerResponse> {
    const target = path.resolve(args.projectPath);
    await fs.mkdir(target, { recursive: true });
    await fs.writeFile(path.join(target, "game.rmmzproject"), "{}", "utf-8");
    await fs.mkdir(path.join(target, "data"), { recursive: true });
    await fs.writeFile(
        path.join(target, "data", "System.json"),
        JSON.stringify({ gameTitle: args.gameTitle, variables: [], switches: [] }, null, 2),
        "utf-8"
    );
    return jsonText({
        ok: true,
        warning: "Minimal stub only. Open this folder in RPG Maker MZ to generate full project files.",
        path: target,
    });
}

export async function generate_asset(args: ProjectArgs & { prompt: string; assetType: string; filename: string }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    return jsonText({
        ok: false,
        status: "ENV-BLOCKED",
        message:
            "Gemini/image pipeline is not configured in this runtime. Set GEMINI_API_KEY and provider integration to enable.",
        requested: { assetType: args.assetType, filename: args.filename, promptLen: args.prompt.length },
    });
}

export async function generate_asset_batch(args: { requests: unknown[] }): Promise<HandlerResponse> {
    return jsonText({
        ok: false,
        status: "ENV-BLOCKED",
        message: "generate_asset_batch requires external provider wiring (Gemini or equivalent).",
        count: Array.isArray(args.requests) ? args.requests.length : 0,
    });
}

export async function describe_asset(
    args: ProjectArgs & { assetType: string; filename: string }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    return jsonText({
        ok: false,
        status: "ENV-BLOCKED",
        message: "describe_asset requires vision provider integration and API key.",
        assetType: args.assetType,
        filename: args.filename,
    });
}

export async function generate_scenario(
    args: ProjectArgs & { theme: string; style?: string; length?: "short" | "medium" | "long" }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const style = args.style ?? "jrpg";
    const length = args.length ?? "medium";
    const scenario = {
        title: `${args.theme} - ${style}`,
        length,
        synopsis: `${args.theme} 테마의 ${style} 스타일 시나리오`,
        acts: [
            { id: 1, goal: "도입: 세계관과 주인공 소개" },
            { id: 2, goal: "전개: 핵심 갈등과 단서 수집" },
            { id: 3, goal: "결말: 보스 대면과 해소" },
        ],
    };
    return jsonText({ ok: true, scenario });
}

export async function generate_scenario_variations(
    args: ProjectArgs & { theme: string; style?: string; length?: "short" | "medium" | "long"; count?: number }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const count = Math.max(1, Math.min(10, Number(args.count ?? 3)));
    const list = [];
    for (let i = 0; i < count; i++) {
        list.push({
            index: i + 1,
            title: `${args.theme} Variation ${i + 1}`,
            hook: `핵심 반전 포인트 ${i + 1}`,
        });
    }
    return jsonText({ ok: true, variations: list });
}

export async function implement_scenario(
    args: ProjectArgs & { scenario: unknown }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const metaDir = await ensureMetaDir(args.projectPath);
    const outFile = path.join(metaDir, "implemented-scenarios.json");
    const existing = await readJsonFile<unknown[]>(outFile, []);
    const next = Array.isArray(existing) ? existing : [];
    next.push({
        implementedAt: new Date().toISOString(),
        scenario: args.scenario,
    });
    await writeJsonFile(outFile, next);
    return jsonText({ ok: true, storedAt: outFile, total: next.length });
}

export async function generate_and_implement_scenario(
    args: ProjectArgs & { theme: string; style?: string; length?: "short" | "medium" | "long" }
): Promise<HandlerResponse> {
    const generated = await generate_scenario(args);
    const payload = JSON.parse((generated.content?.[0] as { text?: string })?.text ?? "{}");
    const implemented = await implement_scenario({ projectPath: args.projectPath, scenario: payload.scenario ?? payload });
    const implPayload = JSON.parse((implemented.content?.[0] as { text?: string })?.text ?? "{}");
    return jsonText({
        ok: true,
        scenario: payload.scenario ?? null,
        implementation: implPayload,
    });
}

export async function autonomous_create_game(
    args: ProjectArgs & { concept: string; gameTitle?: string; length?: "short" | "medium" | "long" }
): Promise<HandlerResponse> {
    const title = args.gameTitle ?? `AutoGame - ${args.concept}`;
    await create_project({ projectPath: args.projectPath, gameTitle: title });
    const scenarioResp = await generate_scenario({
        projectPath: args.projectPath,
        theme: args.concept,
        style: "autonomous",
        length: args.length ?? "medium",
    });
    const scenarioPayload = JSON.parse((scenarioResp.content?.[0] as { text?: string })?.text ?? "{}");
    await implement_scenario({ projectPath: args.projectPath, scenario: scenarioPayload.scenario ?? scenarioPayload });
    return jsonText({
        ok: true,
        projectPath: path.resolve(args.projectPath),
        gameTitle: title,
        note: "Autonomous flow completed with local scaffold + scenario artifacts.",
    });
}

export async function register_resource(
    args: ProjectArgs & { resourceId: string; resourceType: string; name: string; description?: string; content?: unknown; tags?: string[] }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const metaDir = await ensureMetaDir(args.projectPath);
    const file = path.join(metaDir, "resources.json");
    const list = await readJsonFile<any[]>(file, []);
    const filtered = list.filter((r) => r.id !== args.resourceId);
    filtered.push({
        id: args.resourceId,
        type: args.resourceType,
        name: args.name,
        description: args.description ?? "",
        content: args.content ?? null,
        tags: Array.isArray(args.tags) ? args.tags : [],
        updatedAt: new Date().toISOString(),
    });
    await writeJsonFile(file, filtered);
    return jsonText({ ok: true, id: args.resourceId, total: filtered.length });
}

export async function list_resources(
    args: ProjectArgs & { type?: string; tags?: string[] }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const file = path.join(args.projectPath, META_DIR, "resources.json");
    let rows = await readJsonFile<any[]>(file, []);
    if (args.type) rows = rows.filter((r) => r.type === args.type);
    if (Array.isArray(args.tags) && args.tags.length > 0) {
        rows = rows.filter((r) => Array.isArray(r.tags) && args.tags!.every((t) => r.tags.includes(t)));
    }
    return jsonText({ ok: true, count: rows.length, resources: rows });
}

export async function register_prompt_template(
    args: ProjectArgs & { promptId: string; name: string; description?: string; template: string; variables?: string[]; resourceRefs?: string[] }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const metaDir = await ensureMetaDir(args.projectPath);
    const file = path.join(metaDir, "prompt-templates.json");
    const list = await readJsonFile<any[]>(file, []);
    const filtered = list.filter((r) => r.id !== args.promptId);
    filtered.push({
        id: args.promptId,
        name: args.name,
        description: args.description ?? "",
        template: args.template,
        variables: Array.isArray(args.variables) ? args.variables : [],
        resourceRefs: Array.isArray(args.resourceRefs) ? args.resourceRefs : [],
        updatedAt: new Date().toISOString(),
    });
    await writeJsonFile(file, filtered);
    return jsonText({ ok: true, id: args.promptId, total: filtered.length });
}

export async function execute_prompt(
    args: ProjectArgs & { promptId: string; variables?: Record<string, unknown> }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const file = path.join(args.projectPath, META_DIR, "prompt-templates.json");
    const templates = await readJsonFile<any[]>(file, []);
    const target = templates.find((t) => t.id === args.promptId);
    if (!target) {
        return jsonText({ ok: false, error: `Prompt template not found: ${args.promptId}` });
    }
    let rendered = String(target.template ?? "");
    const vars = args.variables ?? {};
    for (const [k, v] of Object.entries(vars)) {
        rendered = rendered.replaceAll(`{{${k}}}`, String(v));
    }
    return jsonText({ ok: true, prompt: rendered, template: target.id });
}

export async function search_database(
    args: ProjectArgs & { types?: string[]; nameContains?: string; idMin?: number; idMax?: number }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const defaultTypes = ["Actors", "Items", "Skills", "Weapons", "Armors", "Enemies", "States", "Classes"];
    const selected = (args.types && args.types.length > 0 ? args.types : defaultTypes)
        .map((t) => t.endsWith(".json") ? t : `${t}.json`);
    const nameQ = (args.nameContains ?? "").toLowerCase();
    const min = args.idMin ?? 0;
    const max = args.idMax ?? Number.MAX_SAFE_INTEGER;
    const results: Array<{ database: string; id: number; name: string }> = [];
    for (const file of selected) {
        const rows = await readDataJson<Array<any>>(args.projectPath, file).catch(() => []);
        for (const row of rows) {
            if (!row || typeof row.id !== "number") continue;
            if (row.id < min || row.id > max) continue;
            const n = String(row.name ?? "");
            if (nameQ && !n.toLowerCase().includes(nameQ)) continue;
            results.push({ database: file, id: row.id, name: n });
        }
    }
    return jsonText({ ok: true, count: results.length, results });
}

export async function analyze_assets(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const imgFiles = await getFilesRecursively(path.join(args.projectPath, "img")).catch(() => []);
    const audioFiles = await getFilesRecursively(path.join(args.projectPath, "audio")).catch(() => []);
    const byExt = new Map<string, number>();
    for (const f of [...imgFiles, ...audioFiles]) {
        const ext = path.extname(f).toLowerCase() || "(none)";
        byExt.set(ext, (byExt.get(ext) ?? 0) + 1);
    }
    return jsonText({
        ok: true,
        totals: { img: imgFiles.length, audio: audioFiles.length },
        byExtension: Object.fromEntries([...byExt.entries()].sort((a, b) => a[0].localeCompare(b[0]))),
    });
}
