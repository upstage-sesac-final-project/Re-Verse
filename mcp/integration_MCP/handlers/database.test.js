import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { fileURLToPath } from 'url';
import { addActor, addItem, addSkill } from './database.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const sourceProjectPath = path.join(__dirname, '../test_project');

let tempRoot;
let testProjectPath;

async function setupTempProject() {
  tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'mz-project-'));
  testProjectPath = path.join(tempRoot, 'project');

  // Copy files individually, excluding .bak files
  await fs.mkdir(testProjectPath, { recursive: true });
  await fs.mkdir(path.join(testProjectPath, 'data'), { recursive: true });

  const sourceDataDir = path.join(sourceProjectPath, 'data');
  const targetDataDir = path.join(testProjectPath, 'data');
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
    await fs.rm(tempRoot, { recursive: true, force: true });
    tempRoot = undefined;
    testProjectPath = undefined;
  }
}

describe('database', () => {
  beforeEach(async () => {
    await setupTempProject();
  });

  afterEach(async () => {
    await cleanupTempProject();
  });

  describe('addActor', () => {
    it('should add a new actor with required parameters', async () => {
      const actorsPath = path.join(testProjectPath, 'data', 'Actors.json');
      const result = await addActor({
        projectPath: testProjectPath,
        name: '테스트 영웅'
      });

      expect(result.content[0].text).toContain('테스트 영웅');
      expect(result.content[0].text).toMatch(/ID: \d+/);

      // Verify the actor was actually added
      const actors = JSON.parse(await fs.readFile(actorsPath, 'utf-8'));
      const newActor = actors.find(a => a && a.name === '테스트 영웅');
      expect(newActor).toBeDefined();
      expect(newActor.classId).toBe(1); // default
      expect(newActor.initialLevel).toBe(1); // default
      expect(newActor.maxLevel).toBe(99); // default
    });

    it('should add actor with custom parameters', async () => {
      const actorsPath = path.join(testProjectPath, 'data', 'Actors.json');
      const result = await addActor({
        projectPath: testProjectPath,
        name: '맞춤 영웅',
        classId: 2,
        initialLevel: 5,
        maxLevel: 50
      });

      const actors = JSON.parse(await fs.readFile(actorsPath, 'utf-8'));
      const newActor = actors.find(a => a && a.name === '맞춤 영웅');
      expect(newActor.classId).toBe(2);
      expect(newActor.initialLevel).toBe(5);
      expect(newActor.maxLevel).toBe(50);
    });

    it('should throw error for invalid project path', async () => {
      await expect(addActor({
        projectPath: '/invalid/path',
        name: 'Test'
      })).rejects.toThrow();
    });
  });

  describe('addItem', () => {
    it('should add a new item with default parameters', async () => {
      const itemsPath = path.join(testProjectPath, 'data', 'Items.json');
      const result = await addItem({
        projectPath: testProjectPath,
        name: '테스트 물약'
      });

      expect(result.content[0].text).toContain('테스트 물약');

      const items = JSON.parse(await fs.readFile(itemsPath, 'utf-8'));
      const newItem = items.find(i => i && i.name === '테스트 물약');
      expect(newItem).toBeDefined();
      expect(newItem.price).toBe(0);
      expect(newItem.consumable).toBe(true);
    });

    it('should add item with custom price and consumable flag', async () => {
      const itemsPath = path.join(testProjectPath, 'data', 'Items.json');
      const result = await addItem({
        projectPath: testProjectPath,
        name: '엘릭서',
        price: 500,
        consumable: false
      });

      const items = JSON.parse(await fs.readFile(itemsPath, 'utf-8'));
      const newItem = items.find(i => i && i.name === '엘릭서');
      expect(newItem.price).toBe(500);
      expect(newItem.consumable).toBe(false);
    });
  });

  describe('addSkill', () => {
    it('should add a new skill with default parameters', async () => {
      const skillsPath = path.join(testProjectPath, 'data', 'Skills.json');
      const result = await addSkill({
        projectPath: testProjectPath,
        name: '화재'
      });

      expect(result.content[0].text).toContain('화재');

      const skills = JSON.parse(await fs.readFile(skillsPath, 'utf-8'));
      const newSkill = skills.find(s => s && s.name === '화재');
      expect(newSkill).toBeDefined();
      expect(newSkill.mpCost).toBe(0);
      expect(newSkill.tpCost).toBe(0);
    });

    it('should add skill with custom MP and TP cost', async () => {
      const skillsPath = path.join(testProjectPath, 'data', 'Skills.json');
      const result = await addSkill({
        projectPath: testProjectPath,
        name: '메가 플레어',
        mpCost: 50,
        tpCost: 30
      });

      const skills = JSON.parse(await fs.readFile(skillsPath, 'utf-8'));
      const newSkill = skills.find(s => s && s.name === '메가 플레어');
      expect(newSkill.mpCost).toBe(50);
      expect(newSkill.tpCost).toBe(30);
    });
  });
});
