# -*- coding:utf-8 -*-
from aqt.qt import *

class ServiceLoaderThread(QThread):
    """
    后台异步加载线程：专门用于并发加载网络与本地词典列表
    """
    # 定义发射信号，携带组装好的字典数据 (dict) 返回给主线程
    finished_signal = pyqtSignal(dict)
    
    def __init__(self, controller):
        super(ServiceLoaderThread, self).__init__()
        self.controller = controller
        
    def run(self):
        # 这里的耗时操作完全在后台执行，绝不会阻塞主界面的渲染
        dict_services = self.controller.load_services()
        # 数据加载完毕，发射信号通知主界面
        self.finished_signal.emit(dict_services)