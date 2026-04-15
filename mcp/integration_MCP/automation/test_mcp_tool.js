import { spawn } from "child_process";
import path from "path";
import { fileURLToPath } from "url";
import fs from "fs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const serverPath = path.join(__dirname, "../index.js");
const projectPath = path.join(__dirname, "../test_project");

// Start the MCP server
const server = spawn("node", [serverPath], {
    stdio: ["pipe", "pipe", "pipe"],
});

server.stderr.on("data", (data) => {
    console.error("Server Error:", data.toString());
});

const sendRequest = (req) => {
    return new Promise((resolve, reject) => {
        console.log("Sending Request:", req.method, req.params ? req.params.name : "");
        server.stdin.write(JSON.stringify(req) + "\n");
        resolve();
    });
};

server.stdout.on("data", (data) => {
    const lines = data.toString().split("\n");
    for (const line of lines) {
        if (!line.trim()) continue;
        try {
            const res = JSON.parse(line);
            if (res.result) {
                console.log("Response received.");
                if (res.result.content && res.result.content[0].type === "image/png") {
                    console.log("Success: Image data received!");
                    const base64Data = res.result.content[0].data;
                    const outputPath = path.join(__dirname, "test_mcp_screenshot.png");
                    fs.writeFileSync(outputPath, Buffer.from(base64Data, "base64"));
                    console.log(`Saved screenshot to: ${outputPath}`);
                    process.exit(0);
                } else {
                    console.log("Result:", JSON.stringify(res.result).substring(0, 200));
                }
            } else if (res.error) {
                console.error("Error:", res.error);
                process.exit(1);
            }
        } catch (e) {
            // ignore
        }
    }
});

async function runTest() {
    console.log("=== Testing run_playtest Tool ===");

    // Initialize
    await sendRequest({
        jsonrpc: "2.0",
        id: 1,
        method: "initialize",
        params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "test-runner", version: "1.0" } }
    });

    // Wait a bit
    await new Promise(r => setTimeout(r, 1000));

    // Call run_playtest
    await sendRequest({
        jsonrpc: "2.0", id: 2, method: "tools/call",
        params: {
            name: "run_playtest",
            arguments: { projectPath, duration: 3000 }
        }
    });
}

runTest();
