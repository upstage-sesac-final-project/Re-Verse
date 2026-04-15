/**
 * Single registry of all MCP tool implementations (used by index.ts and tests).
 */
import { HandlerResponse } from "./types/index.js";
import * as projectHandlers from "./handlers/project.js";
import * as pluginsHandlers from "./handlers/plugins.js";
import * as eventsHandlers from "./handlers/events.js";
import * as databaseHandlers from "./handlers/database.js";
import * as mapHandlers from "./handlers/map.js";
import * as playtestHandlers from "./handlers/playtest.js";
import * as undoHandlers from "./handlers/undo.js";
import * as unifiedDb from "./handlers/unified/integrationDb.js";
import * as unifiedMap from "./handlers/unified/integrationMap.js";
import * as unifiedSystem from "./handlers/unified/integrationSystem.js";
import * as unifiedEngine from "./handlers/unified/integrationEngine.js";
import * as unifiedGen from "./handlers/unified/integrationGeneration.js";

export type ToolHandler<T = unknown> = (args: T) => Promise<HandlerResponse>;

export const toolMap = {
    // Project tools
    get_project_info: projectHandlers.getProjectInfo,
    list_data_files: projectHandlers.listDataFiles,
    read_data_file: projectHandlers.readDataFile,
    write_data_file: projectHandlers.writeDataFile,
    list_assets: projectHandlers.listAssets,

    // Plugin tools
    write_plugin_code: pluginsHandlers.writePluginCode,
    get_plugins_config: pluginsHandlers.getPluginsConfig,
    update_plugins_config: pluginsHandlers.updatePluginsConfig,

    // Event tools
    get_event_page: eventsHandlers.getEventPage,
    add_dialogue: eventsHandlers.addDialogue,
    add_choice: eventsHandlers.addChoice,
    add_loop: eventsHandlers.addLoop,
    add_break_loop: eventsHandlers.addBreakLoop,
    add_conditional_branch: eventsHandlers.addConditionalBranch,
    delete_event_command: eventsHandlers.deleteEventCommand,
    update_event_command: eventsHandlers.updateEventCommand,
    search_events: eventsHandlers.searchEvents,

    // Database tools
    add_actor: databaseHandlers.addActor,
    add_item: databaseHandlers.addItem,
    add_skill: databaseHandlers.addSkill,

    // Map tools
    draw_map_tile: mapHandlers.drawMapTile,
    create_map: mapHandlers.createMap,

    // Project tools (extended)
    check_assets_integrity: projectHandlers.checkAssetsIntegrity,

    // Event tools (extended)
    show_picture: eventsHandlers.showPicture,

    // Playtest tools
    run_playtest: playtestHandlers.runPlaytest,
    inspect_game_state: playtestHandlers.inspectGameState,

    // Undo tools
    undo_last_change: undoHandlers.undoLastChange,
    list_backups: undoHandlers.listBackups,

    // Unified: maps & events
    list_maps: unifiedMap.list_maps,
    get_map_infos: unifiedMap.get_map_infos,
    get_map: unifiedMap.get_map,
    update_map: unifiedMap.update_map,
    get_map_events: unifiedMap.get_map_events,
    get_map_event: unifiedMap.get_map_event,
    create_map_event: unifiedMap.create_map_event,
    update_map_event: unifiedMap.update_map_event,
    search_map_events: unifiedMap.search_map_events,
    add_event_command: unifiedMap.add_event_command,

    // Database (extended)
    list_actors: unifiedDb.list_actors,
    get_actor: unifiedDb.get_actor,
    update_actor: unifiedDb.update_actor,
    search_actors: unifiedDb.search_actors,
    list_items: unifiedDb.list_items,
    update_item: unifiedDb.update_item,
    search_items: unifiedDb.search_items,
    list_skills: unifiedDb.list_skills,
    get_skill: unifiedDb.get_skill,
    update_skill: unifiedDb.update_skill,
    search_skills: unifiedDb.search_skills,
    create_damage_skill: unifiedDb.create_damage_skill,
    create_healing_skill: unifiedDb.create_healing_skill,
    create_buff_skill: unifiedDb.create_buff_skill,
    create_state_skill: unifiedDb.create_state_skill,
    list_weapons: unifiedDb.list_weapons,
    create_weapon: unifiedDb.create_weapon,
    update_weapon: unifiedDb.update_weapon,
    list_armors: unifiedDb.list_armors,
    create_armor: unifiedDb.create_armor,
    update_armor: unifiedDb.update_armor,
    list_classes: unifiedDb.list_classes,
    create_class: unifiedDb.create_class,
    update_class: unifiedDb.update_class,
    list_states: unifiedDb.list_states,
    create_state: unifiedDb.create_state,
    update_state: unifiedDb.update_state,
    list_enemies: unifiedDb.list_enemies,
    create_enemy: unifiedDb.create_enemy,
    update_enemy: unifiedDb.update_enemy,
    update_database: unifiedDb.update_database,

    // System.json
    get_system: unifiedSystem.get_system,
    get_variables: unifiedSystem.get_variables,
    set_variable_name: unifiedSystem.set_variable_name,
    get_switches: unifiedSystem.get_switches,
    set_switch_name: unifiedSystem.set_switch_name,
    get_game_title: unifiedSystem.get_game_title,
    update_game_title: unifiedSystem.update_game_title,
    update_starting_position: unifiedSystem.update_starting_position,

    // Engine / resources
    get_database_info: unifiedEngine.get_database_info,
    get_database_limits: unifiedEngine.get_database_limits,
    set_database_limit: unifiedEngine.set_database_limit,
    scan_resources: unifiedEngine.scan_resources,
    scan_dlc_packages: unifiedEngine.scan_dlc_packages,
    list_plugins: unifiedEngine.list_plugins,
    install_plugin: unifiedEngine.install_plugin,
    get_core_script_versions: unifiedEngine.get_core_script_versions,
    get_generator_parts: unifiedEngine.get_generator_parts,
    get_sample_maps: unifiedEngine.get_sample_maps,

    // Generation / workspace
    list_projects: unifiedGen.list_projects,
    generate_project_context: unifiedGen.generate_project_context,
    analyze_project_structure: unifiedGen.analyze_project_structure,
    extract_game_design_patterns: unifiedGen.extract_game_design_patterns,
    create_project: unifiedGen.create_project,
    generate_asset: unifiedGen.generate_asset,
    generate_asset_batch: unifiedGen.generate_asset_batch,
    describe_asset: unifiedGen.describe_asset,
    generate_scenario: unifiedGen.generate_scenario,
    implement_scenario: unifiedGen.implement_scenario,
    generate_and_implement_scenario: unifiedGen.generate_and_implement_scenario,
    generate_scenario_variations: unifiedGen.generate_scenario_variations,
    autonomous_create_game: unifiedGen.autonomous_create_game,
    register_resource: unifiedGen.register_resource,
    register_prompt_template: unifiedGen.register_prompt_template,
    execute_prompt: unifiedGen.execute_prompt,
    list_resources: unifiedGen.list_resources,
    search_database: unifiedGen.search_database,
    analyze_assets: unifiedGen.analyze_assets,
} as Record<string, ToolHandler<unknown>>;
