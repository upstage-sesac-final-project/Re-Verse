import { validateProjectPath } from "../utils/validation.js";
import { loadMapData, saveMapData, getEventPageList } from "../utils/mapHelpers.js";
import { annotateCommand } from "../utils/commandAnnotator.js";
import { EVENT_CODES } from "../utils/constants.js";
import { HandlerResponse, EventCommand } from "../types/index.js";
import { validateEventCommand } from "../schemas/mz_structures.js";
import { Errors } from "../utils/errors.js";
import { Logger } from "../utils/logger.js";
import fs from "fs/promises";
import path from "path";

type ProjectArgs = { projectPath: string };
type EventPageArgs = ProjectArgs & { mapId: number; eventId: number; pageIndex: number };
type EventCommandArgs = EventPageArgs & { insertPosition: number };
type AddDialogueArgs = EventCommandArgs & { text: string; face?: string; faceIndex?: number; background?: number; position?: number };
type AddChoiceArgs = EventCommandArgs & { options: string[]; cancelType?: number };
type ShowPictureArgs = EventCommandArgs & { pictureId?: number; pictureName: string; origin?: number; x?: number; y?: number };
type AddConditionalBranchArgs = EventCommandArgs & { condition: { code: number; dataA: number; operation: number; dataB: number; class?: number }; includeElse?: boolean };
type DeleteEventCommandArgs = EventPageArgs & { commandIndex: number };
type UpdateEventCommandArgs = EventPageArgs & { commandIndex: number; newCommand: EventCommand };
type SearchEventsArgs = ProjectArgs & { query: string };

export async function getEventPage(args: EventPageArgs): Promise<HandlerResponse> {
    const { projectPath, mapId, eventId, pageIndex } = args;
    await validateProjectPath(projectPath);
    const mapData = await loadMapData(projectPath, mapId);
    const list = getEventPageList(mapData, String(eventId), pageIndex, mapId);
    const annotatedList = list.map(annotateCommand);
    return { content: [{ type: "text", text: JSON.stringify(annotatedList, null, 2) }] };
}

export async function addDialogue(args: AddDialogueArgs): Promise<HandlerResponse> {
    const { projectPath, mapId, eventId, pageIndex, insertPosition, text, face = "", faceIndex = 0, background = 0, position = 2 } = args;
    await validateProjectPath(projectPath);
    const mapData = await loadMapData(projectPath, mapId);
    const list = getEventPageList(mapData, String(eventId), pageIndex, mapId);
    const pos = insertPosition === -1 ? list.length - 1 : insertPosition;
    const cmds: EventCommand[] = [];
    cmds.push({ code: EVENT_CODES.SHOW_TEXT, indent: 0, parameters: [face, faceIndex, background, position] });
    const lines = text.split('\n');
    lines.forEach(line => { cmds.push({ code: EVENT_CODES.TEXT_DATA, indent: 0, parameters: [line] }); });
    list.splice(pos, 0, ...cmds);
    await saveMapData(projectPath, mapId, mapData);
    return { content: [{ type: "text", text: "Added dialogue." }] };
}

export async function addChoice(args: AddChoiceArgs): Promise<HandlerResponse> {
    const { projectPath, mapId, eventId, pageIndex, insertPosition, options, cancelType = -1 } = args;
    await validateProjectPath(projectPath);

    const mapData = await loadMapData(projectPath, mapId);
    const list = getEventPageList(mapData, String(eventId), pageIndex, mapId);
    const pos = insertPosition === -1 ? list.length - 1 : insertPosition;

    const cmds: EventCommand[] = [];
    // Show Choices
    cmds.push({ code: EVENT_CODES.SHOW_CHOICES, indent: 0, parameters: [options, cancelType] });

    // When [choice]
    options.forEach((opt, i) => {
        cmds.push({ code: EVENT_CODES.CHOICE_WHEN, indent: 0, parameters: [i, opt] });
        cmds.push({ code: 0, indent: 1, parameters: [] }); // Empty command for content
    });

    // End
    cmds.push({ code: EVENT_CODES.CHOICE_END, indent: 0, parameters: [] });

    list.splice(pos, 0, ...cmds);
    await saveMapData(projectPath, mapId, mapData);

    return { content: [{ type: "text", text: `Added choice with ${options.length} options.` }] };
}

export async function showPicture(args: ShowPictureArgs): Promise<HandlerResponse> {
    const { projectPath, mapId, eventId, pageIndex, insertPosition, pictureId = 1, pictureName, origin = 0, x = 0, y = 0 } = args;
    await validateProjectPath(projectPath);

    const mapData = await loadMapData(projectPath, mapId);
    const list = getEventPageList(mapData, String(eventId), pageIndex, mapId);
    const pos = insertPosition === -1 ? list.length - 1 : insertPosition;

    // Show Picture
    // parameters: [pictureId, pictureName, origin, x, y, scaleX, scaleY, opacity, blendMode]
    const cmd: EventCommand = {
        code: EVENT_CODES.SHOW_PICTURE,
        indent: 0,
        parameters: [pictureId, pictureName, origin, x, y, 100, 100, 255, 0]
    };

    list.splice(pos, 0, cmd);
    await saveMapData(projectPath, mapId, mapData);

    return { content: [{ type: "text", text: `Added show picture command for "${pictureName}" (ID: ${pictureId}).` }] };
}

export async function addLoop(args: EventCommandArgs): Promise<HandlerResponse> {
    const { projectPath, mapId, eventId, pageIndex, insertPosition } = args;
    await validateProjectPath(projectPath);

    const mapData = await loadMapData(projectPath, mapId);
    const list = getEventPageList(mapData, String(eventId), pageIndex, mapId);

    const pos = insertPosition === -1 ? list.length - 1 : insertPosition;

    const loopCmd: EventCommand = { code: EVENT_CODES.LOOP, indent: 0, parameters: [] };
    const repeatCmd: EventCommand = { code: EVENT_CODES.LOOP_REPEAT, indent: 0, parameters: [] };

    list.splice(pos, 0, loopCmd, repeatCmd);

    await saveMapData(projectPath, mapId, mapData);

    return {
        content: [{ type: "text", text: "Successfully added Loop block." }],
    };
}

export async function addBreakLoop(args: EventCommandArgs): Promise<HandlerResponse> {
    const { projectPath, mapId, eventId, pageIndex, insertPosition } = args;
    await validateProjectPath(projectPath);

    const mapData = await loadMapData(projectPath, mapId);
    const list = getEventPageList(mapData, String(eventId), pageIndex, mapId);

    const pos = insertPosition === -1 ? list.length - 1 : insertPosition;
    const cmd: EventCommand = { code: EVENT_CODES.BREAK_LOOP, indent: 0, parameters: [] };

    list.splice(pos, 0, cmd);

    await saveMapData(projectPath, mapId, mapData);

    return {
        content: [{ type: "text", text: "Successfully added Break Loop command." }],
    };
}

export async function addConditionalBranch(args: AddConditionalBranchArgs): Promise<HandlerResponse> {
    const { projectPath, mapId, eventId, pageIndex, insertPosition, condition, includeElse = true } = args;
    await validateProjectPath(projectPath);

    const mapData = await loadMapData(projectPath, mapId);
    const list = getEventPageList(mapData, String(eventId), pageIndex, mapId);

    const pos = insertPosition === -1 ? list.length - 1 : insertPosition;

    const params = [
        condition.code,
        condition.dataA,
        condition.operation,
        condition.dataB,
        condition.class || 0
    ];

    const branchStart: EventCommand = { code: EVENT_CODES.CONDITIONAL_BRANCH, indent: 0, parameters: params };
    const elseCmd: EventCommand = { code: EVENT_CODES.CONDITIONAL_ELSE, indent: 0, parameters: [] };
    const branchEnd: EventCommand = { code: EVENT_CODES.CONDITIONAL_END, indent: 0, parameters: [] };

    if (includeElse) {
        list.splice(pos, 0, branchStart, elseCmd, branchEnd);
    } else {
        list.splice(pos, 0, branchStart, branchEnd);
    }

    await saveMapData(projectPath, mapId, mapData);

    return {
        content: [{ type: "text", text: "Successfully added Conditional Branch." }],
    };
}

export async function deleteEventCommand(args: DeleteEventCommandArgs): Promise<HandlerResponse> {
    const { projectPath, mapId, eventId, pageIndex, commandIndex } = args;
    await validateProjectPath(projectPath);

    const mapData = await loadMapData(projectPath, mapId);
    const list = getEventPageList(mapData, String(eventId), pageIndex, mapId);

    if (commandIndex < 0 || commandIndex >= list.length) {
        throw new Error(`Command index ${commandIndex} out of bounds (0-${list.length - 1})`);
    }

    list.splice(commandIndex, 1);

    await saveMapData(projectPath, mapId, mapData);

    return {
        content: [{ type: "text", text: `Successfully deleted command at index ${commandIndex}.` }],
    };
}

export async function updateEventCommand(args: UpdateEventCommandArgs): Promise<HandlerResponse> {
    const { projectPath, mapId, eventId, pageIndex, commandIndex, newCommand } = args;
    await validateProjectPath(projectPath);

    // Zod 검증
    const validation = validateEventCommand(newCommand);
    if (!validation.success) {
        throw Errors.invalidParameter("newCommand", validation.error.issues.map(e => `${e.path.join('.')}: ${e.message}`).join(', '));
    }

    const mapData = await loadMapData(projectPath, mapId);
    const list = getEventPageList(mapData, String(eventId), pageIndex, mapId);

    if (commandIndex < 0 || commandIndex >= list.length) {
        throw new Error(`Command index ${commandIndex} out of bounds (0-${list.length - 1})`);
    }

    list[commandIndex] = newCommand;

    await saveMapData(projectPath, mapId, mapData);

    return {
        content: [{ type: "text", text: `Successfully updated command at index ${commandIndex}.` }],
    };
}

export async function searchEvents(args: SearchEventsArgs): Promise<HandlerResponse> {
    const { projectPath, query } = args;
    await validateProjectPath(projectPath);

    const matches: Array<Record<string, unknown>> = [];
    const dataDir = path.join(projectPath, "data");

    const searchInList = (list: Array<Record<string, unknown> | null> | undefined, sourceName: string): void => {
        if (!list) return;
        list.forEach((ev) => {
            if (!ev) return;
            const eventName = (ev.name as string | undefined) || `Event ${ev.id as number}`;
            const pages = ev.pages as Array<Record<string, unknown>> | undefined;
            if (pages) {
                pages.forEach((page, pageIndex) => {
                    const list = page.list as Array<EventCommand> | undefined;
                    if (list) {
                        list.forEach((cmd, cmdIndex) => {
                            const paramStr = JSON.stringify(cmd.parameters);
                            const codeStr = cmd.code.toString();
                            if (paramStr.includes(query) || (query === codeStr)) {
                                matches.push({
                                    source: sourceName,
                                    event: eventName,
                                    eventId: ev.id,
                                    page: pageIndex + 1,
                                    line: cmdIndex + 1,
                                    code: cmd.code,
                                    parameters: cmd.parameters
                                });
                            }
                        });
                    }
                });
            }
        });
    };

    try {
        const commonEventsPath = path.join(dataDir, "CommonEvents.json");
        const commonEvents = JSON.parse(await fs.readFile(commonEventsPath, "utf-8")) as Array<Record<string, unknown> | null>;
        searchInList(commonEvents, "CommonEvents");
    } catch (e: unknown) {
        // Expected file not found is non-critical for search
        await Logger.debug(`Expected CommonEvents.json not found (non-critical)`, e);
    }

    try {
        const mapInfosPath = path.join(dataDir, "MapInfos.json");
        const mapInfos = JSON.parse(await fs.readFile(mapInfosPath, "utf-8")) as Array<Record<string, unknown> | null>;
        for (const mapInfo of mapInfos) {
            if (!mapInfo) continue;
            const mapId = (mapInfo.id as number).toString().padStart(3, "0");
            const mapFilename = `Map${mapId}.json`;
            const mapPath = path.join(dataDir, mapFilename);
            try {
                const mapData = JSON.parse(await fs.readFile(mapPath, "utf-8")) as Record<string, unknown>;
                const events = mapData.events as Record<string, Record<string, unknown> | null> | undefined;
                if (events) {
                    searchInList(Object.values(events), `Map ${mapInfo.id}: ${mapInfo.name as string}`);
                }
            } catch (e: unknown) {
                // Expected file not found is non-critical for search
                await Logger.debug(`Expected map file not found (non-critical): ${mapFilename}`, e);
            }
        }
    } catch (e: unknown) {
        // Expected file not found is non-critical for search
        await Logger.debug(`Expected MapInfos.json not found (non-critical)`, e);
    }

    return {
        content: [{ type: "text", text: JSON.stringify(matches, null, 2) }],
    };
}
