import fs from "fs/promises";
import path from "path";
import { validateProjectPath, getFilesRecursively } from "../utils/validation.js";
import { Errors } from "../utils/errors.js";
import { withBackup, cleanupOldBackups } from "../utils/backup.js";
import { Logger } from "../utils/logger.js";

type HandlerContent = { type: "text"; text: string };
type HandlerResponse = { content: HandlerContent[] };

type ProjectArgs = { projectPath: string };
type DataFileArgs = ProjectArgs & { filename: string };
type WriteDataFileArgs = DataFileArgs & { content: string };
type AssetType = "img" | "audio" | "all";
type ListAssetsArgs = ProjectArgs & { assetType?: AssetType };

export async function getProjectInfo(args: ProjectArgs): Promise<HandlerResponse> {
    const { projectPath } = args;
    await validateProjectPath(projectPath);

    const systemPath = path.join(projectPath, "data", "System.json");
    const content = await fs.readFile(systemPath, "utf-8");
    const systemData = JSON.parse(content) as Record<string, unknown>;

    return {
        content: [
            {
                type: "text",
                text: JSON.stringify({
                    gameTitle: systemData.gameTitle,
                    versionId: systemData.versionId,
                    locale: systemData.locale,
                    currencyUnit: systemData.currencyUnit,
                }, null, 2),
            },
        ],
    };
}

export async function listDataFiles(args: ProjectArgs): Promise<HandlerResponse> {
    const { projectPath } = args;
    await validateProjectPath(projectPath);

    const dataDir = path.join(projectPath, "data");
    const files = await fs.readdir(dataDir);
    const jsonFiles = files.filter(f => f.endsWith(".json"));

    return {
        content: [
            {
                type: "text",
                text: JSON.stringify(jsonFiles, null, 2),
            },
        ],
    };
}

export async function readDataFile(args: DataFileArgs): Promise<HandlerResponse> {
    const { projectPath, filename } = args;
    await validateProjectPath(projectPath);

    if (!filename.endsWith(".json")) {
        throw new Error("Only .json files can be read");
    }

    // Normalize path to prevent directory traversal
    const normalizedFilename = path.normalize(filename).replace(/\\/g, "/");
    if (normalizedFilename.includes("..") || path.isAbsolute(normalizedFilename)) {
        throw Errors.assetPathInvalid(filename);
    }

    const filePath = path.join(projectPath, "data", normalizedFilename);
    const resolvedPath = path.resolve(filePath);

    // Check if file exists first
    try {
        await fs.access(resolvedPath);
    } catch {
        throw new Error(`File not found: ${filename}`);
    }

    // Resolve real path to prevent symlink attacks
    const realDataDir = await fs.realpath(path.resolve(projectPath, "data"));
    const realFilePath = await fs.realpath(resolvedPath);

    // Verify resolved path is within data directory
    if (!realFilePath.startsWith(realDataDir + path.sep) && realFilePath !== realDataDir) {
        throw Errors.assetPathInvalid(filename);
    }

    const content = await fs.readFile(realFilePath, "utf-8");

    return {
        content: [
            {
                type: "text",
                text: content,
            },
        ],
    };
}

export async function writeDataFile(args: WriteDataFileArgs): Promise<HandlerResponse> {
    const { projectPath, filename, content } = args;
    await validateProjectPath(projectPath);

    if (!filename.endsWith(".json")) {
        throw new Error("Only .json files can be written");
    }

    JSON.parse(content);

    // Normalize path to prevent directory traversal
    const normalizedFilename = path.normalize(filename).replace(/\\/g, "/");
    if (normalizedFilename.includes("..") || path.isAbsolute(normalizedFilename)) {
        throw Errors.assetPathInvalid(filename);
    }

    const resolvedDir = path.resolve(projectPath, "data");
    const resolvedPath = path.resolve(resolvedDir, normalizedFilename);

    // First check: normalized path must be within data directory
    if (!resolvedPath.startsWith(resolvedDir + path.sep) && resolvedPath !== resolvedDir) {
        throw Errors.assetPathInvalid(filename);
    }

    // Second check: resolve real paths to prevent symlink attacks
    const realDataDir = await fs.realpath(resolvedDir);
    // Check if file exists, if not, check parent directory
    let realFilePath: string;
    try {
        realFilePath = await fs.realpath(resolvedPath);
    } catch {
        // File doesn't exist yet, check parent directory
        realFilePath = await fs.realpath(path.dirname(resolvedPath));
    }

    // Verify resolved path is within real data directory
    if (!realFilePath.startsWith(realDataDir + path.sep) && realFilePath !== realDataDir) {
        throw Errors.assetPathInvalid(filename);
    }

    // Write with backup
    await withBackup(resolvedPath, async () => {
        await fs.writeFile(resolvedPath, content, "utf-8");
    });

    // Cleanup old backups (non-blocking)
    cleanupOldBackups(resolvedPath).catch(async (e: unknown) => {
        await Logger.debug(`Failed to cleanup old backups for ${resolvedPath} (non-critical)`, e).catch(() => {
            // Last resort: ignore logger errors
        });
    });

    return {
        content: [
            {
                type: "text",
                text: `Successfully wrote to ${filename}`,
            },
        ],
    };
}

export async function listAssets(args: ListAssetsArgs): Promise<HandlerResponse> {
    const { projectPath, assetType = "all" } = args;
    await validateProjectPath(projectPath);

    const results: Record<string, unknown> = {};

    if (assetType === "img" || assetType === "all") {
        const imgDir = path.join(projectPath, "img");
        try {
            const files = await getFilesRecursively(imgDir);
            results.img = files.map(f => path.relative(projectPath, f).replace(/\\/g, "/"));
        } catch (e) {
            const reason = e instanceof Error ? e.message : String(e);
            results.img = [`Error reading img directory: ${reason}`];
        }
    }

    if (assetType === "audio" || assetType === "all") {
        const audioDir = path.join(projectPath, "audio");
        try {
            const files = await getFilesRecursively(audioDir);
            results.audio = files.map(f => path.relative(projectPath, f).replace(/\\/g, "/"));
        } catch (e) {
            const reason = e instanceof Error ? e.message : String(e);
            results.audio = [`Error reading audio directory: ${reason}`];
        }
    }

    return {
        content: [
            {
                type: "text",
                text: JSON.stringify(results, null, 2),
            },
        ],
    };
}

export async function checkAssetsIntegrity(args: ProjectArgs): Promise<HandlerResponse> {
    const { projectPath } = args;
    await validateProjectPath(projectPath);

    const issues: Array<Record<string, unknown>> = [];
    const dataDir = path.join(projectPath, "data");

    const checkImageReferences = async (dataFile: string, propertyName: string): Promise<void> => {
        try {
            const filePath = path.join(dataDir, dataFile);
            const data = JSON.parse(await fs.readFile(filePath, "utf-8")) as Array<Record<string, any>>;

            for (const item of data) {
                if (!item) continue;
                const imageName = item[propertyName];
                if (imageName && imageName !== "") {
                    const imgPath = path.join(projectPath, "img", "characters", `${imageName}.png`);
                    try {
                        await fs.access(imgPath);
                    } catch (e: unknown) {
                        // Missing image is expected in some cases, log as debug
                        await Logger.debug(`Expected missing image (non-critical): ${imgPath}`, e);
                        issues.push({
                            type: "missing_image",
                            file: dataFile,
                            itemId: item.id,
                            itemName: item.name || "Unknown",
                            imageName: imageName,
                            expectedPath: `img/characters/${imageName}.png`
                        });
                    }
                }
            }
        } catch (e: unknown) {
            // Expected file not found is non-critical for integrity check
            await Logger.debug(`Expected data file not found (non-critical): ${dataFile}`, e);
        }
    };

    await checkImageReferences("Actors.json", "characterName");

    try {
        const mapInfosPath = path.join(dataDir, "MapInfos.json");
        const mapInfos = JSON.parse(await fs.readFile(mapInfosPath, "utf-8")) as Record<number, unknown>;
        const mapFiles = await fs.readdir(dataDir);

        for (const file of mapFiles) {
            const match = file.match(/^Map(\d{3})\.json$/);
            if (match) {
                const mapId = parseInt(match[1]);
                if (!mapInfos[mapId]) {
                    issues.push({
                        type: "orphaned_map",
                        file: file,
                        mapId: mapId
                    });
                }
            }
        }
    } catch (e: unknown) {
        // Expected errors during integrity check are non-critical
        await Logger.debug(`Expected error during integrity check (non-critical)`, e);
    }

    return {
        content: [{
            type: "text",
            text: issues.length === 0
                ? "No asset integrity issues found."
                : `Found ${issues.length} issue(s):\n${JSON.stringify(issues, null, 2)}`
        }]
    };
}
