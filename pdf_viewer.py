"""
Strollon Browser - PDF.js 統合モジュール
=====================================================================
WebEngine 標準の PDF ビューアは使用せず、pdf.js (Apache-2.0) を
strollon-pdf:// という専用の内部スキームでホストして表示する。

設計概要
---------------------------------------------------------------------
1. PDF への「ナビゲーション」は WebEngine 側では「ダウンロード」として
   検出される（PdfViewerEnabled=False のため）。browser.py 側の
   on_download_requested でこれを捕まえ、ユーザーの目に見えるURLは
   元のPDF URLのまま、実体だけを pdf.js ビューアに差し替える。

2. キャッシュは sha-256(元URL) を鍵として pdfjs_cache/ 配下に保存する。
   起動時・終了時にクリアする。

3. ビューアの表示用URL:
     strollon-pdf://viewer/web/viewer.html?file=strollon-pdf://viewer/data/<sha256>/xxx.pdf
   アドレスバーには常に元のPDF URLを表示する。逆引き手段として
   _pdf_digest_to_original dict（sha256 → 元URL）を使い、QUrlの
   文字列化の揺らぎに左右されない設計にしている。

4. pdf.js のアセットとキャッシュPDFを同一オリジン（strollon-pdf://viewer）
   で配信することで fetch()/Worker の CORS 問題を回避する。

5. viewer.html 配信時に、Strollon と統合できない機能
   （印刷・ファイルを開く・プレゼンテーションモード・ページ番号入力）を
   CSS で非表示にする。
"""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse, unquote

from PySide6.QtCore import QBuffer, QByteArray, QFile, QIODevice, QUrl, QUrlQuery
from PySide6.QtWebEngineCore import (
    QWebEngineUrlRequestJob,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)

# =====================================================================
# 定数
# =====================================================================

PDF_SCHEME = b"strollon-pdf"
PDF_SCHEME_STR = "strollon-pdf"
PDF_VIEWER_HOST = "viewer"
PDF_CACHE_SUBDIR = "pdfjs_cache"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# ---- Strollon が非表示にするツールバー要素 -----------------------------------
# QtWebEngine のChromiumバージョンでは動作しない・または Strollon と
# 統合できない機能を CSS で完全に隠す。
#   - 印刷ボタン (#printButton, #secondaryPrint)
#   - ファイルを開く (#secondaryOpenFile)
#   - プレゼンテーションモード (#presentationMode)
#   - ページ番号入力欄 (.loadingInput.start, #numPages) ← 前後ナビは残す
# セパレータの浮きも考慮して親要素ごと隠せるものは親ごと隠す。
_STROLLON_CSS = b"""
/* Strollon: hide unsupported toolbar features */
/* Print */
#printButton,
#secondaryPrint { display: none !important; }
/* Download button stays; only print is hidden in this group */
.toolbarHorizontalGroup.hiddenMediumView #printButton { display: none !important; }

/* Open file */
#secondaryOpenFile { display: none !important; }

/* Presentation mode */
#presentationMode { display: none !important; }

/* Page number input and total-pages label */
.loadingInput.start,
#numPages { display: none !important; }
"""

# 拡張子 → MIME タイプ
_MIME_TYPES: dict[str, bytes] = {
    ".html": b"text/html; charset=utf-8",
    ".htm":  b"text/html; charset=utf-8",
    ".mjs":  b"text/javascript; charset=utf-8",
    ".js":   b"text/javascript; charset=utf-8",
    ".css":  b"text/css; charset=utf-8",
    ".json": b"application/json; charset=utf-8",
    ".map":  b"application/json; charset=utf-8",
    ".pdf":  b"application/pdf",
    ".bcmap": b"application/octet-stream",
    ".pfb":  b"application/octet-stream",
    ".ttf":  b"font/ttf",
    ".otf":  b"font/otf",
    ".woff": b"font/woff",
    ".woff2": b"font/woff2",
    ".png":  b"image/png",
    ".svg":  b"image/svg+xml",
    ".gif":  b"image/gif",
    ".icc":  b"application/octet-stream",
    ".ftl":  b"text/plain; charset=utf-8",
    ".properties": b"text/plain; charset=utf-8",
    ".wasm": b"application/wasm",
}
_DEFAULT_MIME = b"application/octet-stream"

# viewer.html に挿入するスタイルタグ（バイト列）
_STYLE_INJECTION = b"\n<style>" + _STROLLON_CSS + b"</style>\n</head>"


# =====================================================================
# スキーム登録（QApplication 生成前に1回だけ呼ぶこと）
# =====================================================================

def register_pdf_scheme() -> None:
    """strollon-pdf:// スキームを QtWebEngine に登録する。"""
    scheme = QWebEngineUrlScheme(PDF_SCHEME)
    scheme.setFlags(
        QWebEngineUrlScheme.SecureScheme |
        QWebEngineUrlScheme.LocalScheme |
        QWebEngineUrlScheme.LocalAccessAllowed |
        QWebEngineUrlScheme.ContentSecurityPolicyIgnored |
        QWebEngineUrlScheme.CorsEnabled |
        QWebEngineUrlScheme.FetchApiAllowed
    )
    QWebEngineUrlScheme.registerScheme(scheme)


# =====================================================================
# キャッシュ関連ヘルパー
# =====================================================================

def pdf_cache_dir(base_cache_dir: Path) -> Path:
    d = base_cache_dir / PDF_CACHE_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def url_to_digest(url: str) -> str:
    """URL文字列から SHA-256 hex を生成する。キャッシュキー兼逆引きキー。"""
    return hashlib.sha256(url.encode("utf-8", errors="surrogatepass")).hexdigest()


def cache_path_for_url(base_cache_dir: Path, url: str) -> Path:
    digest = url_to_digest(url)
    return pdf_cache_dir(base_cache_dir) / f"{digest}.pdf"


def clear_pdf_cache(base_cache_dir: Path) -> None:
    d = base_cache_dir / PDF_CACHE_SUBDIR
    if not d.exists():
        return
    try:
        shutil.rmtree(d, ignore_errors=True)
    except Exception:
        pass
    d.mkdir(parents=True, exist_ok=True)


def friendly_filename(original_url: str) -> str:
    try:
        name = Path(urlparse(original_url).path).name
    except Exception:
        name = ""
    if not name or not name.lower().endswith(".pdf"):
        name = "document.pdf"
    name = re.sub(r"[^\w\-. ]", "_", name).strip()
    return name or "document.pdf"


def build_viewer_url(original_url: str, cache_path: Path) -> QUrl:
    """pdf.js ビューアを開くための strollon-pdf:// URL を組み立てる。"""
    digest = cache_path.stem  # = sha-256

    data_url = QUrl()
    data_url.setScheme(PDF_SCHEME_STR)
    data_url.setHost(PDF_VIEWER_HOST)
    data_url.setPath(f"/data/{digest}/{friendly_filename(original_url)}")

    viewer_url = QUrl()
    viewer_url.setScheme(PDF_SCHEME_STR)
    viewer_url.setHost(PDF_VIEWER_HOST)
    viewer_url.setPath("/web/viewer.html")
    query = QUrlQuery()
    query.addQueryItem("file", data_url.toString())
    viewer_url.setQuery(query)
    return viewer_url


def digest_from_viewer_url(raw_url: str) -> str | None:
    """
    strollon-pdf://viewer/web/viewer.html?file=... という URL から
    SHA-256 ダイジェスト文字列を抽出して返す。
    解析できなければ None を返す。

    これにより QUrl.toString() のパーセントエンコーディングの揺らぎに
    依存せず、ダイジェスト経由で元URLを逆引きできる。
    """
    if not raw_url.startswith(f"{PDF_SCHEME_STR}://{PDF_VIEWER_HOST}/web/viewer.html"):
        return None
    try:
        qurl = QUrl(raw_url)
        file_param = QUrlQuery(qurl.query()).queryItemValue("file", QUrl.FullyDecoded)
        # QUrl が返す file_param（完全デコード済み）と、
        # さらにもう一度 unquote した候補の両方を試す（二重エンコーディング対策）
        candidates = [file_param, unquote(file_param)] if file_param else []
        # フォールバック: QUrl が使えない/失敗した場合は生文字列から正規表現で探す
        candidates += [raw_url, unquote(raw_url), unquote(unquote(raw_url))]
        for c in candidates:
            m = re.search(r"/data/([0-9a-f]{64})/", c)
            if m:
                return m.group(1)
    except Exception:
        for c in (raw_url, unquote(raw_url)):
            m = re.search(r"/data/([0-9a-f]{64})/", c)
            if m:
                return m.group(1)
    return None


def is_pdf_viewer_url(url: str) -> bool:
    return url.startswith(f"{PDF_SCHEME_STR}://{PDF_VIEWER_HOST}/web/viewer.html")


# =====================================================================
# strollon-pdf:// スキームハンドラー
# =====================================================================

class PdfSchemeHandler(QWebEngineUrlSchemeHandler):
    """
    strollon-pdf://viewer/ 配下のリクエストを処理するハンドラー。

      strollon-pdf://viewer/web/...    … pdfjs_dir 配下の静的アセット
      strollon-pdf://viewer/build/...  … 同上
      strollon-pdf://viewer/data/<sha256>/<任意のファイル名>.pdf
                                        … キャッシュ済みPDF実体

    viewer.html を返す際は <style> タグを挿入し、
    Strollon と統合できないツールバー機能を非表示にする。
    """

    def __init__(self, pdfjs_dir: Path, cache_dir: Path, parent=None):
        super().__init__(parent)
        self._pdfjs_dir = Path(pdfjs_dir).resolve()
        self._cache_dir = Path(cache_dir).resolve()

    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:
        url = job.requestUrl()
        path = url.path()

        if url.host().lower() != PDF_VIEWER_HOST:
            job.fail(QWebEngineUrlRequestJob.UrlNotFound)
            return

        if path.startswith("/data/"):
            self._serve_cached_pdf(job, path)
            return

        self._serve_asset(job, path)

    # ---- アセット配信 -------------------------------------------------

    def _serve_asset(self, job: QWebEngineUrlRequestJob, path: str) -> None:
        rel = path.lstrip("/") or "web/viewer.html"
        target = (self._pdfjs_dir / rel).resolve()

        try:
            target.relative_to(self._pdfjs_dir)
        except ValueError:
            job.fail(QWebEngineUrlRequestJob.RequestDenied)
            return

        if not target.is_file():
            job.fail(QWebEngineUrlRequestJob.UrlNotFound)
            return

        # viewer.html のみ CSS を注入する
        if target.name == "viewer.html":
            self._reply_viewer_html(job, target)
            return

        self._reply_file(job, target)

    def _reply_viewer_html(self, job: QWebEngineUrlRequestJob, path: Path) -> None:
        """viewer.html を読み込み、Strollon カスタム CSS を挿入して返す。"""
        try:
            html_bytes = path.read_bytes()
        except OSError:
            job.fail(QWebEngineUrlRequestJob.RequestFailed)
            return

        # </head> の直前にスタイルタグを挿入する
        patched = html_bytes.replace(b"</head>", _STYLE_INJECTION, 1)

        buf = QBuffer(job)          # job を親にして寿命を確保
        buf.setData(QByteArray(patched))
        buf.open(QIODevice.ReadOnly)
        job.reply(b"text/html; charset=utf-8", buf)

    # ---- キャッシュ済みPDF配信 ----------------------------------------

    def _serve_cached_pdf(self, job: QWebEngineUrlRequestJob, path: str) -> None:
        parts = [p for p in path.split("/") if p]
        # parts == ["data", "<sha256>", "<friendly-name>.pdf"]
        if len(parts) < 2 or not _SHA256_RE.match(parts[1]):
            job.fail(QWebEngineUrlRequestJob.UrlInvalid)
            return

        target = (self._cache_dir / f"{parts[1]}.pdf").resolve()
        try:
            target.relative_to(self._cache_dir)
        except ValueError:
            job.fail(QWebEngineUrlRequestJob.RequestDenied)
            return

        if not target.is_file():
            job.fail(QWebEngineUrlRequestJob.UrlNotFound)
            return

        self._reply_file(job, target, mime=b"application/pdf")

    # ---- 共通: ファイルをそのまま返す ----------------------------------

    def _reply_file(self, job: QWebEngineUrlRequestJob, path: Path, mime: bytes | None = None) -> None:
        if mime is None:
            mime = _MIME_TYPES.get(path.suffix.lower(), _DEFAULT_MIME)
        qfile = QFile(str(path), job)
        if not qfile.open(QIODevice.ReadOnly):
            job.fail(QWebEngineUrlRequestJob.RequestFailed)
            return
        job.reply(mime, qfile)
