import * as fs from "fs/promises";
import * as path from "path";

/**
 * カスタムエラークラス
 */
export class RPGMakerError extends Error {
  constructor(
    message: string,
    public code: string,
    public details?: any
  ) {
    super(message);
    this.name = "RPGMakerError";
  }
}

export class ValidationError extends RPGMakerError {
  constructor(message: string, details?: any) {
    super(message, "VALIDATION_ERROR", details);
    this.name = "ValidationError";
  }
}

export class FileOperationError extends RPGMakerError {
  constructor(message: string, details?: any) {
    super(message, "FILE_ERROR", details);
    this.name = "FileOperationError";
  }
}

export class APIError extends RPGMakerError {
  constructor(message: string, details?: any) {
    super(message, "API_ERROR", details);
    this.name = "APIError";
  }
}

/**
 * バリデーション関数
 */
export class Validator {
  static requireString(value: any, fieldName: string): string {
    if (typeof value !== "string" || value.trim().length === 0) {
      throw new ValidationError(
        `${fieldName} must be a non-empty string`,
        { field: fieldName, received: typeof value }
      );
    }
    return value;
  }

  static requireNumber(value: any, fieldName: string): number {
    if (typeof value !== "number" || isNaN(value)) {
      throw new ValidationError(
        `${fieldName} must be a valid number`,
        { field: fieldName, received: typeof value }
      );
    }
    return value;
  }

  static requirePositiveNumber(value: any, fieldName: string): number {
    const num = this.requireNumber(value, fieldName);
    if (num <= 0) {
      throw new ValidationError(
        `${fieldName} must be a positive number`,
        { field: fieldName, value: num }
      );
    }
    return num;
  }

  static requireEnum<T extends string>(
    value: any,
    fieldName: string,
    allowedValues: readonly T[]
  ): T {
    if (!allowedValues.includes(value as T)) {
      throw new ValidationError(
        `${fieldName} must be one of: ${allowedValues.join(", ")}`,
        { field: fieldName, received: value, allowed: allowedValues }
      );
    }
    return value as T;
  }

  static async requirePath(value: string, fieldName: string): Promise<string> {
    try {
      await fs.access(value);
      return value;
    } catch (error) {
      throw new ValidationError(
        `${fieldName} path does not exist or is not accessible: ${value}`,
        { field: fieldName, path: value }
      );
    }
  }

  static async requireDirectory(value: string, fieldName: string): Promise<string> {
    await this.requirePath(value, fieldName);

    try {
      const stats = await fs.stat(value);
      if (!stats.isDirectory()) {
        throw new ValidationError(
          `${fieldName} must be a directory: ${value}`,
          { field: fieldName, path: value }
        );
      }
      return value;
    } catch (error) {
      if (error instanceof ValidationError) throw error;
      throw new FileOperationError(
        `Failed to check directory: ${value}`,
        { field: fieldName, error: error instanceof Error ? error.message : String(error) }
      );
    }
  }

  static async requireFile(value: string, fieldName: string): Promise<string> {
    await this.requirePath(value, fieldName);

    try {
      const stats = await fs.stat(value);
      if (!stats.isFile()) {
        throw new ValidationError(
          `${fieldName} must be a file: ${value}`,
          { field: fieldName, path: value }
        );
      }
      return value;
    } catch (error) {
      if (error instanceof ValidationError) throw error;
      throw new FileOperationError(
        `Failed to check file: ${value}`,
        { field: fieldName, error: error instanceof Error ? error.message : String(error) }
      );
    }
  }
}

/**
 * ファイル操作ヘルパー
 */
export class FileHelper {
  static async readJSON<T = any>(filePath: string): Promise<T> {
    try {
      const content = await fs.readFile(filePath, "utf-8");
      return JSON.parse(content) as T;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") {
        throw new FileOperationError(
          `File not found: ${filePath}`,
          { path: filePath }
        );
      }
      if (error instanceof SyntaxError) {
        throw new FileOperationError(
          `Invalid JSON in file: ${filePath}`,
          { path: filePath, parseError: error.message }
        );
      }
      throw new FileOperationError(
        `Failed to read file: ${filePath}`,
        { path: filePath, error: error instanceof Error ? error.message : String(error) }
      );
    }
  }

  static async writeJSON(filePath: string, data: any, pretty = false): Promise<void> {
    try {
      const content = pretty ? JSON.stringify(data, null, 2) : JSON.stringify(data);
      await fs.writeFile(filePath, content, "utf-8");
    } catch (error) {
      throw new FileOperationError(
        `Failed to write file: ${filePath}`,
        { path: filePath, error: error instanceof Error ? error.message : String(error) }
      );
    }
  }

  static async ensureDirectory(dirPath: string): Promise<void> {
    try {
      await fs.mkdir(dirPath, { recursive: true });
    } catch (error) {
      throw new FileOperationError(
        `Failed to create directory: ${dirPath}`,
        { path: dirPath, error: error instanceof Error ? error.message : String(error) }
      );
    }
  }

  static async copyFile(source: string, destination: string): Promise<void> {
    try {
      await fs.copyFile(source, destination);
    } catch (error) {
      throw new FileOperationError(
        `Failed to copy file from ${source} to ${destination}`,
        { source, destination, error: error instanceof Error ? error.message : String(error) }
      );
    }
  }
}

/**
 * APIヘルパー（リトライロジック付き）
 */
export class APIHelper {
  static async fetchWithRetry(
    url: string,
    options: RequestInit,
    maxRetries = 3,
    retryDelay = 1000
  ): Promise<Response> {
    let lastError: Error | null = null;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const response = await fetch(url, options);

        if (!response.ok) {
          const errorBody = await response.text();
          throw new APIError(
            `API request failed with status ${response.status}`,
            {
              status: response.status,
              statusText: response.statusText,
              body: errorBody,
              url,
              attempt
            }
          );
        }

        return response;
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));

        if (error instanceof APIError) {
          // API エラーの場合、特定のステータスコードではリトライしない
          if (error.details?.status === 401 || error.details?.status === 403) {
            throw error; // 認証エラーはリトライしない
          }
        }

        if (attempt < maxRetries) {
          console.error(`API request failed (attempt ${attempt}/${maxRetries}), retrying...`);
          await new Promise(resolve => setTimeout(resolve, retryDelay * attempt));
        }
      }
    }

    throw new APIError(
      `API request failed after ${maxRetries} attempts`,
      { url, lastError: lastError?.message }
    );
  }

  static async fetchJSON<T = any>(
    url: string,
    options: RequestInit,
    maxRetries = 3
  ): Promise<T> {
    const response = await this.fetchWithRetry(url, options, maxRetries);

    try {
      return await response.json() as T;
    } catch (error) {
      throw new APIError(
        "Failed to parse API response as JSON",
        { url, error: error instanceof Error ? error.message : String(error) }
      );
    }
  }
}

/**
 * ロギングシステム
 */
export class Logger {
  private static logFile = "/tmp/rpgmaker-mz-mcp.log";
  private static debugMode = process.env.DEBUG === "true";

  static async log(level: "INFO" | "WARN" | "ERROR" | "DEBUG", message: string, details?: any): Promise<void> {
    const timestamp = new Date().toISOString();
    const logEntry = {
      timestamp,
      level,
      message,
      details
    };

    const logLine = `[${timestamp}] ${level}: ${message}${details ? " " + JSON.stringify(details) : ""}\n`;

    // コンソール出力
    if (level === "ERROR") {
      console.error(logLine);
    } else if (level === "WARN") {
      console.warn(logLine);
    } else if (level === "DEBUG" && this.debugMode) {
      console.debug(logLine);
    } else if (level === "INFO") {
      console.log(logLine);
    }

    // ファイル出力
    try {
      await fs.appendFile(this.logFile, logLine);
    } catch (error) {
      // ログファイル書き込み失敗は無視（無限ループ防止）
    }
  }

  static async info(message: string, details?: any): Promise<void> {
    await this.log("INFO", message, details);
  }

  static async warn(message: string, details?: any): Promise<void> {
    await this.log("WARN", message, details);
  }

  static async error(message: string, details?: any): Promise<void> {
    await this.log("ERROR", message, details);
  }

  static async debug(message: string, details?: any): Promise<void> {
    await this.log("DEBUG", message, details);
  }

  static async clearLog(): Promise<void> {
    try {
      await fs.writeFile(this.logFile, "");
    } catch (error) {
      // Ignore
    }
  }
}

/**
 * エラーレスポンス生成
 */
export function createErrorResponse(error: unknown): {
  success: false;
  error: string;
  code?: string;
  details?: any;
} {
  if (error instanceof RPGMakerError) {
    return {
      success: false,
      error: error.message,
      code: error.code,
      details: error.details
    };
  }

  if (error instanceof Error) {
    return {
      success: false,
      error: error.message,
      code: "UNKNOWN_ERROR"
    };
  }

  return {
    success: false,
    error: String(error),
    code: "UNKNOWN_ERROR"
  };
}

/**
 * 非同期処理のラッパー（エラーハンドリング付き）
 */
export async function safeExecute<T>(
  operation: () => Promise<T>,
  errorMessage: string
): Promise<{ success: true; data: T } | { success: false; error: string; code?: string; details?: any }> {
  try {
    const data = await operation();
    return { success: true, data };
  } catch (error) {
    await Logger.error(errorMessage, error);
    return createErrorResponse(error);
  }
}

/**
 * プロジェクトパス検証
 */
export async function validateProjectPath(projectPath: string): Promise<void> {
  Validator.requireString(projectPath, "project_path");

  // プロジェクトディレクトリの存在確認
  try {
    await fs.access(projectPath);
  } catch (error) {
    throw new ValidationError(
      `Project path does not exist: ${projectPath}`,
      { path: projectPath }
    );
  }

  // Game.rpgproject ファイルの確認
  const projectFile = path.join(projectPath, "Game.rpgproject");
  try {
    await fs.access(projectFile);
  } catch (error) {
    throw new ValidationError(
      `Not a valid RPG Maker MZ project (Game.rpgproject not found): ${projectPath}`,
      { path: projectPath, projectFile }
    );
  }

  // data ディレクトリの確認
  const dataDir = path.join(projectPath, "data");
  try {
    await fs.access(dataDir);
    const stats = await fs.stat(dataDir);
    if (!stats.isDirectory()) {
      throw new ValidationError(
        `Project data directory is not a directory: ${dataDir}`,
        { path: dataDir }
      );
    }
  } catch (error) {
    if (error instanceof ValidationError) throw error;
    throw new ValidationError(
      `Project data directory not found: ${dataDir}`,
      { path: projectPath, dataDir }
    );
  }
}

/**
 * マップID検証
 */
export async function validateMapId(projectPath: string, mapId: number): Promise<void> {
  Validator.requirePositiveNumber(mapId, "map_id");

  const mapFile = path.join(projectPath, "data", `Map${String(mapId).padStart(3, "0")}.json`);

  try {
    await fs.access(mapFile);
  } catch (error) {
    throw new ValidationError(
      `Map does not exist: Map${String(mapId).padStart(3, "0")}`,
      { projectPath, mapId, mapFile }
    );
  }
}

/**
 * Gemini APIキー検証
 */
export function validateGeminiAPIKey(apiKey?: string): string {
  const key = apiKey || process.env.GEMINI_API_KEY;

  if (!key || key.trim().length === 0) {
    throw new ValidationError(
      "Gemini API key is required. Please provide api_key parameter or set GEMINI_API_KEY environment variable.",
      { envVarSet: !!process.env.GEMINI_API_KEY }
    );
  }

  if (!key.startsWith("AIza")) {
    throw new ValidationError(
      "Invalid Gemini API key format. Key should start with 'AIza'.",
      { keyPrefix: key.substring(0, 4) }
    );
  }

  return key;
}

/**
 * エラーを分かりやすくフォーマット
 */
export function formatError(error: unknown): string {
  if (error instanceof RPGMakerError) {
    let message = `❌ ${error.name}: ${error.message}`;
    if (error.details) {
      message += `\n📋 Details: ${JSON.stringify(error.details, null, 2)}`;
    }
    return message;
  }

  if (error instanceof Error) {
    return `❌ Error: ${error.message}`;
  }

  return `❌ Unknown error: ${String(error)}`;
}

/**
 * グローバルエラーハンドラーのセットアップ
 */
export function setupGlobalErrorHandlers(): void {
  process.on("uncaughtException", async (error) => {
    await Logger.error("Uncaught Exception", {
      error: error.message,
      stack: error.stack
    });
    console.error("💥 Uncaught Exception:", error);
    process.exit(1);
  });

  process.on("unhandledRejection", async (reason) => {
    await Logger.error("Unhandled Promise Rejection", {
      reason: reason instanceof Error ? reason.message : String(reason),
      stack: reason instanceof Error ? reason.stack : undefined
    });
    console.error("💥 Unhandled Promise Rejection:", reason);
    process.exit(1);
  });
}
