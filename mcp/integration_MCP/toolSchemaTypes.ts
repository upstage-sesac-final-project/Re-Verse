/** Shared MCP tool list schema (ListTools / CallTool). */

export type ToolSchema = {
    name: string;
    description: string;
    inputSchema: {
        type: "object";
        properties: Record<string, {
            type: string;
            description?: string;
            default?: unknown;
            enum?: string[];
            items?: { type: string; properties?: Record<string, unknown>; required?: string[] };
            properties?: Record<string, unknown>;
            required?: string[];
        }>;
        required: string[];
    };
};
