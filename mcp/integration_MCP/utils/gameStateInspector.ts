/**
 * Whitelist of allowed property access patterns for game state inspection
 * Only these patterns are allowed to prevent arbitrary code execution
 */
export const ALLOWED_ACCESS_PATTERNS = [
    /^\$gameVariables\.value\(\d+\)$/,
    /^\$gameSwitches\.value\(\d+\)$/,
    /^\$gameActors\.actor\(\d+\)$/,
    /^\$gameParty\.members\(\)$/,
    /^\$gameParty\.gold\(\)$/,
    /^\$gameParty\.items\(\)$/,
    /^\$gameParty\.weapons\(\)$/,
    /^\$gameParty\.armors\(\)$/,
    /^\$gameMap\.mapId\(\)$/,
    /^\$gamePlayer\.x\(\)$/,
    /^\$gamePlayer\.y\(\)$/,
    /^\$gamePlayer\.screenX\(\)$/,
    /^\$gamePlayer\.screenY\(\)$/,
    /^SceneManager\._scene$/,
    /^SceneManager\._scene\.constructor\.name$/,
    /^DataManager\._globalId$/,
    /^Graphics\.width$/,
    /^Graphics\.height$/,
] as const;

/**
 * Validates if a script matches allowed access patterns
 */
export function isScriptAllowed(script: string): boolean {
    const trimmed = script.trim();
    return ALLOWED_ACCESS_PATTERNS.some(pattern => pattern.test(trimmed));
}

/**
 * Validates script input for security
 */
export function validateScriptInput(script: string): void {
    // Security: Input length limit (ReDoS対策)
    const MAX_SCRIPT_LENGTH = 100;
    if (script.length > MAX_SCRIPT_LENGTH) {
        throw new Error(`Script too long (max ${MAX_SCRIPT_LENGTH} chars)`);
    }

    // Security: Validate script against whitelist before execution
    if (!isScriptAllowed(script)) {
        throw new Error(`Script not allowed: ${script}. Only whitelisted RPG Maker MZ game state access patterns are permitted.`);
    }

    // Security: ID range validation (1-9999)
    const idMatch = script.match(/\((\d+)\)/);
    if (idMatch) {
        const id = parseInt(idMatch[1], 10);
        if (isNaN(id) || id < 1 || id > 9999) {
            throw new Error(`ID out of allowed range (1-9999): ${id}`);
        }
    }
}
