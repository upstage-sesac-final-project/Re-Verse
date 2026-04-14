import fs from "fs/promises";
import path from "path";
import { validateProjectPath } from "../../utils/validation.js";
import { readDataJson, writeDataJson } from "./jsonFile.js";
import { HandlerResponse } from "../../types/index.js";

type ProjectArgs = { projectPath: string };

function jsonText(data: unknown): HandlerResponse {
    return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
}

function countNamed(arr: unknown[] | null): number {
    if (!Array.isArray(arr)) return 0;
    return arr.filter((i) => i !== null && typeof i === "object" && i && "name" in i && (i as { name?: string }).name !== "").length;
}

async function tryReadData<T>(projectPath: string, filename: string): Promise<T | null> {
    try {
        return await readDataJson<T>(projectPath, filename);
    } catch {
        return null;
    }
}

export async function get_database_info(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const p = args.projectPath;
    const [actors, classes, items, skills, weapons, armors, enemies, states] = await Promise.all([
        tryReadData<(unknown | null)[]>(p, "Actors.json"),
        tryReadData<(unknown | null)[]>(p, "Classes.json"),
        tryReadData<(unknown | null)[]>(p, "Items.json"),
        tryReadData<(unknown | null)[]>(p, "Skills.json"),
        tryReadData<(unknown | null)[]>(p, "Weapons.json"),
        tryReadData<(unknown | null)[]>(p, "Armors.json"),
        tryReadData<(unknown | null)[]>(p, "Enemies.json"),
        tryReadData<(unknown | null)[]>(p, "States.json"),
    ]);
    const safe = (a: unknown[] | null) => a ?? [];
    const summary = {
        actors: { count: countNamed(safe(actors)) },
        classes: { count: countNamed(safe(classes)) },
        skills: { count: countNamed(safe(skills)) },
        items: { count: countNamed(safe(items)) },
        weapons: { count: countNamed(safe(weapons)) },
        armors: { count: countNamed(safe(armors)) },
        enemies: { count: countNamed(safe(enemies)) },
        states: { count: countNamed(safe(states)) },
    };
    return jsonText(summary);
}

const DATABASE_FILES: Record<string, string> = {
    items: "Items.json",
    weapons: "Weapons.json",
    armors: "Armors.json",
    skills: "Skills.json",
    actors: "Actors.json",
    classes: "Classes.json",
    enemies: "Enemies.json",
    states: "States.json",
    animations: "Animations.json",
    tilesets: "Tilesets.json",
    troops: "Troops.json",
    commonEvents: "CommonEvents.json",
};

export async function get_database_limits(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const limits: Record<string, number> = {};
    for (const [name, filename] of Object.entries(DATABASE_FILES)) {
        try {
            const data = await readDataJson<unknown[]>(args.projectPath, filename);
            limits[name] = Math.max(0, data.length - 1);
        } catch {
            limits[name] = 0;
        }
    }
    return jsonText(limits);
}

export async function set_database_limit(
    args: ProjectArgs & { database: string; limit: number }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const filename = DATABASE_FILES[args.database];
    if (!filename) throw new Error(`Unknown database: ${args.database}`);
    const data = await readDataJson<unknown[]>(args.projectPath, filename);
    const targetLength = args.limit + 1;
    if (targetLength > data.length) {
        while (data.length < targetLength) data.push(null);
    } else if (targetLength < data.length) {
        while (data.length > targetLength) {
            const last = data[data.length - 1];
            if (last !== null) {
                throw new Error(`Cannot shrink to ${args.limit}: entry at index ${data.length - 1} is not null`);
            }
            data.pop();
        }
    }
    await writeDataJson(args.projectPath, filename, data);
    return jsonText({ ok: true, database: args.database, limit: args.limit });
}

const SCAN_CATEGORIES: Record<string, string> = {
    plugins: "js/plugins",
    tilesets: "img/tilesets",
    characters: "img/characters",
    faces: "img/faces",
    sv_actors: "img/sv_actors",
    sv_enemies: "img/sv_enemies",
    battlebacks1: "img/battlebacks1",
    battlebacks2: "img/battlebacks2",
    parallaxes: "img/parallaxes",
    pictures: "img/pictures",
    animations: "img/animations",
    enemies: "img/enemies",
    titles1: "img/titles1",
    titles2: "img/titles2",
    system: "img/system",
    bgm: "audio/bgm",
    bgs: "audio/bgs",
    me: "audio/me",
    se: "audio/se",
};

export async function scan_resources(
    args: ProjectArgs & {
        category: string;
        source?: "project" | "engine" | "all";
    }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const rel = SCAN_CATEGORIES[args.category];
    if (!rel) throw new Error(`Unknown category: ${args.category}. Use one of: ${Object.keys(SCAN_CATEGORIES).join(", ")}`);
    const source = args.source ?? "project";
    const result: { project: string[]; engine: string[]; note?: string } = { project: [], engine: [] };
    const ext = args.category === "plugins" ? ".js" : undefined;

    if (source === "project" || source === "all") {
        const dir = path.join(args.projectPath, rel);
        try {
            const entries = await fs.readdir(dir, { withFileTypes: true });
            result.project = entries
                .filter((e) => e.isFile())
                .map((e) => e.name)
                .filter((n) => !ext || n.endsWith(ext));
        } catch {
            result.project = [];
        }
    }

    if (source === "engine" || source === "all") {
        const enginePath = process.env.RPGMAKER_ENGINE_PATH;
        if (!enginePath) {
            result.note = "RPGMAKER_ENGINE_PATH not set; engine scan skipped";
        } else {
            const engineDir = path.join(enginePath, "newdata", rel);
            try {
                const entries = await fs.readdir(engineDir, { withFileTypes: true });
                result.engine = entries
                    .filter((e) => e.isFile())
                    .map((e) => e.name)
                    .filter((n) => !ext || n.endsWith(ext));
            } catch {
                result.engine = [];
            }
        }
    }

    return jsonText(result);
}

export async function list_plugins(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const dir = path.join(args.projectPath, "js", "plugins");
    try {
        const entries = await fs.readdir(dir, { withFileTypes: true });
        const files = entries.filter((e) => e.isFile() && e.name.endsWith(".js")).map((e) => e.name);
        return jsonText(files);
    } catch {
        return jsonText([]);
    }
}

export async function install_plugin(args: ProjectArgs & { sourcePath: string; targetName?: string }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const src = path.resolve(args.sourcePath);
    const base = args.targetName ?? path.basename(src);
    if (!base.endsWith(".js")) throw new Error("Plugin filename must end with .js");
    const destDir = path.join(args.projectPath, "js", "plugins");
    await fs.mkdir(destDir, { recursive: true });
    const dest = path.join(destDir, base);
    await fs.copyFile(src, dest);
    return jsonText({ ok: true, installed: dest });
}

export async function get_core_script_versions(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const scripts = ["rmmz_core.js", "rmmz_managers.js", "rmmz_objects.js", "rmmz_scenes.js", "rmmz_windows.js"];
    const versions: Record<string, string | null> = {};
    for (const file of scripts) {
        const full = path.join(args.projectPath, "js", file);
        try {
            const text = await fs.readFile(full, "utf-8");
            const m = text.match(/v(\d+\.\d+\.\d+)/i) ?? text.match(/version\s*[:=]\s*["']?([\d.]+)/i);
            versions[file] = m ? m[1] : null;
        } catch {
            versions[file] = null;
        }
    }
    return jsonText({ ok: true, versions });
}

export async function get_generator_parts(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const generatorRoot = path.join(args.projectPath, "img", "generator");
    try {
        const entries = await fs.readdir(generatorRoot, { withFileTypes: true });
        const folders = entries.filter((e) => e.isDirectory()).map((e) => e.name).sort();
        return jsonText({ ok: true, root: generatorRoot, folders });
    } catch {
        return jsonText({ ok: true, root: generatorRoot, folders: [], note: "generator folder not found" });
    }
}

export async function get_sample_maps(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const enginePath = process.env.RPGMAKER_ENGINE_PATH;
    if (!enginePath) {
        return jsonText({ ok: false, status: "ENV-BLOCKED", message: "RPGMAKER_ENGINE_PATH not set" });
    }
    const newdata = path.join(enginePath, "newdata");
    try {
        const entries = await fs.readdir(newdata);
        const maps = entries.filter((n) => /^Map\d+\.json$/i.test(n)).sort();
        return jsonText({ ok: true, source: newdata, sampleMaps: maps });
    } catch (e: unknown) {
        return jsonText({ ok: false, source: newdata, error: String(e) });
    }
}

export async function scan_dlc_packages(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const enginePath = process.env.RPGMAKER_ENGINE_PATH;
    if (!enginePath) {
        return jsonText({ ok: false, status: "ENV-BLOCKED", message: "RPGMAKER_ENGINE_PATH not set" });
    }
    const dlcRoot = path.join(enginePath, "dlc");
    try {
        const entries = await fs.readdir(dlcRoot, { withFileTypes: true });
        const packages = entries.filter((e) => e.isDirectory()).map((e) => e.name).sort();
        return jsonText({ ok: true, source: dlcRoot, packages });
    } catch {
        return jsonText({ ok: true, source: dlcRoot, packages: [], note: "dlc directory not found" });
    }
}
