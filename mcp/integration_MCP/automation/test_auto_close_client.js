import { spawn } from "child_process";
import path from "path";

const serverPath = path.resolve("index.js");
const projectPath = path.resolve("test_project");

async function runTest() {
    console.log("Starting MCP server for Playtest...");
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
                    console.log("Response received.");
                    // Check if content mentions autoClose
                    const content = response.result.content;
                    const textContent = content.find(c => c.type === "text")?.text;
                    console.log("Result Text:", textContent);
                    process.exit(0);
                }
                if (response.error) {
                    console.error("Error:", response.error);
                    process.exit(1);
                }
            } catch (e) {
                // Ignore
            }
        }
    });

    // Wait a bit
    await new Promise(resolve => setTimeout(resolve, 1000));

    const request = {
        jsonrpc: "2.0",
        id: 2,
        method: "tools/call",
        params: {
            name: "run_playtest",
            arguments: {
                projectPath: projectPath,
                duration: 3000,
                autoClose: true
            }
        }
    };

    console.log("Sending run_playtest request with autoClose: true...");
    sendRequest(request);
}

runTest();
