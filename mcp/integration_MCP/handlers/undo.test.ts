import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { fileURLToPath } from 'url';
import { undoLastChange, listBackups } from './undo.js';
import { Errors } from '../utils/errors.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const sourceProjectPath = path.join(__dirname, '../test_project');

let tempRoot: string | undefined;
let testProjectPath: string | undefined;

async function setupTempProject() {
    tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'mz-undo-'));
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

describe('undo', () => {
    beforeEach(async () => {
        await setupTempProject();
    });

    afterEach(async () => {
        await cleanupTempProject();
    });

    describe('undoLastChange', () => {
        it('should restore file from latest backup', async () => {
            if (!testProjectPath) throw new Error('testProjectPath not set');
            const filename = 'TestActors.json';
            const filePath = path.join(testProjectPath, 'data', filename);
            const originalContent = JSON.stringify([{ id: 1, name: 'Original' }], null, 2);
            const modifiedContent = JSON.stringify([{ id: 1, name: 'Modified' }], null, 2);

            // Create original file
            await fs.writeFile(filePath, originalContent, 'utf-8');

            // Create backup
            const timestamp = Date.now();
            const backupPath = `${filePath}.${timestamp}.bak`;
            await fs.copyFile(filePath, backupPath);

            // Modify file
            await fs.writeFile(filePath, modifiedContent, 'utf-8');

            // Restore from backup
            const result = await undoLastChange({
                projectPath: testProjectPath,
                filename: filename
            });

            expect(result.content[0].text).toContain('Successfully restored');

            // Verify file was restored
            const restoredContent = await fs.readFile(filePath, 'utf-8');
            expect(restoredContent).toBe(originalContent);
        });

        it('should throw error if no backup found', async () => {
            if (!testProjectPath) throw new Error('testProjectPath not set');
            const filename = 'NonExistent.json';
            const filePath = path.join(testProjectPath, 'data', filename);

            // Create file without backup
            await fs.writeFile(filePath, '{}', 'utf-8');

            await expect(
                undoLastChange({
                    projectPath: testProjectPath,
                    filename: filename
                })
            ).rejects.toThrow('No backup found');
        });

        it('should restore most recently modified file if filename not specified', async () => {
            if (!testProjectPath) throw new Error('testProjectPath not set');
            const file1 = path.join(testProjectPath, 'data', 'File1.json');
            const file2 = path.join(testProjectPath, 'data', 'File2.json');

            // Create files
            await fs.writeFile(file1, JSON.stringify([{ id: 1 }]), 'utf-8');
            await fs.writeFile(file2, JSON.stringify([{ id: 2 }]), 'utf-8');

            // Wait a bit and modify file2 (to make it more recent)
            await new Promise(resolve => setTimeout(resolve, 100));
            await fs.writeFile(file2, JSON.stringify([{ id: 2, modified: true }]), 'utf-8');

            // Create backup for file2
            const timestamp = Date.now();
            const backupPath = `${file2}.${timestamp}.bak`;
            await fs.copyFile(file2, backupPath);

            // Modify file2 again
            await fs.writeFile(file2, JSON.stringify([{ id: 2, modified: false }]), 'utf-8');

            // Restore without specifying filename
            const result = await undoLastChange({
                projectPath: testProjectPath
            });

            expect(result.content[0].text).toContain('Successfully restored');

            // Verify file2 was restored (most recent)
            const restoredContent = await fs.readFile(file2, 'utf-8');
            expect(restoredContent).toContain('"modified":true');
        });

        it('should throw error for invalid filename', async () => {
            if (!testProjectPath) throw new Error('testProjectPath not set');
            await expect(
                undoLastChange({
                    projectPath: testProjectPath,
                    filename: '../../../etc/passwd'
                })
            ).rejects.toThrow();
        });
    });

    describe('listBackups', () => {
        it('should list all backups for a file', async () => {
            if (!testProjectPath) throw new Error('testProjectPath not set');
            const filename = 'TestFile.json';
            const filePath = path.join(testProjectPath, 'data', filename);

            // Create file and multiple backups
            await fs.writeFile(filePath, '{}', 'utf-8');

            const timestamp1 = Date.now();
            const backup1 = `${filePath}.${timestamp1}.bak`;
            await fs.copyFile(filePath, backup1);
            await new Promise(resolve => setTimeout(resolve, 100));

            const timestamp2 = Date.now();
            const backup2 = `${filePath}.${timestamp2}.bak`;
            await fs.copyFile(filePath, backup2);

            const result = await listBackups({
                projectPath: testProjectPath,
                filename: filename
            });

            const backups = JSON.parse(result.content[0].text);
            expect(backups).toHaveLength(1);
            expect(backups[0].file).toBe(filename);
            expect(backups[0].backups.length).toBeGreaterThanOrEqual(2);
        });

        it('should list backups for all files if filename not specified', async () => {
            if (!testProjectPath) throw new Error('testProjectPath not set');
            const file1 = path.join(testProjectPath, 'data', 'File1.json');
            const file2 = path.join(testProjectPath, 'data', 'File2.json');

            await fs.writeFile(file1, '{}', 'utf-8');
            await fs.writeFile(file2, '{}', 'utf-8');

            const backup1 = `${file1}.${Date.now()}.bak`;
            await fs.copyFile(file1, backup1);
            const backup2 = `${file2}.${Date.now()}.bak`;
            await fs.copyFile(file2, backup2);

            const result = await listBackups({
                projectPath: testProjectPath
            });

            const backups = JSON.parse(result.content[0].text);
            expect(backups.length).toBeGreaterThanOrEqual(2);
        });

        it('should return empty array if no backups found', async () => {
            if (!testProjectPath) throw new Error('testProjectPath not set');
            const filename = 'NoBackupFile.json';
            const filePath = path.join(testProjectPath, 'data', filename);
            await fs.writeFile(filePath, '{}', 'utf-8');

            const result = await listBackups({
                projectPath: testProjectPath,
                filename: filename
            });

            const backups = JSON.parse(result.content[0].text);
            expect(backups).toHaveLength(1);
            expect(backups[0].backups).toHaveLength(0);
        });
    });
});
