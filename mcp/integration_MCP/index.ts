import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema, ListResourcesRequestSchema, ReadResourceRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import fs from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";
import * as fsSync from "fs";
import { Logger } from "./utils/logger.js";
import { toolMap } from "./mcpToolMap.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Crash logging
const logCrash = (type: string, error: unknown): void => {
  const logPath = path.join(__dirname, "crash_log.txt");
  const message = `[${new Date().toISOString()}] ${type}: ${error instanceof Error ? error.stack : String(error)}\n`;
  try {
    fsSync.appendFileSync(logPath, message);
  } catch (e: unknown) {
    // Last resort
  }
};

process.on('uncaughtException', (err) => {
  logCrash('Uncaught Exception', err);
  process.exit(1);
});

process.on('unhandledRejection', (reason) => {
  logCrash('Unhandled Rejection', reason);
  process.exit(1);
});

const server = new Server(
  {
    name: "rpg-maker-mz-mcp",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
      resources: {},
    },
  }
);

server.setRequestHandler(ListResourcesRequestSchema, async () => {
  try {
    return {
      resources: [
        {
          uri: "mz://docs/event_commands",
          name: "RPG Maker MZ Event Command Reference",
          description: "Reference manual for MZ event commands with code to parameters mapping",
          mimeType: "application/json"
        }
      ]
    };
  } catch (error: unknown) {
    logCrash('ListResourcesRequestSchema handler error', error);
    throw error;
  }
});

server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
    try {
        const { uri } = request.params;

        if (uri === "mz://docs/event_commands") {
            try {
                const refPath = path.join(__dirname, "resources", "event_commands.json");
                const content = await fs.readFile(refPath, "utf-8");
                return {
                    contents: [
                        {
                            uri: uri,
                            mimeType: "application/json",
                            text: content
                        }
                    ]
                };
            } catch (e: unknown) {
                const err = e as Error;
                throw new Error(`Failed to read event commands reference: ${err.message}`);
            }
        }

        throw new Error(`Unknown resource: ${uri}`);
    } catch (error: unknown) {
        logCrash('ReadResourceRequestSchema handler error', error);
        throw error;
    }
});

// List Tools handler (imports tool schemas from ./toolSchemas.ts)
import { toolSchemas } from "./toolSchemas.js";
import { resolveImplementationToolName } from "./generated/toolRegistry.generated.js";

server.setRequestHandler(ListToolsRequestSchema, async () => {
  try {
    return {
      tools: toolSchemas
    };
  } catch (error: unknown) {
    logCrash('ListToolsRequestSchema handler error', error);
    throw error;
  }
});

// Call Tool handler
server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    const implName = resolveImplementationToolName(name);
    await Logger.info(`Processing tool: ${name}${implName !== name ? ` (resolved: ${implName})` : ""}`);

    try {
        const handler = toolMap[implName as keyof typeof toolMap];
        if (!handler) {
            throw new Error(`Unknown tool: ${name}`);
        }
        if (!args) {
            throw new Error(`Missing arguments for tool: ${name}`);
        }
        // Type assertion: MCP validates args at runtime, so this is safe
        return await handler(args as any);
    } catch (error: unknown) {
        const err = error as Error;
        await Logger.error(`Error executing tool ${name}`, err);
        return {
            content: [
                {
                    type: "text",
                    text: `Error: ${err.message}`,
                },
            ],
            isError: true,
        };
    }
});

// Start server
const transport = new StdioServerTransport();
await server.connect(transport);
await Logger.info("RPG Maker MZ MCP Server running on stdio.");
