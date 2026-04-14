/**
 * Builds the project, then exercises every tool handler (no Vitest / Rollup).
 * Usage: node scripts/run-tool-matrix.mjs
 */
import { cp, mkdtemp, rm, mkdir } from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";
import { tmpdir } from "os";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");

const { toolMap } = await import(path.join(ROOT, "dist/mcpToolMap.js"));
const { resolveImplementationToolName, CANONICAL_TOOL_NAMES } = await import(
    path.join(ROOT, "dist/generated/toolRegistry.generated.js")
);

const SOURCE_PROJECT = path.join(ROOT, "test_project");

function buildArgs(canonical, p) {
    const impl = resolveImplementationToolName(canonical);
    const map = getArgBuilders(p);
    const fn = map[impl] ?? map[canonical];
    if (!fn) throw new Error(`No args for ${canonical} -> ${impl}`);
    return fn();
}

function getArgBuilders(p) {
    return {
        get_project_info: () => ({ projectPath: p }),
        list_data_files: () => ({ projectPath: p }),
        read_data_file: () => ({ projectPath: p, filename: "Actors.json" }),
        write_data_file: () => ({
            projectPath: p,
            filename: "ToolMatrixWrite.json",
            content: JSON.stringify([null, { id: 1, note: "m" }]),
        }),
        list_assets: () => ({ projectPath: p, assetType: "all" }),
        check_assets_integrity: () => ({ projectPath: p }),
        get_plugins_config: () => ({ projectPath: p }),
        update_plugins_config: () => ({
            projectPath: p,
            plugins: [{ name: "TestPlugin", status: true, description: "t" }],
        }),
        write_plugin_code: () => ({
            projectPath: p,
            filename: "MatrixWritePlugin.js",
            code: "/* matrix */\n(() => {})();\n",
        }),
        list_maps: () => ({ projectPath: p }),
        get_map_infos: () => ({ projectPath: p }),
        get_map: () => ({ projectPath: p, mapId: 1 }),
        create_map: () => ({ projectPath: p, mapName: "MatrixMap", width: 17, height: 13, tilesetId: 1 }),
        update_map: () => ({ projectPath: p, mapId: 1, updates: { note: "matrix" } }),
        draw_map_tile: () => ({ projectPath: p, mapId: 1, x: 0, y: 0, layer: 0, tileId: 0 }),
        get_map_events: () => ({ projectPath: p, mapId: 1 }),
        get_map_event: () => ({ projectPath: p, mapId: 1, eventId: 1 }),
        create_map_event: () => ({ projectPath: p, mapId: 1, name: "MX", x: 2, y: 2 }),
        update_map_event: () => ({ projectPath: p, mapId: 1, eventId: 1, updates: { note: "mx" } }),
        search_map_events: () => ({ projectPath: p, mapId: 1, searchTerm: "EV" }),
        search_events: () => ({ projectPath: p, query: "Test" }),
        get_event_page: () => ({ projectPath: p, mapId: 1, eventId: 1, pageIndex: 0 }),
        add_dialogue: () => ({
            projectPath: p,
            mapId: 1,
            eventId: 1,
            pageIndex: 0,
            insertPosition: 0,
            text: "matrix",
        }),
        add_choice: () => ({
            projectPath: p,
            mapId: 1,
            eventId: 1,
            pageIndex: 0,
            insertPosition: 0,
            options: ["A", "B"],
        }),
        add_loop: () => ({
            projectPath: p,
            mapId: 1,
            eventId: 1,
            pageIndex: 0,
            insertPosition: 0,
        }),
        add_break_loop: () => ({
            projectPath: p,
            mapId: 1,
            eventId: 1,
            pageIndex: 0,
            insertPosition: 0,
        }),
        add_conditional_branch: () => ({
            projectPath: p,
            mapId: 1,
            eventId: 1,
            pageIndex: 0,
            insertPosition: 0,
            condition: { code: 0, dataA: 0, operation: 0, dataB: 0 },
        }),
        show_picture: () => ({
            projectPath: p,
            mapId: 1,
            eventId: 1,
            pageIndex: 0,
            insertPosition: 0,
            pictureName: "test",
        }),
        add_event_command: () => ({
            projectPath: p,
            mapId: 1,
            eventId: 1,
            pageIndex: 0,
            command: { code: 0, indent: 0, parameters: [] },
            position: 0,
        }),
        update_event_command: () => ({
            projectPath: p,
            mapId: 1,
            eventId: 1,
            pageIndex: 0,
            commandIndex: 0,
            newCommand: { code: 0, indent: 0, parameters: [] },
        }),
        delete_event_command: () => ({
            projectPath: p,
            mapId: 1,
            eventId: 1,
            pageIndex: 0,
            commandIndex: 1,
        }),
        add_actor: () => ({ projectPath: p, name: "MatrixActor" }),
        add_item: () => ({ projectPath: p, name: "MatrixItem" }),
        add_skill: () => ({ projectPath: p, name: "MatrixSkill" }),
        list_actors: () => ({ projectPath: p }),
        get_actor: () => ({ projectPath: p, actorId: 1 }),
        update_actor: () => ({ projectPath: p, actorId: 1, updates: { note: "x" } }),
        search_actors: () => ({ projectPath: p, searchTerm: "Test" }),
        list_items: () => ({ projectPath: p }),
        update_item: () => ({ projectPath: p, itemId: 1, updates: { name: "MatrixItem2" } }),
        search_items: () => ({ projectPath: p, searchTerm: "Test" }),
        list_skills: () => ({ projectPath: p }),
        get_skill: () => ({ projectPath: p, skillId: 1 }),
        update_skill: () => ({ projectPath: p, skillId: 1, updates: { note: "n" } }),
        search_skills: () => ({ projectPath: p, searchTerm: "Test" }),
        create_damage_skill: () => ({
            projectPath: p,
            name: "Dmg",
            damageFormula: "a.atk * 2",
        }),
        create_healing_skill: () => ({
            projectPath: p,
            name: "Heal",
            healFormula: "100",
        }),
        create_buff_skill: () => ({
            projectPath: p,
            name: "Buff",
            buffType: 0,
            turns: 3,
        }),
        create_state_skill: () => ({
            projectPath: p,
            name: "St",
            stateId: 1,
            chance: 100,
        }),
        list_weapons: () => ({ projectPath: p }),
        create_weapon: () => ({ projectPath: p, name: "W" }),
        update_weapon: () => ({ projectPath: p, weaponId: 1, updates: { note: "w" } }),
        list_armors: () => ({ projectPath: p }),
        create_armor: () => ({ projectPath: p, name: "A" }),
        update_armor: () => ({ projectPath: p, armorId: 1, updates: { note: "a" } }),
        list_classes: () => ({ projectPath: p }),
        create_class: () => ({ projectPath: p, name: "C" }),
        update_class: () => ({ projectPath: p, classId: 1, updates: { note: "c" } }),
        list_states: () => ({ projectPath: p }),
        create_state: () => ({ projectPath: p, name: "S" }),
        update_state: () => ({ projectPath: p, stateId: 1, updates: { note: "s" } }),
        list_enemies: () => ({ projectPath: p }),
        create_enemy: () => ({ projectPath: p, name: "E" }),
        update_enemy: () => ({ projectPath: p, enemyId: 1, updates: { note: "e" } }),
        update_database: () => ({
            projectPath: p,
            database: "actors",
            id: 1,
            updates: { note: "db" },
        }),
        get_system: () => ({ projectPath: p }),
        get_variables: () => ({ projectPath: p }),
        set_variable_name: () => ({ projectPath: p, variableId: 1, name: "VX" }),
        get_switches: () => ({ projectPath: p }),
        set_switch_name: () => ({ projectPath: p, switchId: 1, name: "SY" }),
        get_game_title: () => ({ projectPath: p }),
        update_game_title: () => ({ projectPath: p, title: "Matrix Title" }),
        update_starting_position: () => ({ projectPath: p, mapId: 1, x: 1, y: 1 }),
        get_database_info: () => ({ projectPath: p }),
        get_database_limits: () => ({ projectPath: p }),
        set_database_limit: () => ({ projectPath: p, database: "items", limit: 120 }),
        scan_resources: () => ({ projectPath: p, category: "plugins", source: "project" }),
        scan_dlc_packages: () => ({ projectPath: p }),
        get_core_script_versions: () => ({ projectPath: p }),
        get_generator_parts: () => ({ projectPath: p }),
        get_sample_maps: () => ({ projectPath: p }),
        list_plugins: () => ({ projectPath: p }),
        install_plugin: () => ({
            projectPath: p,
            sourcePath: path.join(p, "js", "plugins", "TestPlugin.js"),
            targetName: "MatrixInstalled.js",
        }),
        list_projects: () => ({ directory: path.dirname(p) }),
        generate_project_context: () => ({ projectPath: p }),
        analyze_project_structure: () => ({ projectPath: p }),
        extract_game_design_patterns: () => ({ projectPath: p }),
        generate_asset: () => ({
            projectPath: p,
            assetType: "picture",
            prompt: "test",
            filename: "x.png",
        }),
        generate_asset_batch: () => ({ requests: [] }),
        describe_asset: () => ({ projectPath: p, assetType: "picture", filename: "a.png" }),
        generate_scenario: () => ({ projectPath: p, theme: "matrix" }),
        implement_scenario: () => ({ projectPath: p, scenario: { title: "mx" } }),
        generate_and_implement_scenario: () => ({ projectPath: p, theme: "matrix" }),
        generate_scenario_variations: () => ({ projectPath: p, theme: "matrix", count: 2 }),
        autonomous_create_game: () => ({
            projectPath: path.join(path.dirname(p), `auto-${Date.now()}`),
            concept: "matrix concept",
            gameTitle: "Matrix Auto",
            length: "short",
        }),
        register_resource: () => ({
            projectPath: p,
            resourceId: "r1",
            resourceType: "lore",
            name: "Matrix Lore",
            description: "desc",
            content: { a: 1 },
            tags: ["matrix"],
        }),
        register_prompt_template: () => ({
            projectPath: p,
            promptId: "pt1",
            name: "Prompt1",
            template: "Hello {{name}}",
            variables: ["name"],
            resourceRefs: ["r1"],
        }),
        execute_prompt: () => ({ projectPath: p, promptId: "pt1", variables: { name: "Matrix" } }),
        list_resources: () => ({ projectPath: p, type: "lore" }),
        search_database: () => ({ projectPath: p, types: ["Actors"], nameContains: "Test", idMin: 1, idMax: 10 }),
        analyze_assets: () => ({ projectPath: p }),
        list_backups: () => ({ projectPath: p }),
        run_playtest: () => ({ projectPath: p, duration: 500, autoClose: true }),
        inspect_game_state: () => ({ port: 9222, script: "1+1" }),
    };
}

async function callTool(canonical, args) {
    const impl = resolveImplementationToolName(canonical);
    const handler = toolMap[impl];
    if (!handler) throw new Error(`No handler for ${canonical} -> ${impl}`);
    return handler(args);
}

async function main() {
    const projectPath = await mkdtemp(path.join(tmpdir(), "mcp-matrix-"));
    await cp(SOURCE_PROJECT, projectPath, { recursive: true });
    await mkdir(path.join(projectPath, "img"), { recursive: true });
    await mkdir(path.join(projectPath, "audio", "bgm"), { recursive: true });

    const skipPlaytest = !process.env.RUN_PLAYTEST;
    const skipInspect = !process.env.RUN_INSPECT_GAME_STATE;

    const failures = [];
    const envBlocked = [];
    for (const name of CANONICAL_TOOL_NAMES) {
        if (name === "run_playtest" && skipPlaytest) continue;
        if (name === "inspect_game_state" && skipInspect) continue;
        if (name === "undo_last_change") continue;
        if (name === "create_project") continue;
        if (name === "write_data_file") continue;
        try {
            const args = buildArgs(name, projectPath);
            const impl = resolveImplementationToolName(name);
            const res = await callTool(name, args);
            const text = (res.content || []).map((c) => (c.type === "text" ? c.text : "")).join("\n");
            if (!text || text.length === 0) failures.push({ name, impl, err: "empty response" });
        } catch (e) {
            const impl = resolveImplementationToolName(name);
            const errText = String(e?.message || e);
            const isExternal =
                name === "run_playtest" ||
                name === "inspect_game_state" ||
                name === "generate_asset" ||
                name === "generate_asset_batch" ||
                name === "describe_asset" ||
                name === "get_sample_maps" ||
                name === "scan_dlc_packages";
            const looksEnvBlocked =
                /RPGMAKER_ENGINE_PATH|Could not find Chrome|Puppeteer|ECONNREFUSED|Script not allowed|not configured|ENV-BLOCKED/i.test(
                    errText
                );
            if (isExternal && looksEnvBlocked) {
                envBlocked.push({ name, impl, err: errText });
            } else {
                failures.push({ name, impl, err: errText });
            }
        }
    }

    try {
        await callTool("write_data_file", buildArgs("write_data_file", projectPath));
        await callTool("undo_last_change", { projectPath, filename: "ToolMatrixWrite.json" });
    } catch (e) {
        failures.push({ name: "write_data_file/undo_last_change", err: String(e) });
    }

    try {
        const stubDir = path.join(tmpdir(), `mcp-cp-${Date.now()}`);
        await callTool("create_project", { projectPath: stubDir, gameTitle: "MatrixStub" });
        await rm(stubDir, { recursive: true, force: true });
    } catch (e) {
        failures.push({ name: "create_project", err: String(e) });
    }

    await rm(projectPath, { recursive: true, force: true });

    if (failures.length > 0) {
        console.error(JSON.stringify(failures, null, 2));
        process.exit(1);
    }
    console.log(
        JSON.stringify(
            {
                ok: true,
                tested: CANONICAL_TOOL_NAMES.length,
                skippedPlaytest: skipPlaytest,
                skippedInspect: skipInspect,
                envBlocked,
            },
            null,
            2
        )
    );
}

main().catch((e) => {
    console.error(e);
    process.exit(1);
});
