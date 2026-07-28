【ソフト名称】Strollon WebBrowser
【バージョン】1.0.0.0
【最終更新日】2026/07/28
【 著 作 者 】ABATBeliever
【 動作環境 】Windows10+ / Linux (Wayland/X11)
【 推奨環境 】Windows11+ / Linux (Wayland)
【ライセンス】LGPL v3
________________________________________________________________________________________________
■ 概要

Strollon は、縦タブ対応のシンプルな モダン Web ブラウザです。
Pythonベースで、Chromium エンジンを採用する LGPLライセンスの下で、
過去のInternetStrollerシリーズの設計思想と、VELA Praxisの拡張性が合流。
________________________________________________________________________________________________
■ 主な機能

・縦タブパネル
　　縦タブでタブ管理。並び替えやタブの複製なども。
・シークレットタブ
　　履歴・Cookie を保存しないシークレットモードを「タブ単位で」利用できます。
・プライバシー・ファースト
　　Adblockライブラリと EasyList による広告ブロックと、Do Not Track に対応。
・テーマ対応
　　Default / Dark / Sakura など、複数テーマを設定から選択できます。
・Chromium エンジン
　　Qt WebEngine（Chromium ベース）により、現代的な Web サイトを快適に閲覧できます。
・最小構成
　　わかりやすく、洗練された軽量システムデザイン。
・XDG準拠
　　XDG Base Directory 仕様に準拠したインストール、またはポータブル運用もOK。
・互換性の維持
　　同じメジャーバージョン内では設定・データの互換性を維持します。
________________________________________________________________________________________________
■ 技術仕様

開発言語        : Python 3.12
UIフレームワーク: PySide6
レンダリング    : Qt WebEngine
ビルド方法      : Nuitka (+AppImageTool)
________________________________________________________________________________________________
■ ライセンス

LGPL v3 License に基づいて公開されています。
ただし、ソースコードにおける resources/pdfjs 以下など、Apache2.0ライセンスの成果物を含みます。
詳細は、LICENSEファイルを参照ください。
________________________________________________________________________________________________
■ 免責事項

- 本ソフトウェアは「現状のまま」提供されます。  
- 本ソフトウェアの使用による損害について、一切責任を負いません。 
________________________________________________________________________________________________
■ 追加の依存関係

◇LinuxのX11セッションをお使いの場合、以下のモジュールが必要です。
　 (Debian系の場合) sudo apt install libxcb-cursor0 fuse3

◇WSL2でお使いの場合、以下のモジュールが必要です。
　 (Debian系の場合) sudo apt install \
  fuse3 \
  libnspr4 \
  libnss3 \
  libatk1.0-0 \
  libatk-bridge2.0-0 \
  libcups2 \
  libxcomposite1 \
  libxdamage1 \
  libxfixes3 \
  libxrandr2 \
  libgbm1 \
  libasound2t64 \
  libxkbcommon0 \
  libxkbfile1 \
  libgtk-3-0 \
  libgl1 \
  libgl1 \
  libglx-mesa0 \
  libegl1 \
  libglu1-mesa \
  mesa-utils

さらに文字化けが起こった場合は、
  sudo apt install fonts-noto-cjk
  sudo fc-cache -fv
________________________________________________________________________________________________
■ お問い合わせ・貢献

不具合報告、要望、コントリビュート等は以下にご連絡ください。
GitHub               : [https://github.com/ABATBeliever/Strollon]
公式ページ           : [https://abatbeliever.net/software/bin/Strollon]
バグ・脆弱性ビューワ : [https://abatbeliever.net/bugs/?q=Strollon]
