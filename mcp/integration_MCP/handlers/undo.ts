import fs from "fs/promises";
import path from "path";
import { validateProjectPath } from "../utils/validation.js";
import { HandlerResponse } from "../types/index.js";
import { Errors } from "../utils/errors.js";
import { Logger } from "../utils/logger.js";

type ProjectArgs = { projectPath: string };
type UndoLastChangeArgs = ProjectArgs & { filename?: string };
type ListBackupsArgs = ProjectArgs & { filename?: string };

/**
 * Finds the latest backup file for a given file
 */
async function findLatestBackup(filePath: string): Promise<string | null> {
    const dir = path.dirname(filePath);
    const basename = path.basename(filePath);

    try {
        const files = await fs.readdir(dir);

        const backupFiles = files
            .filter(f => f.startsWith(`${basename}.`) && f.endsWith('.bak'))
            .map(f => ({
                name: f,
                path: path.join(dir, f),
                timestamp: parseInt(f.replace(`${basename}.`, '').replace('.bak', ''), 10)
            }))
            .filter(f => !isNaN(f.timestamp))
            .sort((a, b) => b.timestamp - a.timestamp); // Newest first

        return backupFiles.length > 0 ? backupFiles[0].path : null;
    } catch (e: unknown) {
        await Logger.debug(`Failed to list backups for ${filePath}`, e);
        return null;
    }
}

/**
 * Restores a file from its latest backup
 */
export async function undoLastChange(args: UndoLastChangeArgs): Promise<HandlerResponse> {
    const { projectPath, filename } = args;
    await validateProjectPath(projectPath);

    let targetPath: string;

    if (filename) {
        // Restore specific file
        if (!filename.endsWith(".json")) {
            throw Errors.invalidParameter("filename", "Only .json files can be restored");
        }

        const normalizedFilename = path.normalize(filename).replace(/\\/g, "/");
        if (normalizedFilename.includes("..") || path.isAbsolute(normalizedFilename)) {
            throw Errors.assetPathInvalid(filename);
        }

        const resolvedDir = path.resolve(projectPath, "data");
        targetPath = path.resolve(resolvedDir, normalizedFilename);

        if (!targetPath.startsWith(resolvedDir + path.sep) && targetPath !== resolvedDir) {
            throw Errors.assetPathInvalid(filename);
        }
    } else {
        // Find the most recently modified file in data directory
        const dataDir = path.resolve(projectPath, "data");
        try {
            const files = await fs.readdir(dataDir);
            const jsonFiles = files.filter(f => f.endsWith(".json"));

            let latestFile: string | null = null;
            let latestTime = 0;

            for (const file of jsonFiles) {
                const filePath = path.join(dataDir, file);
                try {
                    const stats = await fs.stat(filePath);
                    if (stats.mtimeMs > latestTime) {
                        latestTime = stats.mtimeMs;
                        latestFile = filePath;
                    }
                } catch {
                    // Skip files we can't stat
                }
            }

            if (!latestFile) {
                throw new Error("No JSON files found in data directory");
            }

            targetPath = latestFile;
        } catch (e: unknown) {
            throw new Error(`Failed to find latest file: ${e instanceof Error ? e.message : String(e)}`);
        }
    }

    // Find latest backup
    const backupPath = await findLatestBackup(targetPath);

    if (!backupPath) {
        throw new Error(`No backup found for ${path.basename(targetPath)}`);
    }

    // Restore from backup
    try {
        await fs.copyFile(backupPath, targetPath);
        await Logger.info(`Restored ${targetPath} from backup ${backupPath}`);

        return {
            content: [
                {
                    type: "text",
                    text: `Successfully restored ${path.basename(targetPath)} from backup.`,
                },
            ],
        };
    } catch (e: unknown) {
        await Logger.error(`Failed to restore ${targetPath}`, e);
        throw new Error(`Failed to restore file: ${e instanceof Error ? e.message : String(e)}`);
    }
}

/**
 * Lists available backups for a file or all files in data directory
 */
export async function listBackups(args: ListBackupsArgs): Promise<HandlerResponse> {
    const { projectPath, filename } = args;
    await validateProjectPath(projectPath);

    const dataDir = path.resolve(projectPath, "data");
    const backups: Array<Record<string, unknown>> = [];

    if (filename) {
        // List backups for specific file
        if (!filename.endsWith(".json")) {
            throw Errors.invalidParameter("filename", "Only .json files can be listed");
        }

        const normalizedFilename = path.normalize(filename).replace(/\\/g, "/");
        if (normalizedFilename.includes("..") || path.isAbsolute(normalizedFilename)) {
            throw Errors.assetPathInvalid(filename);
        }

        const targetPath = path.resolve(dataDir, normalizedFilename);

        if (!targetPath.startsWith(dataDir + path.sep) && targetPath !== dataDir) {
            throw Errors.assetPathInvalid(filename);
        }

        const dir = path.dirname(targetPath);
        const basename = path.basename(targetPath);

        try {
            const files = await fs.readdir(dir);
            const backupFiles = files
                .filter(f => f.startsWith(`${basename}.`) && f.endsWith('.bak'))
                .map(f => ({
                    name: f,
                    path: path.join(dir, f),
                    timestamp: parseInt(f.replace(`${basename}.`, '').replace('.bak', ''), 10)
                }))
                .filter(f => !isNaN(f.timestamp))
                .sort((a, b) => b.timestamp - a.timestamp);

            backups.push({
                file: filename,
                backups: backupFiles.map(f => ({
                    backupFile: f.name,
                    timestamp: f.timestamp,
                    date: new Date(f.timestamp).toISOString()
                }))
            });
        } catch (e: unknown) {
            await Logger.debug(`Failed to list backups for ${filename}`, e);
        }
    } else {
        // List backups for all files in data directory
        try {
            const files = await fs.readdir(dataDir);
            const jsonFiles = files.filter(f => f.endsWith(".json"));

            for (const file of jsonFiles) {
                const filePath = path.join(dataDir, file);
                const basename = path.basename(filePath);

                try {
                    const allFiles = await fs.readdir(dataDir);
                    const backupFiles = allFiles
                        .filter(f => f.startsWith(`${basename}.`) && f.endsWith('.bak'))
                        .map(f => ({
                            name: f,
                            path: path.join(dataDir, f),
                            timestamp: parseInt(f.replace(`${basename}.`, '').replace('.bak', ''), 10)
                        }))
                        .filter(f => !isNaN(f.timestamp))
                        .sort((a, b) => b.timestamp - a.timestamp);

                    if (backupFiles.length > 0) {
                        backups.push({
                            file: file,
                            backups: backupFiles.map(f => ({
                                backupFile: f.name,
                                timestamp: f.timestamp,
                                date: new Date(f.timestamp).toISOString()
                            }))
                        });
                    }
                } catch {
                    // Skip files we can't process
                }
            }
        } catch (e: unknown) {
            await Logger.error(`Failed to list backups`, e);
            throw new Error(`Failed to list backups: ${e instanceof Error ? e.message : String(e)}`);
        }
    }

    return {
        content: [
            {
                type: "text",
                text: JSON.stringify(backups, null, 2),
            },
        ],
    };
}
