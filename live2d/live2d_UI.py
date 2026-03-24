import asyncio
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QPushButton, QWidget, QLineEdit
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl
from PySide6.QtCore import QObject,Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage
import threading
from qasync import QEventLoop
from mika.tool import getLogger

logger=getLogger(log_path="log/live2d.log",log_name="Live2d",mode='w',stream=False)

class Bridget(QObject):
    def __init__(self,event):
        super().__init__()
        self.web_done=event
    @Slot()

    def web_done_set(self):
        logger.info("Web结束信号发出！！！")
        self.web_done.set()

class CustomPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, sourceid):
        logger.info(f"Web输出:(Line: {line}): {message}")

class Live2dPage(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("浅宜")
        self.resize(800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.browser = QWebEngineView()
        self.my_page=CustomPage(self.browser)
        self.browser.setPage(self.my_page)

        self.browser.setUrl(QUrl("http://localhost:5173")) 
        layout.addWidget(self.browser)

        self.web_done=threading.Event()
        self.web_bridget=Bridget(self.web_done)
        self.channel=QWebChannel()
        self.channel.registerObject('web_bridget',self.web_bridget)
        self.browser.page().setWebChannel(self.channel)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("输入文字，点发送让小人变大...")
        layout.addWidget(self.input_box)

        self.btn_send = QPushButton("发送并改变小人缩放")
        self.btn_send.clicked.connect(self.send_to_vue)
        layout.addWidget(self.btn_send)

    def send_to_vue(self):
        text_len = len(self.input_box.text())
        new_scale = min(0.1, 0.2 + (text_len * 0.05))
        js_code = f"window.model.scale.set({new_scale}); console.log('Python 已将缩放设为: {new_scale}');"
        self.browser.page().runJavaScript(js_code)

    def closeEvent(self,event):
        if not self.web_done.is_set():
            self.hide()
            self.browser.page().runJavaScript("if (window.CLEAR) window.CLEAR();")
            event.ignore()
        else:
            event.accept()