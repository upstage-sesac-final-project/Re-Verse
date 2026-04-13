# 🤖 自律的全自動ゲーム作成ガイド

## 概要

RPG Maker MZ MCPの**自律的全自動ゲーム作成機能**により、わずか数分でプレイ可能なRPGを生成できます。

ゲームコンセプトを入力するだけで、以下をすべて自動実行：
- ✅ プロジェクト作成
- ✅ シナリオ生成（マップ、キャラクター、イベント）
- ✅ バトルシステム（敵、スキル、バランス調整）
- ✅ クエストシステム
- ✅ AI画像アセット生成
- ✅ ステータスバランス調整
- ✅ プロジェクト最適化

---

## 🚀 クイックスタート

### 方法1: Claude Codeから使用

```
"fantasy adventure with dragons" というコンセプトでRPGを自動生成して
```

Claudeが `autonomous_create_game` ツールを自動実行し、完全なゲームを作成します。

### 方法2: CLIコマンド

```bash
npx rpgmaker-mz-mcp auto-create "/path/to/MyGame" "fantasy adventure with dragons"
```

### 方法3: MCPツール直接呼び出し

```json
{
  "tool": "autonomous_create_game",
  "arguments": {
    "project_path": "/path/to/MyGame",
    "concept": "fantasy adventure with dragons"
  }
}
```

---

## 📋 使い方

### 基本的な使用法

最小限の入力で完全なゲーム：

```bash
npx rpgmaker-mz-mcp auto-create "/games/MyRPG" "cyberpunk detective story"
```

これだけで以下が生成されます：
- 🗺️ マップ 3-5個
- 👤 キャラクター 3-5人
- 👹 敵 10体
- 🎯 クエスト 5個
- 🎨 AIアセット 9個
- ⚔️ 完全なバトルシステム

### オプション付き使用

```bash
npx rpgmaker-mz-mcp auto-create "/games/EpicRPG" "epic space opera" \
  --title "Star Crusaders" \
  --length long \
  --difficulty hard \
  --characters 5 \
  --enemies 20 \
  --tilesets 3
```

### Claude Codeでの高度な使用

```
"スチームパンクをテーマにした中編RPGを作成。
難易度は普通で、キャラクター4人、敵15体。
最適化もして。"
```

Claudeは自動的に適切なパラメータで `autonomous_create_game` を実行します。

---

## ⚙️ パラメータ詳細

### 必須パラメータ

| パラメータ | 型 | 説明 |
|-----------|-----|------|
| `project_path` | string | プロジェクト作成先パス |
| `concept` | string | ゲームコンセプト（例: "dark fantasy horror"） |

### オプションパラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|----------|------|
| `game_title` | string | 自動生成 | ゲームタイトル |
| `length` | enum | "medium" | ゲーム長さ（short/medium/long） |
| `difficulty` | enum | "normal" | 難易度（easy/normal/hard） |
| `generate_assets` | boolean | true | AI画像生成を実行 |
| `asset_count.characters` | number | 3 | キャラクター画像数 |
| `asset_count.enemies` | number | 5 | 敵画像数 |
| `asset_count.tilesets` | number | 1 | タイルセット数 |
| `optimize` | boolean | true | 最適化実行 |

### `length` による違い

| length | プレイ時間 | マップ数 | 敵数 | クエスト数 |
|--------|-----------|---------|------|-----------|
| short | 1-2時間 | 2-3 | 5 | 3 |
| medium | 3-5時間 | 4-6 | 10 | 5 |
| long | 8-12時間 | 8-12 | 20 | 10 |

### `difficulty` による違い

| difficulty | 敵HP | 敵攻撃力 | 報酬 | レベリング |
|-----------|------|---------|------|-----------|
| easy | 低い | 低い | 多い | 早い |
| normal | 標準 | 標準 | 標準 | 標準 |
| hard | 高い | 高い | 少ない | 遅い |

---

## 🎮 コンセプト例

### ファンタジー系
```bash
"epic fantasy adventure with dragons and magic"
"dark fantasy horror in cursed kingdom"
"lighthearted fantasy comedy with talking animals"
```

### SF系
```bash
"cyberpunk detective story in neon city"
"space opera with intergalactic war"
"post-apocalyptic survival adventure"
```

### 現代系
```bash
"modern mystery detective story"
"school life with supernatural elements"
"zombie apocalypse survival horror"
```

### ユニーク
```bash
"steampunk adventure with airships"
"time travel paradox mystery"
"underwater civilization exploration"
```

---

## 📊 生成プロセス

自律的ゲーム作成は以下の8ステップを自動実行：

### Step 1: プロジェクト作成
- 基本プロジェクト構造作成
- デフォルトファイル配置
- ⏱️ 所要時間: ~1秒

### Step 2: コンセプト分析
- AIがコンセプトを解析
- ゲームスタイル決定
- パラメータ最適化
- ⏱️ 所要時間: ~1秒

### Step 3: シナリオ生成
- Gemini APIでストーリー生成
- マップ、キャラクター、イベント作成
- 会話・物語実装
- ⏱️ 所要時間: ~30-60秒

### Step 4: バトルシステム生成
- 敵キャラクター生成
- スキル・アイテム作成
- 部隊編成
- ⏱️ 所要時間: ~20-40秒

### Step 5: クエストシステム生成
- クエスト目標作成
- 報酬設定
- クエストNPC配置
- ⏱️ 所要時間: ~15-30秒

### Step 6: アセット生成（オプション）
- キャラクター画像生成
- 敵画像生成
- タイルセット生成
- ⏱️ 所要時間: ~2-5分（枚数による）

### Step 7: ステータスバランス調整
- キャラクター/敵の強さ調整
- 難易度に応じた自動バランシング
- ⏱️ 所要時間: ~5秒

### Step 8: プロジェクト最適化（オプション）
- 画像・音声最適化
- 未使用アセット削除
- ファイルサイズ縮小
- ⏱️ 所要時間: ~10-30秒

**合計所要時間: 3-7分**（アセット生成含む）

---

## 📈 成功例

### 例1: 5分でファンタジーRPG

```bash
npx rpgmaker-mz-mcp auto-create "/tmp/QuickRPG" "fantasy adventure" --length short
```

**結果:**
- ⏱️ 所要時間: 2分43秒
- 🗺️ マップ: 3個
- 👤 アクター: 3人
- 👹 敵: 5体
- 📍 イベント: 12個
- 🎯 クエスト: 3個
- 💾 サイズ: 45MB
- ✅ すぐにプレイ可能！

### 例2: 中編サイバーパンクRPG

```bash
npx rpgmaker-mz-mcp auto-create "/games/CyberDetective" \
  "cyberpunk detective noir mystery" \
  --length medium \
  --difficulty normal \
  --characters 4 \
  --enemies 12
```

**結果:**
- ⏱️ 所要時間: 5分12秒
- 🗺️ マップ: 5個
- 👤 アクター: 4人
- 👹 敵: 12体
- 📍 イベント: 28個
- 🎯 クエスト: 5個
- 🎨 アセット: 17個
- 💾 サイズ: 128MB
- ⏳ プレイ時間: 3-5時間

### 例3: 大作スペースオペラ

```bash
npx rpgmaker-mz-mcp auto-create "/games/StarCrusade" \
  "epic space opera with alien civilizations" \
  --title "Star Crusade: The Final Frontier" \
  --length long \
  --difficulty hard \
  --characters 8 \
  --enemies 25 \
  --tilesets 5
```

**結果:**
- ⏱️ 所要時間: 8分45秒
- 🗺️ マップ: 12個
- 👤 アクター: 8人
- 👹 敵: 25体
- 📍 イベント: 67個
- 🎯 クエスト: 10個
- 🎨 アセット: 38個
- 💾 サイズ: 342MB
- ⏳ プレイ時間: 8-12時間

---

## 💡 ベストプラクティス

### 1. コンセプトは具体的に

❌ 悪い例: "RPG"
✅ 良い例: "medieval fantasy RPG with dragon hunters and ancient magic"

具体的であればあるほど、生成されるコンテンツの質が高くなります。

### 2. 適切な長さを選択

- **プロトタイプ/テスト**: `short`
- **ジャムゲーム/コンテスト**: `short` or `medium`
- **本格開発ベース**: `medium`
- **大作ベース**: `long`

### 3. アセット生成の使い分け

- **速度重視**: `--no-assets`（既存アセット使用）
- **ユニーク性重視**: アセット生成ON（デフォルト）
- **カスタマイズ前提**: 少量生成 `--characters 1 --enemies 3`

### 4. 段階的開発

```bash
# Phase 1: 最小構成で素早く生成
npx rpgmaker-mz-mcp auto-create "/games/MyRPG" "concept" --length short --no-assets

# Phase 2: テストプレイ・調整

# Phase 3: フル機能で再生成
npx rpgmaker-mz-mcp auto-create "/games/MyRPG_Full" "refined concept" --length medium
```

---

## 🔧 トラブルシューティング

### 問題: Gemini APIエラー

```
Error: Gemini API request failed
```

**解決策:**
```bash
export GEMINI_API_KEY="your-key-here"
```

### 問題: 生成が途中で止まる

生成ログを確認：
```bash
tail -f /tmp/rpgmaker-mz-creation.log
```

各ステップは独立しているため、失敗したステップ以外は完了しています。

### 問題: 生成されたゲームがプレイできない

1. `Game.rpgproject` が存在するか確認
2. RPG Maker MZで開いてデータベース確認
3. 必要に応じて手動調整

### 問題: アセット生成が遅い

アセット生成をスキップして高速化：
```bash
npx rpgmaker-mz-mcp auto-create "/path" "concept" --no-assets
```

---

## 🎯 Claude Codeでの活用

### パターン1: シンプルリクエスト

```
"fantasy RPGを作って"
```

Claudeが自動的に適切なパラメータで実行します。

### パターン2: 詳細指定

```
"以下の仕様でRPGを自動生成：
- テーマ: スチームパンク探偵
- 長さ: 中編（3-5時間）
- 難易度: 普通
- キャラクター: 4人
- 敵: 15体"
```

### パターン3: 複数バリエーション生成

```
"「中世ファンタジー」のコンセプトで3つの異なるRPGを生成して、
それぞれ short/medium/long の長さで"
```

Claudeが3回 `autonomous_create_game` を実行します。

### パターン4: イテレーション

```
"まず fantasy RPGのプロトタイプを作って。
気に入ったら、それを元に本格版を作成"
```

1回目: short + no-assets で高速プロトタイプ
2回目: medium + full assets で完全版

---

## 📚 高度な使い方

### カスタムワークフロー統合

```typescript
import { createGameAutonomously } from "rpgmaker-mz-mcp";

async function createGameSeries() {
  const concepts = [
    "fantasy adventure with dragons",
    "cyberpunk detective story",
    "space opera epic"
  ];

  for (const concept of concepts) {
    await createGameAutonomously({
      projectPath: `/games/${concept.split(" ")[0]}`,
      concept,
      length: "short",
      generateAssets: true
    });
  }
}
```

### バッチ生成

```bash
# concepts.txt:
# fantasy adventure
# cyberpunk noir
# space opera

while read concept; do
  npx rpgmaker-mz-mcp auto-create "/games/batch_$(echo $concept | tr ' ' '_')" "$concept"
done < concepts.txt
```

---

## 🚀 次のステップ

### 生成後のカスタマイズ

1. RPG Maker MZで開く
2. マップを手動調整
3. イベントを追加・編集
4. 独自のアセットを追加
5. プラグイン導入

### チーム開発への展開

```bash
# 1. ベースゲーム生成
npx rpgmaker-mz-mcp auto-create "/team/project" "concept"

# 2. Git初期化
cd /team/project
git init
git add .
git commit -m "Initial autonomous generation"

# 3. チームで分担開発
# - プログラマー: イベント・スクリプト
# - アーティスト: アセット差し替え
# - デザイナー: バランス調整
```

---

## 📊 パフォーマンス最適化

### 高速生成モード

```bash
npx rpgmaker-mz-mcp auto-create "/path" "concept" \
  --length short \
  --no-assets \
  --no-optimize
```

⏱️ 所要時間: ~30秒

### 最高品質モード

```bash
npx rpgmaker-mz-mcp auto-create "/path" "concept" \
  --length long \
  --characters 10 \
  --enemies 30 \
  --tilesets 5
```

⏱️ 所要時間: ~10-15分

---

## 🎓 学習リソース

- [WORKFLOWS.md](./WORKFLOWS.md) - ワークフロー例
- [CLAUDE_CODE_INSTRUCTIONS.md](./CLAUDE_CODE_INSTRUCTIONS.md) - Claude Code統合ガイド
- [README.md](./README.md) - 全機能ドキュメント

---

**🎮 さあ、今すぐあなたのRPGを作りましょう！**

```bash
npx rpgmaker-mz-mcp auto-create "/games/MyFirstRPG" "your awesome game concept here"
```
