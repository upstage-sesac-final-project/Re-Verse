import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { fileURLToPath } from 'url';
import { loadMapData, saveMapData, getEventPageList } from './mapHelpers.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const testProjectPath = path.join(__dirname, '../test_project');

describe('mapHelpers', () => {
  describe('loadMapData', () => {
    it('should load map data for valid map ID', async () => {
      const mapData = await loadMapData(testProjectPath, 1);
      expect(mapData).toBeDefined();
      expect(typeof mapData).toBe('object');
    });

    it('should pad map ID with zeros', async () => {
      const mapData = await loadMapData(testProjectPath, 1);
      expect(mapData).toBeDefined();
    });

    it('should throw error for non-existent map', async () => {
      await expect(loadMapData(testProjectPath, 99999)).rejects.toThrow();
    });
  });

  describe('saveMapData', () => {
    it('should save map data', async () => {
      const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'mz-map-'));
      const tempProject = path.join(tempRoot, 'project');

      // Copy files individually, excluding .bak files
      await fs.mkdir(tempProject, { recursive: true });
      await fs.mkdir(path.join(tempProject, 'data'), { recursive: true });

      const sourceDataDir = path.join(testProjectPath, 'data');
      const targetDataDir = path.join(tempProject, 'data');
      const files = await fs.readdir(sourceDataDir);

      for (const file of files) {
        if (!file.endsWith('.bak')) {
          await fs.copyFile(
            path.join(sourceDataDir, file),
            path.join(targetDataDir, file)
          );
        }
      }

      // Copy other directories/files if needed
      const otherItems = await fs.readdir(testProjectPath);
      for (const item of otherItems) {
        if (item !== 'data') {
          const sourcePath = path.join(testProjectPath, item);
          const targetPath = path.join(tempProject, item);
          const stat = await fs.stat(sourcePath);
          if (stat.isDirectory()) {
            await fs.cp(sourcePath, targetPath, { recursive: true });
          } else {
            await fs.copyFile(sourcePath, targetPath);
          }
        }
      }

      try {
        const originalData = await loadMapData(tempProject, 1);
        const testData = { ...originalData, testProperty: 'test' };

        await saveMapData(tempProject, 1, testData);
        const savedData = await loadMapData(tempProject, 1);

        expect(savedData.testProperty).toBe('test');
      } finally {
        await fs.rm(tempRoot, { recursive: true, force: true });
      }
    });
  });

  describe('getEventPageList', () => {
    it('should get event page list for valid event and page', async () => {
      const mapData = await loadMapData(testProjectPath, 1);
      const eventId = Object.keys(mapData.events || {}).find(id => mapData.events[id]);
      expect(eventId).toBeDefined();
      const event = mapData.events[eventId];
      expect(event.pages?.length).toBeGreaterThan(0);

      const list = getEventPageList(mapData, eventId, 0, 1);
      expect(Array.isArray(list)).toBe(true);
    });

    it('should throw error for non-existent event', () => {
      const mapData = { events: {} };
      expect(() => getEventPageList(mapData, '999', 0, 1)).toThrow();
    });

    it('should throw error for non-existent page', async () => {
      const mapData = await loadMapData(testProjectPath, 1);

      const eventId = Object.keys(mapData.events || {}).find(id => mapData.events[id]);
      expect(eventId).toBeDefined();
      expect(() => getEventPageList(mapData, eventId, 999, 1)).toThrow();
    });
  });
});
