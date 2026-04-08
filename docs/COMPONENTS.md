# COMPONENTS.md — コンポーネント設計

## ディレクトリ構成

```
src/
├── components/
│   ├── auth/
│   │   ├── LoginForm.jsx          # ログインフォーム
│   │   ├── RegisterForm.jsx       # 新規登録フォーム
│   │   └── AuthGuard.jsx          # 認証チェックラッパー
│   │
│   ├── dashboard/
│   │   ├── Dashboard.jsx          # メインダッシュボード
│   │   ├── PropertyCard.jsx       # 物件カード（一覧表示）
│   │   └── PropertyList.jsx       # 物件一覧
│   │
│   ├── editor/
│   │   ├── PropertyEditor.jsx     # メインエディター（全体管理）
│   │   ├── sections/
│   │   │   ├── SectionA.jsx       # 基本情報
│   │   │   ├── SectionB.jsx       # 交通アクセス
│   │   │   ├── SectionC.jsx       # 土地情報
│   │   │   ├── SectionD.jsx       # 建物情報
│   │   │   ├── SectionE.jsx       # マンション専用
│   │   │   ├── SectionF.jsx       # 法令制限
│   │   │   ├── SectionG.jsx       # 借地条件
│   │   │   ├── SectionH.jsx       # 周辺環境
│   │   │   ├── SectionI.jsx       # 学区
│   │   │   └── SectionJ.jsx       # 備考
│   │   ├── MediaUploader.jsx      # 画像アップロード（全スロット）
│   │   └── DesignPanel.jsx        # カラー・フォント設定
│   │
│   ├── preview/
│   │   ├── MaisokuPreview.jsx     # A4プレビュー（Template1）
│   │   ├── templates/
│   │   │   └── Template1.jsx      # テンプレート1レイアウト
│   │   └── PDFExporter.jsx        # PDF出力ボタン・ロジック
│   │
│   └── profile/
│       └── ProfileEditor.jsx      # エージェントプロフィール設定
│
├── hooks/
│   ├── useAuth.js                 # 認証状態管理
│   ├── useProperty.js             # 物件CRUD操作
│   ├── useProfile.js              # プロフィール取得・更新
│   ├── useMediaUpload.js          # 画像アップロード
│   └── useAutoFit.js              # テキスト自動フィット
│
├── lib/
│   ├── supabase.js                # Supabaseクライアント初期化
│   ├── sectionVisibility.js       # 物件種別→セクション表示ルール
│   └── pdfExport.js               # html2pdf設定・エクスポート関数
│
└── styles/
    ├── globals.css                # グローバルスタイル
    └── print.css                  # 印刷・PDF用スタイル
```

---

## 主要コンポーネント詳細

### PropertyEditor.jsx
メインのフォーム画面。左ペインにフォーム、右ペインにライブプレビュー。

**状態管理:**
```javascript
const [propertyData, setPropertyData] = useState({...}) // 全フィールド
const [designSettings, setDesignSettings] = useState({
  brandColor: '#e87722',
  fontStyle: 'gothic',
  emphasisFields: {}
})
const [mediaFiles, setMediaFiles] = useState({
  k1: null, k2: null, k3: null, k4: null, k5: null, k6: null
})
```

**セクション表示ロジック:**
```javascript
import { getSectionVisibility } from '../lib/sectionVisibility'
const visibility = getSectionVisibility(propertyData.property_type)
// returns: { C: true, D: true, E: false, F: true, ... }
```

---

### sectionVisibility.js
物件種別に基づいてどのセクションを表示するか返すユーティリティ。

```javascript
export const PROPERTY_TYPES = {
  USED_HOUSE: '中古戸建',
  NEW_HOUSE: '新築戸建',
  MANSION: 'マンション',
  LAND: '土地',
  COMMERCIAL: '事業用'
}

export function getSectionVisibility(propertyType) {
  const base = { A: true, B: true, H: true, J: true, K: true, L: true }

  switch(propertyType) {
    case PROPERTY_TYPES.MANSION:
      return { ...base, C: false, D: true, E: true, F: false, G: false, I: true }
    case PROPERTY_TYPES.LAND:
      return { ...base, C: true, D: false, E: false, F: true, G: true, I: false }
    case PROPERTY_TYPES.COMMERCIAL:
      return { ...base, C: true, D: true, E: false, F: true, G: true, I: false }
    default: // 中古戸建・新築戸建
      return { ...base, C: true, D: true, E: false, F: true, G: true, I: true }
  }
}

// D5は複数階の場合のみ
export function showD5(floor1, floor2) {
  return floor1 && floor2
}
```

---

### Template1.jsx
A4サイズのHTMLレイアウト。このコンポーネントがそのままPDFになる。

**レイアウト実装:**
```jsx
<div className="maisoku-page" style={{ width: '210mm', minHeight: '297mm' }}>

  {/* ヘッダー行 */}
  <div className="grid grid-cols-[38%_12%_50%]">

    {/* 左カラム上段 */}
    <div className="left-top">
      <PropertyTypeBadge />     {/* A1 */}
      <PropertyTitle />          {/* A2 - 大 */}
      <AccessList />             {/* B */}
      <PriceDisplay />           {/* A4 - 特大・ブランドカラー */}
    </div>

    {/* 中央カラム上段: メイン写真 */}
    <div className="col-span-1">
      <ImageSlot slot="k1" />
    </div>

    {/* 右カラム上段: G借地 or 任意ボックス */}
    <div>
      {showG && <LeaseholdBox />}
    </div>

  </div>

  {/* コンテンツ行 */}
  <div className="grid grid-cols-[38%_12%_50%]">

    {/* 左カラム: 物件概要 */}
    <div className="left-main" ref={leftColumnRef}>
      <AddressSection />         {/* A3 */}
      {visibility.C && <LandSection />}
      {visibility.D && <BuildingSection />}
      {visibility.E && <MansionSection />}
      {visibility.F && <LegalSection />}
      <NotesSection />           {/* J */}
    </div>

    {/* 中カラム: H/I */}
    <div className="middle-main">
      <SurroundingsSection />    {/* H */}
      {showI && <SchoolSection />} {/* I */}
    </div>

    {/* 右カラム: 地図・写真2 */}
    <div className="right-main">
      <ImageSlot slot="k5" />    {/* 地図 */}
      <ImageSlot slot="k2" />    {/* 写真2 optional */}
    </div>

  </div>

  {/* フッター */}
  <CompanyFooter />              {/* L - 全幅 */}

</div>
```

---

### useAutoFit.js
左カラムのオーバーフローを検知してフォントサイズを自動縮小。

```javascript
export function useAutoFit(ref) {
  const [fontSize, setFontSize] = useState(100)
  const STEPS = [100, 95, 90, 85]
  const [overflow, setOverflow] = useState(false)

  useEffect(() => {
    if (!ref.current) return
    const el = ref.current
    let fitted = false

    for (const size of STEPS) {
      el.style.fontSize = `${size}%`
      if (el.scrollHeight <= el.clientHeight) {
        setFontSize(size)
        setOverflow(false)
        fitted = true
        break
      }
    }

    if (!fitted) {
      setOverflow(true)
    }
  }, [ref])

  return { fontSize, overflow, setFontSize }
}
```

---

### PDFExporter.jsx
html2pdf.jsを使ってTemplate1コンポーネントをPDFに変換。

```javascript
import html2pdf from 'html2pdf.js'

export async function exportToPDF(elementRef, filename) {
  const options = {
    margin: [8, 8, 8, 8],         // mm
    filename: filename,
    image: { type: 'jpeg', quality: 0.95 },
    html2canvas: {
      scale: 2,
      useCORS: true,
      letterRendering: true
    },
    jsPDF: {
      unit: 'mm',
      format: 'a4',
      orientation: 'portrait'
    }
  }

  await html2pdf().set(options).from(elementRef.current).save()
}
```

---

## ページ構成（React Router）

```
/                    → ダッシュボード（要認証）
/login               → ログイン
/register            → 新規登録
/profile             → プロフィール設定
/property/new        → 新規物件作成
/property/:id/edit   → 物件編集
/property/:id/preview → プレビュー・PDF出力
```

---

*Phase 1対象設計 — 2026年4月*
