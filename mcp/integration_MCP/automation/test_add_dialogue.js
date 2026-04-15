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

server.stdout.on("data", (data) => {
    const lines = data.toString().split("\n");
    for (const line of lines) {
        if (!line.trim()) continue;
        try {
            const res = JSON.parse(line);
            if (res.result) {
                console.log("Response:", JSON.stringify(res.result, null, 2));
                if (res.id === 2) {
                    console.log("\n=== Test Complete ===");
                    process.exit(0);
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
    console.log("=== Testing add_dialogue Tool ===");

    // Initialize
    sendRequest({
        jsonrpc: "2.0",
        id: 1,
        method: "initialize",
        params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "test-runner", version: "1.0" } }
    });

    await new Promise(r => setTimeout(r, 1000));

    // Test add_dialogue
    sendRequest({
        jsonrpc: "2.0",
        id: 2,
        method: "tools/call",
        params: {
            name: "add_dialogue",
            arguments: {
                projectPath,
                mapId: 1,
                eventId: 1,
                pageIndex: 0,
                insertPosition: -1,
                text: "이것은 테스트 메시지입니다. \\n추상화 레이어가 제대로 작동하고 있습니다!",
                face: "Actor1",
                faceIndex: 0
            }
        }
    });
}

runTest();
