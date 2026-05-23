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
    IS_FIRST_RUN, IS_UPDATED, BROWSER_VERSION_NAME, INSTALL, INSTALL_MODE
from managers import HistoryManager, BookmarkManager, DownloadManager, SessionManager, UpdateChecker
from dialogs import AddBookmarkDialog, MainDialog, FindDialog, SavePageDialog


from PySide6.QtCore import QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QListWidgetItem



# =====================================================================
# strollon:// 内部URLスキームハンドラー
# =====================================================================

from PySide6.QtWebEngineCore import QWebEngineUrlSchemeHandler, QWebEngineUrlRequestJob, QWebEngineUrlScheme
from PySide6.QtCore import QBuffer, QByteArray


def _register_strollon_scheme():
    """strollon:// スキームをQtWebEngineに登録する（QApplication生成前に呼ぶこと）"""
    scheme = QWebEngineUrlScheme(b"strollon")
    scheme.setFlags(
        QWebEngineUrlScheme.SecureScheme |
        QWebEngineUrlScheme.LocalScheme |
        QWebEngineUrlScheme.LocalAccessAllowed |
        QWebEngineUrlScheme.ContentSecurityPolicyIgnored
    )
    QWebEngineUrlScheme.registerScheme(scheme)


# Strollon.py の main() より前に呼ぶため、モジュールロード時に実行
_register_strollon_scheme()


def _build_welcome_html(version_name: str, install: bool) -> str:
    """
    strollon://welcome 用HTML。
    「次へ/戻る」ウィザード形式、レガシー調デザイン。
    ページ構成:
      0: ようこそ
      1: アピールポイント
      2: リリースノート
      3: 始める (strollon://start へ遷移)
    """
    mode_label = "インストール版 (XDG)" if install else "ポータブル版"
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>ようこそ</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{
    height: 100%;
    font-family: "Segoe UI", "Meiryo", "MS Gothic", sans-serif;
    font-size: 13px;
    background: #d4d0c8;
    color: #000;
  }}
  .wizard-shell {{
    display: flex;
    flex-direction: column;
    height: 100vh;
  }}
  .wizard-body {{
    display: flex;
    flex: 1;
    overflow: hidden;
  }}
  .sidebar {{
    width: 164px;
    min-width: 164px;
    background: #ffffff;
    border-right: 1px solid #808080;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding-top: 24px;
    gap: 12px;
  }}
  .sidebar-logo {{
    width: 80px;
    height: 80px;
    border: 2px solid #808080;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    font-size: 11px;
    font-weight: bold;
    text-align: center;
    line-height: 1.4;
    letter-spacing: 1px;
  }}
  .sidebar-logo img {{
    width: 100%;
    height: 100%;
    object-fit: contain;
    display: block;
  }}
  .sidebar-ver {{
    font-size: 10px;
    color: #888;
    margin-top: auto;
    padding-bottom: 12px;
  }}
  .content-area {{
    flex: 1;
    background: #f0f0f0;
    overflow: hidden;
    position: relative;
  }}
  .slide {{
    position: absolute;
    inset: 0;
    padding: 28px 32px 16px;
    opacity: 0;
    display: none;
  }}
  .slide.active {{
    opacity: 1;
    display: block;
  }}
  .slide-heading {{
    border-bottom: 1px solid #808080;
    padding-bottom: 6px;
    margin-bottom: 16px;
  }}
  .slide-heading h1 {{
    font-size: 15px;
    font-weight: bold;
    color: #003087;
  }}
  .slide-heading p {{
    font-size: 11px;
    color: #444;
    margin-top: 3px;
  }}
  .welcome-text {{
    font-size: 13px;
    line-height: 1.8;
    color: #222;
    margin-bottom: 14px;
  }}
  .welcome-text b {{ color: #003087; }}
  .infobox {{
    background: #fff;
    border: 1px solid #808080;
    padding: 10px 14px;
    font-size: 12px;
    color: #333;
    line-height: 1.7;
  }}
  .feature-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }}
  .feature-table tr {{
    border-bottom: 1px solid #ccc;
  }}
  .feature-table td {{
    padding: 8px 10px;
    vertical-align: top;
  }}
  .feature-table td.icon-col {{
    width: 36px;
    text-align: center;
    padding-top: 10px;
  }}
  .feature-icon {{
    width: 24px;
    height: 24px;
    background: #003087;
    border: 1px solid #808080;
    display: inline-block;
  }}
  .feature-name {{
    font-weight: bold;
    color: #003087;
    display: block;
    margin-bottom: 2px;
  }}
  .feature-desc {{
    color: #444;
    line-height: 1.5;
  }}
  .release-scroll {{
    height: calc(100vh - 220px);
    overflow-y: auto;
    background: #fff;
    border: 1px solid #808080;
    padding: 10px 14px;
  }}
  .release-scroll h2 {{
    font-size: 12px;
    font-weight: bold;
    background: #003087;
    color: #fff;
    padding: 3px 8px;
    margin-bottom: 6px;
    margin-top: 10px;
  }}
  .release-scroll h2:first-child {{ margin-top: 0; }}
  .release-scroll ul {{
    padding-left: 16px;
    margin-bottom: 4px;
  }}
  .release-scroll li {{
    font-size: 12px;
    line-height: 1.8;
    color: #222;
  }}
  .tag {{
    display: inline-block;
    font-size: 10px;
    font-weight: bold;
    padding: 0 4px;
    margin-right: 4px;
    border: 1px solid;
    vertical-align: middle;
    line-height: 1.4;
  }}
  .tag-new {{ background: #cce0ff; color: #003087; border-color: #003087; }}
  .tag-fix {{ background: #ccffcc; color: #006400; border-color: #006400; }}
  .tag-del {{ background: #fff0cc; color: #804000; border-color: #804000; }}
  .finish-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    margin-bottom: 14px;
  }}
  .finish-table th, .finish-table td {{
    border: 1px solid #808080;
    padding: 5px 10px;
    text-align: left;
  }}
  .finish-table th {{
    background: #d4d0c8;
    width: 130px;
    font-weight: bold;
  }}
  .wizard-footer {{
    background: #d4d0c8;
    border-top: 1px solid #808080;
    padding: 8px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}
  .footer-steps {{
    font-size: 11px;
    color: #555;
  }}
  .footer-btns {{
    display: flex;
    gap: 6px;
    align-items: center;
  }}
  .btn {{
    font-size: 12px;
    font-family: inherit;
    padding: 4px 18px;
    border: 1px solid #999;
    cursor: pointer;
    font-weight: normal;
    background: #fff;
    color: #000;
    min-width: 80px;
  }}
  .btn:hover {{
    background: #f0f0f0;
  }}
  .btn:active {{
    background: #e0e0e0;
  }}
  .btn:disabled {{
    color: #aaa;
    border-color: #ccc;
    cursor: default;
    background: #f8f8f8;
  }}
  .btn-primary {{
    background: #fff;
    color: #003087;
    border-color: #003087;
    font-weight: bold;
  }}
  .btn-primary:hover {{ background: #eaf0ff; }}
  .btn-finish {{
    background: #fff;
    color: #006400;
    border-color: #006400;
    font-weight: bold;
  }}
  .btn-finish:hover {{ background: #efffef; }}
  .sep {{
    border-left: 1px solid #808080;
    height: 20px;
    margin: 0 4px;
  }}
</style>
</head>
<body>
<div class="wizard-shell">

  <div class="wizard-body">

    <div class="sidebar">
      <div class="sidebar-logo" id="sidebarLogo">
        <img src="data:image/png;base64,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" alt="Strollon">
      </div>
      <div class="sidebar-ver">Ver. {version_name}</div>
    </div>

    <div class="content-area">

      <!-- スライド 0: ようこそ -->
      <div class="slide active" id="slide0">
        <div class="slide-heading">
          <h1>Strollon Browser へようこそ</h1>
        </div>
        <p class="welcome-text">
          このウィザードでは <b>Strollon Browser {version_name}</b> の<br>
          新機能と変更点をご案内します。<br><br>
          「次へ」をクリックしてください。
        </p>
        <div class="infobox">
          <b>このブラウザについて</b><br>
          Strollon は、縦タブ対応のシンプルな Web ブラウザです。<br><br>
          Pythonベースで、Chromium エンジンを採用する LGPL、<br>
          過去のInternetStrollerシリーズの設計思想と、VELA Praxisの拡張性を合流させた、新しいブラウザです。
        </div>
      </div>

      <!-- スライド 1: アピールポイント -->
      <div class="slide" id="slide1">
        <div class="slide-heading">
          <h1>主な機能</h1>
          <p>Strollon の特徴をご紹介します。</p>
        </div>
        <table class="feature-table">
          <tr>
            <td class="icon-col"><div class="feature-icon"></div></td>
            <td>
              <span class="feature-name">縦タブパネル</span>
              <span class="feature-desc">縦タブでタブ管理。並び替えやタブのコピーなども。</span>
            </td>
          </tr>
          <tr>
            <td class="icon-col"><div class="feature-icon"></div></td>
            <td>
              <span class="feature-name">シークレットタブ</span>
              <span class="feature-desc">履歴・Cookie を保存しないシークレットモードを「タブ単位で」利用できます。</span>
            </td>
          </tr>
          <tr>
            <td class="icon-col"><div class="feature-icon"></div></td>
            <td>
              <span class="feature-name">プライバシー・ファースト</span>
              <span class="feature-desc">AdblockライブラリとEasyListによる広告ブロックと、Do Not Trackを搭載。</span>
            </td>
          </tr>
          <tr>
            <td class="icon-col"><div class="feature-icon"></div></td>
            <td>
              <span class="feature-name">テーマ対応</span>
              <span class="feature-desc">Default / Dark / Sakura など複数テーマを設定から利用できます。</span>
            </td>
          </tr>
          <tr>
            <td class="icon-col"><div class="feature-icon"></div></td>
            <td>
              <span class="feature-name">Chromium エンジン</span>
              <span class="feature-desc">Qt WebEngine (Chromium ベース) により現代的なサイトを快適に閲覧できます。</span>
            </td>
          </tr>
          <tr>
            <td class="icon-col"><div class="feature-icon"></div></td>
            <td>
              <span class="feature-name">強固な結合</span>
              <span class="feature-desc">ポータブルと必要最小限の思想のISMemoriaと、VELAのモダン技術を結合。</span>
            </td>
          </tr>
          <tr>
            <td class="icon-col"><div class="feature-icon"></div></td>
            <td>
              <span class="feature-name">最小構成</span>
              <span class="feature-desc">わかりやすく、洗練された軽量システムデザイン</span>
            </td>
          </tr>
          <tr>
            <td class="icon-col"><div class="feature-icon"></div></td>
            <td>
              <span class="feature-name">XDG準拠</span>
              <span class="feature-desc">XDGに準拠、またはポータブルもOK</span>
            </td>
          </tr>
        </table>
      </div>

      <!-- スライド 2: リリースノート -->
      <div class="slide" id="slide2">
        <div class="slide-heading">
          <h1>リリースノート</h1>
          <p>Version {version_name} の変更内容です。</p>
        </div>
        <div class="release-scroll">
          <h2>0.4.0.0 Preview</h2>
          <ul>
            <li><span class="tag tag-new">新機能</span> EasyList / EasyPrivacy / EasyList Japan に基づく広告ブロックを実装</li>
            <li><span class="tag tag-fix">改善</span> アップデート時の更新確認のバグを修正</li>
            <li><span class="tag tag-del">削除</span> 今回は特にありません</li>
          </ul>
        </div>
      </div>

      <!-- スライド 3: 完了 -->
      <div class="slide" id="slide3">
        <div class="slide-heading">
          <h1>準備完了</h1>
          <p>Strollon Browser の準備が整いました。</p>
        </div>
        <table class="finish-table">
          <tr><th>バージョン</th><td>{version_name}</td></tr>
          <tr><th>インストール種別</th><td>{mode_label}</td></tr>
          <tr><th>対応 OS</th><td>Linux (Wayland) / Windows 11+</td></tr>
          <tr><th>開発者</th><td>ABATBeliever</td></tr>
          <tr><th>ライセンス</th><td>GNU LGPL v3</td></tr>
        </table>
        <p style="font-size:12px; color:#333; line-height:1.7; margin-top:12px;">
          「完了」をクリックするとスタートページが開きます。<br>
          このページは strollon://welcome からいつでも再表示できます。
        </p>
      </div>

    </div><!-- /content-area -->
  </div><!-- /wizard-body -->

  <!-- フッターナビゲーション -->
  <div class="wizard-footer">
    <span class="footer-steps" id="stepLabel">1 / 4</span>
    <div class="footer-btns">
      <button class="btn" id="btnSkip" onclick="goStart()">スキップ</button>
      <div class="sep"></div>
      <button class="btn" id="btnBack" onclick="go(-1)" disabled>&#8592; 戻る</button>
      <button class="btn btn-primary" id="btnNext" onclick="go(1)">次へ &#8594;</button>
    </div>
  </div>

</div><!-- /wizard-shell -->

<script>
  var TOTAL = 4;
  var cur = 0;

  function go(dir) {{
    var next = cur + dir;
    if (next < 0 || next >= TOTAL) return;

    document.getElementById('slide' + cur).className = 'slide';
    cur = next;
    document.getElementById('slide' + cur).className = 'slide active';

    updateUI();
  }}

  function updateUI() {{
    document.getElementById('stepLabel').textContent = (cur + 1) + ' / ' + TOTAL;
    document.getElementById('btnBack').disabled = (cur === 0);

    var btnNext = document.getElementById('btnNext');
    var btnSkip = document.getElementById('btnSkip');

    if (cur === TOTAL - 1) {{
      btnNext.textContent = '完了';
      btnNext.className = 'btn btn-finish';
      btnNext.onclick = goStart;
      btnSkip.style.visibility = 'hidden';
    }} else {{
      btnNext.textContent = '次へ \u2192';
      btnNext.className = 'btn btn-primary';
      btnNext.onclick = function() {{ go(1); }};
      btnSkip.style.visibility = 'visible';
    }}
  }}

  function goStart() {{
    window.location.href = 'strollon://start';
  }}

  updateUI();
</script>
</body>
</html>"""


def _build_start_html() -> str:
    """strollon://start"""
    return """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>新しいタブ</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background-color: #f5f5f5;
            transition: background-color 0.3s ease, color 0.3s ease;
        }

        .search-container {
            text-align: center;
            padding: 30px;
            background-color: white;
            border-radius: 10px;
            box-shadow: 0px 2px 5px rgba(0, 0, 0, 0);
            display: inline-block;
            transition: background-color 0.3s ease;
        }

        .search-input {
            width: 90%;
            padding: 10px;
            border: 1px solid #ccc;
            border-radius: 5px;
        }

        .search-button {
            background-color: #007BFF;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 10px 20px;
            margin-top: 10px;
            cursor: pointer;
        }

        .search-button:hover {
            background-color: #0056B3;
        }

        canvas {
            border: 1px solid #333;
            display: none;
            margin: 20px auto;
        }

        #scoreDisplay {
            font-size: 18px;
            margin-bottom: 10px;
            display: none;
        }

        #uploadContainer {
            margin-bottom: 20px;
            display: none;
            text-align: center;
        }

        input[type="file"] {
            margin-right: 10px;
        }

        button {
            padding: 8px 200px;
            background-color: #4CAF50;
            color: white;
            border: none;
            cursor: pointer;
        }

        #online-status {
            position: fixed;
            bottom: 10px;
            right: 10px;
        }

        #gameLink {
            position: fixed;
            bottom: 10px;
            left: 10px;
            cursor: pointer;
        }

        table, th, td {
            border: 1px #000000 solid;
            text-align: center;
        }

    </style>
</head>
<body>
    <div class="search-container">
        <input type="text" class="search-input" placeholder="Internet Stroller Syncria">
        <button class="search-button" onclick="search('bing')">Microsoft Bing</button>
        <button class="search-button" onclick="search('google')">Google</button>
        <button class="search-button" onclick="search('duckduckgo')">DuckDuckGo</button>
    </div>

    <div id="online-status"></div>

<script>
    const onlineStatusDiv = document.getElementById('online-status');
    const searchInput = document.querySelector('.search-input');

    function search(engine) {
        const searchInput = document.querySelector('.search-input').value;
        let url;

        if (engine === 'bing') {
            url = `https://www.bing.com/search?q=${encodeURIComponent(searchInput)}`;
        } else if (engine === 'google') {
            url = `https://www.google.com/search?q=${encodeURIComponent(searchInput)}`;
        } else if (engine === 'duckduckgo') {
            url = `https://duckduckgo.com/?q=${encodeURIComponent(searchInput)}`;
        }

        window.location.href = url;
    }

    searchInput.addEventListener("keydown", function(event) {
        if (event.key === "Enter") {
            search("duckduckgo");
        }
    });

    function updateOnlineStatus() {
        if (navigator.onLine) {
            onlineStatusDiv.textContent = 'ONLINE';
            onlineStatusDiv.style.color = 'green';
        } else {
            onlineStatusDiv.textContent = 'OFFLINE';
            onlineStatusDiv.style.color = 'red';
        }
    }

    updateOnlineStatus();
    window.addEventListener('online', updateOnlineStatus);
    window.addEventListener('offline', updateOnlineStatus);
</script>

</body>
</html>"""


class StrollonSchemeHandler(QWebEngineUrlSchemeHandler):
    """
    strollon:// 内部URLスキームのリクエストを処理するハンドラー。
    対応URL:
      strollon://welcome  — ようこそページ
      strollon://start    — スタートページ
    """

    def requestStarted(self, job: QWebEngineUrlRequestJob):
        url = job.requestUrl()
        host = url.host().lower()

        if host == "welcome":
            html = _build_welcome_html(BROWSER_VERSION_NAME, INSTALL)
        elif host == "start":
            html = _build_start_html()
        else:
            job.fail(QWebEngineUrlRequestJob.UrlNotFound)
            return

        data = QByteArray(html.encode("utf-8"))
        buf = QBuffer(job)
        buf.setData(data)
        buf.open(QBuffer.ReadOnly)
        job.reply(b"text/html; charset=utf-8", buf)


# =====================================================================
# DNT（Do Not Track）URLリクエストインターセプター
# =====================================================================

class AdBlockInterceptor(QWebEngineUrlRequestInterceptor):
    """
    広告ブロック + DNT ヘッダー付加を行うリクエストインターセプター。
    旧 DntRequestInterceptor を置き換える。
    """

    def __init__(self, adblock_manager=None, enabled: bool = False, parent=None):
        super().__init__(parent)
        self._dnt_enabled = enabled
        self._adblock_manager = adblock_manager

    def set_dnt_enabled(self, enabled: bool):
        self._dnt_enabled = enabled

    def set_adblock_manager(self, manager):
        self._adblock_manager = manager

    def interceptRequest(self, info):
        # DNT ヘッダー付加
        info.setHttpHeader(b"DNT", b"1" if self._dnt_enabled else b"0")

        # 広告ブロック
        if self._adblock_manager and self._adblock_manager.is_enabled():
            url        = info.requestUrl().toString()
            # initiatorOrigin() は PySide6 に存在しない。
            # firstPartyUrl() でリクエスト元ページの URL を取得する。
            source_url = info.firstPartyUrl().toString() or url
            rtype      = info.resourceType().value
            if self._adblock_manager.should_block(url, source_url, rtype):
                info.block(True)


# 後方互換エイリアス（万が一他モジュールから参照されている場合用）
DntRequestInterceptor = AdBlockInterceptor






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

        # strollon:// スキームハンドラーを両プロファイルに登録
        self._strollon_handler = StrollonSchemeHandler(self)
        self._strollon_handler_incognito = StrollonSchemeHandler(self)
        self.profile.installUrlSchemeHandler(b"strollon", self._strollon_handler)
        self.incognito_profile.installUrlSchemeHandler(b"strollon", self._strollon_handler_incognito)

        self.history_manager = HistoryManager()
        self.bookmark_manager = BookmarkManager()
        self.download_manager = DownloadManager()
        self.session_manager = SessionManager()
        self.settings = settings

        # 広告ブロックマネージャー（インターセプターより先に初期化）
        from managers import AdBlockManager
        self.adblock_manager = AdBlockManager()

        # AdBlock + DNT インターセプターを両プロファイルに登録
        self._dnt_interceptor = AdBlockInterceptor(
            adblock_manager=self.adblock_manager, enabled=False, parent=self
        )
        self._dnt_interceptor_incognito = AdBlockInterceptor(
            adblock_manager=self.adblock_manager, enabled=False, parent=self
        )
        self.profile.setUrlRequestInterceptor(self._dnt_interceptor)
        self.incognito_profile.setUrlRequestInterceptor(self._dnt_interceptor_incognito)
        
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
        self.do_not_track = self.settings.value("do_not_track", False, type=bool)
        self._dnt_interceptor.set_dnt_enabled(self.do_not_track)
        self._dnt_interceptor_incognito.set_dnt_enabled(self.do_not_track)
        log(f"[INFO] DNT header set to: {'1' if self.do_not_track else '0'}")

        # 広告ブロック設定をインターセプターに反映
        if hasattr(self, 'adblock_manager'):
            self._dnt_interceptor.set_adblock_manager(self.adblock_manager)
            self._dnt_interceptor_incognito.set_adblock_manager(self.adblock_manager)
            log(f"[INFO] AdBlock: enabled={self.adblock_manager.is_enabled()}, rules={self.adblock_manager.rule_count()}")


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
        """セッションを復元。初回起動時・更新時はウェルカムページを表示する。"""

        # 初回起動 or バージョン更新: ウェルカムページを開く
        if IS_FIRST_RUN or IS_UPDATED:
            reason = "初回起動" if IS_FIRST_RUN else "バージョン更新"
            log(f"[INFO] {reason}: ウェルカムページを表示します")
            self.add_new_tab("strollon://welcome", activate=True)
            # sync() は main() で既に呼ばれているが、
            # ここでも呼んで確実に新バージョンをファイルへ書き込む
            # （次回起動時に IS_UPDATED が False になることを保証する）
            self.settings.sync()
            # 初回起動時: フィルタファイルが未取得であれば自動ダウンロード開始
            if IS_FIRST_RUN and hasattr(self, "adblock_manager")                     and not self.adblock_manager._filter_path.exists():
                log("[INFO] AdBlock: 初回起動のためフィルターを自動ダウンロードします")
                self.adblock_manager.update_filters()
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
            homepage = self.settings.value("homepage", "strollon://start")
            self.add_new_tab(homepage)
        else:
            self.add_new_tab("strollon://start")

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
            # about: / chrome: / strollon: など復元しても意味のないURLも除外
            if not url or url.startswith("about:") or url.startswith("chrome:") or url.startswith("strollon:"):
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
            lambda: self.add_new_tab(self.settings.value("homepage", "strollon://start")))
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
        new_tab_action.triggered.connect(lambda: self.add_new_tab(self.settings.value("homepage", "strollon://start")))
        menu.addAction(new_tab_action)
        
        # シークレットタブ
        incognito_action = QAction(qta.icon('fa5s.user-secret', color=STYLES['icon_color_incognito']), "シークレットタブ", self)
        incognito_action.triggered.connect(lambda: self.add_new_tab(
            self.settings.value("homepage", "strollon://start"), incognito=True))
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
        new_tab_btn.clicked.connect(lambda: self.add_new_tab(self.settings.value("homepage", "strollon://start")))
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
        
        return search_urls.get(search_engine, search_urls[2])  # デフォルト: duck
    
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

        # 内部スキームはそのまま通す
        if text.startswith("strollon://"):
            return text

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
        # シークレットタブ・内部URLは履歴に記録しない
        if not incognito and not url.startswith("strollon:"):
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
            self.add_new_tab(self.settings.value("homepage", "strollon://start"), activate=True)
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

        # ブロックカウントを永続化（100件未満の端数を確実に保存）
        if hasattr(self, "adblock_manager"):
            self.adblock_manager.flush_block_count()

        event.accept()