#!/usr/bin/env bash
set -e

echo "============================================"
echo " Strollon Development Kit for Linux"
echo "============================================"
echo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# ── 1. uv の確認 / インストール ──────────────────────────────
if ! command -v uv >/dev/null 2>&1; then
    echo "[INFO] uv not found. Installing..."
    curl -Ls https://astral.sh/uv/install.sh | sh
    echo "[INFO] uv installed. Reloading PATH..."
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv >/dev/null 2>&1; then
        echo "[CRITICAL] uv still not found after install."
        echo "           Please re-open your terminal and run this script again."
        exit 1
    fi
else
    echo "[INFO] $(uv --version) found."
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

# ── 2. pyproject.toml の確認 ─────────────────────────────────
if [ ! -f pyproject.toml ]; then
    echo "[CRITICAL] pyproject.toml not found."
    echo "           Please run this script from the project root."
    exit 1
fi

# ── 3. ビルド依存パッケージのインストール（distro検出）────────
echo
echo "[INFO] Installing build dependencies (binutils patchelf gcc build-essential)..."
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get install -y binutils patchelf gcc build-essential
elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y binutils patchelf gcc gcc-c++ make
elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --noconfirm binutils patchelf gcc base-devel
elif command -v zypper >/dev/null 2>&1; then
    sudo zypper install -y binutils patchelf gcc gcc-c++ make
else
    echo "[WARN] Unknown package manager. Please install manually:"
    echo "       binutils patchelf gcc build-essential (or equivalent)"
fi

# ── 4. ビルドスクリプトに実行権を付与 ───────────────────────
if ls scripts/build*.sh >/dev/null 2>&1; then
    chmod +x scripts/build*.sh
    echo "[INFO] Executable permission set on scripts/build*.sh"
fi

# ── 5. uv sync で依存関係をインストール ─────────────────────
echo
echo "[INFO] Syncing dependencies with uv sync..."
uv sync
echo

# ── 6. pdf.js の配置 ─────────────────────────────────────────
PDFJS_VERSION="5.4.624"
PDFJS_URL="https://github.com/mozilla/pdf.js/releases/download/v${PDFJS_VERSION}/pdfjs-${PDFJS_VERSION}-dist.zip"
PDFJS_ZIP="/tmp/pdfjs-${PDFJS_VERSION}-dist.zip"
PDFJS_DEST="resources/pdfjs"

if [ -f "${PDFJS_DEST}/web/viewer.html" ]; then
    echo "[INFO] pdf.js v${PDFJS_VERSION} already present. Skipping."
else
    echo "[INFO] Downloading pdf.js v${PDFJS_VERSION}..."
    if command -v curl >/dev/null 2>&1; then
        curl -L --fail --show-error -o "$PDFJS_ZIP" "$PDFJS_URL"
    elif command -v wget >/dev/null 2>&1; then
        wget -q --show-progress -O "$PDFJS_ZIP" "$PDFJS_URL"
    else
        echo "[CRITICAL] Neither curl nor wget found. Please install either and retry."
        exit 1
    fi

    echo "[INFO] Extracting pdf.js..."
    mkdir -p "$PDFJS_DEST"
    if command -v unzip >/dev/null 2>&1; then
        unzip -q "$PDFJS_ZIP" -d "$PDFJS_DEST"
    else
        echo "[CRITICAL] unzip not found. Please install unzip and retry."
        rm -f "$PDFJS_ZIP"
        exit 1
    fi

    rm -f "$PDFJS_ZIP"
    echo "[INFO] pdf.js v${PDFJS_VERSION} installed to ${PDFJS_DEST}/"
fi
echo

# ── 7. 完了メッセージ ────────────────────────────────────────
echo "============================================"
echo " [SUCCESS] Environment is ready."
echo "============================================"
echo
echo " Run:"
echo "   uv run python Strollon.py"
echo
echo " Build: (AppImage)"
echo "   ./scripts/build-linux-x64-appimage.sh"
echo

exec bash
