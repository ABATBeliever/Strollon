"""
Strollon Browser - データ管理クラス群
履歴、ブックマーク、ダウンロード、セッション管理、更新チェック
"""

import sqlite3
import json
import re
from urllib.request import urlopen
from urllib.error import URLError
from packaging import version
from html import escape, unescape

from PySide6.QtCore import QThread, Signal

from constants import (
    HISTORY_DB, BOOKMARKS_DB, SESSION_FILE, DOWNLOADS_DB,
    BROWSER_VERSION_SEMANTIC, BROWSER_FULL_NAME, UPDATE_CHECK_URL,
    set_db_strollon_version, check_db_version,
    stamp_version_to_json, check_version_stamp, VERSION_KEY, log
)


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
                    SELECT url, title, visit_time, visit_count 
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
                cursor.execute('''
                    SELECT url, title, visit_time, visit_count 
                    FROM history 
                    WHERE url LIKE ? OR title LIKE ?
                    ORDER BY visit_time DESC 
                    LIMIT ?
                ''', (f'%{query}%', f'%{query}%', limit))
                return cursor.fetchall()
        except sqlite3.Error as e:
            log(f"[ERROR] search_history failed: {e}")
            return []
    
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
    
    def export_html(self, filepath):
        """HTML形式でエクスポート（Netscape Bookmark File Format）"""
        bookmarks = self.get_bookmarks()
        folders = {}
        
        for bm_id, title, url, folder in bookmarks:
            if folder not in folders:
                folders[folder] = []
            folders[folder].append((title, url))
        
        html = [
            '<!DOCTYPE NETSCAPE-Bookmark-file-1>',
            '<!-- This is an automatically generated file.',
            '     It will be read and overwritten.',
            '     DO NOT EDIT! -->',
            '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
            f'<TITLE>Bookmarks - {BROWSER_FULL_NAME}</TITLE>',
            '<H1>Bookmarks</H1>',
            '<DL><p>'
        ]
        
        for folder, items in folders.items():
            if folder != 'root':
                html.append(f'    <DT><H3>{escape(folder)}</H3>')
                html.append('    <DL><p>')
            
            for title, url in items:
                html.append(f'        <DT><A HREF="{escape(url)}">{escape(title)}</A>')
            
            if folder != 'root':
                html.append('    </DL><p>')
        
        html.append('</DL><p>')
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(html))
        
        log(f"[INFO] Bookmarks exported to {filepath}")
    
    def import_html(self, filepath):
        """HTML形式でインポート"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            current_folder = 'root'
            h3_pattern = re.compile(r'<H3[^>]*>(.*?)</H3>', re.IGNORECASE)
            a_pattern = re.compile(r'<A\s+HREF="([^"]+)"[^>]*>(.*?)</A>', re.IGNORECASE)
            
            lines = content.split('\n')
            for line in lines:
                h3_match = h3_pattern.search(line)
                if h3_match:
                    current_folder = unescape(h3_match.group(1))
                    continue
                
                a_match = a_pattern.search(line)
                if a_match:
                    url = unescape(a_match.group(1))
                    title = unescape(a_match.group(2))
                    self.add_bookmark(title, url, current_folder)
            
            log(f"[INFO] Bookmarks imported from {filepath}")
            return True
        except Exception as e:
            log(f"[ERROR] Failed to import bookmarks: {e}")
            return False


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
                    SELECT filename, url, download_path, total_bytes, received_bytes, state, start_time, finish_time
                    FROM downloads
                    ORDER BY start_time DESC
                    LIMIT ?
                ''', (limit,))
                return cursor.fetchall()
        except sqlite3.Error as e:
            log(f"[ERROR] get_download_history failed: {e}")
            return []
    
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
    _RESOURCE_TYPE_MAP = {
        0:  "document",        # MainFrame
        1:  "subdocument",     # SubFrame
        2:  "stylesheet",      # Stylesheet
        3:  "script",          # Script
        4:  "image",           # Image
        5:  "font",            # Font
        6:  "other",           # SubResource
        7:  "object",          # Object
        8:  "media",           # Media
        9:  "other",           # Worker
        10: "other",           # SharedWorker
        11: "xmlhttprequest",  # Xhr
        13: "ping",            # Ping
        14: "other",           # ServiceWorker
        15: "csp_report",      # CspReport
        16: "object",          # PluginResource
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
        self._load_engine()

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def is_enabled(self) -> bool:
        return self._settings.value("adblock_enabled", True, type=bool)

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

        # strollon:// など内部スキームは絶対にブロックしない
        if not (url.startswith("http://") or url.startswith("https://")
                or url.startswith("wss://") or url.startswith("ws://")):
            return False

        rtype = self._RESOURCE_TYPE_MAP.get(resource_type, "other")
        try:
            result = self._engine.check_network_urls(url, source_url or url, rtype)
            if result.matched:
                self._block_count += 1
                self._log(f"[AdBlock] BLOCK {url[:80]} (type={rtype})")
                # 10件ごとに永続化（頻繁なディスク書き込みを避ける）
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

    def block_count(self) -> int:
        """ブロックした実績の累計数を返す。"""
        return self._block_count

    def flush_block_count(self):
        """現在のカウントを設定ファイルに書き込む（アプリ終了時などに呼ぶ）。"""
        self._settings.setValue("adblock_block_count", self._block_count)
        self._settings.sync()

    def update_filters(self, callback=None):
        """フィルターリストをバックグラウンドでダウンロード・再構築する。"""
        import threading
        t = threading.Thread(target=self._download_and_rebuild, args=(callback,), daemon=True)
        t.start()

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
        """adblock_filters.dat のテキストから Engine を構築してシリアライズキャッシュを作る。"""
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
        except Exception as e:
            self._log(f"[ERROR] AdBlock: engine build failed: {e}")
            self._loaded = True

    def _download_and_rebuild(self, callback):
        """バックグラウンドスレッド: ダウンロード → テキスト保存 → Engine 再構築。"""
        from urllib.request import urlopen, Request
        from urllib.error import URLError
        import datetime

        all_lines = []
        errors = []

        for url in self.FILTER_URLS:
            try:
                self._log(f"[INFO] AdBlock: downloading {url}")
                req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(req, timeout=20) as resp:
                    text = resp.read().decode("utf-8", errors="ignore")
                    all_lines.extend(text.splitlines())
                    self._log(f"[INFO] AdBlock: fetched {url} ({len(text.splitlines())} lines)")
            except URLError as e:
                errors.append(f"{url}: {e.reason}")
                self._log(f"[WARN] AdBlock: failed {url}: {e.reason}")
            except Exception as e:
                errors.append(str(e))
                self._log(f"[WARN] AdBlock: error {url}: {e}")

        if not all_lines and errors:
            if callback:
                callback(False, "ダウンロードに失敗しました:\n" + "\n".join(errors))
            return

        # テキストを保存
        try:
            self._filter_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._filter_path, "w", encoding="utf-8") as f:
                f.write("\n".join(all_lines))
        except Exception as e:
            if callback:
                callback(False, f"保存に失敗しました: {e}")
            return

        # 古いキャッシュを削除して再構築
        if self._engine_path.exists():
            try:
                self._engine_path.unlink()
            except Exception:
                pass

        self._build_engine_from_text()

        self._settings.setValue("adblock_last_updated", datetime.datetime.now().isoformat())
        self._settings.sync()

        line_count = len(all_lines)
        msg = f"フィルターを更新しました（{line_count:,} 行）"
        if errors:
            msg += f"\n※一部取得失敗: {len(errors)} 件"
        self._log(f"[INFO] AdBlock: {msg}")
        if callback:
            callback(True, msg)


# =====================================================================
# 更新チェック（スレッド）
# =====================================================================

class UpdateChecker(QThread):
    """更新チェックを行うスレッド"""
    update_available = Signal(str, str)

    def run(self):
        log("[INFO] UpdateCheck Start")
        try:
            with urlopen(UPDATE_CHECK_URL, timeout=10) as response:
                content = response.read().decode('utf-8').strip()
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
