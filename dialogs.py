"""
Strollon Browser - ダイアログ類
ブックマーク追加、メインダイアログ（設定・履歴・ブックマーク統合）、ダウンロードマネージャー
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel, QComboBox, QFrame, QMessageBox, QTabWidget,
    QTextEdit, QCheckBox, QRadioButton, QSpinBox, QGroupBox, QScrollArea,
    QFormLayout, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QTreeWidget, QTreeWidgetItem,
    QProgressBar
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

        title_label = QLabel(f"<h1>{BROWSER_NAME} Preview</h1>")
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
            f"<p style='font-size: 11pt;'>{BROWSER_NAME}は、左側に縦タブを配置した<br>"
            "シンプルで使いやすいWebブラウザです。</p>"
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
        
        mode_label = "XDG 準拠" if INSTALL_MODE == "xdg" else "ポータブル"
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

        privacy_group.setLayout(privacy_layout)
        layout.addWidget(privacy_group)

        # ---- ダウンロード設定 ----
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
        """閲覧履歴タブ"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 検索バー
        search_layout = QHBoxLayout()
        self.history_search_input = QLineEdit()
        self.history_search_input.setPlaceholderText("履歴を検索...")
        self.history_search_input.textChanged.connect(self.search_history)
        search_layout.addWidget(self.history_search_input)
        
        clear_history_btn = QPushButton("履歴を全削除")
        clear_history_btn.setStyleSheet(STYLES['button_secondary'])
        clear_history_btn.clicked.connect(self.clear_history)
        search_layout.addWidget(clear_history_btn)
        
        layout.addLayout(search_layout)
        
        # 履歴テーブル
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(["タイトル", "URL", "訪問日時", "訪問回数"])
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.doubleClicked.connect(self.on_history_item_double_clicked)
        layout.addWidget(self.history_table)
        
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
        self.history_table.setRowCount(len(history))
        for i, (url, title, visit_time, visit_count) in enumerate(history):
            self.history_table.setItem(i, 0, QTableWidgetItem(title or ""))
            self.history_table.setItem(i, 1, QTableWidgetItem(url))
            self.history_table.setItem(i, 2, QTableWidgetItem(visit_time))
            self.history_table.setItem(i, 3, QTableWidgetItem(str(visit_count)))
    
    def on_history_item_double_clicked(self, index):
        row = index.row()
        url = self.history_table.item(row, 1).text()
        self.open_url.emit(url)
        self.close()
    
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
        """ダウンロードタブ"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        info_label = QLabel("現在のダウンロードと過去のダウンロード履歴を表示します。")
        layout.addWidget(info_label)

        # テーブル（5列：ファイル名・URL・保存先・サイズ・進捗）
        self.download_table = QTableWidget()
        self.download_table.setColumnCount(5)
        self.download_table.setHorizontalHeaderLabels([
            "ファイル名", "URL", "保存先", "サイズ", "進捗"
        ])
        hh = self.download_table.horizontalHeader()
        # 全列をInteractiveにして手動リサイズ可能に
        for i in range(5):
            hh.setSectionResizeMode(i, QHeaderView.Interactive)
        self.download_table.setColumnWidth(0, 90)  # ファイル名
        self.download_table.setColumnWidth(1, 160)  # URL
        self.download_table.setColumnWidth(2, 220)  # 保存先
        self.download_table.setColumnWidth(3, 40)   # サイズ
        self.download_table.setColumnWidth(4, 40)   # 進捗
        self.download_table.setSelectionBehavior(QAbstractItemView.SelectItems)  # セル単位選択
        self.download_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.download_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # 右クリックメニュー
        self.download_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.download_table.customContextMenuRequested.connect(self._download_context_menu)
        layout.addWidget(self.download_table)

        button_layout = QHBoxLayout()
        refresh_btn = QPushButton("更新")
        refresh_btn.setStyleSheet(STYLES['button_secondary'])
        refresh_btn.clicked.connect(self.load_downloads)
        button_layout.addWidget(refresh_btn)
        clear_history_btn = QPushButton("履歴をクリア")
        clear_history_btn.setStyleSheet(STYLES['button_secondary'])
        clear_history_btn.clicked.connect(self.clear_download_history)
        button_layout.addWidget(clear_history_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # 自動更新タイマー（0.5秒ごと）
        self._download_refresh_timer = QTimer(self)
        self._download_refresh_timer.setInterval(500)
        self._download_refresh_timer.timeout.connect(self.load_downloads)
        self._download_refresh_timer.start()

        self.load_downloads()
        return widget

    def _download_context_menu(self, pos):
        """ダウンロードテーブルの右クリックメニュー（コピー）"""
        row = self.download_table.rowAt(pos.y())
        if row < 0:
            return

        file_item = self.download_table.item(row, 0)
        url_item  = self.download_table.item(row, 1)
        path_item = self.download_table.item(row, 2)
        if not file_item:
            return

        import os
        filename  = file_item.text() if file_item else ""
        url_text  = url_item.text()  if url_item  else ""
        dir_text  = path_item.text() if path_item else ""
        full_path = os.path.join(dir_text, filename) if dir_text else filename

        from PySide6.QtWidgets import QMenu as _QMenu
        menu = _QMenu(self)
        menu.setStyleSheet(STYLES.get('menu', ''))

        copy_name_action = menu.addAction(f"ファイル名をコピー")
        copy_url_action  = menu.addAction(f"URLをコピー")
        copy_path_action = menu.addAction(f"絶対パスをコピー")

        # URLが空の場合はグレーアウト
        if not url_text:
            copy_url_action.setEnabled(False)

        action = menu.exec(self.download_table.viewport().mapToGlobal(pos))

        from PySide6.QtWidgets import QApplication as _QApp
        if action == copy_name_action:
            _QApp.clipboard().setText(filename)
        elif action == copy_url_action:
            _QApp.clipboard().setText(url_text)
        elif action == copy_path_action:
            _QApp.clipboard().setText(full_path)

    def load_downloads(self):
        """ダウンロードデータを読み込み（DBから一本化・進捗はメモリ側で補完）"""
        from PySide6.QtWebEngineCore import QWebEngineDownloadRequest

        # メモリ上の進行中ダウンロードをURLでインデックス化
        live_by_url = {}
        for dl in self.download_manager.get_downloads():
            live_by_url[dl.url().toString()] = dl

        download_history = self.download_manager.get_download_history(100)

        # スクロール位置を保持
        scrollbar = self.download_table.verticalScrollBar()
        scroll_pos = scrollbar.value()

        self.download_table.setRowCount(0)

        for filename, url, download_path, total_bytes, received_bytes, state, start_time, finish_time in download_history:
            row = self.download_table.rowCount()
            self.download_table.insertRow(row)

            self.download_table.setItem(row, 0, QTableWidgetItem(filename))
            self.download_table.setItem(row, 1, QTableWidgetItem(url or ""))
            self.download_table.setItem(row, 2, QTableWidgetItem(download_path or ""))

            # サイズ
            if total_bytes and total_bytes > 0:
                self.download_table.setItem(
                    row, 3, QTableWidgetItem(f"{total_bytes / (1024*1024):.2f} MB"))
            else:
                self.download_table.setItem(row, 3, QTableWidgetItem("不明"))

            # 進捗（列4）
            live = live_by_url.get(url)
            if live and live.state().value == 1:  # DownloadInProgress
                live_total = live.totalBytes()
                live_recv  = live.receivedBytes()
                pct = int(live_recv / live_total * 100) if live_total > 0 else 0
                progress_bar = QProgressBar()
                progress_bar.setValue(pct)
                self.download_table.setCellWidget(row, 4, progress_bar)
            else:
                # DB値で表示。100% or 完了(state==2) なら「完了」テキスト
                if total_bytes and total_bytes > 0:
                    pct = int((received_bytes or 0) / total_bytes * 100)
                else:
                    pct = 100 if state == 2 else 0

                if pct >= 100 or state == 2:
                    item = QTableWidgetItem("完了")
                    item.setForeground(__import__('PySide6.QtGui', fromlist=['QColor']).QColor('#2e7d32'))
                    self.download_table.setItem(row, 4, item)
                else:
                    self.download_table.setItem(row, 4, QTableWidgetItem(f"{pct}%"))

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
