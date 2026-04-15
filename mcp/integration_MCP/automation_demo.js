import { spawn } from "child_process";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const serverPath = path.join(__dirname, "index.js");
const projectPath = path.join(__dirname, "test_project");

// Start the MCP server
const server = spawn("node", [serverPath], {
    stdio: ["pipe", "pipe", "inherit"],
});

// Helper to send requests
const sendRequest = (req) => {
    return new Promise((resolve, reject) => {
        console.log("Sending Request:", req.method, req.params ? req.params.name : "");
        server.stdin.write(JSON.stringify(req) + "\n");
        // Simple one-off response handling for demo purposes
        // In a real runner, we'd have a proper message loop
        resolve();
    });
};

// We need a listener to capture output
server.stdout.on("data", (data) => {
    const lines = data.toString().split("\n");
    for (const line of lines) {
        if (!line.trim()) continue;
        try {
            const res = JSON.parse(line);
            if (res.result) {
                console.log("Response Result:", JSON.stringify(res.result.content[0].text).substring(0, 100) + "...");
            }
        } catch (e) {
            // ignore partial lines
        }
    }
});

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function runDemo() {
    console.log("=== Starting Automation Demo ===");

    // 1. Initialize
    await sendRequest({
        jsonrpc: "2.0",
        id: 1,
        method: "initialize",
        params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "auto-runner", version: "1.0" } }
    });
    await sendRequest({ jsonrpc: "2.0", method: "notifications/initialized" });
    await sleep(1000);

    // 2. Read original data
    console.log("\n--- Reading Original Actor Data ---");
    await sendRequest({
        jsonrpc: "2.0", id: 2, method: "tools/call",
        params: {
            name: "read_data_file",
            arguments: { projectPath, filename: "Actors.json" }
        }
    });
    await sleep(1000);

    // 3. Modify data (Change "Reid" to "Reid (Auto-Test)")
    console.log("\n--- Modifying Actor Data (Reid -> Reid (Auto-Test)) ---");
    const newActors = [
        null,
        { "id": 1, "name": "Reid (Auto-Test)", "classId": 1, "level": 50, "characterName": "Actor1", "characterIndex": 0, "faceName": "Actor1", "faceIndex": 0, "traits": [], "initialLevel": 1, "maxLevel": 99, "name": "Reid (Auto-Test)", "nickname": "", "note": "", "profile": "" },
        { "id": 2, "name": "Priscilla", "classId": 2, "level": 1, "characterName": "Actor1", "characterIndex": 1, "faceName": "Actor1", "faceIndex": 1, "traits": [], "initialLevel": 1, "maxLevel": 99, "name": "Priscilla", "nickname": "", "note": "", "profile": "" },
        { "id": 3, "name": "Gale", "classId": 3, "level": 1, "characterName": "Actor1", "characterIndex": 2, "faceName": "Actor1", "faceIndex": 2, "traits": [], "initialLevel": 1, "maxLevel": 99, "name": "Gale", "nickname": "", "note": "", "profile": "" },
        { "id": 4, "name": "Michelle", "classId": 4, "level": 1, "characterName": "Actor1", "characterIndex": 3, "faceName": "Actor1", "faceIndex": 3, "traits": [], "initialLevel": 1, "maxLevel": 99, "name": "Michelle", "nickname": "", "note": "", "profile": "" }
    ];

    await sendRequest({
        jsonrpc: "2.0", id: 3, method: "tools/call",
        params: {
            name: "write_data_file",
            arguments: {
                projectPath,
                filename: "Actors.json",
                content: JSON.stringify(newActors, null, 2)
            }
        }
    });
    await sleep(1000);

    console.log("\n=== Data Modified. Please Reload Browser to Verify. ===");
    console.log("Waiting 10 seconds for verification...");
    await sleep(10000);

    // 4. Revert data
    console.log("\n--- Reverting Actor Data ---");
    const originalActors = [
        null,
        { "id": 1, "name": "Reid", "classId": 1, "level": 1, "characterName": "Actor1", "characterIndex": 0, "faceName": "Actor1", "faceIndex": 0, "traits": [], "initialLevel": 1, "maxLevel": 99, "name": "Reid", "nickname": "", "note": "", "profile": "" },
        { "id": 2, "name": "Priscilla", "classId": 2, "level": 1, "characterName": "Actor1", "characterIndex": 1, "faceName": "Actor1", "faceIndex": 1, "traits": [], "initialLevel": 1, "maxLevel": 99, "name": "Priscilla", "nickname": "", "note": "", "profile": "" },
        { "id": 3, "name": "Gale", "classId": 3, "level": 1, "characterName": "Actor1", "characterIndex": 2, "faceName": "Actor1", "faceIndex": 2, "traits": [], "initialLevel": 1, "maxLevel": 99, "name": "Gale", "nickname": "", "note": "", "profile": "" },
        { "id": 4, "name": "Michelle", "classId": 4, "level": 1, "characterName": "Actor1", "characterIndex": 3, "faceName": "Actor1", "faceIndex": 3, "traits": [], "initialLevel": 1, "maxLevel": 99, "name": "Michelle", "nickname": "", "note": "", "profile": "" }
    ];

    await sendRequest({
        jsonrpc: "2.0", id: 4, method: "tools/call",
        params: {
            name: "write_data_file",
            arguments: {
                projectPath,
                filename: "Actors.json",
                content: JSON.stringify(originalActors, null, 2)
            }
        }
    });
    await sleep(1000);

    console.log("\n=== Demo Completed. Server shutting down. ===");
    server.kill();
}

runDemo();
