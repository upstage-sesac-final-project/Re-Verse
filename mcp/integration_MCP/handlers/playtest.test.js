import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock puppeteer
vi.mock('puppeteer', () => {
  return {
    default: {
      connect: vi.fn()
    }
  };
});

// Mock utils
vi.mock('../utils/logger.js', () => ({
  Logger: {
    warn: vi.fn().mockResolvedValue(),
    info: vi.fn().mockResolvedValue(),
    debug: vi.fn().mockResolvedValue(),
    error: vi.fn().mockResolvedValue()
  }
}));

vi.mock('../utils/constants.js', () => ({
  DEFAULTS: {
    PORT: 9222
  }
}));

import puppeteer from 'puppeteer';
import { Logger } from '../utils/logger.js';
import { inspectGameState } from './playtest.js';

describe('playtest', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('inspectGameState', () => {
    const createMockBrowser = (pages) => ({
      pages: vi.fn().mockResolvedValue(pages),
      disconnect: vi.fn().mockResolvedValue()
    });

    it('evaluates script on the first page and returns result', async () => {
      const mockEvaluate = vi.fn().mockResolvedValue({ switches: [1, 2, 3] });
      const mockPage = { evaluate: mockEvaluate };
      const mockBrowser = createMockBrowser([mockPage]);
      puppeteer.connect.mockResolvedValue(mockBrowser);

      const result = await inspectGameState({
        port: 9333,
        script: 'return $gameSwitches.value(1);'
      });

      expect(Logger.warn).toHaveBeenCalledWith(
        expect.stringContaining('Executing arbitrary code via inspect_game_state')
      );
      expect(puppeteer.connect).toHaveBeenCalledWith({
        browserURL: 'http://127.0.0.1:9333',
        defaultViewport: null
      });
      expect(mockEvaluate).toHaveBeenCalledWith(expect.any(Function), 'return $gameSwitches.value(1);');
      expect(result.content[0].text).toContain('switches');
    });

    it('throws when no pages are available', async () => {
      const mockBrowser = createMockBrowser([]);
      puppeteer.connect.mockResolvedValue(mockBrowser);

      await expect(
        inspectGameState({ port: 9222, script: 'return 1;' })
      ).rejects.toThrow('No pages found in browser');
    });

    it('handles connection errors gracefully', async () => {
      puppeteer.connect.mockRejectedValue(new Error('Connection failed'));

      await expect(
        inspectGameState({ port: 9222, script: 'return 1;' })
      ).rejects.toThrow('Failed to inspect game state');
    });
  });

  // Note: runPlaytest tests are complex due to dynamic imports and process spawning
  // These are covered by E2E tests in automation/ directory
});
