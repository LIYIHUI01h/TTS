import os
import base64
import socket
import asyncio
from PySide6.QtCore import QBuffer, QIODevice, QPoint, QProcess, QUrl, Qt, QEvent, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap, QCursor
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSlider, QSplitter, QStackedLayout, QTextEdit, QWidget, QFrame, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from qasync import asyncSlot
from live2d.live2d_UI import CustomPage
from UI.widgets import ToastNotification
from UI.common import logger


class MultimodalEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)

        self.image_data_list = []
        self.preview_layout = None
        self.preview_container = None

        self.setStyleSheet('''
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3e4451;
                border-radius: 8px;
                padding: 10px;
                font-family: 'Segoe UI', 'Microsoft YaHei UI', 'PingFang SC', sans-serif;
                font-size: 14px;
            }
            QScrollBar:vertical {
                width: 8px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #3e4451;
                border-radius: 4px;
            }
        ''')
        self.setPlaceholderText('在此输入文字...')

    def insertFromMimeData(self, source):
        if source.hasImage():
            image = QImage(source.imageData())
            if not image.isNull():
                self._process_qimage(image, 'Clipboard_Image')
                return
        super().insertFromMimeData(source)

    def insert_image(self, file_path):
        image = QImage(file_path)
        if image.isNull():
            return
        self._process_qimage(image, file_path)

    def _process_qimage(self, image, label_path):
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, 'JPG', 85)
        img_base64 = base64.b64encode(buffer.data().data()).decode()
        buffer.close()

        self.image_data_list.append(img_base64)
        self.add_preview_card(image, img_base64)
        if self.preview_container:
            self.preview_container.show()

    def add_preview_card(self, qimage_obj, data_ptr):
        card = QFrame()
        card.setFixedSize(70, 70)
        card.setStyleSheet('''
            QFrame { 
                background: #2c313c; border-radius: 6px; 
                border: 1px solid #3e4451; 
            }
        ''')

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(2, 2, 2, 2)

        lbl = QLabel()
        pix = QPixmap.fromImage(qimage_obj).scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        lbl.setPixmap(pix)
        lbl.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(lbl)

        del_btn = QPushButton('×', card)
        del_btn.setFixedSize(16, 16)
        del_btn.move(52, 2)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet('''
            QPushButton { 
                background: rgba(255, 85, 85, 0.8); color: white; 
                border-radius: 8px; font-size: 10px; font-weight: bold; border: none;
            }
            QPushButton:hover { background: #ff5555; }
        ''')

        def remove_card():
            if data_ptr in self.image_data_list:
                self.image_data_list.remove(data_ptr)
            card.deleteLater()
            QTimer.singleShot(10, self._check_preview_empty)

        del_btn.clicked.connect(remove_card)
        if self.preview_layout:
            self.preview_layout.insertWidget(self.preview_layout.count() - 1, card)

    def _check_preview_empty(self):
        if not self.image_data_list and self.preview_container:
            self.preview_container.hide()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            found_image = False
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    self.insert_image(path)
                    found_image = True
            if found_image:
                event.setDropAction(Qt.CopyAction)
                event.accept()
                return
        super().dropEvent(event)

    def clear_all(self):
        self.clear()
        self.image_data_list = []
        if self.preview_container:
            self.preview_container.hide()
        if self.preview_layout:
            while self.preview_layout.count() > 1:
                item = self.preview_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.setParent(None)
                    widget.deleteLater()


class HoverButton(QPushButton):
    hovered = Signal(bool)

    def enterEvent(self, event):
        super().enterEvent(event)
        self.hovered.emit(True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.hovered.emit(False)


class ChatPage(QWidget):
    def __init__(self, flags):
        super().__init__()
        self.flags = flags
        self.is_voice_mode = False
        self.interpt = asyncio.Event()
        self.forbid_change = asyncio.Event()
        self.wait_for_get = asyncio.Event()
        self.asr_prepare = asyncio.Event()
        self.text = ''
        self.VL_models = ['Qwen2-VL-72B']

        self.main_stack = QStackedLayout(self)
        self.setStyleSheet('background-color: #1a1d22;')

        self.chat_input = MultimodalEdit()
        self.chat_input.installEventFilter(self)

        self.preview_scroll = QScrollArea()
        self.preview_scroll.setFixedHeight(90)
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preview_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preview_scroll.setStyleSheet('background: #16191d; border: none; border-bottom: 1px solid #2c313c;')
        self.preview_scroll.hide()

        self.preview_content = QFrame()
        self.preview_layout = QHBoxLayout(self.preview_content)
        self.preview_layout.setContentsMargins(10, 10, 10, 10)
        self.preview_layout.setSpacing(10)
        self.preview_layout.addStretch()
        self.preview_scroll.setWidget(self.preview_content)

        self.chat_input.preview_layout = self.preview_layout
        self.chat_input.preview_container = self.preview_scroll

        self.toggle_ex_btn = HoverButton('＋')
        self.toggle_ex_btn.setFixedSize(36, 36)
        self.update_ex_btn_style()
        self.toggle_ex_btn.hovered.connect(self.on_btn_hovered)
        self.toggle_ex_btn.clicked.connect(self.on_ex_btn_clicked)

        self.live2d_view = QWebEngineView()
        self.live2d_view.page().setBackgroundColor(Qt.transparent)
        self.live2d_page = CustomPage(self.live2d_view)
        self.live2d_view.setPage(self.live2d_page)
        self.live2d_view.setUrl(QUrl('http://localhost:5173'))
        self.live2d_view.setStyleSheet('background: transparent;')

        self.setup_page1()
        self.setup_page2()
        self.init_history_view()
        self.init_floating_panel()
        self.pattern = None
        self.server_started = False

    def init_history_view(self):
        self.history_widget = QWidget()
        self.history_widget.setStyleSheet('background: transparent;')

        self.history_layout = QVBoxLayout(self.history_widget)
        self.history_layout.setContentsMargins(15, 15, 15, 15)
        self.history_layout.setSpacing(15)
        self.history_layout.addStretch()

        self.history_area.setWidget(self.history_widget)
        self.history_area.setWidgetResizable(True)

    def setup_page1(self):
        self.page1 = QWidget()
        layout = QVBoxLayout(self.page1)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.v_splitter = QSplitter(Qt.Vertical)
        self.v_splitter.setHandleWidth(1)
        self.v_splitter.setStyleSheet('QSplitter::handle { background: #2c313c; }')

        self.unity_area = QFrame()
        self.unity_area.setStyleSheet('background: transparent; border: none;')
        self.u_layout = QVBoxLayout(self.unity_area)
        self.u_layout.setContentsMargins(0, 0, 0, 0)
        self.u_layout.addWidget(self.live2d_view)

        self.input_container = QFrame()
        self.input_container.setStyleSheet('background-color: #1d2127; border-top: 1px solid #2c313c;')
        self.v_input_layout = QVBoxLayout(self.input_container)
        self.v_input_layout.setContentsMargins(0, 0, 0, 0)
        self.v_input_layout.addWidget(self.preview_scroll)

        self.input_row = QFrame()
        self.h_layout = QHBoxLayout(self.input_row)
        self.h_layout.setContentsMargins(10, 8, 10, 8)
        self.h_layout.addWidget(self.chat_input)
        self.h_layout.addWidget(self.toggle_ex_btn)

        self.v_input_layout.addWidget(self.input_row)
        self.v_splitter.addWidget(self.unity_area)
        self.v_splitter.addWidget(self.input_container)
        layout.addWidget(self.v_splitter)
        self.main_stack.addWidget(self.page1)

    def setup_page2(self):
        self.page2 = QWidget()
        lay = QHBoxLayout(self.page2)
        lay.setContentsMargins(0, 0, 0, 0)

        self.h_splitter = QSplitter(Qt.Horizontal)
        self.h_splitter.setStyleSheet('QSplitter::handle { background: #2c313c; }')

        self.p2_left_area = QFrame()
        self.p2_left_area.setStyleSheet('background: transparent; border: none;')
        self.p2_u_layout = QVBoxLayout(self.p2_left_area)
        self.p2_u_layout.setContentsMargins(0, 0, 0, 0)

        right_panel = QFrame()
        right_panel.setStyleSheet('background: #1d2127; border-left: 1px solid #2c313c;')
        rv = QVBoxLayout(right_panel)
        rv.setContentsMargins(0, 0, 0, 0)
        self.right_v_splitter = QSplitter(Qt.Vertical)
        self.right_v_splitter.setHandleWidth(1)
        self.right_v_splitter.setStyleSheet('QSplitter::handle { background: #2c313c; }')

        self.history_area = QScrollArea()
        self.history_area.setStyleSheet('background: transparent; border: none;')

        self.p2_input_box = QFrame()
        self.p2_input_box.setMinimumHeight(85)
        self.p2_v_lay = QVBoxLayout(self.p2_input_box)
        self.p2_v_lay.setContentsMargins(0, 0, 0, 0)

        self.p2_h_row = QHBoxLayout()
        self.p2_h_row.setContentsMargins(10, 5, 10, 10)
        self.p2_h_row.setSpacing(10)
        self.p2_v_lay.addLayout(self.p2_h_row)

        self.right_v_splitter.addWidget(self.history_area)
        self.right_v_splitter.addWidget(self.p2_input_box)
        self.right_v_splitter.setStretchFactor(0, 1)
        self.right_v_splitter.setStretchFactor(1, 0)
        self.right_v_splitter.setSizes([10000, 85])

        rv.addWidget(self.right_v_splitter)
        self.h_splitter.addWidget(self.p2_left_area)
        self.h_splitter.addWidget(right_panel)
        lay.addWidget(self.h_splitter)
        self.main_stack.addWidget(self.page2)

    def add_chat_item(self, content, is_user=True, is_forced_image=False):
        if not hasattr(self, 'history_layout') or self.history_layout is None:
            self.init_history_view()

        bubble_row = QWidget()
        bubble_row.setStyleSheet('background: transparent;')

        row_layout = QHBoxLayout(bubble_row)
        row_layout.setContentsMargins(10, 5, 10, 5)
        row_layout.setSpacing(0)

        area_w = self.history_area.width()
        limit_width = int((area_w if area_w > 100 else 500) * 0.7)

        display_widget = None
        pixmap = QPixmap()
        is_image_success = False

        if is_forced_image:
            try:
                b64_data = content.split(',')[1] if ',' in content else content
                img_bytes = base64.b64decode(b64_data)
                if pixmap.loadFromData(img_bytes):
                    is_image_success = True
            except Exception as e:
                logger.info(f'图片解码失败: {e}')

        if not is_image_success:
            if isinstance(content, (QPixmap, QImage)):
                pixmap = QPixmap(content) if isinstance(content, QImage) else content
                is_image_success = not pixmap.isNull()
            elif isinstance(content, str) and len(content) < 512:
                if content.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')) and os.path.exists(content):
                    pixmap = QPixmap(content)
                    is_image_success = not pixmap.isNull()

        if is_image_success:
            display_widget = QLabel()
            scaled_pix = pixmap.scaled(limit_width, 10000, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            display_widget.setPixmap(scaled_pix)
            display_widget.setStyleSheet('border-radius: 8px; border: 1px solid #2c313c;')
        else:
            text_content = str(content)
            if len(text_content) > 5000:
                text_content = text_content[:5000] + '\n\n[内容过长已截断...]'

            display_widget = QLabel(text_content)
            display_widget.setWordWrap(True)
            display_widget.setMaximumWidth(limit_width)
            display_widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)

            bg_color = '#2b5278' if is_user else '#2c313c'
            text_color = '#ffffff' if is_user else '#dcdfe4'
            radius = '12px 2px 12px 12px' if is_user else '2px 12px 12px 12px'
            display_widget.setStyleSheet(f'''
                QLabel {{
                    background-color: {bg_color}; 
                    color: {text_color}; 
                    border-radius: {radius}; 
                    padding: 10px 15px; 
                    font-size: 14px;
                    line-height: 1.4;
                }}
            ''')

        if is_user:
            row_layout.addStretch(1)
            row_layout.addWidget(display_widget, 0)
        else:
            row_layout.addWidget(display_widget, 0)
            row_layout.addStretch(1)

        count = self.history_layout.count()
        index = max(0, count - 1)
        self.history_layout.insertWidget(index, bubble_row)

        bubble_row.show()
        display_widget.adjustSize()
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        bar = self.history_area.verticalScrollBar()
        bar.setValue(bar.maximum())

    def init_floating_panel(self):
        self.floating_panel = QFrame(self)
        self.floating_panel.setFixedSize(180, 50)
        self.floating_panel.setStyleSheet('''
            QFrame { background: #2c313c; border: 1px solid #4e5565; border-radius: 10px; }
        ''')

        fl = QHBoxLayout(self.floating_panel)
        fl.setContentsMargins(10, 5, 10, 5)
        fl.setSpacing(8)

        self.btn_mode = QPushButton('🎤', self.floating_panel)
        self.btn_file = QPushButton('📁', self.floating_panel)
        self.btn_sw = QPushButton('⇌', self.floating_panel)
        self.btn_refresh = QPushButton('🔄', self.floating_panel)

        self.btn_mode.clicked.connect(self.toggle_mode)
        self.btn_file.clicked.connect(self.upload_image_dialog)
        self.btn_sw.clicked.connect(self.toggle_layout)
        self.btn_refresh.clicked.connect(self.start_live2d_render)

        for b in [self.btn_file, self.btn_mode, self.btn_sw, self.btn_refresh]:
            b.setFixedSize(32, 32)
            b.setStyleSheet('background: #3e4451; color: white; border-radius: 6px; border: none;')
            fl.addWidget(b)

        self.floating_panel.hide()
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.floating_panel.hide)

        def on_enter(event):
            self.hide_timer.stop()

        def on_leave(event):
            self.hide_timer.start(300)

        self.floating_panel.enterEvent = on_enter
        self.floating_panel.leaveEvent = on_leave

    def show_panel_at_right(self, target_right_x, y_pos):
        panel_width = 180
        new_x = target_right_x - panel_width
        self.floating_panel.setFixedSize(panel_width, 50)
        self.floating_panel.move(new_x, y_pos)
        self.floating_panel.show()
        self.floating_panel.raise_()

    def update_ui_state(self):
        if self.is_voice_mode and not self.asr_prepare.is_set():
            return
        icon = '⌨️' if self.is_voice_mode else '🎤'
        self.btn_mode.setText(icon)
        self.btn_mode.setStyleSheet('background: #3e4451; color: white; border-radius: 6px; border: none;')

    def update_ex_btn_style(self):
        if self.forbid_change.is_set():
            self.toggle_ex_btn.setText('⏹️')
            self.toggle_ex_btn.setStyleSheet('background: #ff5555; color: white; border-radius: 18px; border: 1px solid #ff8888; font-size: 14px;')
        else:
            self.toggle_ex_btn.setText('＋')
            self.toggle_ex_btn.setStyleSheet('QPushButton { background: #3e4451; color: white; border-radius: 18px; border: 1px solid #565f73; font-size: 20px; } QPushButton:hover { background: #4e5565; border-color: #87CEFA; }')

    def on_ex_btn_clicked(self):
        if self.forbid_change.is_set():
            self.interpt.set()
            self.notify('操作已中止', 'warn')
            return

    def toggle_layout(self):
        curr = self.main_stack.currentIndex()
        new_idx = 1 if curr == 0 else 0
        offset_y = 120
        if new_idx == 1:
            self.p2_u_layout.addWidget(self.live2d_view)
            self.p2_v_lay.insertWidget(0, self.preview_scroll)
            self.p2_h_row.addWidget(self.chat_input)
            self.p2_h_row.addWidget(self.toggle_ex_btn)
            self.live2d_view.page().runJavaScript(f'window.resizeModel({offset_y});')
        else:
            self.u_layout.addWidget(self.live2d_view)
            self.v_input_layout.insertWidget(0, self.preview_scroll)
            self.h_layout.addWidget(self.chat_input)
            self.h_layout.addWidget(self.toggle_ex_btn)
            self.live2d_view.page().runJavaScript(f'window.resizeModel({0});')
        self.main_stack.setCurrentIndex(new_idx)
        self.floating_panel.hide()
        if new_idx == 1:
            QTimer.singleShot(20, lambda: self.h_splitter.setSizes([int(self.width() * 0.75), int(self.width() * 0.25)]))
        else:
            QTimer.singleShot(20, lambda: self.v_splitter.setSizes([self.height() - 120, 120]))

    def is_port_open(self, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0

    @asyncSlot()
    async def start_live2d_render(self):
        if not self.is_port_open(5173):
            logger.info('🌐 检测到服务器未启动，正在启动...')
            if not hasattr(self, 'web_server_process') or self.web_server_process is None:
                self.web_server_process = QProcess(self)
                self.web_server_process.setWorkingDirectory('live2d')
                self.web_server_process.start('cmd', ['/c', 'npm run dev'])
            self.server_started = True
        else:
            self.server_started = True

        try:
            self.live2d_view.loadFinished.disconnect()
        except Exception:
            pass
        self.live2d_view.loadFinished.connect(self._on_live2d_load_done)
        self._final_render_init()
        logger.info('🚀 正在载入 Live2D 页面...')
        self.live2d_view.setUrl(QUrl('http://localhost:5173'))

    def _on_live2d_load_done(self, success):
        if success:
            logger.info('✅ 网页框架载入完成，等待组件初始化...')
            QTimer.singleShot(1000, self._final_render_init)
        else:
            logger.error('❌ 网页加载失败，请检查前端服务是否运行在 5173 端口')
            self._final_render_init()

    def _final_render_init(self):
        logger.info('🎨 开始初始化模型和背景渲染...')
        self.set_live2d_model(self.flags.model_path, self.flags.mouthparam)
        bg_relative_path = os.path.join('background', self.flags.live2d_bg).replace('\\', '/')
        self.set_live2d_background(bg_relative_path)

    def send_message(self):
        if self.is_voice_mode or self.forbid_change.is_set() or self.wait_for_get.is_set():
            return

        content = self.chat_input.toPlainText().strip()
        images = list(self.chat_input.image_data_list)
        if content or images:
            for img_b64 in images:
                self.add_chat_item(img_b64, is_user=True, is_forced_image=True)
            if content:
                self.add_chat_item(content, is_user=True)
            try:
                self.text = content
                self.current_images = images
                self.chat_input.clear_all()
                self.chat_input.setFocus()
                self.wait_for_get.set()
                self.chat_input.clear()
                self.chat_input.setFocus()
            except Exception as e:
                logger.exception(e)

    @asyncSlot()
    async def toggle_mode(self):
        if self.forbid_change.is_set():
            self.interpt.set()
        self.is_voice_mode = not self.is_voice_mode
        if not self.asr_prepare.is_set():
            await self.asr_prepare.wait()
        self.update_ui_state()
        if self.is_voice_mode:
            self.chat_input.setReadOnly(True)
            self.chat_input.setPlainText('语音识别模式: 准备就绪，请说话...')
            self.chat_input.setStyleSheet(self.chat_input.styleSheet().replace('color: white;', 'color: #87CEFA;'))
        else:
            self.interpt.set()
            self.chat_input.setReadOnly(False)
            self.chat_input.clear()
            self.chat_input.setStyleSheet(self.chat_input.styleSheet().replace('color: #87CEFA;', 'color: white;'))

    def eventFilter(self, obj, event):
        if obj is self.chat_input and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ControlModifier:
                    self.chat_input.insertPlainText('\n')
                    return True
                if not self.forbid_change.is_set() and not self.wait_for_get.is_set():
                    self.send_message()
                    return True
                return True
        return super().eventFilter(obj, event)

    def on_btn_hovered(self, is_hover):
        if self.forbid_change.is_set():
            self.floating_panel.hide()
            return
        if is_hover:
            self.hide_timer.stop()
            if self.floating_panel.isVisible():
                return
            self.update_ex_btn_style()
            btn_pos = self.toggle_ex_btn.mapTo(self, QPoint(0, 0))
            target_right = btn_pos.x() + self.toggle_ex_btn.width()
            target_y = btn_pos.y() - 55
            self.show_panel_at_right(target_right, target_y)
        else:
            self.hide_timer.start(300)

    def upload_image_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择图片', '', 'Images (*.png *.jpg *.jpeg *.bmp *.gif)')
        if path:
            self.chat_input.insert_image(path)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(50, lambda: self.v_splitter.setSizes([self.height() - 100, 100]))

    def set_live2d_model(self, model_path, mouth_param):
        js_code = f"window.loadModel('{model_path}', '{mouth_param}')"
        self.live2d_view.page().runJavaScript(js_code)
        if self.flags.name == '浅宜':
            self.live2d_view.page().runJavaScript("model.internalModel.coreModel.setParameterValueById('Param123', 1.0);")
        logger.info(f'尝试加载模型路径 -> {model_path}')

    def set_live2d_background(self, bg_path):
        js_code = f"if(window.loadBackground) {{ window.loadBackground('{bg_path}'); }} else {{ console.error('loadBackground not found'); }}"
        self.live2d_view.page().runJavaScript(js_code)
        logger.info(f'尝试切换背景 -> {bg_path}')

    def notify(self, message, level='info'):
        colors = {'info': '#87CEFA', 'warn': '#ffb86c', 'error': '#ff5555'}
        ToastNotification(self, message, colors.get(level, '#87CEFA'))
