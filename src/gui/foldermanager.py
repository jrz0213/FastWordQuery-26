import os
import re
from aqt.qt import *

from ..context import config
from ..lang import _, _sl
from .base import WIDGET_SIZE, Dialog
from ..utils.logger import logger

try:
    from ..libs import MdxBuilder
except ImportError:
    MdxBuilder = None

__all__ = ['FoldersManageDialog']



def process_and_copy_custom_py(mdx_path, py_path, dict_folder_path):
    """
    处理并拷贝自定义 .py 文件到 dict 目录
    """
    if not os.path.exists(dict_folder_path):
        os.makedirs(dict_folder_path, exist_ok=True)

    # 1. 直接获取文件名（不带后缀）
    dict_name = os.path.splitext(os.path.basename(mdx_path))[0]
    
    # 2. 只需要替换掉中括号，并转义单引号（防止破坏 Python 字符串语法）
    safe_title = dict_name.replace('[', '_').replace(']', '_')
    safe_title_escaped = safe_title.replace("'", "\\'")

    # 3. 读取原 .py 文件内容
    with open(py_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # =========================================================
    # 替换 DICT_PATH
    # =========================================================
    safe_mdx_path = mdx_path.replace('\\', '/')
    content = re.sub(
        r"^DICT_PATH\s*=.*$", 
        f"DICT_PATH = r'{safe_mdx_path}'", 
        content,
        flags=re.MULTILINE
    )

    # =========================================================
    # 清理并替换 @register
    # =========================================================
    def sanitize_register(match):
        text = match.group(0)
        def replace_brackets(m_str):
            return m_str.group(0).replace('[', '_').replace(']', '_')
        return re.sub(r"[uU]?[rR]?['\"].*?['\"]", replace_brackets, text)
        
    content = re.sub(r"@register\(\s*\[.*?\]\s*\)", sanitize_register, content)

    def inject_name(match):
        text = match.group(0)
        quotes_content = re.findall(r"['\"](.*?)['\"]", text)
        if quotes_content and all(not val.strip() for val in quotes_content):
            return f"@register([u' -{safe_title_escaped}', u'MDX-{safe_title_escaped}'])"
        return text
            
    content = re.sub(r"@register\(\s*\[.*?\]\s*\)", inject_name, content)

    # ---------------------------------------------------------
    # 修复 import 路径
    # ---------------------------------------------------------
    content = re.sub(
        r"from\s+[A-Za-z0-9_.]*?service\.base\s+import", 
        "from ..base import", 
        content
    )

    # ---------------------------------------------------------
    # 写入到目标目录
    # ---------------------------------------------------------
    dest_py_path = os.path.join(dict_folder_path, os.path.basename(py_path))
    with open(dest_py_path, 'w', encoding='utf-8') as f:
        f.write(content)

    # ---------------------------------------------------------
    # 强制在配置中启用该词典
    # ---------------------------------------------------------
    from ..context import config
    match = re.search(r"class\s+([A-Za-z0-9_]+)\s*\(", content)
    if match:
        unique_key = match.group(1)
        dicts_conf = config.dicts
        if unique_key not in dicts_conf:
            dicts_conf[unique_key] = {}
        dicts_conf[unique_key]['enabled'] = True
        config.update({'dicts': dicts_conf})
    logger.info(f"脚本自动同步成功 | 词典: [{dict_name}] | 目标文件: [{os.path.basename(dest_py_path)}]")
class FoldersManageDialog(Dialog):
    '''
    Dictionary folder manager window. add or remove dictionary folders.
    '''

    def __init__(self, parent, title=u'Dictionary Folder Manager'):
        super(FoldersManageDialog, self).__init__(parent, title)
        # 维护一个内部的文件夹列表
        self._current_folders = list(config.dirs)
        
        # 定位插件的 service/dict/ 文件夹绝对路径
        self.plugin_dict_folder = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'service', 'dict'
        )
        
        self.build()

    def build(self):
        layout = QVBoxLayout()
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("+")
        remove_btn = QPushButton("-")
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        add_btn.clicked.connect(self.add_folder)
        remove_btn.clicked.connect(self.remove_folder)
        
        # 1. 初始化树状结构
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["词典文件列表", "脚本状态"])
        self.tree.setColumnWidth(0, 200) # 第一列宽一点
        self.tree.setColumnWidth(1, 50) 
        # 渲染文件夹树并处理复制逻辑
        self.refresh_tree()

        self.chk_use_filename = QCheckBox(_('CHECK_FILENAME_LABEL'))
        self.chk_export_media = QCheckBox(_('EXPORT_MEDIA'))
        self.chk_use_filename.setChecked(config.use_filename)
        self.chk_export_media.setChecked(config.export_media)
        
        chk_layout = QHBoxLayout()
        chk_layout.addWidget(self.chk_use_filename)
        chk_layout.addWidget(self.chk_export_media)
        
        btnbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, Qt.Orientation.Horizontal, self)
        btnbox.accepted.connect(self.accept)
        
        layout.addLayout(btn_layout)
        layout.addWidget(self.tree)
        layout.addLayout(chk_layout)
        layout.addWidget(btnbox)
        self.setLayout(layout)
    def refresh_tree(self):
        """
        刷新树形菜单，使用 os.walk 深度扫描所有子目录中的 mdx
        """
        self.tree.clear()
        
        for folder in self._current_folders:
            if not os.path.isdir(folder):
                # 文件夹不存在或被删除
                err_node = QTreeWidgetItem(self.tree)
                err_node.setText(0, f"📁 {folder} (失效)")
                err_node.setForeground(0, QBrush(QColor("red")))
                err_node.setData(0, Qt.ItemDataRole.UserRole, folder)
                continue
                
            # 添加根文件夹节点
            folder_node = QTreeWidgetItem(self.tree)
            folder_node.setText(0, f"📁 {folder}")
            folder_node.setData(0, Qt.ItemDataRole.UserRole, folder)
            folder_node.setExpanded(False) # 默认不展开，防止文件太多卡顿
            
            try:
                # 使用 os.walk 递归遍历所有子文件夹
                for root_dir, dirs, files in os.walk(folder):
                    for file in files:
                        if file.lower().endswith('.mdx'):
                            # mdx 文件的绝对路径
                            mdx_path = os.path.join(root_dir, file)
                            
                            # 在同一层级（root_dir）查找对应的 .py 文件
                            py_name = file[:-4] + '.py'
                            py_path = os.path.join(root_dir, py_name)
                            
                            # 获取相对路径，让 UI 显示更好看 (比如 "OALD\oald.mdx")
                            display_name = os.path.relpath(mdx_path, folder)
                            
                            mdx_node = QTreeWidgetItem(folder_node)
                            mdx_node.setText(0, f"📄 {display_name}")
                            
                            # 检查同级目录下是否有 .py
                            if os.path.exists(py_path):
                                mdx_node.setText(1, "√")
                                mdx_node.setForeground(1, QBrush(QColor("green")))
                                
                                # 处理并拷贝自定义的 py 脚本
                                process_and_copy_custom_py(mdx_path, py_path, self.plugin_dict_folder)
                            else:
                                mdx_node.setText(1, " ")
                                mdx_node.setForeground(1, QBrush(QColor("gray")))
            except Exception:
                continue

    def add_folder(self):
        dir_ = QFileDialog.getExistingDirectory(
            self,
            caption=u"Select Folder",
            directory=config.last_folder,
            options=QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks)
        if dir_:
            # 查重并添加
            if dir_ not in self._current_folders:
                self._current_folders.append(dir_)
                logger.info(f"添加本地词典文件夹: [{dir_}]")
                self.refresh_tree()
            config.update({'last_folder': dir_})

    def remove_folder(self):
        item = self.tree.currentItem()
        if not item:
            return
            
        # 如果选中的是子节点(文件)，找到它的父节点(文件夹)
        if item.parent():
            item = item.parent()
            
        folder_path = item.data(0, Qt.ItemDataRole.UserRole)
        if folder_path in self._current_folders:
            # 【完美逻辑】：统一使用深度反向清理
            try:
                # 统一转换为系统标准路径（处理大小写和正反斜杠问题）
                norm_folder = os.path.normcase(os.path.normpath(folder_path))
                # 保证文件夹路径以分隔符结尾，防止 "C:\Dict" 匹配到 "C:\Dictionary"
                if not norm_folder.endswith(os.sep):
                    norm_folder += os.sep

                for file in os.listdir(self.plugin_dict_folder):
                    if file.lower().endswith('.py') and file != '__init__.py':
                        dest_py_path = os.path.join(self.plugin_dict_folder, file)
                        try:
                            with open(dest_py_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            
                            # 提取脚本里的 DICT_PATH 路径
                            match = re.search(r"DICT_PATH\s*=\s*[rR]?['\"](.*?)['\"]", content)
                            if match:
                                dict_path_in_py = match.group(1).replace('\\\\', '\\')
                                norm_dict_path = os.path.normcase(os.path.normpath(dict_path_in_py))
                                
                                # 【关键修复】：只要词典的绝对路径以被移除的文件夹开头，说明它属于这个文件夹(或子文件夹)，直接干掉！
                                if norm_dict_path.startswith(norm_folder):
                                    os.remove(dest_py_path)
                                    logger.info(f"级联清理失效配置脚本 | 脚本文件: [{file}] | 关联目录: [{norm_folder}]")
                        except Exception:
                            pass
            except Exception:
                pass

            # 最后，从列表中移除并刷新界面树
            self._current_folders.remove(folder_path)
            logger.info(f"移除本地词典文件夹: [{folder_path}]")
            self.refresh_tree()
    @property
    def dirs(self):
        '''dictionary folders list'''
        # 直接返回维护的列表
        return self._current_folders

    def accept(self):
        '''ok button clicked'''
        self.save()
        super(FoldersManageDialog, self).accept()

    def save(self):
        '''save config to file'''
        data = {
            'dirs': self.dirs,
            'use_filename': self.chk_use_filename.isChecked(),
            'export_media': self.chk_export_media.isChecked()
        }
        config.update(data)