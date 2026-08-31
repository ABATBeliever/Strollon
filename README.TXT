【ソフト名称】Strollon WebBrowser
【バージョン】1.2.0.0
【最終更新日】2026/08/31
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
■ 既定のブラウザに設定する方法

◇Windowsでインストール版を利用する

① インストール時に、「Strollonを既定のブラウザの候補として登録する」にチェックを入れておきます。
　 ※チェックを入れていない場合や覚えていない場合は、1.2.0.0以降のインストーラーで
　 　上書きインストールしてください。設定や履歴は保持されます。

② Windowsの設定をいじります

　 1. Windows の「設定」→「アプリ」→「既定のアプリ」を開く
　 2. アプリ一覧から「Strollon WebBrowser」を探して選択する
　　  (見つからない場合は上部の検索欄に "Strollon" と入力)
　 3. 開いた画面で、.html / .htm / HTTP / HTTPS の項目を
　　　それぞれ Strollon に変更する
　　　(「既定のブラウザ」欄のボタンがある場合はこれでも構いません)
　 ※Strollonをアンインストールした場合、次回にそれらが発動した際に尋ねられます
　 ※Edge等に戻す場合は、2でそのブラウザを選択して同じことをします

◇Linuxで.deb、.rpmまたはtarball版を利用する

　インストール時点で必要な.desktopファイルは配置されているので、
　以下のコマンドを実行することで既定に設定できます。

　xdg-settings set default-web-browser strollon.desktop

　GNOMEの場合、以下のコマンドを使うこともできます。

　gio mime x-scheme-handler/http strollon.desktop
　gio mime x-scheme-handler/https strollon.desktop

　反映されない場合、再起動してください。

◇LinuxでAppImageを利用する

　AppImage版の場合、配布物に同封されている Strollon.desktop / strollon.png を使い、
　以下を実行してください。
　※このコマンドを実行した後は、AppImageを更新する場合に置き換える以外は
　　いじらないことを推奨します。

① 実際に置いたAppImageファイルの絶対パスを、変数に代入します。
　 
　APPIMAGE_PATH="○○/Strollon-x64.AppImage"

② 以下のコマンドを実行します。

　mkdir -p ~/.local/share/applications ~/.local/share/icons/hicolor/256x256/apps
　cp Strollon.png ~/.local/share/icons/hicolor/256x256/apps/strollon.png
　cp Strollon.desktop ~/.local/share/applications/strollon.desktop
　sed -i "s#^Exec=.*#Exec=$APPIMAGE_PATH %U#" ~/.local/share/applications/strollon.desktop
　update-desktop-database ~/.local/share/applications

③「Linuxで.deb、.rpmまたはtarball版を利用する」にあるコマンドを実行して既定に設定できます。

________________________________________________________________________________________________
■ お問い合わせ・貢献

不具合報告、要望、コントリビュート等は以下にご連絡ください。
GitHub               : [https://github.com/ABATBeliever/Strollon]
公式ページ           : [https://abatbeliever.net/software/bin/Strollon]
バグ・脆弱性ビューワ : [https://abatbeliever.net/bugs/?q=Strollon]
