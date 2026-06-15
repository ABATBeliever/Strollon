"""
Strollon Browser - ダイアログ類
ブックマーク追加・ダウンロードマネージャー・ページ保存・ページ内検索
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer, Slot
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel, QFrame, QMessageBox, QRadioButton, QGroupBox, QComboBox,
    QFileDialog, QProgressBar, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFormLayout,
)
from PySide6.QtWebEngineCore import QWebEngineDownloadRequest, QWebEnginePage

from constants import (
    STYLES, BROWSER_NAME, log,
)


# =====================================================================
# 履歴・ダウンロード カードウィジェット
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
