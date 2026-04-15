import fs from "fs/promises";
import path from "path";
import { Logger } from "./logger.js";

/**
 * Creates a backup of a file before modification
 * @param filePath Path to the file to backup
 * @returns Path to the backup file
 */
export async function createBackup(filePath: string): Promise<string | null> {
    try {
        await fs.access(filePath);
    } catch {
        // New file: nothing to back up before first write
        return null;
    }

    const timestamp = Date.now();
    const dir = path.dirname(filePath);
    const basename = path.basename(filePath);
    const backupPath = path.join(dir, `${basename}.${timestamp}.bak`);

    try {
        await fs.copyFile(filePath, backupPath);
        await Logger.info(`Created backup: ${backupPath}`);
        return backupPath;
    } catch (error: unknown) {
        await Logger.error(`Failed to create backup for ${filePath}`, error);
        throw new Error(`Failed to create backup: ${error instanceof Error ? error.message : String(error)}`);
    }
}

/**
 * Executes an operation with automatic backup and rollback on failure
 * @param filePath Path to the file to backup
 * @param operation Async operation that modifies the file
 * @returns Result of the operation
 */
export async function withBackup<T>(
    filePath: string,
    operation: () => Promise<T>
): Promise<T> {
    const backupPath = await createBackup(filePath);

    try {
        return await operation();
    } catch (error: unknown) {
        if (backupPath) {
            try {
                await fs.copyFile(backupPath, filePath);
                await Logger.info(`Rolled back ${filePath} from backup ${backupPath}`);
            } catch (rollbackError: unknown) {
                await Logger.error(`Failed to rollback ${filePath}`, rollbackError);
                throw new Error(`Operation failed and rollback also failed: ${error instanceof Error ? error.message : String(error)}`);
            }
        }
        throw error;
    }
}

/**
 * Cleans up old backup files (keeps only the most recent N backups)
 * @param filePath Path to the original file
 * @param keepCount Number of backups to keep (default: 5)
 */
export async function cleanupOldBackups(filePath: string, keepCount: number = 5): Promise<void> {
    try {
        const dir = path.dirname(filePath);
        const basename = path.basename(filePath);
        const files = await fs.readdir(dir);

        // Find all backup files for this file
        const backupFiles = files
            .filter(f => f.startsWith(`${basename}.`) && f.endsWith('.bak'))
            .map(f => ({
                name: f,
                path: path.join(dir, f),
                timestamp: parseInt(f.replace(`${basename}.`, '').replace('.bak', ''), 10)
            }))
            .filter(f => !isNaN(f.timestamp))
            .sort((a, b) => b.timestamp - a.timestamp); // Newest first

        // Remove old backups
        if (backupFiles.length > keepCount) {
            const toRemove = backupFiles.slice(keepCount);
            for (const file of toRemove) {
                try {
                    await fs.unlink(file.path);
                    await Logger.debug(`Removed old backup: ${file.path}`);
                } catch (e: unknown) {
                    await Logger.error(`Failed to remove old backup ${file.path}`, e);
                }
            }
        }
    } catch (error: unknown) {
        // Non-critical, just log
        await Logger.debug(`Failed to cleanup old backups for ${filePath}`, error);
    }
}
