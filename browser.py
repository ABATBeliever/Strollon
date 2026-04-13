"""
Strollon Browser - メインブラウザウィンドウ
縦タブブラウザの実装、カスタムWebEnginePage、タブアイテム
"""

import re
import sys
import os
from pathlib import Path
from urllib.parse import quote_plus

# =====================================================================
# Chromium フラグ設定（QApplication より前に設定する必要がある）
# =====================================================================
# QCoreApplication.setAttribute より前、かつ QApplication 生成前に
# sys.argv に追加する方式で Chromium コマンドラインスイッチを渡す。
# ここではモジュールインポート時に設定する。
# =====================================================================


# =====================================================================
# Chromium フラグ定義（設定から読み込んで適用）
# =====================================================================
# フラグは QApplication 生成前に sys.argv へ追加する必要がある。
# StrollonBrowser.py の main() から呼び出す。
# =====================================================================

# 設定キー → (フラグ文字列, 説明)
CHROMIUM_FLAGS: dict[str, tuple[str, str]] = {
    "flag_hevc":         ("--enable-features=PlatformHEVCDecoderSupport",            "H.265/HEVC デコードを有効化（YouTube Live等）"),
    "flag_vaapi":        ("--enable-features=VaapiVideoDecodeLinuxGL,VaapiVideoEncoder,AcceleratedVideoDecodeLinuxGL,AcceleratedVideoDecodeLinuxZeroCopyGL", "VA-API GPU デコード/エンコードの有効化（Linux向け）"),
    "flag_mediafound":   ("--enable-features=MediaFoundationH264Encoding",           "Media Foundation H.264を有効化（Windows向け）"),
    "flag_ozone":        ("--enable-features=UseOzonePlatform",                      "Ozone プラットフォームを有効化（Linux Wayland向け）"),
    "flag_wasm_simd":    ("--enable-features=WebAssemblySimd",                       "WebAssembly SIMDを有効化"),
    "flag_wasm_threads": ("--enable-features=WebAssemblyThreads,SharedArrayBuffer",  "WebAssembly スレッド / SharedArrayBuffer を有効化"),
    "flag_gpu_raster":   ("--enable-gpu-rasterization --enable-oop-rasterization",   "GPU ラスタライズ の有効化"),
    "flag_zero_copy":    ("--enable-zero-copy",                                      "ゼロコピー テクスチャ の有効化"),
    "flag_ignore_gpu":   ("--ignore-gpu-blocklist --disable-gpu-driver-bug-workarounds", "GPU ブロックリストを無視し、古いGPUを活用する"),
    "flag_overlays":     ("--enable-hardware-overlays=single-fullscreen",            "ハードウェアオーバーレイ"),
    "flag_autoplay":     ("--autoplay-policy=no-user-gesture-required",              "自動再生制限を解除"),
    "flag_raw_draw":     ("--enable-raw-draw",                                       "Raw Draw の有効化"),
    "flag_no_cros_vd":   ("--disable-features=UseChromeOSDirectVideoDecoder",        "ChromeOS DirectVideoDecoder を無効化"),
}


def apply_chromium_flags_from_settings():
    """
    設定ファイル (config.toml / config.ini) から各フラグの有効/無効を読み取り、有効なものだけ sys.argv に追加する。
    QApplication 生成前に StrollonBrowser.py の main() から呼ぶこと。
    """
    from constants import settings as s, log
    applied = []
    for key, (flag_str, _desc) in CHROMIUM_FLAGS.items():
        if s.value(key, False, type=bool):
            for token in flag_str.split():
                if token not in sys.argv:
                    sys.argv.append(token)
            applied.append(key)
    if applied:
        log(f"[INFO] Chromium flags applied: {', '.join(applied)}")
    else:
        log("[INFO] Chromium flags: all disabled")


from PySide6.QtCore import Qt, QUrl, QTimer, QStringListModel
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QListWidget, QSplitter, QToolBar, QMessageBox,
    QFileDialog, QApplication, QMenu, QLabel, QProgressBar, QCompleter
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import (
    QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor
)
from PySide6.QtGui import QFont, QAction, QShortcut, QKeySequence
import qtawesome as qta

from constants import STYLES, BROWSER_FULL_NAME, BROWSER_VERSION_SEMANTIC, DOWNLOADS_DIR, USER_AGENT_PRESETS, \
    PROFILE_PATH, INCOGNITO_CACHE_PATH, INCOGNITO_STATE_PATH, CACHE_DIR, CHECK_FOR_UPDATES, settings, log, \
    IS_FIRST_RUN, BROWSER_VERSION_NAME, INSTALL, INSTALL_MODE
from managers import HistoryManager, BookmarkManager, DownloadManager, SessionManager, UpdateChecker
from dialogs import AddBookmarkDialog, MainDialog, FindDialog, SavePageDialog


from PySide6.QtCore import QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QListWidgetItem


# =====================================================================
# DNT（Do Not Track）URLリクエストインターセプター
# =====================================================================

class DntRequestInterceptor(QWebEngineUrlRequestInterceptor):
    """
    全リクエストに DNT ヘッダーを付加するインターセプター。
    enabled=True のとき DNT: 1、False のとき DNT: 0 を送信する。
    RFC 7230 に従い値はバイト列で渡す。
    """

    def __init__(self, enabled: bool = False, parent=None):
        super().__init__(parent)
        self._enabled = enabled

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    def interceptRequest(self, info):
        info.setHttpHeader(b"DNT", b"1" if self._enabled else b"0")






class UrlLineEdit(QLineEdit):
    """フォーカスを外したときに先頭（ドメイン部分）が表示されるURLバー"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 本当のフォーカスイン（ユーザー操作）かどうかを追跡するフラグ
        self._user_focused = False

    def focusOutEvent(self, event):
        self._user_focused = False
        super().focusOutEvent(event)
        # カーソルを先頭に移動してドメインを見えるようにする
        self.home(False)  # False = 選択解除

    def focusInEvent(self, event):
        super().focusInEvent(event)
        # コンプリーターのポップアップ操作（候補クリックなど）では
        # Qt.PopupFocusReason でフォーカスが戻ることがある。
        # その場合は全選択を行わず、カーソル位置を保持する。
        if event.reason() in (Qt.PopupFocusReason, Qt.ActiveWindowFocusReason):
            return
        if not self._user_focused:
            self._user_focused = True
            # フォーカス取得直後に selectAll() すると Linux では
            # QCompleter 等の内部処理と競合するため、次のイベントループで実行する
            QTimer.singleShot(0, self._select_all_if_focused)

    def _select_all_if_focused(self):
        """フォーカスが継続中のときだけ全選択する（コンプリーター由来の再トリガー防止）"""
        if self._user_focused and self.hasFocus():
            self.selectAll()


# =====================================================================
# カスタムWebEnginePage
# =====================================================================

class CustomWebEnginePage(QWebEnginePage):
    """新しいウィンドウ/タブの処理をカスタマイズしたWebEnginePage"""

    new_tab_requested = Signal(QUrl)

    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self._profile = profile

    def _find_browser(self):
        """親ウィジェットをたどって VerticalTabBrowser を返す"""
        w = self.parent()
        while w and not isinstance(w, VerticalTabBrowser):
            w = w.parent()
        return w

    def createWindow(self, window_type):
        """target="_blank" / window.open() などで新タブが要求されたとき"""
        log("[INFO] TabControl: createWindow requested")
        browser = self._find_browser()
        if browser:
            web_view = browser.add_new_tab(
                url="about:blank", activate=True, incognito=False, _return_view=True
            )
            if web_view is not None:
                return web_view.page()
        return super().createWindow(window_type)

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        """
        Ctrl+クリック / 中クリックによるリンクを新タブで開く。
        NavigationTypeLinkClicked かつ修飾キーが押されているときに
        シグナル経由で新タブを開き、このページへの遷移はキャンセルする。
        """
        from PySide6.QtWebEngineCore import QWebEnginePage as _Page
        from PySide6.QtWidgets import QApplication as _App
        from PySide6.QtCore import Qt as _Qt

        if (
            nav_type == _Page.NavigationTypeLinkClicked
            and is_main_frame
            and (_App.keyboardModifiers() & (_Qt.ControlModifier | _Qt.MetaModifier))
        ):
            browser = self._find_browser()
            if browser:
                browser.add_new_tab(url=url.toString(), activate=True)
            return False  # このページへの遷移をキャンセル
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


# =====================================================================
# タブアイテム
# =====================================================================

class TabItemWidget(QWidget):
    """タブアイテム用のカスタムウィジェット（タイトル＋閉じるボタン）"""
    close_requested = Signal()
    
    def __init__(self, title, parent=None, incognito=False):
        super().__init__(parent)
        self._incognito = incognito
        self.init_ui(title)
    
    def init_ui(self, title):
        # ウィジェット自体の背景を透明に
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        
        # シークレットアイコン（シークレットタブのみ）
        if self._incognito:
            self.incognito_icon = QLabel()
            self.incognito_icon.setPixmap(qta.icon('fa5s.user-secret', color=STYLES['icon_color_incognito']).pixmap(14, 14))
            self.incognito_icon.setStyleSheet("background: transparent; padding: 0px;")
            layout.addWidget(self.incognito_icon)
        
        # ミュートアイコン（初期状態では非表示）
        self.mute_icon = QLabel()
        self.mute_icon.setPixmap(qta.icon('fa5s.volume-mute', color=STYLES['icon_color_default']).pixmap(12, 12))
        self.mute_icon.setStyleSheet("background: transparent; padding: 0px;")
        self.mute_icon.setVisible(False)
        layout.addWidget(self.mute_icon)
        
        # タイトルラベル
        self.title_label = QLabel(title)
        if self._incognito:
            self.title_label.setStyleSheet(STYLES['incognito_title_label'])
        else:
            self.title_label.setStyleSheet(STYLES['tab_title_label'])
        self.title_label.setWordWrap(False)
        layout.addWidget(self.title_label, 1)
        
        # 閉じるボタン
        self.close_button = QPushButton()
        self.close_button.setIcon(qta.icon('fa5s.times', color=STYLES['icon_color_default']))
        self.close_button.setStyleSheet(STYLES['tab_item_close_button'])
        self.close_button.setToolTip("タブを閉じる")
        self.close_button.clicked.connect(self.close_requested.emit)
        layout.addWidget(self.close_button)
    
    def set_title(self, title):
        """タイトルを設定"""
        self.title_label.setText(title)
    
    def set_muted(self, is_muted):
        """ミュート状態を設定"""
        self.mute_icon.setVisible(is_muted)


class TabItem(QListWidgetItem):
    """タブを表すリストアイテム"""
    
    def __init__(self, title, web_view, incognito=False):
        super().__init__()
        self.web_view = web_view
        self.url = web_view.url()
        self.is_muted = False
        self.incognito = incognito  # シークレットタブフラグ
        self.widget = TabItemWidget(title, incognito=incognito)
        # サイズヒントを大きめに設定
        self.setSizeHint(self.widget.sizeHint())
        # フラグ設定（選択可能、有効）
        self.setFlags(self.flags() | Qt.ItemIsSelectable | Qt.ItemIsEnabled)


# =====================================================================
# メインブラウザウィンドウ
# =====================================================================

class VerticalTabBrowser(QMainWindow):
    """縦タブブラウザのメインウィンドウ"""
    
    def __init__(self):
        super().__init__()
        self.tabs = []
        self._closed_tab_stack = []  # 閉じたタブのURLスタック（複数対応）
        self._zoom_levels = {}  # タブごとのズーム倍率 {web_view: float}
        
        # 永続化プロファイルを作成（Cookie、LocalStorageなどが保存される）
        self.profile = QWebEngineProfile("StrollonProfile")
        self.profile.setPersistentStoragePath(str(PROFILE_PATH))
        self.profile.setCachePath(str(CACHE_DIR / "profile"))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.AllowPersistentCookies)

        # シークレット用プロファイル（非永続）
        self.incognito_profile = QWebEngineProfile("StrollonIncognito")
        self.incognito_profile.setCachePath(str(INCOGNITO_CACHE_PATH))
        self.incognito_profile.setPersistentStoragePath(str(INCOGNITO_STATE_PATH))
        self.incognito_profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)

        # DNT インターセプターを両プロファイルに登録（apply_settings で有効/無効を切り替える）
        self._dnt_interceptor = DntRequestInterceptor(enabled=False, parent=self)
        self._dnt_interceptor_incognito = DntRequestInterceptor(enabled=False, parent=self)
        self.profile.setUrlRequestInterceptor(self._dnt_interceptor)
        self.incognito_profile.setUrlRequestInterceptor(self._dnt_interceptor_incognito)
        
        self.history_manager = HistoryManager()
        self.bookmark_manager = BookmarkManager()
        self.download_manager = DownloadManager()
        self.session_manager = SessionManager()
        self.settings = settings
        
        self.apply_settings()
        self.init_ui()
        self.setup_shortcuts()
        self.check_for_updates()
        self.restore_session()
        # show() 後に winId() が確定してから always_on_top を適用
        QTimer.singleShot(0, self._apply_always_on_top)
    
    def apply_settings(self):
        """設定を適用"""
        web_settings = self.profile.settings()
        
        web_settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, 
                                 self.settings.value("allow_fullscreen", True, type=bool))
        web_settings.setAttribute(QWebEngineSettings.JavascriptEnabled, 
                                 self.settings.value("enable_javascript", True, type=bool))
        web_settings.setAttribute(QWebEngineSettings.AutoLoadImages,
                                 self.settings.value("auto_load_images", True, type=bool))
        # PDFはダウンロードとして処理する
        web_settings.setAttribute(QWebEngineSettings.PdfViewerEnabled, False)
        
        # ハードウェアアクセラレーション設定
        if not self.settings.value("enable_hardware_acceleration", True, type=bool):
            web_settings.setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, False)
            web_settings.setAttribute(QWebEngineSettings.WebGLEnabled, False)
        
        # シークレットプロファイルにも同設定を適用
        incognito_settings = self.incognito_profile.settings()
        incognito_settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
        incognito_settings.setAttribute(QWebEngineSettings.JavascriptEnabled,
                                       self.settings.value("enable_javascript", True, type=bool))
        incognito_settings.setAttribute(QWebEngineSettings.AutoLoadImages, True)
        incognito_settings.setAttribute(QWebEngineSettings.PdfViewerEnabled, False)
        
        # UserAgent設定
        ua_preset = self.settings.value("ua_preset", 0, type=int)
        if ua_preset > 0:
            if ua_preset == 5:
                ua = self.settings.value("ua_custom", "")
            else:
                ua = USER_AGENT_PRESETS.get(ua_preset, "")
            if ua:
                self.profile.setHttpUserAgent(ua)
                log(f"[INFO] UserAgent set to preset {ua_preset}")
        
        # Do Not Track ヘッダー設定
        # Do Not Track ヘッダー設定
        # QWebEngineProfile に直接 DNT API はないため、
        # setUrlRequestInterceptor で全リクエストに DNT ヘッダーを付加する。
        self.do_not_track = self.settings.value("do_not_track", False, type=bool)
        self._dnt_interceptor.set_enabled(self.do_not_track)
        self._dnt_interceptor_incognito.set_enabled(self.do_not_track)
        log(f"[INFO] DNT header set to: {'1' if self.do_not_track else '0'}")


        # downloadRequested の重複接続を防ぐために一度切断してから接続
        # 初回起動時は未接続のため RuntimeWarning が出るが無害なので抑制する
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                self.profile.downloadRequested.disconnect(self.on_download_requested)
            except RuntimeError:
                pass
            try:
                self.incognito_profile.downloadRequested.disconnect(self.on_download_requested)
            except RuntimeError:
                pass
        self.profile.downloadRequested.connect(self.on_download_requested)
        self.incognito_profile.downloadRequested.connect(self.on_download_requested)
        log("[INFO] Settings applied")
    
    def on_download_requested(self, download):
        """ダウンロード要求時の処理"""
        filename = download.downloadFileName()
        log(f"[INFO] Download requested: {filename}")

        # 設定からダウンロード先を取得
        from constants import _get_default_downloads_dir
        _dl_val = self.settings.value("download_dir", "")
        download_dir = Path(_dl_val) if _dl_val else _get_default_downloads_dir()
        try:
            download_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log(f"[ERROR] Cannot create download directory: {e}")
            download_dir = _get_default_downloads_dir()
            download_dir.mkdir(parents=True, exist_ok=True)
        
        if self.settings.value("ask_download", True, type=bool):
            filepath, _ = QFileDialog.getSaveFileName(
                self,
                "ファイルを保存",
                str(download_dir / filename),
                "All Files (*)"
            )
            if filepath:
                download.setDownloadDirectory(str(Path(filepath).parent))
                download.setDownloadFileName(Path(filepath).name)
                download.accept()
                self.download_manager.add_download(download)
                self.show_download_dialog()
        else:
            download.setDownloadDirectory(str(download_dir))
            download.accept()
            self.download_manager.add_download(download)
            self.show_download_dialog()
    
    def init_ui(self):
        """UIの初期化"""
        self.setWindowTitle(f"{BROWSER_FULL_NAME}")
        self.setGeometry(100, 100, 1200, 800)
        self.setStyleSheet(STYLES['main_window'])
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet(STYLES['splitter'])
        
        self.tab_list_widget = self.create_tab_list()
        splitter.addWidget(self.tab_list_widget)
        
        browser_widget = self.create_browser_area()
        splitter.addWidget(browser_widget)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([200, 1000])
        
        main_layout.addWidget(splitter)
    
    def restore_session(self):
        """セッションを復元。初回起動時はウェルカムページを表示する。"""

        # 初回起動: ウェルカムページをインライン HTML で開く
        if IS_FIRST_RUN:
            log("[INFO] 初回起動: ウェルカムページを表示します")
            self.add_new_tab(self._welcome_page_url(), activate=True)
            return

        startup_action = self.settings.value("startup_action", 0, type=int)

        if startup_action == 0 and self.settings.value("save_session", True, type=bool):
            status, session_data = self.session_manager.load_session()

            if status == "newer_version":
                pass
            elif status == "ok":
                if session_data:
                    tabs_data = session_data.get("tabs", [])
                    active_index = session_data.get("active_index", 0)

                    if tabs_data:
                        opened = 0
                        for i, tab_data in enumerate(tabs_data):
                            url = tab_data.get("url", "")
                            if not url or url.startswith("about:") or url.startswith("chrome:"):
                                continue
                            activate = (i == active_index)
                            self.add_new_tab(url, activate=activate)
                            opened += 1
                        if opened > 0:
                            return

        if startup_action == 1:
            homepage = self.settings.value("homepage", "https://www.google.com")
            self.add_new_tab(homepage)
        else:
            self.add_new_tab("https://www.google.com")

    def _welcome_page_url(self) -> str:
        """
        初回起動時に表示するウェルカムページを data URI として返す。
        外部ファイル不要でブラウザ内に直接表示する。
        """
        mode_label = "インストール版 (XDG)" if INSTALL else "ポータブル版"
        html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>Strollon へようこそ</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "Segoe UI", "Noto Sans JP", sans-serif;
    background: #f4f6fb;
    color: #222;
    display: flex;
    justify-content: center;
    padding: 48px 16px;
    min-height: 100vh;
  }}
  .card {{
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 2px 16px rgba(0,0,0,.10);
    max-width: 640px;
    width: 100%;
    padding: 48px 48px 40px;
  }}
  h1 {{ font-size: 2rem; color: #1a1a2e; margin-bottom: 6px; }}
  .version {{ color: #4a90d9; font-size: .95rem; margin-bottom: 28px; }}
  p {{ line-height: 1.75; color: #444; margin-bottom: 14px; }}
  hr {{ border: none; border-top: 1px solid #e8eaf0; margin: 28px 0; }}
  .info-table {{ width: 100%; border-collapse: collapse; font-size: .88rem; }}
  .info-table td {{ padding: 6px 8px; vertical-align: top; }}
  .info-table td:first-child {{ color: #888; white-space: nowrap; width: 140px; }}
  .info-table tr:nth-child(even) td {{ background: #f9fafc; border-radius: 4px; }}
  .tip {{
    background: #eaf2fb;
    border-left: 4px solid #4a90d9;
    border-radius: 4px;
    padding: 12px 16px;
    font-size: .88rem;
    color: #1f5fa5;
    margin-top: 24px;
  }}
</style>
</head>
<body>
<div class="card">
  <h1>Strollon へようこそ</h1>
  <div class="version">Version {BROWSER_VERSION_NAME}</div>

  <p>
    Strollon は、左側に縦タブを配置したシンプルなWebブラウザです。<br>
    Chromium エンジン（Qt WebEngine）を使用しており、一般的なWebサイトを快適に閲覧できます。
  </p>
  <p>
    右上の <strong>≡ メニュー</strong> から設定・ブックマーク・履歴などにアクセスできます。<br>
    タブは左のパネルで管理でき、ドラッグ＆ドロップで並び替えも可能です。
  </p>

  <hr>

  <table class="info-table">
    <tr><td>バージョン</td><td>{BROWSER_VERSION_NAME}</td></tr>
    <tr><td>インストール種別</td><td>{mode_label}</td></tr>
    <tr><td>対応OS</td><td>Linux (Wayland) / Windows 11+</td></tr>
    <tr><td>開発者</td><td>ABATBeliever</td></tr>
    <tr><td>ライセンス</td><td>GNU LGPL v3</td></tr>
  </table>

  <div class="tip">
    💡 このページは初回起動時のみ表示されます。次回からはホームページが開きます。
  </div>
</div>
</body>
</html>"""

        from urllib.parse import quote
        return "data:text/html;charset=utf-8," + quote(html)
    
    def save_current_session(self):
        """現在のセッションを保存"""
        if not self.settings.value("save_session", True, type=bool):
            return

        tabs_data = []
        current_index = self.tab_list.currentRow()

        # シークレットタブを除外した通常タブのみ収集
        normal_tab_indices = []
        for i in range(self.tab_list.count()):
            item = self.tab_list.item(i)
            if not isinstance(item, TabItem):
                continue
            if item.incognito:
                continue
            url = item.web_view.url().toString()
            # about: / chrome: など復元しても意味のないURLも除外
            if not url or url.startswith("about:") or url.startswith("chrome:"):
                continue
            normal_tab_indices.append(i)
            tabs_data.append({
                "url": url,
                "title": item.web_view.title() or ""
            })

        # アクティブタブのインデックスを正規化（除外後のインデックス）
        active_normal_index = 0
        for idx, original_i in enumerate(normal_tab_indices):
            if original_i == current_index:
                active_normal_index = idx
                break

        result = {"tabs": tabs_data, "active_index": active_normal_index}
        self.session_manager.save_session(result)
    
    def setup_shortcuts(self):
        """キーボードショートカットを設定"""
        # Ctrl+T: 新しいタブ
        QShortcut(QKeySequence("Ctrl+T"), self).activated.connect(
            lambda: self.add_new_tab(self.settings.value("homepage", "https://www.google.com")))
        # Ctrl+W: 現在のタブを閉じる
        QShortcut(QKeySequence("Ctrl+W"), self).activated.connect(self.close_current_tab)
        # Ctrl+Tab: 次のタブ（下）
        QShortcut(QKeySequence("Ctrl+Tab"), self).activated.connect(self.switch_to_next_tab)
        # Ctrl+Shift+Tab: 前のタブ（上）
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self).activated.connect(self.switch_to_prev_tab)
        # Ctrl+F: ページ内検索
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.find_in_page)
        # ズームイン: Ctrl++ (= Ctrl+Shift+=) / Ctrl+= / Ctrl+; (JISキーボードの+無シフト)
        QShortcut(QKeySequence("Ctrl++"), self).activated.connect(self.zoom_in)
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(self.zoom_in)
        QShortcut(QKeySequence("Ctrl+Shift+="), self).activated.connect(self.zoom_in)
        QShortcut(QKeySequence("Ctrl+;"), self).activated.connect(self.zoom_in)
        # ズームアウト: Ctrl+-
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(self.zoom_out)
        # ズームリセット: Ctrl+0
        QShortcut(QKeySequence("Ctrl+0"), self).activated.connect(self.zoom_reset)
        log("[INFO] Shortcuts registered")
    
    def _on_tabs_reordered(self, parent, start, end, dest, dest_row):
        """タブのドラッグ&ドロップ並び替え後にカスタムウィジェットを再アタッチ"""
        for i in range(self.tab_list.count()):
            item = self.tab_list.item(i)
            if isinstance(item, TabItem):
                # ドラッグ後にカスタムウィジェットの参照が外れるため再セット
                self.tab_list.setItemWidget(item, item.widget)
        log("[INFO] TabControl: Reordered")

    def switch_to_next_tab(self):
        """次のタブ（下方向）に切り替え"""
        count = self.tab_list.count()
        if count <= 1:
            return
        current = self.tab_list.currentRow()
        next_row = (current + 1) % count
        self.tab_list.setCurrentRow(next_row)
    
    def switch_to_prev_tab(self):
        """前のタブ（上方向）に切り替え"""
        count = self.tab_list.count()
        if count <= 1:
            return
        current = self.tab_list.currentRow()
        prev_row = (current - 1) % count
        self.tab_list.setCurrentRow(prev_row)
    
    # ---- ズーム操作 ----
    _ZOOM_STEPS = [0.25, 0.33, 0.50, 0.67, 0.75, 0.80, 0.90,
                   1.00, 1.10, 1.25, 1.50, 1.75, 2.00, 2.50, 3.00]

    def _current_web_view(self):
        """現在アクティブな WebView を返す。なければ None"""
        item = self.tab_list.currentItem()
        if item and isinstance(item, TabItem):
            return item.web_view
        return None

    def zoom_in(self):
        """ズームイン（Ctrl++）"""
        wv = self._current_web_view()
        if not wv:
            return
        current = self._zoom_levels.get(wv, 1.0)
        larger = [z for z in self._ZOOM_STEPS if z > current + 0.001]
        new_zoom = larger[0] if larger else self._ZOOM_STEPS[-1]
        self._apply_zoom(wv, new_zoom)

    def zoom_out(self):
        """ズームアウト（Ctrl+-）"""
        wv = self._current_web_view()
        if not wv:
            return
        current = self._zoom_levels.get(wv, 1.0)
        smaller = [z for z in self._ZOOM_STEPS if z < current - 0.001]
        new_zoom = smaller[-1] if smaller else self._ZOOM_STEPS[0]
        self._apply_zoom(wv, new_zoom)

    def zoom_reset(self):
        """ズームリセット（Ctrl+0）"""
        wv = self._current_web_view()
        if not wv:
            return
        self._apply_zoom(wv, 1.0)

    def _apply_zoom(self, web_view, factor):
        """指定 WebView にズーム倍率を適用してURLバー末尾に表示"""
        web_view.setZoomFactor(factor)
        self._zoom_levels[web_view] = factor
        pct = int(factor * 100)
        log(f"[INFO] Zoom: {pct}%")
        # URLバーの右端に一時的にズーム率を表示（2秒後に元に戻す）
        if not hasattr(self, '_zoom_label'):
            self._zoom_label = QLabel(self.url_bar)
            self._zoom_label.setStyleSheet(
                "QLabel { color: #666; font-size: 9pt; background: transparent; "
                "padding-right: 6px; }"
            )
            self._zoom_label.setAttribute(Qt.WA_TranslucentBackground)
        self._zoom_label.setText(f"{pct}%")
        self._zoom_label.adjustSize()
        # URLバー内の右端に配置
        self._zoom_label.move(
            self.url_bar.width() - self._zoom_label.width() - 4,
            (self.url_bar.height() - self._zoom_label.height()) // 2
        )
        self._zoom_label.show()
        if hasattr(self, '_zoom_label_timer'):
            self._zoom_label_timer.stop()
        self._zoom_label_timer = QTimer(self)
        self._zoom_label_timer.setSingleShot(True)
        self._zoom_label_timer.timeout.connect(self._zoom_label.hide)
        self._zoom_label_timer.start(2000)
    
    def check_for_updates(self):
        """更新チェック（constants.CHECK_FOR_UPDATES が False の場合はスキップ）"""
        if not CHECK_FOR_UPDATES:
            log("[INFO] UpdateCheck: skipped (CHECK_FOR_UPDATES=False)")
            return
        self.update_checker = UpdateChecker()
        self.update_checker.update_available.connect(self.show_update_notification)
        self.update_checker.start()
    
    def show_update_notification(self, latest_version, message):
        """更新通知（今すぐ更新 / 後で確認）"""
        from constants import BROWSER_TARGET_ARCHITECTURE
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("更新が利用可能です")
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setText(f"<h3>Strollonの新しいバージョン ({latest_version}) が利用可能です</h3>")
        msg_box.setInformativeText(
            f"<p>現在のバージョン: {BROWSER_VERSION_SEMANTIC}<br>最新のバージョン: {latest_version}</p>"
            f"<p><b>更新内容:</b></p><p>{message}</p>"
        )
        
        update_btn = msg_box.addButton("今すぐ更新", QMessageBox.AcceptRole)
        later_btn  = msg_box.addButton("後で確認",   QMessageBox.RejectRole)
        msg_box.setDefaultButton(update_btn)
        
        msg_box.exec()
        
        if msg_box.clickedButton() == update_btn:
            download_url = (
                f"https://github.com/ABATBeliever/StrollonBrowser2x/releases/download/"
                f"{latest_version}/Strollon-{BROWSER_TARGET_ARCHITECTURE}.zip"
            )
            self.add_new_tab(download_url, activate=True)
            log(f"[INFO] UpdateCheck-> Opening download URL: {download_url}")
    
    def show_menu(self):
        """メニューを表示"""
        menu = QMenu(self)
        menu.setStyleSheet(STYLES['menu'])
        
        # 新しいタブ
        new_tab_action = QAction(qta.icon('fa5s.plus', color=STYLES['icon_color_accent']), "新しいタブ", self)
        new_tab_action.triggered.connect(lambda: self.add_new_tab(self.settings.value("homepage", "https://www.google.com")))
        menu.addAction(new_tab_action)
        
        # シークレットタブ
        incognito_action = QAction(qta.icon('fa5s.user-secret', color=STYLES['icon_color_incognito']), "シークレットタブ", self)
        incognito_action.triggered.connect(lambda: self.add_new_tab(
            self.settings.value("homepage", "https://www.google.com"), incognito=True))
        menu.addAction(incognito_action)
        
        menu.addSeparator()
        
        # ブックマーク
        bookmark_action = QAction(qta.icon('fa5s.star', color=STYLES['icon_color_bookmark']), "ブックマーク", self)
        bookmark_action.triggered.connect(self.show_bookmarks_dialog)
        menu.addAction(bookmark_action)
        
        # 履歴
        history_action = QAction(qta.icon('fa5s.history', color=STYLES['icon_color_default']), "履歴", self)
        history_action.triggered.connect(self.show_history_dialog)
        menu.addAction(history_action)
        
        # ダウンロード
        download_action = QAction(qta.icon('fa5s.download', color=STYLES['icon_color_default']), "ダウンロード", self)
        download_action.triggered.connect(self.show_download_dialog)
        menu.addAction(download_action)
        
        menu.addSeparator()
        
        # ローカルファイルを開く
        local_action = QAction(qta.icon('fa5s.folder-open', color=STYLES['icon_color_default']), "ローカルファイルを開く", self)
        local_action.triggered.connect(self.open_local_file)
        menu.addAction(local_action)
        
        # ページ内を検索
        find_action = QAction(qta.icon('fa5s.search', color=STYLES['icon_color_default']), "ページ内を検索", self)
        find_action.triggered.connect(self.find_in_page)
        menu.addAction(find_action)
        
        # ページを保存
        save_page_action = QAction(qta.icon('fa5s.camera', color=STYLES['icon_color_default']), "ページを保存", self)
        save_page_action.triggered.connect(self.save_page)
        menu.addAction(save_page_action)
        
        menu.addSeparator()

        # 他のブラウザで開く（サブメニュー）
        send_menu = QMenu("他のブラウザで開く", self)
        send_menu.setStyleSheet(STYLES['menu'])
        send_menu.setIcon(qta.icon('fa5s.external-link-alt', color=STYLES['icon_color_default']))
        for browser_name, browser_cmd in self._get_external_browsers():
            act = QAction(browser_name, self)
            act.triggered.connect(lambda checked=False, cmd=browser_cmd: self._open_in_browser(cmd))
            send_menu.addAction(act)
        menu.addMenu(send_menu)

        # 常に最前面（現在の状態に応じてラベルを切り替え）
        _aot_on = self.settings.value("always_on_top", False, type=bool)
        _aot_label = "最前面表示を無効にする" if _aot_on else "常に最前面に表示する"
        aot_action = QAction(
            qta.icon('fa5s.thumbtack', color=STYLES['icon_color_accent']),
            _aot_label, self
        )
        aot_action.triggered.connect(lambda: self._toggle_always_on_top(not _aot_on))
        menu.addAction(aot_action)

        menu.addSeparator()

        # 設定（設定タブを開く）
        settings_action = QAction(qta.icon('fa5s.cog', color=STYLES['icon_color_default']), "設定", self)
        settings_action.triggered.connect(self.show_main_dialog)
        menu.addAction(settings_action)

        # ブラウザについて
        about_action = QAction(qta.icon('fa5s.info-circle', color=STYLES['icon_color_default']), "ブラウザについて", self)
        about_action.triggered.connect(self.show_about_dialog)
        menu.addAction(about_action)

        menu.addSeparator()

        # 終了
        exit_action = QAction(qta.icon('fa5s.sign-out-alt', color=STYLES['icon_color_danger']), "終了", self)
        exit_action.triggered.connect(self.close)
        menu.addAction(exit_action)
        
        # メニューを表示（ボタンの下に）
        sender = self.sender()
        if sender:
            menu.exec(sender.mapToGlobal(sender.rect().bottomLeft()))
    
    def _get_external_browsers(self) -> list:
        """
        外部ブラウザのリストを返す。
        Windows: 存在確認なし（なければ Popen が失敗するだけ）
        Linux  : shutil.which() で実際にインストール済みのものだけ返す
        戻り値: [(表示名, コマンド), ...]
        """
        import shutil
        import platform as _pl
        candidates = []
        if _pl.system().lower() == "windows":
            candidates = [
                ("Microsoft Edge",
                 r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
                ("Google Chrome",
                 r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                ("Mozilla Firefox",
                 r"C:\Program Files\Mozilla Firefox\firefox.exe"),
            ]
        else:  # Linux
            linux_browsers = [
                ("Microsoft Edge",  "microsoft-edge"),
                ("Google Chrome",   "google-chrome"),
                ("Mozilla Firefox", "firefox"),
                ("Floorp",          "floorp"),
                ("Falkon",          "falkon"),
                ("Konqueror",       "konqueror"),
                ("Chromium",        "chromium"),
                ("Chromium",        "chromium-browser"),
            ]
            seen_cmd: set = set()
            for name, cmd in linux_browsers:
                if cmd not in seen_cmd and shutil.which(cmd):
                    candidates.append((name, cmd))
                    seen_cmd.add(cmd)
            if not candidates:
                candidates.append(("（利用可能なブラウザが見つかりません）", ""))
        return candidates

    def _open_in_browser(self, cmd: str, url: str = ""):
        """指定コマンドの外部ブラウザで URL を開く。
        url 省略時は現在アクティブなタブの URL を使用する。
        """
        if not cmd:
            return
        if not url:
            current_item = self.tab_list.currentItem()
            if not current_item or not isinstance(current_item, TabItem):
                return
            url = current_item.web_view.url().toString()
        if not url or url.startswith("about:") or url.startswith("data:"):
            return
        import subprocess
        try:
            subprocess.Popen([cmd, url])
            log(f"[INFO] SendURL: opened {url} in {cmd}")
        except Exception as e:
            log(f"[ERROR] SendURL: failed to open {cmd}: {e}")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "エラー", f"ブラウザを起動できませんでした:\n{e}")

    def _apply_always_on_top(self):
        """
        always_on_top フラグをウィンドウに適用する。

        Windows: ctypes.SetWindowPos で Z-order のみ変更（ウィンドウ破棄なし）。
                 64bit HWND に対応するため argtypes を明示的に設定する。
        Linux:   setWindowFlags → 遅延 show でメニュー消滅後に再表示。
        """
        import platform as _pl
        always_on_top = self.settings.value("always_on_top", False, type=bool)
        log(f"[INFO] _apply_always_on_top: always_on_top={always_on_top}, winId={int(self.winId())}")

        if _pl.system().lower() == "windows":
            import ctypes
            import ctypes.wintypes

            # 64bit HWND を正しく渡すために argtypes を明示
            _SetWindowPos = ctypes.windll.user32.SetWindowPos
            _SetWindowPos.restype  = ctypes.wintypes.BOOL
            _SetWindowPos.argtypes = [
                ctypes.wintypes.HWND,
                ctypes.wintypes.HWND,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.wintypes.UINT,
            ]

            HWND_TOPMOST   = ctypes.wintypes.HWND(-1)
            HWND_NOTOPMOST = ctypes.wintypes.HWND(-2)
            SWP_NOMOVE     = 0x0002
            SWP_NOSIZE     = 0x0001
            SWP_NOACTIVATE = 0x0010

            hwnd = ctypes.wintypes.HWND(int(self.winId()))
            z_order = HWND_TOPMOST if always_on_top else HWND_NOTOPMOST
            ret = _SetWindowPos(
                hwnd, z_order, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
            )
            err = ctypes.get_last_error() if ret == 0 else 0
            log(f"[INFO] SetWindowPos ret={ret} err={err} z={'TOPMOST' if always_on_top else 'NOTOPMOST'}")
        else:
            from PySide6.QtCore import Qt
            base_flags = Qt.Window
            if always_on_top:
                self.setWindowFlags(base_flags | Qt.WindowStaysOnTopHint)
            else:
                self.setWindowFlags(base_flags)
            QTimer.singleShot(150, self.show)
            QTimer.singleShot(160, self.raise_)
            QTimer.singleShot(170, self.activateWindow)
            log(f"[INFO] AlwaysOnTop (Linux): {always_on_top}")

    def _toggle_always_on_top(self, checked: bool):
        """常に最前面の設定を切り替えて永続化する"""
        self.settings.setValue("always_on_top", checked)
        self.settings.sync()
        self._apply_always_on_top()
        log(f"[INFO] Always on top: {checked}")

    def show_bookmarks_dialog(self):
        """ブックマークダイアログを表示（現在のページ情報を渡す）"""
        # 現在のタブのURLとタイトルを取得してダイアログに渡す
        current_url = ""
        current_title = ""
        current_item = self.tab_list.currentItem()
        if current_item and isinstance(current_item, TabItem):
            current_url = current_item.web_view.url().toString()
            current_title = current_item.web_view.title()

        dialog = MainDialog(
            self.history_manager, self.bookmark_manager, self.download_manager, self,
            current_url=current_url, current_title=current_title
        )
        dialog.open_url.connect(lambda url: self.add_new_tab(url, activate=True))
        dialog.tab_widget.setCurrentIndex(3)  # ブックマークタブを選択
        dialog.exec()
    
    def show_history_dialog(self):
        """履歴ダイアログを表示"""
        current_url = ""
        current_title = ""
        current_item = self.tab_list.currentItem()
        if current_item and isinstance(current_item, TabItem):
            current_url = current_item.web_view.url().toString()
            current_title = current_item.web_view.title()
        dialog = MainDialog(
            self.history_manager, self.bookmark_manager, self.download_manager, self,
            current_url=current_url, current_title=current_title)
        dialog.open_url.connect(lambda url: self.add_new_tab(url, activate=True))
        dialog.tab_widget.setCurrentIndex(2)  # 履歴タブを選択
        dialog.exec()
    
    def open_local_file(self):
        """ローカルファイルを新しいタブで開く"""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "ローカルファイルを開く",
            str(Path.home()),
            "All Files (*)"
        )
        if filepath:
            file_url = QUrl.fromLocalFile(filepath)
            self.add_new_tab(file_url.toString(), activate=True)
    
    def find_in_page(self):
        """ページ内検索（改良版ダイアログ）"""
        current_item = self.tab_list.currentItem()
        if current_item and isinstance(current_item, TabItem):
            dialog = FindDialog(current_item.web_view, self)
            dialog.exec()
    
    def show_main_dialog(self):
        """設定ダイアログ表示（設定タブ）"""
        current_url = ""
        current_title = ""
        current_item = self.tab_list.currentItem()
        if current_item and isinstance(current_item, TabItem):
            current_url = current_item.web_view.url().toString()
            current_title = current_item.web_view.title()
        dialog = MainDialog(
            self.history_manager, self.bookmark_manager, self.download_manager, self,
            current_url=current_url, current_title=current_title)
        dialog.open_url.connect(lambda url: self.add_new_tab(url, activate=True))
        dialog.show_settings_tab()
        dialog.exec()
    
    def show_about_dialog(self):
        """ブラウザについてダイアログ表示"""
        current_url = ""
        current_title = ""
        current_item = self.tab_list.currentItem()
        if current_item and isinstance(current_item, TabItem):
            current_url = current_item.web_view.url().toString()
            current_title = current_item.web_view.title()
        dialog = MainDialog(
            self.history_manager, self.bookmark_manager, self.download_manager, self,
            current_url=current_url, current_title=current_title)
        dialog.open_url.connect(lambda url: self.add_new_tab(url, activate=True))
        dialog.show_about_tab()
        dialog.exec()
    
    def show_download_dialog(self):
        """ダウンロードマネージャー表示"""
        # シングルトンを廃止し毎回生成する。
        # current_url="" で使い回されるとブックマークの「新規追加」が
        # 無効化されたままになるバグを防ぐため。
        current_url = ""
        current_title = ""
        current_item = self.tab_list.currentItem()
        if current_item and isinstance(current_item, TabItem):
            current_url = current_item.web_view.url().toString()
            current_title = current_item.web_view.title()
        dialog = MainDialog(
            self.history_manager, self.bookmark_manager, self.download_manager, self,
            current_url=current_url, current_title=current_title)
        dialog.open_url.connect(lambda url: self.add_new_tab(url, activate=True))
        dialog.show_download_tab()
        dialog.exec()
    
    def save_page(self):
        """ページを保存（PNG / PDF）"""
        current_item = self.tab_list.currentItem()
        if current_item and isinstance(current_item, TabItem):
            dialog = SavePageDialog(current_item.web_view, self)
            dialog.exec()


    def add_bookmark_from_current_tab(self):
        """現在のタブをブックマークに追加"""
        current_item = self.tab_list.currentItem()
        if current_item and isinstance(current_item, TabItem):
            url = current_item.web_view.url().toString()
            title = current_item.web_view.title() or "無題"
            
            folders = self.bookmark_manager.get_folders()
            dialog = AddBookmarkDialog(title, url, folders, self)
            
            if dialog.exec():
                result = dialog.get_result()
                if result:
                    self.bookmark_manager.add_bookmark(
                        result["title"], 
                        result["url"], 
                        result["folder"]
                    )
    
    def create_tab_list(self):
        """タブリスト作成"""
        widget = QWidget()
        widget.setStyleSheet(STYLES['tab_list'])
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # 新規タブボタン（横幅いっぱいに拡張）
        new_tab_btn = QPushButton()
        new_tab_btn.setIcon(qta.icon('fa5s.plus', color=STYLES['icon_color_new_tab']))
        new_tab_btn.setToolTip("新規タブ")
        new_tab_btn.setMinimumHeight(36)
        new_tab_btn.setStyleSheet(STYLES['button_secondary'])
        new_tab_btn.clicked.connect(lambda: self.add_new_tab(self.settings.value("homepage", "https://www.google.com")))
        layout.addWidget(new_tab_btn)
        
        self.tab_list = QListWidget()
        self.tab_list.currentItemChanged.connect(self.on_tab_changed)
        self.tab_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab_list.customContextMenuRequested.connect(self.show_tab_context_menu)
        # ドラッグ&ドロップによるタブ並び替えを有効化
        self.tab_list.setDragDropMode(QListWidget.InternalMove)
        self.tab_list.setDefaultDropAction(Qt.MoveAction)
        self.tab_list.model().rowsMoved.connect(self._on_tabs_reordered)
        layout.addWidget(self.tab_list)
        
        return widget
    
    def create_browser_area(self):
        """ブラウザエリア作成"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setStyleSheet(STYLES['toolbar'])
        layout.addWidget(toolbar)
        
        self.back_btn = QPushButton()
        self.back_btn.setIcon(qta.icon('fa5s.arrow-left', color=STYLES['icon_color_primary']))
        self.back_btn.setToolTip("戻る")
        self.back_btn.setFixedSize(32, 32)
        self.back_btn.clicked.connect(self.go_back)
        toolbar.addWidget(self.back_btn)
        
        self.forward_btn = QPushButton()
        self.forward_btn.setIcon(qta.icon('fa5s.arrow-right', color=STYLES['icon_color_primary']))
        self.forward_btn.setToolTip("進む")
        self.forward_btn.setFixedSize(32, 32)
        self.forward_btn.clicked.connect(self.go_forward)
        toolbar.addWidget(self.forward_btn)
        
        self.reload_btn = QPushButton()
        self.reload_btn.setIcon(qta.icon('fa5s.sync-alt', color=STYLES['icon_color_primary']))
        self.reload_btn.setToolTip("再読み込み")
        self.reload_btn.setFixedSize(32, 32)
        self.reload_btn.clicked.connect(self.reload_page)
        toolbar.addWidget(self.reload_btn)
        
        self.url_bar = UrlLineEdit()
        self.url_bar.setPlaceholderText("URLを入力またはキーワードで検索")
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        # オートコンプリート
        self._completer_model = QStringListModel()
        self._url_completer = QCompleter(self._completer_model, self)
        self._url_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._url_completer.setFilterMode(Qt.MatchContains)
        self._url_completer.setMaxVisibleItems(12)
        # UnfilteredPopupCompletion: モデルの内容をそのまま全表示。
        # フィルタリングは _update_url_completer() で手動管理するため
        # QCompleter 側の自動フィルタに「🔍〇〇を検索」が消される問題を防ぐ。
        self._url_completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self.url_bar.setCompleter(self._url_completer)
        self.url_bar.textEdited.connect(self._update_url_completer)
        # 「🔍〇〇を検索」が選択された瞬間に即ナビゲートする
        self._url_completer.activated.connect(self._on_completer_activated)
        toolbar.addWidget(self.url_bar)
        
        bookmark_add_btn = QPushButton()
        bookmark_add_btn.setIcon(qta.icon('fa5s.star', color=STYLES['icon_color_bookmark']))
        bookmark_add_btn.setToolTip("ブックマーク")
        bookmark_add_btn.setFixedSize(32, 32)
        bookmark_add_btn.clicked.connect(self.show_bookmarks_dialog)
        toolbar.addWidget(bookmark_add_btn)
        
        menu_btn = QPushButton()
        menu_btn.setIcon(qta.icon('fa5s.ellipsis-h', color=STYLES['icon_color_default']))
        menu_btn.setToolTip("メニュー")
        menu_btn.setFixedSize(32, 32)
        menu_btn.clicked.connect(self.show_menu)
        toolbar.addWidget(menu_btn)
        
        # ロード進捗バー（URLバー下部・3pxの細いバー）
        # setVisible(False) するとレイアウトが詰まって揺れるため、
        # 常に領域を確保しつつ完了時は透明にする
        self.load_progress_bar = QProgressBar()
        self.load_progress_bar.setStyleSheet(STYLES['load_progress_bar'])
        self.load_progress_bar.setRange(0, 100)
        self.load_progress_bar.setValue(0)
        self.load_progress_bar.setTextVisible(False)
        self.load_progress_bar.setFixedHeight(3)
        # 初期状態は透明（非ロード中）
        self.load_progress_bar.setStyleSheet(
            STYLES['load_progress_bar'] + "QProgressBar::chunk { background-color: transparent; }"
        )
        layout.addWidget(self.load_progress_bar)
        
        # 疑似ロード進捗用タイマー
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(80)
        self._progress_timer.timeout.connect(self._advance_pseudo_progress)
        self._pseudo_progress = 0
        
        self.web_container = QWidget()
        self.web_layout = QVBoxLayout(self.web_container)
        self.web_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web_container)
        
        return widget
    
    def get_search_url(self, query):
        """検索エンジンに応じた検索URLを取得"""
        search_engine = self.settings.value("search_engine", 0, type=int)
        encoded_query = quote_plus(query)
        
        search_urls = {
            0: f"https://www.google.com/search?q={encoded_query}",
            1: f"https://www.bing.com/search?q={encoded_query}",
            2: f"https://duckduckgo.com/?q={encoded_query}",
            3: f"https://search.yahoo.co.jp/search?p={encoded_query}"
        }
        
        return search_urls.get(search_engine, search_urls[1])  # デフォルト: Bing
    
    def is_valid_url(self, text):
        """URL判定"""
        url_pattern = re.compile(r'^https?://|^www\.|^[a-zA-Z0-9-]+\.[a-zA-Z]{2,}')
        
        if ' ' in text:
            return False
        
        if url_pattern.match(text):
            return True
        
        if '.' in text and not text.startswith('.') and not text.endswith('.'):
            parts = text.split('.')
            if len(parts) >= 2 and len(parts[-1]) >= 2:
                return True
        
        return False
    
    def process_url_or_search(self, text):
        """URL/検索処理"""
        text = text.strip()
        
        if self.is_valid_url(text):
            if not text.startswith("http://") and not text.startswith("https://"):
                text = "https://" + text
            return text
        else:
            return self.get_search_url(text)
    
    def add_new_tab(self, url, activate=True, incognito=False, _return_view=False):
        """
        新規タブ追加。

        _return_view=True の場合は作成した QWebEngineView を返す。
        createWindow からの呼び出し時に使用する内部フラグ。
        """
        web_view = QWebEngineView()

        # createWindow 経由の場合は呼び出し元ページのプロファイルを引き継ぐ
        # 通常は self.profile、シークレットは self.incognito_profile
        profile = self.incognito_profile if incognito else self.profile
        page = CustomWebEnginePage(profile, web_view)
        page.fullScreenRequested.connect(self.handle_fullscreen_request)

        # new_tab_requested は createWindow 経由では使わないが、
        # JavaScript の window.open() など他の経路で発火することがある。
        # ただし二重タブ防止のため接続しない（createWindow が直接タブを作る）。

        web_view.setPage(page)
        web_view.setUrl(QUrl(url))

        web_view.titleChanged.connect(lambda title: self.update_tab_title(web_view, title))
        web_view.urlChanged.connect(lambda u: self.update_url_bar(web_view, u))
        web_view.loadFinished.connect(lambda: self.on_load_finished(web_view, incognito))
        web_view.loadStarted.connect(lambda: self.on_load_started(web_view))
        web_view.loadProgress.connect(lambda p: self.on_load_progress(web_view, p))

        # 中クリックで新タブ
        def _on_mouse_press(event, _wv=web_view):
            from PySide6.QtCore import Qt as _Qt
            if event.button() == _Qt.MiddleButton:
                hit = _wv.page().hitTestContent(event.pos())
                url_str = hit.linkUrl().toString() if hit and not hit.linkUrl().isEmpty() else ""
                if url_str:
                    self.add_new_tab(url=url_str, activate=True)
                    event.accept()
                    return
            QWebEngineView.mousePressEvent(_wv, event)
        web_view.mousePressEvent = _on_mouse_press

        tab_item = TabItem("新しいタブ", web_view, incognito=incognito)

        self.tab_list.addItem(tab_item)
        self.tab_list.setItemWidget(tab_item, tab_item.widget)

        # 閉じるボタンのシグナル接続
        tab_item.widget.close_requested.connect(lambda: self.close_tab_by_item(tab_item))

        self.tabs.append(web_view)

        if activate:
            self.tab_list.setCurrentItem(tab_item)

        mode = "Incognito" if incognito else "Normal"
        log(f"[INFO] TabControl: Add ({mode})")

        if _return_view:
            return web_view
    
    def handle_fullscreen_request(self, request):
        """全画面表示リクエスト処理"""
        if request.toggleOn():
            log("[INFO] Fullscreen: ON")
            request.accept()
        else:
            log("[INFO] Fullscreen: OFF")
            request.accept()
    
    def on_load_finished(self, web_view, incognito=False):
        """ページ読み込み完了時"""
        url = web_view.url().toString()
        title = web_view.title()
        # シークレットタブは履歴に記録しない
        if not incognito:
            self.history_manager.add_history(url, title)
        self._stop_progress_bar()
    
    def on_load_started(self, web_view):
        """ページ読み込み開始時"""
        current_item = self.tab_list.currentItem()
        if current_item and isinstance(current_item, TabItem) and current_item.web_view == web_view:
            self._start_progress_bar()
    
    def on_load_progress(self, web_view, progress):
        """ページ読み込み進捗更新"""
        current_item = self.tab_list.currentItem()
        if current_item and isinstance(current_item, TabItem) and current_item.web_view == web_view:
            if progress > 0 and progress < 100:
                self._progress_timer.stop()
                self._show_progress_bar()
                display = min(progress, 85)
                self.load_progress_bar.setValue(display)
            elif progress == 100:
                self.load_progress_bar.setValue(100)
    
    def _show_progress_bar(self):
        """進捗バーを表示状態に（色を戻す）"""
        self.load_progress_bar.setStyleSheet(STYLES['load_progress_bar'])

    def _hide_progress_bar(self):
        """進捗バーを非表示状態に（透明化・領域は保持）"""
        self.load_progress_bar.setStyleSheet(
            STYLES['load_progress_bar'] + "QProgressBar::chunk { background-color: transparent; }"
        )
        self.load_progress_bar.setValue(0)

    def _start_progress_bar(self):
        """ロード開始時に進捗バーをアニメーション開始（疑似進捗）"""
        self._pseudo_progress = 0
        self.load_progress_bar.setValue(0)
        self._show_progress_bar()
        self._progress_timer.start()
    
    def _advance_pseudo_progress(self):
        """疑似進捗を少しずつ進める（最大85%で止まる）"""
        if self._pseudo_progress < 30:
            self._pseudo_progress += 5
        elif self._pseudo_progress < 60:
            self._pseudo_progress += 3
        elif self._pseudo_progress < 85:
            self._pseudo_progress += 1
        else:
            self._progress_timer.stop()
            return
        self.load_progress_bar.setValue(self._pseudo_progress)
    
    def _stop_progress_bar(self):
        """ロード完了時に進捗バーを終了（透明化）"""
        self._progress_timer.stop()
        self.load_progress_bar.setValue(100)
        QTimer.singleShot(300, self._hide_progress_bar)
    
    def on_tab_changed(self, current, previous):
        """タブ切り替え"""
        if current is None:
            return

        # 既存ウィジェットをコンテナから取り外す
        for i in reversed(range(self.web_layout.count())):
            widget = self.web_layout.itemAt(i).widget()
            if widget:
                self.web_layout.removeWidget(widget)
                widget.setParent(None)

        tab_item = current

        # ----- 通常の Web タブ -----
        web_view = tab_item.web_view
        self.web_layout.addWidget(web_view)
        web_view.show()

        self.url_bar.setText(web_view.url().toString())
        if not self.url_bar.hasFocus():
            self.url_bar.home(False)
        zoom = self._zoom_levels.get(web_view, 1.0)
        web_view.setZoomFactor(zoom)
        self.update_window_title(web_view.title())

        # ロード進捗バーをリセット
        self._stop_progress_bar()

    
    def update_tab_title(self, web_view, title):
        """タブタイトル更新"""
        for i in range(self.tab_list.count()):
            item = self.tab_list.item(i)
            if isinstance(item, TabItem) and item.web_view == web_view:
                display_title = title[:30] + "..." if len(title) > 30 else title
                item.widget.set_title(display_title)
                
                # 現在アクティブなタブの場合、ウィンドウタイトルも更新
                if self.tab_list.currentItem() == item:
                    self.update_window_title(title)
                break
    
    def update_url_bar(self, web_view, url):
        """URLバー更新"""
        current_item = self.tab_list.currentItem()
        if current_item and isinstance(current_item, TabItem):
            if current_item.web_view == web_view:
                self.url_bar.setText(url.toString())
                # フォーカスがURLバーにない場合は先頭を表示
                if not self.url_bar.hasFocus():
                    self.url_bar.home(False)
    
    def update_window_title(self, page_title):
        """ウィンドウタイトルを更新"""
        if page_title:
            self.setWindowTitle(f"{page_title} - {BROWSER_FULL_NAME}")
        else:
            self.setWindowTitle(BROWSER_FULL_NAME)
    
    # 検索候補先頭に付けるプレフィックス（navigate_to_url での判定にも使用）
    _SEARCH_PREFIX = "\U0001f50d "  # 🔍

    @staticmethod
    def _looks_like_url(text: str) -> bool:
        """入力が明らかにURLと判断できるか（検索エントリ表示の抑制に使用）"""
        t = text.strip()
        if not t or ' ' in t:
            return False
        # http(s):// または ftp:// スキーム付き
        if re.match(r'^https?://', t) or re.match(r'^ftp://', t):
            return True
        # www. 始まり
        if t.startswith('www.'):
            return True
        # ドットを含み、スペースなし（example.com など）
        if '.' in t and not t.startswith('.') and not t.endswith('.'):
            parts = t.split('.')
            if len(parts) >= 2 and len(parts[-1]) >= 2:
                return True
        return False

    def _update_url_completer(self, text):
        """URLバー入力中に履歴を検索してオートコンプリート候補を更新"""
        if len(text) < 1:
            self._completer_model.setStringList([])
            return

        results = self.history_manager.search_history(text, limit=10)
        # URL と タイトル 両方を候補に（重複排除）
        seen = set()
        candidates = []
        for url, title, _, _ in results:
            if url not in seen:
                seen.add(url)
                candidates.append(url)
            if title and title not in seen:
                seen.add(title)
                candidates.append(title)

        # 明らかなURL入力のときは「を検索」エントリを表示しない
        if self._looks_like_url(text):
            self._completer_model.setStringList(candidates)
        else:
            search_entry = f"{self._SEARCH_PREFIX}{text} を検索"
            self._completer_model.setStringList([search_entry] + candidates)

    def _on_completer_activated(self, text: str):
        """コンプリーター候補がマウスクリック等で選択されたときの処理"""
        if text.startswith(self._SEARCH_PREFIX) and text.endswith(" を検索"):
            # 「🔍〇〇を検索」がクリックされた → 即検索
            query = text[len(self._SEARCH_PREFIX):-len(" を検索")]
            current_item = self.tab_list.currentItem()
            if current_item and isinstance(current_item, TabItem):
                url = self.process_url_or_search(query)
                current_item.web_view.setUrl(QUrl(url))
                # QCompleter が activated の後に候補テキストを LineEdit へ
                # 書き戻すため、次のイベントループで上書きして打ち消す
                QTimer.singleShot(0, lambda: self.url_bar.setText(url))

    def navigate_to_url(self):
        """URL移動（Enterキー）: 入力テキストをそのまま URL/検索として処理する"""
        current_item = self.tab_list.currentItem()
        if current_item and isinstance(current_item, TabItem):
            text = self.url_bar.text()
            url = self.process_url_or_search(text)
            current_item.web_view.setUrl(QUrl(url))
    
    def go_back(self):
        """戻る"""
        current_item = self.tab_list.currentItem()
        if current_item and isinstance(current_item, TabItem):
            current_item.web_view.back()
    
    def go_forward(self):
        """進む"""
        current_item = self.tab_list.currentItem()
        if current_item and isinstance(current_item, TabItem):
            current_item.web_view.forward()
    
    def reload_page(self):
        """再読み込み"""
        current_item = self.tab_list.currentItem()
        if current_item and isinstance(current_item, TabItem):
            current_item.web_view.reload()
    
    def show_tab_context_menu(self, position):
        """タブの右クリックメニューを表示"""
        item = self.tab_list.itemAt(position)
        if not isinstance(item, TabItem):
            return
        
        menu = QMenu(self)
        menu.setStyleSheet(STYLES['tab_context_menu'])
        
        # タブを閉じる
        close_action = QAction(qta.icon('fa5s.times', color=STYLES['icon_color_danger']), "タブを閉じる", self)
        close_action.triggered.connect(lambda: self.close_tab_by_item(item))
        menu.addAction(close_action)
        
        # 閉じたタブを開く
        reopen_action = QAction(qta.icon('fa5s.undo', color=STYLES['icon_color_default']), "閉じたタブを開く", self)
        reopen_action.triggered.connect(self.reopen_closed_tab)
        menu.addAction(reopen_action)
        
        # タブを複製
        duplicate_action = QAction(qta.icon('fa5s.clone', color=STYLES['icon_color_accent']), "タブを複製", self)
        duplicate_action.triggered.connect(lambda: self.duplicate_tab(item))
        menu.addAction(duplicate_action)
        
        menu.addSeparator()
        
        # ブックマークに追加
        bookmark_action = QAction(qta.icon('fa5s.star', color=STYLES['icon_color_bookmark']), "ブックマークに追加", self)
        bookmark_action.triggered.connect(lambda: self.add_bookmark_from_tab(item))
        menu.addAction(bookmark_action)
        
        menu.addSeparator()
        
        # ミュート/ミュート解除
        if item.is_muted:
            mute_action = QAction(qta.icon('fa5s.volume-up', color=STYLES['icon_color_primary']), "ミュート解除", self)
            mute_action.triggered.connect(lambda: self.toggle_mute(item))
        else:
            mute_action = QAction(qta.icon('fa5s.volume-mute', color=STYLES['icon_color_default']), "ミュート", self)
            mute_action.triggered.connect(lambda: self.toggle_mute(item))
        menu.addAction(mute_action)

        menu.addSeparator()

        # 他のブラウザで開く（SendURL）
        send_menu = QMenu("他のブラウザで開く", self)
        send_menu.setStyleSheet(STYLES['tab_context_menu'])
        send_menu.setIcon(qta.icon('fa5s.external-link-alt', color=STYLES['icon_color_default']))
        for browser_name, browser_cmd in self._get_external_browsers():
            act = QAction(browser_name, self)
            url_for_send = item.web_view.url().toString()
            act.triggered.connect(
                lambda checked=False, cmd=browser_cmd, u=url_for_send:
                    self._open_in_browser(cmd, url=u)
            )
            send_menu.addAction(act)
        menu.addMenu(send_menu)

        menu.exec(self.tab_list.mapToGlobal(position))
    
    def close_tab_by_item(self, item):
        """指定されたタブアイテムを閉じる"""
        if not isinstance(item, TabItem):
            return
        
        # タブが1つしかない場合はブラウザを閉じる
        if self.tab_list.count() == 1:
            log("[INFO] TabControl: Close(Exit)")
            self.close()
            return
        
        # タブのインデックスを取得
        for i in range(self.tab_list.count()):
            if self.tab_list.item(i) == item:
                # シークレットタブは閉じたタブスタックに追加しない
                if not item.incognito:
                    url = item.web_view.url().toString()
                    if url and not url.startswith("about:") and not url.startswith("chrome:"):
                        self._closed_tab_stack.append(url)
                        if len(self._closed_tab_stack) > 20:
                            self._closed_tab_stack.pop(0)
                self.tab_list.takeItem(i)
                self._zoom_levels.pop(item.web_view, None)
                item.web_view.deleteLater()
                if item.web_view in self.tabs:
                    self.tabs.remove(item.web_view)
                log("[INFO] TabControl: Close")
                break
    
    def reopen_closed_tab(self):
        """最後に閉じたタブを開く（なければホームページ）"""
        if self._closed_tab_stack:
            url = self._closed_tab_stack.pop()
            self.add_new_tab(url, activate=True)
            log(f"[INFO] TabControl: Reopen - {url}")
        else:
            self.add_new_tab(self.settings.value("homepage", "https://www.google.com"), activate=True)
            log("[INFO] TabControl: Reopen (no history, opening homepage)")
    
    def duplicate_tab(self, item):
        """タブを複製"""
        if isinstance(item, TabItem):
            url = item.web_view.url().toString()
            self.add_new_tab(url, activate=True)
            log(f"[INFO] TabControl: Duplicate - {url}")
    
    def add_bookmark_from_tab(self, item):
        """指定されたタブをブックマークに追加"""
        if isinstance(item, TabItem):
            url = item.web_view.url().toString()
            title = item.web_view.title() or "無題"
            
            folders = self.bookmark_manager.get_folders()
            dialog = AddBookmarkDialog(title, url, folders, self)
            
            if dialog.exec():
                result = dialog.get_result()
                if result:
                    self.bookmark_manager.add_bookmark(
                        result["title"], 
                        result["url"], 
                        result["folder"]
                    )
    
    def toggle_mute(self, item):
        """タブのミュート状態を切り替え"""
        if isinstance(item, TabItem):
            item.is_muted = not item.is_muted
            item.web_view.page().setAudioMuted(item.is_muted)
            item.widget.set_muted(item.is_muted)
            status = "ミュート" if item.is_muted else "ミュート解除"
            log(f"[INFO] TabControl: {status}")
    
    def close_current_tab(self):
        """現在のタブを閉じる"""
        current_item = self.tab_list.currentItem()
        if current_item:
            self.close_tab_by_item(current_item)
    

    def closeEvent(self, event):
        """終了時の処理"""
        self.save_current_session()
        
        if self.settings.value("clear_on_exit", False, type=bool):
            self.history_manager.clear_history()
        
        event.accept()