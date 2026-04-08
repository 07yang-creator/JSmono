# フィールド表示条件ロジック

物件種別（A1）の選択値によって、各セクション・フィールドの表示/非表示を制御するロジックを定義する。

---

## 物件種別コード

| コード | 表示名 |
|---|---|
| `used_house` | 中古戸建 |
| `new_house` | 新築戸建 |
| `mansion` | マンション |
| `land` | 土地 |
| `commercial` | 事業用 |

---

## セクション別表示条件

### C. 土地情報
```
表示条件: A1 ∈ [used_house, new_house, land, commercial]
非表示条件: A1 = mansion
```

### D. 建物情報
```
表示条件: A1 ∈ [used_house, new_house, mansion, commercial]
非表示条件: A1 = land
```

### D5. 床面積合計
```
表示条件: D4（2階以上の床面積）が入力済みの場合のみ
ロジック: D4 !== null && D4 !== ''
```

### E. マンション専用情報
```
表示条件: A1 = mansion のみ
非表示条件: A1 ≠ mansion
```

### E5〜E8（管理費・修繕積立・管理会社・管理形態）
```
表示条件: A1 = mansion かつ エージェントが入力した場合
（任意項目のため、入力なしなら行非表示）
```

### F. 法令制限
```
表示条件: A1 ∈ [used_house, new_house, land, commercial]
非表示条件: A1 = mansion
```

### F1（都市計画）
```
表示条件: F セクション表示中 かつ 入力あり
必須: なし（optional）
```

### F3（防火指定）
```
表示条件: F セクション表示中 かつ 入力あり
必須: なし（optional）
```

### G. 借地条件
```
表示条件: 
  - A1 ∈ [used_house, new_house, land, commercial] かつ
  - エージェントが「借地条件を表示する」トグルをON
推奨トリガー: C3（土地権利）= 借地権 の場合に表示を促すヒント
非表示条件: A1 = mansion（マンションには適用しない）
```

### I. 学区
```
表示条件: エージェントが「学区を表示する」トグルをON
推奨条件: A1 ∈ [used_house, new_house, mansion]
非推奨（トグル非表示）: A1 ∈ [land, commercial]
```

---

## フィールド単位の表示条件

### B2, B3（交通アクセス2・3件目）
```
表示条件: 入力欄として常に表示（最大3件）
レイアウト表示: 入力ありの場合のみ印刷に反映
```

### C6（建築条件）
```
表示条件: C セクション表示中 かつ 入力あり
```

### D4（2階以上の床面積）
```
表示条件: D セクション表示中（常に入力欄として表示）
```

### D6（間取り）
```
表示条件: A1 ∈ [used_house, new_house, mansion] かつ 入力あり
```

### H2〜H8（周辺環境2〜8件目）
```
表示条件: 入力ありの場合のみ
最大件数: 8件
```

### J4（再建築）
```
表示条件: 入力あり かつ エージェントが表示を選択
```

### J5（その他備考）
```
表示条件: 入力あり
```

---

## UIロジック実装メモ

```javascript
// セクション表示判定関数（React実装例）
const sectionVisibility = (propertyType) => ({
  C: ['used_house', 'new_house', 'land', 'commercial'].includes(propertyType),
  D: ['used_house', 'new_house', 'mansion', 'commercial'].includes(propertyType),
  E: propertyType === 'mansion',
  F: ['used_house', 'new_house', 'land', 'commercial'].includes(propertyType),
  G: false, // エージェントのトグルで制御
  I: false, // エージェントのトグルで制御
});

// D5表示判定
const showD5 = (d4Value) => d4Value !== null && d4Value !== '';

// G表示推奨ヒント
const suggestG = (c3Value) => c3Value === '借地権';

// I表示推奨
const suggestI = (propertyType) => 
  ['used_house', 'new_house', 'mansion'].includes(propertyType);
```

---

## エージェントトグル一覧

フォーム上でエージェントがON/OFFできるセクション:

| トグル | デフォルト | 対象 |
|---|---|---|
| 借地条件を表示する | OFF | C3=借地権の場合ONを推奨 |
| 学区を表示する | OFF | 住居系でONを推奨 |
| 取引態様を表示する | ON | フッターに表示 |
| 手数料を表示する | ON | フッターに表示 |
