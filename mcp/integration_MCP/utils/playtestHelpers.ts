import { Page } from "puppeteer";
import { Logger } from "./logger.js";
import { sleep } from "./validation.js";

export type HandlerContent = { type: string; text?: string; data?: string };

/**
 * Captures a screenshot of the game canvas via Puppeteer
 */
export async function captureGameScreenshot(
    page: Page,
    startNewGame: boolean,
    duration: number,
    startTime: number,
    postLaunchScript?: string
): Promise<HandlerContent[]> {
    const content: HandlerContent[] = [];
    try {
        await page.waitForSelector('#gameCanvas', { timeout: duration });
        await Logger.debug("Found #gameCanvas.");

        if (startNewGame) {
            await Logger.debug("Attempting to start new game...");
            try {
                await page.waitForFunction(() => {
                    const win = globalThis as any;
                    return win.SceneManager && win.SceneManager._scene && win.SceneManager._scene.constructor.name === 'Scene_Title';
                }, { timeout: 10000 });
                await Logger.debug("Scene_Title detected.");
                await page.evaluate(() => {
                    const win = globalThis as any;
                    win.DataManager.setupNewGame();
                    win.SceneManager.goto(win.Scene_Map);
                });
                await Logger.debug("New Game command sent.");
            } catch (e: unknown) {
                const err = e as Error;
                await Logger.debug(`Failed to start new game: ${err.message}`);
            }
        }

        const remainingTime = Math.max(2000, duration - (Date.now() - startTime));
        try {
            await page.waitForFunction((targetScene: string | null) => {
                const win = globalThis as any;
                if (!win.SceneManager || !win.SceneManager._scene) return false;
                const sceneName = win.SceneManager._scene.constructor.name;
                if (sceneName === 'Scene_Boot') return false;
                if (targetScene && sceneName !== targetScene) return false;
                return true;
            }, { timeout: remainingTime }, startNewGame ? 'Scene_Map' : null);
            await Logger.debug("Scene ready check passed.");
        } catch (e: unknown) {
            await Logger.debug("Scene ready check timed out.");
        }

        if (postLaunchScript) {
            await Logger.debug(`Executing post-launch script: ${postLaunchScript}`);
            try {
                await page.evaluate((script) => {
                    try {
                        const func = new Function(script);
                        func();
                    } catch (e) {
                        console.error("Post-launch script error:", e);
                        throw e;
                    }
                }, postLaunchScript);
                await Logger.debug("Post-launch script executed.");
            } catch (e: unknown) {
                const err = e as Error;
                await Logger.error(`Post-launch script failed: ${err.message}`, err);
            }
        }

        await sleep(1000);

        try {
            const canvasDataUrl = await page.evaluate(() => {
                const canvas = (globalThis as any).document.querySelector('#gameCanvas');
                return canvas.toDataURL('image/png');
            });
            const base64Data = canvasDataUrl.replace(/^data:image\/png;base64,/, "");
            content.push({ type: "image/png", data: base64Data });
            content.push({ type: "text", text: `Game launched and screenshot taken via Canvas.toDataURL. (New Game: ${startNewGame})` });
            await Logger.debug("Screenshot taken via Canvas.toDataURL.");
        } catch (e: unknown) {
            const err = e as Error;
            await Logger.debug(`Canvas toDataURL failed: ${err.message}`);
            const base64Img = await page.screenshot({ encoding: 'base64' }) as string;
            content.push({ type: "image/png", data: base64Img });
            content.push({ type: "text", text: `Game launched and screenshot taken via Puppeteer page.screenshot. (New Game: ${startNewGame})` });
            await Logger.debug("Screenshot taken via page.screenshot.");
        }
    } catch (e: unknown) {
        await Logger.error("Puppeteer operation failed", e);
    }
    return content;
}
