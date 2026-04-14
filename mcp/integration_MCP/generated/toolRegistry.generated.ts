/* eslint-disable */
/**
 * AUTO-GENERATED FILE — do not edit by hand.
 * Source: tool-registry.json
 * Generator: scripts/build-tool-registry.mjs
 * Version: 1.0.0
 */

export type ToolProfile = "core" | "engine" | "generation" | "playtest";

export const REGISTRY_VERSION = "1.0.0" as const;

export const CANONICAL_TOOL_NAMES = [
  "add_break_loop",
  "add_choice",
  "add_conditional_branch",
  "add_dialogue",
  "add_event_command",
  "add_loop",
  "analyze_assets",
  "analyze_project_structure",
  "autonomous_create_game",
  "check_assets_integrity",
  "create_actor",
  "create_armor",
  "create_buff_skill",
  "create_class",
  "create_damage_skill",
  "create_enemy",
  "create_healing_skill",
  "create_item",
  "create_map",
  "create_map_event",
  "create_project",
  "create_skill",
  "create_state",
  "create_state_skill",
  "create_weapon",
  "delete_event_command",
  "describe_asset",
  "draw_map_tile",
  "execute_prompt",
  "extract_game_design_patterns",
  "generate_and_implement_scenario",
  "generate_asset",
  "generate_asset_batch",
  "generate_project_context",
  "generate_scenario",
  "generate_scenario_variations",
  "get_actor",
  "get_core_script_versions",
  "get_database_info",
  "get_database_limits",
  "get_event_page",
  "get_game_title",
  "get_generator_parts",
  "get_map",
  "get_map_event",
  "get_map_events",
  "get_map_infos",
  "get_plugins_config",
  "get_project_info",
  "get_sample_maps",
  "get_skill",
  "get_switches",
  "get_system",
  "get_variables",
  "implement_scenario",
  "inspect_game_state",
  "install_plugin",
  "list_actors",
  "list_armors",
  "list_assets",
  "list_backups",
  "list_classes",
  "list_data_files",
  "list_enemies",
  "list_items",
  "list_maps",
  "list_plugins",
  "list_projects",
  "list_resources",
  "list_skills",
  "list_states",
  "list_weapons",
  "read_data_file",
  "register_prompt_template",
  "register_resource",
  "run_playtest",
  "scan_dlc_packages",
  "scan_resources",
  "search_actors",
  "search_database",
  "search_events",
  "search_items",
  "search_map_events",
  "search_skills",
  "set_database_limit",
  "set_switch_name",
  "set_variable_name",
  "show_picture",
  "undo_last_change",
  "update_actor",
  "update_armor",
  "update_class",
  "update_database",
  "update_enemy",
  "update_event_command",
  "update_game_title",
  "update_item",
  "update_map",
  "update_map_event",
  "update_plugins_config",
  "update_skill",
  "update_starting_position",
  "update_state",
  "update_weapon",
  "write_data_file",
  "write_plugin_code"
] as const;

export type CanonicalToolName = (typeof CANONICAL_TOOL_NAMES)[number];

export const ALIAS_TO_CANONICAL: Readonly<Record<string, string>> = Object.freeze({
  "read_project_info": "get_project_info",
  "get_maps": "list_maps",
  "update_map_tile": "draw_map_tile",
  "add_event": "create_map_event",
  "get_actors": "list_actors",
  "add_actor": "create_actor",
  "get_items": "list_items",
  "add_item": "create_item",
  "get_skills": "list_skills",
  "add_skill": "create_skill",
  "get_weapons": "list_weapons",
  "get_armors": "list_armors",
  "get_classes": "list_classes",
  "get_states": "list_states",
  "get_enemies": "list_enemies",
  "get_installed_plugins": "list_plugins",
  "read_map": "get_map",
  "add_class": "create_class"
});

export const CANONICAL_TO_ALIASES: Readonly<Record<string, readonly string[]>> = Object.freeze({
  "get_project_info": [
    "read_project_info"
  ],
  "list_maps": [
    "get_maps"
  ],
  "draw_map_tile": [
    "update_map_tile"
  ],
  "create_map_event": [
    "add_event"
  ],
  "list_actors": [
    "get_actors"
  ],
  "create_actor": [
    "add_actor"
  ],
  "list_items": [
    "get_items"
  ],
  "create_item": [
    "add_item"
  ],
  "list_skills": [
    "get_skills"
  ],
  "create_skill": [
    "add_skill"
  ],
  "list_weapons": [
    "get_weapons"
  ],
  "list_armors": [
    "get_armors"
  ],
  "list_classes": [
    "get_classes"
  ],
  "list_states": [
    "get_states"
  ],
  "list_enemies": [
    "get_enemies"
  ],
  "list_plugins": [
    "get_installed_plugins"
  ],
  "get_map": [
    "read_map"
  ],
  "create_class": [
    "add_class"
  ]
} as Record<string, readonly string[]>);

export const TOOL_PROFILE_BY_NAME: Readonly<Record<string, ToolProfile>> = Object.freeze({
  "get_project_info": "core",
  "list_data_files": "core",
  "read_data_file": "core",
  "write_data_file": "core",
  "list_assets": "core",
  "check_assets_integrity": "core",
  "get_plugins_config": "core",
  "update_plugins_config": "core",
  "list_plugins": "core",
  "write_plugin_code": "core",
  "list_maps": "core",
  "get_map_infos": "core",
  "get_map": "core",
  "create_map": "core",
  "update_map": "core",
  "draw_map_tile": "core",
  "get_map_events": "core",
  "get_map_event": "core",
  "create_map_event": "core",
  "update_map_event": "core",
  "search_map_events": "core",
  "search_events": "core",
  "get_event_page": "core",
  "add_event_command": "core",
  "update_event_command": "core",
  "delete_event_command": "core",
  "add_dialogue": "core",
  "add_choice": "core",
  "add_loop": "core",
  "add_break_loop": "core",
  "add_conditional_branch": "core",
  "show_picture": "core",
  "list_actors": "core",
  "get_actor": "core",
  "create_actor": "core",
  "update_actor": "core",
  "search_actors": "core",
  "list_items": "core",
  "create_item": "core",
  "update_item": "core",
  "search_items": "core",
  "list_weapons": "core",
  "create_weapon": "core",
  "update_weapon": "core",
  "list_armors": "core",
  "create_armor": "core",
  "update_armor": "core",
  "list_skills": "core",
  "get_skill": "core",
  "create_skill": "core",
  "update_skill": "core",
  "search_skills": "core",
  "create_damage_skill": "core",
  "create_healing_skill": "core",
  "create_buff_skill": "core",
  "create_state_skill": "core",
  "list_classes": "core",
  "create_class": "core",
  "update_class": "core",
  "list_states": "core",
  "create_state": "core",
  "update_state": "core",
  "list_enemies": "core",
  "create_enemy": "core",
  "update_enemy": "core",
  "get_system": "core",
  "get_variables": "core",
  "set_variable_name": "core",
  "get_switches": "core",
  "set_switch_name": "core",
  "get_game_title": "core",
  "update_game_title": "core",
  "update_starting_position": "core",
  "update_database": "core",
  "list_backups": "core",
  "undo_last_change": "core",
  "install_plugin": "engine",
  "get_database_info": "engine",
  "get_database_limits": "engine",
  "set_database_limit": "engine",
  "scan_resources": "engine",
  "scan_dlc_packages": "engine",
  "get_core_script_versions": "engine",
  "get_generator_parts": "engine",
  "get_sample_maps": "engine",
  "list_projects": "generation",
  "generate_project_context": "generation",
  "analyze_project_structure": "generation",
  "extract_game_design_patterns": "generation",
  "create_project": "generation",
  "generate_asset": "generation",
  "generate_asset_batch": "generation",
  "describe_asset": "generation",
  "generate_scenario": "generation",
  "implement_scenario": "generation",
  "generate_and_implement_scenario": "generation",
  "generate_scenario_variations": "generation",
  "autonomous_create_game": "generation",
  "register_resource": "generation",
  "register_prompt_template": "generation",
  "execute_prompt": "generation",
  "list_resources": "generation",
  "search_database": "generation",
  "analyze_assets": "generation",
  "run_playtest": "playtest",
  "inspect_game_state": "playtest"
});

export const DEFAULT_PROFILE_FLAGS: Readonly<Record<ToolProfile, boolean>> = Object.freeze({
  "core": true,
  "engine": false,
  "generation": false,
  "playtest": false
});

export const CANONICAL_TO_IMPLEMENTATION_NAME: Readonly<Record<string, string>> = Object.freeze({
  "create_actor": "add_actor",
  "create_item": "add_item",
  "create_skill": "add_skill"
});

/**
 * Resolve alias or canonical name to canonical tool name.
 */
export function resolveCanonicalToolName(name: string): string {
  return ALIAS_TO_CANONICAL[name] ?? name;
}

/**
 * Map registry canonical name to the current server implementation key (if different).
 * Example: create_actor -> add_actor until handlers are renamed.
 */
export function resolveImplementationToolName(name: string): string {
  const canonical = resolveCanonicalToolName(name);
  return CANONICAL_TO_IMPLEMENTATION_NAME[canonical] ?? canonical;
}

/**
 * All names (canonical + aliases) that map to the same canonical tool.
 */
export function allNamesForCanonical(canonical: string): readonly string[] {
  const aliases = CANONICAL_TO_ALIASES[canonical] ?? [];
  return [canonical, ...aliases];
}
