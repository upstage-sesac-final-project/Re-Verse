/**
 * RPG Maker MZ MCP Server Type Definitions
 */

/**
 * Event command structure
 */
export interface EventCommand {
  code: number;
  indent: number;
  parameters: unknown[];
  _description?: string;
}

/**
 * Event page structure
 */
export interface EventPage {
  conditions: {
    actorId: number;
    actorValid: boolean;
    itemId: number;
    itemValid: boolean;
    selfSwitchCh: string;
    selfSwitchValid: boolean;
    switch1Id: number;
    switch1Valid: boolean;
    switch2Id: number;
    switch2Valid: boolean;
    variableId: number;
    variableValid: boolean;
    variableValue: number;
  };
  image: {
    tileId: number;
    characterName: string;
    direction: number;
    pattern: number;
    characterIndex: number;
  };
  list: EventCommand[];
  moveFrequency: number;
  moveRoute: {
    list: unknown[];
    repeat: boolean;
    skippable: boolean;
    wait: boolean;
  };
  moveSpeed: number;
  moveType: number;
  priorityType: number;
  stepAnime: boolean;
  through: boolean;
  trigger: number;
  walkAnime: boolean;
}

/**
 * Event structure
 */
export interface Event {
  id: number;
  name: string;
  note: string;
  pages: EventPage[];
  x: number;
  y: number;
}

/**
 * Map data structure
 */
export interface MapData {
  autoplayBgm: boolean;
  autoplayBgs: boolean;
  battleback1Name: string;
  battleback2Name: string;
  bgm: {
    name: string;
    pan: number;
    pitch: number;
    volume: number;
  };
  bgs: {
    name: string;
    pan: number;
    pitch: number;
    volume: number;
  };
  disableDashing: boolean;
  displayName: string;
  encoding: string;
  events: Record<string, Event>;
  note: string;
  parallaxLoopX: boolean;
  parallaxLoopY: boolean;
  parallaxName: string;
  parallaxShow: boolean;
  parallaxSx: number;
  parallaxSy: number;
  scrollType: number;
  specifyBattleback: boolean;
  tilesetId: number;
  width: number;
  height: number;
  data: number[];
}

/**
 * Project path validation result
 */
export type ProjectPathValidationResult = {
  valid: boolean;
  error?: string;
};

/**
 * Logger interface
 */
export interface ILogger {
  info(message: string): Promise<void>;
  error(message: string, error: Error | unknown): Promise<void>;
  debug(message: string): Promise<void>;
}

/**
 * Actor structure
 */
export interface Actor {
  id: number;
  name: string;
  classId: number;
  level: number;
  characterName: string;
  characterIndex: number;
  faceName: string;
  faceIndex: number;
  traits: unknown[];
  initialLevel: number;
  maxLevel: number;
  nickname: string;
  note: string;
  profile: string;
}

/**
 * Item structure
 */
export interface Item {
  id: number;
  name: string;
  iconIndex: number;
  description: string;
  price: number;
  consumable: boolean;
  scope: number;
  occasion: number;
  speed: number;
  successRate: number;
  repeats: number;
  tpGain: number;
  hitType: number;
  animationId: number;
  damage: {
    type: number;
    elementId: number;
    formula: string;
    variance: number;
  };
  effects: unknown[];
  note: string;
}

/**
 * Skill structure
 */
export interface Skill {
  id: number;
  name: string;
  iconIndex: number;
  description: string;
  mpCost: number;
  tpCost: number;
  scope: number;
  occasion: number;
  speed: number;
  successRate: number;
  repeats: number;
  tpGain: number;
  hitType: number;
  animationId: number;
  damage: {
    type: number;
    elementId: number;
    formula: string;
    variance: number;
  };
  effects: unknown[];
  note: string;
  message1: string;
  message2: string;
  requiredWtypeId1: number;
  requiredWtypeId2: number;
  stypeId: number;
}

/**
 * Handler response type
 */
export type HandlerContent = { type: "text"; text: string };
export type HandlerResponse = { content: HandlerContent[] };
