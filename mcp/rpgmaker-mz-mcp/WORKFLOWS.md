# 🔄 RPG Maker MZ MCP ワークフローガイド

## 📚 目次
1. [クイックスタート](#クイックスタート)
2. [基本ワークフロー](#基本ワークフロー)
3. [高度なワークフロー](#高度なワークフロー)
4. [プロダクションワークフロー](#プロダクションワークフロー)
5. [トラブルシューティング](#トラブルシューティング)

---

## 🚀 クイックスタート

### 最速でゲームを作る (5分)

```typescript
// Step 1: プロジェクト作成
create_project({
  project_path: "/tmp/QuickGame",
  game_title: "My First RPG"
})

// Step 2: AIでゲーム生成
generate_and_implement_scenario({
  project_path: "/tmp/QuickGame",
  theme: "fantasy adventure",
  style: "simple",
  length: "short"
})

// Step 3: 完成！
// /tmp/QuickGame/Game.rpgproject をRPG Maker MZで開く
```

---

## 🎯 基本ワークフロー

### ワークフロー1: 手動でゲームを構築

```typescript
// 1. プロジェクト作成
const project = await create_project({
  project_path: "/games/MyRPG",
  game_title: "Hero's Journey"
})

// 2. クラス作成
await add_class({
  project_path: "/games/MyRPG",
  id: 1,
  name: "Warrior"
})

// 3. アクター作成
await add_actor({
  project_path: "/games/MyRPG",
  id: 1,
  name: "Hero"
})

// 4. マップ作成
await create_map({
  project_path: "/games/MyRPG",
  map_id: 2,
  name: "Starting Village",
  width: 20,
  height: 15
})

// 5. NPCイベント追加
await add_event({
  project_path: "/games/MyRPG",
  map_id: 2,
  event_id: 1,
  name: "Village Elder",
  x: 10,
  y: 10
})

// 6. 会話設定
await add_event_command({
  project_path: "/games/MyRPG",
  map_id: 2,
  event_id: 1,
  page_index: 0,
  code: 101,  // Show Text
  parameters: ["", 0, 0, 2]
})

await add_event_command({
  project_path: "/games/MyRPG",
  map_id: 2,
  event_id: 1,
  page_index: 0,
  code: 401,  // Text
  parameters: ["Welcome, brave hero!"]
})
```

### ワークフロー2: AI支援開発

```typescript
// 1. プロジェクト作成
await create_project({
  project_path: "/games/AIGame",
  game_title: "AI Generated RPG"
})

// 2. AIでシナリオ生成
const scenario = await generate_scenario({
  project_path: "/games/AIGame",
  theme: "sci-fi space opera",
  style: "epic",
  length: "medium"
})

// 3. シナリオ実装
await implement_scenario({
  project_path: "/games/AIGame",
  scenario: scenario.scenario
})

// 4. バトルシステム生成
await generate_and_implement_battle_system({
  project_path: "/games/AIGame",
  difficulty: "normal",
  battleType: "traditional",
  enemyCount: 15
})

// 5. アセット生成
await generate_asset_batch({
  requests: [
    {
      project_path: "/games/AIGame",
      asset_type: "character",
      prompt: "space marine protagonist",
      filename: "Hero.png"
    },
    {
      project_path: "/games/AIGame",
      asset_type: "enemy",
      prompt: "alien creature",
      filename: "Alien.png"
    }
  ]
})
```

### ワークフロー3: データ駆動開発

```typescript
// 1. 既存プロジェクト分析
const analysis = await analyze_project_structure({
  project_path: "/games/ExistingGame"
})

// 2. パターン抽出
const patterns = await extract_game_design_patterns({
  project_path: "/games/ExistingGame"
})

// 3. 新プロジェクト作成（似た構造）
await create_project({
  project_path: "/games/NewGame",
  game_title: "Spiritual Successor"
})

// 4. パターンを応用して生成
await generate_and_implement_scenario({
  project_path: "/games/NewGame",
  theme: patterns.commonThemes[0],
  style: patterns.gameStyle,
  length: "medium"
})
```

---

## 🎨 高度なワークフロー

### ワークフロー4: マルチレイヤー開発

```typescript
// Layer 1: コアシステム
await create_project(...)
await generate_and_implement_scenario(...)

// Layer 2: バトルシステム
await generate_and_implement_battle_system(...)

// Layer 3: クエストシステム
await generate_quest_system({
  project_path: "/games/ComplexRPG",
  questCount: 10,
  theme: "epic fantasy"
})

// Layer 4: ダイアログシステム
for (const npc of importantNPCs) {
  await generate_dialogue_tree({
    character: npc.name,
    context: npc.role,
    depth: 3
  })
}

// Layer 5: バランス調整
await auto_balance_stats({
  project_path: "/games/ComplexRPG",
  difficulty: "normal"
})

// Layer 6: 最適化
await optimize_assets({
  project_path: "/games/ComplexRPG",
  assetTypes: ["all"],
  quality: 90,
  removeUnused: true
})
```

### ワークフロー5: 多言語対応ゲーム

```typescript
// 1. 日本語版作成
await create_project({
  project_path: "/games/MultiLang",
  game_title: "世界の冒険"
})

await generate_and_implement_scenario({
  project_path: "/games/MultiLang",
  theme: "world adventure",
  style: "friendly",
  length: "medium"
})

// 2. 英語翻訳
await translate_project({
  project_path: "/games/MultiLang",
  target_language: "English"
})

// 3. 中国語翻訳
await translate_project({
  project_path: "/games/MultiLang",
  target_language: "Chinese"
})

// 4. 韓国語翻訳
await translate_project({
  project_path: "/games/MultiLang",
  target_language: "Korean"
})

// 5. 各言語バージョンをエクスポート
// 実装予定...
```

### ワークフロー6: イテレーティブ開発

```typescript
// Iteration 1: プロトタイプ
await create_project(...)
const v1 = await generate_and_implement_scenario({
  length: "short"
})
await create_snapshot({
  project_path: "/games/Iterative",
  message: "v1: Initial prototype"
})

// Iteration 2: コア機能追加
await generate_and_implement_battle_system(...)
await create_snapshot({
  message: "v2: Battle system added"
})

// Iteration 3: コンテンツ拡張
await generate_quest_system(...)
await create_snapshot({
  message: "v3: Quest system added"
})

// Iteration 4: 最適化
await optimize_assets(...)
await auto_balance_stats(...)
await create_snapshot({
  message: "v4: Optimized and balanced"
})

// Iteration 5: リリース準備
await analyze_performance(...)
const size = await get_project_size(...)
await create_backup({
  project_path: "/games/Iterative",
  backup_dir: "/backups"
})
```

---

## 🏭 プロダクションワークフロー

### ワークフロー7: チーム開発

```typescript
// 1. プロジェクトセットアップ
await create_project(...)
await init_version_control({
  project_path: "/team/project"
})

// 2. 基本システム実装（プログラマー）
await generate_and_implement_scenario(...)
await create_snapshot({
  message: "Core systems implemented"
})

// 3. アセット作成（アーティスト）
await generate_asset_batch({
  requests: characterAssets
})
await create_snapshot({
  message: "Character assets added"
})

// 4. バランス調整（ゲームデザイナー）
await auto_balance_stats(...)
await analyze_performance(...)
await create_snapshot({
  message: "Balance pass 1"
})

// 5. ローカライゼーション（翻訳者）
await translate_project({ target_language: "English" })
await translate_project({ target_language: "Chinese" })
await create_snapshot({
  message: "Localization complete"
})

// 6. 最終最適化
await optimize_assets({
  quality: 95,
  removeUnused: true
})
await create_snapshot({
  message: "Release candidate"
})
```

### ワークフロー8: A/Bテスト用バリエーション

```typescript
// Base version
await create_project({
  project_path: "/games/Base",
  game_title: "Test Game"
})

// Generate 3 variations
const variations = await generate_scenario_variations({
  project_path: "/games/Base",
  theme: "fantasy",
  style: "adventure",
  length: "short",
  count: 3
})

// Create separate projects for each
for (let i = 0; i < variations.length; i++) {
  const varPath = `/games/Variation${i + 1}`

  await create_project({
    project_path: varPath,
    game_title: `Test Game V${i + 1}`
  })

  await implement_scenario({
    project_path: varPath,
    scenario: variations[i].scenario
  })
}

// Analyze each
for (let i = 1; i <= 3; i++) {
  const analysis = await analyze_project_structure({
    project_path: `/games/Variation${i}`
  })

  console.log(`Variation ${i}:`, analysis)
}
```

### ワークフロー9: プラグインエコシステム

```typescript
// 1. 基本プロジェクト
await create_project(...)

// 2. プラグイン導入
await install_plugin({
  project_path: "/games/PluginGame",
  plugin_source: "https://example.com/BattleCore.js",
  plugin_name: "BattleCore.js",
  enabled: true
})

await install_plugin({
  project_path: "/games/PluginGame",
  plugin_name: "VisuMZ_0_CoreEngine",  // From registry
  enabled: true
})

// 3. プラグイン確認
const plugins = await list_installed_plugins({
  project_path: "/games/PluginGame"
})

// 4. プラグイン管理
await enable_plugin({
  project_path: "/games/PluginGame",
  plugin_name: "BattleCore",
  enabled: false
})

await uninstall_plugin({
  project_path: "/games/PluginGame",
  plugin_name: "UnusedPlugin"
})
```

---

## 🔧 トラブルシューティング

### 問題1: パフォーマンスが悪い

```typescript
// 診断
const perf = await analyze_performance({
  project_path: "/games/SlowGame"
})

// 推奨事項に従って最適化
await optimize_assets({
  project_path: "/games/SlowGame",
  quality: 85,
  removeUnused: true
})

// 再確認
const newPerf = await analyze_performance({
  project_path: "/games/SlowGame"
})
```

### 問題2: データ破損

```typescript
// バックアップから復元
await create_backup({
  project_path: "/games/Corrupted",
  backup_dir: "/backups"
})

// または前のコミットに戻る
// (git経由で手動操作)
```

### 問題3: バランスが悪い

```typescript
// 自動バランス調整
await auto_balance_stats({
  project_path: "/games/Unbalanced",
  difficulty: "normal"
})

// バトルシステム再生成
await generate_and_implement_battle_system({
  project_path: "/games/Unbalanced",
  difficulty: "normal",
  enemyCount: 10
})
```

---

## 📈 推奨ワークフロー

### 小規模プロジェクト (1-5時間プレイ)
```
1. create_project
2. generate_and_implement_scenario (length: "short")
3. generate_asset_batch (5-10 assets)
4. optimize_assets
5. 完成
```

### 中規模プロジェクト (5-20時間プレイ)
```
1. create_project
2. generate_and_implement_scenario (length: "medium")
3. generate_and_implement_battle_system
4. generate_quest_system
5. generate_asset_batch (20-30 assets)
6. auto_balance_stats
7. optimize_assets
8. translate_project (if needed)
9. 完成
```

### 大規模プロジェクト (20+ 時間プレイ)
```
1. create_project + init_version_control
2. イテレーティブ開発 (複数スプリント)
3. チーム協働
4. 定期的なバックアップ・スナップショット
5. 段階的なアセット生成
6. 継続的なバランス調整
7. 多言語対応
8. パフォーマンステスト
9. 最終最適化
10. リリース
```

---

**これらのワークフローで、あなたのRPG開発が10倍速く！🚀**
