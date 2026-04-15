import puppeteer from 'puppeteer';

class MZDriver {
    constructor(browser, page) {
        this.browser = browser;
        this.page = page;
    }

    static async connect(port = 9222) {
        const browserUrl = `http://127.0.0.1:${port}`;
        const browser = await puppeteer.connect({
            browserURL: browserUrl,
            defaultViewport: null
        });
        const pages = await browser.pages();
        const page = pages[0];
        return new MZDriver(browser, page);
    }

    async close() {
        await this.browser.disconnect();
    }

    async evaluate(script) {
        return await this.page.evaluate(script);
    }

    async clickCommand(text) {
        // Find element containing text and click it
        // This is a heuristic, might need adjustment based on MZ's DOM
        await this.page.evaluate((searchText) => {
            const elements = Array.from(document.querySelectorAll('*'));
            const target = elements.find(el => el.textContent.includes(searchText) && el.offsetParent !== null);
            if (target) {
                target.click();
                // Also try touch event for mobile emulation
                const touchObj = new Touch({
                    identifier: Date.now(),
                    target: target,
                    clientX: target.getBoundingClientRect().x,
                    clientY: target.getBoundingClientRect().y,
                    radiusX: 2.5,
                    radiusY: 2.5,
                    rotationAngle: 10,
                    force: 0.5,
                });
                const touchEvent = new TouchEvent('touchstart', {
                    cancelable: true,
                    bubbles: true,
                    touches: [touchObj],
                    targetTouches: [],
                    changedTouches: [touchObj],
                    shiftKey: true,
                });
                target.dispatchEvent(touchEvent);
            } else {
                throw new Error(`Element with text "${searchText}" not found`);
            }
        }, text);
    }

    async newGame() {
        // Simulate Enter key or click "New Game"
        // MZ Title Screen usually handles input via keyboard or touch
        await this.page.keyboard.press('Enter');
        await new Promise(r => setTimeout(r, 1000));
        await this.page.keyboard.press('Enter'); // Confirm if needed
    }

    async movePlayer(direction, steps = 1) {
        const keyMap = {
            'up': 'ArrowUp',
            'down': 'ArrowDown',
            'left': 'ArrowLeft',
            'right': 'ArrowRight'
        };
        const key = keyMap[direction.toLowerCase()];
        if (!key) throw new Error(`Invalid direction: ${direction}`);

        for (let i = 0; i < steps; i++) {
            await this.page.keyboard.down(key);
            await new Promise(r => setTimeout(r, 200)); // Hold for movement
            await this.page.keyboard.up(key);
            await new Promise(r => setTimeout(r, 100)); // Wait between steps
        }
    }

    async getSwitch(id) {
        return await this.page.evaluate((switchId) => {
            return $gameSwitches.value(switchId);
        }, id);
    }

    async getVariable(id) {
        return await this.page.evaluate((varId) => {
            return $gameVariables.value(varId);
        }, id);
    }

    async takeScreenshot(path) {
        await this.page.screenshot({ path: path });
    }
}

export default MZDriver;
