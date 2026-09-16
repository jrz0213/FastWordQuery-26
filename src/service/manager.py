import inspect
import os
import importlib
import traceback  # 【新增】：用于提取详细的错误堆栈信息
from hashlib import md5

from .base import LocalService, MdxService, StardictService, WebService, service_wrap
from ..context import config
# 引入全局日志对象
from ..utils.logger import logger


class ServiceManager(object):
    """
    Query service class manager
    """

    def __init__(self):
        self.update_services()

    @property
    def services(self):
        return self.web_services + self.local_services

    def update_services(self):
        logger.info("开始更新并重新扫描所有词典服务...")
        
        # ===================================================
        # 🌟 核心修改：扫描外部目录，若发现同名 .py，则自动复制并覆盖内部
        # ===================================================
        self._sync_external_scripts()
        
        # 优先扫描并加载自定义脚本服务，获取成功加载的脚本名称列表
        self.web_services, self.local_custom_services, self.loaded_scripts = self._get_services_from_files()
        
        # 将成功加载的脚本列表传入，以便在扫描本地词典时提供 Fallback 降级机制
        self.mdx_services, self.star_dict_services = self._get_available_local_services(self.loaded_scripts)
        
        # combine the customized local services into local services
        self.local_services = self.mdx_services + self.star_dict_services + self.local_custom_services
        
        logger.info(f"服务更新完成 | 共加载: 网络词典 {len(self.web_services)} 个, 本地词典 {len(self.local_services)} 个 (含自定义 {len(self.local_custom_services)} 个)")

    def _sync_external_scripts(self):
        """自动从外部词典目录同步 .py 到内部 dict 目录并进行覆盖"""
        import shutil
        service_path = u'dict'
        internal_dict_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), service_path)
        
        if not os.path.exists(internal_dict_path):
            os.makedirs(internal_dict_path)
            
        for ext_dir in config.dirs:
            if not os.path.exists(ext_dir):
                continue
            for dirpath, _, filenames in os.walk(ext_dir):
                for filename in filenames:
                    if filename.lower().endswith('.py'):
                        ext_py = os.path.join(dirpath, filename)
                        int_py = os.path.join(internal_dict_path, filename)
                        try:
                            # 如果内部不存在该文件，或者外部文件的修改时间更新，则强制覆盖
                            if not os.path.exists(int_py) or os.path.getmtime(ext_py) > os.path.getmtime(int_py):
                                shutil.copy2(ext_py, int_py)
                                logger.info(f"同步外部脚本并覆盖内部同名文件: [{filename}]")
                        except Exception as e:
                            logger.error(f"同步外部脚本失败: [{filename}] | 错误: {str(e)}")

    def get_service(self, unique):
        # webservice unique: class name
        # mdxservice unique: md5 of dict filepath
        for each in self.services:
            if each.__unique__ == unique:
                try:
                    # 尝试实例化该词典服务（无论是默认的还是自定义的脚本）
                    service = each()
                    service.unique = unique
                    return service
                except Exception as e:
                    import traceback
                    error_details = traceback.format_exc()
                    logger.error(f"[服务调度] 初始化自定义脚本或词典服务失败，已安全剔除 | Unique: [{unique}] | 错误信息: {str(e)}\n【详细错误堆栈】:\n{error_details}")
                    # 返回 None，GUI 层（options.py）判断为 None 就会自动跳过，不再引发崩溃
                    return None

    def _get_services_from_files(self, *args):
        """
        get service from service packages, available type is
        WebService, LocalService
        """
        service_path = u'dict'
        web_services, local_custom_services = list(), list()
        loaded_scripts = set()
        mypath = os.path.join(os.path.dirname(os.path.realpath(__file__)), service_path)
        
        logger.info(f"扫描自定义词典脚本目录: [{mypath}]")
        
        files = [
            f for f in os.listdir(mypath) \
            if f not in ('__init__.py') and \
            f.endswith('.py') and \
            not os.path.isdir(mypath+os.sep+f)
        ]
        base_class = (
            WebService, 
            LocalService,
            MdxService, 
            StardictService
        )
        
        for f in files:
            try:
                module = importlib.import_module( 
                    u'.%s.%s' % (service_path, os.path.splitext(f)[0]), 
                    __package__
                )
                
                has_valid_service = False
                
                for name, clazz in inspect.getmembers(module, predicate=inspect.isclass):
                    if clazz in base_class:
                        continue
                    if not(issubclass(clazz, WebService) or issubclass(clazz, LocalService)):
                        continue
                    if getattr(clazz, '__register_label__', None) is None:
                        continue
                        
                    service = service_wrap(clazz, *args)
                    service.__title__ = getattr(clazz, '__register_label__', name)
                    service.__unique__ = name
                    service.__path__ = os.path.join(mypath, f)
                    
                    if issubclass(clazz, WebService):
                        web_services.append(service)
                        logger.info(f"成功加载网络词典/服务: [{service.__title__}] -> 文件: {f}")
                        has_valid_service = True
                        
                    # get the customized local services
                    if issubclass(clazz, LocalService):
                        local_custom_services.append(service)
                        logger.info(f"成功加载自定义本地词典: [{service.__title__}] -> 文件: {f}")
                        has_valid_service = True
                
                # 如果脚本内有合法的服务类注册，则记录为成功加载的脚本
                if has_valid_service:
                    loaded_scripts.add(f)
                        
            except Exception as e:
                # 【修改】：使用 traceback 获取完整的报错行号和错误类型，方便排查脚本 bug
                error_details = traceback.format_exc()
                logger.error(f"加载自定义词典脚本失败: [{f}] | 错误信息: {str(e)}\n【详细错误堆栈】:\n{error_details}")
                
        web_services = sorted(web_services, key=lambda service: service.__title__)
        local_custom_services = sorted(local_custom_services, key=lambda service: service.__title__)
        
        return web_services, local_custom_services, loaded_scripts

    def _get_available_local_services(self, loaded_scripts):
        '''
        available local dictionary services
        '''
        mdx_services = list()
        star_dict_services = list()
        logger.info("扫描本地词典目录 (配置的文件夹)...")
        
        for each in config.dirs:
            for dirpath, dirnames, filenames in os.walk(each):
                for filename in filenames:
                    try:
                        service = None
                        dict_path = os.path.join(dirpath, filename)
                        
                        # MDX
                        if MdxService.check(dict_path):
                            # 检测是否存在同名 .py
                            py_name = filename[:-4] + '.py'
                            py_path = os.path.join(dirpath, py_name)
                            
                            if os.path.exists(py_path):
                                # Fallback降级机制：如果脚本存在，且在之前的动态加载中被记录为成功，才跳过默认封装
                                if py_name in loaded_scripts:
                                    logger.info(f"检测到专属配置文件且加载成功，跳过默认 MDX 加载: [{filename}]")
                                    continue
                                else:
                                    logger.warning(f"专属配置文件 [{py_name}] 加载失败或未就绪，触发降级(Fallback)，使用默认 MDX 解析: [{filename}]")
                                
                            service = service_wrap(MdxService, dict_path)
                            service.__unique__ = md5(str(dict_path).encode('utf-8')).hexdigest()
                            mdx_services.append(service)
                            logger.info(f"成功发现本地 MDX 词典: [{filename}]")
                            
                        # Stardict    
                        elif StardictService.check(dict_path):
                            service = service_wrap(StardictService, dict_path)
                            service.__unique__ = md5(str(dict_path[:-4]).encode('utf-8')).hexdigest()
                            star_dict_services.append(service)
                            logger.info(f"成功发现本地 Stardict 词典: [{filename}]")
                            
                    except Exception as e:
                        # 【修改】：增加防崩溃保护和详细日志，防止某个损坏的文件中断整个扫描过程
                        error_details = traceback.format_exc()
                        logger.error(f"解析本地词典文件异常: [{filename}] | 错误信息: {str(e)}\n【详细错误堆栈】:\n{error_details}")
                        
        return mdx_services, star_dict_services
    
    
# ==========================================
# 🌟 新增：全局静默预热机制 (启动后3秒自动建库)
# ==========================================
from aqt import gui_hooks
from aqt.qt import QTimer

def _auto_prewarm_dictionaries():
    logger.info("[全局预热] Anki 配置加载完毕，延迟 3 秒后开始静默扫描和建库准备...")
    try:
        # 预先扫描所有词典文件路径
        mgr = ServiceManager()
        
        # 遍历本地词典，预先实例化它们以触发 base.py 中的 _get_builder 
        # 从而把任务全部送进 _DictBuilderQueueThread 后台线程
        count = 0
        for svc_wrap in mgr.local_services:
            try:
                svc_wrap()  # 触发 MdxService/StardictService 的 __init__
                count += 1
            except Exception:
                pass
                
        logger.info(f"[全局预热] 分发完成！共触发 {count} 个本地词典的后台状态检测。")
    except Exception as e:
        logger.error(f"[全局预热] 异常: {str(e)}")

def _on_profile_loaded():
    # 延迟 10000 毫秒后执行静默预热，避开 Anki 刚启动时的卡顿高峰
    QTimer.singleShot(10000, _auto_prewarm_dictionaries)

# 将预热函数挂载到 Anki 的“配置打开完成”钩子上
gui_hooks.profile_did_open.append(_on_profile_loaded)