import { z } from 'zod';

// Event Command Schema
export const EventCommandSchema = z.object({
    code: z.number().int().min(0),
    indent: z.number().int().min(0),
    parameters: z.array(z.union([z.string(), z.number(), z.null(), z.boolean(), z.array(z.any())]))
});

// Event Page Schema
export const EventPageSchema = z.object({
    conditions: z.any().optional(),
    image: z.any().optional(),
    moveType: z.any().optional(),
    moveSpeed: z.any().optional(),
    moveFrequency: z.any().optional(),
    moveRoute: z.any().optional(),
    walkAnime: z.any().optional(),
    stepAnime: z.any().optional(),
    directionFix: z.any().optional(),
    through: z.any().optional(),
    priorityType: z.any().optional(),
    trigger: z.any().optional(),
    list: z.array(EventCommandSchema)
        .refine((list) => {
            // Must have at least one command
            if (list.length === 0) return false;
            // Last command must be code 0 (Empty/End)
            return list[list.length - 1].code === 0;
        }, {
            message: "Event list must end with code 0"
        })
});

// Event Schema
export const EventSchema = z.object({
    id: z.number().int().positive(),
    name: z.string(),
    note: z.string().optional(),
    pages: z.array(EventPageSchema).min(1),
    x: z.number().int().min(0).optional(),
    y: z.number().int().min(0).optional()
});

// Validation helper functions
export function validateEventCommand(command) {
    return EventCommandSchema.safeParse(command);
}

export function validateEventPage(page) {
    return EventPageSchema.safeParse(page);
}

export function validateEvent(event) {
    return EventSchema.safeParse(event);
}

// Custom validators for specific tool outputs
export function validateDialogueCommands(commands) {
    // Dialogues should be code 101 followed by code 401(s)
    if (commands.length < 2) return false;
    if (commands[0].code !== 101) return false;
    for (let i = 1; i < commands.length; i++) {
        if (commands[i].code !== 401) return false;
    }
    return true;
}

export function validateChoiceStructure(commands) {
    // Choice structure: 102 -> 402(s) -> [403?] -> 404
    if (commands.length < 3) return false;
    if (commands[0].code !== 102) return false;
    if (commands[commands.length - 1].code !== 404) return false;

    // Check that we have 402 (When) commands
    const whenCommands = commands.filter(cmd => cmd.code === 402);
    if (whenCommands.length === 0) return false;

    return true;
}
