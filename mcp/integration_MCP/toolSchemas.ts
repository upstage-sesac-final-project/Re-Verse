// Tool schemas for implemented tools (keep in sync with index.ts toolMap)

import { unifiedToolSchemas } from "./unifiedToolSchemas.js";
import type { ToolSchema } from "./toolSchemaTypes.js";

export type { ToolSchema };

export const toolSchemas: ToolSchema[] = [
    {
        name: "get_project_info",
        description: "Get basic information about the RPG Maker MZ project from System.json",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string", description: "Absolute path to the RPG Maker MZ project folder" }
            },
            required: ["projectPath"]
        }
    },
    {
        name: "list_data_files",
        description: "List all JSON data files in the project's data directory",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" }
            },
            required: ["projectPath"]
        }
    },
    {
        name: "read_data_file",
        description: "Read a specific data file from the data directory",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                filename: { type: "string", description: "Name of the JSON file to read (e.g., 'Actors.json')" }
            },
            required: ["projectPath", "filename"]
        }
    },
    {
        name: "write_data_file",
        description: "Write to a data file in the data directory",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                filename: { type: "string" },
                content: { type: "string", description: "JSON string content to write" }
            },
            required: ["projectPath", "filename", "content"]
        }
    },
    {
        name: "search_events",
        description: "Search for text or command codes in map and common events",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                query: { type: "string", description: "Search query (text or command code)" }
            },
            required: ["projectPath", "query"]
        }
    },
    {
        name: "get_event_page",
        description: "Get event page commands with readable annotations",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                mapId: { type: "number" },
                eventId: { type: "number" },
                pageIndex: { type: "number" }
            },
            required: ["projectPath", "mapId", "eventId", "pageIndex"]
        }
    },
    {
        name: "list_assets",
        description: "List assets in img and audio directories",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                assetType: { type: "string", enum: ["img", "audio", "all"], default: "all" }
            },
            required: ["projectPath"]
        }
    },
    {
        name: "write_plugin_code",
        description: "Write a plugin file to js/plugins directory",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                filename: { type: "string" },
                code: { type: "string" }
            },
            required: ["projectPath", "filename", "code"]
        }
    },
    {
        name: "get_plugins_config",
        description: "Read current plugins configuration from js/plugins.js",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" }
            },
            required: ["projectPath"]
        }
    },
    {
        name: "update_plugins_config",
        description: "Update plugins configuration in js/plugins.js",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                plugins: {
                    type: "array",
                    items: {
                        type: "object",
                        properties: {
                            name: { type: "string" },
                            status: { type: "boolean" },
                            description: { type: "string" }
                        },
                        required: ["name", "status"]
                    },
                    description: "Array of plugin configuration objects"
                }
            },
            required: ["projectPath", "plugins"]
        }
    },
    {
        name: "add_dialogue",
        description: "Add dialogue text to an event",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                mapId: { type: "number" },
                eventId: { type: "number" },
                pageIndex: { type: "number" },
                insertPosition: { type: "number" },
                text: { type: "string" },
                face: { type: "string", default: "" },
                faceIndex: { type: "number", default: 0 },
                background: { type: "number", default: 0 },
                position: { type: "number", default: 2 }
            },
            required: ["projectPath", "mapId", "eventId", "pageIndex", "insertPosition", "text"]
        }
    },
    {
        name: "add_choice",
        description: "Add a choice selection to an event",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                mapId: { type: "number" },
                eventId: { type: "number" },
                pageIndex: { type: "number" },
                insertPosition: { type: "number" },
                options: { type: "array", items: { type: "string" }, description: "Choice options" },
                cancelType: { type: "number", default: -1, description: "Cancel behavior: -1=disallow, 0-n=branch to option" }
            },
            required: ["projectPath", "mapId", "eventId", "pageIndex", "insertPosition", "options"]
        }
    },
    {
        name: "add_loop",
        description: "Add a loop structure to an event",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                mapId: { type: "number" },
                eventId: { type: "number" },
                pageIndex: { type: "number" },
                insertPosition: { type: "number" }
            },
            required: ["projectPath", "mapId", "eventId", "pageIndex", "insertPosition"]
        }
    },
    {
        name: "add_break_loop",
        description: "Add a break loop command to an event",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                mapId: { type: "number" },
                eventId: { type: "number" },
                pageIndex: { type: "number" },
                insertPosition: { type: "number" }
            },
            required: ["projectPath", "mapId", "eventId", "pageIndex", "insertPosition"]
        }
    },
    {
        name: "add_conditional_branch",
        description: "Add a conditional branch to an event",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                mapId: { type: "number" },
                eventId: { type: "number" },
                pageIndex: { type: "number" },
                insertPosition: { type: "number" },
                condition: {
                    type: "object",
                    properties: {
                        code: { type: "number", description: "Condition code" },
                        dataA: { type: "number", description: "First data value" },
                        operation: { type: "number", description: "Operation type" },
                        dataB: { type: "number", description: "Second data value" },
                        class: { type: "number", description: "Optional class ID" }
                    },
                    required: ["code", "dataA", "operation", "dataB"]
                },
                includeElse: { type: "boolean", default: true }
            },
            required: ["projectPath", "mapId", "eventId", "pageIndex", "insertPosition", "condition"]
        }
    },
    {
        name: "delete_event_command",
        description: "Delete an event command at specified index",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                mapId: { type: "number" },
                eventId: { type: "number" },
                pageIndex: { type: "number" },
                commandIndex: { type: "number" }
            },
            required: ["projectPath", "mapId", "eventId", "pageIndex", "commandIndex"]
        }
    },
    {
        name: "update_event_command",
        description: "Update an event command at specified index",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                mapId: { type: "number" },
                eventId: { type: "number" },
                pageIndex: { type: "number" },
                commandIndex: { type: "number" },
                newCommand: { type: "object" }
            },
            required: ["projectPath", "mapId", "eventId", "pageIndex", "commandIndex", "newCommand"]
        }
    },
    {
        name: "create_actor",
        description: "Add a new actor to the database",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                name: { type: "string" },
                classId: { type: "number", default: 1 },
                initialLevel: { type: "number", default: 1 },
                maxLevel: { type: "number", default: 99 }
            },
            required: ["projectPath", "name"]
        }
    },
    {
        name: "create_item",
        description: "Add a new item to the database",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                name: { type: "string" },
                price: { type: "number", default: 0 },
                consumable: { type: "boolean", default: true },
                scope: { type: "number", default: 7 },
                occasion: { type: "number", default: 0 }
            },
            required: ["projectPath", "name"]
        }
    },
    {
        name: "create_skill",
        description: "Add a new skill to the database",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                name: { type: "string" },
                mpCost: { type: "number", default: 0 },
                tpCost: { type: "number", default: 0 },
                scope: { type: "number", default: 1 },
                occasion: { type: "number", default: 1 }
            },
            required: ["projectPath", "name"]
        }
    },
    {
        name: "draw_map_tile",
        description: "Draw a tile on the map",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                mapId: { type: "number" },
                x: { type: "number" },
                y: { type: "number" },
                layer: { type: "number", description: "0-3: Map Layers, 4: Shadow, 5: Region" },
                tileId: { type: "number" }
            },
            required: ["projectPath", "mapId", "x", "y", "layer", "tileId"]
        }
    },
    {
        name: "inspect_game_state",
        description: "Inspect game variables and switches via Puppeteer. Requires game running with --remote-debugging-port.",
        inputSchema: {
            type: "object",
            properties: {
                port: { type: "number", default: 9222, description: "Remote debugging port" },
                script: { type: "string", description: "JavaScript code to evaluate (e.g. '$gameVariables.value(1)')" }
            },
            required: ["script"]
        }
    },
    {
        name: "create_map",
        description: "Create a new map in the project",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                mapName: { type: "string" },
                width: { type: "number", default: 17 },
                height: { type: "number", default: 13 },
                tilesetId: { type: "number", default: 1 }
            },
            required: ["projectPath", "mapName"]
        }
    },
    {
        name: "show_picture",
        description: "Show a picture in an event",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                mapId: { type: "number" },
                eventId: { type: "number" },
                pageIndex: { type: "number" },
                insertPosition: { type: "number" },
                pictureId: { type: "number", default: 1 },
                pictureName: { type: "string" },
                origin: { type: "number", default: 0, description: "0: Upper Left, 1: Center" },
                x: { type: "number", default: 0 },
                y: { type: "number", default: 0 }
            },
            required: ["projectPath", "mapId", "eventId", "pageIndex", "insertPosition", "pictureName"]
        }
    },
    {
        name: "check_assets_integrity",
        description: "Check for missing assets and orphaned files",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" }
            },
            required: ["projectPath"]
        }
    },
    {
        name: "run_playtest",
        description: "Run a playtest of the game. Launches Game.exe if available, otherwise uses browser-based fallback.",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                duration: { type: "number", default: 5000, description: "Time to wait before screenshot (ms)" },
                autoClose: { type: "boolean", default: false, description: "Automatically close game after screenshot" },
                debugPort: { type: "number", default: 9222, description: "Remote debugging port for Puppeteer" },
                startNewGame: { type: "boolean", default: false, description: "Skip title and start new game" },
                postLaunchScript: { type: "string", description: "JavaScript code to execute after game launch (e.g. input injection)" }
            },
            required: ["projectPath"]
        }
    },
    {
        name: "undo_last_change",
        description: "Restore a file from its latest backup. If filename is not specified, restores the most recently modified file.",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                filename: { type: "string", description: "Optional: specific JSON file to restore (e.g., 'Actors.json'). If omitted, restores the most recently modified file." }
            },
            required: ["projectPath"]
        }
    },
    {
        name: "list_backups",
        description: "List available backup files for a specific file or all files in the data directory.",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                filename: { type: "string", description: "Optional: specific JSON file to list backups for. If omitted, lists backups for all files." }
            },
            required: ["projectPath"]
        }
    },
    ...unifiedToolSchemas
];

// Tool registry (canonical names, aliases, profiles) — see tool-registry.json
export {
    resolveCanonicalToolName,
    resolveImplementationToolName,
    REGISTRY_VERSION,
    CANONICAL_TOOL_NAMES,
    TOOL_PROFILE_BY_NAME,
    DEFAULT_PROFILE_FLAGS,
} from "./generated/toolRegistry.generated.js";
