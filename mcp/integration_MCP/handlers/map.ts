import { validateProjectPath } from "../utils/validation.js";
import { loadMapData, saveMapData } from "../utils/mapHelpers.js";
import { LIMITS } from "../utils/constants.js";
import { Errors } from "../utils/errors.js";
import { HandlerResponse, MapData } from "../types/index.js";
import fs from "fs/promises";
import path from "path";

type ProjectArgs = { projectPath: string };
type DrawMapTileArgs = ProjectArgs & { mapId: number; x: number; y: number; layer: number; tileId: number };
type CreateMapArgs = ProjectArgs & { mapName: string; width?: number; height?: number; tilesetId?: number };

export async function drawMapTile(args: DrawMapTileArgs): Promise<HandlerResponse> {
    const { projectPath, mapId, x, y, layer, tileId } = args;
    await validateProjectPath(projectPath);

    const mapData = await loadMapData(projectPath, mapId);
    const width = mapData.width;
    const height = mapData.height;

    if (x < 0 || x >= width || y < 0 || y >= height) {
        throw Errors.invalidParameter("coordinates", `Coordinates (${x},${y}) out of bounds (W:${width}, H:${height})`);
    }
    if (layer < LIMITS.MIN_LAYER || layer > LIMITS.MAX_LAYER) {
        throw Errors.invalidParameter("layer", `Layer ${layer} out of bounds (${LIMITS.MIN_LAYER}-${LIMITS.MAX_LAYER})`);
    }

    // Calculate index in flattened array: (z * height + y) * width + x
    const index = (layer * height + y) * width + x;

    if (index >= mapData.data.length) {
        throw Errors.invalidParameter("index", `Calculated index ${index} out of bounds`);
    }

    mapData.data[index] = tileId;

    await saveMapData(projectPath, mapId, mapData);

    return {
        content: [{ type: "text", text: `Successfully drew tile ${tileId} at (${x},${y}) on layer ${layer}.` }],
    };
}

export async function createMap(args: CreateMapArgs): Promise<HandlerResponse> {
    const { projectPath, mapName, width = 17, height = 13, tilesetId = 1 } = args;
    await validateProjectPath(projectPath);

    const dataDir = path.join(projectPath, "data");

    // Read MapInfos.json to get next available ID
    const mapInfosPath = path.join(dataDir, "MapInfos.json");
    let mapInfos: Array<Record<string, unknown> | null> = [];
    try {
        mapInfos = JSON.parse(await fs.readFile(mapInfosPath, "utf-8")) as Array<Record<string, unknown> | null>;
    } catch (e: unknown) {
        // If it doesn't exist, start with [null]
        mapInfos = [null];
    }

    const newMapId = mapInfos.length;
    const mapIdPadded = String(newMapId).padStart(3, "0");

    // Create new map data
    const newMapData: MapData & { encounterList?: unknown[]; encounterStep?: number; encoding?: string } = {
        autoplayBgm: false,
        autoplayBgs: false,
        battleback1Name: "",
        battleback2Name: "",
        bgm: { name: "", pan: 0, pitch: 100, volume: 90 },
        bgs: { name: "", pan: 0, pitch: 100, volume: 90 },
        disableDashing: false,
        displayName: mapName,
        encoding: "UTF-8",
        encounterList: [],
        encounterStep: 30,
        height: height,
        width: width,
        note: "",
        parallaxLoopX: false,
        parallaxLoopY: false,
        parallaxName: "",
        parallaxShow: true,
        parallaxSx: 0,
        parallaxSy: 0,
        scrollType: 0,
        specifyBattleback: false,
        tilesetId: tilesetId,
        data: new Array(width * height * 6).fill(0),
        events: {}
    };

    // Save new map file
    const newMapPath = path.join(dataDir, `Map${mapIdPadded}.json`);
    await fs.writeFile(newMapPath, JSON.stringify(newMapData, null, 2), "utf-8");

    // Update MapInfos.json
    mapInfos.push({
        id: newMapId,
        expanded: false,
        name: mapName,
        order: newMapId,
        parentId: 0,
        scrollX: 0,
        scrollY: 0
    });
    await fs.writeFile(mapInfosPath, JSON.stringify(mapInfos, null, 2), "utf-8");

    return {
        content: [{ type: "text", text: `Successfully created map "${mapName}" (ID: ${newMapId}, ${width}x${height}).` }],
    };
}
