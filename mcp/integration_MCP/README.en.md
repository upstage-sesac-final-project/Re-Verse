# RPG Maker MZ MCP Server - Documentation

![Tests](https://github.com/rein1225/RPGMakerMZ_MCP/actions/workflows/test.yml/badge.svg)

> ⚠ **Experimental / WIP**
>
> This is a **work-in-progress version (0.x)** of the MCP server for "letting AI work with RPG Maker MZ".
> Specifications are not yet finalized, and updates **may break things**.
>
> - Recommended for use with test projects only
> - Backup required before touching production data
> - Issues / PRs / Feedback are welcome
>
> This is a release for "people who want to try experimental stuff", so use at your own risk.

## TL;DR (Quick Start)

### Target Users
**People who want AI to work with RPG Maker MZ**

### What You Can Do
- ✅ Let AI create maps
- ✅ Let AI add events
- ✅ Add and configure plugins
- ✅ Automate playtesting and screenshots

### 3-Step Quick Start

1. **Install**: `npm install -g @rein634/rpg-maker-mz-mcp`
2. **Configure MCP**: Add the following to your MCP client's config file:
   ```json
   {
     "mcpServers": {
       "rpg-maker-mz": {
         "command": "rpg-maker-mz-mcp"
       }
     }
   }
   ```
3. **Use**: Tell your AI "Analyze this project and add a dialogue event to the first map"

---

## Overview

This MCP server is a tool for **complete automation** of RPG Maker MZ game development. Simply give natural language instructions to AI, and it will automatically create maps, place events, manage switches, check assets, and more.

**Key Features:**
- ✅ **Abstraction Layer**: Develop without knowing MZ's internal structure
- ✅ **Automatic ID Management**: Automatically resolve/assign switch and map IDs
- ✅ **Hallucination Prevention**: Reference specifications via MCP Resources
- ✅ **Quality Assurance**: Zod Validation and asset integrity checks
- ✅ **Automatic Backup**: Automatic backup creation before file writes
- ✅ **Undo Function**: Easily revert the last change
- ✅ **Security Enhanced**: Whitelist-based code execution, path traversal protection

---

## Setup

### Method 1: Run from Source Code (For Developers - Recommended)

No need to install npm packages. Just clone the repository and install dependencies.

#### 1. Clone Repository

```bash
git clone https://github.com/rein1225/RPGMakerMZ_MCP.git
cd RPGMakerMZ_MCP
```

#### 2. Install Dependencies

```bash
npm install
```

That's it! You can now run TypeScript files directly.

#### 3. Configure MCP Settings

Add the following to your Antigravity config file (`mcp_config.json`):

```json
{
  "mcpServers": {
    "rpg-maker-mz": {
      "command": "npx",
      "args": ["tsx", "C:/path/to/RPGMakerMZ_MCP/index.ts"],
      "cwd": "C:/path/to/RPGMakerMZ_MCP"
    }
  }
}
```

> ⚠️ **Important**:
> - Replace `C:/path/to/RPGMakerMZ_MCP` with your actual project path
> - Use forward slashes (`/`) on Windows, not backslashes (`\`)
> - Using `npx tsx` allows direct execution of TypeScript files (no build required)
> - **If `cwd` property is not allowed**: See Troubleshooting Q1 (recommend using npm package or batch file)

### Method 2: Install from npm Package (For Distribution)

The package is published on npm, so you can install it globally:

```bash
npm install -g @rein634/rpg-maker-mz-mcp
```

After installation, add the following to your MCP config file:

```json
{
  "mcpServers": {
    "rpg-maker-mz": {
      "command": "rpg-maker-mz-mcp"
    }
  }
}
```

### Method 3: Build and Run (Optional)

You can also compile TypeScript to JavaScript first:

```bash
npm run build
```

Then run `dist/index.js`:

```json
{
  "mcpServers": {
    "rpg-maker-mz": {
      "command": "node",
      "args": ["C:/path/to/RPGMakerMZ_MCP/dist/index.js"],
      "cwd": "C:/path/to/RPGMakerMZ_MCP"
    }
  }
}
```

> 💡 **Recommendation**: For development/personal use, **Method 1** (run from source) is the easiest. No build required, and you can edit code and test immediately.

---

## Available Tools

### Phase 1: Project Analysis & Data Operations

#### 1. `get_project_info` - Get Project Basic Information
**Description:** Retrieves basic information such as game title, version, currency unit from System.json.
**Parameters:**
- `projectPath` (required): Absolute path to project folder

#### 2. `list_data_files` - List Data Files
**Description:** Gets a list of JSON files in the data folder.
**Parameters:**
- `projectPath` (required): Absolute path to project folder

#### 3. `read_data_file` - Read Data File
**Description:** Reads the contents of a specified data file (e.g., Actors.json).
**Parameters:**
- `projectPath` (required): Absolute path to project folder
- `filename` (required): File name (e.g., 'Actors.json')

#### 4. `write_data_file` - Write Data File
**Description:** Writes JSON content to a specified data file. Automatic backup is created before writing.
**Parameters:**
- `projectPath` (required): Absolute path to project folder
- `filename` (required): File name
- `content` (required): JSON string to write

#### 5. `search_events` - Search Events
**Description:** Searches for text or command codes within map events and common events.
**Parameters:**
- `projectPath` (required): Absolute path to project folder
- `query` (required): Text or number to search for

#### 6. `get_event_page` - Get Event Page
**Description:** Gets the command list for a specified event page. Major commands (dialogue, choices, switch operations, etc.) include highly readable descriptions, allowing AI to understand existing event content and refine or modify it.
**Parameters:**
- `projectPath` (required): Absolute path to project folder
- `mapId` (required): Map ID
- `eventId` (required): Event ID
- `pageIndex` (required): Page number (0-based)

---

### Phase 2: Asset Management

#### 7. `list_assets` - List Assets
**Description:** Gets a list of files in the img and audio directories.
**Parameters:**
- `projectPath` (required): Absolute path to project folder
- `assetType` (optional): 'img', 'audio', 'all' (default: 'all')

#### 8. `check_assets_integrity` - Check Asset Integrity
**Description:** Checks if assets (images, audio, etc.) referenced in events actually exist in the project.
**Parameters:**
- `projectPath` (required): Absolute path to project folder

---

### Phase 3: Plugin Management

#### 9. `write_plugin_code` - Create Plugin
**Description:** Creates a new plugin file (.js) in js/plugins directory.
**Parameters:**
- `projectPath` (required): Absolute path to project folder
- `filename` (required): Plugin file name (e.g., 'MyPlugin.js')
- `code` (required): JavaScript code

#### 10. `get_plugins_config` - Get Plugin Configuration
**Description:** Reads current plugin configuration from js/plugins.js.
**Parameters:**
- `projectPath` (required): Absolute path to project folder

#### 11. `update_plugins_config` - Update Plugin Configuration
**Description:** Updates plugin configuration in js/plugins.js.
**Parameters:**
- `projectPath` (required): Absolute path to project folder
- `plugins` (required): Array of plugin configuration objects

---

### Phase 4: Map & Event Operations (Abstraction Layer)

#### 12. `add_dialogue` - Add Dialogue Event
**Description:** Adds dialogue to the message window.
**Parameters:**
- `projectPath` (required): Absolute path to project folder
- `mapId` (required): Map ID
- `eventId` (required): Event ID
- `pageIndex` (required): Page number
- `insertPosition` (required): Insert position (-1 for end)
- `text` (required): Display text
- `face`, `faceIndex`, `background`, `position` (optional)

**Request Example:**
```json
{
  "tool": "add_dialogue",
  "arguments": {
    "projectPath": "C:/Games/MyProject",
    "mapId": 1,
    "eventId": 1,
    "pageIndex": 0,
    "insertPosition": -1,
    "text": "Hello!\nNew companion here."
  }
}
```

**Response Example:**
```json
{
  "content": [
    {
      "type": "text",
      "text": "Dialogue event added."
    }
  ]
}
```

#### 13. `add_choice` - Add Choice Selection
**Description:** Adds choices to an event. Up to 6 choices can be set.
**Parameters:**
- `projectPath` (required): Absolute path to project folder
- `mapId` (required): Map ID
- `eventId` (required): Event ID
- `pageIndex` (required): Page number
- `insertPosition` (required): Insert position (-1 for end)
- `options` (required): Array of choice strings (max 6)
- `cancelType` (optional): Cancel behavior (-1=no cancel, 0-5=branch to choice, default: -1)

**Request Example:**
```json
{
  "tool": "add_choice",
  "arguments": {
    "projectPath": "C:/Games/MyProject",
    "mapId": 1,
    "eventId": 1,
    "pageIndex": 0,
    "insertPosition": -1,
    "options": ["Yes", "No"],
    "cancelType": -1
  }
}
```

**Response Example:**
```json
{
  "content": [
    {
      "type": "text",
      "text": "Choices added."
    }
  ]
}
```

#### 14. `add_loop` - Add Loop
**Description:** Adds a loop structure (Loop + Repeat Above) to event commands.
**Parameters:**
- `projectPath`, `mapId`, `eventId`, `pageIndex`, `insertPosition` (required)

#### 15. `add_break_loop` - Break Loop
**Description:** Adds a command to break a loop.
**Parameters:**
- `projectPath`, `mapId`, `eventId`, `pageIndex`, `insertPosition` (required)

#### 16. `add_conditional_branch` - Add Conditional Branch
**Description:** Adds a conditional branch (If-Else-End).
**Parameters:**
- `projectPath`, `mapId`, `eventId`, `pageIndex`, `insertPosition` (required)
- `condition` (required): Condition parameter object
- `includeElse` (optional): Include Else branch (default: true)

#### 17. `delete_event_command` - Delete Event Command
**Description:** Deletes an event command at the specified index.
**Parameters:**
- `projectPath`, `mapId`, `eventId`, `pageIndex`, `commandIndex` (required)

#### 18. `update_event_command` - Update Event Command
**Description:** Overwrites an event command at the specified index with new content.
**Parameters:**
- `projectPath`, `mapId`, `eventId`, `pageIndex`, `commandIndex`, `newCommand` (required)

#### 19. `add_actor` - Add Actor
**Description:** Adds a new actor to the database.
**Parameters:**
- `projectPath`, `name` (required)
- `classId`, `initialLevel`, `maxLevel` (optional)

#### 20. `add_item` - Add Item
**Description:** Adds a new item to the database.
**Parameters:**
- `projectPath`, `name` (required)
- `price`, `consumable`, `scope`, `occasion` (optional)

#### 21. `add_skill` - Add Skill
**Description:** Adds a new skill to the database.
**Parameters:**
- `projectPath`, `name` (required)
- `mpCost`, `tpCost`, `scope`, `occasion` (optional)

#### 22. `draw_map_tile` - Draw Map Tile
**Description:** Places a tile at the specified coordinates on the map.
**Parameters:**
- `projectPath`, `mapId`, `x`, `y`, `layer`, `tileId` (required)

#### 23. `create_map` - Create New Map
**Description:** Creates a new map.
**Parameters:**
- `projectPath` (required): Absolute path to project folder
- `mapName` (required): Map name
- `width` (optional): Map width in tiles (default: 17)
- `height` (optional): Map height in tiles (default: 13)
- `parentMapId` (optional): Parent map ID (default: 0)

#### 24. `show_picture` - Show Picture
**Description:** Adds a picture display command to an event.
**Parameters:**
- `projectPath` (required): Absolute path to project folder
- `mapId` (required): Map ID
- `eventId` (required): Event ID
- `pageIndex` (required): Page number
- `insertPosition` (required): Insert position (-1 for end)
- `pictureId` (required): Picture number
- `pictureName` (required): Image file name
- `x`, `y` (required): Display coordinates
- `origin` (optional): Origin position (0=top-left, 1=center, default: 0)
- `scaleX`, `scaleY` (optional): Scale percentage (default: 100)
- `opacity` (optional): Opacity (0-255, default: 255)
- `blendMode` (optional): Blend mode (0-3, default: 0)

#### 25. `inspect_game_state` - Inspect Game State
**Description:** Retrieves variable and switch values from a running game (Puppeteer connection).
**Security:** Uses a whitelist approach, only allowing approved patterns. Input length limit (100 characters) and ID range check (1-9999) are also implemented.
**Allowed Pattern Examples:**
- `$gameVariables.value(1)` - Get variable value
- `$gameSwitches.value(1)` - Get switch value
- `$gameParty.gold()` - Get gold amount
- `$gameMap.mapId()` - Get current map ID
- `SceneManager._scene` - Get current scene
**Parameters:**
- `script` (required): JavaScript code to evaluate (only whitelisted patterns)
- `port` (optional): Debug port (default: 9222)

**Request Example:**
```json
{
  "tool": "inspect_game_state",
  "arguments": {
    "script": "$gameVariables.value(1)",
    "port": 9222
  }
}
```

**Response Example:**
```json
{
  "content": [
    {
      "type": "text",
      "text": "100"
    }
  ]
}
```

> ⚠️ **Dangerous Tool**: This tool executes JavaScript code. See "[Dangerous Tools Guide](#dangerous-tools-guide)" for details.

---

### Phase 5: Testing & Automation

#### 26. `run_playtest` - Run Playtest
**Description:** Launches Game.exe and takes a screenshot after the specified time. If Game.exe is not found, browser-based playtest (fallback mode) is automatically executed. Debug port for Puppeteer connection can also be specified.
**Parameters:**
- `projectPath` (required): Absolute path to project folder
- `duration` (optional): Wait time before capture in ms (default: 5000)
- `autoClose` (optional): If true, automatically closes the game after capture (default: false)
- `debugPort` (optional): Remote debugging port (e.g., 9222). Used when connecting with Puppeteer.
- `startNewGame` (optional): If true, skips title screen and starts a new game (default: false)

### Phase 6: Backup & Undo Functions

#### 27. `undo_last_change` - Undo Last Change
**Description:** Restores a file from the latest backup. If `filename` is not specified, the most recently modified file is automatically restored.
**Parameters:**
- `projectPath` (required): Absolute path to project folder
- `filename` (optional): File name to restore (e.g., 'Actors.json'). If omitted, automatically detects the most recently modified file

#### 28. `list_backups` - List Backups
**Description:** Displays a list of backups for a specified file or all files.
**Parameters:**
- `projectPath` (required): Absolute path to project folder
- `filename` (optional): File name to show backups for. If omitted, shows backups for all files

**About Backup Function:**
- Automatic backups are created for all file write operations (`write_data_file`, `add_actor`, `add_item`, `add_skill`, `write_plugin_code`, `update_plugins_config`, map operations, etc.)
- Backup files are saved in `.{timestamp}.bak` format
- Old backups are automatically cleaned up (keeps latest 5)
- Automatic rollback on error

---

## Typical Use Cases

### Scenario 1: Adding Sub-quests to Existing Project

**Goal**: Add 3 sub-quest events to an existing village map

**Steps**:
1. **Project Analysis**: Use `get_project_info` to get project information
2. **Event Search**: Use `search_events` to check existing events
3. **Get Event Page**: Use `get_event_page` to understand existing event structure
4. **Add Dialogue**: Use `add_dialogue` to add NPC dialogue
5. **Add Choices**: Use `add_choice` to add quest choices
6. **Conditional Branch**: Use `add_conditional_branch` to set quest completion conditions
7. **Playtest**: Use `run_playtest` to verify behavior

**AI Instruction Example**:
```
Analyze this project and add 3 sub-quests to Map 1's village.
Each quest should include dialogue, choices, and completion conditions.
```

### Scenario 2: Creating New Map and Placing Events

**Goal**: Create a new dungeon map and place treasure chest events

**Steps**:
1. **Create Map**: Use `create_map` to create a new map
2. **Place Tiles**: Use `draw_map_tile` to draw the map
3. **Create Events**: Use `add_dialogue` to add treasure chest messages
4. **Add Items**: Use `add_item` to create reward items
5. **Link Events**: Set item granting with conditional branches
6. **Test**: Use `run_playtest` to verify behavior

**AI Instruction Example**:
```
Create a new dungeon map and place 3 treasure chest events.
Each chest should contain different items.
```

### Scenario 3: Adding and Configuring Plugins

**Goal**: Add a custom plugin and update configuration

**Steps**:
1. **Create Plugin**: Use `write_plugin_code` to add plugin code
2. **Get Config**: Use `get_plugins_config` to check current configuration
3. **Update Config**: Use `update_plugins_config` to enable the plugin
4. **Test**: Use `run_playtest` to verify plugin behavior

**AI Instruction Example**:
```
Create a custom battle plugin and enable it.
```

---

## Dangerous Tools Guide

### Dangerous Tools List

The following tools require **careful use** for security reasons:

- **`inspect_game_state`**: Executes JavaScript code (protected by whitelist, but runtime errors may occur)

### Recommended Settings

**It is recommended to disable these in the initial state**. You can disable specific tools in your MCP client configuration:

```json
{
  "mcpServers": {
    "rpg-maker-mz": {
      "command": "rpg-maker-mz-mcp",
      "disabledTools": ["inspect_game_state"]
    }
  }
}
```

> ⚠️ **Note**: Some MCP clients may not support the `disabledTools` property. In that case, avoid using the tool or use it only in trusted environments.

### Security Measures

The `inspect_game_state` tool implements the following security measures:

- ✅ **Whitelist Approach**: Only approved patterns can be executed
- ✅ **Input Length Limit**: Up to 100 characters
- ✅ **ID Range Check**: Only allows range 1-9999
- ✅ **Path Traversal Protection**: Prevents unauthorized path access

Still, **avoid executing untrusted code**.

---

## Changelog

### v1.5.1 (2025-11-29)
- npm publication preparation complete (@rein634/rpg-maker-mz-mcp)
- Test coverage improvements (added tests for undo.ts, backup.ts)
- CI/CD configuration updates (coverage reports, E2E test automation)
- playtest.ts refactoring (527 lines → 311 lines, ~41% reduction)
- README improvements (added TL;DR, request examples, use cases)

### v1.5.0 (2025-11-29)
- **TypeScript Migration Complete**: All handlers layer and entry point migrated to TypeScript
- CI/CD Integration: Added type checking to GitHub Actions
- Significant improvement in type safety

### v1.4.1 (2025-11-29)
- Implementation of undo_last_change tool
- Implementation of list_backups tool
- toolSchemas.ts type definition enhancements (detailed schemas for plugins array, condition object)
- Added Logger.debug to empty catch blocks
- Moved robotjs to devDependencies

### v1.4.0 (2025-11-29)
- Security enhancements: Path traversal protection, arbitrary code execution warnings
- Error handling improvements and unification
- Improved async operation safety
- Eliminated magic numbers

### v1.3.0 (2025-11-29)
- New tools added: `add_choice`, `create_map`, `show_picture`, `check_assets_integrity`
- Unit test introduction (Vitest)
- Logger utility added
- Constant externalization
- TypeScript type definitions added

### v1.2.0 (2025-11-29)
- Added browser-based fallback functionality to `run_playtest` (Game.exe not required)

### v1.1.0 (2025-11-29)
- Organized implemented tools list (22 tools)
- Added `startNewGame` parameter to `run_playtest`

### v1.0.0 (2025-11-29)
- Initial release (16 tools at the time)
- MCP Resources implementation
- Zod Validation implementation

---

## License

MIT License
