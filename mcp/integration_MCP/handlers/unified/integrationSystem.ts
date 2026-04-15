import { validateProjectPath } from "../../utils/validation.js";
import { readDataJson, writeDataJson } from "./jsonFile.js";
import { HandlerResponse } from "../../types/index.js";

type ProjectArgs = { projectPath: string };

type SystemJson = Record<string, unknown> & {
    gameTitle?: string;
    variables?: string[];
    switches?: string[];
    startMapId?: number;
    startX?: number;
    startY?: number;
};

function jsonText(data: unknown): HandlerResponse {
    return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
}

function ensureStringArray(arr: unknown, minLen: number): string[] {
    const a = Array.isArray(arr) ? [...(arr as string[])] : [];
    while (a.length <= minLen) a.push("");
    return a;
}

export async function get_system(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const sys = await readDataJson<SystemJson>(args.projectPath, "System.json");
    return jsonText(sys);
}

export async function get_variables(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const sys = await readDataJson<SystemJson>(args.projectPath, "System.json");
    const vars = ensureStringArray(sys.variables, 1);
    return jsonText(vars);
}

export async function set_variable_name(args: ProjectArgs & { variableId: number; name: string }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const sys = await readDataJson<SystemJson>(args.projectPath, "System.json");
    const vars = ensureStringArray(sys.variables, args.variableId);
    vars[args.variableId] = args.name;
    sys.variables = vars;
    await writeDataJson(args.projectPath, "System.json", sys);
    return jsonText({ ok: true, variableId: args.variableId, name: args.name });
}

export async function get_switches(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const sys = await readDataJson<SystemJson>(args.projectPath, "System.json");
    const sw = ensureStringArray(sys.switches, 1);
    return jsonText(sw);
}

export async function set_switch_name(args: ProjectArgs & { switchId: number; name: string }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const sys = await readDataJson<SystemJson>(args.projectPath, "System.json");
    const sw = ensureStringArray(sys.switches, args.switchId);
    sw[args.switchId] = args.name;
    sys.switches = sw;
    await writeDataJson(args.projectPath, "System.json", sys);
    return jsonText({ ok: true, switchId: args.switchId, name: args.name });
}

export async function get_game_title(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const sys = await readDataJson<SystemJson>(args.projectPath, "System.json");
    return jsonText(sys.gameTitle ?? "");
}

export async function update_game_title(args: ProjectArgs & { title: string }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const sys = await readDataJson<SystemJson>(args.projectPath, "System.json");
    sys.gameTitle = args.title;
    await writeDataJson(args.projectPath, "System.json", sys);
    return jsonText({ ok: true, gameTitle: args.title });
}

export async function update_starting_position(
    args: ProjectArgs & { mapId: number; x: number; y: number }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const sys = await readDataJson<SystemJson>(args.projectPath, "System.json");
    sys.startMapId = args.mapId;
    sys.startX = args.x;
    sys.startY = args.y;
    await writeDataJson(args.projectPath, "System.json", sys);
    return jsonText({ ok: true, startMapId: args.mapId, startX: args.x, startY: args.y });
}
