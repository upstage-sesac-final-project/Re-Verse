import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import { validateProjectPath, getFilesRecursively, sleep } from './validation.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const testProjectPath = path.join(__dirname, '../test_project');

describe('validation', () => {
  describe('validateProjectPath', () => {
    it('should validate a valid project path', async () => {
      await expect(validateProjectPath(testProjectPath)).resolves.not.toThrow();
    });

    it('should throw error for non-existent path', async () => {
      const invalidPath = path.join(__dirname, '../non-existent');
      await expect(validateProjectPath(invalidPath)).rejects.toThrow();
    });

    it('should throw error for path that is not a directory', async () => {
      const filePath = path.join(testProjectPath, 'game.rmmzproject');
      await expect(validateProjectPath(filePath)).rejects.toThrow('not a directory');
    });

    it('should throw error for directory without game.rmmzproject', async () => {
      const tempDir = path.join(__dirname, '../temp_test_dir');
      try {
        await fs.mkdir(tempDir, { recursive: true });
        await expect(validateProjectPath(tempDir)).rejects.toThrow('game.rmmzproject not found');
      } finally {
        await fs.rmdir(tempDir).catch(() => {});
      }
    });
  });

  describe('getFilesRecursively', () => {
    it('should get all files recursively', async () => {
      const files = await getFilesRecursively(testProjectPath);
      expect(Array.isArray(files)).toBe(true);
      expect(files.length).toBeGreaterThan(0);
      expect(files.some(f => f.includes('game.rmmzproject'))).toBe(true);
    });

    it('should return empty array for empty directory', async () => {
      const tempDir = path.join(__dirname, '../temp_empty_dir');
      try {
        await fs.mkdir(tempDir, { recursive: true });
        const files = await getFilesRecursively(tempDir);
        expect(files).toEqual([]);
      } finally {
        await fs.rmdir(tempDir).catch(() => {});
      }
    });
  });

  describe('sleep', () => {
    it('should wait for specified milliseconds', async () => {
      const start = Date.now();
      await sleep(100);
      const elapsed = Date.now() - start;
      expect(elapsed).toBeGreaterThanOrEqual(90); // Allow some margin
      expect(elapsed).toBeLessThan(200);
    });
  });
});
