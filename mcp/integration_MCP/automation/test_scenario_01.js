import { spawn } from "child_process";
import path from "path";
import { fileURLToPath } from "url";
import puppeteer from "puppeteer";

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

server.stdout.on("data", async (data) => {
    const lines = data.toString().split("\n");
    for (const line of lines) {
        if (!line.trim()) continue;
        try {
            const res = JSON.parse(line);
            if (res.result) {
                console.log("Response:", JSON.stringify(res.result, null, 2));
                if (res.id === 2) {
                    // Game launched. Connect Puppeteer.
                    await runPuppeteerTest();
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

async function runPuppeteerTest() {
    console.log("Connecting Puppeteer...");
    // Give game some time to initialize DevTools
    await new Promise(r => setTimeout(r, 3000));

    try {
        const browser = await puppeteer.connect({
            browserURL: 'http://localhost:9222',
            defaultViewport: null
        });

        const pages = await browser.pages();
        const page = pages[0];
        console.log("Connected to page:", await page.title());

        // Take a screenshot via Puppeteer
        await page.screenshot({ path: path.join(__dirname, "../screenshots/puppeteer_initial.png") });
        console.log("Screenshot taken: puppeteer_initial.png");

        // Wait for Title Screen canvas or element
        // RPG Maker MZ uses Canvas. We can't easily select UI elements via DOM.
        // But we can execute JS in the game context.

        // Check if Scene_Title is active
        const isTitle = await page.evaluate(() => {
            return SceneManager._scene instanceof Scene_Title;
        });
        console.log("Is Title Scene:", isTitle);

        if (isTitle) {
            // Simulate "New Game" command
            // In MZ, command window is usually active.
            // We can try to call processOk() or similar, or simulate input.
            console.log("Starting New Game...");
            await page.evaluate(() => {
                // Simulate Enter key or Touch
                // Or directly call SceneManager.push(Scene_Map); for testing?
                // Better to use DataManager.setupNewGame(); SceneManager.goto(Scene_Map);
                DataManager.setupNewGame();
                SceneManager.goto(Scene_Map);
            });

            // Wait for Map Scene
            await new Promise(r => setTimeout(r, 2000));
            const isMap = await page.evaluate(() => {
                return SceneManager._scene instanceof Scene_Map;
            });
            console.log("Is Map Scene:", isMap);

            if (isMap) {
                await page.screenshot({ path: path.join(__dirname, "../screenshots/puppeteer_map.png") });
                console.log("Screenshot taken: puppeteer_map.png");
                console.log("SUCCESS: New Game started.");
            } else {
                console.error("FAILED: Did not transition to Map scene.");
            }
        }

        // Cleanup
        await browser.disconnect();
        // We can kill the game process via server or just exit (server will die, game might stay open if detached)
        // But run_playtest with autoClose=false leaves it open.
        // We should probably close it.
        // Since we don't have the PID here easily (unless we ask server), we can rely on manual close or taskkill in a real env.
        // For this test, we can try to close window via Puppeteer?
        // await page.close(); // Might close the game window

        console.log("=== Test Complete ===");
        process.exit(0);

    } catch (e) {
        console.error("Puppeteer Error:", e);
        process.exit(1);
    }
}

console.log("=== Testing Puppeteer Integration ===");

// 1. Initialize
sendRequest({
    jsonrpc: "2.0",
    id: 1,
    method: "initialize",
    params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "test-runner", version: "1.0" } }
});

// 2. Launch Game with Debug Port
setTimeout(() => {
    sendRequest({
        jsonrpc: "2.0",
        id: 2,
        method: "tools/call",
        params: {
            name: "run_playtest",
            arguments: {
                projectPath,
                duration: 2000,
                autoClose: false,
                debugPort: 9222
            }
        }
    });
}, 1000);
