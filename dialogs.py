"""
Strollon Browser - ダイアログ類
ブックマーク追加、メインダイアログ（設定・履歴・ブックマーク統合）、ダウンロードマネージャー
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer, Slot
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel, QComboBox, QFrame, QMessageBox, QTabWidget,
    QTextEdit, QCheckBox, QRadioButton, QSpinBox, QGroupBox, QScrollArea,
    QFormLayout, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QTreeWidget, QTreeWidgetItem,
    QProgressBar, QListWidget, QListWidgetItem
)
from PySide6.QtWebEngineCore import QWebEngineDownloadRequest

from constants import (
    STYLES, BROWSER_NAME, BROWSER_FULL_NAME, BROWSER_TARGET_ARCHITECTURE,
    DATA_DIR, DOWNLOADS_DIR, USER_AGENT_PRESETS, USER_AGENT_PRESET_NAMES,
    THEMES_DIR, settings, CONFIG_FILE, INSTALL_MODE, log,
    _get_default_downloads_dir
)
import theme as _theme_mod
from browser import CHROMIUM_FLAGS


# =====================================================================
# 履歴・ダウンロード カードウィジェット
# =====================================================================

class _HistoryCard(QWidget):
    """閲覧履歴の1行カードウィジェット。"""

    def __init__(self, title, url, time_str,
                 bg, bg_hover, border, title_color, url_color, time_color,
                 parent=None):
        super().__init__(parent)
        self._bg       = bg
        self._bg_hover = bg_hover
        self._border   = border
        self._hovered  = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(8)

        # 左: タイトル + URL の縦並び
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {title_color}; font-size: 13px; font-weight: 500; background: transparent;")
        title_label.setMaximumWidth(600)
        title_label.setTextInteractionFlags(Qt.NoTextInteraction)
        # 長いタイトルは省略
        title_label.setText(title[:80] + ("…" if len(title) > 80 else ""))
        text_layout.addWidget(title_label)

        url_label = QLabel(url)
        url_label.setStyleSheet(f"color: {url_color}; font-size: 11px; background: transparent;")
        url_label.setText(url[:100] + ("…" if len(url) > 100 else ""))
        url_label.setTextInteractionFlags(Qt.NoTextInteraction)
        text_layout.addWidget(url_label)

        layout.addLayout(text_layout, stretch=1)

        # 右: 時刻
        time_label = QLabel(time_str)
        time_label.setStyleSheet(f"color: {time_color}; font-size: 11px; background: transparent;")
        time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(time_label)

        self._apply_bg()

    def _apply_bg(self):
        bg = self._bg_hover if self._hovered else self._bg
        self.setStyleSheet(
            f"background-color: {bg}; border-bottom: 1px solid {self._border};"
        )

    def enterEvent(self, event):
        self._hovered = True
        self._apply_bg()

    def leaveEvent(self, event):
        self._hovered = False
        self._apply_bg()


class _DownloadCard(QWidget):
    """ダウンロード履歴の1行カードウィジェット。"""

    def __init__(self, filename, url, path, size_text, status_text,
                 is_live, live_pct,
                 bg, bg_hover, border, title_color, url_color, time_color,
                 parent=None):
        super().__init__(parent)
        self._bg       = bg
        self._bg_hover = bg_hover
        self._border   = border
        self._hovered  = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        # 左: ファイル名 + 保存先
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setContentsMargins(0, 0, 0, 0)

        fname_label = QLabel(filename)
        fname_label.setStyleSheet(f"color: {title_color}; font-size: 13px; font-weight: 500; background: transparent;")
        fname_label.setTextInteractionFlags(Qt.NoTextInteraction)
        text_layout.addWidget(fname_label)

        path_label = QLabel(path if path else url)
        path_label.setStyleSheet(f"color: {url_color}; font-size: 11px; background: transparent;")
        disp = (path if path else url)
        path_label.setText(disp[:100] + ("…" if len(disp) > 100 else ""))
        path_label.setTextInteractionFlags(Qt.NoTextInteraction)
        text_layout.addWidget(path_label)
        layout.addLayout(text_layout, stretch=1)

        # 右: サイズ + 進捗
        right_layout = QVBoxLayout()
        right_layout.setSpacing(4)
        right_layout.setContentsMargins(0, 0, 0, 0)

        size_label = QLabel(size_text)
        size_label.setStyleSheet(f"color: {time_color}; font-size: 11px; background: transparent;")
        size_label.setAlignment(Qt.AlignRight)
        right_layout.addWidget(size_label)

        if is_live:
            bar = QProgressBar()
            bar.setValue(live_pct)
            bar.setFixedWidth(100)
            bar.setFixedHeight(14)
            bar.setTextVisible(True)
            right_layout.addWidget(bar, alignment=Qt.AlignRight)
        else:
            if status_text == "完了":
                color = "#2e7d32"
            elif status_text in ("キャンセル", "中断"):
                color = "#c62828"
            else:
                color = time_color
            status_label = QLabel(status_text)
            status_label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 500; background: transparent;")
            status_label.setAlignment(Qt.AlignRight)
            right_layout.addWidget(status_label)

        layout.addLayout(right_layout)
        self._apply_bg()

    def _apply_bg(self):
        bg = self._bg_hover if self._hovered else self._bg
        self.setStyleSheet(
            f"background-color: {bg}; border-bottom: 1px solid {self._border};"
        )

    def enterEvent(self, event):
        self._hovered = True
        self._apply_bg()

    def leaveEvent(self, event):
        self._hovered = False
        self._apply_bg()


# =====================================================================
# ブックマーク追加ダイアログ
# =====================================================================

class AddBookmarkDialog(QDialog):
    """ブックマーク追加ダイアログ（改善版）"""
    
    def __init__(self, title="", url="", folders=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ブックマークに追加")
        self.setMinimumWidth(500)
        self.result_data = None
        self.init_ui(title, url, folders or ['root'])
    
    def init_ui(self, title, url, folders):
        self.setStyleSheet(STYLES['dialog'])
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # タイトル
        title_label = QLabel("<h3>新しいブックマークを追加</h3>")
        layout.addWidget(title_label)
        
        # フォームレイアウト
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        
        self.title_input = QLineEdit(title)
        self.title_input.setPlaceholderText("ブックマークのタイトルを入力")
        form_layout.addRow("タイトル:", self.title_input)
        
        self.url_input = QLineEdit(url)
        self.url_input.setPlaceholderText("URLを入力")
        self.url_input.setReadOnly(True)
        form_layout.addRow("URL:", self.url_input)
        
        self.folder_combo = QComboBox()
        self.folder_combo.addItems(folders)
        form_layout.addRow("フォルダ:", self.folder_combo)
        
        layout.addLayout(form_layout)
        
        # 新しいフォルダ作成
        new_folder_layout = QHBoxLayout()
        self.new_folder_input = QLineEdit()
        self.new_folder_input.setPlaceholderText("新しいフォルダ名を入力（オプション）")
        new_folder_layout.addWidget(self.new_folder_input)
        
        add_folder_btn = QPushButton("フォルダを作成")
        add_folder_btn.setStyleSheet(STYLES['button_secondary'])
        add_folder_btn.clicked.connect(self.add_new_folder)
        new_folder_layout.addWidget(add_folder_btn)
        
        layout.addLayout(new_folder_layout)
        
        # 区切り線
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)
        
        # ボタン
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.setStyleSheet(STYLES['button_secondary'])
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("保存")
        save_btn.setMinimumWidth(100)
        save_btn.setStyleSheet(STYLES['button_primary'])
        save_btn.clicked.connect(self.save_bookmark)
        save_btn.setDefault(True)
        button_layout.addWidget(save_btn)
        
        layout.addLayout(button_layout)
    
    def add_new_folder(self):
        folder_name = self.new_folder_input.text().strip()
        if folder_name and folder_name not in [self.folder_combo.itemText(i) for i in range(self.folder_combo.count())]:
            self.folder_combo.addItem(folder_name)
            self.folder_combo.setCurrentText(folder_name)
            self.new_folder_input.clear()
    
    def save_bookmark(self):
        title = self.title_input.text().strip()
        url = self.url_input.text().strip()
        folder = self.folder_combo.currentText()
        
        if title and url:
            self.result_data = {"title": title, "url": url, "folder": folder}
            self.accept()
        else:
            QMessageBox.warning(self, "入力エラー", "タイトルとURLを入力してください。")
    
    def get_result(self):
        return self.result_data


# =====================================================================
# メインダイアログ（統合）
# =====================================================================

class MainDialog(QDialog):
    """メインダイアログ（ブラウザについて・設定・履歴・ブックマーク・ダウンロード統合）"""

    open_url = Signal(str)
    # 広告フィルター更新完了をバックグラウンドスレッドからメインスレッドへ届けるシグナル
    _adblock_done_signal = Signal(bool, str)

    def __init__(self, history_manager, bookmark_manager, download_manager, parent=None,
                 current_url: str = "", current_title: str = ""):
        super().__init__(parent)
        self.history_manager = history_manager
        self.bookmark_manager = bookmark_manager
        self.download_manager = download_manager
        self.current_url = current_url      # 呼び出し元から渡された現在ページのURL
        self.current_title = current_title  # 呼び出し元から渡された現在ページのタイトル
        self.setWindowTitle(f"{BROWSER_NAME}について")
        self.setMinimumSize(600, 500)

        # 設定を遅延インポート（循環参照回避）
        self.settings = settings

        # シグナルとスロットを接続（スレッドセーフなUI更新）
        self._adblock_done_signal.connect(self._on_adblock_update_done)

        self.init_ui()
    
    def init_ui(self):
        self.setStyleSheet(STYLES['dialog'])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # タブウィジェット
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(STYLES['tab_widget'])
        
        self.tab_widget.addTab(self.create_about_tab(), "ブラウザについて")
        self.tab_widget.addTab(self.create_settings_tab(), "設定")
        self.tab_widget.addTab(self.create_history_tab(), "閲覧履歴")
        self.tab_widget.addTab(self.create_bookmarks_tab(), "ブックマーク")
        self.tab_widget.addTab(self.create_downloads_tab(), "ダウンロード")
        # ブックマークタブ(index=3)に切り替わるたびに add_btn を再評価
        self.tab_widget.currentChanged.connect(self._on_tab_widget_changed)
        
        layout.addWidget(self.tab_widget)
        
        # 閉じるボタン
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(10, 10, 10, 10)
        button_layout.addStretch()
        
        close_button = QPushButton("閉じる")
        close_button.setMinimumWidth(100)
        close_button.setStyleSheet(STYLES['button_primary'])
        close_button.clicked.connect(self.close)
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
    
    def create_about_tab(self):
        """ブラウザについてタブ"""
        widget = QVBoxLayout()
        container = QWidget()
        container.setLayout(widget)
        # ハードコード背景を除去 → テーマの bg_surface を継承
        container.setStyleSheet(
            f"background-color: {STYLES.get('_bg_surface', '')};"
            if '_bg_surface' in STYLES else ""
        )

        widget.setContentsMargins(30, 30, 30, 30)
        widget.setSpacing(20)
        
        from constants import BROWSER_VERSION_NAME
        _te = _theme_mod.theme_engine
        _c = _te.c if _te else lambda k: ""

        title_label = QLabel(f"<h1>{BROWSER_NAME}</h1>")
        title_label.setAlignment(Qt.AlignCenter)
        widget.addWidget(title_label)
        
        version_label = QLabel(f"<h3>バージョン: {BROWSER_VERSION_NAME}</h3>")
        version_label.setAlignment(Qt.AlignCenter)
        widget.addWidget(version_label)
        
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        widget.addWidget(line)
        
        description = QLabel(
            f"<p style='font-size: 11pt;'>{BROWSER_NAME}は、縦タブ対応のシンプルな モダン Web ブラウザです。</p>"
        )
        description.setAlignment(Qt.AlignCenter)
        widget.addWidget(description)
        
        tech_info = QTextEdit()
        tech_info.setReadOnly(True)
        tech_info.setMaximumHeight(220)
        # テーマカラーで塗る
        tech_info.setStyleSheet(
            f"QTextEdit {{ background-color: {_c('bg_surface_dim')}; "
            f"color: {_c('text_primary')}; "
            f"border: 1px solid {_c('border_light')}; "
            f"border-radius: 4px; padding: 8px; }}"
        )
        
        from PySide6 import __version__ as pyside_version
        from PySide6.QtCore import qVersion
        
        mode_label = "XDG" if INSTALL_MODE == "xdg" else "Portable"
        tech_text = f"""• Python バージョン : {sys.version.split()[0]}
• PySide バージョン : {pyside_version}
• Qt バージョン     : {qVersion()}
• 検出アーキテクチャ: {BROWSER_TARGET_ARCHITECTURE}
• インストールモード: {mode_label}
• 設定ファイル      : {CONFIG_FILE}
• データディレクトリ: {DATA_DIR}"""
        tech_info.setPlainText(tech_text)
        widget.addWidget(tech_info)
        
        copyright_label = QLabel(
            f"<p style='color: {_c('text_muted')}; font-size: 9pt;'>"
            "© 2025-2026, ABATBeliever.<br>"
            "Under LGPL v3 License"
            "</p>"
        )
        copyright_label.setAlignment(Qt.AlignCenter)
        widget.addWidget(copyright_label)
        
        widget.addStretch()
        return container
    
    def create_settings_tab(self):
        """設定タブ（スクロール対応・リアルタイム保存）"""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # ---- 一般設定 ----
        general_group = QGroupBox("一般設定")
        general_layout = QVBoxLayout()

        homepage_layout = QHBoxLayout()
        homepage_layout.addWidget(QLabel("ホームページ:"))
        self.homepage_input = QLineEdit()
        self.homepage_input.setText(self.settings.value("homepage", "https://www.google.com"))
        self.homepage_input.textChanged.connect(
            lambda v: self._apply_setting("homepage", v))
        homepage_layout.addWidget(self.homepage_input)
        general_layout.addLayout(homepage_layout)

        startup_layout = QHBoxLayout()
        startup_layout.addWidget(QLabel("起動時:"))
        self.startup_combo = QComboBox()
        self.startup_combo.addItems(["前回のセッションを復元", "ホームページを開く", "新しいタブを開く"])
        self.startup_combo.setCurrentIndex(self.settings.value("startup_action", 0, type=int))
        self.startup_combo.currentIndexChanged.connect(
            lambda v: self._apply_setting("startup_action", v))
        startup_layout.addWidget(self.startup_combo)
        general_layout.addLayout(startup_layout)

        self.save_session_check = QCheckBox("終了時にセッションを保存")
        self.save_session_check.setChecked(self.settings.value("save_session", True, type=bool))
        self.save_session_check.toggled.connect(
            lambda v: self._apply_setting("save_session", v))
        general_layout.addWidget(self.save_session_check)

        theme_select_layout = QHBoxLayout()
        theme_select_layout.addWidget(QLabel("テーマ: *"))
        self.theme_combo = QComboBox()
        _te = _theme_mod.theme_engine
        if _te is not None:
            self.theme_combo.addItems(_te.list_themes())
            current = _te.current_theme()
            idx = self.theme_combo.findText(current)
            if idx >= 0:
                self.theme_combo.setCurrentIndex(idx)
        else:
            self.theme_combo.addItem("Default")
        self.theme_combo.currentIndexChanged.connect(
            lambda v: self._apply_setting("theme", self.theme_combo.currentText()))
        theme_select_layout.addWidget(self.theme_combo)
        general_layout.addLayout(theme_select_layout)

        general_group.setLayout(general_layout)
        layout.addWidget(general_group)

        # ---- 検索設定 ----
        search_group = QGroupBox("検索設定")
        search_layout = QVBoxLayout()

        engine_layout = QHBoxLayout()
        engine_layout.addWidget(QLabel("検索エンジン:"))
        self.search_engine_combo = QComboBox()
        self.search_engine_combo.addItems(["Google", "Bing", "DuckDuckGo", "Yahoo! JAPAN"])
        self.search_engine_combo.setCurrentIndex(self.settings.value("search_engine", 2, type=int))
        self.search_engine_combo.currentIndexChanged.connect(
            lambda v: self._apply_setting("search_engine", v))
        engine_layout.addWidget(self.search_engine_combo)
        search_layout.addLayout(engine_layout)

        search_group.setLayout(search_layout)
        layout.addWidget(search_group)

        # ---- プライバシー設定 ----
        privacy_group = QGroupBox("プライバシー設定")
        privacy_layout = QVBoxLayout()

        self.clear_on_exit_check = QCheckBox("終了時に履歴を削除")
        self.clear_on_exit_check.setChecked(self.settings.value("clear_on_exit", False, type=bool))
        self.clear_on_exit_check.toggled.connect(
            lambda v: self._apply_setting("clear_on_exit", v))
        privacy_layout.addWidget(self.clear_on_exit_check)

        self.do_not_track_check = QCheckBox("Do Not Track (DNT) を送信する")
        self.do_not_track_check.setToolTip(
            "HTTP ヘッダー \'DNT: 1\' を全リクエストに付加します。\n"
            "対応しているサイトに対してトラッキング拒否の意思を伝えます。\n"
            "（サイト側が従う保証はありません）"
        )
        self.do_not_track_check.setChecked(self.settings.value("do_not_track", True, type=bool))
        self.do_not_track_check.toggled.connect(
            lambda v: self._apply_setting("do_not_track", v))
        privacy_layout.addWidget(self.do_not_track_check)

        self.ssl_warn_check = QCheckBox("SSL 証明書エラー時に確認ダイアログを表示する")
        self.ssl_warn_check.setToolTip(
            "自己署名証明書・期限切れ証明書などのエラーが発生した際に、\n"
            "続行するかどうかをユーザーに確認します。\n"
            "無効にすると証明書エラーのあるサイトへのアクセスは自動的にブロックされます。"
        )
        self.ssl_warn_check.setChecked(self.settings.value("ssl_warn_dialog", True, type=bool))
        self.ssl_warn_check.toggled.connect(
            lambda v: self._apply_setting("ssl_warn_dialog", v))
        privacy_layout.addWidget(self.ssl_warn_check)

        privacy_group.setLayout(privacy_layout)
        layout.addWidget(privacy_group)

        # ---- 広告ブロック設定 ----
        adblock_group = QGroupBox("広告ブロック")
        adblock_layout = QVBoxLayout()

        self.adblock_check = QCheckBox("広告ブロックを有効にする")
        self.adblock_check.setToolTip(
            "EasyList / EasyList Japan のフィルタールールに基づき、\n"
            "広告・トラッキングリクエストをブロックします。\n"
            "有効化後、「フィルターを今すぐ更新」でルールを取得してください。"
        )
        self.adblock_check.setChecked(self.settings.value("adblock_enabled", True, type=bool))
        self.adblock_check.toggled.connect(lambda v: self._apply_setting("adblock_enabled", v))
        adblock_layout.addWidget(self.adblock_check)

        # ルール数・最終更新日表示 + 更新ボタン
        adblock_info_layout = QHBoxLayout()
        self._adblock_status_label = QLabel()
        self._refresh_adblock_status_label()
        adblock_info_layout.addWidget(self._adblock_status_label)
        adblock_info_layout.addStretch()

        update_filter_btn = QPushButton("フィルターを今すぐ更新")
        update_filter_btn.setToolTip("インターネットから最新の広告フィルターリストをダウンロードします")
        update_filter_btn.clicked.connect(self._update_adblock_filters)
        adblock_info_layout.addWidget(update_filter_btn)
        adblock_layout.addLayout(adblock_info_layout)

        # ---- ホワイトリスト編集 ----
        allowlist_label = QLabel("ブロック除外リスト（URL に含まれる文字列）:")
        allowlist_label.setToolTip(
            "ここに登録した文字列を URL に含むリクエストは、\n"
            "広告ブロックフィルターに一致してもブロックされません。\n"
            "例: googlevideo.com/videoplayback"
        )
        adblock_layout.addWidget(allowlist_label)

        self._allowlist_widget = QListWidget()
        self._allowlist_widget.setMaximumHeight(120)
        self._allowlist_widget.setToolTip("選択して「削除」ボタンで除外できます")
        self._reload_allowlist_widget()
        adblock_layout.addWidget(self._allowlist_widget)

        allowlist_edit_layout = QHBoxLayout()
        self._allowlist_input = QLineEdit()
        self._allowlist_input.setPlaceholderText("除外する URL 文字列を入力（例: example.com/api/）")
        self._allowlist_input.returnPressed.connect(self._allowlist_add)
        allowlist_edit_layout.addWidget(self._allowlist_input)

        allowlist_add_btn = QPushButton("追加")
        allowlist_add_btn.setFixedWidth(60)
        allowlist_add_btn.clicked.connect(self._allowlist_add)
        allowlist_edit_layout.addWidget(allowlist_add_btn)

        allowlist_del_btn = QPushButton("削除")
        allowlist_del_btn.setFixedWidth(60)
        allowlist_del_btn.clicked.connect(self._allowlist_remove)
        allowlist_edit_layout.addWidget(allowlist_del_btn)

        allowlist_reset_btn = QPushButton("既定値に戻す")
        allowlist_reset_btn.clicked.connect(self._allowlist_reset)
        allowlist_edit_layout.addWidget(allowlist_reset_btn)

        adblock_layout.addLayout(allowlist_edit_layout)

        adblock_group.setLayout(adblock_layout)
        layout.addWidget(adblock_group)
        download_group = QGroupBox("ダウンロード設定")
        download_layout = QVBoxLayout()

        download_dir_layout = QHBoxLayout()
        download_dir_layout.addWidget(QLabel("保存先:"))
        self.download_dir_input = QLineEdit()
        _dl_default = str(_get_default_downloads_dir())
        _dl_val = self.settings.value("download_dir", "")
        self.download_dir_input.setText(_dl_val if _dl_val else _dl_default)
        self.download_dir_input.textChanged.connect(
            lambda v: self._apply_setting("download_dir", v))
        download_dir_layout.addWidget(self.download_dir_input)

        browse_btn = QPushButton("参照")
        browse_btn.clicked.connect(self.browse_download_dir)
        download_dir_layout.addWidget(browse_btn)
        download_layout.addLayout(download_dir_layout)

        self.ask_download_check = QCheckBox("ダウンロード時に保存場所を確認")
        self.ask_download_check.setChecked(self.settings.value("ask_download", True, type=bool))
        self.ask_download_check.toggled.connect(
            lambda v: self._apply_setting("ask_download", v))
        download_layout.addWidget(self.ask_download_check)

        download_group.setLayout(download_layout)
        layout.addWidget(download_group)

        # ---- 詳細設定 ----
        advanced_group = QGroupBox("詳細設定")
        advanced_layout = QVBoxLayout()

        self.javascript_check = QCheckBox("JavaScript を有効にする *")
        self.javascript_check.setChecked(self.settings.value("enable_javascript", True, type=bool))
        self.javascript_check.toggled.connect(
            lambda v: self._apply_setting("enable_javascript", v))
        advanced_layout.addWidget(self.javascript_check)

        self.fullscreen_check = QCheckBox("全画面表示を許可 *")
        self.fullscreen_check.setChecked(self.settings.value("allow_fullscreen", True, type=bool))
        self.fullscreen_check.toggled.connect(
            lambda v: self._apply_setting("allow_fullscreen", v))
        advanced_layout.addWidget(self.fullscreen_check)

        self.images_check = QCheckBox("画像を自動的に読み込む *")
        self.images_check.setChecked(self.settings.value("auto_load_images", True, type=bool))
        self.images_check.toggled.connect(
            lambda v: self._apply_setting("auto_load_images", v))
        advanced_layout.addWidget(self.images_check)

        self.hardware_acceleration_check = QCheckBox("ハードウェアアクセラレーションを有効にする *")
        self.hardware_acceleration_check.setChecked(
            self.settings.value("enable_hardware_acceleration", True, type=bool))
        self.hardware_acceleration_check.toggled.connect(
            lambda v: self._apply_setting("enable_hardware_acceleration", v))
        advanced_layout.addWidget(self.hardware_acceleration_check)

        advanced_group.setLayout(advanced_layout)
        layout.addWidget(advanced_group)

        # ---- UserAgent 設定 ----
        useragent_group = QGroupBox("UserAgent設定")
        useragent_layout = QVBoxLayout()

        ua_preset_layout = QHBoxLayout()
        ua_preset_layout.addWidget(QLabel("プリセット: *"))
        self.ua_preset_combo = QComboBox()
        self.ua_preset_combo.addItems(USER_AGENT_PRESET_NAMES)
        self.ua_preset_combo.setCurrentIndex(self.settings.value("ua_preset", 0, type=int))
        self.ua_preset_combo.currentIndexChanged.connect(self.on_ua_preset_changed)
        ua_preset_layout.addWidget(self.ua_preset_combo)
        useragent_layout.addLayout(ua_preset_layout)

        self.ua_custom_input = QLineEdit()
        self.ua_custom_input.setPlaceholderText("カスタムUserAgentを入力")
        self.ua_custom_input.setText(self.settings.value("ua_custom", ""))
        self.ua_custom_input.textChanged.connect(
            lambda v: self._apply_setting("ua_custom", v))
        useragent_layout.addWidget(self.ua_custom_input)

        useragent_group.setLayout(useragent_layout)
        layout.addWidget(useragent_group)

        # ---- 実験的機能 ----
        experimental_group = QGroupBox("実験的機能")
        experimental_layout = QVBoxLayout()
        experimental_layout.addSpacing(8)

        flags_label = QLabel("実験的機能 ( * = 再起動が必要):")
        flags_label.setStyleSheet("font-weight: bold; color: #c0392b;")
        experimental_layout.addWidget(flags_label)

        warn_label = QLabel("⚠ 予期せぬ結果を招く可能性があります ⚠")
        warn_label.setStyleSheet("color: #888; font-size: 10px;")
        warn_label.setWordWrap(True)
        experimental_layout.addWidget(warn_label)

        self._flag_checks: dict[str, QCheckBox] = {}
        for key, (flag_str, desc) in CHROMIUM_FLAGS.items():
            cb = QCheckBox(desc + " *")
            cb.setToolTip(flag_str)
            cb.setChecked(self.settings.value(key, False, type=bool))
            cb.toggled.connect(lambda v, k=key: self._apply_setting(k, v))
            experimental_layout.addWidget(cb)
            self._flag_checks[key] = cb

        experimental_group.setLayout(experimental_layout)
        layout.addWidget(experimental_group)

        # ---- 下部ボタン（スクロールエリア内の最下部）----
        layout.addStretch()

        bottom_sep = QFrame()
        bottom_sep.setFrameShape(QFrame.HLine)
        bottom_sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(bottom_sep)

        reset_btn = QPushButton("既定値に戻す")
        reset_btn.setStyleSheet(STYLES['button_primary'])
        reset_btn.clicked.connect(self.reset_settings_to_default)
        layout.addWidget(reset_btn)

        scroll_area.setWidget(widget)
        return scroll_area
    
    def create_history_tab(self):
        """閲覧履歴タブ（Chromium 風カードリスト）"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 検索バー
        search_bar = QWidget()
        search_bar.setStyleSheet(
            f"background-color: {STYLES.get('history_bg_surface', '#fff')};"
            f"border-bottom: 1px solid {STYLES.get('history_border', '#ddd')};"
        )
        sb_layout = QHBoxLayout(search_bar)
        sb_layout.setContentsMargins(10, 8, 10, 8)

        self.history_search_input = QLineEdit()
        self.history_search_input.setPlaceholderText("履歴を検索...")
        self.history_search_input.textChanged.connect(self.search_history)
        sb_layout.addWidget(self.history_search_input)

        clear_history_btn = QPushButton("履歴を全削除")
        clear_history_btn.setStyleSheet(STYLES['button_secondary'])
        clear_history_btn.clicked.connect(self.clear_history)
        sb_layout.addWidget(clear_history_btn)
        layout.addWidget(search_bar)

        # カードリスト
        self.history_list = QListWidget()
        self.history_list.setStyleSheet(STYLES.get('history_list', ''))
        self.history_list.setSpacing(0)
        self.history_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        layout.addWidget(self.history_list)

        self.load_history()
        return widget
    
    def create_bookmarks_tab(self):
        """ブックマークタブ"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        # ツールバー
        toolbar_layout = QHBoxLayout()

        self.add_bookmark_btn = QPushButton("新規追加")
        self.add_bookmark_btn.setStyleSheet(STYLES['button_primary'])
        self.add_bookmark_btn.setToolTip("現在開いているページをブックマークに追加します")
        self.add_bookmark_btn.clicked.connect(self.add_current_page_bookmark)
        self._update_add_bookmark_btn()  # 初期状態を設定
        toolbar_layout.addWidget(self.add_bookmark_btn)

        delete_btn = QPushButton("削除")
        delete_btn.setStyleSheet(STYLES['button_secondary'])
        delete_btn.clicked.connect(self.delete_selected_bookmark)
        toolbar_layout.addWidget(delete_btn)

        toolbar_layout.addStretch()

        export_btn = QPushButton("エクスポート")
        export_btn.setStyleSheet(STYLES['button_secondary'])
        export_btn.clicked.connect(self.export_bookmarks)
        toolbar_layout.addWidget(export_btn)

        import_btn = QPushButton("インポート")
        import_btn.setStyleSheet(STYLES['button_secondary'])
        import_btn.clicked.connect(self.import_bookmarks)
        toolbar_layout.addWidget(import_btn)

        layout.addLayout(toolbar_layout)

        # ブックマークツリー
        self.bookmark_tree = QTreeWidget()
        self.bookmark_tree.setHeaderLabels(["タイトル", "URL"])
        self.bookmark_tree.setColumnWidth(0, 300)
        self.bookmark_tree.itemDoubleClicked.connect(self.on_bookmark_item_double_clicked)
        layout.addWidget(self.bookmark_tree)

        self.load_bookmarks()

        return widget
    
    def browse_download_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self, "ダウンロードフォルダを選択",
            self.download_dir_input.text()
        )
        if directory:
            self.download_dir_input.setText(directory)
    
    def on_ua_preset_changed(self, index):
        if index < 5:
            self.ua_custom_input.setEnabled(False)
            self.ua_custom_input.setPlaceholderText(USER_AGENT_PRESETS.get(index, ""))
        else:
            self.ua_custom_input.setEnabled(True)
    
    def showEvent(self, event):
        """ダイアログが表示されるたびに広告ブロックのルール数を最新状態に更新する。"""
        super().showEvent(event)
        if hasattr(self, "_adblock_status_label"):
            self._refresh_adblock_status_label()

    def _apply_setting(self, key: str, value):
        """
        リアルタイム設定反映。
        各 widget の変更シグナルから呼ばれ、設定を即時保存・反映する。
        """
        self.settings.setValue(key, value)
        self.settings.sync()

        # ブラウザ本体に即時反映（再起動不要な設定のみ apply_settings で拾われる）
        from browser import VerticalTabBrowser
        browser = self.parent()
        while browser and not isinstance(browser, VerticalTabBrowser):
            browser = browser.parent()
        if browser:
            browser.apply_settings()

        log(f"[INFO] Setting changed: {key} = {value}")

    # ------------------------------------------------------------------
    # ホワイトリスト (ブロック除外リスト) 操作
    # ------------------------------------------------------------------

    def _get_adblock_manager(self):
        from browser import VerticalTabBrowser
        browser = self.parent()
        while browser and not isinstance(browser, VerticalTabBrowser):
            browser = browser.parent()
        if browser and hasattr(browser, "adblock_manager"):
            return browser.adblock_manager
        return None

    def _reload_allowlist_widget(self):
        self._allowlist_widget.clear()
        mgr = self._get_adblock_manager()
        entries = mgr.get_allowlist() if mgr else []
        for entry in entries:
            self._allowlist_widget.addItem(QListWidgetItem(entry))

    def _allowlist_add(self):
        text = self._allowlist_input.text().strip()
        if not text:
            return
        mgr = self._get_adblock_manager()
        if mgr is None:
            return
        entries = mgr.get_allowlist()
        if text not in entries:
            entries.append(text)
            mgr.save_allowlist(entries)
        self._allowlist_input.clear()
        self._reload_allowlist_widget()
        log(f"[INFO] AdBlock allowlist: added '{text}'")

    def _allowlist_remove(self):
        row = self._allowlist_widget.currentRow()
        if row < 0:
            return
        item = self._allowlist_widget.item(row)
        if item is None:
            return
        text = item.text()
        mgr = self._get_adblock_manager()
        if mgr is None:
            return
        entries = mgr.get_allowlist()
        if text in entries:
            entries.remove(text)
            mgr.save_allowlist(entries)
        self._reload_allowlist_widget()
        log(f"[INFO] AdBlock allowlist: removed '{text}'")

    def _allowlist_reset(self):
        mgr = self._get_adblock_manager()
        if mgr is None:
            return
        mgr.save_allowlist(list(mgr._DEFAULT_ALLOWLIST))
        self._reload_allowlist_widget()
        log("[INFO] AdBlock allowlist: reset to defaults")

    def _refresh_adblock_status_label(self):
        """広告ブロックのルール数・最終更新日ラベルを更新する。"""
        from browser import VerticalTabBrowser
        browser = self.parent()
        while browser and not isinstance(browser, VerticalTabBrowser):
            browser = browser.parent()

        rule_count = 0
        blocked = 0
        if browser and hasattr(browser, "adblock_manager"):
            rule_count = browser.adblock_manager.rule_count()
            blocked   = browser.adblock_manager.block_count()

        last_updated = self.settings.value("adblock_last_updated", "")
        if last_updated:
            try:
                import datetime
                dt = datetime.datetime.fromisoformat(last_updated)
                last_updated_str = dt.strftime("%Y/%m/%d %H:%M")
            except Exception:
                last_updated_str = last_updated
        else:
            last_updated_str = "未取得"

        if rule_count > 0:
            text = (f"ルール数: {rule_count:,} 件　最終更新: {last_updated_str}\n"
                    f"ブロック実績: {blocked:,} 件")
        else:
            text = "フィルター未取得　（「今すぐ更新」でダウンロードしてください）"
        self._adblock_status_label.setText(text)

    def _update_adblock_filters(self):
        """広告フィルターを非同期でダウンロード・更新する。"""
        from browser import VerticalTabBrowser
        browser = self.parent()
        while browser and not isinstance(browser, VerticalTabBrowser):
            browser = browser.parent()

        if not browser or not hasattr(browser, "adblock_manager"):
            QMessageBox.warning(self, "エラー", "ブラウザインスタンスが見つかりません。")
            return

        sender_btn = self.sender()
        if sender_btn:
            sender_btn.setEnabled(False)
            sender_btn.setText("ダウンロード中...")

        # バックグラウンドスレッド → メインスレッドの安全な橋渡しに
        # Signal を使う。Signal は emit() がスレッドセーフで、
        # Qt のイベントループ経由でメインスレッドのスロットに届く。
        def on_done(success, message):
            self._adblock_done_signal.emit(success, message)

        # sender_btn をインスタンス変数に退避（クロージャがGCされないように）
        self._adblock_update_btn = sender_btn
        browser.adblock_manager.update_filters(callback=on_done)

    @Slot(bool, str)
    def _on_adblock_update_done(self, success, message):
        """バックグラウンド完了シグナルをメインスレッドで受け取るスロット。"""
        btn = getattr(self, "_adblock_update_btn", None)
        if btn:
            btn.setEnabled(True)
            btn.setText("フィルターを今すぐ更新")
            self._adblock_update_btn = None
        self._refresh_adblock_status_label()
        if success:
            QMessageBox.information(self, "広告フィルター更新", message)
        else:
            QMessageBox.warning(self, "広告フィルター更新", message)


    def reset_settings_to_default(self):
        """設定を既定値に戻す（各 widget を既定値にセット → シグナル経由でリアルタイム保存）"""
        reply = QMessageBox.question(
            self, "確認", "全ての設定を既定値に戻しますか？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.homepage_input.setText("strollon://start")
            self.startup_combo.setCurrentIndex(0)
            self.save_session_check.setChecked(True)
            self.search_engine_combo.setCurrentIndex(2)  # Duck
            self.clear_on_exit_check.setChecked(False)
            self.do_not_track_check.setChecked(True)
            self.download_dir_input.setText(str(_get_default_downloads_dir()))
            self.ask_download_check.setChecked(True)
            self.javascript_check.setChecked(True)
            self.fullscreen_check.setChecked(True)
            self.images_check.setChecked(True)
            self.hardware_acceleration_check.setChecked(True)
            self.ua_preset_combo.setCurrentIndex(0)
            self.ua_custom_input.setText("")
            default_idx = self.theme_combo.findText("Default")
            if default_idx >= 0:
                self.theme_combo.setCurrentIndex(default_idx)
            for cb in self._flag_checks.values():
                cb.setChecked(False)
            log("[INFO] Settings reset to defaults")

    def load_history(self):
        history = self.history_manager.get_history(500)
        self.display_history(history)

    def search_history(self, query):
        if query:
            history = self.history_manager.search_history(query)
        else:
            history = self.history_manager.get_history(500)
        self.display_history(history)

    def display_history(self, history):
        """履歴を日付グループ分けしてカードリスト形式で表示する。"""
        from datetime import datetime, date, timedelta, timezone
        from PySide6.QtCore import QSize

        self.history_list.clear()

        today     = date.today()
        yesterday = today - timedelta(days=1)
        current_group = None

        for url, title, visit_time, visit_count in history:
            try:
                # SQLite の CURRENT_TIMESTAMP は UTC で保存されるため
                # ローカルタイムゾーンに変換して表示する
                dt_utc = datetime.fromisoformat(visit_time).replace(tzinfo=timezone.utc)
                dt     = dt_utc.astimezone()          # システムのローカルTZに変換
                d      = dt.date()
                if d == today:
                    group_label = "今日"
                elif d == yesterday:
                    group_label = "昨日"
                else:
                    group_label = f"{d.month}月{d.day}日"
                time_str = dt.strftime("%H:%M")
            except Exception:
                group_label = "日付不明"
                time_str    = visit_time or ""

            if group_label != current_group:
                current_group = group_label
                header_item = QListWidgetItem()
                header_item.setData(Qt.UserRole, {"type": "header"})
                header_item.setFlags(Qt.NoItemFlags)
                self.history_list.addItem(header_item)
                header_widget = QLabel(group_label)
                header_widget.setStyleSheet(STYLES.get("history_group_header", ""))
                self.history_list.setItemWidget(header_item, header_widget)
                header_item.setSizeHint(QSize(0, 28))

            card_item = QListWidgetItem()
            card_item.setData(Qt.UserRole, {"type": "entry", "url": url})
            self.history_list.addItem(card_item)
            card = _HistoryCard(
                title       = title or url,
                url         = url,
                time_str    = time_str,
                bg          = STYLES.get("history_bg_surface", "#fff"),
                bg_hover    = STYLES.get("history_bg_hover", "#f0f3f7"),
                border      = STYLES.get("history_border", "#ddd"),
                title_color = STYLES.get("history_title_color", "#2e2e2e"),
                url_color   = STYLES.get("history_url_color", "#666"),
                time_color  = STYLES.get("history_time_color", "#666"),
            )
            self.history_list.setItemWidget(card_item, card)
            card_item.setSizeHint(QSize(0, 52))

        try:
            self.history_list.itemClicked.disconnect(self._on_history_card_clicked)
        except (RuntimeError, TypeError):
            pass
        self.history_list.itemClicked.connect(self._on_history_card_clicked)

    def _on_history_card_clicked(self, item):
        data = item.data(Qt.UserRole)
        if data and data.get("type") == "entry":
            self.open_url.emit(data["url"])
            self.close()

    def on_history_item_double_clicked(self, index):
        """後方互換"""
        pass
    
    def clear_history(self):
        reply = QMessageBox.question(
            self, "確認", "本当に全ての履歴を削除しますか？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.history_manager.clear_history()
            self.load_history()
    
    def load_bookmarks(self):
        self.bookmark_tree.clear()
        folders = {}
        
        bookmarks = self.bookmark_manager.get_bookmarks()
        
        for bm_id, title, url, folder in bookmarks:
            if folder not in folders:
                folder_item = QTreeWidgetItem(self.bookmark_tree, [folder, ""])
                folder_item.setData(0, Qt.UserRole, {"type": "folder", "name": folder})
                folders[folder] = folder_item
            
            bookmark_item = QTreeWidgetItem(folders[folder], [title, url])
            bookmark_item.setData(0, Qt.UserRole, {"type": "bookmark", "id": bm_id, "url": url})
        
        self.bookmark_tree.expandAll()
    
    def _on_tab_widget_changed(self, index):
        """タブ切り替え時の処理"""
        if index == 3:  # ブックマークタブ
            self._update_add_bookmark_btn()

    def _update_add_bookmark_btn(self):
        """「新規追加」ボタンの有効/無効を current_url の状態で再評価する"""
        enabled = bool(
            self.current_url
            and not self.current_url.startswith("about:")
            and not self.current_url.startswith("chrome:")
        )
        if hasattr(self, 'add_bookmark_btn'):
            self.add_bookmark_btn.setEnabled(enabled)

    def add_current_page_bookmark(self):
        """現在のページをブックマークに追加する（AddBookmarkDialog を使用）"""
        if not self.current_url:
            return
        folders = self.bookmark_manager.get_folders()
        dialog = AddBookmarkDialog(
            self.current_title or self.current_url,
            self.current_url,
            folders,
            self
        )
        if dialog.exec():
            result = dialog.get_result()
            title, url, folder = result["title"], result["url"], result["folder"]
            self.bookmark_manager.add_bookmark(title, url, folder)
            self.load_bookmarks()  # ツリーを更新

    def delete_selected_bookmark(self):
        current_item = self.bookmark_tree.currentItem()
        if current_item:
            data = current_item.data(0, Qt.UserRole)
            if data and data["type"] == "bookmark":
                reply = QMessageBox.question(
                    self, "確認", "このブックマークを削除しますか？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self.bookmark_manager.delete_bookmark(data["id"])
                    self.load_bookmarks()
    
    def on_bookmark_item_double_clicked(self, item, column):
        data = item.data(0, Qt.UserRole)
        if data and data["type"] == "bookmark":
            self.open_url.emit(data["url"])
            self.close()
    
    def export_bookmarks(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "ブックマークをエクスポート", 
            str(DATA_DIR / "bookmarks.html"),
            "HTML Files (*.html)"
        )
        if filepath:
            self.bookmark_manager.export_html(filepath)
            QMessageBox.information(self, "完了", "ブックマークをエクスポートしました。")
    
    def import_bookmarks(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "ブックマークをインポート",
            str(Path.home()),
            "HTML Files (*.html)"
        )
        if filepath:
            if self.bookmark_manager.import_html(filepath):
                self.load_bookmarks()
                QMessageBox.information(self, "完了", "ブックマークをインポートしました。")
            else:
                QMessageBox.warning(self, "エラー", "ブックマークのインポートに失敗しました。")
    
    def create_downloads_tab(self):
        """ダウンロードタブ（カードリスト形式）"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ツールバー
        toolbar = QWidget()
        toolbar.setStyleSheet(
            f"background-color: {STYLES.get('history_bg_surface', '#fff')};"
            f"border-bottom: 1px solid {STYLES.get('history_border', '#ddd')};"
        )
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(10, 8, 10, 8)
        clear_history_btn = QPushButton("履歴をクリア")
        clear_history_btn.setStyleSheet(STYLES['button_secondary'])
        clear_history_btn.clicked.connect(self.clear_download_history)
        tb_layout.addStretch()
        tb_layout.addWidget(clear_history_btn)
        layout.addWidget(toolbar)

        # カードリスト
        self.download_list = QListWidget()
        self.download_list.setStyleSheet(STYLES.get('history_list', ''))
        self.download_list.setSpacing(0)
        self.download_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        layout.addWidget(self.download_list)

        # 自動更新タイマー（0.5秒ごと）
        self._download_refresh_timer = QTimer(self)
        self._download_refresh_timer.setInterval(500)
        self._download_refresh_timer.timeout.connect(self.load_downloads)
        self._download_refresh_timer.start()

        self.load_downloads()
        return widget


    def load_downloads(self):
        """ダウンロードデータをカードリストに表示する。"""
        from PySide6.QtWebEngineCore import QWebEngineDownloadRequest
        from PySide6.QtCore import QSize

        live_by_url = {}
        for dl in self.download_manager.get_downloads():
            live_by_url[dl.url().toString()] = dl

        download_history = self.download_manager.get_download_history(100)

        # スクロール位置を保持
        scrollbar = self.download_list.verticalScrollBar()
        scroll_pos = scrollbar.value()

        self.download_list.clear()

        for filename, url, download_path, total_bytes, received_bytes, state, start_time, finish_time in download_history:
            # 進捗・状態テキストを計算
            live = live_by_url.get(url)
            if live and live.state().value == 1:  # DownloadInProgress
                live_total = live.totalBytes()
                live_recv  = live.receivedBytes()
                pct = int(live_recv / live_total * 100) if live_total > 0 else 0
                status_text = f"{pct}%"
                is_live = True
                live_pct = pct
            else:
                is_live = False
                live_pct = 0
                if total_bytes and total_bytes > 0:
                    pct = int((received_bytes or 0) / total_bytes * 100)
                else:
                    pct = 100 if state == 2 else 0
                if pct >= 100 or state == 2:
                    status_text = "完了"
                elif state == 3:
                    status_text = "キャンセル"
                elif state == 4:
                    status_text = "中断"
                else:
                    status_text = f"{pct}%"

            size_text = f"{total_bytes / (1024*1024):.1f} MB" if (total_bytes and total_bytes > 0) else "不明"

            card_item = QListWidgetItem()
            card_item.setData(Qt.UserRole, {
                "filename": filename, "url": url or "", "path": download_path or ""
            })
            self.download_list.addItem(card_item)

            card = _DownloadCard(
                filename    = filename,
                url         = url or "",
                path        = download_path or "",
                size_text   = size_text,
                status_text = status_text,
                is_live     = is_live,
                live_pct    = live_pct,
                bg          = STYLES.get("history_bg_surface", "#fff"),
                bg_hover    = STYLES.get("history_bg_hover", "#f0f3f7"),
                border      = STYLES.get("history_border", "#ddd"),
                title_color = STYLES.get("history_title_color", "#2e2e2e"),
                url_color   = STYLES.get("history_url_color", "#666"),
                time_color  = STYLES.get("history_time_color", "#666"),
            )
            self.download_list.setItemWidget(card_item, card)
            card_item.setSizeHint(QSize(0, 64))

        scrollbar.setValue(scroll_pos)
    
    def clear_download_history(self):
        """ダウンロード履歴をクリア"""
        reply = QMessageBox.question(
            self, "確認", "完了・キャンセル・中断済みのダウンロード履歴を削除しますか？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.download_manager.clear_download_history()
            self.load_downloads()
    
    def show_download_tab(self):
        """ダウンロードタブを表示"""
        self.tab_widget.setCurrentIndex(4)

    def show_settings_tab(self):
        """設定タブを表示"""
        self.tab_widget.setCurrentIndex(1)

    def show_about_tab(self):
        """ブラウザについてタブを表示"""
        self.tab_widget.setCurrentIndex(0)


# =====================================================================
# ダウンロードマネージャーダイアログ
# =====================================================================

class DownloadDialog(QDialog):
    """ダウンロードマネージャーダイアログ"""
    
    def __init__(self, download_manager, parent=None):
        super().__init__(parent)
        self.download_manager = download_manager
        self.setWindowTitle("ダウンロードマネージャー")
        self.setMinimumSize(700, 400)
        self.init_ui()
    
    def init_ui(self):
        self.setStyleSheet(STYLES['dialog'])
        layout = QVBoxLayout(self)
        
        self.download_table = QTableWidget()
        self.download_table.setColumnCount(4)
        self.download_table.setHorizontalHeaderLabels(["ファイル名", "URL", "進捗", "状態"])
        self.download_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.download_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.download_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.download_table)
        
        button_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("更新")
        refresh_btn.setStyleSheet(STYLES['button_secondary'])
        refresh_btn.clicked.connect(self.refresh_downloads)
        button_layout.addWidget(refresh_btn)
        
        button_layout.addStretch()
        
        close_btn = QPushButton("閉じる")
        close_btn.setStyleSheet(STYLES['button_primary'])
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        
        self.refresh_downloads()
    
    def refresh_downloads(self):
        downloads = self.download_manager.get_downloads()
        self.download_table.setRowCount(len(downloads))
        
        for i, download in enumerate(downloads):
            self.download_table.setItem(i, 0, QTableWidgetItem(download.downloadFileName()))
            self.download_table.setItem(i, 1, QTableWidgetItem(download.url().toString()))
            
            progress = QProgressBar()
            progress.setValue(int(download.receivedBytes() / max(download.totalBytes(), 1) * 100))
            self.download_table.setCellWidget(i, 2, progress)
            
            state_map = {
                QWebEngineDownloadRequest.DownloadRequested: "要求中",
                QWebEngineDownloadRequest.DownloadInProgress: "ダウンロード中",
                QWebEngineDownloadRequest.DownloadCompleted: "完了",
                QWebEngineDownloadRequest.DownloadCancelled: "キャンセル",
                QWebEngineDownloadRequest.DownloadInterrupted: "中断"
            }
            state = state_map.get(download.state(), "不明")
            self.download_table.setItem(i, 3, QTableWidgetItem(state))


# =====================================================================
# ページ保存ダイアログ
# =====================================================================

class SavePageDialog(QDialog):
    """ページ保存ダイアログ（PNG / PDF 選択）"""

    def __init__(self, web_view, parent=None):
        super().__init__(parent)
        self.web_view = web_view
        self._is_saving = False
        self.setWindowTitle("ページを保存")
        self.setMinimumWidth(420)
        self.setWindowFlags(Qt.Dialog)
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet(STYLES['dialog'])

        # ---- 選択画面 ----
        self.select_widget = QWidget()
        select_layout = QVBoxLayout(self.select_widget)
        select_layout.setContentsMargins(20, 20, 20, 20)
        select_layout.setSpacing(14)

        title_label = QLabel("<h3>ページを保存</h3>")
        select_layout.addWidget(title_label)

        format_group = QGroupBox("保存形式")
        format_layout = QVBoxLayout()
        self.png_radio = QRadioButton("PNG 画像  （現在の表示エリアをキャプチャ）")
        self.pdf_radio = QRadioButton("PDF ドキュメント  （ページ全体を出力）")
        self.png_radio.setChecked(True)
        format_layout.addWidget(self.png_radio)
        format_layout.addWidget(self.pdf_radio)
        format_group.setLayout(format_layout)
        select_layout.addWidget(format_group)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        select_layout.addWidget(line)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.setStyleSheet(STYLES['button_secondary'])
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        save_btn = QPushButton("次へ（保存先を指定）")
        save_btn.setMinimumWidth(160)
        save_btn.setStyleSheet(STYLES['button_primary'])
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.proceed_to_save)
        button_layout.addWidget(save_btn)
        select_layout.addLayout(button_layout)

        # ---- 出力中画面 ----
        self.saving_widget = QWidget()
        saving_layout = QVBoxLayout(self.saving_widget)
        saving_layout.setContentsMargins(20, 30, 20, 30)
        saving_layout.setSpacing(20)

        saving_title = QLabel("<h3>出力中です...</h3>")
        saving_title.setAlignment(Qt.AlignCenter)
        saving_layout.addWidget(saving_title)

        self.saving_info_label = QLabel("")
        self.saving_info_label.setAlignment(Qt.AlignCenter)
        self.saving_info_label.setStyleSheet("color: #666666; font-size: 10pt;")
        self.saving_info_label.setWordWrap(True)
        saving_layout.addWidget(self.saving_info_label)

        saving_progress = QProgressBar()
        saving_progress.setMinimum(0)
        saving_progress.setMaximum(0)
        saving_layout.addWidget(saving_progress)

        note_label = QLabel("完了するまでこのウィンドウは閉じられません。")
        note_label.setAlignment(Qt.AlignCenter)
        note_label.setStyleSheet("color: #999999; font-size: 9pt;")
        saving_layout.addWidget(note_label)

        # ---- 重ねて配置 ----
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self.select_widget)
        outer_layout.addWidget(self.saving_widget)
        self.saving_widget.setVisible(False)

    def _show_saving_screen(self, filepath):
        self._is_saving = True
        self.saving_info_label.setText(f"保存先: {filepath}")
        self.select_widget.setVisible(False)
        self.saving_widget.setVisible(True)
        self.setMinimumHeight(0)
        self.adjustSize()

    def _restore_select_screen(self):
        self._is_saving = False
        self.saving_widget.setVisible(False)
        self.select_widget.setVisible(True)
        self.adjustSize()

    def closeEvent(self, event):
        if self._is_saving:
            event.ignore()
        else:
            event.accept()

    def proceed_to_save(self):
        if self.png_radio.isChecked():
            self._save_png()
        else:
            self._save_pdf()

    def _save_png(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "PNG として保存", "", "PNG Images (*.png)")
        if not filepath:
            return
        if not filepath.lower().endswith(".png"):
            filepath += ".png"
        self._show_saving_screen(filepath)
        pixmap = self.web_view.grab()
        self._is_saving = False
        if pixmap.save(filepath, "PNG"):
            QMessageBox.information(self, "保存完了", f"PNG を保存しました:\n{filepath}")
            self.accept()
        else:
            QMessageBox.warning(self, "エラー", "PNG の保存に失敗しました。")
            self._restore_select_screen()

    def _save_pdf(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "PDF として保存", "", "PDF Documents (*.pdf)")
        if not filepath:
            return
        if not filepath.lower().endswith(".pdf"):
            filepath += ".pdf"
        self._show_saving_screen(filepath)
        try:
            self.web_view.page().pdfPrintingFinished.connect(self._on_pdf_finished)
        except Exception:
            pass
        self.web_view.page().printToPdf(filepath)

    def _on_pdf_finished(self, filepath, success):
        try:
            self.web_view.page().pdfPrintingFinished.disconnect(self._on_pdf_finished)
        except Exception:
            pass
        self._is_saving = False
        if success:
            QMessageBox.information(self, "保存完了", f"PDF を保存しました:\n{filepath}")
            self.accept()
        else:
            QMessageBox.warning(self, "エラー", "PDF の保存に失敗しました。")
            self._restore_select_screen()


# =====================================================================
# ページ内検索ダイアログ
# =====================================================================

class FindDialog(QDialog):
    """ページ内検索ダイアログ（Chrome風・リアルタイム検索）"""
    
    def __init__(self, web_view, parent=None):
        super().__init__(parent)
        self.web_view = web_view
        self.setWindowTitle("ページ内を検索")
        self.setMinimumWidth(400)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.init_ui()
    
    def init_ui(self):
        self.setStyleSheet(STYLES['dialog'])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # タイトル
        title_label = QLabel("<h3>ページ内を検索</h3>")
        layout.addWidget(title_label)
        
        # 検索バーと次/前ボタン
        search_layout = QHBoxLayout()
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("検索するテキストを入力...")
        self.search_input.textChanged.connect(self.on_text_changed)
        search_layout.addWidget(self.search_input)
        
        # 前へボタン
        prev_btn = QPushButton("前へ")
        prev_btn.setStyleSheet(STYLES['button_secondary'])
        prev_btn.setFixedWidth(70)
        prev_btn.clicked.connect(self.find_previous)
        search_layout.addWidget(prev_btn)
        
        # 次へボタン
        next_btn = QPushButton("次へ")
        next_btn.setStyleSheet(STYLES['button_secondary'])
        next_btn.setFixedWidth(70)
        next_btn.clicked.connect(self.find_next)
        search_layout.addWidget(next_btn)
        
        layout.addLayout(search_layout)
        
        # 区切り線
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)
        
        # 閉じるボタン
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_btn = QPushButton("閉じる")
        close_btn.setMinimumWidth(100)
        close_btn.setStyleSheet(STYLES['button_primary'])
        close_btn.clicked.connect(self.close_and_clear)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        
        # フォーカスを検索フィールドに
        self.search_input.setFocus()
    
    def on_text_changed(self, text):
        """テキストが変更されたらリアルタイムで検索"""
        if text:
            self.web_view.findText(text)
        else:
            # 空の場合は検索をクリア
            self.web_view.findText("")
    
    def find_next(self):
        """次を検索"""
        text = self.search_input.text()
        if text:
            self.web_view.findText(text)
    
    def find_previous(self):
        """前を検索"""
        from PySide6.QtWebEngineCore import QWebEnginePage
        text = self.search_input.text()
        if text:
            self.web_view.findText(text, QWebEnginePage.FindBackward)
    
    def close_and_clear(self):
        """閉じる際に検索をクリア"""
        self.web_view.findText("")
        self.close()
    
    def closeEvent(self, event):
        """ダイアログが閉じられる際に検索をクリア"""
        self.web_view.findText("")
        event.accept()
