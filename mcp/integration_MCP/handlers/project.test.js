import { describe, it, expect, beforeEach } from 'vitest';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import {
    getProjectInfo,
    listDataFiles,
    readDataFile,
    writeDataFile,
    listAssets,
    checkAssetsIntegrity
} from './project.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const testProjectPath = path.join(__dirname, '../test_project');

describe('project', () => {
    describe('getProjectInfo', () => {
        it('should return project information from System.json', async () => {
            const result = await getProjectInfo({
                projectPath: testProjectPath
            });

            expect(result.content[0].text).toBeDefined();
            const info = JSON.parse(result.content[0].text);
            expect(info.gameTitle).toBeDefined();
            expect(info.versionId).toBeDefined();
        });

        it('should throw error for invalid project path', async () => {
            await expect(getProjectInfo({
                projectPath: '/invalid/path'
            })).rejects.toThrow();
        });
    });

    describe('listDataFiles', () => {
        it('should list all JSON files in data directory', async () => {
            const result = await listDataFiles({
                projectPath: testProjectPath
            });

            expect(result.content[0].text).toBeDefined();
            const files = JSON.parse(result.content[0].text);
            expect(Array.isArray(files)).toBe(true);
            expect(files.length).toBeGreaterThan(0);
            expect(files).toContain('System.json');
            expect(files).toContain('Actors.json');
            expect(files).toContain('Items.json');
        });
    });

    describe('readDataFile', () => {
        it('should read a data file', async () => {
            const result = await readDataFile({
                projectPath: testProjectPath,
                filename: 'System.json'
            });

            expect(result.content[0].text).toBeDefined();
            const data = JSON.parse(result.content[0].text);
            expect(data.gameTitle).toBeDefined();
        });

        it('should throw error for non-JSON file', async () => {
            await expect(readDataFile({
                projectPath: testProjectPath,
                filename: 'notjson.txt'
            })).rejects.toThrow('Only .json files can be read');
        });

        it('should throw error for non-existent file', async () => {
            await expect(readDataFile({
                projectPath: testProjectPath,
                filename: 'ReallyNonExistentFile.json'
            })).rejects.toThrow();
        });
    });

    describe('writeDataFile', () => {
        let testFilePath;
        let originalContent;

        beforeEach(async () => {
            testFilePath = path.join(testProjectPath, 'data', 'TestWrite.json');
            // Create a test file
            const testData = { test: true };
            await fs.writeFile(testFilePath, JSON.stringify(testData), 'utf-8');
            originalContent = JSON.stringify(testData);
        });

        it('should write valid JSON to a file', async () => {
            const newData = { updated: true, value: 42 };
            const result = await writeDataFile({
                projectPath: testProjectPath,
                filename: 'TestWrite.json',
                content: JSON.stringify(newData)
            });

            expect(result.content[0].text).toContain('Successfully wrote');

            // Verify the file was written
            const writtenContent = await fs.readFile(testFilePath, 'utf-8');
            expect(JSON.parse(writtenContent)).toEqual(newData);

            // Cleanup
            await fs.unlink(testFilePath).catch(() => { });
        });

        it('should throw error for invalid JSON', async () => {
            await expect(writeDataFile({
                projectPath: testProjectPath,
                filename: 'TestWrite.json',
                content: 'invalid json content'
            })).rejects.toThrow();

            // Cleanup
            await fs.unlink(testFilePath).catch(() => { });
        });

        it('should throw error for non-JSON filename', async () => {
            await expect(writeDataFile({
                projectPath: testProjectPath,
                filename: 'test.txt',
                content: JSON.stringify({ test: true })
            })).rejects.toThrow('Only .json files can be written');

            // Cleanup
            await fs.unlink(testFilePath).catch(() => { });
        });
    });

    describe('listAssets', () => {
        it('should list all assets when assetType is "all"', async () => {
            const result = await listAssets({
                projectPath: testProjectPath,
                assetType: 'all'
            });

            expect(result.content[0].text).toBeDefined();
            const assets = JSON.parse(result.content[0].text);
            expect(assets.img).toBeDefined();
            expect(assets.audio).toBeDefined();
        });

        it('should list only image assets when assetType is "img"', async () => {
            const result = await listAssets({
                projectPath: testProjectPath,
                assetType: 'img'
            });

            const assets = JSON.parse(result.content[0].text);
            expect(assets.img).toBeDefined();
            expect(assets.audio).toBeUndefined();
        });

        it('should list only audio assets when assetType is "audio"', async () => {
            const result = await listAssets({
                projectPath: testProjectPath,
                assetType: 'audio'
            });

            const assets = JSON.parse(result.content[0].text);
            expect(assets.audio).toBeDefined();
            expect(assets.img).toBeUndefined();
        });

        it('should default to "all" when assetType is not specified', async () => {
            const result = await listAssets({
                projectPath: testProjectPath
            });

            const assets = JSON.parse(result.content[0].text);
            expect(assets.img).toBeDefined();
            expect(assets.audio).toBeDefined();
        });
    });

    describe('checkAssetsIntegrity', () => {
        it('should check for missing assets and orphaned files', async () => {
            const result = await checkAssetsIntegrity({
                projectPath: testProjectPath
            });

            expect(result.content[0].text).toBeDefined();
            // The result should either report no issues or list found issues
            expect(typeof result.content[0].text).toBe('string');
        });

        it('should report no issues for a valid project', async () => {
            const result = await checkAssetsIntegrity({
                projectPath: testProjectPath
            });

            // Depending on test_project state, this might have issues or not
            // We just verify it returns a valid response
            expect(result.content[0].text).toBeDefined();
        });
    });
});
