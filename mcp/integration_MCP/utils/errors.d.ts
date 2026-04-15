export declare const ErrorCodes: {
    INVALID_PROJECT_PATH: string;
    PROJECT_NOT_DIRECTORY: string;
    PROJECT_FILE_NOT_FOUND: string;
    MAP_FILE_NOT_FOUND: string;
    MAP_FILE_READ_ERROR: string;
    MAP_FILE_WRITE_ERROR: string;
    EVENT_NOT_FOUND: string;
    EVENT_PAGE_NOT_FOUND: string;
    DATA_FILE_NOT_FOUND: string;
    DATA_FILE_READ_ERROR: string;
    DATA_FILE_WRITE_ERROR: string;
    DATA_FILE_INVALID_JSON: string;
    ASSET_NOT_FOUND: string;
    ASSET_PATH_INVALID: string;
    PLUGIN_FILE_NOT_FOUND: string;
    PLUGIN_FILE_READ_ERROR: string;
    PLUGIN_FILE_WRITE_ERROR: string;
    VALIDATION_ERROR: string;
    INVALID_PARAMETER: string;
    MISSING_REQUIRED_PARAMETER: string;
    RUNTIME_ERROR: string;
    OPERATION_FAILED: string;
};

export declare class MCPError extends Error {
    constructor(code: string, message: string, details?: Record<string, unknown>);
    code: string;
    details: Record<string, unknown>;
}

export declare const Errors: {
    invalidProjectPath(projectPath: string, reason: string): MCPError;
    projectNotDirectory(projectPath: string): MCPError;
    projectFileNotFound(projectPath: string): MCPError;
    mapFileNotFound(mapId: number, projectPath: string): MCPError;
    mapFileReadError(mapId: number, reason: string): MCPError;
    eventNotFound(eventId: string | number, mapId: string | number): MCPError;
    eventPageNotFound(eventId: string | number, pageIndex: number, mapId: string | number): MCPError;
    dataFileNotFound(filename: string, projectPath: string): MCPError;
    dataFileReadError(filename: string, reason: string): MCPError;
    dataFileWriteError(filename: string, reason: string): MCPError;
    invalidParameter(parameterName: string, reason: string): MCPError;
    missingRequiredParameter(parameterName: string): MCPError;
    assetPathInvalid(path: string): MCPError;
};
