import { EventCommand } from "../types/index.js";

export declare function annotateCommand(cmd: EventCommand): EventCommand & { _description?: string };
