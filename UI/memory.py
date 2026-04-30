import asyncio
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QSplitter, QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QLineEdit,
                               QSizePolicy)
from UI.widgets import BasePage
from UI.common import logger, TextNode


class MemoryPage(BasePage):
    def __init__(self, flags):
        super().__init__('MEMORY CORE', '系统长期记忆图谱 - 仅限浏览模式')
        self.flags = flags
        self.layout.setContentsMargins(25, 20, 25, 15)
        self.memory_manager = None

        sub_title_label = self.layout.itemAt(1).widget()
        self.header_row = QHBoxLayout()
        self.header_row.addWidget(sub_title_label)
        self.header_row.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(' 🔍 搜索关键词...')
        self.search_input.setFixedWidth(240)
        self.search_input.setStyleSheet('''
            QLineEdit {
                background: #1d2127; border: 1px solid #3e4451;
                border-radius: 15px; padding: 6px 15px; color: #dcdcdc;
            }
            QLineEdit:focus { border: 1px solid #87CEFA; background: #232830; }
        ''')
        self.search_input.textChanged.connect(self.search_tree)

        self.edit_mode_btn = QPushButton('记忆图谱界面 ↗')
        self.edit_mode_btn.setFixedSize(140, 34)
        self.edit_mode_btn.setCursor(Qt.PointingHandCursor)
        self.edit_mode_btn.setStyleSheet('''
            QPushButton { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6272a4, stop:1 #bd93f9); 
                border-radius: 17px; /* 全圆角 */
                color: white; font-size: 12px; font-weight: bold; border: none;
            } 
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7283b5, stop:1 #caabf1); }
        ''')

        self.header_row.addWidget(self.search_input)
        self.header_row.addSpacing(15)
        self.header_row.addWidget(self.edit_mode_btn)
        self.layout.insertLayout(1, self.header_row)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(1)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(20)
        self.tree.setAnimated(True)
        self.tree.setStyleSheet('''
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
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {
                border-image: none;
                image: none;
            }
        ''')

        self.container_layout.addWidget(self.tree)
        self.edit_mode_btn.clicked.connect(self.verify_and_open_editor)
        self.editor_window = None

    async def load_memory_tree(self):
        self.tree.setWordWrap(True)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.tree.setEditTriggers(self.tree.EditTrigger.NoEditTriggers)
        self.tree.setIndentation(25)
        self.tree.header().setSectionResizeMode(0, self.tree.header().ResizeMode.Stretch)

        try:
            self.tree.itemClicked.disconnect()
        except Exception:
            pass

        self.tree.itemClicked.connect(lambda item: item.setExpanded(not item.isExpanded()))
        self.tree.clear()

        try:
            memories = await self.memory_manager.show_memories(_print=False)
            if not memories:
                self.tree.addTopLevelItem(QTreeWidgetItem(self.tree, ['📭 暂无长期记忆数据']))
                return

            for m in memories:
                raw_text = m.get('text', '无内容')
                node_id = m.get('id', '')
                qa_list = m.get('QA', [])

                tree_item = QTreeWidgetItem(self.tree, [f'📝 {raw_text}'])
                main_font = QFont('Segoe UI', 10)
                main_font.setBold(True)
                tree_item.setFont(0, main_font)
                tree_item.setFlags(tree_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                tree_item.setData(0, Qt.ItemDataRole.UserRole, node_id)

                for qa in qa_list:
                    if isinstance(qa, dict):
                        q_text = qa.get('Q') or qa.get('q') or '未记录详情'
                        a_text = qa.get('A') or qa.get('a') or ''
                        display_qa = f'Q: {q_text}\nA: {a_text}' if a_text else f'Q: {q_text}'
                    else:
                        display_qa = str(qa)

                    qa_item = QTreeWidgetItem(tree_item, [display_qa])
                    sub_font = QFont('Consolas', 9)
                    qa_item.setFont(0, sub_font)
                    qa_item.setForeground(0, QColor('#87CEFA'))

                self.tree.addTopLevelItem(tree_item)

        except Exception as e:
            logger.info(f'❌ 加载记忆树失败: {e}')

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
            while p:
                p.setHidden(False)
                p.setExpanded(True)
                p = p.parent()

    def verify_and_open_editor(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('权限验证')
        dialog.setFixedWidth(350)
        dialog.setStyleSheet('''
            QDialog { background-color: #1d2127; border: 1px solid #87CEFA; }
            QLabel { color: #ffffff; font-family: 'Microsoft YaHei'; }
            QLineEdit { background: #16191d; color: white; border: 1px solid #444444; padding: 5px; }
            QPushButton { 
                border: 1px solid #87CEFA; border-radius: 3px; padding: 5px 15px;
                background: transparent; color: #87CEFA; min-width: 80px;
            }
            QPushButton:hover { background-color: rgba(135, 206, 250, 0.1); }
        ''')

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('进入管理界面需要管理员权限：'))

        pwd_input = QLineEdit()
        pwd_input.setEchoMode(QLineEdit.Password)
        pwd_input.setPlaceholderText('请输入管理密码...')
        layout.addWidget(pwd_input)

        btn_layout = QHBoxLayout()
        yes_btn = QPushButton('确认进入')
        no_btn = QPushButton('取消')
        btn_layout.addWidget(no_btn)
        btn_layout.addWidget(yes_btn)
        layout.addLayout(btn_layout)

        yes_btn.clicked.connect(dialog.accept)
        no_btn.clicked.connect(dialog.reject)

        if dialog.exec() == QDialog.Accepted:
            if pwd_input.text() == '121176':
                self.open_editor()
            else:
                logger.info('密码错误')
                if hasattr(self.window(), 'notify'):
                    self.window().notify('密码错误', 'error')

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
            logger.info(f'❌ 弹窗失败: {e}')
            self.editor_window = None


class MemoryEditorWindow(QWidget):
    def __init__(self, memory_manager):
        super().__init__()
        self.memory_manager = memory_manager
        self.current_data = None
        self.pending_updates = {}
        self.pending_deletes = set()

        self.setWindowTitle('MEMORY EDITOR - 核心记忆修正协议')
        self.resize(900, 650)
        self.setWindowFlags(Qt.Window | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)

        self.init_ui()

    def init_ui(self):
        self.setStyleSheet('''
            QWidget { background-color: #16191d; color: #abb2bf; font-family: 'Segoe UI', 'Microsoft YaHei'; }
            QListWidget { background-color: #1d2127; border: 1px solid #2d323b; border-radius: 10px; outline: none; }
            QListWidget::item { padding: 12px; border-bottom: 1px solid #2d323b; color: #dcdcdc; }
            QListWidget::item:selected { background-color: #2c313c; border-left: 5px solid #bd93f9; color: #87CEFA; }
            QCheckBox { color: #6272a4; font-size: 11px; font-weight: bold; }
            QTextEdit { background: #16191d; border: 1px solid #3e4451; border-radius: 8px; padding: 10px; font-size: 13px; line-height: 1.4; }
            QLineEdit { background: #1d2127; border-radius: 15px; padding: 6px 12px; border: 1px solid #3e4451; }
            QPushButton#SaveBtn { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #bd93f9, stop:1 #ff79c6); color: white; padding: 10px 25px; border-radius: 18px; font-weight: bold; }
            QPushButton#DelBtn { color: #ff5555; border: 1px solid #ff5555; padding: 6px; border-radius: 6px; }
        ''')

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 10)

        header = QHBoxLayout()
        title_label = QLabel('🧠 核心事实编辑器')
        title_label.setStyleSheet('font-size: 16px; font-weight: bold; color: #87CEFA;')
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(' 🔍 搜索记忆碎片...')
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
        self.edit_panel.setStyleSheet('background: #1d2127; border-radius: 12px; border: 1px solid #2d323b;')
        panel_layout = QVBoxLayout(self.edit_panel)
        panel_layout.setContentsMargins(15, 15, 15, 15)

        fact_bar = QHBoxLayout()
        fact_bar.addWidget(QLabel('📝 事实陈述 (Node Text)'))
        self.fact_lock_cb = QCheckBox('开启编辑模式')
        self.fact_lock_cb.stateChanged.connect(self.toggle_fact_edit)
        fact_bar.addStretch()
        fact_bar.addWidget(self.fact_lock_cb)
        panel_layout.addLayout(fact_bar)

        self.text_editor = QTextEdit()
        self.text_editor.setReadOnly(True)
        self.text_editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        panel_layout.addWidget(self.text_editor)

        qa_bar = QHBoxLayout()
        qa_bar.addWidget(QLabel('📂 溯源素材 (Root QA Trace)'))
        self.qa_lock_cb = QCheckBox('编辑原始对话')
        self.qa_lock_cb.stateChanged.connect(self.toggle_qa_edit)
        qa_bar.addStretch()
        qa_bar.addWidget(self.qa_lock_cb)
        panel_layout.addLayout(qa_bar)

        self.qa_display = QTextEdit()
        self.qa_display.setReadOnly(True)
        self.qa_display.setStyleSheet('color: #6272a4; background: #1a1d22;')
        self.qa_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        panel_layout.addWidget(self.qa_display)

        btn_layout = QHBoxLayout()
        self.del_btn = QPushButton(' 🗑 彻底遗忘 ')
        self.del_btn.setObjectName('DelBtn')
        self.del_btn.clicked.connect(self.delete_current_memory)
        self.save_btn = QPushButton(' ⚡ 暂存修改 ')
        self.save_btn.setObjectName('SaveBtn')
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

        self.status_bar = QLabel('系统就绪 | 等待节点选择')
        self.status_bar.setStyleSheet('color: #6272a4; font-size: 11px; padding-top: 5px;')
        main_layout.addWidget(self.status_bar)

    def toggle_fact_edit(self, state):
        is_unlocked = (state == Qt.Checked)
        self.text_editor.setReadOnly(not is_unlocked)
        self.text_editor.setStyleSheet(f"border: 1px solid {'#bd93f9' if is_unlocked else '#3e4451'};")

    def toggle_qa_edit(self, state):
        self.qa_display.setReadOnly(state != Qt.Checked)

    def filter_items(self, text):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    async def refresh_data(self):
        try:
            self.status_bar.setText('⏳ 正在同步全量记忆...')
            self.list_widget.clear()
            memories = await self.memory_manager.show_memories(_print=False)
            if not memories:
                self.status_bar.setText('📭 记忆库为空')
                return

            for m in memories:
                m['_raw_text'] = m.get('text', '')
                m['_raw_qa'] = list(m.get('QA', []))
                preview = m.get('text', 'Empty').replace('\n', ' ')
                item = QListWidgetItem(f"ID: {m['id'][:8]}... | {preview[:25]}...")
                item.setData(Qt.UserRole, m)
                self.list_widget.addItem(item)
            self.status_bar.setText(f'✅ 已加载 {len(memories)} 个节点')
        except Exception as e:
            self.status_bar.setText(f'❌ 加载失败: {str(e)}')

    def on_selection_changed(self):
        selected = self.list_widget.selectedItems()
        if not selected:
            return
        data = selected[0].data(Qt.UserRole)
        self.current_data = data
        self.text_editor.setPlainText(data.get('text', ''))
        qa_list = data.get('QA', [])
        self.qa_display.setPlainText('\n\n'.join(qa_list) if qa_list else '无溯源素材')
        self.fact_lock_cb.setChecked(False)
        self.qa_lock_cb.setChecked(False)

    def save_to_cache(self):
        if not self.current_data:
            return
        node_id = self.current_data['id']
        new_text = self.text_editor.toPlainText().strip()
        new_qa = self.qa_display.toPlainText().split('\n\n')

        if new_text == self.current_data.get('_raw_text') and new_qa == self.current_data.get('_raw_qa'):
            self.status_bar.setText('ℹ️ 内容未变动')
            return

        self.current_data['text'] = new_text
        self.current_data['QA'] = new_qa
        self.pending_updates[node_id] = self.current_data

        selected_item = self.list_widget.selectedItems()[0]
        selected_item.setData(Qt.UserRole, self.current_data)
        selected_item.setForeground(QColor('#bd93f9'))
        self.status_bar.setText(f'✨ 节点 {node_id[:8]} 已暂存')

    def delete_current_memory(self):
        if not self.current_data:
            return
        node_id = self.current_data['id']
        if QMessageBox.question(self, '彻底遗忘', '确定删除该节点？') == QMessageBox.Yes:
            self.pending_deletes.add(node_id)
            self.list_widget.takeItem(self.list_widget.currentRow())
            self.text_editor.clear()
            self.current_data = None

    def closeEvent(self, event):
        if not self.pending_updates and not self.pending_deletes:
            event.accept()
            return
        reply = QMessageBox.question(self, '同步确认', '是否保存修改到数据库？', QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
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
                            'QA': data['QA'],
                            'display_time': data['stime'].strftime('%Y-%m-%d %H:%M:%S'),
                            'last_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'stimestamp': int(data['stime'].timestamp()),
                            'etimestamp': int(datetime.now().timestamp())
                        }
                    )

                    node.excluded_embed_metadata_keys = ['QA', 'display_time', 'last_time', 'stimestamp', 'etimestamp']
                    object.__setattr__(node, 'embedding', new_vector)
                    update_nodes.append(node)

                if update_nodes:
                    for n in update_nodes:
                        try:
                            self.memory_manager.index.docstore.delete_document(n.id_, raise_error=False)
                        except Exception:
                            pass
                    await self.memory_manager.index.ainsert_nodes(update_nodes)

            self.pending_updates = {}
            self.pending_deletes = set()

        except Exception as e:
            logger.error(f'❌ UI记忆同步失败: {e}')
