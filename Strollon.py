"""
 *
 * Strollon Browser
 * Copyright (C) 2025-2026 ABATBeliever
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Lesser General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>
 *
 * For description, please watch "LICENSE" file.
 *
"""

# =====================================================================
# このファイルは constants.py を内包しています。
# sys.modules に自分自身を "constants" として登録し、
# 他モジュールが from constants import ... できるようにします。
# =====================================================================

import sys
import os
import platform
import logging
from pathlib import Path

# =====================================================================
# OS チェック
# 対応: Linux (Wayland) / Windows 11+
# それ以外は即終了（QApplication 生成前なので stderr に素の print）
# =====================================================================

_SYSTEM = platform.system().lower()

if _SYSTEM not in ("linux", "windows"):
    print(
        "Strollon Browser はこの OS をサポートしていません。\n"
        "対応OS: Linux (Wayland) / Windows 11+\n"
        f"検出OS: {platform.system()} ({platform.machine()})",
        file=sys.stderr,
    )
    sys.exit(1)

# =====================================================================
# ブラウザ情報
# =====================================================================

BROWSER_NAME             = "Strollon"
BROWSER_VERSION_SEMANTIC = "0.1.0.0"
BROWSER_VERSION_NAME     = "0.1.0.0"
BROWSER_FULL_NAME        = f"{BROWSER_NAME} {BROWSER_VERSION_NAME}"


def detect_browser_target_architecture() -> str:
    machine = platform.machine().lower()
    if _SYSTEM == "linux":
        if machine in ("x86_64", "amd64"):
            return "linux-x64"
        elif machine in ("aarch64", "arm64"):
            try:
                with open("/proc/cpuinfo", "r") as f:
                    if "raspberry pi" in f.read().lower():
                        return "rasp-a64"
            except Exception:
                pass
            return "linux-a64"
    else:  # windows
        if machine in ("arm64", "aarch64"):
            return "win-a64"
        return "win-x64"
    return "unknown"


BROWSER_TARGET_ARCHITECTURE = detect_browser_target_architecture()

UPDATE_CHECK_URL = (
    f"https://abatbeliever.net/upd/Strollon/"
    f"{BROWSER_TARGET_ARCHITECTURE}.updat"
)

# =====================================================================
# 開発者向けフラグ
# =====================================================================

CHECK_FOR_UPDATES: bool = True

# =====================================================================
# UserAgent プリセット
# =====================================================================

USER_AGENT_PRESETS = {
    0: "",
    1: "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
    2: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    3: "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.5615.135 Mobile Safari/537.36",
    4: "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
    5: "",
}

USER_AGENT_PRESET_NAMES = [
    "デフォルト (Chromium)",
    "Firefox 147 (Windows)",
    "Safari 16.5 (macOS)",
    "Chrome Mobile (Android)",
    "Safari Mobile (iOS)",
    "カスタム",
]

# =====================================================================
# 実行ファイルのディレクトリ
# =====================================================================

def _get_exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.resolve()

_EXE_DIR = _get_exe_dir()

def _get_default_downloads_dir() -> Path:
    """
    OS の標準ダウンロードフォルダを返す。
    Linux / Windows ともに ~/Downloads が一般的。
    """
    return Path.home() / "Downloads"


# =====================================================================
# 設定ファイル名（OS ごと）
# =====================================================================

_CONFIG_FILENAME = "config.toml" if _SYSTEM == "linux" else "config.ini"

# =====================================================================
# XDG ベースパス（Linux: XDG 標準、Windows: ホーム配下の XDG 風）
# =====================================================================

_APP_NAME = "Strollon"
_home = Path.home()

if _SYSTEM == "linux":
    _xdg_config_base = Path(os.environ.get("XDG_CONFIG_HOME", str(_home / ".config")))
    _xdg_data_base   = Path(os.environ.get("XDG_DATA_HOME",   str(_home / ".local" / "share")))
    _xdg_cache_base  = Path(os.environ.get("XDG_CACHE_HOME",  str(_home / ".cache")))
    _xdg_state_base  = Path(os.environ.get("XDG_STATE_HOME",  str(_home / ".local" / "state")))
else:
    _xdg_config_base = _home / ".config"
    _xdg_data_base   = _home / ".local" / "share"
    _xdg_cache_base  = _home / ".local" / "cache"
    _xdg_state_base  = _home / ".local" / "state"

# =====================================================================
# モード解決
# =====================================================================
# 優先順位:
#   1. 実行ファイル隣の config/ に設定ファイルが存在 → ポータブルモード
#   2. XDG / ホーム配下の設定ファイルが存在         → XDG モード
#   3. どちらもない                                  → 未設定（ようこそ画面へ）
# =====================================================================

# ポータブルの設定ファイルは EXE_DIR/config/<filename>
# (_apply_dirs("portable") で CONFIG_DIR = EXE_DIR/config/ になるため)
_PORTABLE_CONFIG_FILE = _EXE_DIR / "config" / _CONFIG_FILENAME
_XDG_CONFIG_FILE      = _xdg_config_base / _APP_NAME / _CONFIG_FILENAME


def _resolve_mode() -> "str | None":
    if _PORTABLE_CONFIG_FILE.exists():
        return "portable"
    if _XDG_CONFIG_FILE.exists():
        return "xdg"
    return None


_BOOT_MODE: "str | None" = _resolve_mode()

# =====================================================================
# ディレクトリ確定（モードに応じて切り替え）
# =====================================================================

def _build_dirs(mode: str) -> "tuple[Path, Path, Path, Path]":
    if mode == "portable":
        base = _EXE_DIR
        return (
            base / "config",
            base / "data",
            base / "cache",
            base / "state",
        )
    else:  # xdg
        return (
            _xdg_config_base / _APP_NAME,
            _xdg_data_base   / _APP_NAME,
            _xdg_cache_base  / _APP_NAME,
            _xdg_state_base  / _APP_NAME,
        )


def _apply_dirs(mode: str):
    """グローバルなパス定数群を指定モードで（再）設定する。"""
    global CONFIG_DIR, DATA_DIR, CACHE_DIR, STATE_DIR
    global THEMES_DIR, CONFIG_FILE
    global HISTORY_DB, SESSION_FILE, BOOKMARKS_DB, DOWNLOADS_DB, DOWNLOADS_DIR
    global LOG_FILE, PROFILE_PATH, INCOGNITO_CACHE_PATH, INCOGNITO_STATE_PATH

    CONFIG_DIR, DATA_DIR, CACHE_DIR, STATE_DIR = _build_dirs(mode)

    for _d in (CONFIG_DIR, DATA_DIR, CACHE_DIR, STATE_DIR):
        _d.mkdir(parents=True, exist_ok=True)

    THEMES_DIR = CONFIG_DIR / "themes"
    THEMES_DIR.mkdir(parents=True, exist_ok=True)

    CONFIG_FILE = CONFIG_DIR / _CONFIG_FILENAME

    HISTORY_DB    = DATA_DIR / "history.db"
    SESSION_FILE  = DATA_DIR / "session.json"
    BOOKMARKS_DB  = DATA_DIR / "bookmarks.db"
    DOWNLOADS_DB  = DATA_DIR / "downloads.db"
    DOWNLOADS_DIR = _get_default_downloads_dir()
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

    LOG_FILE = STATE_DIR / "strollon.log"

    PROFILE_PATH         = STATE_DIR / "profile"
    INCOGNITO_CACHE_PATH = CACHE_DIR / "incognito"
    INCOGNITO_STATE_PATH = STATE_DIR / "incognito_storage"


# 初期適用（モード未確定なら暫定 XDG。ようこそ後に _apply_dirs が再実行される）
_apply_dirs(_BOOT_MODE if _BOOT_MODE is not None else "xdg")
INSTALL_MODE: str = _BOOT_MODE if _BOOT_MODE is not None else "xdg"

# =====================================================================
# ロガー / log() 関数
# =====================================================================
# ・起動ヘッダー（名前・URL など）は素の print() でコンソールのみ出力
# ・それ以外の全メッセージは log() を使い、コンソール＋ファイルに記録
# ・builtins.print の書き換えは行わない
# =====================================================================

def _setup_logger() -> logging.Logger:
    _logger = logging.getLogger("Strollon")
    _logger.setLevel(logging.DEBUG)
    if _logger.handlers:
        return _logger

    fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(fmt)
    _logger.addHandler(ch)

    try:
        fh = logging.FileHandler(str(LOG_FILE), mode="w", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        _logger.addHandler(fh)
    except OSError as e:
        _logger.warning(f"ログファイルを開けません: {e}")

    return _logger


logger = _setup_logger()


def log(msg: str):
    """
    アプリケーション共通ログ関数。コンソール＋ファイルに出力する。
    先頭の [ERROR] / [WARN] でレベルを自動判定する。

    使い方:
        log("[INFO] タブを追加しました")
        log("[WARN] 設定ファイルが見つかりません")
        log("[ERROR] DB の初期化に失敗しました")
    """
    upper = msg.upper()
    if upper.startswith("[ERROR]"):
        logger.error(msg)
    elif upper.startswith("[WARN]"):
        logger.warning(msg)
    else:
        logger.info(msg)

# =====================================================================
# 設定管理クラス（config.toml / config.ini 一本化）
# =====================================================================

class StrollonSettings:
    """
    設定ファイル（TOML / INI）ラッパー。

    使い方:
        val = settings.value("homepage", "https://www.google.com")
        settings.setValue("homepage", "https://example.com")
        settings.sync()
    """

    DEFAULTS: dict = {
        "homepage":                     "https://www.google.com",
        "startup_action":               0,
        "save_session":                 True,
        "search_engine":                0,
        "clear_on_exit":                False,
        "do_not_track":                 True,
        "download_dir":                 "",
        "ask_download":                 True,
        "enable_javascript":            True,
        "allow_fullscreen":             True,
        "auto_load_images":             True,
        "enable_hardware_acceleration": True,
        "ua_preset":                    0,
        "ua_custom":                    "",
        "theme":                        "Default",
        "flag_hevc":         False,
        "flag_vaapi":        False,
        "flag_mediafound":   False,
        "flag_ozone":        False,
        "flag_wasm_simd":    False,
        "flag_wasm_threads": False,
        "flag_gpu_raster":   False,
        "flag_zero_copy":    False,
        "flag_ignore_gpu":   False,
        "flag_overlays":     False,
        "flag_autoplay":     False,
        "flag_raw_draw":     False,
        "flag_no_cros_vd":   False,
    }

    def __init__(self):
        self._data: dict = {}
        self._load()

    def _current_path(self) -> Path:
        return CONFIG_FILE

    def _load(self):
        self._data = {}
        path = self._current_path()
        if not path.exists():
            return
        try:
            if _SYSTEM == "linux":
                self._load_toml(path)
            else:
                self._load_ini(path)
        except Exception as e:
            log(f"[WARN] 設定ファイルの読み込みに失敗しました: {e}")

    def _load_toml(self, path: Path):
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore[no-redef]
            except ImportError:
                log("[WARN] tomllib/tomli が見つかりません。デフォルト設定を使用します。")
                return
        with open(path, "rb") as f:
            raw = tomllib.load(f)
        self._data = raw.get("strollon", {})

    def _load_ini(self, path: Path):
        import configparser
        cfg = configparser.ConfigParser()
        cfg.read(str(path), encoding="utf-8")
        if cfg.has_section("strollon"):
            self._data = dict(cfg["strollon"])

    def reload(self):
        """_apply_dirs() 後にパスが変わった場合に再ロードする。"""
        self._load()

    def _save_toml(self, path: Path):
        lines = ["[strollon]\n"]
        for k, v in sorted(self._data.items()):
            if isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}\n")
            elif isinstance(v, int):
                lines.append(f"{k} = {v}\n")
            elif isinstance(v, float):
                lines.append(f"{k} = {v}\n")
            else:
                escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{k} = "{escaped}"\n')
        path.write_text("".join(lines), encoding="utf-8")

    def _save_ini(self, path: Path):
        import configparser
        cfg = configparser.ConfigParser()
        cfg.add_section("strollon")
        for k, v in self._data.items():
            cfg.set("strollon", k, str(v))
        with open(path, "w", encoding="utf-8") as f:
            cfg.write(f)

    def value(self, key: str, default=None, type=None):
        fallback = self.DEFAULTS.get(key, default)
        raw = self._data.get(key, fallback)
        if type is not None:
            try:
                if type is bool:
                    if isinstance(raw, bool):
                        return raw
                    return str(raw).lower() in ("true", "1", "yes")
                return type(raw)
            except (ValueError, TypeError):
                return fallback
        return raw

    def setValue(self, key: str, val):
        self._data[key] = val

    def sync(self):
        path = self._current_path()
        try:
            if _SYSTEM == "linux":
                self._save_toml(path)
            else:
                self._save_ini(path)
            log("[INFO] Settings saved")
        except Exception as e:
            log(f"[ERROR] 設定ファイルの書き込みに失敗しました: {e}")

    def allKeys(self) -> list:
        return list(self._data.keys())


settings = StrollonSettings()

# =====================================================================
# バージョンスタンプ（DB / JSON への埋め込みと検証）
# =====================================================================

VERSION_KEY = "_strollon_version"


def stamp_version_to_json(data: dict) -> dict:
    data[VERSION_KEY] = BROWSER_VERSION_SEMANTIC
    return data


def check_version_stamp(data: dict, source_label: str = "") -> bool:
    from packaging import version as _ver
    stamped = data.get(VERSION_KEY, "")
    if not stamped:
        return True
    try:
        if _ver.parse(stamped) > _ver.parse(BROWSER_VERSION_SEMANTIC):
            log(f"[WARN] {source_label}: データは新しいStrollon ({stamped}) で書かれています")
            return False
    except Exception:
        pass
    return True


def get_db_strollon_version(db_path) -> str:
    import sqlite3
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM meta WHERE key = ?", (VERSION_KEY,))
            row = cur.fetchone()
            return row[0] if row else ""
    except Exception:
        return ""


def set_db_strollon_version(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cur.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        (VERSION_KEY, BROWSER_VERSION_SEMANTIC),
    )


def check_db_version(db_path, label: str = "") -> bool:
    from packaging import version as _ver
    stamped = get_db_strollon_version(db_path)
    if not stamped:
        return True
    try:
        if _ver.parse(stamped) > _ver.parse(BROWSER_VERSION_SEMANTIC):
            log(f"[WARN] {label}: DB は新しいStrollon ({stamped}) で書かれています")
            return False
    except Exception:
        pass
    return True


# =====================================================================
# sys.modules への自己登録
# =====================================================================

sys.modules.setdefault("constants", sys.modules[__name__])

# =====================================================================
# STYLES をモジュールレベルで公開
# =====================================================================
# browser.py / dialogs.py が from constants import STYLES できるよう、
# theme.STYLES をここで公開しておく。
# テーマ初期化（init_theme_engine）は main() 内でモード確定後に行われるが、
# theme.STYLES 自体はモジュール変数として常に存在するため参照可能。
# （テーマ未初期化時は空辞書 {} が返る）
import theme as _theme_module


class _StylesProxy:
    """theme.STYLES への透過プロキシ。常に最新の STYLES を返す。"""
    def __getitem__(self, key):
        return _theme_module.STYLES[key]
    def get(self, key, default=None):
        return _theme_module.STYLES.get(key, default)
    def __contains__(self, key):
        return key in _theme_module.STYLES


STYLES = _StylesProxy()

# =====================================================================
# ようこそダイアログ（初回起動時のモード選択）
# =====================================================================

def _show_welcome_dialog() -> "str | None":
    """
    XDG / ポータブルのどちらを使うか選ばせる。
    戻り値: "xdg" | "portable" | None（キャンセル→終了）
    """
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel,
        QPushButton, QRadioButton, QButtonGroup, QFrame,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont

    dlg = QDialog()
    dlg.setWindowTitle("Strollon Browser Preview へようこそ")
    dlg.setMinimumWidth(540)
    dlg.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(32, 28, 32, 24)
    layout.setSpacing(16)

    title = QLabel("<h2>Strollon Browser Previewへようこそ</h2>")
    title.setAlignment(Qt.AlignCenter)
    layout.addWidget(title)

    sub = QLabel("※Preview版であり、互換性や安定性は保証されません。<br>データの保存場所を選んでください。後から変更することはできません。")
    sub.setAlignment(Qt.AlignCenter)
    sub.setWordWrap(True)
    layout.addWidget(sub)

    sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine); sep1.setFrameShadow(QFrame.Sunken)
    layout.addWidget(sep1)

    # ---- XDG モード ----
    radio_xdg = QRadioButton("XDG互換のインストール")
    radio_xdg.setChecked(True)
    radio_xdg.setFont(QFont("", 10, QFont.Bold))
    layout.addWidget(radio_xdg)

    if _SYSTEM == "linux":
        xdg_detail = (
            f"このモードは、XDG準拠の場所にファイルを生成します。\n長期的に運用する場合や、OS単位でバックアップする場合におすすめ。\n"
            f"設定      : {_xdg_config_base / _APP_NAME}\n"
            f"データ    : {_xdg_data_base   / _APP_NAME}\n"
            f"キャッシュ: {_xdg_cache_base / _APP_NAME}\n"
            f"ログ等    : {_xdg_state_base  / _APP_NAME}"
        )
    else:
        xdg_detail = (
            f"このモードは、XDG準拠の場所にファイルを生成します。\n長期的に運用する場合や、OS単位でバックアップする場合におすすめ。\n"
            f"設定    : {_xdg_config_base / _APP_NAME}\n"
            f"データ  : {_xdg_data_base   / _APP_NAME}\n"
            f"キャッシュ: {_xdg_cache_base / _APP_NAME}\n"
            f"ログ等  : {_xdg_state_base  / _APP_NAME}"
        )
    xdg_desc = QLabel(xdg_detail)
    xdg_desc.setStyleSheet("color: #555; font-size: 9pt; margin-left: 22px;")
    xdg_desc.setWordWrap(False)
    layout.addWidget(xdg_desc)

    layout.addSpacing(4)

    # ---- ポータブルモード ----
    radio_portable = QRadioButton("ポータブル(実行ファイルのパス)")
    radio_portable.setFont(QFont("", 10, QFont.Bold))
    layout.addWidget(radio_portable)

    # Path の str() は OS のパス区切り文字を使う（Windows は \、Linux は /）
    portable_detail = (
        f"このモードは、実行ファイルと同じ場所にファイルを生成します。\nUSBファイルなどに入れて持ち歩く場合や、ファイルを簡単に管理したい場合はこちらがおすすめ。\n"
        f"設定      : {_EXE_DIR / 'config'}\n"
        f"データ    : {_EXE_DIR / 'data'}\n"
        f"キャッシュ: {_EXE_DIR / 'cache'}\n"
        f"ログ等    : {_EXE_DIR / 'state'}"
    )
    portable_desc = QLabel(portable_detail)
    portable_desc.setStyleSheet("color: #555; font-size: 9pt; margin-left: 22px;")
    portable_desc.setWordWrap(False)
    layout.addWidget(portable_desc)

    group = QButtonGroup(dlg)
    group.addButton(radio_xdg,      0)
    group.addButton(radio_portable, 1)

    sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine); sep2.setFrameShadow(QFrame.Sunken)
    layout.addWidget(sep2)

    btn_row = QHBoxLayout()
    btn_row.addStretch()

    btn_cancel = QPushButton("終了")
    btn_cancel.setMinimumWidth(90)
    btn_cancel.clicked.connect(dlg.reject)
    btn_row.addWidget(btn_cancel)

    btn_ok = QPushButton("この設定で開始する")
    btn_ok.setMinimumWidth(130)
    btn_ok.setDefault(True)
    btn_ok.clicked.connect(dlg.accept)
    btn_row.addWidget(btn_ok)

    layout.addLayout(btn_row)

    if dlg.exec() != QDialog.Accepted:
        return None
    return "portable" if radio_portable.isChecked() else "xdg"


# =====================================================================
# 起動前チェック: データバージョン整合性
# =====================================================================

def _check_data_version_conflicts() -> bool:
    import json
    from PySide6.QtWidgets import QMessageBox

    newer_sources = []

    for db_path, label in [
        (HISTORY_DB,   "閲覧履歴 (history.db)"),
        (BOOKMARKS_DB, "ブックマーク (bookmarks.db)"),
        (DOWNLOADS_DB, "ダウンロード (downloads.db)"),
    ]:
        if db_path.exists() and not check_db_version(db_path, label):
            newer_sources.append((label, get_db_strollon_version(db_path)))

    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                sess = json.load(f)
            if not check_version_stamp(sess, "session.json"):
                newer_sources.append(("セッション (session.json)", sess.get(VERSION_KEY, "不明")))
        except Exception:
            pass

    if not newer_sources:
        return True

    detail_lines = "\n".join(
        f"  • {label}（バージョン {ver}）" for label, ver in newer_sources
    )
    msg = QMessageBox()
    msg.setWindowTitle("データバージョンの警告")
    msg.setIcon(QMessageBox.Warning)
    msg.setText(
        f"以下のデータは、現在のStrollon ({BROWSER_VERSION_SEMANTIC}) より\n"
        f"新しいバージョンで保存されています。\n\n"
        f"{detail_lines}\n\n"
        f"このまま起動すると、データが失われたり\n"
        f"正しく読み込めない可能性があります。\n"
        f"開発元は、この動作に対しデータの保証を行えません。"
    )
    msg.setInformativeText("起動しますか？")
    continue_btn = msg.addButton("無視して続行", QMessageBox.AcceptRole)
    abort_btn    = msg.addButton("起動しない (推奨)", QMessageBox.RejectRole)
    msg.setDefaultButton(abort_btn)
    msg.exec()

    return msg.clickedButton() == continue_btn


# =====================================================================
# メイン
# =====================================================================

def main():
    global INSTALL_MODE

    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont
    # ---- 起動ヘッダー（素の print でコンソールのみ・ログファイルには書かない） ----
    print(f"\n{BROWSER_FULL_NAME}")
    print("\nCopyright (C) 2025-2026 ABATBeliever")
    print("Strollon Website     | https://abatbeliever.net/software/bin/Strollon/")
    print("Strollon Github Repo | https://github.com/ABATBeliever/Strollon/")

    from browser import apply_chromium_flags_from_settings
    apply_chromium_flags_from_settings()

    app = QApplication(sys.argv)
    font = QFont()
    font.setPointSize(8)
    app.setFont(font)

    # ---- モード解決 ----
    if _BOOT_MODE is None:
        log("[INFO] 設定ファイルが見つかりません。")
        chosen_mode = _show_welcome_dialog()
        if chosen_mode is None:
            log("[INFO] セットアップがキャンセルされました。終了します。")
            sys.exit(0)

        _apply_dirs(chosen_mode)
        INSTALL_MODE = chosen_mode
        settings.reload()
        settings.setValue("install_mode", chosen_mode)
        settings.sync()
        log(f"[INFO] モードを選択しました: {chosen_mode}")
    else:
        INSTALL_MODE = _BOOT_MODE
        log(f"[INFO] 設定ファイルを検出しました。モード: {INSTALL_MODE}")

    # ---- テーマ初期化（1回のみ・モード確定後） ----
    from theme import init_theme_engine
    theme_name = settings.value("theme", "Default")
    init_theme_engine(THEMES_DIR, theme_name)
    from theme import STYLES as _app_styles
    app.setStyleSheet(_app_styles["app_global"])

    # ---- ログ出力 ----
    log(f"[INFO] OS           : {platform.system()} ({BROWSER_TARGET_ARCHITECTURE})")
    log(f"[INFO] Mode         : {INSTALL_MODE}")
    log(f"[INFO] Config File  : {CONFIG_FILE}")
    log(f"[INFO] Data Dir     : {DATA_DIR}")
    log(f"[INFO] Themes Dir   : {THEMES_DIR}")
    log(f"[INFO] Log File     : {LOG_FILE}")
    log(f"[INFO] Theme        : {theme_name}")

    if not _check_data_version_conflicts():
        sys.exit(0)

    from browser import VerticalTabBrowser
    browser = VerticalTabBrowser()
    browser.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
