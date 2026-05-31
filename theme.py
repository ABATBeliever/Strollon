"""
 *
 * Strollon Browser
 * Copyright (C) 2025-2026 ABATBeliever
 *
 * theme.py — スキン（テーマ）エンジン
 * INI形式のテーマファイルを読み込み、STYLESディクショナリを生成する。
 *
 * テーマファイルは CONFIG_DIR / "themes" / "<テーマ名>.ini" に配置する。
 * テーマは [colors] セクションに色キーを記述する。
 * 未定義のキーはデフォルトテーマの値にフォールバックする。
 *
"""

import configparser
import re
from pathlib import Path


# =====================================================================
# デフォルトカラーパレット（Light テーマ相当）
# =====================================================================

DEFAULT_COLORS: dict[str, str] = {
    # --- 背景 ---
    "bg_window":           "#fafafa",   # メインウィンドウ背景
    "bg_surface":          "#ffffff",   # 通常サーフェス（ダイアログ・リストなど）
    "bg_surface_dim":      "#f9f9f9",   # 少し暗めのサーフェス
    "bg_surface_alt":      "#f7f9fc",   # テーブル交互行
    "bg_sidebar":          "#f5f6f8",   # タブリストサイドバー
    "bg_toolbar":          "#f3f4f6",   # ツールバー・タブバー
    "bg_hover":            "#f0f3f7",   # ホバー時背景

    # --- ボーダー ---
    "border_default":      "#dcdfe3",   # 標準ボーダー
    "border_light":        "#e0e0e0",   # 薄いボーダー
    "border_grid":         "#e2e5ea",   # テーブルグリッド線

    # --- テキスト ---
    "text_primary":        "#2e2e2e",   # メインテキスト
    "text_secondary":      "#5f6368",   # セカンダリテキスト（コンボボックス矢印など）
    "text_muted":          "#666666",   # 控えめなテキスト
    "text_disabled":       "#9aa0a6",   # 無効・チェックボックス枠
    "text_placeholder":    "#999999",   # プレースホルダー

    # --- アクセント（青） ---
    "accent_primary":      "#4a90d9",   # プライマリアクセント
    "accent_hover":        "#3a7fc4",   # ホバー時アクセント
    "accent_pressed":      "#2f6ca8",   # 押下時アクセント
    "accent_dark":         "#1f5fa5",   # 選択テキスト色 / 強調
    "accent_light":        "#eaf2fb",   # アクセント薄い背景
    "accent_lighter":      "#d6e8fa",   # アクセントさらに薄い背景

    # --- アクセント（ダイアログボタン用 Windows blue） ---
    "accent_win":          "#0078d4",   # QMessageBox ボタン
    "accent_win_hover":    "#106ebe",   # QMessageBox ボタンホバー

    # --- 特殊アクセント ---
    "accent_incognito":    "#8a2be2",   # シークレットタブ（紫）
    "color_warning":       "#c0392b",   # 警告テキスト
    "color_danger":        "#d13438",   # 危険・閉じるアクション
    "color_success":       "#2e7d32",   # 成功・完了
    "color_bookmark":      "#f4c430",   # ブックマーク（星）

    # --- ツールチップ ---
    "tooltip_bg":          "#333333",   # ツールチップ背景
    "tooltip_text":        "#ffffff",   # ツールチップテキスト
    "tooltip_border":      "#555555",   # ツールチップボーダー
}


# =====================================================================
# 色のバリデーション
# =====================================================================

_COLOR_RE = re.compile(r'^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$')


def _is_valid_color(value: str) -> bool:
    """#RGB / #RRGGBB / #RRGGBBAA 形式かどうか確認する"""
    return bool(_COLOR_RE.match(value.strip()))


# =====================================================================
# テーマエンジン本体
# =====================================================================

class ThemeEngine:
    """
    スキン（テーマ）エンジン。

    使い方:
        engine = ThemeEngine(themes_dir)
        engine.load("Dark")          # themes_dir/Dark.ini を読む
        styles = engine.build_styles()
    """

    def __init__(self, themes_dir: Path):
        self.themes_dir = themes_dir
        self.themes_dir.mkdir(parents=True, exist_ok=True)
        self._colors: dict[str, str] = dict(DEFAULT_COLORS)
        self._current_theme: str = "Default"
        self._ensure_builtin_themes()

    # ------------------------------------------------------------------
    # テーマ一覧
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 組み込みテーマの自動生成
    # ------------------------------------------------------------------

    def _ensure_builtin_themes(self):
        """
        組み込みテーマ（Default / Dark / Sakura）が themes_dir に存在しない場合、
        または INI の strollon_version が現在のブラウザバージョンと一致しない場合に
        再生成する。ユーザーが作成したカスタムテーマは対象外。
        """
        _BUILTIN_NAMES = {
            "Default": _BUILTIN_DEFAULT_INI,
            "Dark":    _BUILTIN_DARK_INI,
            "Sakura":  _BUILTIN_SAKURA_INI,
        }
        for name, content in _BUILTIN_NAMES.items():
            self._write_builtin_if_outdated(name, content)

    def _get_ini_strollon_version(self, path: Path) -> str:
        """INI の [info] セクションから strollon_version を読む。なければ空文字を返す。"""
        try:
            cfg = configparser.ConfigParser()
            cfg.read(str(path), encoding="utf-8")
            return cfg.get("info", "strollon_version", fallback="")
        except Exception:
            return ""

    def _write_builtin_if_outdated(self, name: str, content: str):
        """
        ファイルが存在しない、または strollon_version が現バージョンと異なる場合に書き出す。
        """
        from constants import BROWSER_VERSION_SEMANTIC
        path = self.themes_dir / f"{name}.ini"
        if path.exists():
            stored_ver = self._get_ini_strollon_version(path)
            if stored_ver == BROWSER_VERSION_SEMANTIC:
                return  # 最新 → スキップ
            print(f"[INFO] Theme: built-in '{name}.ini' is outdated "
                  f"(ini={stored_ver or 'none'}, current={BROWSER_VERSION_SEMANTIC}), regenerating")
        try:
            from constants import BROWSER_VERSION_SEMANTIC
            # INI 文字列内の {BROWSER_VERSION_SEMANTIC} プレースホルダを実値に展開
            resolved = content.replace("{BROWSER_VERSION_SEMANTIC}", BROWSER_VERSION_SEMANTIC)
            path.write_text(resolved, encoding="utf-8")
            print(f"[INFO] Theme: wrote built-in '{name}.ini' (strollon_version={BROWSER_VERSION_SEMANTIC})")
        except OSError as e:
            print(f"[WARN] Theme: could not write '{name}.ini': {e}")

    # ------------------------------------------------------------------
    # テーマ一覧
    # ------------------------------------------------------------------

    def list_themes(self) -> list[str]:
        """利用可能なテーマ名の一覧を返す（.ini ファイル名からの拡張子除去）"""
        names = [p.stem for p in sorted(self.themes_dir.glob("*.ini"))]
        # "Default" が先頭に来るよう並び替え
        if "Default" in names:
            names.remove("Default")
            names.insert(0, "Default")
        return names

    def current_theme(self) -> str:
        return self._current_theme

    # ------------------------------------------------------------------
    # 読み込み
    # ------------------------------------------------------------------

    def load(self, theme_name: str) -> bool:
        """
        指定テーマを読み込む。
        テーマファイルが見つからない・パースエラーの場合は
        デフォルトにフォールバックして False を返す。
        """
        ini_path = self.themes_dir / f"{theme_name}.ini"

        # まずデフォルトパレットにリセット
        self._colors = dict(DEFAULT_COLORS)

        if not ini_path.exists():
            print(f"[WARN] Theme '{theme_name}' not found, using Default")
            self._current_theme = "Default"
            return False

        cfg = configparser.ConfigParser()
        try:
            cfg.read(str(ini_path), encoding="utf-8")
        except Exception as e:
            print(f"[WARN] Theme '{theme_name}' parse error: {e}, using Default")
            self._current_theme = "Default"
            return False

        if "colors" not in cfg:
            print(f"[WARN] Theme '{theme_name}' has no [colors] section, using Default")
            self._current_theme = "Default"
            return False

        loaded = 0
        skipped = 0
        for key, value in cfg["colors"].items():
            value = value.strip()
            if key not in DEFAULT_COLORS:
                print(f"[WARN] Theme '{theme_name}': unknown key '{key}', skipped")
                skipped += 1
                continue
            if not _is_valid_color(value):
                print(f"[WARN] Theme '{theme_name}': invalid color '{value}' for '{key}', using default")
                skipped += 1
                continue
            self._colors[key] = value
            loaded += 1

        self._current_theme = theme_name
        print(f"[INFO] Theme '{theme_name}' loaded ({loaded} colors, {skipped} skipped/fallback)")
        return True

    # ------------------------------------------------------------------
    # 色アクセサ
    # ------------------------------------------------------------------

    def c(self, key: str) -> str:
        """色キーから色コードを返す。未知のキーはデフォルトにフォールバック。"""
        return self._colors.get(key, DEFAULT_COLORS.get(key, "#000000"))

    # ------------------------------------------------------------------
    # STYLESディクショナリ生成
    # ------------------------------------------------------------------

    def build_styles(self) -> dict[str, str]:
        """現在のカラーパレットから STYLES ディクショナリを構築して返す"""
        c = self.c  # ショートハンド

        styles: dict[str, str] = {}

        # ---- main_window ----
        styles["main_window"] = f"""
            QMainWindow {{
                background-color: {c('bg_window')};
            }}
        """

        # ---- toolbar ----
        styles["toolbar"] = f"""
            QToolBar {{
                background-color: {c('bg_toolbar')};
                border-bottom: 1px solid {c('border_default')};
                spacing: 6px;
                padding: 6px;
            }}
            QPushButton {{
                background-color: {c('bg_surface')};
                color: {c('text_primary')};
                border: 1px solid {c('border_default')};
                border-radius: 4px;
                padding: 6px 8px;
            }}
            QPushButton:hover {{
                background-color: {c('accent_light')};
                border-color: {c('accent_primary')};
                color: {c('accent_dark')};
            }}
            QPushButton:pressed {{
                background-color: {c('accent_lighter')};
            }}
            QLineEdit {{
                background-color: {c('bg_surface')};
                color: {c('text_primary')};
                border: 1px solid {c('border_default')};
                border-radius: 4px;
                padding: 6px;
                font-size: 10pt;
                selection-background-color: {c('accent_primary')};
                selection-color: {c('bg_surface')};
            }}
            QLineEdit:focus {{
                border: 2px solid {c('accent_primary')};
            }}
        """

        # ---- tab_list ----
        styles["tab_list"] = f"""
            QWidget {{
                background-color: {c('bg_sidebar')};
                border-right: 1px solid {c('border_default')};
            }}
            QListWidget {{
                background-color: {c('bg_surface')};
                border: 1px solid {c('border_default')};
                border-radius: 4px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 0px;
                margin: 2px;
                color: {c('text_primary')};
                background-color: {c('bg_surface')};
                border-radius: 4px;
            }}
            QListWidget::item:hover {{
                background-color: {c('bg_hover')};
            }}
            QListWidget::item:selected {{
                background-color: {c('accent_light')};
                color: {c('accent_dark')};
            }}
        """

        # ---- splitter ----
        styles["splitter"] = f"""
            QSplitter::handle {{
                background-color: {c('border_default')};
                width: 1px;
            }}
        """

        # ---- 履歴・ダウンロード カードリスト ----
        styles["history_list"] = f"""
            QListWidget {{
                background-color: {c('bg_surface_dim')};
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                padding: 0px;
                margin: 0px;
                background-color: transparent;
                border: none;
            }}
            QListWidget::item:selected {{
                background-color: transparent;
                border: none;
            }}
        """
        styles["history_card"] = f"""
            background-color: {c('bg_surface')};
            border-bottom: 1px solid {c('border_default')};
        """
        styles["history_card_hover"] = f"""
            background-color: {c('bg_hover')};
            border-bottom: 1px solid {c('border_default')};
        """
        styles["history_group_header"] = f"""
            background-color: {c('bg_surface_dim')};
            color: {c('text_muted')};
            font-size: 11px;
            font-weight: 600;
            padding: 6px 14px 4px 14px;
            border-bottom: 1px solid {c('border_default')};
        """
        styles["history_title_color"]   = c('text_primary')
        styles["history_url_color"]     = c('text_muted')
        styles["history_time_color"]    = c('text_muted')
        styles["history_bg_surface"]    = c('bg_surface')
        styles["history_bg_hover"]      = c('bg_hover')
        styles["history_border"]        = c('border_default')

        # ---- menu ----
        styles["menu"] = f"""
            QMenu {{
                background-color: {c('bg_surface')};
                border: 1px solid {c('border_default')};
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 30px 8px 10px;
                border-radius: 4px;
                color: {c('text_primary')};
            }}
            QMenu::item:selected {{
                background-color: {c('accent_light')};
                color: {c('accent_dark')};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {c('border_default')};
                margin: 4px 0px;
            }}
        """

        # ---- dialog ----
        styles["dialog"] = f"""
            QDialog {{
                background-color: {c('bg_surface')};
                color: {c('text_primary')};
            }}
            QLabel {{
                color: {c('text_primary')};
            }}

            QLineEdit, QTextEdit {{
                background-color: {c('bg_surface')};
                border: 1px solid {c('border_default')};
                border-radius: 4px;
                padding: 6px;
                selection-background-color: {c('accent_primary')};
                selection-color: {c('bg_surface')};
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border: 2px solid {c('accent_primary')};
            }}

            QComboBox {{
                background-color: {c('bg_surface')};
                border: 1px solid {c('border_default')};
                border-radius: 4px;
                padding: 6px 28px 6px 6px;
                color: {c('text_primary')};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 22px;
                border: none;
                background: transparent;
            }}
            QComboBox::down-arrow {{
                width: 0;
                height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {c('text_secondary')};
            }}
            QComboBox:hover {{
                border-color: {c('accent_primary')};
            }}
            QComboBox QAbstractItemView {{
                background-color: {c('bg_surface')};
                border: 1px solid {c('border_default')};
                selection-background-color: {c('accent_light')};
                selection-color: {c('accent_dark')};
            }}

            QGroupBox {{
                border: 1px solid {c('border_default')};
                border-radius: 4px;
                margin-top: 12px;
                color: {c('text_primary')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                background-color: {c('bg_surface')};
                font-weight: 600;
            }}

            QCheckBox, QRadioButton {{
                spacing: 6px;
                color: {c('text_primary')};
            }}

            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {c('text_disabled')};
                border-radius: 4px;
                background-color: {c('bg_surface')};
            }}
            QCheckBox::indicator:checked {{
                background-color: {c('accent_primary')};
                border-color: {c('accent_primary')};
            }}

            QRadioButton::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 9px;
                border: 2px solid {c('text_disabled')};
                background-color: {c('bg_surface')};
            }}
            QRadioButton::indicator:checked {{
                border-color: {c('accent_primary')};
                background-color: {c('accent_primary')};
            }}

            QTableWidget, QTreeWidget {{
                border: 1px solid {c('border_default')};
                alternate-background-color: {c('bg_surface_alt')};
                gridline-color: {c('border_grid')};
                background-color: {c('bg_surface')};
                color: {c('text_primary')};
            }}
            QTableWidget::item:selected, QTreeWidget::item:selected {{
                background-color: {c('accent_light')};
                color: {c('accent_dark')};
            }}
            QTableWidget::item:hover, QTreeWidget::item:hover {{
                background-color: {c('bg_hover')};
                color: {c('text_primary')};
            }}

            QHeaderView::section {{
                background-color: {c('bg_toolbar')};
                border: 1px solid {c('border_default')};
                padding: 6px;
                font-weight: 600;
                color: {c('text_primary')};
            }}

            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
            }}
            QScrollBar::handle:vertical {{
                background-color: rgba(120, 120, 120, 80);
                border-radius: 5px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: rgba(120, 120, 120, 140);
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            QProgressBar {{
                border: 1px solid {c('border_default')};
                border-radius: 4px;
                background-color: {c('bg_toolbar')};
                text-align: center;
                color: {c('text_primary')};
            }}
            QProgressBar::chunk {{
                background-color: {c('accent_primary')};
                border-radius: 3px;
            }}
        """

        # ---- tab_widget ----
        styles["tab_widget"] = f"""
            QTabWidget::pane {{
                border: 1px solid {c('border_default')};
                background-color: {c('bg_surface')};
            }}
            QTabBar::tab {{
                background-color: {c('bg_toolbar')};
                padding: 10px 20px;
                border: 1px solid {c('border_default')};
                border-bottom: none;
                color: {c('text_primary')};
            }}
            QTabBar::tab:selected {{
                background-color: {c('bg_surface')};
                color: {c('accent_primary')};
                border-bottom: 2px solid {c('accent_primary')};
            }}
            QTabBar::tab:hover {{
                background-color: {c('accent_light')};
            }}
        """

        # ---- button_primary ----
        styles["button_primary"] = f"""
            QPushButton {{
                background-color: {c('accent_primary')};
                color: {c('bg_surface')};
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {c('accent_hover')};
            }}
            QPushButton:pressed {{
                background-color: {c('accent_pressed')};
            }}
        """

        # ---- button_secondary ----
        styles["button_secondary"] = f"""
            QPushButton {{
                background-color: {c('bg_surface')};
                color: {c('text_primary')};
                border: 1px solid {c('border_default')};
                padding: 8px 16px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {c('bg_hover')};
            }}
            QPushButton:pressed {{
                background-color: {c('border_grid')};
            }}
        """

        # ---- tab_item_close_button ----
        styles["tab_item_close_button"] = f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 3px;
                padding: 2px;
                min-width: 16px;
                max-width: 16px;
                min-height: 16px;
                max-height: 16px;
            }}
            QPushButton:hover {{
                background-color: rgba(0, 0, 0, 0.1);
            }}
            QPushButton:pressed {{
                background-color: rgba(0, 0, 0, 0.2);
            }}
        """

        # ---- tab_context_menu ----
        styles["tab_context_menu"] = styles["menu"]

        # ---- tab_title_label (通常タブのタイトル文字) ----
        styles["tab_title_label"] = f"""
            QLabel {{
                background: transparent;
                color: {c('text_primary')};
                padding: 0px;
                font-size: 10pt;
            }}
        """

        # ---- incognito_title_label ----
        styles["incognito_title_label"] = f"""
            QLabel {{
                background: transparent;
                color: {c('accent_incognito')};
                padding: 0px;
                font-size: 10pt;
            }}
        """

        # ---- load_progress_bar ----
        styles["load_progress_bar"] = f"""
            QProgressBar {{
                border: none;
                border-radius: 0px;
                background-color: transparent;
                max-height: 3px;
                min-height: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {c('accent_primary')};
                border-radius: 0px;
            }}
        """

        # ---- app_global (QApplication.setStyleSheet 用) ----
        styles["app_global"] = f"""
            QWidget {{
                background-color: {c('bg_surface')};
                color: {c('text_primary')};
            }}
            QMessageBox {{
                background-color: {c('bg_surface')};
                color: {c('text_primary')};
            }}
            QMessageBox QLabel {{
                color: {c('text_primary')};
            }}
            QMessageBox QPushButton {{
                background-color: {c('accent_win')};
                color: {c('bg_surface')};
                border: none;
                padding: 6px 16px;
                border-radius: 4px;
                min-width: 80px;
            }}
            QMessageBox QPushButton:hover {{
                background-color: {c('accent_win_hover')};
            }}
            QFileDialog {{
                background-color: {c('bg_surface')};
                color: {c('text_primary')};
            }}
            QFileDialog QLabel {{
                color: {c('text_primary')};
            }}
            QFileDialog QPushButton {{
                background-color: {c('bg_surface')};
                color: {c('text_primary')};
                border: 1px solid {c('border_light')};
                padding: 6px 16px;
                border-radius: 4px;
            }}
            QFileDialog QTreeView, QFileDialog QListView {{
                background-color: {c('bg_surface')};
                color: {c('text_primary')};
                border: 1px solid {c('border_light')};
            }}
            QFileDialog QTreeView::item, QFileDialog QListView::item {{
                color: {c('text_primary')};
            }}
            QFileDialog QTreeView::item:selected, QFileDialog QListView::item:selected {{
                background-color: {c('accent_win')};
                color: {c('bg_surface')};
            }}
            QToolTip {{
                background-color: {c('tooltip_bg')};
                color: {c('tooltip_text')};
                border: 1px solid {c('tooltip_border')};
                padding: 4px;
            }}
        """

        # ---- icon_colors (qtawesome アイコン色として使う辞書) ----
        # browser.py 側で qta.icon(..., color=STYLES['icon_...']) として参照できるよう
        # キーを文字列で格納しておく
        styles["icon_color_default"]    = c("text_primary")
        styles["icon_color_primary"]    = c("text_primary")
        styles["icon_color_accent"]     = c("accent_primary")
        styles["icon_color_bookmark"]   = c("color_bookmark")
        styles["icon_color_incognito"]  = c("accent_incognito")
        styles["icon_color_danger"]     = c("color_danger")
        styles["icon_color_warning"]    = c("color_warning")
        styles["icon_color_new_tab"]    = c("text_primary")

        return styles



# =====================================================================
# 組み込みテーマ INI 文字列定数
# （ThemeEngine._ensure_builtin_themes() から使用）
# =====================================================================

_BUILTIN_DEFAULT_INI = """\
; ============================================================
; Strollon Browser - Default (Light) テーマ
; ============================================================
; このファイルは Strollon の組み込みデフォルトテーマです。
; コピーして別名で保存することで独自テーマを作れます。
; [colors] セクションにキーと #RGB/#RRGGBB 形式の色コードを記述します。
; 未記述のキーはデフォルト値にフォールバックします。
; ============================================================

[info]
name        = Default
author      = ABATBeliever
description = Strollonブラウザ標準ライトテーマ
version     = 1.0
strollon_version = {BROWSER_VERSION_SEMANTIC}

[colors]
bg_window           = #fafafa
bg_surface          = #ffffff
bg_surface_dim      = #f9f9f9
bg_surface_alt      = #f7f9fc
bg_sidebar          = #f5f6f8
bg_toolbar          = #f3f4f6
bg_hover            = #f0f3f7
border_default      = #dcdfe3
border_light        = #e0e0e0
border_grid         = #e2e5ea
text_primary        = #2e2e2e
text_secondary      = #5f6368
text_muted          = #666666
text_disabled       = #9aa0a6
text_placeholder    = #999999
accent_primary      = #4a90d9
accent_hover        = #3a7fc4
accent_pressed      = #2f6ca8
accent_dark         = #1f5fa5
accent_light        = #eaf2fb
accent_lighter      = #d6e8fa
accent_win          = #0078d4
accent_win_hover    = #106ebe
accent_incognito    = #8a2be2
color_warning       = #c0392b
color_danger        = #d13438
color_success       = #2e7d32
color_bookmark      = #f4c430
tooltip_bg          = #333333
tooltip_text        = #ffffff
tooltip_border      = #555555
"""

_BUILTIN_DARK_INI = """\
; ============================================================
; Strollon Browser - Dark テーマ
; ============================================================

[info]
name        = Dark
author      = ABATBeliever
description = Strollonブラウザ標準ダークテーマ
version     = 1.0
strollon_version = {BROWSER_VERSION_SEMANTIC}

[colors]
bg_window           = #1a1a1a
bg_surface          = #242424
bg_surface_dim      = #1e1e1e
bg_surface_alt      = #2a2a2a
bg_sidebar          = #1e1e1e
bg_toolbar          = #2d2d2d
bg_hover            = #333333
border_default      = #3a3a3a
border_light        = #444444
border_grid         = #383838
text_primary        = #e8e8e8
text_secondary      = #aaaaaa
text_muted          = #888888
text_disabled       = #555555
text_placeholder    = #606060
accent_primary      = #4a9eff
accent_hover        = #3a8ee0
accent_pressed      = #2a7ec8
accent_dark         = #90c8ff
accent_light        = #1a2a3a
accent_lighter      = #152232
accent_win          = #0078d4
accent_win_hover    = #1a88e0
accent_incognito    = #a060e0
color_warning       = #e05555
color_danger        = #e05555
color_success       = #4caf50
color_bookmark      = #f4c430
tooltip_bg          = #111111
tooltip_text        = #eeeeee
tooltip_border      = #444444
"""

_BUILTIN_SAKURA_INI = """\
; ============================================================
; Strollon Browser - Sakura テーマ
; ============================================================

[info]
name        = Sakura
author      = ABATBeliever
description = 桜をイメージしたピンク系ライトテーマ
version     = 1.0
strollon_version = {BROWSER_VERSION_SEMANTIC}

[colors]
bg_window           = #fff5f7
bg_surface          = #ffffff
bg_surface_dim      = #fff0f3
bg_surface_alt      = #fdf0f4
bg_sidebar          = #fce8ed
bg_toolbar          = #fcd9e2
bg_hover            = #fde8ef
border_default      = #f0b8c8
border_light        = #f5ccd6
border_grid         = #edafc0
text_primary        = #3a1a22
text_secondary      = #7a4458
text_muted          = #9a6070
text_disabled       = #c8a0a8
text_placeholder    = #c0a0a8
accent_primary      = #d46090
accent_hover        = #c05080
accent_pressed      = #a84070
accent_dark         = #8a2050
accent_light        = #fce8ef
accent_lighter      = #fad8e5
accent_win          = #c05080
accent_win_hover    = #a84070
accent_incognito    = #9060c0
color_warning       = #c05050
color_danger        = #d04040
color_success       = #508040
color_bookmark      = #e8a020
tooltip_bg          = #3a1a22
tooltip_text        = #ffffff
tooltip_border      = #8a4060
"""

# =====================================================================
# グローバルシングルトン
# =====================================================================
# StrollonBrowser.py で初期化し、他モジュールは
#   from theme import theme_engine, STYLES
# でアクセスする。

theme_engine: ThemeEngine | None = None
STYLES: dict[str, str] = {}


def init_theme_engine(themes_dir: Path, theme_name: str = "Default") -> ThemeEngine:
    """
    テーマエンジンを初期化してグローバル STYLES を更新する。
    StrollonBrowser.py から呼び出すこと。
    """
    global theme_engine, STYLES
    theme_engine = ThemeEngine(themes_dir)
    theme_engine.load(theme_name)
    STYLES = theme_engine.build_styles()
    return theme_engine


def reload_theme(theme_name: str) -> bool:
    """
    実行中にテーマを切り替える。
    設定ダイアログの「テーマ選択」から呼び出す。
    戻り値: 成功したら True
    """
    global theme_engine, STYLES
    if theme_engine is None:
        return False
    ok = theme_engine.load(theme_name)
    STYLES = theme_engine.build_styles()
    return ok


def get_colors() -> dict[str, str]:
    """現在のカラーパレットをそのまま返す（デバッグ・テーマエディタ用）"""
    if theme_engine is None:
        return dict(DEFAULT_COLORS)
    return dict(theme_engine._colors)
