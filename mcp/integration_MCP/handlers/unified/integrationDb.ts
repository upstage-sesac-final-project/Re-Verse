import { validateProjectPath } from "../../utils/validation.js";
import { HandlerResponse, Actor, Item, Skill } from "../../types/index.js";
import { readDataJson, writeDataJson } from "./jsonFile.js";

type ProjectArgs = { projectPath: string };

function jsonText(data: unknown): HandlerResponse {
    return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
}

async function readArray<T>(projectPath: string, filename: string): Promise<T[]> {
    try {
        return await readDataJson<T[]>(projectPath, filename);
    } catch {
        return [null] as unknown as T[];
    }
}

function nextId<T extends { id?: number } | null>(rows: T[]): number {
    return rows.reduce((max, row) => (row && row.id != null && row.id > max ? row.id : max), 0) + 1;
}

// --- Actors ---
export async function list_actors(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const actors = await readArray<Actor | null>(args.projectPath, "Actors.json");
    const summary = actors
        .map((a, i) => (a ? { index: i, id: a.id, name: a.name } : null))
        .filter(Boolean);
    return jsonText(summary);
}

export async function get_actor(args: ProjectArgs & { actorId: number }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const actors = await readArray<Actor | null>(args.projectPath, "Actors.json");
    const a = actors.find((x) => x && x.id === args.actorId) ?? null;
    return jsonText(a);
}

export async function update_actor(args: ProjectArgs & { actorId: number; updates: Record<string, unknown> }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const actors = await readArray<Actor | null>(args.projectPath, "Actors.json");
    const idx = actors.findIndex((x) => x && x.id === args.actorId);
    if (idx === -1) throw new Error(`Actor ${args.actorId} not found`);
    actors[idx] = { ...(actors[idx] as Actor), ...(args.updates as Partial<Actor>) } as Actor;
    await writeDataJson(args.projectPath, "Actors.json", actors);
    return jsonText(actors[idx]);
}

export async function search_actors(args: ProjectArgs & { searchTerm: string }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const q = args.searchTerm.toLowerCase();
    const actors = await readArray<Actor | null>(args.projectPath, "Actors.json");
    const out = actors.filter(
        (a) =>
            a &&
            (a.name.toLowerCase().includes(q) || (a.nickname && a.nickname.toLowerCase().includes(q)))
    );
    return jsonText(out);
}

// --- Items ---
export async function list_items(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const items = await readArray<Item | null>(args.projectPath, "Items.json");
    const summary = items
        .map((it, i) => (it ? { index: i, id: it.id, name: it.name } : null))
        .filter(Boolean);
    return jsonText(summary);
}

export async function update_item(args: ProjectArgs & { itemId: number; updates: Record<string, unknown> }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const items = await readArray<Item | null>(args.projectPath, "Items.json");
    const idx = items.findIndex((x) => x && x.id === args.itemId);
    if (idx === -1) throw new Error(`Item ${args.itemId} not found`);
    items[idx] = { ...(items[idx] as Item), ...(args.updates as Partial<Item>) } as Item;
    await writeDataJson(args.projectPath, "Items.json", items);
    return jsonText(items[idx]);
}

export async function search_items(args: ProjectArgs & { searchTerm: string }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const q = args.searchTerm.toLowerCase();
    const items = await readArray<Item | null>(args.projectPath, "Items.json");
    const out = items.filter(
        (it) => it && (it.name.toLowerCase().includes(q) || it.description.toLowerCase().includes(q))
    );
    return jsonText(out);
}

// --- Skills ---
export async function list_skills(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const skills = await readArray<Skill | null>(args.projectPath, "Skills.json");
    const summary = skills
        .map((s, i) => (s ? { index: i, id: s.id, name: s.name } : null))
        .filter(Boolean);
    return jsonText(summary);
}

export async function get_skill(args: ProjectArgs & { skillId: number }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const skills = await readArray<Skill | null>(args.projectPath, "Skills.json");
    const s = skills.find((x) => x && x.id === args.skillId) ?? null;
    return jsonText(s);
}

export async function update_skill(args: ProjectArgs & { skillId: number; updates: Record<string, unknown> }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const skills = await readArray<Skill | null>(args.projectPath, "Skills.json");
    const idx = skills.findIndex((x) => x && x.id === args.skillId);
    if (idx === -1) throw new Error(`Skill ${args.skillId} not found`);
    skills[idx] = { ...(skills[idx] as Skill), ...(args.updates as Partial<Skill>) } as Skill;
    await writeDataJson(args.projectPath, "Skills.json", skills);
    return jsonText(skills[idx]);
}

export async function search_skills(args: ProjectArgs & { searchTerm: string }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const q = args.searchTerm.toLowerCase();
    const skills = await readArray<Skill | null>(args.projectPath, "Skills.json");
    const out = skills.filter(
        (s) => s && (s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q))
    );
    return jsonText(out);
}

async function pushSkill(projectPath: string, skill: Skill): Promise<Skill> {
    const skills = await readArray<Skill | null>(projectPath, "Skills.json");
    skills.push(skill);
    await writeDataJson(projectPath, "Skills.json", skills);
    return skill;
}

function baseSkill(id: number, name: string): Skill {
    return {
        id,
        name,
        iconIndex: 64,
        description: "",
        mpCost: 0,
        tpCost: 0,
        scope: 1,
        occasion: 1,
        speed: 0,
        successRate: 100,
        repeats: 1,
        tpGain: 0,
        hitType: 1,
        animationId: 0,
        damage: { type: 0, elementId: 0, formula: "0", variance: 20 },
        effects: [],
        note: "",
        message1: "",
        message2: "",
        requiredWtypeId1: 0,
        requiredWtypeId2: 0,
        stypeId: 1,
    };
}

export async function create_damage_skill(
    args: ProjectArgs & {
        name: string;
        damageFormula: string;
        mpCost?: number;
        scope?: number;
        elementId?: number;
        description?: string;
    }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const skills = await readArray<Skill | null>(args.projectPath, "Skills.json");
    const id = nextId(skills);
    const s = baseSkill(id, args.name);
    s.mpCost = args.mpCost ?? 0;
    s.scope = args.scope ?? 1;
    s.description = args.description ?? "";
    s.hitType = 1;
    s.damage = {
        type: 1,
        elementId: args.elementId ?? 0,
        formula: args.damageFormula,
        variance: 20,
    };
    s.animationId = 1;
    return jsonText(await pushSkill(args.projectPath, s));
}

export async function create_healing_skill(
    args: ProjectArgs & {
        name: string;
        healFormula: string;
        mpCost?: number;
        scope?: number;
        description?: string;
    }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const skills = await readArray<Skill | null>(args.projectPath, "Skills.json");
    const id = nextId(skills);
    const s = baseSkill(id, args.name);
    s.mpCost = args.mpCost ?? 0;
    s.scope = args.scope ?? 1;
    s.description = args.description ?? "";
    s.hitType = 0;
    s.damage = {
        type: 3,
        elementId: 0,
        formula: args.healFormula,
        variance: 20,
    };
    s.animationId = 47;
    s.iconIndex = 72;
    return jsonText(await pushSkill(args.projectPath, s));
}

export async function create_buff_skill(
    args: ProjectArgs & {
        name: string;
        buffType: number;
        turns: number;
        mpCost?: number;
        scope?: number;
        description?: string;
    }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const skills = await readArray<Skill | null>(args.projectPath, "Skills.json");
    const id = nextId(skills);
    const s = baseSkill(id, args.name);
    s.mpCost = args.mpCost ?? 0;
    s.scope = args.scope ?? 1;
    s.description = args.description ?? "";
    s.effects = [{ code: 31, dataId: args.buffType, value1: args.turns, value2: 0 }];
    s.animationId = 52;
    s.iconIndex = 73;
    return jsonText(await pushSkill(args.projectPath, s));
}

export async function create_state_skill(
    args: ProjectArgs & {
        name: string;
        stateId: number;
        chance: number;
        mpCost?: number;
        scope?: number;
        description?: string;
    }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const skills = await readArray<Skill | null>(args.projectPath, "Skills.json");
    const id = nextId(skills);
    const s = baseSkill(id, args.name);
    s.mpCost = args.mpCost ?? 0;
    s.scope = args.scope ?? 1;
    s.description = args.description ?? "";
    s.effects = [{ code: 21, dataId: args.stateId, value1: args.chance, value2: 0 }];
    s.damage = { type: 0, elementId: 0, formula: "0", variance: 20 };
    s.animationId = 1;
    return jsonText(await pushSkill(args.projectPath, s));
}

// --- Weapons / Armors ---
type JsonRow = Record<string, unknown> | null;

export async function list_weapons(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const rows = await readArray<JsonRow>(args.projectPath, "Weapons.json");
    return jsonText(rows.map((r, i) => (r && typeof r === "object" && "id" in r ? { index: i, id: r.id, name: r.name } : null)).filter(Boolean));
}

export async function list_armors(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const rows = await readArray<JsonRow>(args.projectPath, "Armors.json");
    return jsonText(rows.map((r, i) => (r && typeof r === "object" && "id" in r ? { index: i, id: r.id, name: r.name } : null)).filter(Boolean));
}

function defaultWeaponRow(id: number, name: string): Record<string, unknown> {
    return {
        id,
        name,
        description: "",
        iconIndex: 0,
        wtypeId: 0,
        price: 0,
        params: [0, 0, 0, 0, 0, 0, 0, 0],
        traits: [],
        etypeId: 1,
        animationId: 0,
        note: "",
    };
}

function defaultArmorRow(id: number, name: string): Record<string, unknown> {
    return {
        id,
        name,
        description: "",
        iconIndex: 0,
        atypeId: 0,
        price: 0,
        params: [0, 0, 0, 0, 0, 0, 0, 0],
        traits: [],
        etypeId: 1,
        note: "",
    };
}

export async function create_weapon(args: ProjectArgs & { name: string; updates?: Record<string, unknown> }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const rows = await readArray<JsonRow>(args.projectPath, "Weapons.json");
    const id = nextId(rows as { id?: number }[]);
    const row = { ...defaultWeaponRow(id, args.name), ...(args.updates ?? {}) };
    rows.push(row);
    await writeDataJson(args.projectPath, "Weapons.json", rows);
    return jsonText(row);
}

export async function update_weapon(args: ProjectArgs & { weaponId: number; updates: Record<string, unknown> }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const rows = await readArray<JsonRow>(args.projectPath, "Weapons.json");
    const idx = rows.findIndex((x) => x && (x as { id?: number }).id === args.weaponId);
    if (idx === -1) throw new Error(`Weapon ${args.weaponId} not found`);
    rows[idx] = { ...(rows[idx] as Record<string, unknown>), ...args.updates };
    await writeDataJson(args.projectPath, "Weapons.json", rows);
    return jsonText(rows[idx]);
}

export async function create_armor(args: ProjectArgs & { name: string; updates?: Record<string, unknown> }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const rows = await readArray<JsonRow>(args.projectPath, "Armors.json");
    const id = nextId(rows as { id?: number }[]);
    const row = { ...defaultArmorRow(id, args.name), ...(args.updates ?? {}) };
    rows.push(row);
    await writeDataJson(args.projectPath, "Armors.json", rows);
    return jsonText(row);
}

export async function update_armor(args: ProjectArgs & { armorId: number; updates: Record<string, unknown> }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const rows = await readArray<JsonRow>(args.projectPath, "Armors.json");
    const idx = rows.findIndex((x) => x && (x as { id?: number }).id === args.armorId);
    if (idx === -1) throw new Error(`Armor ${args.armorId} not found`);
    rows[idx] = { ...(rows[idx] as Record<string, unknown>), ...args.updates };
    await writeDataJson(args.projectPath, "Armors.json", rows);
    return jsonText(rows[idx]);
}

// --- Classes / States / Enemies ---
function cloneOrDefault(
    rows: JsonRow[],
    id: number,
    name: string,
    fallback: Record<string, unknown>
): Record<string, unknown> {
    const src = rows.find((r) => r && (r as { id?: number }).id != null && (r as { id?: number }).id! > 0) as Record<string, unknown> | undefined;
    const base = src ? (JSON.parse(JSON.stringify(src)) as Record<string, unknown>) : { ...fallback };
    base.id = id;
    base.name = name;
    return base;
}

const defaultClass: Record<string, unknown> = {
    id: 1,
    expParams: [30, 20, 30, 30, 30, 30, 30, 30],
    traits: [],
    learnings: [],
    name: "",
    note: "",
};

const defaultState: Record<string, unknown> = {
    id: 1,
    autoRemovalTiming: 0,
    chanceByDamage: 100,
    iconIndex: 0,
    maxTurns: 1,
    message1: "",
    message2: "",
    message3: "",
    message4: "",
    minTurns: 1,
    motion: 0,
    name: "",
    note: "",
    overlay: 0,
    priority: 50,
    releaseByDamage: false,
    removeAtBattleEnd: false,
    removeByDamage: false,
    removeByRestriction: false,
    removeByWalking: false,
    restriction: 0,
    stepsToRemove: 100,
    traits: [],
};

const defaultEnemy: Record<string, unknown> = {
    id: 1,
    name: "",
    battlerName: "",
    battlerHue: 0,
    params: [100, 0, 10, 10, 10, 10, 10, 10],
    exp: 0,
    gold: 0,
    dropItems: [],
    actions: [{ skillId: 1, conditionType: 0, conditionParam1: 0, conditionParam2: 0, rating: 5 }],
    traits: [],
    note: "",
};

export async function list_classes(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const rows = await readArray<JsonRow>(args.projectPath, "Classes.json");
    return jsonText(rows.map((r, i) => (r && typeof r === "object" && "id" in r ? { index: i, id: r.id, name: r.name } : null)).filter(Boolean));
}

export async function create_class(args: ProjectArgs & { name: string; updates?: Record<string, unknown> }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const rows = await readArray<JsonRow>(args.projectPath, "Classes.json");
    const id = nextId(rows as { id?: number }[]);
    const row = { ...cloneOrDefault(rows, id, args.name, defaultClass), ...(args.updates ?? {}) };
    rows.push(row);
    await writeDataJson(args.projectPath, "Classes.json", rows);
    return jsonText(row);
}

export async function update_class(args: ProjectArgs & { classId: number; updates: Record<string, unknown> }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const rows = await readArray<JsonRow>(args.projectPath, "Classes.json");
    const idx = rows.findIndex((x) => x && (x as { id?: number }).id === args.classId);
    if (idx === -1) throw new Error(`Class ${args.classId} not found`);
    rows[idx] = { ...(rows[idx] as Record<string, unknown>), ...args.updates };
    await writeDataJson(args.projectPath, "Classes.json", rows);
    return jsonText(rows[idx]);
}

export async function list_states(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const rows = await readArray<JsonRow>(args.projectPath, "States.json");
    return jsonText(rows.map((r, i) => (r && typeof r === "object" && "id" in r ? { index: i, id: r.id, name: r.name } : null)).filter(Boolean));
}

export async function create_state(args: ProjectArgs & { name: string; updates?: Record<string, unknown> }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const rows = await readArray<JsonRow>(args.projectPath, "States.json");
    const id = nextId(rows as { id?: number }[]);
    const row = { ...cloneOrDefault(rows, id, args.name, defaultState), ...(args.updates ?? {}) };
    rows.push(row);
    await writeDataJson(args.projectPath, "States.json", rows);
    return jsonText(row);
}

export async function update_state(args: ProjectArgs & { stateId: number; updates: Record<string, unknown> }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const rows = await readArray<JsonRow>(args.projectPath, "States.json");
    const idx = rows.findIndex((x) => x && (x as { id?: number }).id === args.stateId);
    if (idx === -1) throw new Error(`State ${args.stateId} not found`);
    rows[idx] = { ...(rows[idx] as Record<string, unknown>), ...args.updates };
    await writeDataJson(args.projectPath, "States.json", rows);
    return jsonText(rows[idx]);
}

export async function list_enemies(args: ProjectArgs): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const rows = await readArray<JsonRow>(args.projectPath, "Enemies.json");
    return jsonText(rows.map((r, i) => (r && typeof r === "object" && "id" in r ? { index: i, id: r.id, name: r.name } : null)).filter(Boolean));
}

export async function create_enemy(args: ProjectArgs & { name: string; updates?: Record<string, unknown> }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const rows = await readArray<JsonRow>(args.projectPath, "Enemies.json");
    const id = nextId(rows as { id?: number }[]);
    const row = { ...cloneOrDefault(rows, id, args.name, defaultEnemy), ...(args.updates ?? {}) };
    rows.push(row);
    await writeDataJson(args.projectPath, "Enemies.json", rows);
    return jsonText(row);
}

export async function update_enemy(args: ProjectArgs & { enemyId: number; updates: Record<string, unknown> }): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const rows = await readArray<JsonRow>(args.projectPath, "Enemies.json");
    const idx = rows.findIndex((x) => x && (x as { id?: number }).id === args.enemyId);
    if (idx === -1) throw new Error(`Enemy ${args.enemyId} not found`);
    rows[idx] = { ...(rows[idx] as Record<string, unknown>), ...args.updates };
    await writeDataJson(args.projectPath, "Enemies.json", rows);
    return jsonText(rows[idx]);
}

const DB_FILES: Record<string, string> = {
    actors: "Actors.json",
    classes: "Classes.json",
    items: "Items.json",
    skills: "Skills.json",
    weapons: "Weapons.json",
    armors: "Armors.json",
    enemies: "Enemies.json",
    states: "States.json",
    animations: "Animations.json",
    tilesets: "Tilesets.json",
    troops: "Troops.json",
    commonEvents: "CommonEvents.json",
};

export async function update_database(
    args: ProjectArgs & { database: string; id: number; updates: Record<string, unknown> }
): Promise<HandlerResponse> {
    await validateProjectPath(args.projectPath);
    const key = args.database.trim().toLowerCase();
    const filename = DB_FILES[key] ?? (args.database.endsWith(".json") ? args.database : `${args.database}.json`);
    if (!filename) throw new Error(`Unknown database key: ${args.database}`);
    const rows = await readArray<JsonRow>(args.projectPath, filename);
    const idx = rows.findIndex((x) => x && (x as { id?: number }).id === args.id);
    if (idx === -1) throw new Error(`Entry id ${args.id} not found in ${filename}`);
    rows[idx] = { ...(rows[idx] as Record<string, unknown>), ...args.updates };
    await writeDataJson(args.projectPath, filename, rows);
    return jsonText(rows[idx]);
}
