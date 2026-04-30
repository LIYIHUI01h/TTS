import os
import asyncio
import aiofiles
from qasync import asyncSlot
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSplitter, QTextEdit, QVBoxLayout, QWidget
from UI.widgets import BasePage
from UI.common import logger


class FloatingLogMonitor(QWidget):
    def __init__(self, log_dir):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle('实时日志监控')
        self.resize(700, 450)
        self.log_dir = log_dir
        self.setStyleSheet('background-color: #16191d; color: #dcdcdc;')

        layout = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        self.file_selector = QComboBox()
        self.file_selector.setStyleSheet('''
            QComboBox { background: #1d2127; border: 1px solid #2c313c; padding: 5px; color: #87CEFA; }
        ''')
        self.refresh_files()
        top_bar.addWidget(QLabel('选择日志:'))
        top_bar.addWidget(self.file_selector)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        self.display = QTextEdit()
        self.display.setReadOnly(True)
        self.display.setStyleSheet('''
            QTextEdit {
                background-color: #050505; color: #abb2bf; 
                font-family: 'Consolas', 'Monaco'; font-size: 12px;
                border: 1px solid #2c313c;
            }
        ''')
        layout.addWidget(self.display)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_log_content)
        self.timer.start(1000)

    def refresh_files(self):
        if os.path.exists(self.log_dir):
            files = [f for f in os.listdir(self.log_dir) if f.endswith(('.log', '.txt'))]
            files.sort(reverse=True)
            self.file_selector.addItems(files)
            if 'speech.log' in files:
                self.file_selector.setCurrentText('speech.log')

    def update_log_content(self):
        filename = self.file_selector.currentText()
        if not filename:
            return
        full_path = os.path.join(self.log_dir, filename)
        if os.path.exists(full_path):
            try:
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    f.seek(max(0, size - 10000))
                    content = f.read()
                if self.display.toPlainText() != content:
                    v_bar = self.display.verticalScrollBar()
                    at_bottom = v_bar.value() >= v_bar.maximum() - 20
                    self.display.setPlainText(content)
                    if at_bottom:
                        self.display.moveCursor(QTextCursor.End)
            except Exception as e:
                logger.info(f'日志文件读取异常: {e}')


class LogPage(BasePage):
    def __init__(self, flags):
        super().__init__('SYSTEM LOGS', '支持多窗口对齐查看与实时跟踪')
        self.flags = flags
        self.layout.setContentsMargins(15, 10, 15, 0)
        self.log_dir = 'log'
        self.viewers = []
        self.floating_log_win = None

        sub_title_label = self.layout.itemAt(1).widget()
        self.sub_header_row = QHBoxLayout()
        self.sub_header_row.setContentsMargins(0, 0, 0, 0)
        self.sub_header_row.addWidget(sub_title_label)
        self.sub_header_row.addStretch()

        btn_style = '''
            QPushButton { 
                background: #343b48; border-radius: 4px; padding: 6px 15px; 
                color: white; font-size: 12px; font-weight: bold;
            } 
            QPushButton:hover { background: #4b5465; border: 1px solid #87CEFA; }
        '''

        self.float_log_btn = QPushButton('弹出监控 ↗')
        self.float_log_btn.setStyleSheet(btn_style.replace('#343b48', '#bd93f9'))
        self.add_view_btn = QPushButton('添加分屏 +')
        self.del_view_btn = QPushButton('移除分屏 -')
        self.add_view_btn.setStyleSheet(btn_style)
        self.del_view_btn.setStyleSheet(btn_style)

        self.sub_header_row.addWidget(self.float_log_btn)
        self.sub_header_row.addSpacing(20)
        self.sub_header_row.addWidget(self.add_view_btn)
        self.sub_header_row.addSpacing(10)
        self.sub_header_row.addWidget(self.del_view_btn)
        self.layout.insertLayout(1, self.sub_header_row)

        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(0)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setStyleSheet('QSplitter::handle { background: #3e4451; width: 1px; }')
        self.container_layout.addWidget(self.splitter)

        self.add_view_btn.clicked.connect(self.add_viewer)
        self.del_view_btn.clicked.connect(self.remove_viewer)
        self.float_log_btn.clicked.connect(self.open_floating_log)

        self.log_task = None
        self.add_viewer()

    def showEvent(self, event):
        super().showEvent(event)
        if self.log_task is None or self.log_task.done():
            self.log_task = asyncio.create_task(self.update_logs_loop())

    def hideEvent(self, event):
        super().hideEvent(event)
        if self.log_task:
            self.log_task.cancel()
            self.log_task = None

    def open_floating_log(self):
        if not self.floating_log_win:
            self.floating_log_win = FloatingLogMonitor(self.log_dir)
        self.floating_log_win.show()
        self.floating_log_win.raise_()
        self.floating_log_win.activateWindow()

    async def update_logs_loop(self):
        while True:
            try:
                await self.refresh_all_viewers()
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.info(f'日志更新出错: {e}')
                await asyncio.sleep(5)

    async def refresh_all_viewers(self):
        tasks = []
        for viewer in list(self.viewers):
            selector = viewer.findChild(QComboBox)
            display = viewer.findChild(QTextEdit)
            if selector and display:
                filename = selector.currentText()
                if filename and filename != '目录不存在':
                    tasks.append(self.load_log_async(filename, display))
        if tasks:
            await asyncio.gather(*tasks)

    @asyncSlot()
    async def load_log_async(self, filename, display_widget):
        full_path = os.path.join(self.log_dir, filename)
        if not os.path.exists(full_path):
            return
        try:
            async with aiofiles.open(full_path, mode='r', encoding='utf-8', errors='ignore') as f:
                await f.seek(0, os.SEEK_END)
                file_size = await f.tell()
                read_pos = max(0, file_size - 30000)
                await f.seek(read_pos)
                content = await f.read()
            if display_widget.toPlainText() != content:
                v_bar = display_widget.verticalScrollBar()
                at_bottom = v_bar.value() >= v_bar.maximum() - 50
                display_widget.setPlainText(content)
                if at_bottom:
                    display_widget.moveCursor(QTextCursor.End)
        except Exception as e:
            logger.info(f'文件读取出错({filename}): {e}')

    def add_viewer(self):
        if len(self.viewers) >= 3:
            return

        viewer_widget = QWidget()
        v_layout = QVBoxLayout(viewer_widget)
        v_layout.setContentsMargins(0, 5, 0, 0)

        file_selector = QComboBox()
        file_selector.setStyleSheet('''
            QComboBox { background: #1d2127; border: 1px solid #2c313c; padding: 5px; color: #87CEFA; }
            QComboBox QAbstractItemView { background: #1d2127; selection-background-color: #bd93f9; color: white; }
        ''')
        self.refresh_files(file_selector)

        display = QTextEdit()
        display.setReadOnly(True)
        display.setStyleSheet('''
            QTextEdit {
                background-color: #16191d; color: #abb2bf; font-family: 'Consolas', 'Monaco';
                border: 1px solid #2c313c; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;
            }
        ''')

        file_selector.currentTextChanged.connect(lambda text, d=display: asyncio.ensure_future(self.load_log_async(text, d)))
        v_layout.addWidget(file_selector)
        v_layout.addWidget(display)

        self.splitter.addWidget(viewer_widget)
        self.viewers.append(viewer_widget)

        index = file_selector.findText('speech.log')
        if index >= 0:
            file_selector.setCurrentIndex(index)
        if file_selector.currentText():
            asyncio.ensure_future(self.load_log_async(file_selector.currentText(), display))

    def remove_viewer(self):
        if len(self.viewers) > 1:
            viewer = self.viewers.pop()
            viewer.setParent(None)
            viewer.deleteLater()

    def refresh_files(self, combo_box):
        combo_box.clear()
        if os.path.exists(self.log_dir):
            files = [f for f in os.listdir(self.log_dir) if f.endswith(('.log', '.txt'))]
            files.sort(reverse=True)
            combo_box.addItems(files)
        else:
            combo_box.addItem('目录不存在')
