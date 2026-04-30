import os
import hashlib
import mysql.connector
from PySide6.QtCore import QEvent, QPropertyAnimation, QVariantAnimation, Qt, QTimer, QSettings
from PySide6.QtGui import QPainter, QPainterPath, QPixmap, QCursor
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QStackedWidget, QWidget
from UI.widgets import BasePage, ToastNotification, get_round_pixmap
from UI.common import logger

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'user_names'
}


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(360, 420)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.settings = QSettings('MikaApp', 'LoginSettings')
        self.logged_user_data = None
        self.is_reg_mode = False
        self.init_ui()
        self.load_last_account()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.container = QFrame()
        self.container.setStyleSheet('''
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
        ''')

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(30, 10, 30, 25)
        layout.setSpacing(15)

        top_bar = QHBoxLayout()
        top_bar.addStretch()
        self.close_btn = QPushButton('×')
        self.close_btn.setObjectName('CloseBtn')
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self.reject)
        top_bar.addWidget(self.close_btn)
        layout.addLayout(top_bar)

        self.title_label = QLabel('SYSTEM LOGIN')
        self.title_label.setObjectName('Title')
        layout.addWidget(self.title_label, alignment=Qt.AlignCenter)
        layout.addSpacing(5)

        self.acc_i = QLineEdit()
        self.acc_i.setPlaceholderText('账号')

        self.pwd_i = QLineEdit()
        self.pwd_i.setPlaceholderText('密码')
        self.pwd_i.setEchoMode(QLineEdit.Password)

        self.name_i = QLineEdit()
        self.name_i.setPlaceholderText('用户名(称呼)')
        self.name_i.hide()

        layout.addWidget(self.acc_i)
        layout.addWidget(self.pwd_i)
        layout.addWidget(self.name_i)
        layout.addStretch()

        self.btn = QPushButton('确 认 登 录')
        self.btn.setObjectName('ActionBtn')
        self.btn.clicked.connect(self.handle_action)
        layout.addWidget(self.btn)

        self.switch_btn = QPushButton('没有账号？点击注册')
        self.switch_btn.setObjectName('SwitchBtn')
        self.switch_btn.setCursor(Qt.PointingHandCursor)
        self.switch_btn.clicked.connect(self.toggle_mode)
        layout.addWidget(self.switch_btn, alignment=Qt.AlignCenter)

        self.main_layout.addWidget(self.container)

    def try_silent_login(self):
        acc = self.settings.value('last_account', '')
        pwd_h = self.settings.value('last_pwd_h', '')
        auto = self.settings.value('auto_login', 'false')
        if auto == 'false' or auto is False:
            return None

        if not acc or not pwd_h:
            return None

        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT * FROM users WHERE account=%s AND password_hash=%s', (acc, pwd_h))
            user = cursor.fetchone()
            conn.close()
            if user:
                return {
                    'username': str(user.get('username', 'Unknown')),
                    'uid': str(user.get('id', '0')),
                    'avatar_path': user.get('profile_photo_path')
                }
        except Exception as e:
            logger.info(f'自动登录异常: {e}')
        return None

    def toggle_mode(self):
        self.is_reg_mode = not self.is_reg_mode
        if self.is_reg_mode:
            self.title_label.setText('CREATE ACCOUNT')
            self.btn.setText('注 册 并 登 录')
            self.switch_btn.setText('已有账号？返回登录')
            self.name_i.show()
            self.setFixedSize(360, 480)
        else:
            self.title_label.setText('SYSTEM LOGIN')
            self.btn.setText('确 认 登 录')
            self.switch_btn.setText('没有账号？点击注册')
            self.name_i.hide()
            self.setFixedSize(360, 420)

    def handle_action(self):
        if self.is_reg_mode:
            self.run_registration()
        else:
            self.handle_auth()

    def run_registration(self):
        acc = self.acc_i.text().strip()
        pwd = self.pwd_i.text().strip()
        name = self.name_i.text().strip()
        if not acc or not pwd or not name:
            QMessageBox.warning(self, '错误', '请填写完整注册信息')
            return

        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM users WHERE account=%s', (acc,))
            if cursor.fetchone():
                QMessageBox.warning(self, '错误', '该账号已存在')
                return
            pwd_h = hashlib.sha256(pwd.encode()).hexdigest()
            cursor.execute('INSERT INTO users (account, password_hash, username) VALUES (%s, %s, %s)', (acc, pwd_h, name))
            conn.commit()
            conn.close()
            QMessageBox.information(self, '成功', '注册成功，正在进入系统...')
            self.handle_auth()
        except Exception as e:
            QMessageBox.critical(self, '数据库异常', str(e))

    def handle_auth(self):
        acc = self.acc_i.text().strip()
        pwd = self.pwd_i.text().strip()
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            pwd_h = hashlib.sha256(pwd.encode()).hexdigest()
            cursor.execute('SELECT * FROM users WHERE account=%s AND password_hash=%s', (acc, pwd_h))
            user = cursor.fetchone()
            if user:
                self.settings.setValue('last_account', acc)
                self.settings.setValue('last_pwd_h', pwd_h)
                self.settings.setValue('auto_login', True)
                self.settings.sync()
                self.logged_user_data = {
                    'username': str(user.get('username', 'Unknown')),
                    'uid': str(user.get('id', '0')),
                    'avatar_path': user.get('profile_photo_path')
                }
                conn.close()
                self.accept()
            else:
                QMessageBox.warning(self, '失败', '账号或密码错误')
                conn.close()
        except Exception as e:
            QMessageBox.critical(self, '错误', f'数据库连接异常: {e}')

    def load_last_account(self):
        last_acc = self.settings.value('last_account', '')
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


class ProfileHoverCard(QFrame):
    def __init__(self, parent, login_cb, logout_cb):
        super().__init__(parent)
        self.setFixedSize(280, 400)
        self.login_cb = login_cb
        self.logout_cb = logout_cb
        self.target_avatar = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._check_mouse)
        self.setStyleSheet('''
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
        ''')

        layout = QVBoxLayout(self)
        self.stack = QStackedWidget()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)

        self.p0 = QWidget()
        l0 = QVBoxLayout(self.p0)
        l0.setContentsMargins(20, 60, 20, 20)
        self.tip = QLabel('登录以体验更多功能')
        btn_in = QPushButton('立即登录')
        btn_in.setObjectName('login')
        btn_in.clicked.connect(self._on_in)
        l0.addWidget(self.tip, alignment=Qt.AlignCenter)
        l0.addStretch()
        l0.addWidget(btn_in)
        self.stack.addWidget(self.p0)

        self.p1 = QWidget()
        l1 = QVBoxLayout(self.p1)
        l1.setContentsMargins(20, 60, 20, 20)
        self.u_na = QLabel('璃依回')
        self.u_na.setStyleSheet('font-size: 20px; font-weight: bold;')
        self.u_id = QLabel('UID: 1')
        self.u_id.setStyleSheet('font-size: 12px; color: #717e95;')
        btn_out = QPushButton('注销登录')
        btn_out.setObjectName('logout')
        btn_out.clicked.connect(self._on_out)
        l1.addWidget(self.u_na, alignment=Qt.AlignCenter)
        l1.addWidget(self.u_id, alignment=Qt.AlignCenter)
        l1.addStretch()
        l1.addWidget(btn_out)
        self.stack.addWidget(self.p1)

    def set_user_data(self, data):
        if data:
            self.u_na.setText(data.get('username', '璃依回'))
            self.u_id.setText(f"UID: {data.get('uid', '1')}")
            self.stack.setCurrentIndex(1)
        else:
            self.stack.setCurrentIndex(0)

    def show_safe(self, pos, target):
        self.target_avatar = target
        self.move(pos)
        self.show()
        self.raise_()
        if self.target_avatar:
            self.target_avatar.raise_()
        self.timer.start(80)

    def _check_mouse(self):
        if not self.isVisible() or self.target_avatar is None:
            return
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

    def _on_out(self):
        self.logout_cb()
        self.set_user_data(None)


class HomePage(QWidget):
    def __init__(self, flags):
        super().__init__()
        self.flags = flags
        self.user_data = None
        self.user_name = '游客'
        self.flags.user_name = self.user_name
        self.init_ui()

        self.card_widget = ProfileHoverCard(self, self._exec_login, self._exec_logout)
        self.card_widget.hide()

        self.avatar_label = QLabel(self)
        self.avatar_label.setFixedSize(45, 45)
        self.avatar_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setStyleSheet('''
            background: #2d323b; 
            border: 2px solid white; 
            border-radius: 22px; 
            color: white; 
            font-weight: bold;
        ''')
        self.avatar_label.setText('?')

        self.ani = QPropertyAnimation(self)
        self.ani.setDuration(150)
        self.ani.setStartValue(45)
        self.ani.setEndValue(75)
        self.ani.valueChanged.connect(self._animate_avatar)

        self.avatar_label.installEventFilter(self)
        self.avatar_label.raise_()

        QTimer.singleShot(200, self.check_auto_login)

    def init_ui(self):
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

        self.page_title = QLabel('USER PROFILE')
        self.page_title.setStyleSheet('font-size: 26px; font-weight: bold; color: white;')

        self.sub_tip = QLabel('用户主页，用于用户个性展示')
        self.sub_tip.setStyleSheet('color: #717e95; font-size: 13px;')

        self.purple_line = QFrame()
        self.purple_line.setFixedHeight(3)
        self.purple_line.setFixedWidth(45)
        self.purple_line.setStyleSheet('background-color: #bd93f9; border-radius: 1px;')

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
        if self.user_data and self.user_data.get('avatar_path'):
            pix = get_round_pixmap(self.user_data['avatar_path'], value)
            if pix:
                self.avatar_label.setPixmap(pix)
                self.avatar_label.setText('')
        self.avatar_label.setStyleSheet(f'background: #2d323b; border: 2px solid white; border-radius: {radius}px; color: white;')
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
        if watched == self.avatar_label and event.type() == QEvent.Type.Enter:
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
                self.user_name = data.get('username', '游客')
                self.flags.user_name = self.user_name
                settings = QSettings('MikaApp', 'LoginSettings')
                settings.setValue('auto_login', True)
                settings.setValue('user_data', data)
                self.apply_user_state(data)

    def _exec_logout(self):
        self.user_data = None
        settings = QSettings('MikaApp', 'LoginSettings')
        settings.remove('auto_login')
        settings.remove('user_data')
        self.apply_user_state(None)

    def apply_user_state(self, data):
        self.user_data = data
        self.user_name = '游客'
        self.flags.user_name = self.user_name
        if data:
            self.user_name = data.get('username', '游客')
            self.flags.user_name = self.user_name
            pix = get_round_pixmap(data.get('avatar_path'), 45)
            if pix:
                self.avatar_label.setPixmap(pix)
                self.avatar_label.setText('')
            else:
                self.avatar_label.setText(data.get('username', 'U')[0])
            self.card_widget.set_user_data(data)
        else:
            self.avatar_label.setPixmap(QPixmap())
            self.avatar_label.setText('?')
            self.card_widget.set_user_data(None)

    def check_auto_login(self):
        settings = QSettings('MikaApp', 'LoginSettings')
        is_auto = str(settings.value('auto_login', 'false')).lower() == 'true'
        if is_auto:
            saved_data = settings.value('user_data')
            if saved_data:
                self.user_name = saved_data.get('username', '游客')
                self.flags.user_name = self.user_name
                self.apply_user_state(saved_data)
