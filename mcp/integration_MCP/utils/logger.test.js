import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import { Logger, LogLevel } from './logger.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const LOG_FILE_PATH = path.join(__dirname, '..', 'server.log');
const DEBUG_LOG_PATH = path.join(__dirname, '..', 'debug_log.txt');
const ERROR_LOG_PATH = path.join(__dirname, '..', 'error.log');

describe('Logger', () => {
  beforeEach(async () => {
    // Reset logger config
    Logger.configure({
      level: LogLevel.INFO,
      enableConsole: true,
      enableFile: true,
      enableDebugFile: true,
      enableErrorFile: true,
    });

    // Clean up log files before each test
    try {
      await fs.unlink(LOG_FILE_PATH);
    } catch {}
    try {
      await fs.unlink(DEBUG_LOG_PATH);
    } catch {}
    try {
      await fs.unlink(ERROR_LOG_PATH);
    } catch {}
  });

  afterEach(async () => {
    // Clean up log files after each test
    try {
      await fs.unlink(LOG_FILE_PATH);
    } catch {}
    try {
      await fs.unlink(DEBUG_LOG_PATH);
    } catch {}
    try {
      await fs.unlink(ERROR_LOG_PATH);
    } catch {}
  });

  describe('info', () => {
    it('should log info message', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      await Logger.info('Test info message');

      expect(consoleSpy).toHaveBeenCalled();
      consoleSpy.mockRestore();
    });

    it('should write info message to log file', async () => {
      await Logger.info('Test info message');

      const logContent = await fs.readFile(LOG_FILE_PATH, 'utf-8');
      expect(logContent).toContain('[INFO]');
      expect(logContent).toContain('Test info message');
    });
  });

  describe('error', () => {
    it('should log error message', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      await Logger.error('Test error', new Error('Test error message'));

      expect(consoleSpy).toHaveBeenCalled();
      consoleSpy.mockRestore();
    });

    it('should write error message to log file', async () => {
      const testError = new Error('Test error message');
      await Logger.error('Test error', testError);

      const logContent = await fs.readFile(LOG_FILE_PATH, 'utf-8');
      expect(logContent).toContain('[ERROR]');
      expect(logContent).toContain('Test error');
      expect(logContent).toContain('Test error message');
    });

    it('should handle non-Error objects', async () => {
      await Logger.error('Test error', 'String error');

      const logContent = await fs.readFile(LOG_FILE_PATH, 'utf-8');
      expect(logContent).toContain('[ERROR]');
      expect(logContent).toContain('String error');
    });
  });

  describe('warn', () => {
    it('should log warn message', async () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      await Logger.warn('Test warn message');

      expect(consoleSpy).toHaveBeenCalled();
      consoleSpy.mockRestore();
    });

    it('should write warn message to log file', async () => {
      await Logger.warn('Test warn message');

      const logContent = await fs.readFile(LOG_FILE_PATH, 'utf-8');
      expect(logContent).toContain('[WARN]');
      expect(logContent).toContain('Test warn message');
    });
  });

  describe('debug', () => {
    it('should write debug message to debug log file', async () => {
      Logger.configure({ level: LogLevel.DEBUG });
      await Logger.debug('Test debug message');

      const logContent = await fs.readFile(DEBUG_LOG_PATH, 'utf-8');
      expect(logContent).toContain('[DEBUG]');
      expect(logContent).toContain('Test debug message');
    });

    it('should not write debug message when level is above DEBUG', async () => {
      Logger.configure({ level: LogLevel.INFO });
      await Logger.debug('Test debug message');

      try {
        await fs.readFile(DEBUG_LOG_PATH, 'utf-8');
        expect.fail('Debug log file should not exist');
      } catch {
        // Expected - file should not exist
      }
    });
  });

  describe('configure', () => {
    it('should update logger configuration', () => {
      const originalConfig = Logger.getConfig();
      Logger.configure({ level: LogLevel.DEBUG });

      const newConfig = Logger.getConfig();
      expect(newConfig.level).toBe(LogLevel.DEBUG);
      expect(newConfig.enableConsole).toBe(originalConfig.enableConsole);
    });
  });

  describe('child', () => {
    it('should create a child logger with prefix', async () => {
      const childLogger = Logger.child('TEST');
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      await childLogger.info('Test message');

      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('[TEST] Test message')
      );
      consoleSpy.mockRestore();
    });
  });
});
