"""
Strollon Browser - データ管理クラス群
履歴、ブックマーク、ダウンロード、セッション管理、更新チェック
"""

import sqlite3
import json
import platform as _platform
import ssl
from urllib.request import urlopen, Request
from urllib.error import URLError
from packaging import version

from PySide6.QtCore import QThread, Signal

from constants import (
    HISTORY_DB, BOOKMARKS_DB, SESSION_FILE, DOWNLOADS_DB,
    BROWSER_VERSION_SEMANTIC, UPDATE_CHECK_URL,
    set_db_strollon_version,
    stamp_version_to_json, check_version_stamp, VERSION_KEY, log
)


# =====================================================================
# HTTPS通信ヘルパー（OS証明書ストア優先 + certifiフォールバック）
# =====================================================================
#
# 1.3.0.0 バグ修正: 一部のWindows環境で、広告ブロックのフィルターダウンロード・
# 更新チェックの両方が常に
#   [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
#   unable to get local issuer certificate
# で失敗する不具合が報告された。urlopen() が明示的にcontextを渡さない場合、
# ssl.create_default_context() は内部的にOSの証明書ストアを参照するが、
# Nuitkaでビルドしたスタンドアロン配布物では、実行環境によってはこの
# システム証明書ストアの参照がうまくいかないケースがある
# （python.orgの通常のインストーラーで実行した場合には発生しない）。
#
# ここで「certifiへ完全に切り替える」のではなく「OS証明書ストアで検証に
# 失敗した場合にのみ certifi 同梱のCAバンドルで再試行する」設計にしている
# 理由: 社内プロキシ等でOS証明書ストアに独自のルートCAを追加している
# 企業環境では、そのOS証明書ストアでの検証が正しい挙動であり、certifiの
# 一般公開CAバンドルだけを使うとかえって接続できなくなる（実際に動作検証中、
# この開発環境のサンドボックスがまさにその状態だった: OS既定では成功するのに
# certifi固定にすると社内的な検証エラーになった）。まずOS既定を試し、
# 証明書検証エラーの場合にだけcertifiで再試行することで、両方のケースに
# 対応できるようにする。
_CERTIFI_CONTEXT = None
_CERTIFI_CONTEXT_TRIED = False

def _get_certifi_context():
    """certifi同梱のCAバンドルを使ったSSLContextを返す（フォールバック用）。
    certifi未インストール、または構築に失敗した場合は None を返す。"""
    global _CERTIFI_CONTEXT, _CERTIFI_CONTEXT_TRIED
    if _CERTIFI_CONTEXT_TRIED:
        return _CERTIFI_CONTEXT
    _CERTIFI_CONTEXT_TRIED = True
    try:
        import certifi
        _CERTIFI_CONTEXT = ssl.create_default_context(cafile=certifi.where())
    except Exception as e:
        log(f"[WARN] Network: certifi CA bundle unavailable ({e})")
        _CERTIFI_CONTEXT = None
    return _CERTIFI_CONTEXT


def _fetch_url(url: str, timeout: float, user_agent: str) -> bytes:
    """
    urlopen() のラッパー。まずOS既定の証明書ストアで通信を試み、
    証明書検証エラー（ssl.SSLCertVerificationError）の場合にのみ
    certifi 同梱のCAバンドルで自動的に再試行する。
    それ以外の例外（タイムアウト・DNS失敗等）はそのまま呼び出し元に送出する。
    """
    req = Request(url, headers={"User-Agent": user_agent})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except URLError as e:
        if not isinstance(e.reason, ssl.SSLCertVerificationError):
            raise
        fallback_ctx = _get_certifi_context()
        if fallback_ctx is None:
            raise
        log(f"[INFO] Network: OS certificate store failed for {url} "
            f"({e.reason}), retrying with certifi CA bundle")
        with urlopen(req, timeout=timeout, context=fallback_ctx) as resp:
            return resp.read()


# =====================================================================
# 履歴管理
# =====================================================================

class HistoryManager:
    """履歴管理クラス"""
    
    def __init__(self):
        self.db_path = HISTORY_DB
        self.init_database()
    
    def init_database(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url TEXT NOT NULL,
                        title TEXT,
                        visit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        visit_count INTEGER DEFAULT 1
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_url ON history(url)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_visit_time ON history(visit_time DESC)')
                set_db_strollon_version(conn)
                conn.commit()
            log("[INFO] History database initialized")
        except sqlite3.Error as e:
            log(f"[ERROR] History database init failed: {e}")
    
    def add_history(self, url, title):
        if not url or url.startswith("about:") or url.startswith("chrome:"):
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id, visit_count FROM history WHERE url = ?', (url,))
                result = cursor.fetchone()
                if result:
                    cursor.execute('''
                        UPDATE history 
                        SET title = ?, visit_time = CURRENT_TIMESTAMP, visit_count = ?
                        WHERE id = ?
                    ''', (title, result[1] + 1, result[0]))
                else:
                    cursor.execute('INSERT INTO history (url, title) VALUES (?, ?)', (url, title))
                set_db_strollon_version(conn)
                conn.commit()
        except sqlite3.Error as e:
            log(f"[ERROR] add_history failed: {e}")
    
    def get_history(self, limit=100):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, url, title, visit_time, visit_count 
                    FROM history 
                    ORDER BY visit_time DESC 
                    LIMIT ?
                ''', (limit,))
                return cursor.fetchall()
        except sqlite3.Error as e:
            log(f"[ERROR] get_history failed: {e}")
            return []
    
    def search_history(self, query, limit=50):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # クエリ中の LIKE ワイルドカード（% と _）およびエスケープ文字自体を
                # エスケープしてから ESCAPE 句を指定する。これをしないと、例えば
                # 検索欄に "%" や "_" を含む文字列を入力した際に、意図せず
                # ワイルドカードとして働いてしまう（不正確な検索結果につながる）。
                escaped_query = (
                    query.replace('\\', '\\\\')
                         .replace('%', '\\%')
                         .replace('_', '\\_')
                )
                pattern = f'%{escaped_query}%'
                cursor.execute('''
                    SELECT id, url, title, visit_time, visit_count 
                    FROM history 
                    WHERE url LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\'
                    ORDER BY visit_time DESC 
                    LIMIT ?
                ''', (pattern, pattern, limit))
                return cursor.fetchall()
        except sqlite3.Error as e:
            log(f"[ERROR] search_history failed: {e}")
            return []
    
    def delete_history(self, history_id: int):
        """指定IDの履歴を1件削除"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM history WHERE id = ?', (history_id,))
                conn.commit()
            log(f"[INFO] History entry deleted: {history_id}")
        except sqlite3.Error as e:
            log(f"[ERROR] delete_history failed: {e}")

    def clear_history(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM history')
                conn.commit()
            log("[INFO] History cleared")
        except sqlite3.Error as e:
            log(f"[ERROR] clear_history failed: {e}")


# =====================================================================
# ブックマーク管理
# =====================================================================

class BookmarkManager:
    """ブックマーク管理クラス"""
    
    def __init__(self):
        self.db_path = BOOKMARKS_DB
        self.init_database()
    
    def init_database(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS bookmarks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        url TEXT NOT NULL,
                        folder TEXT DEFAULT 'root',
                        created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                set_db_strollon_version(conn)
                conn.commit()
            log("[INFO] Bookmarks database initialized")
        except sqlite3.Error as e:
            log(f"[ERROR] Bookmarks database init failed: {e}")
    
    def add_bookmark(self, title, url, folder='root'):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO bookmarks (title, url, folder) VALUES (?, ?, ?)', 
                              (title, url, folder))
                set_db_strollon_version(conn)
                conn.commit()
            log(f"[INFO] Bookmark added: {title}")
        except sqlite3.Error as e:
            log(f"[ERROR] add_bookmark failed: {e}")
    
    def get_bookmarks(self, folder=None):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if folder:
                    cursor.execute('SELECT id, title, url, folder FROM bookmarks WHERE folder = ?', (folder,))
                else:
                    cursor.execute('SELECT id, title, url, folder FROM bookmarks')
                return cursor.fetchall()
        except sqlite3.Error as e:
            log(f"[ERROR] get_bookmarks failed: {e}")
            return []
    
    def get_folders(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT DISTINCT folder FROM bookmarks')
                results = [row[0] for row in cursor.fetchall()]
            return results if results else ['root']
        except sqlite3.Error as e:
            log(f"[ERROR] get_folders failed: {e}")
            return ['root']
    
    def delete_bookmark(self, bookmark_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM bookmarks WHERE id = ?', (bookmark_id,))
                conn.commit()
        except sqlite3.Error as e:
            log(f"[ERROR] delete_bookmark failed: {e}")


# =====================================================================
# ダウンロード管理
# =====================================================================

class DownloadManager:
    """ダウンロード管理クラス（永続化対応）"""
    
    def __init__(self):
        self.db_path = DOWNLOADS_DB
        self.downloads = []
        self.init_database()
    
    def init_database(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS downloads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        filename TEXT NOT NULL,
                        url TEXT NOT NULL,
                        download_path TEXT,
                        total_bytes INTEGER DEFAULT 0,
                        received_bytes INTEGER DEFAULT 0,
                        state INTEGER DEFAULT 0,
                        start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        finish_time TIMESTAMP
                    )
                ''')
                set_db_strollon_version(conn)
                conn.commit()
            log("[INFO] Downloads database initialized")
        except sqlite3.Error as e:
            log(f"[ERROR] Downloads database init failed: {e}")
    
    def add_download(self, download_item):
        """ダウンロードをメモリとDBに追加"""
        self.downloads.append(download_item)
        
        download_path = download_item.downloadDirectory()
        filename = download_item.downloadFileName()
        download_id = None
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO downloads (filename, url, download_path, total_bytes, received_bytes, state)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    filename,
                    download_item.url().toString(),
                    download_path,
                    download_item.totalBytes(),
                    download_item.receivedBytes(),
                    download_item.state().value
                ))
                download_id = cursor.lastrowid
                conn.commit()
            log(f"[INFO] Download added to DB with ID {download_id}: {filename}")
        except sqlite3.Error as e:
            log(f"[ERROR] add_download DB insert failed: {e}")
        
        if download_id is not None:
            download_item.receivedBytesChanged.connect(
                lambda: self.update_download_progress(download_id, download_item)
            )
            download_item.stateChanged.connect(
                lambda state: self.update_download_state(download_id, download_item, state)
            )
        
        log(f"[INFO] Download started: {filename}")
    
    def update_download_progress(self, download_id, download_item):
        """ダウンロード進捗をDBに更新"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE downloads 
                    SET received_bytes = ?, total_bytes = ?
                    WHERE id = ?
                ''', (download_item.receivedBytes(), download_item.totalBytes(), download_id))
                conn.commit()
        except sqlite3.Error as e:
            log(f"[ERROR] Failed to update download progress: {e}")
    
    def update_download_state(self, download_id, download_item, state):
        """ダウンロード状態をDBに更新"""
        try:
            state_value = state.value if hasattr(state, 'value') else int(state)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if state_value == 2:  # DownloadCompleted
                    cursor.execute('''
                        UPDATE downloads 
                        SET state = ?, received_bytes = ?, finish_time = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (state_value, download_item.receivedBytes(), download_id))
                    log(f"[INFO] Download completed: {download_id}")
                else:
                    cursor.execute('''
                        UPDATE downloads 
                        SET state = ?
                        WHERE id = ?
                    ''', (state_value, download_id))
                conn.commit()
        except sqlite3.Error as e:
            log(f"[ERROR] Failed to update download state: {e}")
    
    def get_downloads(self):
        """現在のダウンロードリストを取得"""
        return self.downloads
    
    def get_download_history(self, limit=100):
        """ダウンロード履歴をDBから取得"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, filename, url, download_path, total_bytes, received_bytes, state, start_time, finish_time
                    FROM downloads
                    ORDER BY start_time DESC
                    LIMIT ?
                ''', (limit,))
                return cursor.fetchall()
        except sqlite3.Error as e:
            log(f"[ERROR] get_download_history failed: {e}")
            return []

    def delete_download(self, download_id: int):
        """指定IDのダウンロード履歴を1件削除（進行中は削除しない）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'DELETE FROM downloads WHERE id = ? AND state NOT IN (0, 1)',
                    (download_id,)
                )
                conn.commit()
            log(f"[INFO] Download entry deleted: {download_id}")
        except sqlite3.Error as e:
            log(f"[ERROR] delete_download failed: {e}")

    def clear_download_history(self):
        """ダウンロード履歴をクリア（進行中・要求中は除外）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # state: 0=要求中, 1=進行中, 2=完了, 3=キャンセル, 4=中断
                # 進行中(0,1)は残し、終了済み(2,3,4)のみ削除
                cursor.execute('DELETE FROM downloads WHERE state NOT IN (0, 1)')
                deleted = cursor.rowcount
                conn.commit()
            log(f"[INFO] Download history cleared ({deleted} entries removed, in-progress preserved)")
        except sqlite3.Error as e:
            log(f"[ERROR] clear_download_history failed: {e}")


# =====================================================================
# セッション管理
# =====================================================================

class SessionManager:
    """セッション管理クラス（バージョンスタンプ対応）"""

    def __init__(self):
        self.session_file = SESSION_FILE

    def save_session(self, tabs_data):
        """
        セッションを保存する。
        tabs_data は {"tabs": [...], "active_index": N} の辞書形式。
        バージョンスタンプを付与して保存する。
        """
        try:
            stamped = stamp_version_to_json(tabs_data)
            with open(self.session_file, 'w', encoding='utf-8') as f:
                json.dump(stamped, f, ensure_ascii=False, indent=2)
            log(f"[INFO] Session saved: {len(tabs_data.get('tabs', []))} tabs")
        except Exception as e:
            log(f"[ERROR] Failed to save session: {e}")

    def load_session(self):
        """
        セッションを読み込む。
        戻り値:
          ("ok",   dict)           正常読み込み
          ("newer_version", str)   現在より新しいStrollonが書いたデータ（str=そのバージョン）
          ("empty", None)          ファイルなし or 空
        """
        if not self.session_file.exists():
            return ("empty", None)

        try:
            with open(self.session_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
        except Exception as e:
            log(f"[ERROR] Failed to load session: {e}")
            return ("empty", None)

        # --- バージョン新しすぎチェック ---
        if not check_version_stamp(raw, "session.json"):
            newer_ver = raw.get(VERSION_KEY, "不明")
            return ("newer_version", newer_ver)

        tabs_count = len(raw.get("tabs", []))
        log(f"[INFO] Session loaded: {tabs_count} tabs")
        return ("ok", raw)


# =====================================================================
# 広告ブロック管理
# =====================================================================

class AdBlockManager:
    """
    広告ブロックマネージャー。

    キャッシュ:
      - フィルタテキスト : DATA_DIR / "adblock_filters.dat"  (ダウンロード生テキスト)
      - シリアライズ済み : DATA_DIR / "adblock_engine.bin"   (高速ロード用)
    """

    FILTER_URLS = [
        "https://easylist.to/easylist/easylist.txt",
        "https://easylist.to/easylist/easyprivacy.txt",
        "https://raw.githubusercontent.com/k2jp/abp-japanese-filters/master/abpjf.txt",
    ]

    # QWebEngineUrlRequestInfo.ResourceType → adblock resource type 文字列
    #
    # 0.7.5.0 [1.0.0.0-rc3]: 以前の対応表は ResourceTypeFavicon(=12) が
    # 抜けていたため、Xhr 以降の値がすべて1つずつズレていた
    # （実際の Xhr=13 が誤って「ping」として判定される等）。
    # https://doc.qt.io/qt-6/qwebengineurlrequestinfo.html の
    # ResourceType 一覧に基づき正しい値へ修正。
    _RESOURCE_TYPE_MAP = {
        0:  "document",        # MainFrame
        1:  "subdocument",     # SubFrame
        2:  "stylesheet",      # Stylesheet
        3:  "script",          # Script
        4:  "image",           # Image
        5:  "font",            # FontResource
        6:  "other",           # SubResource
        7:  "object",          # Object
        8:  "media",           # Media
        9:  "other",           # Worker
        10: "other",           # SharedWorker
        11: "other",           # Prefetch
        12: "image",           # Favicon
        13: "xmlhttprequest",  # Xhr
        14: "ping",            # Ping
        15: "other",           # ServiceWorker
        16: "csp_report",      # CspReport
        17: "object",          # PluginResource
        19: "document",        # NavigationPreloadMainFrame
        20: "subdocument",     # NavigationPreloadSubFrame
        21: "other",           # Json
        254: "websocket",      # WebSocket
        255: "other",          # Unknown
    }

    def __init__(self):
        from constants import DATA_DIR, settings, log as _log
        self._log = _log
        self._settings = settings
        self._filter_path = DATA_DIR / "adblock_filters.dat"
        self._engine_path = DATA_DIR / "adblock_engine.bin"
        self._engine = None
        self._loaded = False
        self._rule_count = 0
        # ブロック実績カウンター（設定ファイルから復元し累積保存）
        self._block_count: int = self._settings.value("adblock_block_count", 0, type=int)
        # フィルター更新用バックグラウンドスレッドの追跡
        # （終了時にこのスレッドを待たずにプロセスを終了すると、Windowsで
        #   ヒープ破壊クラッシュの原因になり得るため）
        self._update_thread = None
        # 1.3.0.0: 直近のフィルター更新結果 (success: bool, message: str) | None。
        # 以前は update_filters() の callback に渡すだけで、Settings画面（
        # strollon://settings）側では一切使われておらず、ログファイル
        # （strollon.log。起動のたびに上書きされる）を見ない限り、更新が
        # 実際に失敗していても画面上は何も変化がなく「更新ボタンを押しても
        # 反応がない／ダウンロードできているのか分からない」ように見えて
        # いた。ここに保持しておき、Settings画面の再読み込み時に一度だけ
        # 消費して結果（成功/失敗とその理由）を画面に表示できるようにする。
        self._last_update_result = None
        self._load_engine()

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def is_enabled(self) -> bool:
        return self._settings.value("adblock_enabled", True, type=bool)

    # ホワイトリストの既定値（設定画面から追加/削除可能）
    _DEFAULT_ALLOWLIST: list = [
        "www.youtube.com/youtubei/",
        "googlevideo.com/videoplayback",
        "i.ytimg.com/generate_204",
    ]

    _DEFAULT_FILTER_URLS: list = [
        "https://easylist.to/easylist/easylist.txt",
        "https://easylist.to/easylist/easyprivacy.txt",
        "https://raw.githubusercontent.com/k2jp/abp-japanese-filters/master/abpjf.txt",
    ]

    def get_filter_urls(self) -> list:
        """フィルターURLリストを設定から読み込む。未設定なら既定値を返す。"""
        raw = self._settings.value("adblock_filter_urls", None)
        if raw is None:
            return list(self._DEFAULT_FILTER_URLS)
        try:
            import json as _json
            parsed = _json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if x]
        except Exception:
            pass
        return list(self._DEFAULT_FILTER_URLS)

    def save_filter_urls(self, urls: list) -> None:
        """フィルターURLリストを設定に保存する。"""
        import json as _json
        self._settings.setValue("adblock_filter_urls", _json.dumps(urls, ensure_ascii=False))
        self._settings.sync()
        self._log(f"[AdBlock] Filter URLs updated ({len(urls)} entries)")

    def get_allowlist(self) -> list:
        """設定からホワイトリストを読み込む。未設定なら既定値を返す。"""
        raw = self._settings.value("adblock_allowlist", None)
        if raw is None:
            return list(self._DEFAULT_ALLOWLIST)
        try:
            import json as _json
            parsed = _json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if x]
        except Exception:
            pass
        return list(self._DEFAULT_ALLOWLIST)

    def save_allowlist(self, entries: list) -> None:
        """ホワイトリストを設定に保存する。"""
        import json as _json
        self._settings.setValue("adblock_allowlist", _json.dumps(entries, ensure_ascii=False))
        self._settings.sync()
        self._log(f"[AdBlock] Allowlist updated ({len(entries)} entries)")

    def should_block(self, url: str, source_url: str = "", resource_type: int = 255) -> bool:
        """
        url をブロックすべきなら True を返す。

        Args:
            url:           チェックするリクエスト URL
            source_url:    リクエスト元ページの URL（省略時は空文字）
            resource_type: QWebEngineUrlRequestInfo.ResourceType の整数値
        """
        if not self.is_enabled() or not self._loaded or self._engine is None:
            return False

        if not (url.startswith("http://") or url.startswith("https://")
                or url.startswith("wss://") or url.startswith("ws://")):
            return False

        for entry in self.get_allowlist():
            if entry and entry in url:
                return False

        rtype = self._RESOURCE_TYPE_MAP.get(resource_type, "other")
        try:
            result = self._engine.check_network_urls(url, source_url or url, rtype)
            if result.matched:
                self._block_count += 1
                self._log(f"[AdBlock] BLOCK {url[:80]} (type={rtype})")
                if self._block_count % 10 == 0:
                    self._settings.setValue("adblock_block_count", self._block_count)
                    self._settings.sync()
            return result.matched
        except Exception as e:
            self._log(f"[AdBlock] check error: {e}")
            return False

    def rule_count(self) -> int:
        """エンジンにロードされた正味のルール数を返す。"""
        return self._rule_count

    def get_cosmetic_resources(self, url: str):
        """
        1.3.0.0: 指定URLに対するコスメティックフィルタ情報
        （adblock.UrlSpecificResources）を返す。無効時・未ロード時は None。

        これまで Strollon は check_network_urls() によるネットワークレベルの
        リクエストブロックのみを行っており、EasyList/EasyPrivacy が多く含む
        要素非表示ルール（##selector 等）を一切適用していなかった。
        そのため、広告用のiframe/スクリプト自体はブロックできていても、
        その「空になった枠」やアンチアドブロック検知用のダミー要素が
        非表示にならずに残り、サイト側の検知スクリプトに広告ブロッカーの
        存在を気付かれてしまうケースがあった。
        """
        if not self.is_enabled() or not self._loaded or self._engine is None:
            return None
        if not (url.startswith("http://") or url.startswith("https://")):
            return None
        try:
            return self._engine.url_cosmetic_resources(url)
        except Exception as e:
            self._log(f"[AdBlock] cosmetic resource lookup error: {e}")
            return None

    def get_generic_hide_selectors(self, classes, ids, exceptions):
        """
        1.3.0.0: ページ内に実在するクラス名・ID群（classes/ids）から、
        適用すべき汎用非表示セレクタ（ドメイン非依存の ##.foo のようなルール）
        のリストを返す。exceptions は get_cosmetic_resources() が返した
        UrlSpecificResources.exceptions をそのまま渡すこと。
        """
        if not self.is_enabled() or not self._loaded or self._engine is None:
            return []
        try:
            return list(self._engine.hidden_class_id_selectors(classes, ids, exceptions))
        except Exception as e:
            self._log(f"[AdBlock] generic selector lookup error: {e}")
            return []

    def block_count(self) -> int:
        """ブロックした実績の累計数を返す。"""
        return self._block_count

    def flush_block_count(self):
        """現在のカウントを設定ファイルに書き込む（アプリ終了時などに呼ぶ）。"""
        self._settings.setValue("adblock_block_count", self._block_count)
        self._settings.sync()

    def is_updating(self) -> bool:
        """フィルター更新スレッドが実行中かどうかを返す。"""
        return self._update_thread is not None and self._update_thread.is_alive()

    def pop_last_update_result(self):
        """
        1.3.0.0: 直近のフィルター更新結果を (success, message) のタプルで
        返し、内部状態はクリアする（一度取得したら消費される）。
        更新が一度も行われていない場合は None を返す。
        Settings画面のリロード直後に一度だけ結果を表示するために使う。
        """
        result = self._last_update_result
        self._last_update_result = None
        return result

    def update_filters(self, callback=None):
        """フィルターリストをバックグラウンドでダウンロード・再構築する。"""
        import threading
        if self.is_updating():
            self._log("[WARN] AdBlock: update already in progress, ignoring request")
            message = "フィルターの更新は既に実行中です。しばらく待ってから再度お試しください。"
            self._last_update_result = (False, message)
            if callback:
                callback(False, message)
            return
        # 0.7.5.0 [1.0.0.0-rc3]: 以前は daemon=True の生スレッドをどこにも
        # 保持していなかった。このスレッドはネットワークI/O（urlopen）や
        # adblock（Rust拡張）によるEngine構築・ファイルシリアライズという
        # ネイティブ処理を行うため、これが実行中にアプリを終了すると
        # Pythonインタプリタの終了処理とスレッドの動作が競合し、Windowsで
        # ヒープ破壊クラッシュ（終了時に code 0xc0000374 が出る不具合）の
        # 原因になっていた。
        # daemon=False にすることで、Pythonの標準の終了処理が必ずこの
        # スレッドの完了を待ってからインタプリタを終了するようになる上、
        # スレッドオブジェクト自体も self._update_thread に保持し、
        # closeEvent 側からも明示的に完了を待てるようにする。
        self._update_thread = threading.Thread(
            target=self._download_and_rebuild, args=(callback,), daemon=False
        )
        self._update_thread.start()

    # ------------------------------------------------------------------
    # 内部実装
    # ------------------------------------------------------------------

    def _load_engine(self):
        """起動時: シリアライズ済みエンジンがあれば高速ロード、なければテキストから構築。"""
        import adblock as _ab

        # シリアライズ済みバイナリが存在すれば超高速ロード
        if self._engine_path.exists():
            try:
                engine = _ab.Engine(_ab.FilterSet(debug=False), optimize=False)
                engine.deserialize_from_file(str(self._engine_path))
                self._engine = engine
                self._loaded = True
                # テキストファイルが残っていればルール数を復元
                if self._filter_path.exists():
                    try:
                        with open(self._filter_path, "r", encoding="utf-8", errors="ignore") as _f:
                            self._rule_count = sum(
                                1 for l in _f
                                if l.strip() and not l.startswith("!") and not l.startswith("[")
                                and "##" not in l and "#@#" not in l
                            )
                    except Exception:
                        pass
                self._log(f"[INFO] AdBlock: engine loaded from cache "
                          f"({self._rule_count:,} rules, {self._engine_path.stat().st_size:,} bytes)")
                return
            except Exception as e:
                self._log(f"[WARN] AdBlock: cache load failed ({e}), rebuilding from text...")
                # キャッシュが壊れていたら削除してテキストから再構築

        # テキストファイルから構築
        if self._filter_path.exists():
            self._build_engine_from_text()
        else:
            self._log("[INFO] AdBlock: no filter file. Use 'Update Filters' to download.")
            self._loaded = True

    def _build_engine_from_text(self):
        """
        adblock_filters.dat のテキストから Engine を構築してシリアライズ
        キャッシュを作る。

        戻り値: (success, error_message) のタプル。
        1.3.0.0: 以前はここで例外を捕捉してログに残すだけで、呼び出し元
        （_download_and_rebuild）には常に「成功」として伝わっていた。
        そのため、例えば adblock（Rust拡張）側の問題でEngine構築自体が
        失敗していても、Settings画面には「フィルターを更新しました」と
        表示され、実際には広告ブロックが機能していない、という状態に
        気付けなかった。戻り値で成否を伝えるようにする。
        """
        import adblock as _ab
        try:
            with open(self._filter_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()

            fs = _ab.FilterSet(debug=False)
            fs.add_filter_list(text, format="standard")
            engine = _ab.Engine(fs, optimize=True)

            # シリアライズキャッシュを保存（次回起動が速くなる）
            self._engine_path.parent.mkdir(parents=True, exist_ok=True)
            engine.serialize_to_file(str(self._engine_path))

            # フィルタテキストから有効ルール数をカウント（コメント・空行・CSSセレクタ除外）
            self._rule_count = sum(
                1 for l in text.splitlines()
                if l.strip() and not l.startswith("!") and not l.startswith("[")
                and "##" not in l and "#@#" not in l
            )
            self._engine = engine
            self._loaded = True
            self._log(f"[INFO] AdBlock: engine built ({self._rule_count:,} rules), "
                      f"cache saved ({self._engine_path.stat().st_size:,} bytes)")
            return True, None
        except Exception as e:
            self._log(f"[ERROR] AdBlock: engine build failed: {e}")
            self._loaded = True
            return False, str(e)

    def _download_and_rebuild(self, callback):
        """バックグラウンドスレッド: ダウンロード → テキスト保存 → Engine 再構築。"""
        from urllib.error import URLError
        import datetime

        all_lines = []
        errors = []

        for url in self.get_filter_urls():
            # フィルターURLは http/https のみ許可する（多層防御）。
            # 変更自体はアクショントークンで保護済みだが、file:// 等の
            # ローカル/内部スキームを urlopen() に渡してしまう経路を
            # そもそも塞いでおく。
            if not (url.startswith("http://") or url.startswith("https://")):
                errors.append(f"{url}: unsupported scheme (http/https only)")
                self._log(f"[WARN] AdBlock: rejected non-http(s) filter URL: {url}")
                continue
            try:
                self._log(f"[INFO] AdBlock: downloading {url}")
                text = _fetch_url(url, timeout=20, user_agent="Mozilla/5.0").decode("utf-8", errors="ignore")
                all_lines.extend(text.splitlines())
                self._log(f"[INFO] AdBlock: fetched {url} ({len(text.splitlines())} lines)")
            except URLError as e:
                errors.append(f"{url}: {e.reason}")
                self._log(f"[WARN] AdBlock: failed {url}: {e.reason}")
            except Exception as e:
                errors.append(str(e))
                self._log(f"[WARN] AdBlock: error {url}: {e}")

        if not all_lines and errors:
            message = "ダウンロードに失敗しました:\n" + "\n".join(errors)
            self._last_update_result = (False, message)
            if callback:
                callback(False, message)
            return

        # テキストを保存
        try:
            self._filter_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._filter_path, "w", encoding="utf-8") as f:
                f.write("\n".join(all_lines))
        except Exception as e:
            message = f"保存に失敗しました: {e}"
            self._last_update_result = (False, message)
            if callback:
                callback(False, message)
            return

        # 古いキャッシュを削除して再構築
        if self._engine_path.exists():
            try:
                self._engine_path.unlink()
            except Exception:
                pass

        build_ok, build_error = self._build_engine_from_text()

        self._settings.setValue("adblock_last_updated", datetime.datetime.now().isoformat())
        self._settings.sync()

        line_count = len(all_lines)
        if build_ok:
            msg = f"フィルターを更新しました（{line_count:,} 行）"
            if errors:
                msg += f"\n※一部取得失敗: {len(errors)} 件"
            success = True
        else:
            # ダウンロード自体は成功したが、Engineの構築（adblock拡張側の処理）に
            # 失敗したケース。これを「成功」として報告すると、広告ブロックが
            # 実際には機能していないことに気付けなくなるため失敗として扱う。
            msg = f"フィルターの取得はできましたが、エンジンの構築に失敗しました: {build_error}"
            success = False
        self._last_update_result = (success, msg)
        self._log(f"[INFO] AdBlock: {msg}")
        if callback:
            callback(success, msg)


# =====================================================================
# 更新チェック（スレッド）
# =====================================================================

class UpdateChecker(QThread):
    """更新チェックを行うスレッド"""
    update_available = Signal(str, str)

    def run(self):
        log("[INFO] UpdateCheck Start")
        try:
            _os = _platform.system()
            _ua = f"Strollon/{BROWSER_VERSION_SEMANTIC} ({_os};)"
            content = _fetch_url(UPDATE_CHECK_URL, timeout=10, user_agent=_ua).decode('utf-8').strip()
            log(f"[INFO] UpdateCheck Response: {repr(content[:80])}")
            self.parse_update_info(content)
            log("[INFO] UpdateCheck Close")
        except URLError as e:
            log(f"[INFO] UpdateCheck Failed (URLError): {e.reason}")
        except Exception as e:
            log(f"[INFO] UpdateCheck Failed ({type(e).__name__}): {e}")

    def parse_update_info(self, content):
        try:
            parts = content.split(',', 2)
            if len(parts) < 3:
                log(f"[INFO] UpdateCheck: invalid format (parts={len(parts)})")
                return
            if parts[0].strip() != "[Strollon]":
                log(f"[INFO] UpdateCheck: unexpected header '{parts[0].strip()}'")
                return

            latest_version = parts[1].strip()
            update_message = parts[2].strip()

            log(f"[INFO] UpdateCheck: latest={latest_version}, current={BROWSER_VERSION_SEMANTIC}")
            if version.parse(latest_version) > version.parse(BROWSER_VERSION_SEMANTIC):
                log("[INFO] UpdateCheck-> New Version Available")
                self.update_available.emit(latest_version, update_message)
            else:
                log("[INFO] UpdateCheck-> Latest")
        except Exception as e:
            log(f"[INFO] UpdateCheck parse failed ({type(e).__name__}): {e}")
