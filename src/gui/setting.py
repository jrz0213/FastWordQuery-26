

from aqt.qt import *

from ..context import config
from ..lang import _
from .base import Dialog

__all__ = ['SettingDialog']


class SettingDialog(Dialog):
    '''
    Setting window, some golbal params for query function.
    '''

    def __init__(self, parent, title=u'Setting'):
        super(SettingDialog, self).__init__(parent, title)
        self.setFixedWidth(400)
        self.check_force_update = None
        self.check_ignore_accents = None
        self.input_thread_number = None
        self.build()

    def build(self):
        # 1. 创建最外层的主布局 (负责把 滚动区 和 底部按钮 上下分开)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10) # 可选：设置边缘留白

        # 2. 创建滚动区域
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True) # 【关键】让内部的 Widget 自动拉伸适应宽度
        scroll_area.setFrameShape(QFrame.Shape.NoFrame) # 去掉滚动区域自带的边框，看起来更融洽

        # 3. 创建一个用来装所有设置项的“内容容器 (Widget)”
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        # ============ 下面开始往 content_layout 里塞你的控件 ============
        check_force_update = QCheckBox(_("FORCE_UPDATE"))
        check_force_update.setChecked(config.force_update)
        content_layout.addWidget(check_force_update)
        content_layout.addSpacing(10)

        check_ignore_accents = QCheckBox(_("IGNORE_ACCENTS"))
        check_ignore_accents.setChecked(config.ignore_accents)
        content_layout.addWidget(check_ignore_accents)
        content_layout.addSpacing(10)

        check_ighore_mdx_wordcase = QCheckBox(_("IGNORE_MDX_WORDCASE"))
        check_ighore_mdx_wordcase.setChecked(config.ignore_mdx_wordcase)
        content_layout.addWidget(check_ighore_mdx_wordcase)
        content_layout.addSpacing(10)

        hbox_thread = QHBoxLayout()
        input_thread_number = QSpinBox(parent=self)
        input_thread_number.setRange(1, 120)
        input_thread_number.setValue(config.thread_number)
        input_label_thread = QLabel(_("THREAD_NUMBER") + ":", parent=self)
        hbox_thread.addWidget(input_label_thread)
        hbox_thread.setStretchFactor(input_label_thread, 1)
        hbox_thread.addWidget(input_thread_number)
        hbox_thread.setStretchFactor(input_thread_number, 2)
        content_layout.addLayout(hbox_thread)

        hbox_cloze = QHBoxLayout()
        input_cloze_str = QLineEdit()
        input_cloze_str.setText(config.cloze_str)
        input_label_cloze = QLabel(_("CLOZE_WORD_FORMAT") + ":", parent=self)
        hbox_cloze.addWidget(input_label_cloze)
        hbox_cloze.setStretchFactor(input_label_cloze, 1)
        hbox_cloze.addWidget(input_cloze_str)
        hbox_cloze.setStretchFactor(input_cloze_str, 2)
        content_layout.addLayout(hbox_cloze)

        hbox_sound = QHBoxLayout()
        input_sound_str = QLineEdit()
        input_sound_str.setText(config.sound_str)
        input_label_sound = QLabel(_("SOUND_FORMAT") + ":", parent=self)
        hbox_sound.addWidget(input_label_sound)
        hbox_sound.setStretchFactor(input_label_sound, 1)
        hbox_sound.addWidget(input_sound_str)
        hbox_sound.setStretchFactor(input_sound_str, 2)
        content_layout.addLayout(hbox_sound)

        content_layout.addStretch(1) 


        scroll_area.setWidget(content_widget)


        main_layout.addWidget(scroll_area)


        hbox_btns = QHBoxLayout()
        okbtn = QDialogButtonBox(parent=self)
        okbtn.setStandardButtons(QDialogButtonBox.StandardButton.Ok)
        okbtn.clicked.connect(self.accept)
        resetbtn = QDialogButtonBox(parent=self)
        resetbtn.setStandardButtons(QDialogButtonBox.StandardButton.Reset)
        resetbtn.clicked.connect(self.reset)
        
        hbox_btns.addStretch(1) 
        hbox_btns.addWidget(resetbtn)
        hbox_btns.addWidget(okbtn)


        main_layout.addSpacing(10)
        main_layout.addLayout(hbox_btns)

        self.check_force_update = check_force_update
        self.check_ignore_accents = check_ignore_accents
        self.check_ighore_mdx_wordcase = check_ighore_mdx_wordcase
        self.input_thread_number = input_thread_number
        self.input_cloze_str = input_cloze_str
        self.input_sound_str = input_sound_str

        self.setLayout(main_layout)

    def accept(self):
        self.save()
        super(SettingDialog, self).accept()

    def reset(self):
        data = {
            'force_update': False,
            'ignore_accents': False,
            'ignore_mdx_wordcase': False,
            'thread_number': 16,
            'cloze_str': '{{c1::%s}}',
            'sound_str': '[sound:{0}]'
        }
        config.update(data)
        self.check_force_update.setChecked(config.force_update)
        self.check_ignore_accents.setChecked(config.ignore_accents)
        self.check_ighore_mdx_wordcase.setChecked(config.ignore_mdx_wordcase)
        self.input_thread_number.setValue(config.thread_number)
        self.input_cloze_str.setText(config.cloze_str)
        self.input_sound_str.setText(config.sound_str)

    def save(self):
        data = {
            'force_update': self.check_force_update.isChecked(),
            'ignore_accents': self.check_ignore_accents.isChecked(),
            'ignore_mdx_wordcase': self.check_ighore_mdx_wordcase.isChecked(),
            'thread_number': self.input_thread_number.value(),
            'cloze_str': self.input_cloze_str.text(),
            'sound_str': self.input_sound_str.text()
        }
        config.update(data)
