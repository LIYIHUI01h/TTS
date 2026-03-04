import os
import random
import sys
import pynvml
import asyncio
import datetime
import psutil
import aiofiles
from PySide6.QtCore import QEvent, QEasingCurve, QPointF, Qt, QPropertyAnimation, QPoint, QRect, QSize, QVariantAnimation
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QComboBox, QMainWindow, QProgressBar, QSizeGrip, QPushButton, QSlider, QSplitter, QTextEdit, QWidget
from qasync import QEventLoop, asyncSlot
from main_ui import QFrame, QHBoxLayout, QLabel, QVBoxLayout, Ui_MainWindow 

class ToastNotification(QWidget):
    def __init__(self, parent, message, color="#87CEFA"):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.ToolTip)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 布局
        layout = QHBoxLayout(self)
        self.label = QLabel(message)
        self.label.setStyleSheet(f"""
            QLabel {{
                background-color: #1d2127; 
                color: {color}; 
                border: 1px solid {color};
                border-radius: 5px;
                padding: 10px 20px;
                font-family: 'Segoe UI';
                font-size: 13px;
            }}
        """)
        layout.addWidget(self.label)
        
        # 初始位置：主窗口右上角
        self.adjustSize()
        parent_rect = parent.geometry()
        self.move(parent_rect.right() - self.width() - 20, parent_rect.top() + 60)

        # 动画：淡入淡出
        self.opacity_ani = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_ani.setDuration(500)
        
        # 启动显示
        self.show_toast()

    def show_toast(self):
        self.setWindowOpacity(0)
        self.show()
        self.opacity_ani.setStartValue(0)
        self.opacity_ani.setEndValue(0.9)
        self.opacity_ani.start()
        
        # 3秒后自动淡出并销毁
        asyncio.get_event_loop().call_later(3, self.hide_toast)

    def hide_toast(self):
        self.opacity_ani.setDirection(QPropertyAnimation.Backward)
        self.opacity_ani.finished.connect(self.deleteLater)
        self.opacity_ani.start()

class BasePage(QWidget):
    """
    统一基类：解决所有页面的对齐、标题渲染。
    """
    def __init__(self, title, sub_title):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(25, 25, 25, 25)
        self.layout.setSpacing(10)
        
        t_label = QLabel(title)
        t_label.setStyleSheet("font-size: 26px; font-weight: bold; color: white; font-family: 'Segoe UI';")
        s_label = QLabel(sub_title)
        s_label.setStyleSheet("color: #717e95; font-size: 12px;")
        
        line = QFrame()
        line.setFixedHeight(2)
        line.setFixedWidth(40)
        line.setStyleSheet("background-color: #bd93f9;") 

        self.layout.addWidget(t_label)
        self.layout.addWidget(s_label)
        self.layout.addWidget(line)
        
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 15, 0, 0)
        self.layout.addWidget(self.container, 1)

class HomePage(BasePage):
    def __init__(self):
        super().__init__("DASHBOARD", "系统运行状态实时概览")
        label = QLabel("欢迎回来，这是主页内容。")
        label.setStyleSheet("color: #888; font-size: 14px;")
        self.container_layout.addWidget(label, alignment=Qt.AlignTop)

class ChatPage(BasePage):
    def __init__(self):
        super().__init__("AI CHAT", "智能对话交互终端")
        self.container.setStyleSheet("background: rgba(0, 0, 0, 20); border-radius: 10px;")

class LogPage(BasePage):
    def __init__(self):
        super().__init__("SYSTEM LOGS", "支持多窗口对齐查看与实时跟踪")
        self.layout.setContentsMargins(15, 10, 15, 0) 
        self.log_dir = r"D:\filedir\github\my\TTS\log"
        self.viewers = [] 

        sub_title_label = self.layout.itemAt(1).widget() 
        
        self.sub_header_row = QHBoxLayout()
        self.sub_header_row.setContentsMargins(0, 0, 0, 0)
        self.sub_header_row.addWidget(sub_title_label)
        self.sub_header_row.addStretch() 

        btn_style = """
            QPushButton { 
                background: #343b48; border-radius: 4px; padding: 6px 15px; 
                color: white; font-size: 12px; font-weight: bold;
            } 
            QPushButton:hover { background: #4b5465; border: 1px solid #87CEFA; }
        """
        self.add_view_btn = QPushButton("添加分屏 +")
        self.del_view_btn = QPushButton("移除分屏 -")
        self.add_view_btn.setStyleSheet(btn_style)
        self.del_view_btn.setStyleSheet(btn_style)
        
        self.sub_header_row.addWidget(self.add_view_btn)
        self.sub_header_row.addSpacing(10)
        self.sub_header_row.addWidget(self.del_view_btn)

        self.layout.insertLayout(1, self.sub_header_row)

        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Horizontal) 
        self.splitter.setStyleSheet("QSplitter::handle { background: #3e4451; width: 1px; }")
        self.container_layout.addWidget(self.splitter)

        self.add_view_btn.clicked.connect(self.add_viewer)
        self.del_view_btn.clicked.connect(self.remove_viewer)

        self.add_viewer()
        asyncio.ensure_future(self.auto_refresh())

    async def auto_refresh(self):
        while True:
            if hasattr(self, 'stackedWidget') and self.stackedWidget.currentWidget() == self:
                await self.refresh_logs()
            await asyncio.sleep(2)

    async def refresh_logs(self):
        tasks=[]
        for viewer in self.viewers:
            selector = viewer.findChild(QComboBox)
            display = viewer.findChild(QTextEdit)
            if selector and display:
                tasks.append(self.load_log_async(selector.currentText(), display))
        if tasks: await asyncio.gather(*tasks)

    @asyncSlot()
    async def load_log_async(self,filename,display_widget):
        if not filename or filename=="目录不存在":return
        full_path = os.path.join(self.log_dir, filename)
    
        async with aiofiles.open(full_path, mode='r', encoding='utf-8', errors='ignore') as f:
            lines = await f.readlines()
            content = "".join(lines[-1000:])
        
        if display_widget.toPlainText() != content:
            v_bar = display_widget.verticalScrollBar()
            at_bottom = v_bar.value() >= v_bar.maximum() - 20
            display_widget.setPlainText(content)
            if at_bottom:
                v_bar.setValue(v_bar.maximum())

    def add_viewer(self):
        if len(self.viewers) >= 3:
            return

        viewer_widget = QWidget()
        v_layout = QVBoxLayout(viewer_widget)
        v_layout.setContentsMargins(0, 5, 0, 0)

        file_selector = QComboBox()
        file_selector.setStyleSheet("""
            QComboBox { background: #1d2127; border: 1px solid #2c313c; padding: 5px; color: #87CEFA; }
            QComboBox QAbstractItemView { background: #1d2127; selection-background-color: #bd93f9; }
        """)
        self.refresh_files(file_selector)
        
        display = QTextEdit()
        display.setReadOnly(True)
        display.setStyleSheet("""
            QTextEdit {
                background-color: #1d2127; 
                border: 1px solid #2c313c;
                border-bottom-left-radius: 8px; 
                border-bottom-right-radius: 8px;
            }
        """)

        file_selector.currentTextChanged.connect(
            lambda text, d=display: asyncio.ensure_future(self.load_log_async(text, d))
        )

        v_layout.addWidget(file_selector)
        v_layout.addWidget(display)
        
        self.splitter.addWidget(viewer_widget)
        self.viewers.append(viewer_widget)
        
        index = file_selector.findText("speech.log")
        if index >= 0:
            file_selector.setCurrentIndex(index)
        
        if file_selector.currentText():
            asyncio.ensure_future(self.load_log_async(file_selector.currentText(), display))

    def remove_viewer(self):
        if len(self.viewers) > 1:
            self.viewers.pop().deleteLater()

    def refresh_files(self, combo_box):
        combo_box.clear()
        if os.path.exists(self.log_dir):
            files = [f for f in os.listdir(self.log_dir) if f.endswith(('.log', '.txt'))]
            combo_box.addItems(files)
        else:
            combo_box.addItem("目录不存在")

class FloatingMonitor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("性能实时监控")
        self.resize(550, 600)
        self.setStyleSheet("background-color: #16191d; color: #dcdcdc;")
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0) 
        self.main_layout.setSpacing(0)
        
        self.top_bar = QWidget()
        self.top_bar.setFixedHeight(45)
        self.top_bar.setStyleSheet("background: transparent;")
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(15, 5, 15, 5)

        self.mode_btn = QPushButton("切换模式：折线图")
        self.mode_btn.setFixedWidth(110)
        self.mode_btn.setStyleSheet("""
            QPushButton { 
                background: #343b48; border-radius: 4px; padding: 4px; 
                font-size: 11px; color: white; border: 1px solid #4b5465; 
            }
            QPushButton:hover { background: #4b5465; border: 1px solid #bd93f9; }
        """)
        self.mode_btn.clicked.connect(self.toggle_mode)
        
        self.time_label = QLabel("区间: 15s")
        self.time_label.setStyleSheet("color: #717e95; font-size: 11px;")
        self.time_slider = QSlider(Qt.Horizontal)
        self.time_slider.setRange(5, 20)
        self.time_slider.setValue(15)
        self.time_slider.setFixedWidth(100)
        self.time_slider.setStyleSheet("""
            QSlider::groove:horizontal { background: #2c313c; height: 4px; border-radius: 2px; }
            QSlider::handle:horizontal { background: #bd93f9; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }
        """)
        self.time_slider.valueChanged.connect(self.update_time_config)
        
        top_layout.addWidget(self.mode_btn)
        top_layout.addStretch()
        top_layout.addWidget(self.time_label)
        top_layout.addWidget(self.time_slider)
        
        self.main_layout.addWidget(self.top_bar)
        
        self.main_layout.addStretch()
        
        self.mode = "line"
        self.max_samples = 15
        self.data_history = {"CPU 处理器负载": [0]*60, "RAM 内存占用": [0]*60, 'GPU 显存占用': [0]*60}

    def toggle_mode(self):
        self.mode = "bar" if self.mode == "line" else "line"
        self.mode_btn.setText(f"切换模式：{'条状图' if self.mode == 'bar' else '折线图'}")
        self.update()

    def update_time_config(self, val):
        self.max_samples = val
        self.time_label.setText(f"区间: {val}s")
        self.update()

    def update_data(self, cpu, ram, gpu):
        for key, val in zip(["CPU 处理器负载", "RAM 内存占用", "GPU 显存占用"], [cpu, ram, gpu]):
            self.data_history[key].pop(0)
            self.data_history[key].append(val)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        padding_top = 50 
        rect = self.contentsRect().adjusted(50, padding_top, -30, -10)
        sub_h = rect.height() // 3
        
        metrics = [("CPU 处理器负载", "#87CEFA"), ("RAM 内存占用", "#ffb86c"), ("GPU 显存占用", "#bd93f9")]
        for i, (label, color_hex) in enumerate(metrics):
            area = QRect(rect.left(), rect.top() + i * sub_h, rect.width(), sub_h - 20)
            self.draw_plot_area(painter, area, label, color_hex)

    def draw_plot_area(self, painter, rect, label, color_hex):
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.drawLine(rect.bottomLeft(), rect.topLeft())

        painter.setPen(QColor(110, 110, 110))
        painter.drawText(rect.left() - 35, rect.top() + 10, "100%")
        painter.drawText(rect.left() - 25, rect.bottom(), "0%")
        
        painter.setPen(QColor(color_hex))
        painter.drawText(rect.left() + 5, rect.top() + 15, f"● {label}")

        display_data = self.data_history[label][-self.max_samples:]
        
        if self.mode == "line":
            step_x = rect.width() / (len(display_data) - 1)
            path = QPainterPath()
            painter.setPen(QPen(QColor(color_hex), 2))
            for i, val in enumerate(display_data):
                x = rect.left() + i * step_x
                y = rect.bottom() - (max(1, val) / 100.0 * rect.height()) 
                if i == 0: path.moveTo(x, y)
                else: path.lineTo(x, y)
            painter.drawPath(path)
        else:
            val = display_data[-1]
            painter.setBrush(QColor(color_hex))
            bar_w = rect.width() * (val / 100.0)
            painter.drawRect(rect.left(), rect.top() + 20, bar_w, rect.height() - 25)
            
        painter.setPen(QColor(color_hex))
        painter.drawText(rect.right() - 30, rect.top() + 15, f"{int(display_data[-1])}%")

class MonitorPage(BasePage):
    def __init__(self):
        super().__init__("PERFORMANCE", "硬件资源实时负载监控")
        self.layout.setContentsMargins(10, 5, 10, 0)
        
        sub_title_label = self.layout.itemAt(1).widget()
        header_row = QHBoxLayout()
        header_row.addWidget(sub_title_label)
        header_row.addStretch()

        self.float_win_btn = QPushButton("开启独立监控 ↗")
        self.float_win_btn.setStyleSheet("""
            QPushButton { 
                background: #bd93f9; border-radius: 4px; padding: 6px 12px; 
                color: white; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background: #ff79c6; }
        """)
        self.float_win_btn.clicked.connect(self.open_floating_monitor)
        header_row.addWidget(self.float_win_btn)
        
        self.layout.insertLayout(1, header_row)

        self.container_layout.setContentsMargins(0, 5, 0, 0)
        self.container_layout.setSpacing(15) 

        self.gpu_enabled = False
        try:
            pynvml.nvmlInit()
            self.gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self.gpu_enabled = True
        except: pass

        grid = QVBoxLayout()
        self.cpu_data = self.add_monitor_item("CPU 处理器负载", grid)
        self.mem_data = self.add_monitor_item("RAM 内存占用", grid) # 已改为内存占用
        self.gpu_data = self.add_monitor_item("GPU 显存占用", grid)
        
        self.container_layout.addLayout(grid)
        self.container_layout.addStretch()

        self.floating_win = None
        asyncio.ensure_future(self.update_stats())

    def open_floating_monitor(self):
        if not self.floating_win: self.floating_win = FloatingMonitor()
        self.floating_win.show()

    async def update_stats(self):
        while True:
            main_active = self.window().stackedWidget.currentWidget() == self
            float_active = self.floating_win and self.floating_win.isVisible()
            
            if main_active or float_active:
                cpu = psutil.cpu_percent()
                mem = psutil.virtual_memory().percent
                
                gpu_percent = 0
                if self.gpu_enabled:
                    try:
                        info = pynvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
                        gpu_percent = (info.used / info.total) * 100
                    except:
                        gpu_percent = 0

                if main_active:
                    self.cpu_data[0].setValue(int(cpu))
                    self.update_bar_style(self.cpu_data[0], cpu, self.cpu_data[1])
                    self.cpu_data[1].setText(f"{int(cpu)}%")
                    
                    self.mem_data[0].setValue(int(mem))
                    self.update_bar_style(self.mem_data[0], mem, self.mem_data[1])
                    self.mem_data[1].setText(f"{int(mem)}%")
                    
                    self.gpu_data[0].setValue(int(gpu_percent))
                    self.update_bar_style(self.gpu_data[0], gpu_percent, self.gpu_data[1])
                    self.gpu_data[1].setText(f"{int(gpu_percent)}%")
                
                if float_active:
                    self.floating_win.update_data(cpu, mem, gpu_percent)
            
            await asyncio.sleep(1 if (main_active or float_active) else 2)

    def update_bar_style(self, bar, value, label):
        color = "#87CEFA"
        if value > 80: color = "#ff5555"
        elif value > 60: color = "#ffb86c"
        
        label.setStyleSheet(f"color: {color}; font-weight: bold; font-family: 'Consolas'; font-size: 14px;")
        bar.setStyleSheet(f"""
            QProgressBar {{ background: #1d2127; border-radius: 4px; border: 1px solid #2c313c; }}
            QProgressBar::chunk {{ background-color: {color}; border-radius: 4px; }}
        """)

    def add_monitor_item(self, name, layout):
        item_w = QWidget()
        v_layout = QVBoxLayout(item_w)
        header_layout = QHBoxLayout()
        
        title_lbl = QLabel(name)
        title_lbl.setStyleSheet("color: #dcdcdc; font-size: 13px;")
        
        value_lbl = QLabel("0%")
        value_lbl.setStyleSheet("color: #87CEFA; font-weight: bold; font-family: 'Consolas'; font-size: 14px;")
        
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        header_layout.addWidget(value_lbl)
        v_layout.addLayout(header_layout)
        
        bar = QProgressBar()
        bar.setFixedHeight(10)
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        v_layout.addWidget(bar)
        
        layout.addWidget(item_w)
        return (bar, value_lbl)

    def __del__(self):
        if hasattr(self, 'gpu_enabled') and self.gpu_enabled:
            try:
                pynvml.nvmlShutdown()
            except:
                pass

class SettingPage(BasePage):
    def __init__(self):
        super().__init__("SETTINGS", "系统参数与个性化配置")

class ShimmerOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0, QColor(0, 0, 0, 0))              
        gradient.setColorAt(0.2, QColor(135, 206, 250, 10))    
        gradient.setColorAt(0.5, QColor(135, 206, 250, 80))    
        gradient.setColorAt(0.8, QColor(200, 235, 255, 255))   
        gradient.setColorAt(0.95, QColor(135, 206, 250, 100))  
        gradient.setColorAt(1, QColor(0, 0, 0, 0))
        
        painter.fillRect(self.rect(), gradient)

    def play(self):
        btn_w = self.parent().width()
        btn_h = self.parent().height()
        overlay_w = btn_w * 2  
        self.resize(overlay_w, btn_h)
        self.show()
        if hasattr(self, 'ani'): self.ani.stop()
        self.ani = QPropertyAnimation(self, b"geometry")
        self.ani.setDuration(1000)
        
        w, h = self.width(), self.height()
        self.ani.setStartValue(QRect(-w, 0, w, h))
        self.ani.setEndValue(QRect(w, 0, w, h))
        self.ani.setEasingCurve(QEasingCurve.OutCubic)
        self.ani.finished.connect(self.hide)
        self.ani.start()

class MyWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setMinimumSize(550, 350)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.sizegrip = QSizeGrip(self.frame_size_grip)
        self.sizegrip.setStyleSheet("width: 20px; height: 20px; margin: 0px; padding: 0px;")
        self.move(100, 100)
        self.dragPos = QPoint()

        self.btn_menu.overlay = ShimmerOverlay(self.btn_menu)
        self.btn_menu.clicked.connect(self.btn_menu.overlay.play)

        menu_btns = [self.btn_home, self.btn_chat, self.btn_setting, self.btn_monitor, self.btn_log]
        for i, btn in enumerate(menu_btns):
            btn.overlay = ShimmerOverlay(btn)
            btn.clicked.connect(lambda checked=False, b=btn, index=i: self.apply_blue_shimmer(b, index))

        self.page_home = HomePage()
        self.page_monitor = MonitorPage()
        self.page_log = LogPage()
        self.page_chat = ChatPage()
        self.page_setting = SettingPage()

        while self.stackedWidget.count() > 0:
            self.stackedWidget.removeWidget(self.stackedWidget.widget(0))

        self.stackedWidget.addWidget(self.page_home)    
        self.stackedWidget.addWidget(self.page_chat)    
        self.stackedWidget.addWidget(self.page_setting) 
        self.stackedWidget.addWidget(self.page_monitor) 
        self.stackedWidget.addWidget(self.page_log)     

        self.stackedWidget.setCurrentIndex(0)

        self.closeAppBtn.clicked.connect(self.close)
        self.maximizeRestoreAppBtn.clicked.connect(self.toggle_maximize)
        self.minimizeAppBtn.clicked.connect(self.showMinimized)

        self.notify("初始化成功")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.contentTopBg.underMouse():
                self.dragPos = event.globalPosition().toPoint()
                event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.contentTopBg.underMouse():
            self.move(self.pos() + event.globalPosition().toPoint() - self.dragPos)
            self.dragPos = event.globalPosition().toPoint()
            event.accept()

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            icon_path = u":/icons/images/icons/icon_maximize.png"
        else: 
            self.showMaximized()
            icon_path = u":/icons/images/icons/icon_restore.png"
        icon = QIcon()
        icon.addFile(icon_path, QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.maximizeRestoreAppBtn.setIcon(icon)
    
    def apply_blue_shimmer(self, button, index):
        if hasattr(button, 'overlay'):
            button.overlay.play()
        self.stackedWidget.setCurrentIndex(index)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.contentTopBg.underMouse():
                self.dragPos = event.globalPosition().toPoint()
                event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.contentTopBg.underMouse():
            self.move(self.pos() + event.globalPosition().toPoint() - self.dragPos)
            self.dragPos = event.globalPosition().toPoint()
            event.accept()

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            icon_path = u":/icons/images/icons/icon_maximize.png"
        else: 
            self.showMaximized()
            icon_path = u":/icons/images/icons/icon_restore.png"
        
        icon = QIcon()
        icon.addFile(icon_path, QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.maximizeRestoreAppBtn.setIcon(icon)
    
    @asyncSlot()
    async def apply_blue_shimmer(self, button, index):
        if hasattr(button, 'overlay'):
            button.overlay.play()
        if hasattr(self, 'stackedWidget'):
            self.stackedWidget.setCurrentIndex(index)

    def notify(self, message, level="info"):
        """
        类似手机通知的非阻塞播报
        level: info (蓝色), warn (橙色), error (红色)
        """
        colors = {
            "info": "#87CEFA",
            "warn": "#ffb86c",
            "error": "#ff5555"
        }
        ToastNotification(self, message, colors.get(level, "#87CEFA"))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MyWindow()
    window.show()

    with loop: loop.run_forever()