# 🛡️ エラーハンドリングガイド

## 概要

RPG Maker MZ MCPサーバーは、包括的なエラーハンドリングシステムを実装しており、堅牢で信頼性の高い動作を保証します。

---

## 🎯 実装されたエラーハンドリング機能

### 1. **入力バリデーション**

すべてのMCPツールで以下の検証を実施：

#### 必須パラメータチェック
```typescript
// 文字列検証
Validator.requireString(value, "fieldName")

// 数値検証
Validator.requireNumber(value, "fieldName")

// 正の数値検証
Validator.requirePositiveNumber(value, "fieldName")

// 列挙型検証
Validator.requireEnum(value, "fieldName", ["option1", "option2"])
```

#### パス検証
```typescript
// パス存在確認
await Validator.requirePath(path, "fieldName")

// ディレクトリ確認
await Validator.requireDirectory(path, "fieldName")

// ファイル確認
await Validator.requireFile(path, "fieldName")
```

#### RPG Maker MZプロジェクト検証
```typescript
// プロジェクト構造検証
await validateProjectPath(projectPath)
// - Game.rpgproject の存在確認
// - data/ ディレクトリの存在確認
// - アクセス権限チェック
```

---

### 2. **ファイル操作のエラーハンドリング**

#### FileHelper クラス
```typescript
// JSON読み込み（エラーハンドリング付き）
const data = await FileHelper.readJSON(filePath)

// JSON書き込み（エラーハンドリング付き）
await FileHelper.writeJSON(filePath, data)

// ディレクトリ作成（再帰的）
await FileHelper.ensureDirectory(dirPath)

// ファイルコピー
await FileHelper.copyFile(source, destination)
```

#### エラー種類
- **ENOENT**: ファイルが存在しない
- **SyntaxError**: 不正なJSON
- **EACCES**: アクセス権限エラー

---

### 3. **API呼び出しのエラーハンドリング**

#### リトライロジック付きAPI呼び出し

```typescript
// 最大3回まで自動リトライ
const response = await APIHelper.fetchWithRetry(url, options, maxRetries = 3)

// JSON APIの場合
const data = await APIHelper.fetchJSON(url, options)
```

#### 対応エラー
- **401/403**: 認証エラー（リトライしない）
- **429**: レート制限（指数バックオフでリトライ）
- **500/502/503**: サーバーエラー（リトライ）
- **Timeout**: タイムアウト（リトライ）
- **Network Error**: ネットワークエラー（リトライ）

#### Gemini API キー検証
```typescript
// APIキー形式チェック
const apiKey = validateGeminiAPIKey(providedKey)
// - "AIza" で始まるかチェック
// - 環境変数フォールバック
// - 詳細なエラーメッセージ
```

---

### 4. **ロギングシステム**

#### Logger クラス

```typescript
// ログレベル
await Logger.info("Message", { details })
await Logger.warn("Warning", { details })
await Logger.error("Error", { details })
await Logger.debug("Debug info", { details })
```

#### ログ出力
- **コンソール出力**: レベルに応じて色分け
- **ファイル出力**: `/tmp/rpgmaker-mz-mcp.log`
- **構造化ログ**: JSON形式で詳細情報を記録

#### ログ例
```
[2025-09-30T15:16:01.166Z] INFO: Creating new project {"projectPath":"/tmp/test","gameTitle":"Test"}
[2025-09-30T15:16:01.171Z] INFO: Project created successfully {"projectPath":"/tmp/test"}
[2025-09-30T15:16:01.175Z] ERROR: Failed to create map {"projectPath":"/tmp/test","mapId":-1,"error":"..."}
```

#### デバッグモード
```bash
DEBUG=true npx rpgmaker-mz-mcp auto-create ...
```

---

### 5. **カスタムエラークラス**

#### エラー階層
```typescript
RPGMakerError (基底クラス)
├── ValidationError - 入力検証エラー
├── FileOperationError - ファイル操作エラー
└── APIError - API呼び出しエラー
```

#### エラー情報
各エラーには以下が含まれる：
- **message**: 人間が読めるエラーメッセージ
- **code**: エラーコード（例: "VALIDATION_ERROR"）
- **details**: 詳細情報（JSON）

---

### 6. **グローバルエラーハンドラー**

#### 未捕捉例外の処理
```typescript
setupGlobalErrorHandlers()
// - uncaughtException をキャッチ
// - unhandledRejection をキャッチ
// - ログに記録してプロセス終了
```

---

## 📋 エラーメッセージ例

### ValidationError
```
❌ ValidationError: project_path must be a non-empty string
📋 Details: {
  "field": "project_path",
  "received": "undefined"
}
```

### FileOperationError
```
❌ FileOperationError: File not found: /path/to/Map001.json
📋 Details: {
  "path": "/path/to/Map001.json"
}
```

### APIError
```
❌ APIError: API request failed with status 401
📋 Details: {
  "status": 401,
  "statusText": "Unauthorized",
  "url": "https://...",
  "attempt": 1
}
```

---

## 🔧 エラーハンドリングのベストプラクティス

### 1. **早期検証**
関数の最初で入力を検証：
```typescript
export async function myFunction(param: string) {
  // ✅ 最初に検証
  Validator.requireString(param, "param");

  // 処理続行
  // ...
}
```

### 2. **詳細なエラーメッセージ**
```typescript
// ❌ 悪い例
throw new Error("Invalid input");

// ✅ 良い例
throw new ValidationError(
  "map_id must be a positive number",
  { field: "map_id", value: -1 }
);
```

### 3. **ログ記録**
```typescript
try {
  await Logger.info("Starting operation", { params });
  // 処理
  await Logger.info("Operation completed successfully");
} catch (error) {
  await Logger.error("Operation failed", { error });
  throw error;
}
```

### 4. **適切なエラー型の選択**
```typescript
// 入力検証エラー
throw new ValidationError("Invalid input");

// ファイル操作エラー
throw new FileOperationError("Cannot read file");

// API呼び出しエラー
throw new APIError("API request failed");
```

---

## 🧪 テスト結果

### エラーハンドリングテスト (8/8 成功)

✅ 空文字列パス検証
✅ 空タイトル検証
✅ 重複プロジェクト検出
✅ 負のマップID検証
✅ 不正なAPIキー形式検出
✅ APIキー未設定検出
✅ 不正な列挙値検出（length）
✅ 不正な列挙値検出（assetType）

### 実行方法
```bash
npm run test:error
```

---

## 📊 エラーハンドリング統計

| 機能 | 実装状況 |
|------|----------|
| 入力バリデーション | ✅ 実装済み |
| ファイル操作エラー | ✅ 実装済み |
| API エラー＋リトライ | ✅ 実装済み |
| ロギングシステム | ✅ 実装済み |
| グローバルハンドラー | ✅ 実装済み |
| カスタムエラー型 | ✅ 実装済み |
| テストカバレッジ | ✅ 8/8 成功 |

---

## 🔍 デバッグ方法

### 1. ログファイルを確認
```bash
tail -f /tmp/rpgmaker-mz-mcp.log
```

### 2. デバッグモード有効化
```bash
DEBUG=true npm run start
```

### 3. エラー詳細を取得
エラーレスポンスには常に以下が含まれる：
```json
{
  "success": false,
  "error": "Human readable message",
  "code": "ERROR_CODE",
  "details": {
    "field": "param_name",
    "additional": "info"
  }
}
```

---

## 🚀 エラーハンドリングの効果

### Before (エラーハンドリング前)
```
Error: undefined
  at createMap (...)
```

### After (エラーハンドリング後)
```
❌ ValidationError: map_id must be a positive number
📋 Details: {
  "field": "map_id",
  "value": -1
}

[2025-09-30T15:16:01.175Z] ERROR: Failed to create map {
  "projectPath": "/tmp/test",
  "mapId": -1,
  "error": {...}
}
```

---

## 📚 関連ファイル

- **src/error-handling.ts** - エラーハンドリングコア
- **test-error-handling.mjs** - エラーハンドリングテスト
- **src/game-creation-tools.ts** - 実装例
- **src/scenario-generation.ts** - API エラー処理例
- **src/asset-generation.ts** - APIキー検証例

---

**🛡️ 堅牢で信頼性の高いRPG開発環境！**
