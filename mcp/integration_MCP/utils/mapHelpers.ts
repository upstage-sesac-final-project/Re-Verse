import fs from "fs/promises";
import path from "path";
import { Errors } from "./errors.js";
import type { MapData, EventCommand, Event } from "../types/index.js";
import { withBackup, cleanupOldBackups } from "./backup.js";
import { Logger } from "./logger.js";

/**
 * Some exports use an `events` array (index 0 = null). Normalize to Record<string, Event> for handlers.
 */
export function normalizeMapDataEvents(mapData: MapData): void {
    const raw = mapData.events as unknown;
    if (Array.isArray(raw)) {
        const rec: Record<string, Event> = {};
        for (let i = 0; i < raw.length; i++) {
            const ev = raw[i];
            if (ev != null && typeof ev === "object" && "id" in ev) {
                const e = ev as Event;
                rec[String(e.id)] = e;
            }
        }
        mapData.events = rec;
    }
}

/**
 * Loads map data from a project directory.
 * @throws {MCPError} If the map file cannot be read
 */
export async function loadMapData(projectPath: string, mapId: number): Promise<MapData> {
    const mapIdPadded = String(mapId).padStart(3, "0");
    const mapFilePath = path.join(projectPath, "data", `Map${mapIdPadded}.json`);
    try {
        const mapContent = await fs.readFile(mapFilePath, "utf-8");
        const mapData = JSON.parse(mapContent) as MapData;
        normalizeMapDataEvents(mapData);
        return mapData;
    } catch (e: unknown) {
        const err = e as NodeJS.ErrnoException;
        if (err?.code === 'ENOENT') {
            throw Errors.mapFileNotFound(mapId, projectPath);
        }
        const reason = err?.message ?? String(e);
        throw Errors.mapFileReadError(mapId, reason);
    }
}

/**
 * Saves map data to a project directory.
 */
export async function saveMapData(projectPath: string, mapId: number, mapData: MapData): Promise<void> {
    const mapIdPadded = String(mapId).padStart(3, "0");
    const mapFilePath = path.join(projectPath, "data", `Map${mapIdPadded}.json`);

    // Write with backup
    await withBackup(mapFilePath, async () => {
        await fs.writeFile(mapFilePath, JSON.stringify(mapData, null, 2), "utf-8");
    });

    // Cleanup old backups (non-blocking)
    cleanupOldBackups(mapFilePath).catch(async (e: unknown) => {
        await Logger.debug(`Failed to cleanup old backups for ${mapFilePath} (non-critical)`, e).catch(() => {
            // Last resort: ignore logger errors
        });
    });
}

/**
 * Gets the event page list from map data.
 */
export function getEventPageList(
    mapData: MapData,
    eventId: string | number,
    pageIndex: number,
    mapId: number | string | null = null
): EventCommand[] {
    const eventKey = String(eventId);
    const ownerMapId = mapId ?? 'unknown';
    if (!mapData.events[eventKey]) {
        throw Errors.eventNotFound(eventId, ownerMapId);
    }
    const event = mapData.events[eventKey];
    if (!event.pages[pageIndex]) {
        throw Errors.eventPageNotFound(eventId, pageIndex, ownerMapId);
    }
    return event.pages[pageIndex].list;
}
