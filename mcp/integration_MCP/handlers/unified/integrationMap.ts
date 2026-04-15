import { validateProjectPath } from "../../utils/validation.js";
import { loadMapData, saveMapData, getEventPageList } from "../../utils/mapHelpers.js";
import { HandlerResponse, Event, EventCommand, EventPage, MapData } from "../../types/index.js";
import { readDataJson } from "./jsonFile.js";
import { validateEventCommand } from "../../schemas/mz_structures.js";

type ProjectArgs = { projectPath: string };

function jsonText(data: unknown): HandlerResponse {
    return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
}

export async function list_maps(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    let infos: Array<Record<string, unknown> | null>;
    try {
        infos = await readDataJson<Array<Record<string, unknown> | null>>(args.projectPath, "MapInfos.json");
    } catch {
        infos = [null];
    }
    const list = infos
        .map((m, i) => {
            if (!m) return null;
            return { index: i, id: m.id, name: m.name, parentId: m.parentId, order: m.order };
        })
        .filter(Boolean);
    return jsonText(list);
}

export async function get_map_infos(args: ProjectArgs): Promise<HandlerResponse> {
    return list_maps(args);
}

export async function get_map(args: ProjectArgs & { mapId: number }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const map = await loadMapData(args.projectPath, args.mapId);
    return jsonText(map);
}

export async function update_map(args: ProjectArgs & { mapId: number; updates: Record<string, unknown> }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const map = await loadMapData(args.projectPath, args.mapId);
    const merged = { ...map, ...args.updates } as MapData;
    await saveMapData(args.projectPath, args.mapId, merged);
    return jsonText(merged);
}

export async function get_map_events(args: ProjectArgs & { mapId: number }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const map = await loadMapData(args.projectPath, args.mapId);
    const ev = map.events;
    const out: Array<{ id: number; name: string; x: number; y: number } | null> = [];
    for (const k of Object.keys(ev)) {
        const e = ev[k];
        if (e) out.push({ id: e.id, name: e.name, x: e.x, y: e.y });
    }
    out.sort((a, b) => (a && b ? a.id - b.id : 0));
    return jsonText(out);
}

export async function get_map_event(args: ProjectArgs & { mapId: number; eventId: number }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const map = await loadMapData(args.projectPath, args.mapId);
    const e = map.events[String(args.eventId)] ?? null;
    return jsonText(e);
}

function emptyEventPage(): EventPage {
    return {
        conditions: {
            actorId: 1,
            actorValid: false,
            itemId: 1,
            itemValid: false,
            selfSwitchCh: "A",
            selfSwitchValid: false,
            switch1Id: 1,
            switch1Valid: false,
            switch2Id: 1,
            switch2Valid: false,
            variableId: 1,
            variableValid: false,
            variableValue: 0,
        },
        image: {
            tileId: 0,
            characterName: "",
            direction: 2,
            pattern: 0,
            characterIndex: 0,
        },
        list: [{ code: 0, indent: 0, parameters: [] }],
        moveFrequency: 3,
        moveRoute: { list: [], repeat: false, skippable: false, wait: false },
        moveSpeed: 3,
        moveType: 0,
        priorityType: 1,
        stepAnime: false,
        through: false,
        trigger: 0,
        walkAnime: true,
    };
}

export async function create_map_event(
    args: ProjectArgs & {
        mapId: number;
        name: string;
        x: number;
        y: number;
        note?: string;
        pages?: EventPage[];
    }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const map = await loadMapData(args.projectPath, args.mapId);
    let maxId = 0;
    for (const k of Object.keys(map.events)) {
        const n = Number(k);
        if (!Number.isNaN(n) && n > maxId) maxId = n;
        const ev = map.events[k];
        if (ev && ev.id > maxId) maxId = ev.id;
    }
    const newId = maxId + 1;
    const pages = args.pages && args.pages.length > 0 ? args.pages : [emptyEventPage()];
    const newEvent: Event = {
        id: newId,
        name: args.name,
        note: args.note ?? "",
        pages,
        x: args.x,
        y: args.y,
    };
    map.events[String(newId)] = newEvent;
    await saveMapData(args.projectPath, args.mapId, map);
    return jsonText(newEvent);
}

export async function update_map_event(
    args: ProjectArgs & { mapId: number; eventId: number; updates: Record<string, unknown> }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const map = await loadMapData(args.projectPath, args.mapId);
    const key = String(args.eventId);
    const cur = map.events[key];
    if (!cur) throw new Error(`Event ${args.eventId} not found on map ${args.mapId}`);
    map.events[key] = { ...cur, ...(args.updates as Partial<Event>) } as Event;
    await saveMapData(args.projectPath, args.mapId, map);
    return jsonText(map.events[key]);
}

export async function search_map_events(args: ProjectArgs & { mapId: number; searchTerm: string }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const map = await loadMapData(args.projectPath, args.mapId);
    const q = args.searchTerm.toLowerCase();
    const out: Event[] = [];
    for (const k of Object.keys(map.events)) {
        const e = map.events[k];
        if (e && e.name.toLowerCase().includes(q)) out.push(e);
    }
    return jsonText(out);
}

export async function add_event_command(
    args: ProjectArgs & {
        mapId: number;
        eventId: number;
        pageIndex: number;
        command: EventCommand;
        position?: number;
    }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    validateEventCommand(args.command);
    const map = await loadMapData(args.projectPath, args.mapId);
    const list = getEventPageList(map, String(args.eventId), args.pageIndex, args.mapId);
    const pos =
        args.position !== undefined && args.position >= 0 && args.position <= list.length
            ? args.position
            : Math.max(0, list.length - 1);
    list.splice(pos, 0, args.command);
    await saveMapData(args.projectPath, args.mapId, map);
    return jsonText({ ok: true, insertedAt: pos });
}
