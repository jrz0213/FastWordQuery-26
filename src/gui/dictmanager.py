import os
import sys
import subprocess
from aqt.qt import *

from ..context import config
from ..lang import _, _sl
from ..service import service_manager, service_pool
from .base import WIDGET_SIZE, Dialog
from ..utils.logger import logger

__all__ = ['DictManageDialog']


class DictManageDialog(Dialog):
    """
    Dictionary manager window. enabled or disabled dictionary, and setting params of dictionary.
    """

    def __init__(self, parent, title=u'Dictionary Manager'):
        super(DictManageDialog, self).__init__(parent, title)
        
        logger.info("打开词典管理面板 (DictManageDialog)...")
        
        # 给窗口一个合理的初始尺寸
        self.resize(400, 500) 
        
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)
        
        text_line = QLabel(_('EDITOR_NAME_NOTE'))
        text_line.setWordWrap(True)
        self.edit_line = QLineEdit()
        self.edit_line.setPlaceholderText("editor name")
        self.main_layout.addWidget(text_line)
        self.main_layout.addWidget(self.edit_line)
        self._options = list()
        
        btnbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, Qt.Orientation.Horizontal, self)
        btnbox.accepted.connect(self.accept)
        
        self.scroll = QWidget()
        
        self.dicts_layout = QGridLayout(self.scroll)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True) # 【关键】让内部容器自适应宽度
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame) # 去除自带边框
        self.scroll_area.setWidget(self.scroll)
        
        self.main_layout.addWidget(self.scroll_area)
        self.main_layout.addWidget(btnbox)
        
        self.build()


    def build(self):
        """ """
        # labels
        f = QFont()
        f.setBold(True)
        labels = ['', '']
        for i, s in enumerate(labels):
            if s:
                label = QLabel(_(s))
                label.setFont(f)
                label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
                self.dicts_layout.addWidget(label, 0, i)
        
        # enabled all
        self.enabled_all_check_btn = QCheckBox(_('DICTS_NAME'))
        self.enabled_all_check_btn.setFont(f)
        self.enabled_all_check_btn.setEnabled(True)
        self.enabled_all_check_btn.setChecked(False)
        
        # signal
        self.enabled_all_check_btn.clicked.connect(self.enabled_all_changed)
        
        # add widgets
        self.dicts_layout.addWidget(self.enabled_all_check_btn, 0, 0)
        
        # dict service list
        confs = config.dicts
        dicts = list()
        services = service_manager.local_custom_services + service_manager.web_services
        for clazz in services:
            dicts.append({
                'title': clazz.__title__,
                'unique': clazz.__unique__,
                'path': clazz.__path__,
                'enabled': confs.get(clazz.__unique__, dict()).get('enabled', False)
            })
            
        # add dict
        for i, d in enumerate(dicts):
            self.add_dict_layout(i, **d)
            
        # 【关键修改】：在网格布局的最下方，添加一个会自动伸展的空行（弹簧），把内容全部往上顶
        current_row = self.dicts_layout.rowCount()
        self.dicts_layout.setRowStretch(current_row, 1)

        # update
        self.enabled_all_update()


    def add_dict_layout(self, i, **kwargs):
        # args
        title, unique, enabled, path = (
            kwargs.get('title', u''),
            kwargs.get('unique', u''),
            kwargs.get('enabled', False),
            kwargs.get('path', u''),
        )
        
        # button
        check_btn = QCheckBox(title)
        check_btn.setMinimumSize(WIDGET_SIZE.map_dict_width * 2, 0)
        check_btn.setEnabled(True)
        check_btn.setChecked(enabled)
        edit_btn = QToolButton(self)
        edit_btn.setText(_('EDIT'))
        
        # signal
        check_btn.stateChanged.connect(self.enabled_all_update)
        # 为避免 Python 在循环中 lambda 绑定的坑，最好将 path 默认值传入
        edit_btn.clicked.connect(lambda checked=False, p=path: self.on_edit(p))
        
        # add
        self.dicts_layout.addWidget(check_btn, i + 1, 0)
        self.dicts_layout.addWidget(edit_btn, i + 1, 1)
        self._options.append({
            'unique': unique,
            'check_btn': check_btn,
            'edit_btn': edit_btn,
        })


    def enabled_all_update(self):
        b = True
        for row in self._options:
            if not row['check_btn'].isChecked():
                b = False
                break
        self.enabled_all_check_btn.setChecked(b)


    def enabled_all_changed(self):
        b = self.enabled_all_check_btn.isChecked()
        for row in self._options:
            row['check_btn'].setChecked(b)


    def on_edit(self, path):
        """edit dictionary file"""
        logger.info(f"准备编辑词典脚本文件: [{path}]")
        try:
            on_edit = self.edit_line.text()
            self.open_text_editor(path, on_edit)
        except Exception as e:
            logger.error(f"编辑词典脚本文件失败: {str(e)}")


    def open_text_editor(self, filename, editor=""):
        logger.info(f"调用外部编辑器打开文件: [{filename}] | 指定编辑器: [{editor if editor else '系统默认'}]")
        if editor:
            subprocess.Popen([f"{editor}", filename])
        else:
            # 优先使用 Qt 跨平台原生接口，调用系统默认的文本/代码编辑器安全打开文件
            QDesktopServices.openUrl(QUrl.fromLocalFile(filename))


    def accept(self):
        """ok button clicked"""
        self.save()
        super(DictManageDialog, self).accept()


    def save(self):
        """save config to file"""
        data = dict()
        dicts = {}
        for row in self._options:
            dicts[row['unique']] = {
                'enabled': row['check_btn'].isChecked(),
            }
        data['dicts'] = dicts
        config.update(data)
        logger.info(f"保存词典启用状态配置成功 | 共 {len(dicts)} 个词典配置")