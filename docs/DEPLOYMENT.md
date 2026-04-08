# DEPLOYMENT.md — デプロイ手順

## 必要なアカウント

- [Supabase](https://supabase.com) — 無料プランで開始可
- [Vercel](https://vercel.com) — 無料プランで開始可
- [GitHub](https://github.com) — ソースコード管理

---

## Step 1 — Supabaseプロジェクト作成

1. https://supabase.com にログイン
2. 「New Project」をクリック
3. プロジェクト名: `jsmono`、リージョン: `Northeast Asia (Tokyo)` を選択
4. データベースパスワードを設定（メモしておく）
5. 「Create new project」をクリック（約2分待つ）

### DBマイグレーション実行

Supabaseダッシュボードの「SQL Editor」を開き、以下のファイルを順番に実行:

```
supabase/migrations/001_create_profiles.sql
supabase/migrations/002_create_properties.sql
supabase/migrations/003_create_media_files.sql
supabase/migrations/004_rls_policies.sql
supabase/migrations/005_storage_bucket.sql
```

### Storageバケット作成

1. Supabaseダッシュボード → Storage → 「New bucket」
2. バケット名: `maisoku-media`
3. Public bucket: ✅ ON（画像をパブリックに表示するため）

### 環境変数を取得

Supabaseダッシュボード → Settings → API:
- `Project URL` → `NEXT_PUBLIC_SUPABASE_URL`
- `anon public key` → `NEXT_PUBLIC_SUPABASE_ANON_KEY`

---

## Step 2 — ローカル開発環境セットアップ

```bash
# リポジトリをクローン
git clone https://github.com/your-org/JSmono.git
cd JSmono

# 依存パッケージインストール
npm install

# 環境変数ファイル作成
cp .env.example .env.local
```

`.env.local` を編集:
```
NEXT_PUBLIC_SUPABASE_URL=https://xxxxxxxxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJxxxxxxxxxx...
```

```bash
# 開発サーバー起動
npm run dev
# → http://localhost:3000 で確認
```

---

## Step 3 — Vercelデプロイ

### GitHubとの連携

1. GitHubにコードをプッシュ:
```bash
git add .
git commit -m "Initial commit"
git push origin main
```

2. https://vercel.com にログイン
3. 「New Project」→ GitHubリポジトリ `JSmono` を選択
4. Framework Preset: `Vite` または `Create React App` を選択

### 環境変数設定

Vercelプロジェクト設定 → Environment Variables:

| Name | Value |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase Project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key |

5. 「Deploy」をクリック
6. 約2〜3分でデプロイ完了

---

## Step 4 — Supabase Auth設定

1. Supabaseダッシュボード → Authentication → URL Configuration
2. Site URL: `https://your-app.vercel.app` に設定
3. Redirect URLs に `https://your-app.vercel.app/**` を追加

---

## Step 5 — 動作確認チェックリスト

- [ ] トップページが表示される
- [ ] 新規登録ができる
- [ ] ログイン・ログアウトができる
- [ ] プロフィール設定が保存される
- [ ] 新規物件を作成・保存できる
- [ ] 画像アップロードができる
- [ ] プレビューが正しく表示される
- [ ] PDFが出力される
- [ ] 物件一覧に保存された物件が表示される
- [ ] 編集・複製・削除ができる

---

## 依存パッケージ一覧

```json
{
  "dependencies": {
    "react": "^18.x",
    "react-dom": "^18.x",
    "react-router-dom": "^6.x",
    "@supabase/supabase-js": "^2.x",
    "html2pdf.js": "^0.10.x",
    "tailwindcss": "^3.x"
  }
}
```

---

## トラブルシューティング

### 画像がPDFに表示されない
→ html2canvasの`useCORS: true`設定を確認。Supabase StorageのCORS設定でVercelドメインを許可する。

### 日本語フォントがPDFで文字化けする
→ `print.css` でNoto Sans JPをインポートし、`@font-face`で明示的に指定する。

### RLSエラーで保存できない
→ Supabase SQL EditorでRLSポリシーが正しく設定されているか確認。

---

## 本番運用メモ

- Supabase無料プランの制限: ストレージ1GB、DBサイズ500MB
- 本格運用時はProプラン（$25/月）を検討
- Vercel無料プランで通常の利用は十分

---

*Phase 1デプロイ手順 — 2026年4月*
