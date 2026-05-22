"""
POC 在线同步弹窗 - 支持多仓库管理和一键同步
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QGroupBox, QProgressBar,
    QMessageBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialogButtonBox, QFormLayout
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

import os
import sys
import zipfile
import shutil
import urllib.request
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ui_scale import scaled, scaled_style
from core.settings_manager import get_settings
from i18n import tr


class RepoInputDialog(QDialog):
    """仓库信息输入对话框"""

    def __init__(self, parent=None, colors=None, name="", url="", title=""):
        super().__init__(parent)
        self.colors = colors if colors else {}
        self.setWindowTitle(title)
        self.resize(scaled(500), scaled(150))

        from core.fortress_style import get_dialog_stylesheet, get_button_style, get_secondary_button_style
        self.setStyleSheet(get_dialog_stylesheet(self.colors))

        layout = QVBoxLayout(self)
        layout.setSpacing(scaled(15))
        layout.setContentsMargins(scaled(20), scaled(20), scaled(20), scaled(20))

        form_layout = QFormLayout()

        self.name_input = QLineEdit()
        self.name_input.setText(name)
        self.name_input.setPlaceholderText(tr("poc.sync.repo_name_placeholder"))
        self.name_input.setMinimumWidth(scaled(300))
        form_layout.addRow(tr("poc.sync.repo_name") + ":", self.name_input)
        
        self.url_input = QLineEdit()
        self.url_input.setText(url)
        self.url_input.setPlaceholderText(tr("poc.sync.repo_url_placeholder"))
        self.url_input.setMinimumWidth(scaled(350))
        form_layout.addRow(tr("poc.sync.repo_url") + ":", self.url_input)

        layout.addLayout(form_layout)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_ok = btn_box.button(QDialogButtonBox.Ok)
        btn_ok.setStyleSheet(get_button_style('primary', self.colors))
        btn_ok.setText(tr("common.confirm"))

        btn_cancel = btn_box.button(QDialogButtonBox.Cancel)
        btn_cancel.setStyleSheet(get_secondary_button_style(self.colors))
        btn_cancel.setText(tr("common.cancel"))

        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_data(self):
        """获取输入的数据"""
        return self.name_input.text().strip(), self.url_input.text().strip()


class SyncThread(QThread):
    """同步后台线程"""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)  # 当前, 总数
    finished_signal = pyqtSignal(bool, str)  # 成功, 消息

    def __init__(self, target_dir: str, repo_url: str, repo_name: str):
        super().__init__()
        self.target_dir = target_dir
        self.repo_url = repo_url
        self.repo_name = repo_name
        self._is_running = True

    def run(self):
        try:
            self.log_signal.emit(f"[*] {tr('poc.sync.start_download')}")
            self.log_signal.emit(f"[*] {tr('poc.sync.repo_name')}: {self.repo_name}")
            self.log_signal.emit(tr("poc.sync.download_url", download_url=self.repo_url))

            # 创建临时目录
            temp_dir = tempfile.mkdtemp()
            zip_path = os.path.join(temp_dir, "templates.zip")

            # 下载 ZIP
            self.log_signal.emit(f"[*] {tr('poc.sync.downloading')}")

            def progress_hook(block_num, block_size, total_size):
                if total_size > 0:
                    downloaded = block_num * block_size
                    self.progress_signal.emit(downloaded, total_size)

            urllib.request.urlretrieve(self.repo_url, zip_path, progress_hook)

            self.log_signal.emit(f"[*] {tr('poc.sync.download_done_extracting')}")

            # 解压
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            # 找到解压后的目录
            extracted_dir = None
            for item in os.listdir(temp_dir):
                item_path = os.path.join(temp_dir, item)
                if os.path.isdir(item_path) and (item.startswith("nuclei-templates") or os.path.isdir(item_path)):
                    extracted_dir = item_path
                    break

            if not extracted_dir:
                # 如果没找到以 nuclei-templates 开头的目录，找第一个目录
                for item in os.listdir(temp_dir):
                    item_path = os.path.join(temp_dir, item)
                    if os.path.isdir(item_path):
                        extracted_dir = item_path
                        break

            if not extracted_dir:
                raise Exception(tr("poc.sync.template_dir_not_found"))

            self.log_signal.emit(f"[*] {tr('poc.sync.copying_files')}")

            # 统计复制的文件数
            copied_count = 0
            skipped_count = 0
            yaml_files = []

            # 收集所有 YAML 文件
            for root, dirs, files in os.walk(extracted_dir):
                for file in files:
                    if file.endswith(('.yaml', '.yml')):
                        yaml_files.append(os.path.join(root, file))

            total_files = len(yaml_files)
            self.log_signal.emit(f"[*] {tr('poc.sync.found_files', count=total_files)}")

            # 确保目标目录存在
            os.makedirs(self.target_dir, exist_ok=True)

            # 复制文件（去重）
            for i, src_path in enumerate(yaml_files):
                if not self._is_running:
                    break

                filename = os.path.basename(src_path)
                dst_path = os.path.join(self.target_dir, filename)

                # 检查文件是否已存在
                if os.path.exists(dst_path):
                    # 比较文件内容
                    with open(src_path, 'rb') as f_src:
                        src_content = f_src.read()
                    with open(dst_path, 'rb') as f_dst:
                        dst_content = f_dst.read()

                    if src_content == dst_content:
                        # 文件已存在且内容相同，跳过
                        skipped_count += 1
                        continue

                # 文件不存在或内容不同，复制
                shutil.copy2(src_path, dst_path)
                copied_count += 1

                if (i + 1) % 100 == 0:
                    self.log_signal.emit(f"[*] {tr('poc.sync.copied_progress', current=i + 1, total=total_files)}")
                    self.progress_signal.emit(i + 1, total_files)

            # 清理临时文件
            shutil.rmtree(temp_dir, ignore_errors=True)

            # 输出统计信息
            if skipped_count > 0:
                self.log_signal.emit(f"[*] {tr('poc.sync.skipped', count=skipped_count)}")
            self.log_signal.emit(f"\n[✓] {tr('poc.sync.complete', count=copied_count)}")

            message = tr("poc.sync.success", count=copied_count)
            if skipped_count > 0:
                message += tr("poc.sync.skipped_info", skipped=skipped_count)
            self.finished_signal.emit(True, message)

        except Exception as e:
            self.log_signal.emit(f"\n[!] {tr('poc.sync.failed', error=str(e))}")
            self.finished_signal.emit(False, str(e))

    def stop(self):
        self._is_running = False


class POCSyncDialog(QDialog):
    """
    POC 在线同步弹窗
    支持多仓库管理和一键同步
    """

    def __init__(self, target_dir: str, parent=None, colors=None):
        super().__init__(parent)
        self.target_dir = target_dir
        self.colors = colors if colors else {}
        self.sync_thread = None
        self.repos = []
        self.current_repo_index = 0
        self.sync_all_success = 0
        self.sync_all_failed = 0
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(tr("poc.sync.title"))
        self.resize(scaled(700), scaled(700))
        self.setMinimumSize(scaled(500), scaled(500))

        # 应用 FORTRESS 样式
        from core.fortress_style import get_dialog_stylesheet, get_button_style, get_secondary_button_style
        self.setStyleSheet(get_dialog_stylesheet(self.colors))

        layout = QVBoxLayout(self)
        layout.setSpacing(scaled(15))
        layout.setContentsMargins(scaled(20), scaled(20), scaled(20), scaled(20))

        # 仓库管理
        repo_group = QGroupBox(tr("poc.sync.repo_manager"))
        repo_layout = QVBoxLayout()

        # 仓库列表表格
        self.repo_table = QTableWidget()
        self.repo_table.setColumnCount(2)
        self.repo_table.setHorizontalHeaderLabels([tr("poc.sync.repo_name"), tr("poc.sync.repo_url")])
        self.repo_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.repo_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.repo_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.repo_table.setSelectionMode(QTableWidget.SingleSelection)
        self.repo_table.setMinimumHeight(scaled(200))
        repo_layout.addWidget(self.repo_table)

        # 仓库操作按钮
        repo_btn_layout = QHBoxLayout()

        self.btn_add_repo = QPushButton(tr("poc.sync.add_repo"))
        self.btn_add_repo.setStyleSheet(get_button_style('primary', self.colors))
        self.btn_add_repo.clicked.connect(self.add_repo)
        repo_btn_layout.addWidget(self.btn_add_repo)

        self.btn_edit_repo = QPushButton(tr("poc.sync.edit_repo"))
        self.btn_edit_repo.setStyleSheet(get_button_style('info', self.colors))
        self.btn_edit_repo.clicked.connect(self.edit_repo)
        repo_btn_layout.addWidget(self.btn_edit_repo)

        self.btn_delete_repo = QPushButton(tr("poc.sync.delete_repo"))
        self.btn_delete_repo.setStyleSheet(get_button_style('danger', self.colors))
        self.btn_delete_repo.clicked.connect(self.delete_repo)
        repo_btn_layout.addWidget(self.btn_delete_repo)

        repo_btn_layout.addStretch()
        repo_layout.addLayout(repo_btn_layout)

        repo_group.setLayout(repo_layout)
        layout.addWidget(repo_group)

        # 说明
        info_group = QGroupBox(tr("poc.sync.info_group"))
        info_layout = QVBoxLayout()
        info_layout.setSpacing(scaled(10))

        info_label = QLabel(tr("poc.sync.description"))
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)

        # 目标目录
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel(tr("poc.sync.save_dir")))
        self.dir_label = QLabel(self.target_dir)
        btn_primary = self.colors.get('btn_primary', '#2563eb')
        self.dir_label.setStyleSheet(scaled_style(f"color: {btn_primary};"))
        dir_layout.addWidget(self.dir_label)
        dir_layout.addStretch()
        info_layout.addLayout(dir_layout)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # 进度
        progress_group = QGroupBox(tr("poc.sync.progress_group"))
        progress_layout = QVBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", scaled(9)))
        self.log_text.setMaximumHeight(scaled(180))
        bg_color = self.colors.get('input_bg', '#1e1e1e')
        text_color = self.colors.get('text_secondary', '#dcdcdc')
        border_color = self.colors.get('nav_border', '#3e4451')

        self.log_text.setStyleSheet(scaled_style(f"""
            QTextEdit {{
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 6px;
                padding: 10px;
            }}
        """))
        progress_layout.addWidget(self.log_text)

        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)

        # 底部按钮
        btn_layout = QHBoxLayout()

        self.btn_sync_all = QPushButton(tr("poc.sync.sync_all"))
        self.btn_sync_all.setStyleSheet(get_button_style('success', self.colors))
        self.btn_sync_all.clicked.connect(self.sync_all_repos)
        btn_layout.addWidget(self.btn_sync_all)

        btn_layout.addStretch()

        btn_close = QPushButton(tr("common.close"))
        btn_close.setStyleSheet(get_secondary_button_style(self.colors))
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

        # 加载仓库列表
        self.load_repos()

    def load_repos(self):
        """加载仓库列表"""
        settings = get_settings()
        self.repos = settings.get_poc_repos()
        self.repo_table.setRowCount(0)

        for repo in self.repos:
            row = self.repo_table.rowCount()
            self.repo_table.insertRow(row)
            self.repo_table.setItem(row, 0, QTableWidgetItem(repo.get("name", "")))
            self.repo_table.setItem(row, 1, QTableWidgetItem(repo.get("url", "")))

    def add_repo(self):
        """添加仓库"""
        dialog = RepoInputDialog(self, self.colors, "", "", tr("poc.sync.add_repo"))
        if dialog.exec_() == QDialog.Accepted:
            name, url = dialog.get_data()
            if not name:
                QMessageBox.warning(self, tr("msg.warning"), tr("poc.sync.repo_name_required"))
                return
            if not url:
                QMessageBox.warning(self, tr("msg.warning"), tr("poc.sync.repo_url_required"))
                return

            self.repos.append({"name": name, "url": url})
            self.save_repos()
            self.load_repos()

    def edit_repo(self):
        """编辑仓库"""
        selected_row = self.repo_table.currentRow()
        if selected_row < 0 or selected_row >= len(self.repos):
            return

        repo = self.repos[selected_row]
        dialog = RepoInputDialog(self, self.colors, repo.get("name", ""), repo.get("url", ""), tr("poc.sync.edit_repo"))
        if dialog.exec_() == QDialog.Accepted:
            name, url = dialog.get_data()
            if not name:
                QMessageBox.warning(self, tr("msg.warning"), tr("poc.sync.repo_name_required"))
                return
            if not url:
                QMessageBox.warning(self, tr("msg.warning"), tr("poc.sync.repo_url_required"))
                return

            self.repos[selected_row] = {"name": name, "url": url}
            self.save_repos()
            self.load_repos()

    def delete_repo(self):
        """删除仓库"""
        selected_row = self.repo_table.currentRow()
        if selected_row < 0 or selected_row >= len(self.repos):
            return

        repo = self.repos[selected_row]
        reply = QMessageBox.question(
            self, tr("msg.confirm"),
            tr("poc.sync.confirm_delete_repo", name=repo.get("name", "")),
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            del self.repos[selected_row]
            self.save_repos()
            self.load_repos()

    def save_repos(self):
        """保存仓库列表"""
        settings = get_settings()
        settings.save_poc_repos(self.repos)

    def sync_all_repos(self):
        """一键同步所有仓库"""
        if not self.repos:
            QMessageBox.warning(self, tr("msg.warning"), tr("poc.sync.repo_url_required"))
            return

        reply = QMessageBox.question(
            self, tr("poc.sync.confirm_title"),
            tr("poc.sync.confirm_body", target_dir=self.target_dir),
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        self.btn_sync_all.setEnabled(False)
        self.btn_add_repo.setEnabled(False)
        self.btn_edit_repo.setEnabled(False)
        self.btn_delete_repo.setEnabled(False)
        self.log_text.clear()

        self.sync_all_success = 0
        self.sync_all_failed = 0
        self.current_repo_index = 0

        self.sync_next_repo()

    def sync_next_repo(self):
        """同步下一个仓库"""
        if self.current_repo_index >= len(self.repos):
            # 所有仓库同步完成
            self.on_sync_all_finished()
            return

        repo = self.repos[self.current_repo_index]
        self.log_text.append(f"\n{'='*50}")
        self.log_text.append(f"[{self.current_repo_index + 1}/{len(self.repos)}] {repo.get('name')}")
        self.log_text.append('='*50)

        self.sync_thread = SyncThread(self.target_dir, repo.get("url"), repo.get("name"))
        self.sync_thread.log_signal.connect(self.append_log)
        self.sync_thread.progress_signal.connect(self.update_progress)
        self.sync_thread.finished_signal.connect(self.on_single_repo_finished)
        self.sync_thread.start()

    def on_single_repo_finished(self, success, message):
        """单个仓库同步完成"""
        if success:
            self.sync_all_success += 1
        else:
            self.sync_all_failed += 1

        self.current_repo_index += 1
        self.sync_next_repo()

    def on_sync_all_finished(self):
        """所有仓库同步完成"""
        self.btn_sync_all.setEnabled(True)
        self.btn_add_repo.setEnabled(True)
        self.btn_edit_repo.setEnabled(True)
        self.btn_delete_repo.setEnabled(True)

        self.log_text.append(f"\n{'='*50}")
        self.log_text.append(tr("poc.sync.sync_all_success"))
        self.log_text.append(f"成功: {self.sync_all_success}")
        if self.sync_all_failed > 0:
            self.log_text.append(f"失败: {self.sync_all_failed}")
        self.log_text.append('='*50)

        if self.sync_all_failed > 0:
            QMessageBox.warning(self, tr("msg.failed"), tr("poc.sync.sync_all_failed"))
        else:
            QMessageBox.information(self, tr("msg.success"), tr("poc.sync.sync_all_success"))

    def append_log(self, text):
        """追加日志"""
        self.log_text.append(text)

    def update_progress(self, current, total):
        """更新进度条"""
        if total > 0:
            percent = int(current * 100 / total)
            self.progress_bar.setValue(percent)
