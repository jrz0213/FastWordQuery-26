# -*- coding:utf-8 -*-
from ..context import config
from ..service import service_manager, service_pool
from ..service.base import LocalService
from ..utils.logger import logger

class OptionsController:
    """
    选项面板的控制器 (Controller)
    专门负责处理所有非 GUI 的底层业务逻辑：读写配置、扫描词典、查询状态等。
    """
    def __init__(self):
        self.dict_services = {'local': [], 'web': []}

    def get_last_model_id(self):
        return config.last_model_id

    def get_maps(self, model_id):
        return config.get_maps(model_id)

    def load_services(self):
        """扫描并加载所有激活的词典服务，生成供 UI 使用的数据结构"""
        dicts = config.dicts
        self.dict_services = {'local': [], 'web': []}
        local_count = 0
        web_count = 0

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
                
        for clazz in service_manager.web_services:
            if dicts.get(clazz.__unique__, dict()).get('enabled', True):
                service = service_pool.get(clazz.__unique__)
                if service and service.support:
                    self.dict_services['web'].append({
                        'title': service.title,
                        'unique': service.unique
                    })
                    web_count += 1
                service_pool.put(service)
                
        logger.info(f"选项面板加载服务完毕 | 本地词典: {local_count} 个, 网络词典: {web_count} 个")
        return self.dict_services

    def check_dict_status(self):
        """轮询检查后台排队建立的词典数据库状态"""
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
        """根据词典唯一ID获取其支持的导出字段"""
        fields = []
        service = service_pool.get(unique_id)
        if service and service.support and service.fields:
            fields = service.fields
        service_pool.put(service)
        return fields

    def save_config(self, current_model, tabs_data):
        """将前端 UI 拼装好的数据写入配置"""
        if not current_model:
            return
        data = dict()
        current_model_id = str(current_model['id'])
        data[current_model_id] = tabs_data
        data['last_model'] = current_model['id']
        
        logger.info(f"保存查询选项配置 | 目标模型: [{current_model['name']}] | 包含标签页: {len(tabs_data['list'])} 个")
        config.update(data)

    def is_logging_enabled(self):
        """获取当前日志系统状态"""
        from ..utils import logger as logger_module
        return getattr(logger_module, 'ENABLE_LOGGING', False)

    def toggle_logging(self):
        """切换日志系统开关"""
        from ..utils import logger as logger_module
        current_state = self.is_logging_enabled()
        new_state = not current_state
        if hasattr(logger_module, 'set_logging_state'):
            logger_module.set_logging_state(new_state)
        return new_state