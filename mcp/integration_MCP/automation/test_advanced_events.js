import { spawn } from "child_process";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const serverPath = path.join(__dirname, "../index.js");
const projectPath = path.join(__dirname, "../test_project");

const server = spawn("node", [serverPath], {
    stdio: ["pipe", "pipe", "pipe"],
});

server.stderr.on("data", (data) => {
    console.error("Server Error:", data.toString());
});

const sendRequest = (req) => {
    console.log("Sending Request:", req.method, req.params ? req.params.name : "");
    server.stdin.write(JSON.stringify(req) + "\n");
};

let step = 0;

server.stdout.on("data", (data) => {
    const lines = data.toString().split("\n");
    for (const line of lines) {
        if (!line.trim()) continue;
        try {
            const res = JSON.parse(line);
            if (res.result) {
                console.log("Response:", JSON.stringify(res.result, null, 2));
                nextStep();
            } else if (res.error) {
                console.error("Error:", res.error);
                process.exit(1);
            }
        } catch (e) {
            // ignore
        }
    }
});

function nextStep() {
    step++;
    if (step === 1) {
        // 1. Add Loop
        sendRequest({
            jsonrpc: "2.0",
            id: 2,
            method: "tools/call",
            params: {
                name: "add_loop",
                arguments: {
                    projectPath,
                    mapId: 1,
                    eventId: 1,
                    pageIndex: 0,
                    insertPosition: -1
                }
            }
        });
    } else if (step === 2) {
        // 2. Add Conditional Branch
        sendRequest({
            jsonrpc: "2.0",
            id: 3,
            method: "tools/call",
            params: {
                name: "add_conditional_branch",
                arguments: {
                    projectPath,
                    mapId: 1,
                    eventId: 1,
                    pageIndex: 0,
                    insertPosition: -1,
                    condition: {
                        code: 0, // Switch
                        dataA: 1, // Switch ID 1
                        operation: 0, // Equal
                        dataB: 0 // ON
                    },
                    includeElse: true
                }
            }
        });
    } else if (step === 3) {
        // 3. Verify with get_event_page
        sendRequest({
            jsonrpc: "2.0",
            id: 4,
            method: "tools/call",
            params: {
                name: "get_event_page",
                arguments: {
                    projectPath,
                    mapId: 1,
                    eventId: 1,
                    pageIndex: 0
                }
            }
        });
    } else if (step === 4) {
        console.log("\n=== Test Complete ===");
        process.exit(0);
    }
}

console.log("=== Testing Advanced Event Tools ===");

// 0. Initialize
sendRequest({
    jsonrpc: "2.0",
    id: 1,
    method: "initialize",
    params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "test-runner", version: "1.0" } }
});
