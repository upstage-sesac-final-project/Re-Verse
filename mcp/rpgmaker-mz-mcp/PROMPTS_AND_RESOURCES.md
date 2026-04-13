# 🎯 プロンプト＆リソース管理ガイド

MCPツールをより柔軟に活用するためのプロンプトテンプレートとリソース管理システム

---

## 🌟 概要

### リソース管理システムとは

**リソース** = ゲーム開発で再利用可能なデータ

- テンプレート（キャラクター設定、マップレイアウトなど）
- アセット情報（画像の説明、使用箇所）
- シナリオデータ（ストーリー、会話）
- カスタムデータ（任意のJSON）

### プロンプトテンプレートとは

**プロンプト** = AI生成時に使う指示文のテンプレート

- 変数プレースホルダー: `{{theme}}`, `{{style}}`
- リソース参照: `{{resource:resource_id}}`
- 再利用可能

---

## 🚀 クイックスタート

### 1. リソースを登録

```typescript
await register_resource({
  project_path: "/path/to/project",
  resource_id: "hero_template",
  resource_type: "template",
  name: "標準的な勇者キャラクター",
  description: "ファンタジーRPGの主人公テンプレート",
  content: {
    name: "勇者",
    class: "戦士",
    initialLevel: 1,
    traits: ["勇敢", "正義感が強い"]
  },
  tags: ["character", "hero", "template"]
});
```

### 2. プロンプトテンプレートを登録

```typescript
await register_prompt_template({
  project_path: "/path/to/project",
  prompt_id: "create_hero_dialogue",
  name: "勇者の会話生成",
  description: "勇者キャラクターの会話を生成",
  template: `Create dialogue for a hero character:
Name: {{heroName}}
Personality: {{personality}}
Situation: {{situation}}

Character template: {{resource:hero_template}}

Generate 3-5 dialogue lines that fit the character.`,
  variables: ["heroName", "personality", "situation"],
  resource_refs: ["hero_template"]
});
```

### 3. プロンプトを実行

```typescript
await execute_prompt({
  project_path: "/path/to/project",
  prompt_id: "create_hero_dialogue",
  variables: {
    heroName: "アレックス",
    personality: "勇敢で正義感が強い",
    situation: "村長から依頼を受ける"
  }
});
```

**結果**:
```
Create dialogue for a hero character:
Name: アレックス
Personality: 勇敢で正義感が強い
Situation: 村長から依頼を受ける

Character template: {
  "name": "勇者",
  "class": "戦士",
  ...
}

Generate 3-5 dialogue lines that fit the character.
```

---

## 📚 実践例

### 例1: キャラクターテンプレート管理

```typescript
// 1. 複数のキャラクタータイプをリソース登録
await register_resource({
  project_path: "/path/to/project",
  resource_id: "warrior_template",
  resource_type: "template",
  name: "戦士テンプレート",
  content: {
    class: "戦士",
    baseHP: 100,
    baseMP: 20,
    weapons: ["sword", "axe"],
    skills: ["強撃", "防御"]
  },
  tags: ["character", "warrior"]
});

await register_resource({
  project_path: "/path/to/project",
  resource_id: "mage_template",
  resource_type: "template",
  name: "魔法使いテンプレート",
  content: {
    class: "魔法使い",
    baseHP: 60,
    baseMP: 100,
    weapons: ["staff"],
    skills: ["ファイア", "サンダー", "ブリザド"]
  },
  tags: ["character", "mage"]
});

// 2. リソース一覧取得
await list_resources({
  project_path: "/path/to/project",
  tags: ["character"]
});

// 結果: warrior_template, mage_template が返される
```

---

### 例2: シナリオ生成プロンプト

```typescript
// 1. ゲーム世界設定をリソース登録
await register_resource({
  project_path: "/path/to/project",
  resource_id: "world_setting",
  resource_type: "data",
  name: "世界設定",
  content: {
    worldName: "エルドラシア王国",
    era: "中世ファンタジー",
    threats: ["古代のドラゴン", "魔王軍"],
    factions: ["王国騎士団", "魔法使いギルド", "盗賊ギルド"]
  },
  tags: ["world", "setting"]
});

// 2. シナリオ生成プロンプトを登録
await register_prompt_template({
  project_path: "/path/to/project",
  prompt_id: "generate_chapter",
  name: "チャプター生成",
  template: `Create a story chapter for:
World: {{resource:world_setting}}
Chapter Number: {{chapterNumber}}
Theme: {{theme}}
Main Quest: {{mainQuest}}

Generate:
- Chapter title
- Story synopsis (200-300 words)
- 3-5 key events
- Character developments
- Next chapter hook`,
  variables: ["chapterNumber", "theme", "mainQuest"],
  resource_refs: ["world_setting"]
});

// 3. 実行
await execute_prompt({
  project_path: "/path/to/project",
  prompt_id: "generate_chapter",
  variables: {
    chapterNumber: 1,
    theme: "王女の誘拐",
    mainQuest: "王女を救出せよ"
  }
});
```

---

### 例3: アセット生成プロンプト

```typescript
// 1. アートスタイルをリソース登録
await register_resource({
  project_path: "/path/to/project",
  resource_id: "art_style",
  resource_type: "asset",
  name: "ゲームアートスタイル",
  content: {
    style: "ピクセルアート",
    colorPalette: ["#8B4513", "#228B22", "#4169E1", "#FFD700"],
    resolution: "16bit風",
    reference: "スーパーファミコン時代のRPG"
  },
  tags: ["art", "style"]
});

// 2. アセット生成プロンプト
await register_prompt_template({
  project_path: "/path/to/project",
  prompt_id: "generate_character_sprite",
  name: "キャラクタースプライト生成",
  template: `Generate character sprite:
Art Style: {{resource:art_style}}
Character: {{characterName}}
Description: {{description}}
Role: {{role}}

Technical requirements:
- Size: 144x192 pixels
- Format: PNG
- Grid: 3x4 (walking animation)
- Transparent background`,
  variables: ["characterName", "description", "role"],
  resource_refs: ["art_style"]
});
```

---

## 🔧 高度な使い方

### パターン1: マルチステッププロンプト

```typescript
// Step 1: ベースストーリー生成
await register_prompt_template({
  project_path: "/path/to/project",
  prompt_id: "step1_base_story",
  name: "ベースストーリー",
  template: "Create base story for: {{concept}}",
  variables: ["concept"]
});

// Step 2: ストーリーを元にキャラクター生成
await register_prompt_template({
  project_path: "/path/to/project",
  prompt_id: "step2_characters",
  name: "キャラクター生成",
  template: `Based on story: {{resource:generated_story}}
Generate main characters.`,
  variables: [],
  resource_refs: ["generated_story"]
});

// Step 3: マップ生成
await register_prompt_template({
  project_path: "/path/to/project",
  prompt_id: "step3_maps",
  name: "マップ生成",
  template: `Story: {{resource:generated_story}}
Characters: {{resource:generated_characters}}
Generate maps.`,
  variables: [],
  resource_refs: ["generated_story", "generated_characters"]
});
```

### パターン2: バリエーション生成

```typescript
// ベーステンプレート
await register_resource({
  project_path: "/path/to/project",
  resource_id: "enemy_base",
  resource_type: "template",
  name: "敵キャラベース",
  content: {
    dropRate: 0.3,
    expMultiplier: 1.0,
    goldMultiplier: 1.0
  }
});

// 難易度別プロンプト
await register_prompt_template({
  project_path: "/path/to/project",
  prompt_id: "enemy_by_difficulty",
  name: "難易度別敵生成",
  template: `Generate enemy:
Base template: {{resource:enemy_base}}
Name: {{enemyName}}
Difficulty: {{difficulty}}

Adjust stats based on difficulty (easy: 0.8x, normal: 1.0x, hard: 1.5x)`,
  variables: ["enemyName", "difficulty"],
  resource_refs: ["enemy_base"]
});
```

---

## 📊 リソース管理

### リソース一覧表示

```typescript
// 全リソース
await list_resources({
  project_path: "/path/to/project"
});

// タイプでフィルター
await list_resources({
  project_path: "/path/to/project",
  type: "template"
});

// タグでフィルター
await list_resources({
  project_path: "/path/to/project",
  tags: ["character", "hero"]
});
```

### リソース取得

```typescript
const result = await getResource({
  project_path: "/path/to/project",
  resource_id: "hero_template"
});

if (result.success) {
  console.log(result.resource.content);
}
```

---

## 💡 ベストプラクティス

### 1. リソースIDの命名規則

```
✅ 良い例:
- hero_template
- world_setting_chapter1
- art_style_fantasy

❌ 悪い例:
- temp1
- data
- abc123
```

### 2. リソースの粒度

```
✅ 適切:
- キャラクタータイプごとにテンプレート
- チャプターごとに設定
- テーマごとにアートスタイル

❌ 粗すぎ:
- 全キャラクターを1つのリソースに
- ゲーム全体の設定を1つに
```

### 3. プロンプトの再利用性

```typescript
// ✅ 再利用しやすい
template: "Generate {{objectType}} for {{theme}} with {{style}} style"

// ❌ 固定値が多すぎる
template: "Generate warrior character for fantasy theme with epic style"
```

---

## 🎯 実践ワークフロー

### ワークフロー: RPGシリーズ開発

```typescript
// Phase 1: 共通リソース登録
await register_resource({
  project_path: "/project",
  resource_id: "series_world",
  resource_type: "data",
  name: "シリーズ世界観",
  content: { ... }
});

// Phase 2: 作品1
await execute_prompt({
  project_path: "/project1",
  prompt_id: "generate_story",
  variables: {
    title: "第1章",
    worldData: "{{resource:series_world}}"
  }
});

// Phase 3: 作品2（同じ世界観）
await execute_prompt({
  project_path: "/project2",
  prompt_id: "generate_story",
  variables: {
    title: "第2章",
    worldData: "{{resource:series_world}}"  // 同じリソース再利用
  }
});
```

---

## 📖 デフォルトプロンプト

プロジェクト作成時に以下のプロンプトテンプレートが自動登録されます：

### 1. scenario_generation
シナリオ生成用テンプレート

**変数**:
- theme
- style
- length
- mapCount
- characterCount

### 2. asset_generation
アセット生成用テンプレート

**変数**:
- assetType
- description
- style
- specs

### 3. quest_generation
クエスト生成用テンプレート

**変数**:
- questCount
- theme
- difficulty
- objectiveCount

---

## 🔍 データベース検索

### 敵キャラ検索

```typescript
await search_database({
  project_path: "/path/to/project",
  types: ["enemy"],
  name_contains: "dragon"
});
```

### レベル範囲でアクター検索

```typescript
await search_database({
  project_path: "/path/to/project",
  types: ["actor"],
  id_min: 1,
  id_max: 10
});
```

---

## 🎨 アセット分析

### 全アセット分析

```typescript
await analyze_assets({
  project_path: "/path/to/project"
});
```

**生成レポート**:
- 総アセット数
- 使用中/未使用アセット
- タイプ別統計
- 最適化推奨事項
- 大きなファイルリスト

---

## 💼 実用例

### 例1: テンプレートベース開発

```typescript
// 1. NPC会話テンプレート
await register_resource({
  project_path: "/project",
  resource_id: "npc_greeting",
  resource_type: "template",
  name: "NPC挨拶テンプレート",
  content: {
    greetings: [
      "ようこそ、{{villageNa}}へ！",
      "こんにちは、旅の方。",
      "お困りのことは？"
    ]
  }
});

// 2. 使用
const resource = await getResource({
  project_path: "/project",
  resource_id: "npc_greeting"
});

// 3. イベントに適用
for (const greeting of resource.resource.content.greetings) {
  await add_event_command({
    ...
    parameters: [greeting.replace("{{villageName}}", "エルドリア村")]
  });
}
```

### 例2: バリエーション生成

```typescript
// ベース敵テンプレート
await register_resource({
  project_path: "/project",
  resource_id: "slime_base",
  resource_type: "data",
  name: "スライムベース",
  content: {
    hp: 50,
    attack: 10,
    defense: 5,
    exp: 10,
    gold: 5
  }
});

// バリエーションプロンプト
await register_prompt_template({
  project_path: "/project",
  prompt_id: "slime_variant",
  name: "スライム亜種生成",
  template: `Base: {{resource:slime_base}}
Variant: {{variantName}}
Element: {{element}}

Create variant with:
- {{element}} elemental damage
- Adjusted stats for difficulty {{difficulty}}`,
  variables: ["variantName", "element", "difficulty"],
  resource_refs: ["slime_base"]
});

// 生成
await execute_prompt({
  project_path: "/project",
  prompt_id: "slime_variant",
  variables: {
    variantName: "Fire Slime",
    element: "fire",
    difficulty: "hard"
  }
});
```

---

## 🎓 高度な活用

### パターン: コンテキスト継承

```typescript
// Chapter 1 の結果をリソース化
await register_resource({
  project_path: "/project",
  resource_id: "chapter1_result",
  resource_type: "scenario",
  name: "第1章の結果",
  content: {
    ending: "王女救出成功",
    charactersStatus: { ... },
    unlockedAreas: ["城下町", "森"]
  }
});

// Chapter 2 で前章の結果を参照
await register_prompt_template({
  project_path: "/project",
  prompt_id: "chapter2_story",
  name: "第2章ストーリー",
  template: `Previous chapter: {{resource:chapter1_result}}
New theme: {{theme}}

Continue the story...`,
  variables: ["theme"],
  resource_refs: ["chapter1_result"]
});
```

---

## 📋 MCPツール一覧（リソース＆プロンプト）

| ツール名 | 説明 |
|---------|------|
| `register_resource` | リソース登録 |
| `register_prompt_template` | プロンプトテンプレート登録 |
| `execute_prompt` | プロンプト実行 |
| `list_resources` | リソース一覧 |
| `search_database` | データベース検索 |
| `analyze_assets` | アセット分析 |

---

## 🔍 トラブルシューティング

### Q: リソースが見つからない

```bash
# レジストリファイル確認
cat /path/to/project/data/ResourceRegistry.json
```

### Q: プロンプトが正しく展開されない

変数名を確認：
```typescript
// ✅ 正しい
variables: ["theme", "style"]
// template: "Theme: {{theme}}, Style: {{style}}"

// ❌ 間違い
variables: ["theme"]
// template: "Theme: {{theme}}, Style: {{style}}"  // style が未定義
```

### Q: リソース参照が動作しない

リソースIDを確認：
```typescript
resource_refs: ["hero_template"]  // ← 登録したIDと一致するか
```

---

## 🎉 まとめ

リソース＆プロンプト管理により：

- ✅ **再利用性向上**: テンプレートを使い回し
- ✅ **一貫性保持**: 世界観・設定を統一
- ✅ **効率化**: 同じ作業の繰り返しを削減
- ✅ **柔軟性**: 変数で簡単にバリエーション生成
- ✅ **拡張性**: カスタムデータを自由に管理

**プロンプト＆リソースでRPG開発がさらに10倍効率化！🚀**

---

## 📚 関連ドキュメント

- [README.md](./README.md) - 全機能
- [GETTING_STARTED.md](./GETTING_STARTED.md) - 初心者向け
- [WORKFLOWS.md](./WORKFLOWS.md) - ワークフロー例
- [MCP_TOOLS_GUIDE.md](./MCP_TOOLS_GUIDE.md) - ツール詳細
