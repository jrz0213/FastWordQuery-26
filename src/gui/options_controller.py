# -*- coding:utf-8 -*-
import concurrent.futures
from ..context import config
from ..service import service_manager, service_pool
from ..service.base import LocalService
from ..utils.logger import logger

class OptionsController:
    """
    选项面板的控制器 (Controller)
    """
    def __init__(self):
        self.dict_services = {'local': [], 'web': []}

    def get_last_model_id(self):
        return config.last_model_id

    def get_maps(self, model_id):
        return config.get_maps(model_id)

    def load_services(self):
        """多线程并发扫描并加载所有激活的词典服务"""
        dicts = config.dicts
        self.dict_services = {'local': [], 'web': []}
        local_count = 0
        web_count = 0

        # 1. 本地词典加载 (纯内存映射读取，极速，无需多线程)
        for clazz in service_manager.local_services:
            if dicts.get(clazz.__unique__, dict()).get('enabled', True):
                service = service_pool.get(clazz.__unique__)
                if service and service.support:
                    path = getattr(service, 'dict_path', None)
                    status = LocalService.get_db_status(path) if path else 'ready'
                    self.dict_services['local'].append({
                        'title': service.title,
                        'unique': service.unique,
                        'status': status,
                        'path': path
                    })
                    local_count += 1
                service_pool.put(service)
                
        # 2. 网络词典加载 (高延迟 I/O，使用多线程并发池)
        web_classes_to_load = [
            clazz for clazz in service_manager.web_services 
            if dicts.get(clazz.__unique__, dict()).get('enabled', True)
        ]
        
        def check_web_service(clazz):
            try:
                service = service_pool.get(clazz.__unique__)
                res = None
                if service and service.support:
                    res = {
                        'title': service.title,
                        'unique': service.unique
                    }
                service_pool.put(service)
                return res
            except Exception as e:
                logger.error(f"并发探测网络词典失败: [{clazz.__unique__}] | 错误: {e}")
                return None

        # 提取用户的配置并发数
        max_workers = getattr(config, 'thread_number', 16) 
        logger.info(f"启动网络词典并发探测 | 线程池大小: {max_workers} | 待探测数量: {len(web_classes_to_load)}")
        
        if web_classes_to_load:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(check_web_service, cls) for cls in web_classes_to_load]
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        self.dict_services['web'].append(result)
                        web_count += 1

        logger.info(f"选项面板加载服务完毕 | 本地词典: {local_count} 个, 网络词典: {web_count} 个")
        return self.dict_services

    def check_dict_status(self):
        """轮询检查后台排队建立的词典数据库状态 (依然保留，用于监控后台建库进度)"""
        all_ready = True
        status_changed = False

        for service in self.dict_services.get('local', []):
            if service.get('status') == 'building':
                current_status = LocalService.get_db_status(service.get('path')) if service.get('path') else 'ready'
                if current_status == 'ready':
                    service['status'] = 'ready'
                    status_changed = True
                    logger.info(f"后台队列监控 | 词典建库完成: [{service['title']}]")
                else:
                    all_ready = False

        return status_changed, all_ready

    def get_service_fields(self, unique_id):
        fields = []
        service = service_pool.get(unique_id)
        if service and service.support and service.fields:
            fields = service.fields
        service_pool.put(service)
        return fields

    def save_config(self, current_model, tabs_data):
        if not current_model: return
        data = dict()
        current_model_id = str(current_model['id'])
        data[current_model_id] = tabs_data
        data['last_model'] = current_model['id']
        logger.info(f"保存查询选项配置 | 目标模型: [{current_model['name']}] | 包含标签页: {len(tabs_data['list'])} 个")
        config.update(data)
    def is_logging_enabled(self):
        """从全局配置中获取日志系统状态，默认关闭"""
        from ..context import config
        return getattr(config, 'enable_logging', False)

    def toggle_logging(self):
        """切换日志系统开关，并永久保存到配置文件"""
        from ..context import config
        # 精准导入所需的函数，避免命名空间冲突
        from ..utils.logger import set_logging_state
        
        current_state = self.is_logging_enabled()
        new_state = not current_state
        
        # 1. 保存到本地配置，永久生效（重启不丢失）
        config.update({'enable_logging': new_state})
        
        # 2. 实时更新当前内存中的日志器状态
        set_logging_state(new_state)
            
        return new_state