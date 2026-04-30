import os
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSlider, QVBoxLayout, QWidget, QComboBox
from mika.api import SiliconCloud_model
from UI.widgets import BasePage, ToastNotification
from UI.common import logger


class SettingPage(BasePage):
    def __init__(self, flags, chatpage):
        super().__init__('SETTINGS', '系统参数配置')
        self.flags = flags
        self.chatpage = chatpage
        self.config_path = 'config/config.json'
        self.base_model_path = os.path.join('live2d', 'public', 'models')
        self.base_bg_path = os.path.join('live2d', 'public', 'background')
        self.SiliconCloud_model = SiliconCloud_model

        self.load_config_from_file()
        self.setup_setting_ui()
        self.apply_config_to_ui()

    def get_local_models(self):
        if not os.path.exists(self.base_model_path):
            return ['QianYi']
        models = [f for f in os.listdir(self.base_model_path) if os.path.isdir(os.path.join(self.base_model_path, f))]
        return models if models else ['QianYi']

    def get_local_backgrounds(self):
        if not os.path.exists(self.base_bg_path):
            return ['bk4.png']
        valid_exts = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
        bgs = [f for f in os.listdir(self.base_bg_path) if f.lower().endswith(valid_exts)]
        return bgs if bgs else ['bk4.png']

    def showEvent(self, event):
        super().showEvent(event)
        self.load_config_from_file()
        self.live2d_model_combo.clear()
        self.live2d_model_combo.addItems(self.get_local_models())
        self.live2d_bg_combo.clear()
        self.live2d_bg_combo.addItems(self.get_local_backgrounds())
        self.apply_config_to_ui()

    def setup_setting_ui(self):
        self.container_layout.setSpacing(12)
        self.container_layout.setContentsMargins(10, 5, 10, 5)

        self.api_input = QLineEdit()
        self.api_input.setEchoMode(QLineEdit.Password)
        self.api_input.setObjectName('settingInput')
        self.api_input.setPlaceholderText('填入 API Key...')
        self.create_row('API 密钥', '修改密钥后需重载服务以重新初始化', self.api_input)

        self.asr_combo = QComboBox()
        self.asr_combo.addItems(['in', 'out'])
        self.asr_combo.setObjectName('settingCombo')
        self.create_row('识别模式', 'in: 系统内部声音 | out: 麦克风输入', self.asr_combo)

        self.model_select = QComboBox()
        self.model_select.addItems(list(self.SiliconCloud_model.keys()))
        self.model_select.setObjectName('settingCombo')
        self.create_row('思维核心', '选择云端大模型驱动对话', self.model_select)

        self.live2d_model_combo = QComboBox()
        self.live2d_model_combo.addItems(self.get_local_models())
        self.live2d_model_combo.setObjectName('settingCombo')
        self.create_row('看板角色', '加载 live2d/public/models 下的角色文件夹', self.live2d_model_combo)

        self.live2d_bg_combo = QComboBox()
        self.live2d_bg_combo.addItems(self.get_local_backgrounds())
        self.live2d_bg_combo.setObjectName('settingCombo')
        self.create_row('场景背景', '加载 live2d/public/background 下的图片', self.live2d_bg_combo)

        self.t_slider = QSlider(Qt.Horizontal)
        self.t_slider.setRange(5, 30)
        self.t_label = QLabel('1.0s')
        self.t_label.setFixedWidth(45)
        self.t_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        t_layout = QHBoxLayout()
        t_layout.addWidget(self.t_slider)
        t_layout.addWidget(self.t_label)
        self.create_row('听力感度', '检测到停顿多久后开始响应(秒)', t_layout)
        self.t_slider.valueChanged.connect(lambda v: self.t_label.setText(f'{v/10.0}s'))

        self.v_slider = QSlider(Qt.Horizontal)
        self.v_slider.setRange(0, 100)
        self.v_label = QLabel('80%')
        self.v_label.setFixedWidth(45)
        self.v_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        v_layout = QHBoxLayout()
        v_layout.addWidget(self.v_slider)
        v_layout.addWidget(self.v_label)
        self.create_row('输出音量', '调整 agent 说话的声音大小', v_layout)
        self.v_slider.valueChanged.connect(lambda v: self.v_label.setText(f'{v}%'))

        self.container_layout.addSpacing(15)
        btn_container = QHBoxLayout()
        btn_container.addStretch()
        self.save_btn = QPushButton('保存设置')
        self.save_btn.setFixedSize(110, 32)
        self.save_btn.setObjectName('saveButton')
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self.do_save_logic)
        btn_container.addWidget(self.save_btn)
        self.container_layout.addLayout(btn_container)
        self.container_layout.addStretch()
        self.apply_styles()

    def apply_styles(self):
        self.setStyleSheet('''
            #settingInput, #settingCombo { background: #1a1d22; color: #e0e0e0; border: 1px solid #3d444d; border-radius: 4px; padding: 4px; }
            #saveButton { background: transparent; color: #bd93f9; border: 1px solid #bd93f9; border-radius: 4px; font-weight: bold; }
            #saveButton:hover { background: rgba(189, 147, 249, 0.1); }
            QSlider::groove:horizontal { height: 4px; background: #3d444d; border-radius: 2px; }
            QSlider::handle:horizontal { background: #bd93f9; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }
        ''')

    def load_config_from_file(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        setattr(self.flags, key, value)
                m_name = getattr(self.flags, 'live2d_model', None)
                if m_name:
                    self.parse_model_extra_config(m_name)
            except Exception as e:
                logger.error(f'设置参数读取失败: {e}')

    def parse_model_extra_config(self, model_name):
        model_cfg_path = os.path.join(self.base_model_path, model_name, 'model_config.json')
        if os.path.exists(model_cfg_path):
            try:
                with open(model_cfg_path, 'r', encoding='utf-8') as f:
                    model_extra = json.load(f)
                    for k, v in model_extra.items():
                        setattr(self.flags, k, v)
            except Exception as e:
                logger.error(f'live2d模型读取失败: {e}')

    def apply_config_to_ui(self):
        self.api_input.setText(getattr(self.flags, 'api_key', ''))
        self.asr_combo.setCurrentText(getattr(self.flags, 'asr_mode', 'in'))
        stored_model = getattr(self.flags, 'model_name', 'DeepSeek-V3')
        display_name = stored_model
        for name, full_path in self.SiliconCloud_model.items():
            if full_path == stored_model:
                display_name = name
                break
        self.model_select.setCurrentText(display_name)
        self.live2d_model_combo.setCurrentText(getattr(self.flags, 'live2d_model', 'QianYi'))
        self.live2d_bg_combo.setCurrentText(getattr(self.flags, 'live2d_bg', 'bk4.png'))
        self.t_slider.setValue(int(getattr(self.flags, 'silence_threshold', 1.0) * 10))
        self.v_slider.setValue(int(getattr(self.flags, 'volume', 0.8) * 100))

    def do_save_logic(self):
        old_api = getattr(self.flags, 'api_key', '')
        old_asr = getattr(self.flags, 'asr_mode', 'in')
        new_api = self.api_input.text()
        new_asr = self.asr_combo.currentText()

        if (new_api != old_api) or (new_asr != old_asr):
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle('核心参数变更')
            msg_box.setText('API密钥或模式变动需重载服务。\n确定应用？')
            yes_btn = msg_box.addButton('立即重载', QMessageBox.YesRole)
            no_btn = msg_box.addButton('取消修改', QMessageBox.NoRole)
            msg_box.exec()
            if msg_box.clickedButton() == no_btn:
                self.apply_config_to_ui()
                return

        current_model_name = self.live2d_model_combo.currentText()
        new_config = {
            'api_key': new_api,
            'asr_mode': new_asr,
            'model_name': self.SiliconCloud_model.get(self.model_select.currentText(), self.model_select.currentText()),
            'live2d_model': current_model_name,
            'live2d_bg': self.live2d_bg_combo.currentText(),
            'silence_threshold': self.t_slider.value() / 10.0,
            'volume': self.v_slider.value() / 100.0
        }

        model_cfg_path = os.path.join(self.base_model_path, current_model_name, 'model_config.json')
        if os.path.exists(model_cfg_path):
            with open(model_cfg_path, 'r', encoding='utf-8') as f:
                new_config.update(json.load(f))

        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(new_config, f, indent=4, ensure_ascii=False)
            for key, value in new_config.items():
                setattr(self.flags, key, value)
            m_path = self.flags.model_path
            b_path = f'background/{self.flags.live2d_bg}'
            self.chatpage.set_live2d_model(m_path, self.flags.mouthparam)
            self.chatpage.set_live2d_background(b_path)
            self.notify('设置保存成功', 'info')
        except Exception as e:
            self.notify(f'保存异常: {str(e)}', 'error')

    def create_row(self, title, desc, content):
        card = QFrame()
        card.setObjectName('SettingCard')
        row_layout = QHBoxLayout(card)
        row_layout.setContentsMargins(15, 10, 15, 10)
        text_widget = QWidget()
        text_layout = QVBoxLayout(text_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet('color: #bd93f9; font-weight: bold; font-size: 14px; background:transparent;')
        d_lbl = QLabel(desc)
        d_lbl.setStyleSheet('color: #717e95; font-size: 11px; background:transparent;')
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

    def notify(self, message, level='info'):
        colors = {'info': '#87CEFA', 'warn': '#ffb86c', 'error': '#ff5555'}
        ToastNotification(self, message, colors.get(level, '#87CEFA'))
