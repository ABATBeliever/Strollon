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
# このファイルは constants.py を内包。
# =====================================================================

import sys
import os
import logging
from pathlib import Path

# =====================================================================
# プラットフォーム / アーキテクチャ定数
# =====================================================================
# win-x64 / win-a64 / linux-x64 / linux-a64 / rasp-a64 / mac-a64
#
# 0.7.3.0 [1.0.0.0-rc1] より、IS_WINDOWS / IS_LINUX は BROWSER_TARGET_ARCHITECTURE
# の文字列から自動判定するように変更した。以前は IS_WINDOWS / IS_LINUX を
# ビルドごとに手動で True/False を書き換えていたため、書き換え忘れによる
# 実行時の不整合（例: Linuxビルドなのに IS_WINDOWS=True のまま）が起こり得た。
# ビルド時に設定すべき値は BROWSER_TARGET_ARCHITECTURE 一つだけにし、
# そこから他のフラグを一意に導出することで書き換え漏れをなくす。
# =====================================================================

BROWSER_TARGET_ARCHITECTURE: str = "win-x64"

_arch_lower = BROWSER_TARGET_ARCHITECTURE.lower()
IS_WINDOWS: bool = "win" in _arch_lower
IS_LINUX:   bool = ("linux" in _arch_lower) or ("rasp" in _arch_lower)

# =====================================================================
# ブラウザ情報
# =====================================================================

BROWSER_NAME             = "Strollon"
BROWSER_VERSION_SEMANTIC = "0.7.4.0"
BROWSER_VERSION_NAME     = "0.7.4.0 [1.0.0.0 rc-2]"
BROWSER_FULL_NAME        = f"{BROWSER_NAME} {BROWSER_VERSION_NAME}"

# =====================================================================
# インストール種別フラグ
# =====================================================================
# INSTALL = True  → インストール版（XDG モード固定）
# INSTALL = False → ポータブル版（実行ファイル隣のディレクトリを使用）
# =====================================================================

INSTALL: bool = True

UPDATE_CHECK_URL = (
    f"https://abatbeliever.net/upd/Strollon/"
    f"{BROWSER_TARGET_ARCHITECTURE}"
)

# =====================================================================
# 更新確認を行うか
# =====================================================================

CHECK_FOR_UPDATES: bool = True

# =====================================================================
# UserAgent プリセット
# =====================================================================

USER_AGENT_PRESETS = {
    0: "",
    1: "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
    2: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0.1 Safari/605.1.15",
    3: "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36",
    4: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Mobile/15E148 Safari/604.1",
    5: "",
}

USER_AGENT_PRESET_NAMES = [
    "デフォルト (Chromium)",
    "Firefox 152 (Windows)",
    "Safari 26.0.1 (macOS)",
    "Chrome Mobile 140 (Android)",
    "Safari Mobile 18.6 (iOS)",
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

# =====================================================================
# pdf.js リソースディレクトリ
# =====================================================================
# アプリ本体に同梱する静的アセット（Apache-2.0 / pdf.js）。
# ユーザーデータではないため XDG ディレクトリではなく実行ファイル隣に置く。
# 配置例: <EXE_DIR>/resources/pdfjs/{web,build,LICENSE}
# =====================================================================

PDFJS_DIR = _EXE_DIR / "resources" / "pdfjs"


def _get_default_downloads_dir() -> Path:
    """OS の標準ダウンロードフォルダ（~/Downloads）を返す。"""
    return Path.home() / "Downloads"


# =====================================================================
# 設定ファイル名
# =====================================================================

_CONFIG_FILENAME = "config.ini"

# =====================================================================
# XDG ベースパス
# =====================================================================

_APP_NAME = "Strollon"
_home = Path.home()

if IS_LINUX:
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
# モード確定
# =====================================================================
# INSTALL = True  → 常に "xdg"
# INSTALL = False → EXE_DIR/config/<filename> があれば "portable"（なくても "portable"）
#
# 初回起動（設定ファイルが存在しない）かどうかは IS_FIRST_RUN で持つ。
# IS_FIRST_RUN = True のとき browser.py がウェルカムページを最初のタブで開く。
# =====================================================================

def _determine_mode() -> str:
    return "xdg" if INSTALL else "portable"

INSTALL_MODE: str = _determine_mode()

_portable_config = _EXE_DIR / "config" / _CONFIG_FILENAME
_xdg_config      = _xdg_config_base / _APP_NAME / _CONFIG_FILENAME

def _is_first_run() -> bool:
    """設定ファイルが存在しない＝初回起動。"""
    if INSTALL_MODE == "xdg":
        return not _xdg_config.exists()
    else:
        return not _portable_config.exists()

IS_FIRST_RUN: bool = _is_first_run()


def _check_is_updated() -> bool:
    """
    設定ファイルに保存されたバージョンが現在のバージョンより古い場合は更新と判断する。
    初回起動時は False（IS_FIRST_RUN が True のため welcome は別途表示）。

    configparser で直接ファイルを読む（settings オブジェクト初期化前に呼ばれるため）。
    キーが存在しない（旧バージョンの設定ファイル）場合は更新扱いにする。
    """
    if IS_FIRST_RUN:
        return False
    import configparser
    from packaging import version as _ver
    path = _xdg_config if INSTALL_MODE == "xdg" else _portable_config
    if not path.exists():
        return False  # ファイルがない = IS_FIRST_RUN が先に検出するはずだが念のため
    try:
        cfg = configparser.ConfigParser()
        cfg.read(str(path), encoding="utf-8")
        # セクションが存在しない = 旧形式 → 更新扱い
        if not cfg.has_section("strollon"):
            return True
        stored = cfg.get("strollon", "_browser_version", fallback="")
        if not stored:
            return True  # バージョン記録がない旧設定 → 更新扱い
        return _ver.parse(stored) < _ver.parse(BROWSER_VERSION_SEMANTIC)
    except Exception:
        return False  # 読み込み失敗時は welcome を出さない（誤爆防止）

IS_UPDATED: bool = _check_is_updated()

# =====================================================================
# ディレクトリ確定
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
    """グローバルなパス定数群を指定モードで設定する。"""
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


# モード確定後にすぐディレクトリを設定する（QApplication より前）
_apply_dirs(INSTALL_MODE)

# =====================================================================
# ロガー / log() 関数
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
    アプリケーション共通ログ関数。コンソール＋ファイルに出力。
    [ERROR] / [WARN] プレフィックスでレベルを自動判定する。
    """
    upper = msg.upper()
    if upper.startswith("[ERROR]"):
        logger.error(msg)
    elif upper.startswith("[WARN]"):
        logger.warning(msg)
    else:
        logger.info(msg)


# =====================================================================
# 設定管理クラス（config.ini 統一）
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
        "homepage":                     "strollon://start",
        "startup_action":               0,
        "save_session":                 True,
        "search_engine":                2,  # 既定: DuckDuckGo
        "clear_on_exit":                False,
        "do_not_track":                 True,
        "download_dir":                 "",
        "ask_download":                 True,
        "open_pdf_in_viewer":           True,
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
        # ウィンドウ設定
        "always_on_top":     False,
        # 広告ブロック
        "adblock_enabled":       True,
        "adblock_last_updated":  "",
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
            self._load_ini(path)
        except Exception as e:
            log(f"[WARN] 設定ファイルの読み込みに失敗しました: {e}")

    def _load_ini(self, path: Path):
        import configparser
        cfg = configparser.ConfigParser()
        cfg.read(str(path), encoding="utf-8")
        if cfg.has_section("strollon"):
            self._data = dict(cfg["strollon"])

    def reload(self):
        self._load()

    def _save_ini(self, path: Path):
        import configparser
        cfg = configparser.ConfigParser()
        cfg.add_section("strollon")
        for k, v in self._data.items():
            cfg.set("strollon", k, str(v))
        with open(path, "w", encoding="utf-8") as f:
            cfg.write(f)

    def value(self, key: str, default=None, type=None):  # noqa: A002
        """
        設定値を取得する。

        Parameters
        ----------
        key     : 設定キー
        default : DEFAULTS にキーがない場合のフォールバック値
        type    : 変換先の型 (bool / int / str など)。
                  引数名は QSettings との互換性のため "type" のままにしているが、
                  内部では _type_ として参照し組み込み type() を隠さない。
        """
        _type_ = type  # 組み込み type() を隠さないよう別名で参照
        fallback = self.DEFAULTS.get(key, default)
        raw = self._data.get(key, fallback)
        if _type_ is not None:
            # raw が None（キーも DEFAULTS も default も None）の場合は
            # 型変換せずそのまま fallback を返す
            if raw is None:
                return fallback
            try:
                if _type_ is bool:
                    if isinstance(raw, bool):
                        return raw
                    return str(raw).lower() in ("true", "1", "yes")
                return _type_(raw)
            except (ValueError, TypeError):
                return fallback
        return raw

    def setValue(self, key: str, val):
        self._data[key] = val

    def sync(self):
        path = self._current_path()
        # ブラウザバージョンを設定ファイルに記録（更新検出に使用）
        self._data["_browser_version"] = BROWSER_VERSION_SEMANTIC
        try:
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
# STYLES をモジュールレベルで公開（browser.py 等の import 用プロキシ）
# =====================================================================

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
    import faulthandler
    import traceback

    # ---- セグメンテーションフォルト等のネイティブクラッシュをログに記録 ----
    faulthandler.enable()

    # ---- Python 未処理例外をログファイルに記録してから終了 ----
    def _excepthook(exc_type, exc_value, exc_tb):
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log(f"[CRITICAL] Unhandled exception:\n{msg}")
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont

    # ---- 起動ヘッダー（コンソールのみ） ----
    print(f"{BROWSER_FULL_NAME}")
    print("\nCopyright (C) 2025-2026 ABATBeliever")
    print("Strollon WebPage           | https://abatbeliever.net/software/bin/Strollon/")
    print("Strollon Github Repository | https://github.com/ABATBeliever/Strollon/\n")

    from browser import apply_chromium_flags_from_settings
    apply_chromium_flags_from_settings()

    # ---- PDFキャッシュを起動時にクリア（終了時にも closeEvent でクリアする）----
    try:
        from pdf_viewer import clear_pdf_cache
        clear_pdf_cache(CACHE_DIR)
        log("[INFO] PDF cache cleared (startup)")
    except Exception as e:
        log(f"[WARN] PDF cache clear failed: {e}")

    # ---- シークレットモードのキャッシュ・ストレージ残留物を起動時にも削除 ----
    # closeEvent でも削除を試みているが、終了時点では QWebEngineProfile
    # （Chromium側）がまだファイルハンドルを保持していることがあり、
    # 特にWindowsではロック中のファイルが削除できず ignore_errors=True で
    # 失敗が握りつぶされて残留することがあった。起動時（＝どの
    # QWebEngineProfileもまだ生成されておらずファイルハンドルが一切ない
    # タイミング）にも必ず掃除することで、削除漏れを確実に解消する。
    import shutil as _shutil
    for _incognito_leftover in (INCOGNITO_CACHE_PATH, INCOGNITO_STATE_PATH):
        try:
            if _incognito_leftover.exists():
                _shutil.rmtree(_incognito_leftover, ignore_errors=True)
                log(f"[INFO] Incognito leftover data cleared (startup): {_incognito_leftover}")
        except Exception as e:
            log(f"[WARN] Incognito leftover clear failed: {e}")

    app = QApplication(sys.argv)

    # strollon:// ハンドラ(IOスレッドから呼ばれる)がGUI操作を安全にメイン
    # スレッドへ委譲できるよう、確実にメインスレッド上でここに初期化する。
    from browser import init_main_thread_invoker
    init_main_thread_invoker()

    font = QFont()
    font.setPointSize(8)
    app.setFont(font)

    # ---- テーマ初期化（1回のみ・ディレクトリ確定後） ----
    from theme import init_theme_engine
    theme_name = settings.value("theme", "Default")
    init_theme_engine(THEMES_DIR, theme_name)
    from theme import STYLES as _app_styles
    app.setStyleSheet(_app_styles["app_global"])

    # ---- ログ出力 ----
    log(f"[INFO] OS           : {'Windows' if IS_WINDOWS else 'Linux'} ({BROWSER_TARGET_ARCHITECTURE})")
    log(f"[INFO] ConfigType   : {'XDG Mode' if INSTALL else 'Portable Mode'}")
    log(f"[INFO] Mode         : {INSTALL_MODE}")
    log(f"[INFO] First Run    : {IS_FIRST_RUN}")
    log(f"[INFO] Updated      : {IS_UPDATED}")
    log(f"[INFO] Config File  : {CONFIG_FILE}")
    log(f"[INFO] Data Dir     : {DATA_DIR}")
    log(f"[INFO] Themes Dir   : {THEMES_DIR}")
    log(f"[INFO] Log File     : {LOG_FILE}")
    log(f"[INFO] Theme        : {theme_name}")
    if PDFJS_DIR.exists():
        log(f"[INFO] pdf.js Dir   : {PDFJS_DIR}")
    else:
        log(f"[WARN] pdf.js Dir not found: {PDFJS_DIR} "
            f"(PDFファイルは内蔵ビューアではなく通常ダウンロードとして扱われます)")

    # 初回起動 / バージョン更新: 設定ファイルにバージョンを記録
    # （restore_session より前に必ず sync して IS_UPDATED が次回 False になるよう保証する）
    if IS_FIRST_RUN:
        log("[INFO] First Boot: Config init...")
        settings.sync()
    elif IS_UPDATED:
        log(f"[INFO] Version Updated: → {BROWSER_VERSION_SEMANTIC}")
        settings.sync()  # ← ここで新バージョンをファイルに書き込む（次回起動では False になる）

    if not _check_data_version_conflicts():
        sys.exit(0)

    from browser import VerticalTabBrowser
    browser = VerticalTabBrowser()
    browser.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
