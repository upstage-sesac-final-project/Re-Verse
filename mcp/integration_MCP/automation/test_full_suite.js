import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const projectPath = path.resolve(__dirname, "../test_project");

async function main() {
    const transport = new StdioClientTransport({
        command: "node",
        args: [path.resolve(__dirname, "../index.js")],
    });

    const client = new Client(
        { name: "test-client", version: "1.0.0" },
        { capabilities: {} }
    );

    await client.connect(transport);

    try {
        console.log("Starting Full Feature Test Suite...");

        // 1. Database Tools
        console.log("\n--- Testing Database Tools ---");
        const actorRes = await client.callTool({
            name: "add_actor",
            arguments: { projectPath, name: "TestActor", classId: 1, initialLevel: 5 }
        });
        console.log("Add Actor:", actorRes.content[0].text);

        const itemRes = await client.callTool({
            name: "add_item",
            arguments: { projectPath, name: "TestPotion", price: 100 }
        });
        console.log("Add Item:", itemRes.content[0].text);

        const skillRes = await client.callTool({
            name: "add_skill",
            arguments: { projectPath, name: "TestSkill", mpCost: 10 }
        });
        console.log("Add Skill:", skillRes.content[0].text);

        // 2. Map Editing
        console.log("\n--- Testing Map Editing ---");
        // Create a new map first
        const mapRes = await client.callTool({
            name: "create_map",
            arguments: { projectPath, mapName: "TestMap_Full" }
        });
        console.log("Create Map:", mapRes.content[0].text);
        // Extract Map ID from response (simplified parsing)
        const mapIdMatch = mapRes.content[0].text.match(/ID: (\d+)/);
        const mapId = mapIdMatch ? parseInt(mapIdMatch[1]) : 2; // Default to 2 if parse fails

        // Draw tiles
        await client.callTool({
            name: "draw_map_tile",
            arguments: { projectPath, mapId, x: 5, y: 5, layer: 0, tileId: 1555 } // Some grass tile
        });
        console.log(`Drew tile at (5,5) on Map ${mapId}`);

        // 3. Event Creation & Modification
        console.log("\n--- Testing Event Modification ---");
        // Add dialogue
        await client.callTool({
            name: "add_dialogue",
            arguments: { projectPath, mapId, eventId: 1, pageIndex: 0, insertPosition: -1, text: "Original Text" }
        });
        console.log("Added initial dialogue");

        // Update dialogue (assuming it's at index 0 or last)
        // We need to know the index. Let's get the page first.
        const pageRes = await client.callTool({
            name: "get_event_page",
            arguments: { projectPath, mapId, eventId: 1, pageIndex: 0 }
        });
        const commands = JSON.parse(pageRes.content[0].text);
        const lastCmdIndex = commands.length - 1; // The one we just added (Code 401 is Text)

        // Update it
        await client.callTool({
            name: "update_event_command",
            arguments: {
                projectPath, mapId, eventId: 1, pageIndex: 0, commandIndex: lastCmdIndex,
                newCommand: { code: 401, parameters: ["Updated Text"] }
            }
        });
        console.log("Updated dialogue");

        // Delete it
        await client.callTool({
            name: "delete_event_command",
            arguments: { projectPath, mapId, eventId: 1, pageIndex: 0, commandIndex: lastCmdIndex }
        });
        console.log("Deleted dialogue");

        // 4. Advanced Event Structures
        console.log("\n--- Testing Advanced Events ---");
        await client.callTool({
            name: "add_loop",
            arguments: { projectPath, mapId, eventId: 1, pageIndex: 0, insertPosition: -1 }
        });
        console.log("Added Loop");

        await client.callTool({
            name: "add_conditional_branch",
            arguments: {
                projectPath, mapId, eventId: 1, pageIndex: 0, insertPosition: -1,
                condition: { code: 1, dataA: 1, operation: 0, dataB: 0 } // Switch 1 ON
            }
        });
        console.log("Added Conditional Branch");

        console.log("\nTest Suite Completed Successfully!");

    } catch (error) {
        console.error("Test Failed:", error);
    } finally {
        await client.close();
    }
}

main();
