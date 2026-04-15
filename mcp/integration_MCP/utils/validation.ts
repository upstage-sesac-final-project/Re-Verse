import fs from "fs/promises";
import path from "path";
import { Errors, MCPError } from "./errors.js";

/**
 * Validates that the given path is a valid RPG Maker MZ project directory.
 * @throws {MCPError} If the path is invalid or not a valid RPG Maker MZ project
 */
export async function validateProjectPath(projectPath: string): Promise<void> {
    try {
        const stats = await fs.stat(projectPath);
        if (!stats.isDirectory()) {
            throw Errors.projectNotDirectory(projectPath);
        }
        const projectFile = path.join(projectPath, "game.rmmzproject");
        try {
            await fs.access(projectFile);
        } catch {
            throw Errors.projectFileNotFound(projectPath);
        }
    } catch (error: unknown) {
        if (error instanceof MCPError) {
            throw error;
        }
        const reason = error instanceof Error ? error.message : String(error);
        throw Errors.invalidProjectPath(projectPath, reason);
    }
}

/**
 * Recursively gets all files in a directory.
 */
export async function getFilesRecursively(dir: string): Promise<string[]> {
    const dirents = await fs.readdir(dir, { withFileTypes: true });
    const files = await Promise.all(dirents.map((dirent) => {
        const res = path.join(dir, dirent.name);
        return dirent.isDirectory() ? getFilesRecursively(res) : res;
    }));
    return Array.prototype.concat(...files);
}

/**
 * Sleeps for the specified number of milliseconds.
 */
export const sleep = (ms: number): Promise<void> =>
    new Promise(resolve => setTimeout(resolve, ms));
