#!/usr/bin/env bash
set -e

VERSION="${1:?バージョン番号を指定してください（例: 1.0.2.0）}"
ARCH="${2:-amd64}"                                  # .deb向け: amd64 / arm64 等
RPM_ARCH="$([ "${ARCH}" = amd64 ] && echo x86_64 || echo "${ARCH}")"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APPDIR="$ROOT_DIR/Strollon.AppDir"
BIN_DEST="$APPDIR/usr/bin/Strollon"
APPIMAGETOOL="$SCRIPT_DIR/appimagetool-x86_64.AppImage"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
NUITKA_OUTPUT="$ROOT_DIR/Strollon.bin"

APP_NAME="strollon"                                 # コマンド名・パッケージ名
BIN_NAME="Strollon"                                 # AppDir/usr/bin/Strollon と同じ
INSTALL_PREFIX="/opt/Strollon"                      # AppImageと同じ自己完結
MAINTAINER="ABATBeliever <abatbeliever@outlook.jp>" # 開発者表記
URL="https://abatbeliever.net"                      # 開発元
LICENSE="LGPL"                                      # ライセンス（RPM specのLicense:欄用の文字列）
DESCRIPTION="Strollon WebBrowser"

# ---------------------------------------------------------------------
# 出力ディレクトリ構成
# ---------------------------------------------------------------------
# 以前は生成物を全てROOT_DIR直下に平置きしていたが、形式ごとに
# ディレクトリを分けて配布しやすくする。
#   <ARCH>-bin/AppImage/  ... Strollon-x64.AppImage 一式
#   <ARCH>-bin/deb/       ... .deb 一式
#   <ARCH>-bin/rpm/       ... .rpm 一式
#   <ARCH>-bin/tarball/   ... .tar.xz 一式
DIST_DIR="$ROOT_DIR/${ARCH}-bin"
DIST_APPIMAGE="$DIST_DIR/AppImage"
DIST_DEB="$DIST_DIR/deb"
DIST_RPM="$DIST_DIR/rpm"
DIST_TARBALL="$DIST_DIR/tarball"
mkdir -p "$DIST_APPIMAGE" "$DIST_DEB" "$DIST_RPM" "$DIST_TARBALL"

APPIMAGE_OUTPUT="$DIST_APPIMAGE/Strollon-x64.AppImage"

# 各出力ディレクトリに同梱するドキュメント（LICENSE変数とは別名にして
# 上のRPM spec用文字列と衝突しないようにしている）
LICENSE_FILE="$ROOT_DIR/LICENSE"
RELEASE_NOTE_FILE="$ROOT_DIR/ReleaseNote.txt"
README_FILE="$ROOT_DIR/README.TXT"
for _doc in "$LICENSE_FILE" "$RELEASE_NOTE_FILE" "$README_FILE"; do
    if [ ! -f "$_doc" ]; then
        echo "[ERROR] 同梱予定のドキュメントが見つかりません: $_doc" >&2
        exit 1
    fi
done

# 各出力ディレクトリに LICENSE / ReleaseNote.txt / README.TXT をコピーする
copy_release_docs() {
    local dest="$1"
    cp "$LICENSE_FILE" "$dest/LICENSE"
    cp "$RELEASE_NOTE_FILE" "$dest/ReleaseNote.txt"
    cp "$README_FILE" "$dest/README.TXT"
}

echo "======================================================================"
echo "[INFO] Strollon Linux ビルド開始  (version=$VERSION, arch=$ARCH)"
echo "======================================================================"
echo "[INFO] SCRIPT_DIR : $SCRIPT_DIR"
echo "[INFO] ROOT_DIR   : $ROOT_DIR"
echo "[INFO] APPDIR     : $APPDIR"
echo "[INFO] 出力先     : $DIST_DIR/{AppImage,deb,rpm,tarball}/"

# ---------------------------------------------------------------------
# [1/5] AppImageTool の準備
# ---------------------------------------------------------------------
echo ""
echo "---- [1/5] AppImageTool の準備 ----"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo "[INFO] AppImageTool が無いため取得します: $APPIMAGETOOL_URL"
    curl -fsSL "$APPIMAGETOOL_URL" -o "$APPIMAGETOOL"
    chmod +x "$APPIMAGETOOL"
    echo "[INFO] 取得完了: $APPIMAGETOOL"
else
    echo "[INFO] AppImageTool は取得済みです: $APPIMAGETOOL"
fi

# ---------------------------------------------------------------------
# [2/5] Nuitkaビルド
# ---------------------------------------------------------------------
echo ""
echo "---- [2/5] Nuitkaでバイナリをビルド中...（数分かかります）----"
cd "$ROOT_DIR"
uv run nuitka \
    --standalone --onefile \
    --enable-plugin=pyside6 \
    --company-name=ABATBeliever \
    --product-name="Strollon WebBrowser" \
    --file-description="Strollon WebBrowser" \
    --include-data-dir=resources/pdfjs=resources/pdfjs \
    Strollon.py
echo "[INFO] Nuitkaビルド完了"

if [ ! -f "$NUITKA_OUTPUT" ]; then
    echo "[ERROR] Failed to find Strollon.bin: $NUITKA_OUTPUT" >&2
    exit 1
fi
echo "[INFO] ビルド成果物: $NUITKA_OUTPUT ($(du -h "$NUITKA_OUTPUT" | cut -f1))"

# ---------------------------------------------------------------------
# [3/5] AppImage化
# ---------------------------------------------------------------------
echo ""
echo "---- [3/5] AppImageを作成中... ----"
mkdir -p "$APPDIR/usr/bin"
echo "[INFO] バイナリをAppDirにコピー中: $BIN_DEST"
cp "$NUITKA_OUTPUT" "$BIN_DEST"
echo "[INFO] chmod..."
chmod +x "$APPDIR/AppRun"
chmod +x "$BIN_DEST"
chmod +x "$APPDIR/app.png"
echo "[INFO] appimagetool 実行中..."
cd "$ROOT_DIR"
ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "$APPIMAGE_OUTPUT"
chmod +x "$APPIMAGE_OUTPUT"
echo "[INFO] AppImage: $APPIMAGE_OUTPUT ($(du -h "$APPIMAGE_OUTPUT" | cut -f1))"

# ---- ここから先（tarball/.deb/.rpm）は AppDir 内の .desktop / app.png を流用 ----
DESKTOP_SRC="$(find "$APPDIR" -maxdepth 1 -name '*.desktop' | head -n1 || true)"
ICON_SRC="$APPDIR/app.png"
if [ -z "$DESKTOP_SRC" ] || [ ! -f "$ICON_SRC" ]; then
    echo "[ERROR] Strollon.AppDir に .desktop または app.png が見つかりません" >&2
    exit 1
fi
echo "[INFO] desktop source: $DESKTOP_SRC"
echo "[INFO] icon source   : $ICON_SRC"

# AppImage単体では .desktop がどこにも自動配置されないため、README記載の
# 手動デスクトップ統合手順で使えるよう .desktop / アイコンをそのまま同梱する
# （Exec= はまだ "Strollon %U" のままなので、ユーザー側でAppImageの実際の
# パスに書き換えてもらう前提。README.TXT の手順を参照）。
cp "$DESKTOP_SRC" "$DIST_APPIMAGE/Strollon.desktop"
cp "$ICON_SRC" "$DIST_APPIMAGE/Strollon.png"
copy_release_docs "$DIST_APPIMAGE"
echo "[INFO] AppImage用の同梱物（.desktop/アイコン/ドキュメント）を配置しました: $DIST_APPIMAGE"

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT
echo "[INFO] work dir: $WORK_DIR"

# ---------------------------------------------------------------------
# [4/5] ポータブルtarball
# ---------------------------------------------------------------------
echo ""
echo "---- [4/5] tarball を作成中... ----"
TARBALL_ROOT="$WORK_DIR/tarball/${APP_NAME}-${VERSION}"
echo "[INFO] ステージング中: $TARBALL_ROOT"
mkdir -p "$TARBALL_ROOT"
cp "$NUITKA_OUTPUT" "$TARBALL_ROOT/$BIN_NAME"
chmod +x "$TARBALL_ROOT/$BIN_NAME"
cp "$DESKTOP_SRC" "$TARBALL_ROOT/strollon.desktop"
cp "$ICON_SRC" "$TARBALL_ROOT/strollon.png"

echo "[INFO] install.sh / uninstall.sh を生成中..."
cat > "$TARBALL_ROOT/install.sh" <<INSTALL_EOF
#!/usr/bin/env bash
# Strollon インストールスクリプト
#   ./install.sh          システム全体にインストール（要root, /opt配下）
#   ./install.sh --user   現在のユーザーのみ（~/.local配下, rootなしでOK）
set -e
HERE="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
BIN_NAME="$BIN_NAME"

if [ "\${1:-}" = "--user" ]; then
    PREFIX="\$HOME/.local/share/Strollon"
    BIN_DIR="\$HOME/.local/bin"
    APPS_DIR="\$HOME/.local/share/applications"
    ICON_DIR="\$HOME/.local/share/icons/hicolor/256x256/apps"
else
    if [ "\$(id -u)" -ne 0 ]; then
        echo "システム全体へのインストールには root 権限が必要です。" >&2
        echo "root なしでインストールする場合は ./install.sh --user を使ってください。" >&2
        exit 1
    fi
    PREFIX="/opt/Strollon"
    BIN_DIR="/usr/local/bin"
    APPS_DIR="/usr/share/applications"
    ICON_DIR="/usr/share/icons/hicolor/256x256/apps"
fi

echo "==> \$PREFIX にインストールします"
mkdir -p "\$PREFIX" "\$BIN_DIR" "\$APPS_DIR" "\$ICON_DIR"
cp "\$HERE/\$BIN_NAME" "\$PREFIX/\$BIN_NAME"
chmod +x "\$PREFIX/\$BIN_NAME"
ln -sf "\$PREFIX/\$BIN_NAME" "\$BIN_DIR/strollon"

sed "s#^Exec=.*#Exec=\$PREFIX/\$BIN_NAME %U#; s#^Icon=.*#Icon=\$ICON_DIR/strollon.png#" \\
    "\$HERE/strollon.desktop" > "\$APPS_DIR/strollon.desktop"
cp "\$HERE/strollon.png" "\$ICON_DIR/strollon.png"

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "\$APPS_DIR" || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f "\$(dirname "\$(dirname "\$ICON_DIR")")" || true

echo "==> 完了。'strollon' コマンド、またはアプリ一覧から起動できます。"
INSTALL_EOF
chmod +x "$TARBALL_ROOT/install.sh"

cat > "$TARBALL_ROOT/uninstall.sh" <<UNINSTALL_EOF
#!/usr/bin/env bash
set -e
if [ "\${1:-}" = "--user" ]; then
    PREFIX="\$HOME/.local/share/Strollon"
    rm -f "\$HOME/.local/bin/strollon"
    rm -f "\$HOME/.local/share/applications/strollon.desktop"
    rm -f "\$HOME/.local/share/icons/hicolor/256x256/apps/strollon.png"
else
    if [ "\$(id -u)" -ne 0 ]; then
        echo "システム全体からのアンインストールには root 権限が必要です。" >&2
        exit 1
    fi
    PREFIX="/opt/Strollon"
    rm -f /usr/local/bin/strollon
    rm -f /usr/share/applications/strollon.desktop
    rm -f /usr/share/icons/hicolor/256x256/apps/strollon.png
fi
rm -rf "\$PREFIX"
echo "==> アンインストール完了"
UNINSTALL_EOF
chmod +x "$TARBALL_ROOT/uninstall.sh"

TARBALL_OUT="$DIST_TARBALL/${APP_NAME}-${VERSION}-linux-${ARCH}.tar.xz"
echo "[INFO] tar.xz に圧縮中: $TARBALL_OUT"
tar -C "$WORK_DIR/tarball" -cJf "$TARBALL_OUT" "${APP_NAME}-${VERSION}"
echo "[INFO] tarball: $TARBALL_OUT ($(du -h "$TARBALL_OUT" | cut -f1))"
copy_release_docs "$DIST_TARBALL"

# ---------------------------------------------------------------------
# [5/5] .deb / .rpm
# ---------------------------------------------------------------------
echo ""
echo "---- [5/5] .deb / .rpm を作成中... ----"
echo "[INFO] パッケージ内容をステージング中..."
PKG_ROOT="$WORK_DIR/pkgroot"
mkdir -p "$PKG_ROOT$INSTALL_PREFIX"
cp "$NUITKA_OUTPUT" "$PKG_ROOT$INSTALL_PREFIX/$BIN_NAME"
chmod +x "$PKG_ROOT$INSTALL_PREFIX/$BIN_NAME"

mkdir -p "$PKG_ROOT/usr/share/applications"
sed "s#^Exec=.*#Exec=$INSTALL_PREFIX/$BIN_NAME %U#; s#^Icon=.*#Icon=$APP_NAME#" \
    "$DESKTOP_SRC" > "$PKG_ROOT/usr/share/applications/strollon.desktop"

mkdir -p "$PKG_ROOT/usr/share/icons/hicolor/256x256/apps"
cp "$ICON_SRC" "$PKG_ROOT/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png"

mkdir -p "$PKG_ROOT/usr/bin"
ln -sf "$INSTALL_PREFIX/$BIN_NAME" "$PKG_ROOT/usr/bin/$APP_NAME"
echo "[INFO] ステージング完了: $PKG_ROOT"

echo "[INFO] .deb をビルド中 (dpkg-deb)..."
DEB_ROOT="$WORK_DIR/deb_root"
cp -a "$PKG_ROOT" "$DEB_ROOT"
mkdir -p "$DEB_ROOT/DEBIAN"
INSTALLED_SIZE="$(du -sk "$PKG_ROOT" | cut -f1)"
cat > "$DEB_ROOT/DEBIAN/control" <<EOF
Package: $APP_NAME
Version: $VERSION
Section: web
Priority: optional
Architecture: $ARCH
Installed-Size: $INSTALLED_SIZE
Maintainer: $MAINTAINER
Homepage: $URL
Description: $DESCRIPTION
EOF
DEB_OUT="$DIST_DEB/${APP_NAME}_${VERSION}_${ARCH}.deb"
dpkg-deb --build --root-owner-group "$DEB_ROOT" "$DEB_OUT"
echo "[INFO] .deb: $DEB_OUT ($(du -h "$DEB_OUT" | cut -f1))"
copy_release_docs "$DIST_DEB"

echo "[INFO] .rpm をビルド中 (rpmbuild)..."
RPM_TOPDIR="$WORK_DIR/rpmbuild"
mkdir -p "$RPM_TOPDIR"/{SPECS,RPMS,BUILD,BUILDROOT,SOURCES,SRPMS}
SPEC="$RPM_TOPDIR/SPECS/${APP_NAME}.spec"
cat > "$SPEC" <<EOF
Name: $APP_NAME
Version: $VERSION
Release: 1
Summary: $DESCRIPTION
License: $LICENSE
URL: $URL
BuildArch: $RPM_ARCH

%description
$DESCRIPTION

%install
mkdir -p %{buildroot}
cp -a $PKG_ROOT/. %{buildroot}/

%files
$INSTALL_PREFIX/$BIN_NAME
/usr/bin/$APP_NAME
/usr/share/applications/strollon.desktop
/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png
EOF
echo "[INFO] rpmbuild 実行中...（ログ: $WORK_DIR/rpmbuild.log）"
rpmbuild -bb --define "_topdir $RPM_TOPDIR" "$SPEC" > "$WORK_DIR/rpmbuild.log" 2>&1
BUILT_RPM="$(find "$RPM_TOPDIR/RPMS" -name '*.rpm' | head -n1)"
RPM_OUT="$DIST_RPM/$(basename "$BUILT_RPM")"
cp "$BUILT_RPM" "$RPM_OUT"
echo "[INFO] .rpm: $RPM_OUT ($(du -h "$RPM_OUT" | cut -f1))"
copy_release_docs "$DIST_RPM"

echo ""
echo "======================================================================"
echo "[INFO] Build Success! 生成物一覧 ($DIST_DIR):"
echo "  - AppImage/$(basename "$APPIMAGE_OUTPUT")  (+ Strollon.desktop, Strollon.png, LICENSE, ReleaseNote.txt, README.TXT)"
echo "  - tarball/$(basename "$TARBALL_OUT")  (+ LICENSE, ReleaseNote.txt, README.TXT)"
echo "  - deb/$(basename "$DEB_OUT")  (+ LICENSE, ReleaseNote.txt, README.TXT)"
echo "  - rpm/$(basename "$RPM_OUT")  (+ LICENSE, ReleaseNote.txt, README.TXT)"
echo "======================================================================"
