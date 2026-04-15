import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import { createBackup, withBackup, cleanupOldBackups } from './backup.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const testDir = path.join(__dirname, '../test_temp');

describe('backup', () => {
    beforeEach(async () => {
        await fs.mkdir(testDir, { recursive: true });
    });

    afterEach(async () => {
        // Cleanup test files
        try {
            const files = await fs.readdir(testDir);
            for (const file of files) {
                await fs.unlink(path.join(testDir, file)).catch(() => {
                    // Ignore cleanup errors
                });
            }
            await fs.rmdir(testDir).catch(() => {
                // Ignore cleanup errors
            });
        } catch {
            // Ignore cleanup errors
        }
    });

    describe('createBackup', () => {
        it('should create a backup file', async () => {
            const filePath = path.join(testDir, 'test.json');
            const content = JSON.stringify({ test: 'data' });
            await fs.writeFile(filePath, content, 'utf-8');

            const backupPath = await createBackup(filePath);

            expect(backupPath).toContain('.bak');
            expect(backupPath).toContain('test.json');

            const backupContent = await fs.readFile(backupPath, 'utf-8');
            expect(backupContent).toBe(content);
        });

        it('should return null if file does not exist', async () => {
            const filePath = path.join(testDir, 'nonexistent.json');

            await expect(createBackup(filePath)).resolves.toBeNull();
        });
    });

    describe('withBackup', () => {
        it('should execute operation and keep backup', async () => {
            const filePath = path.join(testDir, 'test.json');
            const originalContent = JSON.stringify({ id: 1 });
            const newContent = JSON.stringify({ id: 2 });

            await fs.writeFile(filePath, originalContent, 'utf-8');

            await withBackup(filePath, async () => {
                await fs.writeFile(filePath, newContent, 'utf-8');
            });

            // File should have new content
            const currentContent = await fs.readFile(filePath, 'utf-8');
            expect(currentContent).toBe(newContent);

            // Backup should exist
            const files = await fs.readdir(testDir);
            const backupFiles = files.filter(f => f.endsWith('.bak'));
            expect(backupFiles.length).toBeGreaterThan(0);
        });

        it('should rollback on error', async () => {
            const filePath = path.join(testDir, 'test.json');
            const originalContent = JSON.stringify({ id: 1 });
            const newContent = JSON.stringify({ id: 2 });

            await fs.writeFile(filePath, originalContent, 'utf-8');

            await expect(
                withBackup(filePath, async () => {
                    await fs.writeFile(filePath, newContent, 'utf-8');
                    throw new Error('Operation failed');
                })
            ).rejects.toThrow('Operation failed');

            // File should be rolled back to original content
            const rolledBackContent = await fs.readFile(filePath, 'utf-8');
            expect(rolledBackContent).toBe(originalContent);
        });
    });

    describe('cleanupOldBackups', () => {
        it('should keep only specified number of backups', async () => {
            const filePath = path.join(testDir, 'test.json');
            await fs.writeFile(filePath, '{}', 'utf-8');

            // Create 10 backups
            for (let i = 0; i < 10; i++) {
                const backupPath = `${filePath}.${Date.now() + i}.bak`;
                await fs.copyFile(filePath, backupPath);
                await new Promise(resolve => setTimeout(resolve, 10));
            }

            await cleanupOldBackups(filePath, 5);

            const files = await fs.readdir(testDir);
            const backupFiles = files.filter(f => f.endsWith('.bak'));
            expect(backupFiles.length).toBeLessThanOrEqual(5);
        });

        it('should handle non-existent file gracefully', async () => {
            const filePath = path.join(testDir, 'nonexistent.json');

            // Should not throw
            await expect(cleanupOldBackups(filePath, 5)).resolves.not.toThrow();
        });
    });
});
