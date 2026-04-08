# DATABASE.md — データベーススキーマ定義

## 使用DB: Supabase (PostgreSQL)

---

## テーブル一覧

1. `profiles` — エージェントプロフィール
2. `properties` — 物件情報
3. `media_files` — アップロード画像管理

---

## 1. profiles テーブル

エージェントの会社情報・ブランディング設定。
Supabase Authの `auth.users` と1:1で紐づく。

```sql
CREATE TABLE profiles (
  id            UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW(),

  -- L: 会社情報
  company_name        TEXT NOT NULL,          -- L1
  franchise_name      TEXT,                   -- L2
  logo_url            TEXT,                   -- L3 (Supabase Storageのパス)
  company_address     TEXT NOT NULL,          -- L4
  company_phone       TEXT NOT NULL,          -- L5
  company_fax         TEXT,                   -- L6
  company_email       TEXT NOT NULL,          -- L7
  agent_name          TEXT NOT NULL,          -- L8
  agent_phone         TEXT,                   -- L9
  license_number      TEXT NOT NULL,          -- L10
  association         TEXT,                   -- L11

  -- デザイン設定
  brand_color         TEXT DEFAULT '#e87722', -- HEXカラーコード
  font_style          TEXT DEFAULT 'gothic'   -- gothic / mincho / mixed
);
```

---

## 2. properties テーブル

物件ごとのすべての情報を格納。JSONBカラムを使い、
物件種別によって異なるセクション（C/D/E/F/G）を柔軟に保存。

```sql
CREATE TABLE properties (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW(),
  agent_id      UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,

  -- A: 基本情報
  property_type   TEXT NOT NULL,  -- 中古戸建/新築戸建/マンション/土地/事業用
  title           TEXT NOT NULL,
  address         TEXT NOT NULL,
  price           NUMERIC,
  price_note      TEXT,

  -- B: 交通アクセス (最大3件、JSONB配列)
  -- 例: [{"line":"JR総武線","station":"大久保駅","walk":7}, ...]
  access          JSONB DEFAULT '[]',

  -- C: 土地情報
  land_area_m2    NUMERIC,
  land_area_tsubo NUMERIC,
  land_right      TEXT,
  land_category   TEXT,
  road_access     TEXT,
  build_condition TEXT,

  -- D: 建物情報
  built_date      TEXT,
  structure       TEXT,
  floor1_area     NUMERIC,
  floor2_area     NUMERIC,
  total_floor_area NUMERIC,
  floor_plan      TEXT,

  -- E: マンション専用 (JSONB)
  -- 例: {"building_name":"○○マンション","floor":"3/10", ...}
  mansion_info    JSONB,

  -- F: 法令制限
  city_plan       TEXT,
  zoning          TEXT,
  fire_zone       TEXT,
  height_district TEXT,
  building_ratio  NUMERIC,
  floor_ratio     NUMERIC,
  other_laws      TEXT,

  -- G: 借地条件 (JSONB、任意)
  -- 例: {"start":"2026-02-01","end":"2056-01-31","type":"定期借地", ...}
  leasehold       JSONB,

  -- H: 周辺環境 (JSONB配列、最大8件)
  -- 例: [{"name":"スーパー","distance":"徒歩約1分"}, ...]
  surroundings    JSONB DEFAULT '[]',

  -- I: 学区 (JSONB、任意)
  -- 例: {"elementary":"淀橋第四小学校 徒歩約3分","junior":"新宿西戸山中学校 徒歩約16分"}
  school_district JSONB,

  -- J: 備考
  lifeline        TEXT,
  current_status  TEXT,
  delivery        TEXT,
  rebuild         TEXT,
  notes           TEXT,

  -- デザイン設定（物件ごとに上書き可能）
  emphasis_fields JSONB DEFAULT '{}',
  -- 例: {"A4": ["color","enlarged"], "C1": ["bold"]}

  -- 管理
  template_id     TEXT DEFAULT 'template1',
  is_archived     BOOLEAN DEFAULT FALSE
);

-- エージェントIDでの検索を高速化
CREATE INDEX idx_properties_agent_id ON properties(agent_id);
CREATE INDEX idx_properties_created_at ON properties(created_at DESC);
```

---

## 3. media_files テーブル

各物件にアップロードされた画像を管理。
実ファイルはSupabase Storageに保存し、URLをここで管理。

```sql
CREATE TABLE media_files (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  property_id   UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  agent_id      UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,

  slot          TEXT NOT NULL,
  -- K1: 外観写真メイン
  -- K2: 外観写真2
  -- K3: 外観写真3
  -- K4: 間取り図
  -- K5: 地図画像
  -- K6: その他・デコレーション

  file_url      TEXT NOT NULL,   -- Supabase StorageのパブリックURL
  file_name     TEXT,
  file_size     INTEGER,         -- bytes
  mime_type     TEXT,
  sort_order    INTEGER DEFAULT 0
);

CREATE INDEX idx_media_property_id ON media_files(property_id);
```

---

## Supabase Storage バケット設定

```
バケット名: maisoku-media
アクセス: 認証済みユーザーのみ書き込み可、読み取りはパブリック
```

フォルダ構造:
```
maisoku-media/
├── logos/
│   └── {agent_id}/logo.png
└── properties/
    └── {property_id}/
        ├── k1_main.jpg
        ├── k2.jpg
        ├── k5_map.jpg
        └── ...
```

---

## Row Level Security (RLS) ポリシー

```sql
-- profiles: 自分のプロフィールのみ読み書き可
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "自分のプロフィールのみ" ON profiles
  FOR ALL USING (auth.uid() = id);

-- properties: 自分の物件のみ読み書き可
ALTER TABLE properties ENABLE ROW LEVEL SECURITY;

CREATE POLICY "自分の物件のみ" ON properties
  FOR ALL USING (auth.uid() = agent_id);

-- media_files: 自分の物件の画像のみ
ALTER TABLE media_files ENABLE ROW LEVEL SECURITY;

CREATE POLICY "自分のメディアのみ" ON media_files
  FOR ALL USING (auth.uid() = agent_id);
```

---

## マイグレーションファイル

`supabase/migrations/` に以下の順で実行:

1. `001_create_profiles.sql`
2. `002_create_properties.sql`
3. `003_create_media_files.sql`
4. `004_rls_policies.sql`
5. `005_storage_bucket.sql`

---

*Phase 1対象スキーマ — 2026年4月*
