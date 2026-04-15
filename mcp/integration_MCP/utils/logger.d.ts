export declare const Logger: {
    configure(config: { enableFileLogging?: boolean; logLevel?: string; logDir?: string; enableErrorFile?: boolean }): void;
    getConfig(): { enableFileLogging: boolean; logLevel: string; logDir: string; enableErrorFile: boolean };
    debug(message: string, ...args: unknown[]): Promise<void>;
    info(message: string, ...args: unknown[]): Promise<void>;
    warn(message: string, ...args: unknown[]): Promise<void>;
    error(message: string, error: Error | unknown, ...args: unknown[]): Promise<void>;
    child(prefix: string): {
        debug: (message: string, ...args: unknown[]) => Promise<void>;
        info: (message: string, ...args: unknown[]) => Promise<void>;
        warn: (message: string, ...args: unknown[]) => Promise<void>;
        error: (message: string, error: Error | unknown, ...args: unknown[]) => Promise<void>;
    };
};
