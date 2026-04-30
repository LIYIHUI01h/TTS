import os
import sys
import base64
import http
import math
import copy
import socket
import shutil
import hashlib
import json
import asyncio

import psutil
import aiofiles
import pynvml
import mysql.connector
from datetime import datetime
from mika.tool import getLogger
from mika.api import SiliconCloud_model
from qasync import asyncSlot
from llama_index.core.schema import TextNode
from PySide6.QtCore import QProcess, QUrl, QAbstractAnimation, QBuffer, QEvent, QEasingCurve, QIODevice, QMimeData, QParallelAnimationGroup, QPointF, QSettings, QTimer, Qt, QPropertyAnimation, QPoint, QRect, QSize, QVariantAnimation, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QTextCursor
from PySide6.QtWidgets import QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QGraphicsProxyWidget, QGraphicsScene, QGraphicsView, QGridLayout, QInputDialog, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QScrollArea, QSizeGrip, QPushButton, QSizePolicy, QSlider, QSplitter, QStackedLayout, QStackedWidget, QTextEdit, QTreeWidget, QTreeWidgetItem, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView

logger = getLogger(log_path="log/UI.log", log_name="UI", mode='w')
