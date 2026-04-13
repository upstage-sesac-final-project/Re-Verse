# 🤖 Claude Code でRPG Maker MZ MCPを使う

## 📋 セットアップインストラクション

### 1. MCPサーバー設定

Claude Code の設定ファイル (`~/.claude/config.json` or Claude Desktop設定) に追加:

```json
{
  "mcpServers": {
    "rpgmaker-mz": {
      "command": "node",
      "args": ["/path/to/rpgmaker-mz-mcp/dist/index.js"],
      "env": {
        "GEMINI_API_KEY": "your-gemini-api-key-here"
      }
    }
  }
}
```

### 2. 環境変数

```bash
export GEMINI_API_KEY="your-gemini-api-key"
```

### 3. 確認

Claude Codeを再起動して、MCPツールが利用可能か確認:
- Tools パネルに `rpgmaker-mz` ツールが表示されるはず

---

## 🎮 基本ワークフロー

### ワークフロー1: ゼロからゲーム作成

```
User: "ファンタジーRPGを作りたい"

Claude Code実行順序:
1. create_project
   - project_path: "/path/to/MyFantasyRPG"
   - game_title: "Fantasy Adventure"

2. generate_and_implement_scenario
   - project_path: "/path/to/MyFantasyRPG"
   - theme: "medieval fantasy with dragons"
   - style: "epic"
   - length: "medium"

3. generate_and_implement_battle_system
   - project_path: "/path/to/MyFantasyRPG"
   - difficulty: "normal"
   - battleType: "traditional"
   - enemyCount: 10

4. generate_quest_system
   - project_path: "/path/to/MyFantasyRPG"
   - questCount: 5
   - theme: "fantasy adventure"

5. analyze_project_structure
   - project_path: "/path/to/MyFantasyRPG"

完成！
```

### ワークフロー2: 既存プロジェクト拡張

```
User: "既存のプロジェクトに新しいマップを追加"

Claude Code実行順序:
1. list_projects
   - directory: "/path/to/projects"

2. create_map
   - project_path: "/path/to/existing/project"
   - map_id: 10
   - name: "Hidden Cave"
   - width: 25
   - height: 20

3. add_event
   - project_path: "/path/to/existing/project"
   - map_id: 10
   - event_id: 1
   - name: "Treasure Chest"
   - x: 12
   - y: 10

4. add_event_command
   - project_path: "/path/to/existing/project"
   - map_id: 10
   - event_id: 1
   - page_index: 0
   - code: 125  # Show message
   - parameters: ["You found a treasure!"]
```

### ワークフロー3: AI画像生成

```
User: "キャラクターの画像を生成して"

Claude Code実行順序:
1. generate_asset
   - project_path: "/path/to/project"
   - asset_type: "character"
   - prompt: "brave knight with silver armor and red cape, pixel art"
   - filename: "Knight.png"

2. generate_asset
   - project_path: "/path/to/project"
   - asset_type: "face"
   - prompt: "knight face with multiple expressions"
   - filename: "Knight_Face.png"

3. generate_asset
   - project_path: "/path/to/project"
   - asset_type: "enemy"
   - prompt: "fierce dragon boss"
   - filename: "Dragon.png"
```

### ワークフロー4: プロジェクト最適化

```
User: "プロジェクトを最適化して"

Claude Code実行順序:
1. analyze_performance
   - project_path: "/path/to/project"

2. optimize_assets
   - project_path: "/path/to/project"
   - assetTypes: ["images", "audio"]
   - quality: 85
   - removeUnused: true

3. get_project_size
   - project_path: "/path/to/project"

最適化完了！
```

### ワークフロー5: 翻訳・ローカライゼーション

```
User: "ゲームを英語に翻訳"

Claude Code実行順序:
1. translate_project
   - project_path: "/path/to/project"
   - target_language: "English"

2. translate_project
   - project_path: "/path/to/project"
   - target_language: "Chinese"

多言語対応完了！
```

---

## 🎯 高度なワークフロー

### ワークフロー6: 完全自動ゲーム生成

```markdown
User: "サイバーパンク探偵ストーリーのRPGを完全自動で作って"

Claude Code実行:
1. create_project
2. generate_and_implement_scenario (theme: cyberpunk detective)
3. generate_and_implement_battle_system (difficulty: normal)
4. generate_quest_system (questCount: 8)
5. generate_asset_batch (キャラクター×3, 敵×5)
6. generate_dialogue_tree (主要NPC用)
7. auto_balance_stats (difficulty: normal)
8. analyze_performance
9. generate_project_context (ドキュメント生成)

→ 10分でプレイ可能なRPG完成！
```

### ワークフロー7: データ駆動開発

```
User: "既存のゲームを分析して似たゲームを作って"

Claude Code実行:
1. analyze_project_structure (元プロジェクト)
2. extract_game_design_patterns (パターン抽出)
3. generate_scenario_variations (3バリエーション生成)
4. ユーザーに選択させる
5. 選択されたシナリオで新プロジェクト作成
```

---

## 💡 Claude Codeプロンプト例

### 例1: シンプル
```
"fantasy RPGを作って。主人公は勇者、敵はドラゴン"
```

### 例2: 詳細指定
```
"以下の仕様でRPGを作成:
- テーマ: スチームパンク
- 長さ: 短編 (1-2時間)
- 難易度: 簡単
- 主人公: 発明家
- 特徴: パズル要素重視"
```

### 例3: 段階的開発
```
"まずプロジェクトを作成して、
次に町のマップを作って、
NPCを3人配置して、
それぞれに会話イベントを設定して"
```

### 例4: 既存プロジェクト編集
```
"MyRPGプロジェクトを開いて、
Map003に新しいボスイベントを追加して、
ボスのステータスをバランス調整して、
勝利時に伝説の剣を入手できるようにして"
```

---

## 🔧 便利なClaude Codeコマンド

### プロジェクト情報取得
```
"プロジェクトの構造を教えて"
→ analyze_project_structure

"どんなマップがある?"
→ list_maps

"プラグインは何が入ってる?"
→ list_plugins
```

### トラブルシューティング
```
"ゲームが重い"
→ analyze_performance → 最適化提案

"未使用のアセットを削除して"
→ optimize_assets (removeUnused: true)

"データベースのエラーをチェック"
→ read_project_info → validate
```

### バックアップ・バージョン管理
```
"現在の状態を保存"
→ create_snapshot (message: "Chapter 1 complete")

"バックアップを作成"
→ create_backup (backupDir: "/backups")

"Gitで管理開始"
→ init_version_control
```

---

## 📊 Claude Code統合のベストプラクティス

### 1. 段階的開発
- 一度に全部やらない
- プロジェクト作成 → マップ → イベント → テスト の順

### 2. 頻繁なバックアップ
- 重要な変更前に `create_snapshot`
- 定期的に `create_backup`

### 3. AI生成の活用
- シナリオは複数バリエーション生成して比較
- アセットはバッチ生成で効率化

### 4. パフォーマンス監視
- 定期的に `analyze_performance`
- 推奨事項を実施

### 5. ドキュメント化
- `generate_project_context` でコンテキスト生成
- 将来の自分・チームのために

---

## 🎓 学習リソース

### Claude Codeで学ぶRPG Maker MZ
```
"RPG Maker MZの基本を教えて"
→ 公式ガイド参照 + サンプル生成

"イベントコマンド一覧"
→ 主要コマンド解説 + 使用例

"プラグインの使い方"
→ プラグイン検索 + インストール + 設定例
```

### 実践的なチュートリアル
```
"チュートリアル用の簡単なゲームを作って"
→ 基本システムの実装例

"よくあるバグと対処法"
→ デバッグ支援

"最適化のコツ"
→ パフォーマンステクニック
```

---

## 🚀 次のステップ

1. **今すぐ試す**:
   ```
   "テストプロジェクトを作成して、簡単なマップを1つ追加"
   ```

2. **本格開発**:
   ```
   "自分のゲームアイデアを説明 → 完全自動生成"
   ```

3. **カスタマイズ**:
   ```
   "生成されたゲームを自分好みに調整"
   ```

4. **公開**:
   ```
   "ゲームをエクスポートして配布準備"
   ```

**Claude Code + RPG Maker MZ MCPで、誰でもRPGクリエイター！🎮✨**
