# resources/pdfjs について

このディレクトリには [pdf.js](https://github.com/mozilla/pdf.js)（Mozilla, Apache License 2.0）の
ビルド済みリファレンスビューア一式を同梱しています。

- ソース: https://github.com/mozilla/pdf.js
- タグ  : v5.4.624 （※下記「バージョン選定について」を参照）
- ビルド: `npm install && npx gulp generic`（pdf.js リポジトリ同梱の公式ビルドタスク）
- ライセンス: Apache License 2.0（同梱の LICENSE ファイルを参照）

Strollon (LGPL-3.0) はこのディレクトリのファイルを一切改変せず、
strollon-pdf:// スキームハンドラー (pdf_viewer.py) 経由で静的配信するだけです。

## バージョン選定について（重要）

最新の pdf.js（v6.0.227 以降）は内部で `Map.prototype.getOrInsertComputed`
（TC39 "Upsert" 提案。2026年1月のTC39会議で Stage 4 / 標準入り、
V8への実装は Chrome 145 前後）をフォールバックなしで直接使用しており、
これより前のV8を積んだ環境では

```
Uncaught (in promise) TypeError: this[#methodPromises].getOrInsertComputed is not a function
Uncaught (in promise) ReferenceError: Cannot access 'firstPagePromise' before initialization
```

のようなエラーで**ビューアが一切動作しません**。

QtWebEngine 6.11.x のベースChromiumは 140 系であり、上記の新機能には未対応です
（参考: https://wiki.qt.io/QtWebEngine/ChromiumVersions ）。
そのため本プロジェクトでは `getOrInsertComputed` を一切使用していないことを
ソースレベルで確認済みの **v5.4.624**（2026-02-01リリース）を採用しています。
v5.5.207 以降（2026-03-01〜）はこの新APIを使い始めているため、
当面はそれより新しいバージョンに安易に差し替えないでください。

QtWebEngineのバージョンを上げてベースChromiumが新しくなった場合（目安として
Chromium 145以降）は、より新しい pdf.js に切り替えても問題ない可能性があります。
切り替え前には `grep -c getOrInsertComputed build/pdf.mjs` 等で
未対応APIが使われていないか必ず確認してください。

## 更新方法

```bash
git clone --depth 1 --branch vX.Y.Z https://github.com/mozilla/pdf.js.git
cd pdf.js
PUPPETEER_SKIP_DOWNLOAD=true npm install   # Puppeteerのバイナリ取得をスキップ
npx gulp generic
# build/generic/ の中身（web/, build/, LICENSE）で
# このディレクトリを丸ごと置き換える
```

置き換え後は web/viewer.html → ../build/pdf.mjs などの相対パス構成が
維持されていることを確認してください（strollon-pdf://viewer/ 配下で
web/ と build/ を兄弟ディレクトリとして配信する設計になっています）。
