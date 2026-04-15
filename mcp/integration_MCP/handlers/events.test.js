import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { fileURLToPath } from 'url';
import { addDialogue, showPicture, addChoice, searchEvents, getEventPage } from './events.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const sourceProjectPath = path.join(__dirname, '../test_project');

let tempRoot;
let testProjectPath;

async function setupTempProject() {
    tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'mz-events-'));
    testProjectPath = path.join(tempRoot, 'project');

    // Copy files individually, excluding .bak files
    await fs.mkdir(testProjectPath, { recursive: true });
    await fs.mkdir(path.join(testProjectPath, 'data'), { recursive: true });

    const sourceDataDir = path.join(sourceProjectPath, 'data');
    const targetDataDir = path.join(testProjectPath, 'data');
    const files = await fs.readdir(sourceDataDir);

    for (const file of files) {
        if (!file.endsWith('.bak')) {
            const sourceFile = path.join(sourceDataDir, file);
            try {
                const stat = await fs.stat(sourceFile);
                if (stat.isFile()) {
                    await fs.copyFile(
                        sourceFile,
                        path.join(targetDataDir, file)
                    );
                }
            } catch {
                // Skip if file doesn't exist or is not a file
            }
        }
    }

    // Copy other directories/files if needed
    const otherItems = await fs.readdir(sourceProjectPath);
    for (const item of otherItems) {
        if (item !== 'data') {
            const sourcePath = path.join(sourceProjectPath, item);
            const targetPath = path.join(testProjectPath, item);
            const stat = await fs.stat(sourcePath);
            if (stat.isDirectory()) {
                await fs.cp(sourcePath, targetPath, { recursive: true });
            } else {
                await fs.copyFile(sourcePath, targetPath);
            }
        }
    }
}

async function cleanupTempProject() {
    if (tempRoot) {
        await fs.rm(tempRoot, { recursive: true, force: true }).catch(() => {});
        tempRoot = undefined;
        testProjectPath = undefined;
    }
}

describe('events', () => {
    beforeEach(async () => {
        await setupTempProject();
    });

    afterEach(async () => {
        await cleanupTempProject();
    });

    describe('addDialogue', () => {
        it('should successfully execute addDialogue', async () => {
            if (!testProjectPath) throw new Error('testProjectPath not set');
            const result = await addDialogue({
                projectPath: testProjectPath,
                mapId: 1,
                eventId: 1,
                pageIndex: 0,
                insertPosition: -1,
                text: '테스트 대화'
            });

            expect(result.content[0].text).toContain('Added dialogue');
        });

        it('should throw error for invalid map ID', async () => {
            if (!testProjectPath) throw new Error('testProjectPath not set');
            await expect(addDialogue({
                projectPath: testProjectPath,
                mapId: 9999,
                eventId: 1,
                pageIndex: 0,
                insertPosition: -1,
                text: 'Test'
            })).rejects.toThrow();
        });
    });

    describe('showPicture', () => {
        it('should add show picture command with pictureName parameter', async () => {
            if (!testProjectPath) throw new Error('testProjectPath not set');
            const result = await showPicture({
                projectPath: testProjectPath,
                mapId: 1,
                eventId: 1,
                pageIndex: 0,
                insertPosition: -1,
                pictureId: 1,
                pictureName: 'TestPicture',
                x: 100,
                y: 200
            });

            expect(result.content[0].text).toContain('TestPicture');
            expect(result.content[0].text).toContain('ID: 1');
        });
    });

    describe('addChoice', () => {
        it('should successfully execute addChoice', async () => {
            if (!testProjectPath) throw new Error('testProjectPath not set');
            const result = await addChoice({
                projectPath: testProjectPath,
                mapId: 1,
                eventId: 1,
                pageIndex: 0,
                insertPosition: -1,
                options: ['테스트 1', '테스트 2']
            });

            expect(result.content[0].text).toContain('Added choice');
        });
    });

    describe('searchEvents', () => {
        it('should find text in map events', async () => {
            if (!testProjectPath) throw new Error('testProjectPath not set');
            const result = await searchEvents({
                projectPath: testProjectPath,
                query: 'Test'
            });

            expect(result.content[0].text).toBeDefined();
            const matches = JSON.parse(result.content[0].text);
            expect(Array.isArray(matches)).toBe(true);
        });
    });

    describe('getEventPage', () => {
        it('should get event page commands', async () => {
            if (!testProjectPath) throw new Error('testProjectPath not set');
            const result = await getEventPage({
                projectPath: testProjectPath,
                mapId: 1,
                eventId: 1,
                pageIndex: 0
            });

            expect(result.content[0].text).toBeDefined();
            expect(result.content[0].text.length).toBeGreaterThan(0);
        });

        it('should throw error for invalid event ID', async () => {
            if (!testProjectPath) throw new Error('testProjectPath not set');
            await expect(getEventPage({
                projectPath: testProjectPath,
                mapId: 1,
                eventId: 9999,
                pageIndex: 0
            })).rejects.toThrow();
        });
    });
});
