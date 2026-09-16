import anki
import aqt
import aqt.models
from aqt import sip
from anki.utils import is_mac
from aqt import mw
from aqt.qt import *
from aqt.studydeck import StudyDeck

from ..constants import Endpoint
from ..lang import _, _sl
from ..utils import get_icon, get_model_byId
from .base import WIDGET_SIZE, Dialog
from .setting import SettingDialog

from .options_controller import OptionsController
from .service_loader import ServiceLoaderThread
from ..utils.logger import logger

__all__ = ['OptionsDialog']

class NoScrollComboBox(QComboBox):
    """强制忽略鼠标滚轮事件的下拉框"""
    def wheelEvent(self, event):
        event.ignore()

class OptionsDialog(Dialog):
    '''
    query options window
    setting query dictionary and fileds (GUI Only)
    '''

    __slot__ = ['after_build']
    _signal = pyqtSignal(str)

    _NULL_ICON = get_icon('null.png')
    _OK_ICON = get_icon('ok.png')

    def __init__(self, parent, title=u'Options', model_id=-1):
        super(OptionsDialog, self).__init__(parent, title)
        
        self.controller = OptionsController()
        
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)
        
        self.model_id = model_id if model_id != -1 else self.controller.get_last_model_id()
        self.current_model = None
        self.tabs = []
        
        target_width = WIDGET_SIZE.dialog_width
        target_height = 400
        if self.model_id:
            self.current_model = get_model_byId(mw.col.models, self.model_id)
            if self.current_model:
                target_height = min(max(3, len(self.current_model['flds']) + 1), 14) * WIDGET_SIZE.map_max_height + WIDGET_SIZE.dialog_height_margin
        self.resize(target_width, target_height)

        self.loading_label = QLabel("正在扫描词典，请稍候...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("font-size: 16px; color: #666; font-weight: bold;")
        self.main_layout.addWidget(self.loading_label)

        self.loader_thread = ServiceLoaderThread(self.controller)
        self.loader_thread.finished_signal.connect(self._on_services_loaded)
        self.loader_thread.start()

        if hasattr(mw, 'dict_signals'):
            mw.dict_signals.status_changed.connect(self.check_dict_status)
    def _on_services_loaded(self, dict_services):
        self.dict_services = dict_services
        
        import gc
        from ..service.base import LocalService
        from hashlib import md5
        
        # 🌟 建立 [UI Unique <-> 底层 MD5 Hash] 的智能映射表
        unique_to_hash = {}
        for obj in gc.get_objects():
            try:
                # 增加 try...except 捕获内存中的死对象（弱引用）
                if isinstance(obj, LocalService) and hasattr(obj, 'dict_path') and obj.dict_path:
                    path_key = obj.dict_path[:-4] if 'Stardict' in obj.__class__.__name__ else obj.dict_path
                    obj_hash = md5(str(path_key).encode('utf-8')).hexdigest()
                    unique_to_hash[obj.unique] = obj_hash
            except ReferenceError:
                continue
                
        for service in self.dict_services.get('local', []):
            ui_unique = service.get('unique')
            if ui_unique:
                # 使用映射表找出它真实的底层 MD5 暗号
                real_hash = unique_to_hash.get(ui_unique, ui_unique)
                
                real_status = LocalService._build_status.get(real_hash, "uninitialized")
                has_builder = LocalService._mdx_builders.get(real_hash) is not None
                
                if has_builder or real_status == "ready":
                    service['status'] = "ready"
                elif real_status in ["checking", "building"]:
                    service['status'] = real_status
                    
        if hasattr(self, 'loading_label') and self.loading_label:
            self.main_layout.removeWidget(self.loading_label)
            self.loading_label.deleteLater()
            self.loading_label = None

        self._after_build('after_build')
        self.loader_thread.deleteLater()



    def _after_build(self, s):
        if s != 'after_build':
            return

        models_layout = QHBoxLayout()
        mdx_button = QPushButton(_('DICTS_FOLDERS'))
        mdx_button.clicked.connect(self.show_fm_dialog)
        self.models_button = QPushButton(_('CHOOSE_NOTE_TYPES'))
        self.models_button.clicked.connect(self.btn_models_pressed)
        models_layout.addWidget(mdx_button)
        models_layout.addWidget(self.models_button)
        self.main_layout.addLayout(models_layout)
        
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabBar(CTabBar())
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #c3c3c3; }
            """)
        tab_corner = QWidget()
        tab_corner_layout = QHBoxLayout()
        tab_corner_layout.setSpacing(1)
        tab_corner_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        tab_corner_layout.setContentsMargins(0, 0, 0, 0)
        tab_corner.setLayout(tab_corner_layout)
        tab_add_button = QToolButton(self)
        tab_add_button.setIcon(get_icon('add.png'))
        tab_set_button = QToolButton(self)
        tab_set_button.setIcon(get_icon('setting.png'))
        tab_corner_layout.addWidget(tab_set_button)
        tab_corner_layout.addWidget(tab_add_button)
        self.tab_widget.setCornerWidget(tab_corner)
        
        tab_set_button.clicked.connect(self.show_dm_dialog)
        tab_add_button.clicked.connect(self.addTab)
        self.tab_widget.tabCloseRequested.connect(self.removeTab)
        self.main_layout.addWidget(self.tab_widget)
        
        bottom_layout = QHBoxLayout()
        paras_btn = QPushButton(_('SETTINGS'))
        paras_btn.clicked.connect(self.show_paras)
        about_btn = QPushButton(_('ABOUT'))
        about_btn.clicked.connect(self.show_about)
        
        self.log_toggle_btn = QPushButton()
        self.update_log_btn_text()
        self.log_toggle_btn.clicked.connect(self.toggle_logging)

        home_label = QLabel('<a href="{url}">User Guide</a>'.format(url=Endpoint.user_guide))
        home_label.setOpenExternalLinks(True)
        btnbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, Qt.Orientation.Horizontal, self)
        btnbox.accepted.connect(self.accept)
        
        bottom_layout.addWidget(paras_btn)
        bottom_layout.addWidget(about_btn)
        bottom_layout.addWidget(self.log_toggle_btn)
        bottom_layout.addWidget(home_label)
        bottom_layout.addWidget(btnbox)
        self.main_layout.addLayout(bottom_layout)
        
        if self.current_model:
            self.models_button.setText(u'%s [%s]' % (_('CHOOSE_NOTE_TYPES'), self.current_model['name']))
            self.build_tabs_layout()

    def update_log_btn_text(self):
        if self.controller.is_logging_enabled():
            self.log_toggle_btn.setText("日志:运行中")
        else:
            self.log_toggle_btn.setText("日志:已暂停")

    def toggle_logging(self):
        self.controller.toggle_logging()
        self.update_log_btn_text()

    def check_dict_status(self, hash_key=None, status=None):
        if not hasattr(self, 'dict_services'):
            return

        import gc
        from ..service.base import LocalService
        from hashlib import md5
        from ..utils.logger import logger
        
        # 🌟 收到信号时，将底层的 MD5 反向翻译回 UI 的 Unique
        target_unique = hash_key
        for obj in gc.get_objects():
            try:
                # 增加 try...except 捕获内存中的死对象（弱引用）
                if isinstance(obj, LocalService) and hasattr(obj, 'dict_path') and obj.dict_path:
                    path_key = obj.dict_path[:-4] if 'Stardict' in obj.__class__.__name__ else obj.dict_path
                    obj_hash = md5(str(path_key).encode('utf-8')).hexdigest()
                    
                    if obj_hash == hash_key:
                        target_unique = obj.unique
                        logger.info(f"[UI 信号中转] 成功将底层 Hash [{hash_key}] 翻译为 UI Unique [{target_unique}]")
                        break
            except ReferenceError:
                continue
                    
        if target_unique and status:
            for service in self.dict_services.get('local', []):
                if service.get('unique') == target_unique:
                    service['status'] = status
                    break
                    
        for tab in self.tabs:
            tab.refresh_dict_combos(self.dict_services)
    def show_paras(self):
        dialog = SettingDialog(self, u'Setting')
        dialog.exec()
        dialog.destroy()

    def show_fm_dialog(self):
        self.accept()
        self.setResult(1001)

    def show_dm_dialog(self):
        self.accept()
        self.setResult(1002)

    def show_about(self):
        from .common import show_about_dialog
        show_about_dialog(self)

    def accept(self):
        self.save()
        super(OptionsDialog, self).accept()

    def btn_models_pressed(self):
        self.save()
        self.current_model = self.show_models()
        if self.current_model:
            self.build_tabs_layout()

    def build_tabs_layout(self):
        try:
            self.tab_widget.currentChanged.disconnect()
        except Exception:
            pass
        while len(self.tabs) > 0:
            self.removeTab(0, True)
            
        conf = self.controller.get_maps(self.current_model['id'])
        maps_list = {'list': [conf], 'def': 0} if isinstance(conf, list) else conf
        
        for maps in maps_list['list']:
            self.addTab(maps, False)
            
        self.tab_widget.currentChanged.connect(self.changedTab)
        self.changedTab(maps_list['def'])
        self.tab_widget.setCurrentIndex(maps_list['def'])
        
        self.resize(
            WIDGET_SIZE.dialog_width,
            min(max(3, len(self.current_model['flds']) + 1), 14) *
            WIDGET_SIZE.map_max_height + WIDGET_SIZE.dialog_height_margin)
        self.save()

    def addTab(self, maps=None, forcus=True):
        i = len(self.tabs)
        if isinstance(maps, list):
            maps = {'fields': maps, 'name': _('CONFIG_INDEX') % (i + 1)}
        tab = TabContent(self.current_model, maps['fields'] if maps else None,
                         self.dict_services, self.controller)
        self.tabs.append(tab)
        self.tab_widget.addTab(
            tab, maps['name'] if maps else _('CONFIG_INDEX') % (i + 1))
        if forcus:
            self.tab_widget.setCurrentIndex(i)

    def removeTab(self, i, forcus=False):
        if not forcus and len(self.tabs) <= 1:
            return
        tab = self.tabs[i]
        del self.tabs[i]
        self.tab_widget.removeTab(i)
        tab.destroy()

    def changedTab(self, i):
        for k in range(0, len(self.tabs)):
            self.tab_widget.setTabIcon(k, self._NULL_ICON)
        self.tab_widget.setTabIcon(i, self._OK_ICON)
        self.tabs[i].build_layout()

    def show_models(self):
        edit = QPushButton(_("MANAGE"), clicked=lambda: aqt.models.Models(mw, self))
        ret = StudyDeck(
            mw,
            names=lambda: sorted([n.name for n in mw.col.models.all_names_and_ids()]),
            accept=_("CHOOSE"),
            title=_('CHOOSE_NOTE_TYPES'),
            help="_notes",
            parent=self,
            buttons=[edit],
            cancel=True,
            geomKey="selectModel")
        if ret.name:
            model = mw.col.models.byName(ret.name)
            self.models_button.setText(u'%s [%s]' % (_('CHOOSE_NOTE_TYPES'), ret.name))
            return model

    def save(self):
        if not self.current_model:
            return
        maps_list = {'list': [], 'def': self.tab_widget.currentIndex()}
        for i, tab in enumerate(self.tabs):
            maps_list['list'].append({
                'fields': tab.data,
                'name': self.tab_widget.tabBar().tabText(i)
            })
        self.controller.save_config(self.current_model, maps_list)


class TabContent(QScrollArea):
    """Options tab content"""

    def __init__(self, model, conf, services, controller):
        super(TabContent, self).__init__()
        self._conf = conf
        self._model = model
        self._services = services
        self._controller = controller
        self._last_checkeds = None
        self._options = list()
        self._was_built = False
        
        dicts = QWidget(self)
        dicts.setLayout(QGridLayout())
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setWidget(dicts)
        self.dicts_layout = dicts.layout()

    def refresh_dict_combos(self, services):
        self._services = services
        for row in self._options:
            combo = row['dict_combo']
            current_unique = combo.itemData(combo.currentIndex())
            self.fill_dict_combo_options(combo, current_unique, self._services)

    def build_layout(self):
        if self._was_built:
            return
            
        del self._options[:]
        self._last_checkeds = None
        self._was_built = True

        model = self._model
        maps = self._conf

        f = QFont()
        f.setBold(True)
        labels = [u'＃', '', 'DICTS', 'DICT_FIELDS', '']
        for i, s in enumerate(labels):
            if s:
                label = QLabel(_(s))
                label.setFont(f)
                label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
                self.dicts_layout.addWidget(label, 0, i)

        self.ignore_all_check_btn = QCheckBox(_('SELECT_ALL'))
        self.ignore_all_check_btn.setFont(f)
        self.ignore_all_check_btn.setEnabled(True)
        self.ignore_all_check_btn.setChecked(True)
        self.dicts_layout.addWidget(self.ignore_all_check_btn, 0, 1)
        self.ignore_all_check_btn.clicked.connect(self.ignore_all_check_changed)

        self.skip_all_check_btn = QCheckBox(_('SELECT_ALL'))
        self.skip_all_check_btn.setFont(f)
        self.skip_all_check_btn.setEnabled(True)
        self.skip_all_check_btn.setChecked(True)
        self.dicts_layout.addWidget(self.skip_all_check_btn, 0, 4)
        self.skip_all_check_btn.clicked.connect(self.skip_all_check_changed)

        self.radio_group = QButtonGroup()
        for i, fld in enumerate(model['flds']):
            ord = fld['ord']
            name = fld['name']
            if maps:
                for j, each in enumerate(maps):
                    if each.get('fld_ord', -1) == ord or each.get('fld_name', '') == name:
                        each['fld_name'] = name
                        each['fld_ord'] = ord
                        self.add_dict_layout(j, **each)
                        break
                else:
                    self.add_dict_layout(i, fld_name=name, fld_ord=ord, word_checked=i == 0)
            else:
                self.add_dict_layout(i, fld_name=name, fld_ord=ord, word_checked=i == 0)

        self.ignore_all_update()
        self.skip_all_update()

    def add_dict_layout(self, i, **kwargs):
        word_checked = kwargs.get('word_checked', False)
        fld_name, fld_ord = kwargs.get('fld_name', ''), kwargs.get('fld_ord', '')
        dict_name, dict_unique, dict_fld_name, dict_fld_ord = (
            kwargs.get('dict_name', ''), kwargs.get('dict_unique', ''), 
            kwargs.get('dict_fld_name', ''), kwargs.get('dict_fld_ord', 0)
        )
        ignore, skip, cloze = kwargs.get('ignore', True), kwargs.get('skip_valued', True), kwargs.get('cloze_word', False)

        word_check_btn = QRadioButton(fld_name)
        word_check_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        word_check_btn.setCheckable(True)
        word_check_btn.setChecked(word_checked)
        self.radio_group.addButton(word_check_btn)
        
        dict_combo = NoScrollComboBox()
        dict_combo.setMinimumSize(WIDGET_SIZE.map_dict_width, 0)
        dict_combo.setMaximumSize(WIDGET_SIZE.map_dict_width, WIDGET_SIZE.map_max_height)
        dict_combo.setFocusPolicy(Qt.FocusPolicy.TabFocus | Qt.FocusPolicy.ClickFocus | Qt.FocusPolicy.StrongFocus)
        ignore = not self.fill_dict_combo_options(dict_combo, dict_unique, self._services) or ignore
        dict_unique = dict_combo.itemData(dict_combo.currentIndex())
        dict_combo.setEnabled(not word_checked and not ignore)
        
        field_combo = NoScrollComboBox()
        field_combo.setMinimumSize(WIDGET_SIZE.map_field_width, 0)
        field_combo.setMaximumSize(WIDGET_SIZE.map_field_width, WIDGET_SIZE.map_max_height)
        field_combo.setFocusPolicy(Qt.FocusPolicy.TabFocus | Qt.FocusPolicy.ClickFocus | Qt.FocusPolicy.StrongFocus)
        field_combo.setEnabled(not word_checked and not ignore)
        self.fill_field_combo_options(field_combo, dict_name, dict_unique, dict_fld_name, dict_fld_ord)

        ignore_check_btn = QCheckBox(_("NOT_DICT_FIELD"))
        ignore_check_btn.setEnabled(not word_checked)
        ignore_check_btn.setChecked(ignore)

        skip_check_btn = QCheckBox(_("SKIP_VALUED"))
        skip_check_btn.setEnabled(not word_checked and not ignore)
        skip_check_btn.setChecked(skip)

        cloze_check_btn = QCheckBox(_("CLOZE_WORD"))
        cloze_check_btn.setEnabled(not word_checked and not ignore)
        cloze_check_btn.setChecked(cloze)

        def radio_btn_checked():
            if self._last_checkeds:
                self._last_checkeds[0].setEnabled(True)
                ignore = self._last_checkeds[0].isChecked()
                for i in range(1, len(self._last_checkeds)):
                    self._last_checkeds[i].setEnabled(not ignore)

            word_checked = word_check_btn.isChecked()
            ignore_check_btn.setEnabled(not word_checked)
            ignore = ignore_check_btn.isChecked()
            dict_combo.setEnabled(not word_checked and not ignore)
            field_combo.setEnabled(not word_checked and not ignore)
            skip_check_btn.setEnabled(not word_checked and not ignore)
            cloze_check_btn.setEnabled(not word_checked and not ignore)
            if word_checked:
                self._last_checkeds = [ignore_check_btn, dict_combo, field_combo, skip_check_btn]

        word_check_btn.clicked.connect(radio_btn_checked)
        if word_checked:
            self._last_checkeds = None
            radio_btn_checked()

        def ignore_check_changed():
            word_checked = word_check_btn.isChecked()
            ignore = ignore_check_btn.isChecked()
            dict_combo.setEnabled(not word_checked and not ignore)
            field_combo.setEnabled(not word_checked and not ignore)
            skip_check_btn.setEnabled(not word_checked and not ignore)
            cloze_check_btn.setEnabled(not word_checked and not ignore)

        ignore_check_btn.stateChanged.connect(ignore_check_changed)
        ignore_check_btn.clicked.connect(self.ignore_all_update)
        skip_check_btn.clicked.connect(self.skip_all_update)

        def dict_combo_changed(index):
            self.fill_field_combo_options(
                field_combo, dict_combo.currentText(),
                dict_combo.itemData(index), field_combo.currentText(),
                field_combo.itemData(field_combo.currentIndex()))

        dict_combo.currentIndexChanged.connect(dict_combo_changed)

        self.dicts_layout.addWidget(word_check_btn, i + 1, 0)
        self.dicts_layout.addWidget(ignore_check_btn, i + 1, 1)
        self.dicts_layout.addWidget(dict_combo, i + 1, 2)
        self.dicts_layout.addWidget(field_combo, i + 1, 3)
        self.dicts_layout.addWidget(skip_check_btn, i + 1, 4)
        self.dicts_layout.addWidget(cloze_check_btn, i + 1, 5)

        self._options.append({
            'model': {'fld_name': fld_name, 'fld_ord': fld_ord},
            'word_check_btn': word_check_btn,
            'dict_combo': dict_combo,
            'field_combo': field_combo,
            'ignore_check_btn': ignore_check_btn,
            'skip_check_btn': skip_check_btn,
            'cloze_check_btn': cloze_check_btn
        })

    def fill_dict_combo_options(self, dict_combo, current_unique, services):
        dict_combo.clear()
        
        for service in services['local']:
            status = service.get('status', 'uninitialized')
            title = service.get('title', 'Unknown')
            
            is_selectable = True
            
            if status == 'building':
                display_title = "🔴 " + title + " (建库中)"
                is_selectable = False
            elif status == 'checking':
                display_title = "🟡 " + title + " (状态检测中)"
                is_selectable = False
            elif status == 'ready':
                display_title = "🟢 " + title
            else:
                display_title = "⚪ " + title + " (未就绪)"
                is_selectable = False
                
            dict_combo.addItem(display_title, userData=service['unique'])

            if not is_selectable:
                index = dict_combo.count() - 1
                model = dict_combo.model()
                item = model.item(index)
                if item:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)

        if len(services['local']) > 0:
            dict_combo.insertSeparator(dict_combo.count())

        for service in services['web']:
            dict_combo.addItem("🟢 " + service['title'], userData=service['unique'])

        def set_dict_combo_index():
            dict_combo.setCurrentIndex(0)
            if current_unique:
                for i in range(dict_combo.count()):
                    if dict_combo.itemData(i) == current_unique:
                        dict_combo.setCurrentIndex(i)
                        return True
            return False

        return set_dict_combo_index()

    def fill_field_combo_options(self, field_combo, dict_combo_text,
                                 dict_combo_itemdata, dict_fld_name,
                                 dict_fld_ord):
        field_combo.clear()
        field_combo.setEditable(False)
        if dict_combo_text in _sl('MDX_SERVER'):
            text = dict_fld_name if dict_fld_name else 'http://'
            field_combo.setEditable(True)
            field_combo.setEditText(text)
            field_combo.setFocus(Qt.FocusReason.MouseFocusReason)
        else:
            unique = dict_combo_itemdata
            fields = self._controller.get_service_fields(unique)
            field_combo.setCurrentIndex(0)
            for i, each in enumerate(fields):
                field_combo.addItem(each, userData=i)
                if each == dict_fld_name or i == dict_fld_ord:
                    field_combo.setCurrentIndex(i)

    @property
    def data(self):
        if not self._was_built:
            return self._conf
        maps = []
        for row in self._options:
            maps.append({
                'fld_name': row['model']['fld_name'],
                'fld_ord': row['model']['fld_ord'],
                'word_checked': row['word_check_btn'].isChecked(),
                'dict_name': row['dict_combo'].currentText().strip(),
                'dict_unique': row['dict_combo'].itemData(row['dict_combo'].currentIndex()),
                'dict_fld_name': row['field_combo'].currentText().strip(),
                'dict_fld_ord': row['field_combo'].itemData(row['field_combo'].currentIndex()),
                'ignore': row['ignore_check_btn'].isChecked(),
                'skip_valued': row['skip_check_btn'].isChecked(),
                'cloze_word': row['cloze_check_btn'].isChecked()
            })
        return maps

    def ignore_all_check_changed(self):
        b = self.ignore_all_check_btn.isChecked()
        for row in self._options:
            row['ignore_check_btn'].setChecked(b)

    def skip_all_check_changed(self):
        b = self.skip_all_check_btn.isChecked()
        for row in self._options:
            row['skip_check_btn'].setChecked(b)

    def ignore_all_update(self):
        b = True
        for row in self._options:
            if not row['ignore_check_btn'].isChecked():
                b = False
                break
        self.ignore_all_check_btn.setChecked(b)

    def skip_all_update(self):
        b = True
        for row in self._options:
            if not row['skip_check_btn'].isChecked():
                b = False
                break
        self.skip_all_check_btn.setChecked(b)


class CTabBar(QTabBar):
    def __init__(self, parent=None):
        super(CTabBar, self).__init__(parent)
        self.setTabsClosable(True)
        self.setMovable(False)
        self.setExpanding(False)
        self.setDrawBase(False)
        self._editor = QLineEdit(self)
        self._editor.setWindowFlags(Qt.WindowType.Popup)
        self._editor.setMaxLength(20)
        self._editor.editingFinished.connect(self.handleEditingFinished)
        self._editor.installEventFilter(self)

    def eventFilter(self, widget, event):
        bhide = False
        if event.type() == QEvent.Type.MouseButtonPress:
            if not self._editor.geometry().contains(event.globalPosition().toPoint()):
                bhide = True
        if not bhide:
            if event.type() == QEvent.Type.KeyPress:
                if event.key() == Qt.Key.Key_Escape:
                    bhide = True
        if bhide:
            self.hideEditor()
            return True
        return QTabBar.eventFilter(self, widget, event)

    def mouseDoubleClickEvent(self, event):
        index = self.tabAt(event.pos())
        if index >= 0:
            self.editTab(index)

    def editTab(self, index):
        rect = self.tabRect(index)
        self._editor.setFixedSize(rect.size())
        self._editor.move(self.parent().mapToGlobal(rect.topLeft()))
        self._editor.setText(self.tabText(index))
        if not self._editor.isVisible():
            self._editor.show()
        self._editor.selectAll()
        self._editor.setEnabled(True)
        self._editor.setFocus()

    def hideEditor(self):
        if self._editor.isVisible():
            self._editor.setEnabled(False)
            self._editor.clearFocus()
            self._editor.hide()

    def handleEditingFinished(self):
        index = self.currentIndex()
        if index >= 0:
            self.hideEditor()
            if self._editor.text():
                self.setTabText(index, self._editor.text())