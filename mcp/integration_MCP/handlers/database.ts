import fs from "fs/promises";
import path from "path";
import { validateProjectPath } from "../utils/validation.js";
import { Errors } from "../utils/errors.js";
import { HandlerResponse, Actor, Item, Skill } from "../types/index.js";
import { withBackup, cleanupOldBackups } from "../utils/backup.js";
import { Logger } from "../utils/logger.js";

type ProjectArgs = { projectPath: string };
type AddActorArgs = ProjectArgs & { name: string; classId?: number; initialLevel?: number; maxLevel?: number };
type AddItemArgs = ProjectArgs & { name: string; price?: number; consumable?: boolean; scope?: number; occasion?: number };
type AddSkillArgs = ProjectArgs & { name: string; mpCost?: number; tpCost?: number; scope?: number; occasion?: number };

export async function addActor(args: AddActorArgs): Promise<HandlerResponse> {
    const { projectPath, name, classId = 1, initialLevel = 1, maxLevel = 99 } = args;
    await validateProjectPath(projectPath);

    const filePath = path.join(projectPath, "data", "Actors.json");
    let actors: Array<Actor | null> = [];
    try {
        actors = JSON.parse(await fs.readFile(filePath, "utf-8")) as Array<Actor | null>;
    } catch (e: unknown) {
        const err = e as NodeJS.ErrnoException;
        if (err?.code === 'ENOENT') {
            actors = [null];
        } else {
            throw Errors.dataFileReadError('Actors.json', err?.message ?? String(e));
        }
    }

    const newId = actors.length;
    const newActor: Actor = {
        id: newId,
        name: name,
        classId: classId,
        level: initialLevel,
        characterName: "",
        characterIndex: 0,
        faceName: "",
        faceIndex: 0,
        traits: [],
        initialLevel: initialLevel,
        maxLevel: maxLevel,
        nickname: "",
        note: "",
        profile: ""
    };

    actors.push(newActor);

    // Write with backup
    await withBackup(filePath, async () => {
        await fs.writeFile(filePath, JSON.stringify(actors, null, 2), "utf-8");
    });

    // Cleanup old backups (non-blocking)
    cleanupOldBackups(filePath).catch(async (e: unknown) => {
        await Logger.debug(`Failed to cleanup old backups for ${filePath} (non-critical)`, e).catch(() => {
            // Last resort: ignore logger errors
        });
    });

    return {
        content: [{ type: "text", text: `Successfully added actor "${name}" (ID: ${newId}).` }],
    };
}

export async function addItem(args: AddItemArgs): Promise<HandlerResponse> {
    const { projectPath, name, price = 0, consumable = true, scope = 7, occasion = 0 } = args;
    await validateProjectPath(projectPath);

    const filePath = path.join(projectPath, "data", "Items.json");
    let items: Array<Item | null> = [];
    try {
        items = JSON.parse(await fs.readFile(filePath, "utf-8")) as Array<Item | null>;
    } catch (e: unknown) {
        const err = e as NodeJS.ErrnoException;
        if (err?.code === 'ENOENT') {
            items = [null];
        } else {
            throw Errors.dataFileReadError('Items.json', err?.message ?? String(e));
        }
    }

    const newId = items.length;
    const newItem: Item = {
        id: newId,
        name: name,
        iconIndex: 0,
        description: "",
        price: price,
        consumable: consumable,
        scope: scope,
        occasion: occasion,
        speed: 0,
        successRate: 100,
        repeats: 1,
        tpGain: 0,
        hitType: 0,
        animationId: 0,
        damage: { type: 0, elementId: 0, formula: "0", variance: 20 },
        effects: [],
        note: ""
    };

    items.push(newItem);

    // Write with backup
    await withBackup(filePath, async () => {
        await fs.writeFile(filePath, JSON.stringify(items, null, 2), "utf-8");
    });

    // Cleanup old backups (non-blocking)
    cleanupOldBackups(filePath).catch(async (e: unknown) => {
        await Logger.debug(`Failed to cleanup old backups for ${filePath} (non-critical)`, e).catch(() => {
            // Last resort: ignore logger errors
        });
    });

    return {
        content: [{ type: "text", text: `Successfully added item "${name}" (ID: ${newId}).` }],
    };
}

export async function addSkill(args: AddSkillArgs): Promise<HandlerResponse> {
    const { projectPath, name, mpCost = 0, tpCost = 0, scope = 1, occasion = 1 } = args;
    await validateProjectPath(projectPath);

    const filePath = path.join(projectPath, "data", "Skills.json");
    let skills: Array<Skill | null> = [];
    try {
        skills = JSON.parse(await fs.readFile(filePath, "utf-8")) as Array<Skill | null>;
    } catch (e: unknown) {
        const err = e as NodeJS.ErrnoException;
        if (err?.code === 'ENOENT') {
            skills = [null];
        } else {
            throw Errors.dataFileReadError('Skills.json', err?.message ?? String(e));
        }
    }

    const newId = skills.length;
    const newSkill: Skill = {
        id: newId,
        name: name,
        iconIndex: 0,
        description: "",
        mpCost: mpCost,
        tpCost: tpCost,
        scope: scope,
        occasion: occasion,
        speed: 0,
        successRate: 100,
        repeats: 1,
        tpGain: 0,
        hitType: 1,
        animationId: 0,
        damage: { type: 1, elementId: 0, formula: "0", variance: 20 },
        effects: [],
        note: "",
        message1: "",
        message2: "",
        requiredWtypeId1: 0,
        requiredWtypeId2: 0,
        stypeId: 1
    };

    skills.push(newSkill);

    // Write with backup
    await withBackup(filePath, async () => {
        await fs.writeFile(filePath, JSON.stringify(skills, null, 2), "utf-8");
    });

    // Cleanup old backups (non-blocking)
    cleanupOldBackups(filePath).catch(async (e: unknown) => {
        await Logger.debug(`Failed to cleanup old backups for ${filePath} (non-critical)`, e).catch(() => {
            // Last resort: ignore logger errors
        });
    });

    return {
        content: [{ type: "text", text: `Successfully added skill "${name}" (ID: ${newId}).` }],
    };
}
