# -*- coding:utf-8 -*-
#
# Copyright (C) 2018 sthoo <sth201807@gmail.com>
#
# Support: Report an issue at https://github.com/sth2018/FastWordQuery/issues
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version; http://www.gnu.org/copyleft/gpl.html.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# 【修改】：使用 Python 3 原生的队列，弃用旧版兼容组件
from queue import Queue, Empty
from ..utils.logger import logger


class ServicePool(object):
    """
    Service instance pool
    """
    # 【新增】：每个词典服务最大允许并发实例数量，防止内存泄漏和 SQLite 文件锁死
    MAX_INSTANCES = 5 

    def __init__(self, manager):
        self.pools = {}
        self.instance_counts = {}  # 记录各个词典服务已创建的实例数量
        self.manager = manager
        
    def get(self, unique):
        if unique not in self.pools:
            self.pools[unique] = Queue()
            self.instance_counts[unique] = 0

        queue = self.pools[unique]

        # 如果当前该词典创建的实例数尚未达到上限，我们可以尝试快速获取
        if self.instance_counts[unique] < self.MAX_INSTANCES:
            try:
                # 0.1 秒内如果拿到空闲实例，直接复用
                return queue.get(True, timeout=0.1)
            except Empty:
                # 如果没拿到，且没达到上限，则安全地实例化一个新的服务对象
                service = self.manager.get_service(unique)
                if service:
                    self.instance_counts[unique] += 1
                    logger.info(f"服务池扩容 | 创建新的词典实例: [{unique}] | 当前实例总数: {self.instance_counts[unique]}/{self.MAX_INSTANCES}")
                return service
        else:
            # 【核心修复】：如果实例数已达最大值，说明当前词典极度繁忙，必须阻塞等待其他线程归还实例
            # 绝对不能再无脑创建新实例撑爆内存
            return queue.get(True) 
    
    def put(self, service):
        if service is None:
            return
        unique = service.unique
        if unique not in self.pools:
            self.pools[unique] = Queue()
            self.instance_counts[unique] = 1 
            
        self.pools[unique].put(service)
        
    def clean(self):
        """清空服务池缓存"""
        self.pools = {}
        self.instance_counts = {}
        logger.info("服务池已清空释放")