-- 001_create_profiles.sql
CREATE TABLE profiles (
  id                UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW(),
  company_name      TEXT NOT NULL,
  franchise_name    TEXT,
  logo_url          TEXT,
  company_address   TEXT NOT NULL,
  company_phone     TEXT NOT NULL,
  company_fax       TEXT,
  company_email     TEXT NOT NULL,
  agent_name        TEXT NOT NULL,
  agent_phone       TEXT,
  license_number    TEXT NOT NULL,
  association       TEXT,
  brand_color       TEXT DEFAULT '#e87722',
  font_style        TEXT DEFAULT 'gothic'
);

-- 002_create_properties.sql
CREATE TABLE properties (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW(),
  agent_id          UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  property_type     TEXT NOT NULL,
  title             TEXT NOT NULL,
  address           TEXT NOT NULL,
  price             NUMERIC,
  price_note        TEXT,
  access            JSONB DEFAULT '[]',
  land_area_m2      NUMERIC,
  land_area_tsubo   NUMERIC,
  land_right        TEXT,
  land_category     TEXT,
  road_access       TEXT,
  build_condition   TEXT,
  built_date        TEXT,
  structure         TEXT,
  floor1_area       NUMERIC,
  floor2_area       NUMERIC,
  total_floor_area  NUMERIC,
  floor_plan        TEXT,
  mansion_info      JSONB,
  city_plan         TEXT,
  zoning            TEXT,
  fire_zone         TEXT,
  height_district   TEXT,
  building_ratio    NUMERIC,
  floor_ratio       NUMERIC,
  other_laws        TEXT,
  leasehold         JSONB,
  surroundings      JSONB DEFAULT '[]',
  school_district   JSONB,
  lifeline          TEXT,
  current_status    TEXT,
  delivery          TEXT,
  rebuild           TEXT,
  notes             TEXT,
  emphasis_fields   JSONB DEFAULT '{}',
  template_id       TEXT DEFAULT 'template1',
  is_archived       BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_properties_agent_id ON properties(agent_id);
CREATE INDEX idx_properties_created_at ON properties(created_at DESC);

-- 003_create_media_files.sql
CREATE TABLE media_files (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  property_id   UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  agent_id      UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  slot          TEXT NOT NULL,
  file_url      TEXT NOT NULL,
  file_name     TEXT,
  file_size     INTEGER,
  mime_type     TEXT,
  sort_order    INTEGER DEFAULT 0
);

CREATE INDEX idx_media_property_id ON media_files(property_id);

-- 004_rls_policies.sql
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "自分のプロフィールのみ" ON profiles
  FOR ALL USING (auth.uid() = id);

ALTER TABLE properties ENABLE ROW LEVEL SECURITY;
CREATE POLICY "自分の物件のみ" ON properties
  FOR ALL USING (auth.uid() = agent_id);

ALTER TABLE media_files ENABLE ROW LEVEL SECURITY;
CREATE POLICY "自分のメディアのみ" ON media_files
  FOR ALL USING (auth.uid() = agent_id);
