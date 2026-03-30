import base64
import http
import math
import os
import sys
import pynvml
import asyncio
from datetime import datetime
import copy
import psutil
import aiofiles
import json
import socket
import shutil
import hashlib
import mysql.connector
from mika.tool import  getLogger
from mysql.connector import Error
from mika.api import SiliconCloud_model
from PySide6.QtCore import QProcess, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QAbstractAnimation, QBuffer, QEvent, QEasingCurve, QIODevice, QMimeData, QParallelAnimationGroup, QPointF, QSettings, QTimer, QUrl, Qt, QPropertyAnimation, QPoint, QRect, QSize, QVariantAnimation, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QShowEvent, QTextCursor,QPixmap
from PySide6.QtWidgets import QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QGraphicsProxyWidget, QGraphicsScene, QGraphicsView, QGridLayout, QInputDialog, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QScrollArea, QSizeGrip, QPushButton, QSizePolicy, QSlider, QSplitter, QStackedLayout, QStackedWidget, QTextEdit, QTreeWidget, QTreeWidgetItem, QWidget
from qasync import QEventLoop, asyncSlot
from UI.main_ui import QFrame, QHBoxLayout, QLabel, QVBoxLayout, Ui_MainWindow 
from llama_index.core.schema import TextNode

logger=getLogger(log_path="log/UI.log",log_name="UI",mode='w')

class ToastNotification(QWidget):
    def __init__(self, parent, message, color="#87CEFA"):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.ToolTip)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
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
        
        self.adjustSize()
        parent_rect = parent.geometry()
        self.move(parent_rect.right() - self.width() - 20, parent_rect.top() + 60)

        self.opacity_ani = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_ani.setDuration(500)
        
        self.show_toast()

    def show_toast(self):
        self.setWindowOpacity(0)
        self.show()
        self.opacity_ani.setStartValue(0)
        self.opacity_ani.setEndValue(0.9)
        self.opacity_ani.start()
        
        QTimer.singleShot(3000, self.hide_toast)

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

# ================================HomePage=============================================

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'user_names'
}

def get_round_pixmap(path, size=45):
    if not path or not os.path.exists(path):
        return None
    
    src = QPixmap(path).scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    
    path_draw = QPainterPath()
    path_draw.addEllipse(0, 0, size, size)
    painter.setClipPath(path_draw)
    
    painter.drawPixmap(0, 0, src)
    painter.end()
    return out

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(360, 420)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.settings = QSettings("MikaApp", "LoginSettings")
        self.logged_user_data = None
        self.is_reg_mode = False
        self.init_ui()
        self.load_last_account()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.container = QFrame()
        self.container.setStyleSheet("""
            QFrame { background-color: #1d2127; border: 1px solid #3e4451; border-radius: 15px; }
            #CloseBtn { background: transparent; color: #6272a4; font-size: 18px; border: none; }
            #CloseBtn:hover { color: #ff5555; }
            QLabel#Title { color: #bd93f9; font-size: 20px; font-weight: bold; border: none; }
            QLineEdit { background: #16191d; border-radius: 10px; padding: 12px; color: white; border: 1px solid #3e4451; }
            QPushButton#ActionBtn { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #bd93f9, stop:1 #8be9fd); 
                color: #1d2127; font-weight: bold; border-radius: 10px; height: 45px; border: none; 
            }
            QPushButton#SwitchBtn { 
                background: transparent; color: #6272a4; font-size: 11px; border: none; 
                text-decoration: underline; margin-top: 5px;
            }
            QPushButton#SwitchBtn:hover { color: #bd93f9; }
        """)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(30, 10, 30, 25)
        layout.setSpacing(15)

        top_bar = QHBoxLayout()
        top_bar.addStretch()
        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("CloseBtn")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self.reject)
        top_bar.addWidget(self.close_btn)
        layout.addLayout(top_bar)

        self.title_label = QLabel("SYSTEM LOGIN")
        self.title_label.setObjectName("Title")
        layout.addWidget(self.title_label, alignment=Qt.AlignCenter)
        
        layout.addSpacing(5)

        self.acc_i = QLineEdit()
        self.acc_i.setPlaceholderText("账号")
        
        self.pwd_i = QLineEdit()
        self.pwd_i.setPlaceholderText("密码")
        self.pwd_i.setEchoMode(QLineEdit.Password)
        
        self.name_i = QLineEdit()
        self.name_i.setPlaceholderText("用户名(称呼)")
        self.name_i.hide()
        
        layout.addWidget(self.acc_i)
        layout.addWidget(self.pwd_i)
        layout.addWidget(self.name_i)
        
        layout.addStretch()

        self.btn = QPushButton("确 认 登 录")
        self.btn.setObjectName("ActionBtn")
        self.btn.clicked.connect(self.handle_action)
        layout.addWidget(self.btn)

        self.switch_btn = QPushButton("没有账号？点击注册")
        self.switch_btn.setObjectName("SwitchBtn")
        self.switch_btn.setCursor(Qt.PointingHandCursor)
        self.switch_btn.clicked.connect(self.toggle_mode)
        layout.addWidget(self.switch_btn, alignment=Qt.AlignCenter)
        
        self.main_layout.addWidget(self.container)

    def try_silent_login(self):
        """核心：尝试静默自动登录"""
        acc = self.settings.value("last_account", "")
        pwd_h = self.settings.value("last_pwd_h", "")
        auto = self.settings.value("auto_login", "false")
        if auto == "false" or auto is False: return None

        if not acc or not pwd_h: return None

        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE account=%s AND password_hash=%s", (acc, pwd_h))
            user = cursor.fetchone()
            conn.close()

            if user:
                return {
                    "username": str(user.get("username", "Unknown")),
                    "uid": str(user.get("id", "0")),
                    "avatar_path": user.get("profile_photo_path")
                }
        except Exception as e:
            self.logger.info(f"自动登录异常: {e}")
        return None

    def toggle_mode(self):
        self.is_reg_mode = not self.is_reg_mode
        if self.is_reg_mode:
            self.title_label.setText("CREATE ACCOUNT")
            self.btn.setText("注 册 并 登 录")
            self.switch_btn.setText("已有账号？返回登录")
            self.name_i.show()
            self.setFixedSize(360, 480)
        else:
            self.title_label.setText("SYSTEM LOGIN")
            self.btn.setText("确 认 登 录")
            self.switch_btn.setText("没有账号？点击注册")
            self.name_i.hide()
            self.setFixedSize(360, 420)

    def handle_action(self):
        if self.is_reg_mode: self.run_registration()
        else: self.handle_auth()

    def run_registration(self):
        acc, pwd, name = self.acc_i.text().strip(), self.pwd_i.text().strip(), self.name_i.text().strip()
        if not acc or not pwd or not name:
            QMessageBox.warning(self, "错误", "请填写完整注册信息")
            return
        try:
            import mysql.connector
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE account=%s", (acc,))
            if cursor.fetchone():
                QMessageBox.warning(self, "错误", "该账号已存在")
                return
            pwd_h = hashlib.sha256(pwd.encode()).hexdigest()
            cursor.execute("INSERT INTO users (account, password_hash, username) VALUES (%s, %s, %s)", (acc, pwd_h, name))
            conn.commit()
            conn.close()
            QMessageBox.information(self, "成功", "注册成功，正在进入系统...")
            self.handle_auth()
        except Exception as e:
            QMessageBox.critical(self, "数据库异常", str(e))

    def handle_auth(self):
        acc, pwd = self.acc_i.text().strip(), self.pwd_i.text().strip()
        try:
            import mysql.connector
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            pwd_h = hashlib.sha256(pwd.encode()).hexdigest()
            cursor.execute("SELECT * FROM users WHERE account=%s AND password_hash=%s", (acc, pwd_h))
            user = cursor.fetchone()
            
            if user:
                self.settings.setValue("last_account", acc)
                self.settings.setValue("last_pwd_h", pwd_h) 
                self.settings.setValue("auto_login", True)
                self.settings.sync()
                
                self.logged_user_data = {
                    "username": str(user.get("username", "Unknown")),
                    "uid": str(user.get("id", "0")),
                    "avatar_path": user.get("profile_photo_path")
                }
                conn.close()
                self.accept() 
            else:
                QMessageBox.warning(self, "失败", "账号或密码错误")
                conn.close()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"数据库连接异常: {e}")

    def load_last_account(self):
        last_acc = self.settings.value("last_account", "")
        if last_acc:
            self.acc_i.setText(last_acc)
            self.pwd_i.setFocus()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def get_user_info(self):
        return self.logged_user_data

def get_round_pixmap(path, size):
    if not path or not os.path.exists(path):
        return None
    src = QPixmap(path).scaled(size, size, 
                               Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
                               Qt.TransformationMode.SmoothTransformation)
    
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform) # 增加平滑度
    
    path_circle = QPainterPath()
    path_circle.addEllipse(0, 0, size, size)
    painter.setClipPath(path_circle)
    
    x_offset = (src.width() - size) // 2
    y_offset = (src.height() - size) // 2
    painter.drawPixmap(0, 0, src.copy(x_offset, y_offset, size, size))
    
    painter.end()
    return out

class ProfileHoverCard(QFrame):
    def __init__(self, parent, login_cb, logout_cb):
        super().__init__(parent)
        self.setFixedSize(280, 400)
        self.login_cb, self.logout_cb = login_cb, logout_cb
        self.target_avatar = None
        self.timer = QTimer(self); self.timer.timeout.connect(self._check_mouse)
        
        self.setStyleSheet("""
            QFrame { background: transparent; border: 1px solid rgba(255, 255, 255, 0.1);; }
            QLabel { color: white; font-family: 'Microsoft YaHei'; border: none; background: transparent; }
            QPushButton#login { 
                background-color: #bd93f9; color: white; border-radius: 8px; 
                font-weight: bold; height: 38px; border: none; 
            }
            QPushButton#logout { 
                color: #ff5555; background: transparent; 
                border: 1px solid #ff5555; border-radius: 6px; padding: 4px; 
            }
        """)

        l = QVBoxLayout(self)
        self.stack = QStackedWidget()
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(self.stack)

        self.p0 = QWidget(); l0 = QVBoxLayout(self.p0); l0.setContentsMargins(20, 60, 20, 20)
        self.tip = QLabel("登录以体验更多功能")
        btn_in = QPushButton("立即登录"); btn_in.setObjectName("login"); btn_in.clicked.connect(self._on_in)
        l0.addWidget(self.tip, alignment=Qt.AlignmentFlag.AlignCenter); l0.addStretch(); l0.addWidget(btn_in)
        self.stack.addWidget(self.p0)

        self.p1 = QWidget(); l1 = QVBoxLayout(self.p1); l1.setContentsMargins(20, 60, 20, 20)
        self.u_na = QLabel("璃依回")
        self.u_na.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.u_id = QLabel("UID: 1")
        self.u_id.setStyleSheet("font-size: 12px; color: #717e95;")
        btn_out = QPushButton("注销登录"); btn_out.setObjectName("logout"); btn_out.clicked.connect(self._on_out)
        
        l1.addWidget(self.u_na, alignment=Qt.AlignmentFlag.AlignCenter)
        l1.addWidget(self.u_id, alignment=Qt.AlignmentFlag.AlignCenter)
        l1.addStretch()
        l1.addWidget(btn_out)
        self.stack.addWidget(self.p1)

    def set_user_data(self, data):
        if data:
            self.u_na.setText(data.get('username', '璃依回'))
            self.u_id.setText(f"UID: {data.get('uid', '1')}")
            self.stack.setCurrentIndex(1)
        else: self.stack.setCurrentIndex(0)

    def show_safe(self, pos, target):
        self.target_avatar = target; self.move(pos); self.show(); self.raise_()
        if self.target_avatar: self.target_avatar.raise_()
        self.timer.start(80)

    def _check_mouse(self):
        if not self.isVisible() or self.target_avatar is None: return
        p = QCursor.pos()
        local_p = self.parent().mapFromGlobal(p)
        
        rect_avatar = self.target_avatar.geometry().adjusted(-20, -20, 20, 20)
        if not self.geometry().contains(local_p) and not rect_avatar.contains(local_p):
            self.hide()
            self.timer.stop()
            if hasattr(self.parent(), 'zoom_out_avatar'):
                 self.parent().zoom_out_avatar()

    def _on_in(self):
        self.timer.stop() 
        self.hide()
        
        if hasattr(self.parent(), 'zoom_out_avatar'):
            self.parent().zoom_out_avatar()
            
        self.login_cb()

    def _on_out(self): self.logout_cb(); self.set_user_data(None)

class HomePage(QWidget):
    def __init__(self):
        super().__init__()
        self.user_data = None 
        self.user_name="游客"
        self.init_ui()

        self.card_widget = ProfileHoverCard(self, self._exec_login, self._exec_logout)
        self.card_widget.hide()
        
        self.avatar_label = QLabel(self)
        self.avatar_label.setFixedSize(45, 45)
        self.avatar_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setStyleSheet("""
            background: #2d323b; 
            border: 2px solid white; 
            border-radius: 22px; 
            color: white; 
            font-weight: bold;
        """)
        self.avatar_label.setText("?")
        
        self.ani = QVariantAnimation(self)
        self.ani.setDuration(150)
        self.ani.setStartValue(45)
        self.ani.setEndValue(75) 
        self.ani.valueChanged.connect(self._animate_avatar)

        self.avatar_label.installEventFilter(self)
        self.avatar_label.raise_()

        QTimer.singleShot(200, self.check_auto_login)

    def init_ui(self):
        """主页左上角标题布局"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(25, 25, 25, 0)
        
        header = QWidget()
        header.setFixedHeight(100)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)

        text_wrapper = QWidget()
        v_text = QVBoxLayout(text_wrapper)
        v_text.setContentsMargins(0, 0, 0, 0)
        v_text.setSpacing(6)

        self.page_title = QLabel("USER PROFILE")
        self.page_title.setStyleSheet("font-size: 26px; font-weight: bold; color: white;")
        
        self.sub_tip = QLabel("用户主页，用于用户个性展示")
        self.sub_tip.setStyleSheet("color: #717e95; font-size: 13px;")
        
        self.purple_line = QFrame()
        self.purple_line.setFixedHeight(3)
        self.purple_line.setFixedWidth(45)
        self.purple_line.setStyleSheet("background-color: #bd93f9; border-radius: 1px;")

        v_text.addWidget(self.page_title)
        v_text.addWidget(self.sub_tip)
        v_text.addWidget(self.purple_line)
        
        h_layout.addWidget(text_wrapper, stretch=1)
        h_layout.addSpacing(150) 

        self.main_layout.addWidget(header)
        self.main_layout.addStretch()

    def _animate_avatar(self, value):
        self.avatar_label.setFixedSize(value, value)
        radius = value // 2
        
        if self.user_data and self.user_data.get("avatar_path"):
            pix = get_round_pixmap(self.user_data["avatar_path"], value)
            if pix:
                self.avatar_label.setPixmap(pix)
                self.avatar_label.setText("")
        
        self.avatar_label.setStyleSheet(f"background: #2d323b; border: 2px solid white; border-radius: {radius}px; color: white;")
        self.update_positions()

    def update_positions(self):
        right_margin = 120
        top_margin = 40

        ax = self.width() - self.avatar_label.width() - right_margin
        ay = top_margin
        self.avatar_label.move(ax, ay)

        card_x = ax - (self.card_widget.width() // 2) + (self.avatar_label.width() // 2)
        card_y = ay + (self.avatar_label.height() // 2) 
        self.card_widget.move(card_x, card_y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_positions()

    def eventFilter(self, watched, event):
        if watched == self.avatar_label:
            if event.type() == QEvent.Type.Enter:
                self.ani.setDirection(QVariantAnimation.Direction.Forward)
                self.ani.start()
                self.card_widget.show_safe(self.card_widget.pos(), self.avatar_label)
                self.avatar_label.raise_()
        return super().eventFilter(watched, event)

    def zoom_out_avatar(self):
        self.ani.setDirection(QVariantAnimation.Direction.Backward)
        self.ani.start()

    def _exec_login(self):
        if self.card_widget:
            self.card_widget.hide()
        self.zoom_out_avatar()

        d = LoginDialog(self)
        if d.exec() == QDialog.DialogCode.Accepted:
            data = d.get_user_info()
            if data:
                self.user_name = data.get("username", "游客")
                
                settings = QSettings("MikaApp", "LoginSettings")
                settings.setValue("auto_login", True)
                settings.setValue("user_data", data)
                
                self.apply_user_state(data)

    def _exec_logout(self):
        self.user_data = None
        settings = QSettings("MikaApp", "LoginSettings")
        settings.remove("auto_login")
        settings.remove("user_data")
        
        self.apply_user_state(None)

    def apply_user_state(self, data):
        self.user_data = data
        self.user_name = data.get("username", "游客")
        if data:
            pix = get_round_pixmap(data.get("avatar_path"), 45)
            if pix:
                self.avatar_label.setPixmap(pix)
                self.avatar_label.setText("")
            else:
                self.avatar_label.setText(data.get("username", "U")[0])
            self.card_widget.set_user_data(data)
        else:
            self.avatar_label.setPixmap(QPixmap())
            self.avatar_label.setText("?")
            self.card_widget.set_user_data(None)

    def check_auto_login(self):
        settings = QSettings("MikaApp", "LoginSettings")
        is_auto = str(settings.value("auto_login", "false")).lower() == "true"
        
        if is_auto:
            saved_data = settings.value("user_data")
            if saved_data:
                self.user_name = saved_data.get("username", "游客")
                self.apply_user_state(saved_data)

# ================================ChatPage=============================================

class MultimodalEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)
        
        self.image_data_list = []  
        self.preview_layout = None  
        self.preview_container = None 

        self.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3e4451;
                border-radius: 8px;
                /* padding 解决光标紧贴边缘和输入法遮挡问题 */
                padding: 10px;
                /* 现代字体集 */
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
        """)
        self.setPlaceholderText("在此输入文字...")

    def insertFromMimeData(self, source: QMimeData):
        """处理剪贴板数据：优先拦截图片，如果是文字则正常处理"""
        if source.hasImage():
            image = QImage(source.imageData())
            if not image.isNull():
                self._process_qimage(image, "Clipboard_Image")
                return 

        super().insertFromMimeData(source)

    def insert_image(self, file_path):
        """处理本地文件图片"""
        image = QImage(file_path)
        if image.isNull():
            return
        self._process_qimage(image, file_path)

    def _process_qimage(self, image, label_path):
        """统一处理图片转 Base64 逻辑"""
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "JPG", 85)  
        img_base64 = base64.b64encode(buffer.data().data()).decode()
        buffer.close()
        
        self.image_data_list.append(img_base64)

        self.add_preview_card(image, img_base64)
        
        if self.preview_container:
            self.preview_container.show()

    def add_preview_card(self, qimage_obj, data_ptr):
        """创建一个带删除按钮的缩略图卡片"""
        card = QFrame()
        card.setFixedSize(70, 70)
        card.setStyleSheet("""
            QFrame { 
                background: #2c313c; border-radius: 6px; 
                border: 1px solid #3e4451; 
            }
        """)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(2, 2, 2, 2)

        lbl = QLabel()
        pix = QPixmap.fromImage(qimage_obj).scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        lbl.setPixmap(pix)
        lbl.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(lbl)
        
        del_btn = QPushButton("×", card)
        del_btn.setFixedSize(16, 16)
        del_btn.move(52, 2)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet("""
            QPushButton { 
                background: rgba(255, 85, 85, 0.8); color: white; 
                border-radius: 8px; font-size: 10px; font-weight: bold; border: none;
            }
            QPushButton:hover { background: #ff5555; }
        """)
        
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
        """修复：拖入图片后不再输入文件路径"""
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
                w = item.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()

class HoverButton(QPushButton):
    hovered = Signal(bool)
    def enterEvent(self, event):
        super().enterEvent(event)
        self.hovered.emit(True)
    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.hovered.emit(False)

from live2d.live2d_UI import CustomPage

class ChatPage(QWidget):
    def __init__(self):
        super().__init__()
        self.is_voice_mode = False
        self.interpt = asyncio.Event()
        self.forbid_change = asyncio.Event()
        self.wait_for_get = asyncio.Event()
        self.asr_prepare=asyncio.Event()
        self.text = ""
        self.VL_models = ["Qwen2-VL-72B"]
        
        self.main_stack = QStackedLayout(self)
        self.setStyleSheet("background-color: #1a1d22;")

        self.chat_input = MultimodalEdit() 
        self.chat_input.installEventFilter(self)

        self.preview_scroll = QScrollArea()
        self.preview_scroll.setFixedHeight(90)
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preview_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preview_scroll.setStyleSheet("background: #16191d; border: none; border-bottom: 1px solid #2c313c;")
        self.preview_scroll.hide() 

        self.preview_content = QFrame()
        self.preview_layout = QHBoxLayout(self.preview_content)
        self.preview_layout.setContentsMargins(10, 10, 10, 10)
        self.preview_layout.setSpacing(10)
        self.preview_layout.addStretch() 
        self.preview_scroll.setWidget(self.preview_content)
        
        self.chat_input.preview_layout = self.preview_layout
        self.chat_input.preview_container = self.preview_scroll

        self.toggle_ex_btn = HoverButton("＋")
        self.toggle_ex_btn.setFixedSize(36, 36)
        self.update_ex_btn_style() 
        self.toggle_ex_btn.hovered.connect(self.on_btn_hovered)
        self.toggle_ex_btn.clicked.connect(self.on_ex_btn_clicked)

        self.live2d_view = QWebEngineView()
        self.live2d_view.page().setBackgroundColor(QColor("#050505"))
        self.live2d_page = CustomPage(self.live2d_view)
        self.live2d_view.setPage(self.live2d_page)
        self.live2d_view.setUrl(QUrl("http://localhost:5173")) 
        self.live2d_view.setStyleSheet("background: transparent;")

        self.setup_page1() 
        self.setup_page2() 
        self.init_floating_panel()
        self.pattern=None

    def setup_page1(self):
        self.page1 = QWidget()
        layout = QVBoxLayout(self.page1)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.v_splitter = QSplitter(Qt.Vertical)
        self.v_splitter.setHandleWidth(1)
        self.v_splitter.setStyleSheet("QSplitter::handle { background: #2c313c; }")

        self.unity_area = QFrame()
        self.unity_area.setStyleSheet("background-color: #050505; border: none;")

        self.u_layout = QVBoxLayout(self.unity_area)
        self.u_layout.setContentsMargins(0, 0, 0, 0) 

        self.u_layout.addWidget(self.live2d_view) 

        self.input_container = QFrame()
        self.input_container.setStyleSheet("background-color: #1d2127; border-top: 1px solid #2c313c;")
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
        self.h_splitter.setStyleSheet("QSplitter::handle { background: #2c313c; }")

        self.p2_left_area = QFrame() 
        self.p2_left_area.setStyleSheet("background: #050505; border: none;")
        self.p2_u_layout = QVBoxLayout(self.p2_left_area)
        self.p2_u_layout.setContentsMargins(0, 0, 0, 0)

        right_panel = QFrame()
        right_panel.setStyleSheet("background: #1d2127; border-left: 1px solid #2c313c;")
        rv = QVBoxLayout(right_panel)
        rv.setContentsMargins(0, 0, 0, 0)

        self.history_area = QScrollArea()
        self.history_area.setStyleSheet("background: transparent; border: none;")

        self.p2_input_box = QFrame()
        self.p2_input_box.setFixedHeight(85)
        self.p2_v_lay = QVBoxLayout(self.p2_input_box)
        self.p2_v_lay.setContentsMargins(0, 0, 0, 0)

        self.p2_h_row = QHBoxLayout() 
        self.p2_h_row.setContentsMargins(10, 5, 10, 10)
        self.p2_h_row.setSpacing(10)
        self.p2_v_lay.addLayout(self.p2_h_row) 

        rv.addWidget(self.history_area)
        rv.addWidget(self.p2_input_box)

        self.h_splitter.addWidget(self.p2_left_area)
        self.h_splitter.addWidget(right_panel)
        lay.addWidget(self.h_splitter)
        self.main_stack.addWidget(self.page2)

    def init_floating_panel(self):
        self.floating_panel = QFrame(self)
        self.floating_panel.setFixedSize(135, 50)
        self.floating_panel.setStyleSheet("background: #2c313c; border: 1px solid #4e5565; border-radius: 10px;")
        fl = QHBoxLayout(self.floating_panel); fl.setContentsMargins(5,5,5,5)

        self.mode_btn = QPushButton("🎤", self.floating_panel) 
        self.mode_btn.clicked.connect(self.toggle_mode)

        btn_file = QPushButton("📁", self.floating_panel)
        btn_file.clicked.connect(self.upload_image_dialog)
        
        btn_sw = QPushButton("⇌", self.floating_panel)
        btn_sw.clicked.connect(self.toggle_layout)

        for b in [btn_file, self.mode_btn, btn_sw]:
            b.setFixedSize(32, 32)
            b.setStyleSheet("background: #3e4451; color: white; border-radius: 6px; border: none;")
            fl.addWidget(b)
        
        self.floating_panel.hide()
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.floating_panel.hide)
        self.floating_panel.enterEvent = lambda e: self.hide_timer.stop()
        self.floating_panel.leaveEvent = lambda e: self.hide_timer.start(300)

    def update_ui_state(self):
        if self.is_voice_mode and not self.asr_prepare.is_set():return

        icon = "⌨️" if self.is_voice_mode else "🎤"
        self.mode_btn.setText(icon)
        self.mode_btn.setStyleSheet("background: #3e4451; color: white; border-radius: 6px; border: none;")

    def update_ex_btn_style(self):
        if self.forbid_change.is_set():
            self.toggle_ex_btn.setText("⏹️")
            self.toggle_ex_btn.setStyleSheet("background: #ff5555; color: white; border-radius: 18px; border: 1px solid #ff8888; font-size: 14px;")
        elif not self.forbid_change.is_set():
            self.toggle_ex_btn.setText("＋")
            self.toggle_ex_btn.setStyleSheet("QPushButton { background: #3e4451; color: white; border-radius: 18px; border: 1px solid #565f73; font-size: 20px; } QPushButton:hover { background: #4e5565; border-color: #87CEFA; }")

    def on_ex_btn_clicked(self):
        if self.forbid_change.is_set():
            self.interpt.set()
            self.notify("操作已中止", "warn")
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

            self.live2d_view.page().runJavaScript(f"window.resizeModel({offset_y});")

        else:
            self.u_layout.addWidget(self.live2d_view)
            self.v_input_layout.insertWidget(0, self.preview_scroll)
            self.h_layout.addWidget(self.chat_input)                
            self.h_layout.addWidget(self.toggle_ex_btn)

            self.live2d_view.page().runJavaScript(f"window.resizeModel({0});")

        self.main_stack.setCurrentIndex(new_idx)
        self.floating_panel.hide()

        if new_idx == 1: 
            QTimer.singleShot(20, lambda: self.h_splitter.setSizes([int(self.width()*0.75), int(self.width()*0.25)]))
        else:
            QTimer.singleShot(20, lambda: self.v_splitter.setSizes([self.height()-120, 120]))

    def is_port_open(self,port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0

    async def start_live2d_render(self):
        if not self.is_port_open(5173):
            logger.info("🌐 检测到服务器未启动，正在自动运行 npm run dev...")
            self.web_server_process = QProcess(self)
            self.web_server_process.setWorkingDirectory("live2d")
            self.web_server_process.start("cmd", ["/c", "npm run dev"])

            ready = False
            for _ in range(20):
                try:
                    conn = http.client.HTTPConnection("localhost", 5173, timeout=1)
                    conn.request("GET", "/")
                    resp = conn.getresponse()
                    if resp.status == 200:
                        ready = True
                        conn.close()
                        break
                except:
                    pass
                await asyncio.sleep(1)
                logger.info("⏳ 等待前端页面渲染响应中...")
        else:
            logger.info("✅ 发现已有运行中的服务器，跳过启动步骤")
            self.live2d_view.setUrl(QUrl("http://localhost:5173"))
            logger.info("✅ liv2d加载成功")

    def send_message(self):
        if self.is_voice_mode:
            return
        if self.forbid_change.is_set():
            return
        if self.wait_for_get.is_set():
            return

        content = self.chat_input.toPlainText().strip()
        images = list(self.chat_input.image_data_list) 

        if content or images:
            try:
                self.text = content
                self.current_images = images

                self.chat_input.clear_all() 
                self.chat_input.setFocus()

                self.wait_for_get.set() 

            except Exception as e:
                import traceback
                traceback.print_exc()

    @asyncSlot()
    async def toggle_mode(self):
        if self.forbid_change.is_set():
            self.interpt.set()
        
        self.is_voice_mode = not self.is_voice_mode
        if hasattr(self, 'asr_prepare'): await self.asr_prepare.wait()
        await self._update_ui_state()
        
        if self.is_voice_mode:
            self.chat_input.setReadOnly(True); self.chat_input.setPlainText("语音识别模式: 准备就绪，请说话...")
            self.chat_input.setStyleSheet(self.chat_input.styleSheet().replace("color: white;", "color: #87CEFA;"))
        else:
            self.chat_input.setReadOnly(False); self.chat_input.clear()
            self.chat_input.setStyleSheet(self.chat_input.styleSheet().replace("color: #87CEFA;", "color: white;"))

    def eventFilter(self, obj, event):
        if obj is self.chat_input and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ControlModifier:
                    self.chat_input.insertPlainText("\n")
                    return True 

                if not self.forbid_change.is_set() and not self.wait_for_get.is_set():
                    self.send_message()
                    return True
                else:
                    return True 
        return super().eventFilter(obj, event)

    def on_btn_hovered(self, is_hover):
        if self.forbid_change.is_set():
            self.floating_panel.hide()
            return

        if is_hover:
            self.update_ex_btn_style()
            
            btn_pos = self.toggle_ex_btn.mapTo(self, QPoint(0, 0))
            self.floating_panel.move(btn_pos.x() - 100, btn_pos.y() - 55)
            self.floating_panel.show()
            self.floating_panel.raise_()
        else:
            self.hide_timer.start(300)

    def upload_image_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择图片", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif)")
        if path: self.chat_input.insert_image(path)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(50, lambda: self.v_splitter.setSizes([self.height()-100, 100]))

    def notify(self, message, level="info"):
        colors = {"info": "#87CEFA", "warn": "#ffb86c", "error": "#ff5555"}
        if hasattr(self, 'ToastNotification'): 
            ToastNotification(self, message, colors.get(level, "#87CEFA"))

# =================================LogPage=============================================

class LogPage(BasePage):
    def __init__(self):
        super().__init__("SYSTEM LOGS", "支持多窗口对齐查看与实时跟踪")
        self.layout.setContentsMargins(15, 10, 15, 0) 
        self.log_dir = r"D:\filedir\github\my\TTS\log"
        self.viewers = [] 
        self.floating_log_win = None

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
        
        self.float_log_btn = QPushButton("弹出监控 ↗")
        self.float_log_btn.setStyleSheet(btn_style.replace("#343b48", "#bd93f9")) 
        
        self.add_view_btn = QPushButton("添加分屏 +")
        self.del_view_btn = QPushButton("移除分屏 -")
        
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
        self.splitter.setStyleSheet("QSplitter::handle { background: #3e4451; width: 1px; }")
        self.container_layout.addWidget(self.splitter)

        self.add_view_btn.clicked.connect(self.add_viewer)
        self.del_view_btn.clicked.connect(self.remove_viewer)
        self.float_log_btn.clicked.connect(self.open_floating_log)

        self.log_task = None
        self.add_viewer()

    def showEvent(self, event):
        """进入页面时启动监控"""
        super().showEvent(event)
        if self.log_task is None or self.log_task.done():
            self.log_task = asyncio.create_task(self.update_logs_loop())

    def hideEvent(self, event):
        """离开页面时停止监控"""
        super().hideEvent(event)
        if self.log_task:
            self.log_task.cancel()
            self.log_task = None

    def open_floating_log(self):
        """打开或显示已有的弹出窗口"""
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
                self.logger.info(f"日志更新出错: {e}")
                await asyncio.sleep(5)

    async def refresh_all_viewers(self):
        """遍历所有分屏并更新"""
        tasks = []
        for viewer in list(self.viewers):
            selector = viewer.findChild(QComboBox)
            display = viewer.findChild(QTextEdit)
            if selector and display:
                filename = selector.currentText()
                if filename and filename != "目录不存在":
                    tasks.append(self.load_log_async(filename, display))
        
        if tasks:
            await asyncio.gather(*tasks)

    @asyncSlot()
    async def load_log_async(self, filename, display_widget):
        """高效读取文件并更新 UI"""
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
            self.logger.info(f"文件读取出错({filename}): {e}")

    def add_viewer(self):
        if len(self.viewers) >= 3:
            return

        viewer_widget = QWidget()
        v_layout = QVBoxLayout(viewer_widget)
        v_layout.setContentsMargins(0, 5, 0, 0)

        file_selector = QComboBox()
        file_selector.setStyleSheet("""
            QComboBox { background: #1d2127; border: 1px solid #2c313c; padding: 5px; color: #87CEFA; }
            QComboBox QAbstractItemView { background: #1d2127; selection-background-color: #bd93f9; color: white; }
        """)
        self.refresh_files(file_selector)
        
        display = QTextEdit()
        display.setReadOnly(True)
        display.setStyleSheet("""
            QTextEdit {
                background-color: #16191d; color: #abb2bf; font-family: 'Consolas', 'Monaco';
                border: 1px solid #2c313c; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;
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
            combo_box.addItem("目录不存在")

# =============================MonitorPage=============================================

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
        self.mem_data = self.add_monitor_item("RAM 内存占用", grid)
        self.gpu_data = self.add_monitor_item("GPU 显存占用", grid)
        
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
        if not self.floating_win: self.floating_win = FloatingMonitor()
        self.floating_win.show()

    async def update_stats(self):
        while True:
            try:
                main_active = False
                try:
                    main_active = self.window().stackedWidget.currentWidget() == self
                except: pass
                
                float_active = self.floating_win and self.floating_win.isVisible()
                
                if main_active or float_active:
                    cpu = psutil.cpu_percent()
                    mem = psutil.virtual_memory().percent
                    gpu_percent = 0
                    if self.gpu_enabled:
                        try:
                            info = pynvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
                            gpu_percent = (info.used / info.total) * 100
                        except: pass

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
                
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.info(f"性能监视出错: {e}")
                await asyncio.sleep(1)

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
            try: pynvml.nvmlShutdown()
            except: pass

# ================================SettingPage=============================================

class SettingPage(BasePage):
    def __init__(self):
        super().__init__("SETTINGS", "系统参数配置")
        
        self.config_path = "config/config.json"
        
        self.SiliconCloud_model = SiliconCloud_model

        self.config = {
            "api_key": "",
            "model_name": SiliconCloud_model["DeepSeek-V3"],
            "silence_threshold": 1.0,
            "volume": 0.8,
            "asr_mode": "in"
        }
        
        self.load_config_from_file()
        self.setup_setting_ui()
        self.apply_config_to_ui()

    def showEvent(self, event: QShowEvent):
        """每次切回设置页面时，强制从文件同步，丢弃未保存的临时改动"""
        super().showEvent(event)
        self.load_config_from_file()
        self.apply_config_to_ui()

    def setup_setting_ui(self):
        """构建 UI 布局"""
        self.container_layout.setSpacing(12)
        self.container_layout.setContentsMargins(10, 5, 10, 5)

        self.api_input = QLineEdit()
        self.api_input.setEchoMode(QLineEdit.Password)
        self.api_input.setObjectName("settingInput")
        self.api_input.setPlaceholderText("填入 API Key...")
        self.create_row("API 密钥", "修改密钥后需重启程序以重新初始化服务", self.api_input)

        self.asr_combo = QComboBox()
        self.asr_combo.addItems(["in", "out"])
        self.asr_combo.setObjectName("settingCombo")
        self.create_row("识别模式", "in: 录制系统内部声音 | out: 录制麦克风声音", self.asr_combo)

        self.model_select = QComboBox()
        self.model_select.addItems(list(self.SiliconCloud_model.keys()))
        self.model_select.setObjectName("settingCombo")
        self.create_row("思维核心", "选择当前对话使用的云端大模型", self.model_select)

        self.t_slider = QSlider(Qt.Horizontal)
        self.t_slider.setRange(5, 30)
        self.t_label = QLabel("1.0s")
        self.t_label.setFixedWidth(45)
        self.t_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        t_layout = QHBoxLayout()
        t_layout.addWidget(self.t_slider)
        t_layout.addWidget(self.t_label)
        self.create_row("听力感度", "检测到停顿多久后开始响应(秒)", t_layout)
        self.t_slider.valueChanged.connect(lambda v: self.t_label.setText(f"{v/10.0}s"))

        self.v_slider = QSlider(Qt.Horizontal)
        self.v_slider.setRange(0, 100)
        self.v_label = QLabel("80%")
        self.v_label.setFixedWidth(45)
        self.v_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        v_layout = QHBoxLayout()
        v_layout.addWidget(self.v_slider)
        v_layout.addWidget(self.v_label)
        self.create_row("输出音量", "调整 agent 说话的声音大小", v_layout)
        self.v_slider.valueChanged.connect(lambda v: self.v_label.setText(f"{v}%"))

        self.container_layout.addSpacing(15)
        btn_container = QHBoxLayout()
        btn_container.addStretch()
        
        self.save_btn = QPushButton("保存设置")
        self.save_btn.setFixedSize(110, 32)
        self.save_btn.setObjectName("saveButton")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self.do_save_logic)
        
        btn_container.addWidget(self.save_btn)
        self.container_layout.addLayout(btn_container)

        self.container_layout.addStretch()

        self.setStyleSheet("""
            #settingInput, #settingCombo {
                background: #1a1d22;
                color: #e0e0e0;
                border: 1px solid #3d444d;
                border-radius: 4px;
                padding: 4px;
            }
            #saveButton {
                background: transparent;
                color: #bd93f9;
                border: 1px solid #bd93f9;
                border-radius: 4px;
                font-weight: bold;
            }
            #saveButton:hover { background: rgba(189, 147, 249, 0.1); }
            #saveButton:pressed { background: rgba(189, 147, 249, 0.2); }
            QSlider::groove:horizontal { height: 4px; background: #3d444d; border-radius: 2px; }
            QSlider::handle:horizontal { background: #bd93f9; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }
        """)

    def create_row(self, title, desc, content):
        """每一行设置项的容器封装"""
        card = QFrame()
        card.setObjectName("SettingCard")
        card.setStyleSheet("#SettingCard { background: rgba(30, 34, 39, 200); border: 1px solid #2d323b; border-radius: 10px; }")
        
        row_layout = QHBoxLayout(card)
        row_layout.setContentsMargins(15, 10, 15, 10)

        text_widget = QWidget()
        text_layout = QVBoxLayout(text_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("color: #bd93f9; font-weight: bold; font-size: 14px; background:transparent;")
        d_lbl = QLabel(desc)
        d_lbl.setStyleSheet("color: #717e95; font-size: 11px; background:transparent;")
        
        text_layout.addWidget(t_lbl)
        text_layout.addWidget(d_lbl)
        
        row_layout.addWidget(text_widget, 4)
        row_layout.addStretch(1)
        
        if isinstance(content, QHBoxLayout):
            row_layout.addLayout(content, 3)
        else:
            content.setFixedWidth(220)
            row_layout.addWidget(content, 3)
        
        self.container_layout.addWidget(card)

    def load_config_from_file(self):
        if os.path.exists(self.config_path):
            try:
                key=self.config["api_key"]
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config.update(json.load(f))
                if key:self.config["api_key"]=key
                self.config["model_name"]=SiliconCloud_model[self.config["model_name"]]
            except: pass

    def apply_config_to_ui(self):
        stored_model = self.config.get("model_name", "DeepSeek-V3")
        display_name = stored_model 
        for name, full_path in self.SiliconCloud_model.items():
            if full_path == stored_model:
                display_name = name
                break
        self.model_select.setCurrentText(display_name)
        self.api_input.setText(self.config.get("api_key", ""))
        self.asr_combo.setCurrentText(self.config.get("asr_mode", "in"))
        threshold = self.config.get("silence_threshold", 1.0)
        self.t_slider.setValue(int(threshold * 10))
        self.t_label.setText(f"{float(threshold):.1f}s")
        vol = self.config.get("volume", 0.8)
        self.v_slider.setValue(int(vol * 100))
        self.v_label.setText(f"{int(vol * 100)}%")

    def do_save_logic(self):
        old_api = self.config.get("api_key", "")
        old_asr = self.config.get("asr_mode", "in")

        new_api = self.api_input.text()
        new_asr = self.asr_combo.currentText()

        need_restart = (new_api != old_api) or (new_asr != old_asr)

        if need_restart:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("核心参数变更")
            msg_box.setText("检测到 API 密钥或识别模式变动，这需要重启核心服务。\n是否应用更改？")

            yes_btn = msg_box.addButton("立即重载", QMessageBox.YesRole)
            no_btn = msg_box.addButton("取消修改", QMessageBox.NoRole)
            msg_box.setDefaultButton(yes_btn)

            msg_box.setStyleSheet(f"""
                QMessageBox {{
                    background-color: #1d2127;
                    border: 1px solid #87CEFA;
                }}
                QLabel {{
                    color: #ffffff;
                    font-family: 'Microsoft YaHei';
                    padding: 10px;
                    min-width: 300px;
                }}
                QPushButton {{
                    border: 1px solid #87CEFA;
                    border-radius: 3px;
                    padding: 5px 15px;
                    background: transparent;
                    color: #87CEFA;
                    font-family: 'Microsoft YaHei';
                    min-width: 80px;
                }}
                QPushButton:hover {{
                    background-color: rgba(135, 206, 250, 0.1);
                }}
                QPushButton:pressed {{
                    background-color: rgba(135, 206, 250, 0.2);
                }}
            """)

            no_btn.setStyleSheet("color: #888888; border-color: #444444;")

            msg_box.exec()

            if msg_box.clickedButton() == no_btn:
                self.api_input.setText(old_api)
                self.asr_combo.setCurrentText(old_asr)
                self.notify("操作已取消", "warn")
                return 

        self.config["api_key"] = new_api
        self.config["asr_mode"] = new_asr
        self.config["model_name"] = self.model_select.currentText()
        self.config["silence_threshold"] = self.t_slider.value() / 10.0
        self.config["volume"] = self.v_slider.value() / 100.0

        clean_config = copy.deepcopy(self.config)

        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(clean_config, f, indent=4, ensure_ascii=False)

            main_win = self.window()
            if hasattr(main_win, 'flags'):
                main_win.flags.update(self.config)

            self.notify("设置保存成功", "info")
        except Exception as e:
            self.notify(f"保存异常: {str(e)}", "error")

    def notify(self, message, level="info"):
        """
        level: info (蓝色), warn (橙色), error (红色)
        """
        colors = {
            "info": "#87CEFA",
            "warn": "#ffb86c",
            "error": "#ff5555"
        }
        ToastNotification(self, message, colors.get(level, "#87CEFA"))

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

class FloatingLogMonitor(QWidget):
    def __init__(self, log_dir):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("实时日志监控")
        self.resize(700, 450)
        self.log_dir = log_dir
        self.setStyleSheet("background-color: #16191d; color: #dcdcdc;")
        
        layout = QVBoxLayout(self)
        
        top_bar = QHBoxLayout()
        self.file_selector = QComboBox()
        self.file_selector.setStyleSheet("""
            QComboBox { background: #1d2127; border: 1px solid #2c313c; padding: 5px; color: #87CEFA; }
        """)
        self.refresh_files()
        
        top_bar.addWidget(QLabel("选择日志:"))
        top_bar.addWidget(self.file_selector)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        self.display = QTextEdit()
        self.display.setReadOnly(True)
        self.display.setStyleSheet("""
            QTextEdit {
                background-color: #050505; color: #abb2bf; 
                font-family: 'Consolas', 'Monaco'; font-size: 12px;
                border: 1px solid #2c313c;
            }
        """)
        layout.addWidget(self.display)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_log_content)
        self.timer.start(1000)

    def refresh_files(self):
        if os.path.exists(self.log_dir):
            files = [f for f in os.listdir(self.log_dir) if f.endswith(('.log', '.txt'))]
            files.sort(reverse=True)
            self.file_selector.addItems(files)
            if "speech.log" in files:
                self.file_selector.setCurrentText("speech.log")

    def update_log_content(self):
        filename = self.file_selector.currentText()
        if not filename: return
        
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
            except: pass

class MemoryPage(BasePage):
    def __init__(self):
        super().__init__("MEMORY CORE", "系统长期记忆图谱 - 仅限浏览模式")
        self.layout.setContentsMargins(25, 20, 25, 15)
        self.memory_manager = None
        
        sub_title_label = self.layout.itemAt(1).widget()
        self.header_row = QHBoxLayout()
        self.header_row.addWidget(sub_title_label)
        self.header_row.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(" 🔍 搜索关键词...")
        self.search_input.setFixedWidth(240)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: #1d2127; border: 1px solid #3e4451;
                border-radius: 15px; padding: 6px 15px; color: #dcdcdc;
            }
            QLineEdit:focus { border: 1px solid #87CEFA; background: #232830; }
        """)
        self.search_input.textChanged.connect(self.search_tree)

        self.edit_mode_btn = QPushButton("记忆图谱界面 ↗")
        self.edit_mode_btn.setFixedSize(140, 34)
        self.edit_mode_btn.setCursor(Qt.PointingHandCursor)
        self.edit_mode_btn.setStyleSheet("""
            QPushButton { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6272a4, stop:1 #bd93f9); 
                border-radius: 17px; /* 全圆角 */
                color: white; font-size: 12px; font-weight: bold; border: none;
            } 
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7283b5, stop:1 #caabf1); }
        """)
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(189, 147, 249, 80))
        shadow.setOffset(0, 4)
        self.edit_mode_btn.setGraphicsEffect(shadow)

        self.header_row.addWidget(self.search_input)
        self.header_row.addSpacing(15)
        self.header_row.addWidget(self.edit_mode_btn)
        self.layout.insertLayout(1, self.header_row)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(1)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(20)
        self.tree.setAnimated(True)
        
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: #16191d; color: #abb2bf;
                border: 1px solid #2d323b; border-radius: 12px;
                padding: 10px; outline: none; font-size: 13px;
            }
            QTreeWidget::item { 
                padding: 12px 5px; border-bottom: 1px solid #1d2127; 
            }
            QTreeWidget::item:hover { background-color: rgba(255, 255, 255, 0.05); }
            QTreeWidget::item:selected { background-color: #2c313c; color: #87CEFA; }
            
            /* 自定义展开箭头颜色 */
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {
                border-image: none;
                image: none; /* 强制不显示默认图标 */
            }
        """)
        
        self.container_layout.addWidget(self.tree)
        self.edit_mode_btn.clicked.connect(self.verify_and_open_editor)
        self.editor_window = None

    def load_graph(self):
        """加载优化后的 3D 悬浮感记忆星图"""
        config = {
            "serverUrl": "bolt://localhost:7687",
            "user": "neo4j",
            "pass": "12345678" 
        }

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <script src="https://unpkg.com/neovis.js@2.1.0/dist/neovis.js"></script>
            <style>
                /* 全局样式：对齐主 UI 科技感 */
                body {{ 
                    background-color: #16191d; 
                    margin: 0; 
                    overflow: hidden; 
                    font-family: 'Segoe UI', 'PingFang SC', sans-serif; 
                }}
                
                #viz {{ 
                    width: 100vw; 
                    height: 100vh; 
                    position: absolute; 
                }}

                /* 右侧悬浮面板：更轻量、半透明 */
                #info-panel {{
                    position: absolute;
                    right: -320px; 
                    top: 15px;
                    width: 280px;
                    height: calc(100% - 30px);
                    background: rgba(22, 25, 29, 0.85);
                    backdrop-filter: blur(10px); /* 磨砂玻璃 */
                    border: 1px solid rgba(135, 206, 250, 0.2);
                    border-radius: 15px;
                    color: #abb2bf;
                    padding: 18px;
                    transition: all 0.5s cubic-bezier(0.19, 1, 0.22, 1);
                    z-index: 1000;
                    overflow-y: auto;
                    box-shadow: -10px 0 30px rgba(0,0,0,0.3);
                }}
                #info-panel.active {{ right: 15px; }}

                .close-btn {{ 
                    float: right; cursor: pointer; color: #87CEFA; font-size: 18px; 
                }}
                .title {{ 
                    color: #87CEFA; font-size: 14px; font-weight: bold; 
                    letter-spacing: 1px; margin-bottom: 15px; 
                }}
                .summary-box {{ 
                    background: rgba(255, 255, 255, 0.05); 
                    padding: 12px; border-radius: 8px; 
                    font-size: 13px; line-height: 1.5; color: #dcdcdc;
                    margin-bottom: 15px; border-left: 3px solid #87CEFA;
                }}
                .qa-card {{ 
                    background: rgba(135, 206, 250, 0.03);
                    border-radius: 6px; padding: 10px; margin-bottom: 10px;
                }}
                .qa-q {{ color: #87CEFA; font-size: 12px; font-weight: bold; }}
                .qa-a {{ color: #abb2bf; font-size: 12px; margin-top: 5px; }}
                
                /* 滚动条美化 */
                ::-webkit-scrollbar {{ width: 4px; }}
                ::-webkit-scrollbar-thumb {{ background: #2d323b; border-radius: 10px; }}
            </style>
        </head>
        <body onload="init()">
            <div id="viz"></div>
            
            <div id="info-panel" id="panel">
                <span class="close-btn" onclick="togglePanel(false)">×</span>
                <div class="title">⚡ MEMORY FRAGMENT</div>
                <div id="summary" class="summary-box">点击星尘节点...</div>
                <div class="title" style="font-size: 11px; opacity: 0.7;">ROOT QA TRACE</div>
                <div id="qa-list"></div>
            </div>

            <script>
                let viz;
                
                function togglePanel(show) {{
                    document.getElementById('info-panel').classList.toggle('active', show);
                }}

                function init() {{
                    // 延迟加载确保脚本就绪，防止卡死
                    if (window.NeoVis) {{ draw(); }} 
                    else {{ setTimeout(init, 200); }}
                }}

                function draw() {{
                    const config = {{
                        containerId: "viz",
                        neo4j: {{
                            serverUrl: "{config['serverUrl']}",
                            serverUser: "{config['user']}",
                            serverPassword: "{config['pass']}"
                        }},
                        labels: {{
                            "MemoryNode": {{
                                label: "display",
                                font: {{ size: 12, color: "#87CEFA" }},
                                size: 18,
                                color: "#1d2127",
                                borderWidth: 2,
                                borderColor: "#87CEFA"
                            }}
                        }},
                        // 性能优化：限制初始加载并关闭复杂层级布局
                        initialCypher: "MATCH (n:MemoryNode) RETURN n LIMIT 25",
                        simulation: {{
                            enabled: true,
                            friction: 0.9,
                            forceManyBody: {{ strength: -100 }}
                        }}
                    }};

                    viz = new NeoVis.default(config);
                    viz.render();

                    viz.registerOnEvent("clickNode", (e) => {{
                        const p = e.node.properties;
                        togglePanel(true);
                        
                        document.getElementById('summary').innerText = p.full_summary || "Memory trace corrupted.";
                        
                        const list = document.getElementById('qa-list');
                        list.innerHTML = "";
                        try {{
                            const qas = JSON.parse(p.qa_json || "[]");
                            qas.forEach(item => {{
                                const div = document.createElement('div');
                                div.className = "qa-card";
                                div.innerHTML = `<div class="qa-q">Q: ${{item.Q || item.q}}</div><div class="qa-a">A: ${{item.A || item.a}}</div>`;
                                list.appendChild(div);
                            }});
                        }} catch(err) {{
                            list.innerHTML = "No QA data available.";
                        }}
                    }});
                }}
            </script>
        </body>
        </html>
        """
        self.browser.setHtml(html_content)

    async def load_memory_tree(self):
        self.tree.setWordWrap(True)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.tree.setEditTriggers(self.tree.EditTrigger.NoEditTriggers)
        self.tree.setIndentation(25) 
        self.tree.header().setSectionResizeMode(0, self.tree.header().ResizeMode.Stretch)
        
        try:
            self.tree.itemClicked.disconnect() 
        except: pass
        self.tree.itemClicked.connect(lambda item: item.setExpanded(not item.isExpanded()))

        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: #16191d; 
                color: #dcdcdc;
                border: 1px solid #2d323b; 
                border-radius: 12px;
                outline: none;
                padding: 8px;
                font-family: 'Segoe UI', 'PingFang SC', sans-serif;
            }
            /* 父节点：增加模糊边框效果 */
            QTreeWidget::item { 
                padding: 12px; 
                margin-bottom: 8px;
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(135, 206, 250, 0.2); /* 淡淡的蓝色边框 */
                border-radius: 8px;
                min-height: 40px; 
            }
            /* 子节点：去掉边框，保持简洁 */
            QTreeWidget::item:child {
                padding: 10px 15px;
                margin-bottom: 0px;
                background-color: rgba(135, 206, 250, 0.05);
                border: none;
                border-left: 2px solid rgba(135, 206, 250, 0.3); /* 左侧装饰线 */
                border-radius: 0px;
                color: #abb2bf;
            }
            QTreeWidget::item:hover { 
                background-color: rgba(135, 206, 250, 0.1);
                border: 1px solid rgba(135, 206, 250, 0.5); 
            }
            QTreeWidget::item:selected { 
                background-color: rgba(135, 206, 250, 0.2); 
                color: #87CEFA; 
                border: 1px solid #87CEFA;
            }
            QTreeWidget::branch { image: none; } 
        """)

        self.tree.clear()
        
        try:
            memories = await self.memory_manager.show_memories(_print=False)
            if not memories:
                self.tree.addTopLevelItem(QTreeWidgetItem(self.tree, ["📭 暂无长期记忆数据"]))
                return

            for m in memories:
                raw_text = m.get("text", "无内容")
                node_id = m.get("id", "")
                qa_list = m.get("QA", [])
                
                tree_item = QTreeWidgetItem(self.tree, [f"📝 {raw_text}"])
                main_font = QFont("Segoe UI", 10)
                main_font.setBold(True)
                tree_item.setFont(0, main_font)
                
                tree_item.setFlags(tree_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                tree_item.setData(0, Qt.ItemDataRole.UserRole, node_id)

                for qa in qa_list:
                    if isinstance(qa, dict):
                        q_text = qa.get("Q") or qa.get("q") or "未记录详情"
                        a_text = qa.get("A") or qa.get("a") or ""
                        display_qa = f"Q: {q_text}\nA: {a_text}" if a_text else f"Q: {q_text}"
                    else:
                        display_qa = str(qa)
                        
                    qa_item = QTreeWidgetItem(tree_item, [display_qa])
                    sub_font = QFont("Consolas", 9)
                    qa_item.setFont(0, sub_font)
                    qa_item.setForeground(0, QColor("#87CEFA"))
                
                self.tree.addTopLevelItem(tree_item)
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.logger.info(f"❌ 加载记忆树失败: {e}")

    def showEvent(self, event):
        super().showEvent(event)
        asyncio.ensure_future(self.load_memory_tree())
        
    def search_tree(self, text):
        items = self.tree.findItems(text, Qt.MatchContains | Qt.MatchRecursive)
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setHidden(True)
        for item in items:
            item.setHidden(False)
            p = item.parent()
            while p: p.setHidden(False); p.setExpanded(True); p = p.parent()

    def verify_and_open_editor(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("权限验证")
        dialog.setFixedWidth(350)
        dialog.setStyleSheet("""
            QDialog { background-color: #1d2127; border: 1px solid #87CEFA; }
            QLabel { color: #ffffff; font-family: 'Microsoft YaHei'; }
            QLineEdit { background: #16191d; color: white; border: 1px solid #444444; padding: 5px; }
            QPushButton { 
                border: 1px solid #87CEFA; border-radius: 3px; padding: 5px 15px;
                background: transparent; color: #87CEFA; min-width: 80px;
            }
            QPushButton:hover { background-color: rgba(135, 206, 250, 0.1); }
        """)

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("进入管理界面需要管理员权限："))

        pwd_input = QLineEdit()
        pwd_input.setEchoMode(QLineEdit.Password)
        pwd_input.setPlaceholderText("请输入管理密码...")
        layout.addWidget(pwd_input)

        btn_layout = QHBoxLayout()
        yes_btn = QPushButton("确认进入")
        no_btn = QPushButton("取消")
        btn_layout.addWidget(no_btn)
        btn_layout.addWidget(yes_btn)
        layout.addLayout(btn_layout)

        yes_btn.clicked.connect(dialog.accept)
        no_btn.clicked.connect(dialog.reject)

        if dialog.exec() == QDialog.Accepted:
            if pwd_input.text() == "121176":
                self.open_editor()
            else:
                self.logger.info("密码错误") 
                if hasattr(self.window(), 'notify'):
                    self.window().notify("密码错误", "error")

    def open_editor(self):
        try:
            if self.editor_window is None:
                self.editor_window = MemoryEditorWindow(self.memory_manager)
            
            self.editor_window.setWindowFlags(Qt.Window | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
            self.editor_window.show()
            self.editor_window.raise_()
            self.editor_window.activateWindow()
            
            asyncio.create_task(self.editor_window.refresh_data())
        except Exception as e:
            self.logger.info(f"❌ 弹窗失败: {e}")
            self.editor_window = None 

class MemoryEditorWindow(QWidget):
    def __init__(self, memory_manager):
        super().__init__()
        self.memory_manager = memory_manager
        self.current_data = None
        self.pending_updates = {} 
        self.pending_deletes = set()
        
        self.setWindowTitle("MEMORY EDITOR - 核心记忆修正协议")
        self.resize(900, 650) 
        self.setWindowFlags(Qt.Window | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        
        self.init_ui()
        
    def init_ui(self):
        self.setStyleSheet("""
            QWidget { background-color: #16191d; color: #abb2bf; font-family: 'Segoe UI', 'Microsoft YaHei'; }
            QListWidget { background-color: #1d2127; border: 1px solid #2d323b; border-radius: 10px; outline: none; }
            QListWidget::item { padding: 12px; border-bottom: 1px solid #2d323b; color: #dcdcdc; }
            QListWidget::item:selected { background-color: #2c313c; border-left: 5px solid #bd93f9; color: #87CEFA; }
            QCheckBox { color: #6272a4; font-size: 11px; font-weight: bold; }
            QTextEdit { background: #16191d; border: 1px solid #3e4451; border-radius: 8px; padding: 10px; font-size: 13px; line-height: 1.4; }
            QLineEdit { background: #1d2127; border-radius: 15px; padding: 6px 12px; border: 1px solid #3e4451; }
            QPushButton#SaveBtn { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #bd93f9, stop:1 #ff79c6); color: white; padding: 10px 25px; border-radius: 18px; font-weight: bold; }
            QPushButton#DelBtn { color: #ff5555; border: 1px solid #ff5555; padding: 6px; border-radius: 6px; }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 10)

        header = QHBoxLayout()
        title_label = QLabel("🧠 核心事实编辑器")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #87CEFA;")
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(" 🔍 搜索记忆碎片...")
        self.search_bar.setFixedWidth(250)
        self.search_bar.textChanged.connect(self.filter_items)
        header.addWidget(title_label)
        header.addStretch()
        header.addWidget(self.search_bar)
        main_layout.addLayout(header)

        self.splitter = QSplitter(Qt.Horizontal)
        
        self.list_widget = QListWidget()
        self.list_widget.itemSelectionChanged.connect(self.on_selection_changed)
        
        self.edit_panel = QFrame()
        self.edit_panel.setStyleSheet("background: #1d2127; border-radius: 12px; border: 1px solid #2d323b;")
        panel_layout = QVBoxLayout(self.edit_panel)
        panel_layout.setContentsMargins(15, 15, 15, 15)

        fact_bar = QHBoxLayout()
        fact_bar.addWidget(QLabel("📝 事实陈述 (Node Text)"))
        self.fact_lock_cb = QCheckBox("开启编辑模式")
        self.fact_lock_cb.stateChanged.connect(self.toggle_fact_edit)
        fact_bar.addStretch()
        fact_bar.addWidget(self.fact_lock_cb)
        panel_layout.addLayout(fact_bar)
        
        self.text_editor = QTextEdit()
        self.text_editor.setReadOnly(True)
        self.text_editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding) 
        panel_layout.addWidget(self.text_editor)

        qa_bar = QHBoxLayout()
        qa_bar.addWidget(QLabel("📂 溯源素材 (Root QA Trace)"))
        self.qa_lock_cb = QCheckBox("编辑原始对话")
        self.qa_lock_cb.stateChanged.connect(self.toggle_qa_edit)
        qa_bar.addStretch()
        qa_bar.addWidget(self.qa_lock_cb)
        panel_layout.addLayout(qa_bar)

        self.qa_display = QTextEdit()
        self.qa_display.setReadOnly(True) 
        self.qa_display.setStyleSheet("color: #6272a4; background: #1a1d22;")
        self.qa_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        panel_layout.addWidget(self.qa_display)

        btn_layout = QHBoxLayout()
        self.del_btn = QPushButton(" 🗑 彻底遗忘 ")
        self.del_btn.setObjectName("DelBtn")
        self.del_btn.clicked.connect(self.delete_current_memory)
        self.save_btn = QPushButton(" ⚡ 暂存修改 ")
        self.save_btn.setObjectName("SaveBtn")
        self.save_btn.clicked.connect(self.save_to_cache)
        btn_layout.addWidget(self.del_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        panel_layout.addLayout(btn_layout)

        self.splitter.addWidget(self.list_widget)
        self.splitter.addWidget(self.edit_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)
        main_layout.addWidget(self.splitter)

        self.status_bar = QLabel("系统就绪 | 等待节点选择")
        self.status_bar.setStyleSheet("color: #6272a4; font-size: 11px; padding-top: 5px;")
        main_layout.addWidget(self.status_bar)

    def toggle_fact_edit(self, state):
        is_unlocked = (state == 2)
        self.text_editor.setReadOnly(not is_unlocked)
        self.text_editor.setStyleSheet(f"border: 1px solid {'#bd93f9' if is_unlocked else '#3e4451'};")

    def toggle_qa_edit(self, state):
        self.qa_display.setReadOnly(state != 2)

    def filter_items(self, text):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    async def refresh_data(self):
        try:
            self.status_bar.setText("⏳ 正在同步全量记忆...")
            self.list_widget.clear()
            memories = await self.memory_manager.show_memories(_print=False)
            if not memories:
                self.status_bar.setText("📭 记忆库为空")
                return
            for m in memories:
                m['_raw_text'] = m.get('text', '') 
                m['_raw_qa'] = list(m.get('QA', []))
                preview = m.get('text', 'Empty').replace('\n', ' ')
                item = QListWidgetItem(f"ID: {m['id'][:8]}... | {preview[:25]}...")
                item.setData(Qt.UserRole, m)
                self.list_widget.addItem(item)
            self.status_bar.setText(f"✅ 已加载 {len(memories)} 个节点")
        except Exception as e:
            self.status_bar.setText(f"❌ 加载失败: {str(e)}")

    def on_selection_changed(self):
        selected = self.list_widget.selectedItems()
        if not selected: return
        data = selected[0].data(Qt.UserRole)
        self.current_data = data
        self.text_editor.setPlainText(data.get('text', ''))
        qa_list = data.get('QA', [])
        self.qa_display.setPlainText("\n\n".join(qa_list) if qa_list else "无溯源素材")
        self.fact_lock_cb.setChecked(False)
        self.qa_lock_cb.setChecked(False)

    def save_to_cache(self):
        if not self.current_data: return
        node_id = self.current_data['id']
        new_text = self.text_editor.toPlainText().strip()
        new_qa = self.qa_display.toPlainText().split('\n\n')

        if new_text == self.current_data.get('_raw_text') and new_qa == self.current_data.get('_raw_qa'):
            self.status_bar.setText("ℹ️ 内容未变动")
            return

        self.current_data['text'] = new_text
        self.current_data['QA'] = new_qa
        self.pending_updates[node_id] = self.current_data
        
        selected_item = self.list_widget.selectedItems()[0]
        selected_item.setData(Qt.UserRole, self.current_data)
        selected_item.setForeground(QColor("#bd93f9"))
        self.status_bar.setText(f"✨ 节点 {node_id[:8]} 已暂存")

    def delete_current_memory(self):
        if not self.current_data: return
        node_id = self.current_data['id']
        if QMessageBox.question(self, "彻底遗忘", "确定删除该节点？") == QMessageBox.Yes:
            self.pending_deletes.add(node_id)
            self.list_widget.takeItem(self.list_widget.currentRow())
            self.text_editor.clear()
            self.current_data = None

    def closeEvent(self, event):
        if not self.pending_updates and not self.pending_deletes:
            event.accept()
            return
        reply = QMessageBox.question(self, '同步确认', "是否保存修改到数据库？", QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if reply == QMessageBox.Yes:
            asyncio.create_task(self._do_final_sync())
            event.accept()
        elif reply == QMessageBox.No:
            event.accept()
        else:
            event.ignore()

    async def _do_final_sync(self):
        try:
            if self.pending_deletes:
                await self.memory_manager.aclient.delete(
                    collection_name=self.memory_manager.collection_name, 
                    points_selector=list(self.pending_deletes)
                )

            if self.pending_updates:
                update_nodes = []
                for node_id, data in self.pending_updates.items():
                    new_vector = await self.memory_manager.api_embedding.start(content=data['text'])
                    
                    node = TextNode(
                        id_=node_id, 
                        text=data['text'], 
                        metadata={
                            "QA": data['QA'], 
                            "display_time": data['stime'].strftime("%Y-%m-%d %H:%M:%S"), 
                            "last_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                            "stimestamp": int(data['stime'].timestamp()), 
                            "etimestamp": int(datetime.now().timestamp())
                        }
                    )
                    
                    node.excluded_embed_metadata_keys = ["QA", "display_time", "last_time", "stimestamp", "etimestamp"]
                    
                    object.__setattr__(node, 'embedding', new_vector)
                    update_nodes.append(node)

                if update_nodes:
                    for n in update_nodes:
                        try:
                            self.memory_manager.index.docstore.delete_document(n.id_, raise_error=False)
                        except:
                            pass
                    await self.memory_manager.index.ainsert_nodes(update_nodes)

            self.pending_updates = {}
            self.pending_deletes = set()

        except Exception as e:
                print(f"❌ 同步失败: {e}")

class MyWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.resize(1200, 700)
        self.setMinimumSize(550, 350)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.sizegrip = QSizeGrip(self.frame_size_grip)
        self.sizegrip.setStyleSheet("width: 20px; height: 20px; margin: 0px; padding: 0px;")
        self.move(30, 30)
        self.dragPos = QPoint()

        self.btn_menu.overlay = ShimmerOverlay(self.btn_menu)
        self.btn_menu.clicked.connect(self.btn_menu.overlay.play)

        menu_btns = [self.btn_home, self.btn_chat, self.btn_setting, self.btn_monitor, self.btn_log,self.btn_memory]
        for i, btn in enumerate(menu_btns):
            btn.overlay = ShimmerOverlay(btn)
            btn.clicked.connect(lambda checked=False, b=btn, index=i: self.apply_blue_shimmer(b, index))

        self.page_home = HomePage()
        self.page_monitor = MonitorPage()
        self.page_log = LogPage()
        self.page_chat = ChatPage()
        self.page_setting = SettingPage()
        self.page_memory=MemoryPage()

        while self.stackedWidget.count() > 0:
            self.stackedWidget.removeWidget(self.stackedWidget.widget(0))

        self.stackedWidget.addWidget(self.page_home)    
        self.stackedWidget.addWidget(self.page_chat)    
        self.stackedWidget.addWidget(self.page_setting) 
        self.stackedWidget.addWidget(self.page_monitor) 
        self.stackedWidget.addWidget(self.page_log)
        self.stackedWidget.addWidget(self.page_memory)     

        self.stackedWidget.setCurrentIndex(0)

        self.closeAppBtn.clicked.connect(self._shutdown)
        self.maximizeRestoreAppBtn.clicked.connect(self.toggle_maximize)
        self.minimizeAppBtn.clicked.connect(self.showMinimized)

        self.notify("初始化成功")
        self.DOING=asyncio.Event()
        self.clear_up=asyncio.Event()
        self.prepare=asyncio.Event()

    @asyncSlot()
    async def _shutdown(self):
        self.hide()
        self.DOING.set()
        if hasattr(self, 'web_server_process'):
            logger.info("🔪 正在关闭后台 Node 服务器...")
            self.web_server_process.terminate()
            if not self.web_server_process.waitForFinished(1000): # 如果 1 秒没关掉
                self.web_server_process.kill()
        await self.clear_up.wait()
        self.close()
        loop=asyncio.get_event_loop()
        loop.stop()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.contentTopBg.underMouse():
                self.dragPos = event.globalPosition().toPoint()
                event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self.contentTopBg.underMouse():
            self.move(self.pos() + event.globalPosition().toPoint() - self.dragPos)
            self.dragPos = event.globalPosition().toPoint()
            event.accept()

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else: 
            self.showMaximized()
    
    @asyncSlot()
    async def apply_blue_shimmer(self, button, index):
        if hasattr(button, 'overlay'):
            button.overlay.play()
        if index!=1 and index!=2:self.stackedWidget.setCurrentIndex(index)
        elif index==2 and self.prepare.is_set():self.stackedWidget.setCurrentIndex(index)
        elif index==1 and self.prepare.is_set() and self.page_setting.config["api_key"]: self.stackedWidget.setCurrentIndex(index)
        elif not self.prepare.is_set(): self.notify("界面加载中...")
        else: self.notify("未设置api_key")

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