import fs from "fs/promises";
import path from "path";
import { withBackup, cleanupOldBackups } from "../../utils/backup.js";
import { Logger } from "../../utils/logger.js";
import { Errors } from "../../utils/errors.js";

export async function readDataJson<T>(projectPath: string, filename: string): Promise<T> {
    const fp = path.join(projectPath, "data", filename);
    try {
        const raw = await fs.readFile(fp, "utf-8");
        return JSON.parse(raw) as T;
    } catch (e: unknown) {
        const err = e as NodeJS.ErrnoException;
        if (err?.code === "ENOENT") {
            throw Errors.dataFileReadError(filename, "file not found");
        }
        throw Errors.dataFileReadError(filename, err?.message ?? String(e));
    }
}

export async function writeDataJson(projectPath: string, filename: string, data: unknown): Promise<void> {
    const fp = path.join(projectPath, "data", filename);
    await withBackup(fp, async () => {
        await fs.writeFile(fp, JSON.stringify(data, null, 2), "utf-8");
    });
    cleanupOldBackups(fp).catch(async (e: unknown) => {
        await Logger.debug(`Failed to cleanup old backups for ${fp}`, e).catch(() => {});
    });
}
