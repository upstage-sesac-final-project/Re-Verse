import { describe, it, expect } from 'vitest';
import { DEFAULTS, PATHS, EVENT_CODES } from './constants.js';

describe('constants', () => {
  describe('DEFAULTS', () => {
    it('should have all required default values', () => {
      expect(DEFAULTS.PORT).toBeDefined();
      expect(DEFAULTS.TIMEOUT).toBeDefined();
      expect(DEFAULTS.MAX_WAIT_TIME).toBeDefined();
      expect(DEFAULTS.AUTO_CLOSE).toBeDefined();
      expect(DEFAULTS.START_NEW_GAME).toBeDefined();
      expect(DEFAULTS.TILESET_ID).toBeDefined();
      expect(DEFAULTS.MAP_WIDTH).toBeDefined();
      expect(DEFAULTS.MAP_HEIGHT).toBeDefined();
      expect(DEFAULTS.ASSET_TYPE).toBeDefined();
    });

    it('should have correct default port', () => {
      expect(DEFAULTS.PORT).toBe(9222);
    });
  });

  describe('PATHS', () => {
    it('should have all required path constants', () => {
      expect(PATHS.DATA_DIR).toBeDefined();
      expect(PATHS.IMG_DIR).toBeDefined();
      expect(PATHS.AUDIO_DIR).toBeDefined();
      expect(PATHS.PLUGINS_DIR).toBeDefined();
      expect(PATHS.SYSTEM_FILE).toBeDefined();
      expect(PATHS.MAP_INFOS).toBeDefined();
      expect(PATHS.PLUGINS_FILE).toBeDefined();
    });
  });

  describe('EVENT_CODES', () => {
    it('should have all required event codes', () => {
      expect(EVENT_CODES.SHOW_TEXT).toBe(101);
      expect(EVENT_CODES.SHOW_CHOICES).toBe(102);
      expect(EVENT_CODES.CONDITIONAL_BRANCH).toBe(111);
      expect(EVENT_CODES.LOOP).toBe(112);
      expect(EVENT_CODES.BREAK_LOOP).toBe(113);
      expect(EVENT_CODES.CONTROL_SWITCHES).toBe(121);
      expect(EVENT_CODES.CONTROL_VARIABLES).toBe(122);
      expect(EVENT_CODES.TRANSFER_PLAYER).toBe(201);
      expect(EVENT_CODES.SHOW_PICTURE).toBe(231);
      expect(EVENT_CODES.TEXT_DATA).toBe(401);
      expect(EVENT_CODES.CHOICE_WHEN).toBe(402);
      expect(EVENT_CODES.CHOICE_CANCEL).toBe(403);
      expect(EVENT_CODES.CONDITIONAL_ELSE).toBe(411);
      expect(EVENT_CODES.CONDITIONAL_END).toBe(412);
      expect(EVENT_CODES.LOOP_REPEAT).toBe(413);
    });

    it('should have unique values for all event codes', () => {
      const values = Object.values(EVENT_CODES);
      const uniqueValues = new Set(values);
      expect(values.length).toBe(uniqueValues.size);
    });
  });
});
