import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import path from "path";
import fs from "fs/promises";

// Mock server to test the tool logic directly (or we can just run the tool logic)
// For simplicity, we will import the logic if possible, but since index.js is an ES module
// and the server is initialized at top level, we might need to spawn it or just replicate the logic for testing.
// However, since we are in the same environment, we can just run a client to test the server.
// But wait, the server uses stdio transport.

// Let's create a simple script that acts as a client to the MCP server
// OR, since we have access to the code, we can just run a small script that imports the modified index.js?
// No, index.js starts the server immediately.

// Better approach: Create a test script that spawns the MCP server process and sends requests to it via stdin/stdout.

import { spawn } from "child_process";

const serverPath = path.resolve("index.js");
const projectPath = path.resolve("test_project");

async function runTest() {
    console.log("Starting MCP server...");
    const serverProcess = spawn("node", [serverPath], {
        stdio: ["pipe", "pipe", "inherit"]
    });

    const sendRequest = (request) => {
        const json = JSON.stringify(request);
        serverProcess.stdin.write(json + "\n");
    };

    serverProcess.stdout.on("data", (data) => {
        const lines = data.toString().split("\n");
        for (const line of lines) {
            if (!line.trim()) continue;
            try {
                const response = JSON.parse(line);
                if (response.result) {
                    console.log("Response:", JSON.stringify(response.result, null, 2));
                    process.exit(0);
                }
                if (response.error) {
                    console.error("Error:", response.error);
                    process.exit(1);
                }
            } catch (e) {
                // Ignore non-JSON output
            }
        }
    });

    // Wait a bit for server to start
    await new Promise(resolve => setTimeout(resolve, 1000));

    // Construct a JSON-RPC request
    const request = {
        jsonrpc: "2.0",
        id: 1,
        method: "tools/call",
        params: {
            name: "get_event_page",
            arguments: {
                projectPath: projectPath,
                mapId: 1,
                eventId: 1,
                pageIndex: 0
            }
        }
    };

    console.log("Sending get_event_page request...");
    sendRequest(request);
}

runTest();
