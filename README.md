# Strollon WebBrowser - インターネットを散歩しよう

![License](https://img.shields.io/badge/license-LGPLv3-blue.svg)
![Version](https://img.shields.io/badge/version-1.1.0.0-green.svg)
![Status](https://img.shields.io/badge/status-Stable-orange.svg)
![Language](https://img.shields.io/badge/Language-Python-yellow.svg)

<img width="1194" height="825" alt="スクリーンショット 2026-07-28 170724" src="https://github.com/user-attachments/assets/695c5c00-812c-4953-a31a-a6bd5a5b7533" />


---

## 概要

Strollon は、縦タブ対応のオープンでシンプルな Web ブラウザです。

Pythonベースで、Chromium エンジンを採用する LGPLライセンスの下、
過去の InternetStroller シリーズの設計思想と、VELA Praxis の拡張性を合流させた、新しいブラウザです。

---

## 入手・ダウンロード

[こちら](https://abatbeliever.net/software/bin/Strollon/)

---

## 主要機能

### 縦タブパネル
縦タブでタブ管理。並び替えやタブの複製なども。

### シークレットタブ
履歴・Cookie を保存しないシークレットモードを「タブ単位で」利用できます。

### プライバシー・ファースト
Adblockライブラリと EasyList による広告ブロックと、Do Not Track を搭載。

### テーマ対応
Default / Dark / Sakura など複数テーマを設定から利用できます。

### Chromium エンジン
Qt WebEngine (Chromium ベース) により現代的なサイトを快適に閲覧できます。

### 強固な結合
ポータブルと必要最小限の思想の ISMemoria と、VELA のモダン技術を結合。

### 最小構成
わかりやすく、洗練された軽量システムデザイン

### XDG準拠
XDGに準拠、またはポータブルもOK

<img width="1206" height="772" alt="image" src="https://github.com/user-attachments/assets/19bac84b-a6c2-4353-927d-ff5ade2ac2ad" />

---

## 動作環境・対応状況

| OS                         | アーキテクチャ | ディスプレイサーバー |対応状況|
|----------------------------|----------------|----------------------|--------|
| Windows 10 以降 (11 推奨)  | x64            | -                    | 対応済 |
| Linux                      | x64            | Wayland (推奨) / X11 | 対応済 |

---

## ライセンス

Strollon Browser は **GNU Lesser General Public License (LGPL) v3** に基づいて配布されています。
ただし、ソースコードにおける `resources/pdfjs` 以下など、Apache 2.0 ライセンスの成果物を含みます。
詳細は [LICENSE](./LICENSE) ファイルを参照ください。

---

## クレジット / サードパーティライブラリ

- Qt (Qt Company)
- QtAwesome
- QtWebEngine
- Adblock (adblock-rustベース)
- pdf.js (Mozilla)

各ライブラリのライセンスはそれぞれの配布元に準拠します。

---

## 不具合報告・貢献

不具合報告、要望、コントリビュート等は以下からお願いします。
- Issues : [GitHub Issues](https://github.com/ABATBeliever/Strollon/issues)
- バグ・脆弱性ビューワ : [https://abatbeliever.net/bugs/?q=Strollon](https://abatbeliever.net/bugs/?q=Strollon)

---

## 連絡先
- **作者:** ABATBeliever
- **公式ページ:** [https://abatbeliever.net/software/bin/Strollon](https://abatbeliever.net/software/bin/Strollon)
