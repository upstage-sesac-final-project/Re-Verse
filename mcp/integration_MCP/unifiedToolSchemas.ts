import type { ToolSchema } from "./toolSchemaTypes.js";

const p = { projectPath: { type: "string", description: "Absolute path to the RPG Maker MZ project folder" } };

/**
 * Schemas for tools registered in index.ts (unified MCP 1–4 parity).
 */
export const unifiedToolSchemas: ToolSchema[] = [
    {
        name: "list_maps",
        description: "List maps from MapInfos.json",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "get_map_infos",
        description: "Alias: return MapInfos.json summary (same as list_maps)",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "get_map",
        description: "Load full MapNNN.json for a map id",
        inputSchema: {
            type: "object",
            properties: { ...p, mapId: { type: "number" } },
            required: ["projectPath", "mapId"],
        },
    },
    {
        name: "update_map",
        description: "Merge partial fields into MapNNN.json",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                mapId: { type: "number" },
                updates: { type: "object", description: "Fields to merge into map JSON" },
            },
            required: ["projectPath", "mapId", "updates"],
        },
    },
    {
        name: "get_map_events",
        description: "List events on a map (id, name, x, y)",
        inputSchema: {
            type: "object",
            properties: { ...p, mapId: { type: "number" } },
            required: ["projectPath", "mapId"],
        },
    },
    {
        name: "get_map_event",
        description: "Get one event object from a map",
        inputSchema: {
            type: "object",
            properties: { ...p, mapId: { type: "number" }, eventId: { type: "number" } },
            required: ["projectPath", "mapId", "eventId"],
        },
    },
    {
        name: "create_map_event",
        description: "Create a new map event (default page if pages omitted)",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                mapId: { type: "number" },
                name: { type: "string" },
                x: { type: "number" },
                y: { type: "number" },
                note: { type: "string" },
                pages: { type: "array", description: "Optional full pages array (RPG Maker MZ format)" },
            },
            required: ["projectPath", "mapId", "name", "x", "y"],
        },
    },
    {
        name: "update_map_event",
        description: "Merge updates into an existing event",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                mapId: { type: "number" },
                eventId: { type: "number" },
                updates: { type: "object" },
            },
            required: ["projectPath", "mapId", "eventId", "updates"],
        },
    },
    {
        name: "search_map_events",
        description: "Search events on a map by name substring",
        inputSchema: {
            type: "object",
            properties: { ...p, mapId: { type: "number" }, searchTerm: { type: "string" } },
            required: ["projectPath", "mapId", "searchTerm"],
        },
    },
    {
        name: "add_event_command",
        description: "Insert a raw event command into an event page list",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                mapId: { type: "number" },
                eventId: { type: "number" },
                pageIndex: { type: "number" },
                command: {
                    type: "object",
                    properties: {
                        code: { type: "number" },
                        indent: { type: "number" },
                        parameters: { type: "array" },
                    },
                    required: ["code", "indent", "parameters"],
                },
                position: { type: "number", description: "Insert index; default before implicit end" },
            },
            required: ["projectPath", "mapId", "eventId", "pageIndex", "command"],
        },
    },
    {
        name: "list_actors",
        description: "List actors (summary)",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "get_actor",
        description: "Get one actor by id",
        inputSchema: {
            type: "object",
            properties: { ...p, actorId: { type: "number" } },
            required: ["projectPath", "actorId"],
        },
    },
    {
        name: "update_actor",
        description: "Merge updates into an actor entry",
        inputSchema: {
            type: "object",
            properties: { ...p, actorId: { type: "number" }, updates: { type: "object" } },
            required: ["projectPath", "actorId", "updates"],
        },
    },
    {
        name: "search_actors",
        description: "Search actors by name or nickname",
        inputSchema: {
            type: "object",
            properties: { ...p, searchTerm: { type: "string" } },
            required: ["projectPath", "searchTerm"],
        },
    },
    {
        name: "list_items",
        description: "List items (summary)",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "update_item",
        description: "Merge updates into an item entry",
        inputSchema: {
            type: "object",
            properties: { ...p, itemId: { type: "number" }, updates: { type: "object" } },
            required: ["projectPath", "itemId", "updates"],
        },
    },
    {
        name: "search_items",
        description: "Search items by name or description",
        inputSchema: {
            type: "object",
            properties: { ...p, searchTerm: { type: "string" } },
            required: ["projectPath", "searchTerm"],
        },
    },
    {
        name: "list_skills",
        description: "List skills (summary)",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "get_skill",
        description: "Get one skill by id",
        inputSchema: {
            type: "object",
            properties: { ...p, skillId: { type: "number" } },
            required: ["projectPath", "skillId"],
        },
    },
    {
        name: "update_skill",
        description: "Merge updates into a skill entry",
        inputSchema: {
            type: "object",
            properties: { ...p, skillId: { type: "number" }, updates: { type: "object" } },
            required: ["projectPath", "skillId", "updates"],
        },
    },
    {
        name: "search_skills",
        description: "Search skills by name or description",
        inputSchema: {
            type: "object",
            properties: { ...p, searchTerm: { type: "string" } },
            required: ["projectPath", "searchTerm"],
        },
    },
    {
        name: "create_damage_skill",
        description: "Create an HP damage skill with formula",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                name: { type: "string" },
                damageFormula: { type: "string" },
                mpCost: { type: "number" },
                scope: { type: "number" },
                elementId: { type: "number" },
                description: { type: "string" },
            },
            required: ["projectPath", "name", "damageFormula"],
        },
    },
    {
        name: "create_healing_skill",
        description: "Create an HP recovery skill",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                name: { type: "string" },
                healFormula: { type: "string" },
                mpCost: { type: "number" },
                scope: { type: "number" },
                description: { type: "string" },
            },
            required: ["projectPath", "name", "healFormula"],
        },
    },
    {
        name: "create_buff_skill",
        description: "Create a skill that applies a buff (effect code 31)",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                name: { type: "string" },
                buffType: { type: "number" },
                turns: { type: "number" },
                mpCost: { type: "number" },
                scope: { type: "number" },
                description: { type: "string" },
            },
            required: ["projectPath", "name", "buffType", "turns"],
        },
    },
    {
        name: "create_state_skill",
        description: "Create a skill that applies a state (effect code 21)",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                name: { type: "string" },
                stateId: { type: "number" },
                chance: { type: "number" },
                mpCost: { type: "number" },
                scope: { type: "number" },
                description: { type: "string" },
            },
            required: ["projectPath", "name", "stateId", "chance"],
        },
    },
    {
        name: "list_weapons",
        description: "List weapons (summary)",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "create_weapon",
        description: "Append a weapon with default MZ-like fields",
        inputSchema: {
            type: "object",
            properties: { ...p, name: { type: "string" }, updates: { type: "object" } },
            required: ["projectPath", "name"],
        },
    },
    {
        name: "update_weapon",
        description: "Merge updates into a weapon entry",
        inputSchema: {
            type: "object",
            properties: { ...p, weaponId: { type: "number" }, updates: { type: "object" } },
            required: ["projectPath", "weaponId", "updates"],
        },
    },
    {
        name: "list_armors",
        description: "List armors (summary)",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "create_armor",
        description: "Append an armor with default MZ-like fields",
        inputSchema: {
            type: "object",
            properties: { ...p, name: { type: "string" }, updates: { type: "object" } },
            required: ["projectPath", "name"],
        },
    },
    {
        name: "update_armor",
        description: "Merge updates into an armor entry",
        inputSchema: {
            type: "object",
            properties: { ...p, armorId: { type: "number" }, updates: { type: "object" } },
            required: ["projectPath", "armorId", "updates"],
        },
    },
    {
        name: "list_classes",
        description: "List classes (summary)",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "create_class",
        description: "Append a class entry",
        inputSchema: {
            type: "object",
            properties: { ...p, name: { type: "string" }, updates: { type: "object" } },
            required: ["projectPath", "name"],
        },
    },
    {
        name: "update_class",
        description: "Merge updates into a class entry",
        inputSchema: {
            type: "object",
            properties: { ...p, classId: { type: "number" }, updates: { type: "object" } },
            required: ["projectPath", "classId", "updates"],
        },
    },
    {
        name: "list_states",
        description: "List states (summary)",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "create_state",
        description: "Append a state entry",
        inputSchema: {
            type: "object",
            properties: { ...p, name: { type: "string" }, updates: { type: "object" } },
            required: ["projectPath", "name"],
        },
    },
    {
        name: "update_state",
        description: "Merge updates into a state entry",
        inputSchema: {
            type: "object",
            properties: { ...p, stateId: { type: "number" }, updates: { type: "object" } },
            required: ["projectPath", "stateId", "updates"],
        },
    },
    {
        name: "list_enemies",
        description: "List enemies (summary)",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "create_enemy",
        description: "Append an enemy entry",
        inputSchema: {
            type: "object",
            properties: { ...p, name: { type: "string" }, updates: { type: "object" } },
            required: ["projectPath", "name"],
        },
    },
    {
        name: "update_enemy",
        description: "Merge updates into an enemy entry",
        inputSchema: {
            type: "object",
            properties: { ...p, enemyId: { type: "number" }, updates: { type: "object" } },
            required: ["projectPath", "enemyId", "updates"],
        },
    },
    {
        name: "update_database",
        description: "Merge updates into a database row by numeric id (Actors, Items, …)",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                database: { type: "string", description: "Key like actors, items, or filename stem" },
                id: { type: "number" },
                updates: { type: "object" },
            },
            required: ["projectPath", "database", "id", "updates"],
        },
    },
    {
        name: "get_system",
        description: "Read System.json",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "get_variables",
        description: "Return variable name array from System.json (extends length if needed later)",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "set_variable_name",
        description: "Set variables[id] name in System.json",
        inputSchema: {
            type: "object",
            properties: { ...p, variableId: { type: "number" }, name: { type: "string" } },
            required: ["projectPath", "variableId", "name"],
        },
    },
    {
        name: "get_switches",
        description: "Return switch name array from System.json",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "set_switch_name",
        description: "Set switches[id] name in System.json",
        inputSchema: {
            type: "object",
            properties: { ...p, switchId: { type: "number" }, name: { type: "string" } },
            required: ["projectPath", "switchId", "name"],
        },
    },
    {
        name: "get_game_title",
        description: "Return gameTitle from System.json",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "update_game_title",
        description: "Set gameTitle in System.json",
        inputSchema: {
            type: "object",
            properties: { ...p, title: { type: "string" } },
            required: ["projectPath", "title"],
        },
    },
    {
        name: "update_starting_position",
        description: "Set startMapId, startX, startY in System.json",
        inputSchema: {
            type: "object",
            properties: { ...p, mapId: { type: "number" }, x: { type: "number" }, y: { type: "number" } },
            required: ["projectPath", "mapId", "x", "y"],
        },
    },
    {
        name: "get_database_info",
        description: "Count non-empty database entries across main JSON files",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "get_database_limits",
        description: "Current max id per database (array length - 1)",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "set_database_limit",
        description: "Resize a database array (MCP-Maker style)",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                database: { type: "string", enum: ["items", "weapons", "armors", "skills", "actors", "classes", "enemies", "states", "animations", "tilesets", "troops", "commonEvents"] },
                limit: { type: "number" },
            },
            required: ["projectPath", "database", "limit"],
        },
    },
    {
        name: "scan_resources",
        description: "List files in an img/audio/js category (optional engine scan via RPGMAKER_ENGINE_PATH)",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                category: {
                    type: "string",
                    enum: [
                        "plugins", "tilesets", "characters", "faces", "sv_actors", "sv_enemies",
                        "battlebacks1", "battlebacks2", "parallaxes", "pictures", "animations",
                        "enemies", "titles1", "titles2", "system", "bgm", "bgs", "me", "se",
                    ],
                },
                source: { type: "string", enum: ["project", "engine", "all"], default: "project" },
            },
            required: ["projectPath", "category"],
        },
    },
    {
        name: "list_plugins",
        description: "List .js files in js/plugins",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "install_plugin",
        description: "Copy a .js file into js/plugins",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                sourcePath: { type: "string", description: "Absolute path to source .js" },
                targetName: { type: "string", description: "Destination filename (optional)" },
            },
            required: ["projectPath", "sourcePath"],
        },
    },
    {
        name: "get_core_script_versions",
        description: "Inspect core script files and extract version-like signatures",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "get_generator_parts",
        description: "List folders under img/generator",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "get_sample_maps",
        description: "List sample maps from engine newdata (requires RPGMAKER_ENGINE_PATH)",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "scan_dlc_packages",
        description: "Scan engine DLC package directories (requires RPGMAKER_ENGINE_PATH)",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "list_projects",
        description: "Find directories containing game.rmmzproject under a root (default: ~/Documents)",
        inputSchema: {
            type: "object",
            properties: { directory: { type: "string" } },
            required: [],
        },
    },
    {
        name: "generate_project_context",
        description: "Summarize System.json, MapInfos, plugins.js (truncated)",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                includeMaps: { type: "boolean" },
                includeEvents: { type: "boolean" },
                includePlugins: { type: "boolean" },
            },
            required: ["projectPath"],
        },
    },
    {
        name: "analyze_project_structure",
        description: "Quick file counts under data/ and img/",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "extract_game_design_patterns",
        description: "Heuristic hints only",
        inputSchema: { type: "object", properties: { ...p }, required: ["projectPath"] },
    },
    {
        name: "create_project",
        description: "Create minimal stub folder with game.rmmzproject (use RPG Maker to complete)",
        inputSchema: {
            type: "object",
            properties: {
                projectPath: { type: "string" },
                gameTitle: { type: "string" },
            },
            required: ["projectPath", "gameTitle"],
        },
    },
    {
        name: "generate_asset",
        description: "Not bundled — returns guidance (Gemini pipeline not included)",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                assetType: { type: "string" },
                prompt: { type: "string" },
                filename: { type: "string" },
            },
            required: ["projectPath", "assetType", "prompt", "filename"],
        },
    },
    {
        name: "generate_asset_batch",
        description: "Not bundled — stub response",
        inputSchema: {
            type: "object",
            properties: { requests: { type: "array" } },
            required: ["requests"],
        },
    },
    {
        name: "describe_asset",
        description: "Not bundled — stub response",
        inputSchema: {
            type: "object",
            properties: { ...p, assetType: { type: "string" }, filename: { type: "string" } },
            required: ["projectPath", "assetType", "filename"],
        },
    },
    {
        name: "generate_scenario",
        description: "Generate a scenario draft from theme/style/length",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                theme: { type: "string" },
                style: { type: "string" },
                length: { type: "string", enum: ["short", "medium", "long"] },
            },
            required: ["projectPath", "theme"],
        },
    },
    {
        name: "implement_scenario",
        description: "Persist scenario artifacts into integration metadata",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                scenario: { type: "object" },
            },
            required: ["projectPath", "scenario"],
        },
    },
    {
        name: "generate_and_implement_scenario",
        description: "Generate scenario and persist artifacts in one step",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                theme: { type: "string" },
                style: { type: "string" },
                length: { type: "string", enum: ["short", "medium", "long"] },
            },
            required: ["projectPath", "theme"],
        },
    },
    {
        name: "generate_scenario_variations",
        description: "Generate multiple scenario variants",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                theme: { type: "string" },
                style: { type: "string" },
                length: { type: "string", enum: ["short", "medium", "long"] },
                count: { type: "number" },
            },
            required: ["projectPath", "theme"],
        },
    },
    {
        name: "autonomous_create_game",
        description: "Create minimal project scaffold and scenario artifacts",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                concept: { type: "string" },
                gameTitle: { type: "string" },
                length: { type: "string", enum: ["short", "medium", "long"] },
            },
            required: ["projectPath", "concept"],
        },
    },
    {
        name: "register_resource",
        description: "Register reusable resource metadata in project-local store",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                resourceId: { type: "string" },
                resourceType: { type: "string" },
                name: { type: "string" },
                description: { type: "string" },
                content: { type: "object" },
                tags: { type: "array", items: { type: "string" } },
            },
            required: ["projectPath", "resourceId", "resourceType", "name"],
        },
    },
    {
        name: "register_prompt_template",
        description: "Register prompt template metadata in project-local store",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                promptId: { type: "string" },
                name: { type: "string" },
                description: { type: "string" },
                template: { type: "string" },
                variables: { type: "array", items: { type: "string" } },
                resourceRefs: { type: "array", items: { type: "string" } },
            },
            required: ["projectPath", "promptId", "name", "template"],
        },
    },
    {
        name: "execute_prompt",
        description: "Render a registered prompt template with variables",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                promptId: { type: "string" },
                variables: { type: "object" },
            },
            required: ["projectPath", "promptId"],
        },
    },
    {
        name: "list_resources",
        description: "List resources from project-local metadata store",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                type: { type: "string" },
                tags: { type: "array", items: { type: "string" } },
            },
            required: ["projectPath"],
        },
    },
    {
        name: "search_database",
        description: "Search across data JSON databases by id/name filters",
        inputSchema: {
            type: "object",
            properties: {
                ...p,
                types: { type: "array", items: { type: "string" } },
                nameContains: { type: "string" },
                idMin: { type: "number" },
                idMax: { type: "number" },
            },
            required: ["projectPath"],
        },
    },
    {
        name: "analyze_assets",
        description: "Analyze project asset counts by folder and extension",
        inputSchema: {
            type: "object",
            properties: { ...p },
            required: ["projectPath"],
        },
    },
];
