# API Reference

This document describes the tools available in the RPG Maker MZ MCP server.

## Project Management

### `get_project_info`
Get basic information about the project (Title, Version, Locale, Currency).
- **projectPath**: Absolute path to the project folder.

### `check_assets_integrity`
Check if all assets referenced in events actually exist in the project.
- **projectPath**: Absolute path to the project folder.

## Data Management

### `list_data_files`
List all JSON data files in the `data` directory.
- **projectPath**: Absolute path to the project folder.

### `read_data_file`
Read the content of a specific data file.
- **projectPath**: Absolute path to the project folder.
- **filename**: Name of the file (e.g., `Actors.json`).

### `write_data_file`
Write content to a specific data file.
- **projectPath**: Absolute path to the project folder.
- **filename**: Name of the file.
- **content**: JSON string content.

## Plugin Management

### `get_plugins_config`
Read the current plugin configuration from `js/plugins.js`.
- **projectPath**: Absolute path to the project folder.

### `update_plugins_config`
Update the plugin configuration.
- **projectPath**: Absolute path to the project folder.
- **plugins**: Array of plugin configuration objects.

### `write_plugin_code`
Write a JavaScript plugin file to `js/plugins`.
- **projectPath**: Absolute path to the project folder.
- **filename**: Plugin filename (e.g., `MyPlugin.js`).
- **code**: JavaScript code.

## Asset Management

### `list_assets`
List files in `img` and `audio` directories.
- **projectPath**: Absolute path to the project folder.
- **assetType**: `img`, `audio`, or `all` (default).

## Map & Event Management

### `create_map`
Create a new map.
- **projectPath**: Absolute path to the project folder.
- **mapName**: Name of the new map.
- **width**: Width in tiles (default: 17).
- **height**: Height in tiles (default: 13).
- **parentMapId**: Parent map ID (default: 0).

### `search_events`
Search for text or codes in Map events and Common events.
- **projectPath**: Absolute path to the project folder.
- **query**: Text or number to search for.

### `get_event_page`
Get the command list for a specific event page.
- **projectPath**: Absolute path to the project folder.
- **mapId**: Map ID.
- **eventId**: Event ID.
- **pageIndex**: Page index (0-based).

### `add_choice`
Add a choice selection to an event.
- **projectPath**: Absolute path to the project folder.
- **mapId**: Map ID.
- **eventId**: Event ID.
- **pageIndex**: Page index.
- **insertPosition**: Index to insert at (-1 for end).
- **options**: Array of choice strings (max 6).
- **cancelType**: Cancel behavior (-1=disallow, 0-5=branch to option).

### `add_loop`
Add a Loop block (Loop + Repeat Above).
- **projectPath**: Absolute path to the project folder.
- **mapId**: Map ID.
- **eventId**: Event ID.
- **pageIndex**: Page index.
- **insertPosition**: Index to insert at (-1 for end).

### `add_break_loop`
Add a Break Loop command.
- **projectPath**: Absolute path to the project folder.
- **mapId**: Map ID.
- **eventId**: Event ID.
- **pageIndex**: Page index.
- **insertPosition**: Index to insert at.

### `add_conditional_branch`
Add a Conditional Branch structure (If-Else-End).
- **projectPath**: Absolute path to the project folder.
- **mapId**: Map ID.
- **eventId**: Event ID.
- **pageIndex**: Page index.
- **insertPosition**: Index to insert at.
- **condition**: Condition parameters object.
  - `code`: 0=Switch, 1=Variable, etc.
  - `dataA`: ID.
  - `operation`: Comparison operator.
  - `dataB`: Value/ID.
- **includeElse**: Boolean (default: true).

### `show_picture`
Add a Show Picture command.
- **projectPath**: Absolute path to the project folder.
- **mapId**: Map ID.
- **eventId**: Event ID.
- **pageIndex**: Page index.
- **insertPosition**: Index to insert at.
- **pictureId**: Picture number.
- **pictureName**: Image filename.
- **x**: X coordinate.
- **y**: Y coordinate.
- **origin**: 0=Upper Left, 1=Center.
- **scaleX**: Scale X %.
- **scaleY**: Scale Y %.
- **opacity**: Opacity (0-255).
- **blendMode**: 0-3.

## Testing

### `run_playtest`
Launch the game and optionally take a screenshot.
- **projectPath**: Absolute path to the project folder.
- **duration**: Wait duration in ms (default: 5000).
- **autoClose**: Boolean (default: false).
- **debugPort**: Port for remote debugging (e.g., 9222).

### `inspect_game_state`
Evaluate arbitrary JavaScript inside a running game via Puppeteer.

> ⚠️ **Security notice:** This tool executes the provided script inside the game context. Use only in a trusted local environment and never expose this endpoint publicly.

- **script**: JavaScript string to evaluate (e.g., `$gameSwitches.value(1)`).
- **port**: Debug port to connect to (default: 9222).
