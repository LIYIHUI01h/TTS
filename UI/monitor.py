import os
import asyncio
import psutil
import pynvml
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QSlider, QVBoxLayout, QWidget
from UI.widgets import BasePage
from UI.common import logger


class FloatingMonitor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle('性能实时监控')
        self.resize(550, 600)
        self.setStyleSheet('background-color: #16191d; color: #dcdcdc;')

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.top_bar = QWidget()
        self.top_bar.setFixedHeight(45)
        self.top_bar.setStyleSheet('background: transparent;')
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(15, 5, 15, 5)

        self.mode_btn = QPushButton('切换模式：折线图')
        self.mode_btn.setFixedWidth(110)
        self.mode_btn.setStyleSheet('''
            QPushButton { 
                background: #343b48; border-radius: 4px; padding: 4px; 
                font-size: 11px; color: white; border: 1px solid #4b5465; 
            }
            QPushButton:hover { background: #4b5465; border: 1px solid #bd93f9; }
        ''')
        self.mode_btn.clicked.connect(self.toggle_mode)

        self.time_label = QLabel('区间: 15s')
        self.time_label.setStyleSheet('color: #717e95; font-size: 11px;')
        self.time_slider = QSlider(Qt.Horizontal)
        self.time_slider.setRange(5, 20)
        self.time_slider.setValue(15)
        self.time_slider.setFixedWidth(100)
        self.time_slider.setStyleSheet('''
            QSlider::groove:horizontal { background: #2c313c; height: 4px; border-radius: 2px; }
            QSlider::handle:horizontal { background: #bd93f9; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }
        ''')
        self.time_slider.valueChanged.connect(self.update_time_config)

        top_layout.addWidget(self.mode_btn)
        top_layout.addStretch()
        top_layout.addWidget(self.time_label)
        top_layout.addWidget(self.time_slider)

        self.main_layout.addWidget(self.top_bar)
        self.main_layout.addStretch()

        self.mode = 'line'
        self.max_samples = 15
        self.data_history = {'CPU 处理器负载': [0] * 60, 'RAM 内存占用': [0] * 60, 'GPU 显存占用': [0] * 60}

    def toggle_mode(self):
        self.mode = 'bar' if self.mode == 'line' else 'line'
        self.mode_btn.setText(f"切换模式：{'条状图' if self.mode == 'bar' else '折线图'}")
        self.update()

    def update_time_config(self, val):
        self.max_samples = val
        self.time_label.setText(f'区间: {val}s')
        self.update()

    def update_data(self, cpu, ram, gpu):
        for key, val in zip(['CPU 处理器负载', 'RAM 内存占用', 'GPU 显存占用'], [cpu, ram, gpu]):
            self.data_history[key].pop(0)
            self.data_history[key].append(val)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        padding_top = 50
        rect = self.contentsRect().adjusted(50, padding_top, -30, -10)
        sub_h = rect.height() // 3

        metrics = [('CPU 处理器负载', '#87CEFA'), ('RAM 内存占用', '#ffb86c'), ('GPU 显存占用', '#bd93f9')]
        for i, (label, color_hex) in enumerate(metrics):
            area = QRect(rect.left(), rect.top() + i * sub_h, rect.width(), sub_h - 20)
            self.draw_plot_area(painter, area, label, color_hex)

    def draw_plot_area(self, painter, rect, label, color_hex):
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.drawLine(rect.bottomLeft(), rect.topLeft())

        painter.setPen(QColor(110, 110, 110))
        painter.drawText(rect.left() - 35, rect.top() + 10, '100%')
        painter.drawText(rect.left() - 25, rect.bottom(), '0%')

        painter.setPen(QColor(color_hex))
        painter.drawText(rect.left() + 5, rect.top() + 15, f'● {label}')

        display_data = self.data_history[label][-self.max_samples:]
        if self.mode == 'line':
            step_x = rect.width() / (len(display_data) - 1)
            path = QPainterPath()
            painter.setPen(QPen(QColor(color_hex), 2))
            for i, val in enumerate(display_data):
                x = rect.left() + i * step_x
                y = rect.bottom() - (max(1, val) / 100.0 * rect.height())
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.drawPath(path)
        else:
            val = display_data[-1]
            painter.setBrush(QColor(color_hex))
            bar_w = rect.width() * (val / 100.0)
            painter.drawRect(rect.left(), rect.top() + 20, bar_w, rect.height() - 25)

        painter.setPen(QColor(color_hex))
        painter.drawText(rect.right() - 30, rect.top() + 15, f"{int(display_data[-1])}%")


class MonitorPage(BasePage):
    def __init__(self, flags):
        super().__init__('PERFORMANCE', '硬件资源实时负载监控')
        self.layout.setContentsMargins(10, 5, 10, 0)
        self.flags = flags
        sub_title_label = self.layout.itemAt(1).widget()
        header_row = QHBoxLayout()
        header_row.addWidget(sub_title_label)
        header_row.addStretch()

        self.float_win_btn = QPushButton('开启独立监控 ↗')
        self.float_win_btn.setStyleSheet('''
            QPushButton { 
                background: #bd93f9; border-radius: 4px; padding: 6px 12px; 
                color: white; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background: #ff79c6; }
        ''')
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
        except Exception:
            pass

        grid = QVBoxLayout()
        self.cpu_data = self.add_monitor_item('CPU 处理器负载', grid)
        self.mem_data = self.add_monitor_item('RAM 内存占用', grid)
        self.gpu_data = self.add_monitor_item('GPU 显存占用', grid)
        self.container_layout.addLayout(grid)
        self.container_layout.addStretch()

        self.monitor_task = None
        self.floating_win = None

    def showEvent(self, event):
        super().showEvent(event)
        if self.monitor_task is None or self.monitor_task.done():
            self.monitor_task = asyncio.create_task(self.update_stats())

    def hideEvent(self, event):
        super().hideEvent(event)
        if self.monitor_task:
            self.monitor_task.cancel()
            self.monitor_task = None

    def open_floating_monitor(self):
        if not self.floating_win:
            self.floating_win = FloatingMonitor()
        self.floating_win.show()

    async def update_stats(self):
        while True:
            try:
                main_active = False
                try:
                    main_active = self.window().stackedWidget.currentWidget() == self
                except Exception:
                    pass
                float_active = self.floating_win and self.floating_win.isVisible()
                if main_active or float_active:
                    cpu = psutil.cpu_percent()
                    mem = psutil.virtual_memory().percent
                    gpu_percent = 0
                    if self.gpu_enabled:
                        try:
                            info = pynvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
                            gpu_percent = (info.used / info.total) * 100
                        except Exception:
                            pass
                    if main_active:
                        self.cpu_data[0].setValue(int(cpu))
                        self.update_bar_style(self.cpu_data[0], cpu, self.cpu_data[1])
                        self.cpu_data[1].setText(f'{int(cpu)}%')
                        self.mem_data[0].setValue(int(mem))
                        self.update_bar_style(self.mem_data[0], mem, self.mem_data[1])
                        self.mem_data[1].setText(f'{int(mem)}%')
                        self.gpu_data[0].setValue(int(gpu_percent))
                        self.update_bar_style(self.gpu_data[0], gpu_percent, self.gpu_data[1])
                        self.gpu_data[1].setText(f'{int(gpu_percent)}%')
                    if float_active:
                        self.floating_win.update_data(cpu, mem, gpu_percent)
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.info(f'性能监视出错: {e}')
                await asyncio.sleep(1)

    def update_bar_style(self, bar, value, label):
        color = '#87CEFA'
        if value > 80:
            color = '#ff5555'
        elif value > 60:
            color = '#ffb86c'
        label.setStyleSheet(f'color: {color}; font-weight: bold; font-family: \'Consolas\'; font-size: 14px;')
        bar.setStyleSheet(f'''
            QProgressBar {{ background: #1d2127; border-radius: 4px; border: 1px solid #2c313c; }}
            QProgressBar::chunk {{ background-color: {color}; border-radius: 4px; }}
        ''')

    def add_monitor_item(self, name, layout):
        item_w = QWidget()
        v_layout = QVBoxLayout(item_w)
        header_layout = QHBoxLayout()

        title_lbl = QLabel(name)
        title_lbl.setStyleSheet('color: #dcdcdc; font-size: 13px;')
        value_lbl = QLabel('0%')
        value_lbl.setStyleSheet('color: #87CEFA; font-weight: bold; font-family: \'Consolas\'; font-size: 14px;')

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
            except Exception:
                pass
