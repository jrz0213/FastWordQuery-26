

import inspect
import os
import random
import re
import shutil
import sqlite3
import zlib
import logging
from logging.handlers import RotatingFileHandler
from collections import defaultdict
from functools import wraps
from hashlib import md5, sha1
import threading as _threading
import urllib.parse

import requests
from bs4 import BeautifulSoup

from aqt import mw
from aqt.qt import QMutex, QThread

from ..context import config
from ..lang import _cl
from ..libs import MdxBuilder, StardictBuilder
from ..utils import MapDict, wrap_css
from queue import Queue, Empty
from ..utils.logger import logger

# 🌟 引入我们写的模糊匹配引擎
from ..utils.fuzzy_match import process_fuzzy_media

__all__ = [
    'register', 'export', 'copy_static_file', 'with_styles', 'parse_html', 'service_wrap', 'get_hex_name',
    'Service', 'WebService', 'LocalService', 'MdxService', 'StardictService', 'QueryResult'
]

_default_ua = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 ' \
              '(KHTML, like Gecko) Chrome/70.0.3538.67 Safari/537.36'

# ========================================================
# 🌟 全局文件名安全清洗器：将特殊字符转换为绝对合法、防冲突的格式
# ========================================================
def sanitize_to_safe_encoding(filename):
    """
    将文件名转换为 Anki 和 HTML 双端绝对安全的编码格式，
    同时保留唯一性，不发生破坏性合并。
    """
    decoded = urllib.parse.unquote(filename)
    basename = os.path.basename(decoded.replace('\\', os.path.sep))
    
    mapping = {
        ' ': '-', '#': '_', '&': '_and_', '+': '_plus_', '=': '_eq_'
    }
    for k, v in mapping.items():
        basename = basename.replace(k, v)
        
    def safe_hex_encode(match):
        return f"_x{ord(match.group(0)):02X}_"
        
    # 仅允许：字母、数字、中文、点(.)、中划线(-)、下划线(_)
    safe_name = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5\.\-_]', safe_hex_encode, basename)
    return safe_name

def get_hex_name(prefix, val, suffix):
    ''' get sha1 hax name '''
    hex_digest = sha1(val.encode('utf-8')).hexdigest().lower()
    name = '.'.join(
        ['-'.join([prefix, hex_digest[:8], hex_digest[8:16], hex_digest[16:24], hex_digest[24:32], hex_digest[32:], ]),
         suffix, ])
    return name

def _is_method_or_func(object):
    return inspect.isfunction(object) or inspect.ismethod(object)

def register(labels):
    def _deco(cls):
        cls.__register_label__ = _cl(labels)
        methods = inspect.getmembers(cls, predicate=_is_method_or_func)
        exports = []
        for method_name, method_func in methods:
            attrs = getattr(method_func, '__export_attrs__', None)
            if attrs:
                exports.append((getattr(method_func, '__def_index__', 0), method_name, method_func))
        exports = sorted(exports)
        cls.__export_indexes__ = {}
        for index, item in enumerate(exports):
            method_name = item[1]
            cls.__export_indexes__[method_name] = index
        logger.info(f"成功注册词典服务类: [{cls.__name__}] | 标签: [{cls.__register_label__}] | 共绑定导出字段: {len(exports)} 个")
        return cls
    return _deco

def export(labels):
    def _with(fld_func):
        @wraps(fld_func)
        def _deco(self, *args, **kwargs):
            res = fld_func(self, *args, **kwargs)
            return QueryResult(result=res) if not isinstance(res, QueryResult) else res
        _deco.__export_attrs__ = [_cl(labels), -1]
        _deco.__def_index__ = export.EXPORT_INDEX
        export.EXPORT_INDEX += 1
        return _deco
    return _with
export.EXPORT_INDEX = 0

def copy_static_file(filename, new_filename=None, static_dir='static'):
    abspath = os.path.join(os.path.dirname(os.path.realpath(__file__)), static_dir, filename)
    shutil.copy(abspath, new_filename if new_filename else filename)

def with_styles(**styles):
    def _with(fld_func):
        @wraps(fld_func)
        def _deco(cls, *args, **kwargs):
            res = fld_func(cls, *args, **kwargs)
            cssfile, css, jsfile, js, need_wrap_css, class_wrapper = \
                styles.get('cssfile', None), styles.get('css', None), \
                styles.get('jsfile', None), styles.get('js', None), \
                styles.get('need_wrap_css', False), styles.get('wrap_class', '')

            def wrap(html, css_obj, is_file=True):
                if need_wrap_css and class_wrapper:
                    html = u'<div class="{}">{}</div>'.format(class_wrapper, html)
                    return html, wrap_css(css_obj, is_file=is_file, class_wrapper=class_wrapper)[0]
                return html, css_obj

            if cssfile:
                new_cssfile = cssfile if cssfile.startswith('_') else u'_' + cssfile
                copy_static_file(cssfile, new_cssfile)
                res, new_cssfile = wrap(res, new_cssfile)
                res = u'<link type="text/css" rel="stylesheet" href="{0}" />{1}'.format(new_cssfile, res)
            if css:
                res, css = wrap(res, css, is_file=False)
                res = u'<style>{0}</style>{1}'.format(css, res)

            if not isinstance(res, QueryResult):
                return QueryResult(result=res, jsfile=jsfile, js=js)
            else:
                res.set_styles(jsfile=jsfile, js=js)
                return res
        return _deco
    return _with

_BS_LOCKS = [_threading.Lock(), _threading.Lock()]

def parse_html(html):
    lock = random.choice(_BS_LOCKS)
    lock.acquire()
    soup = BeautifulSoup(html, 'html.parser')
    lock.release()
    return soup

def service_wrap(service, *args, **kwargs):
    def _service():
        return service(*args, **kwargs)
    return _service

class Service(object):
    def __init__(self):
        self.cache = defaultdict(defaultdict)
        self._unique = self.__class__.__name__
        self._exporters = self._get_exporters()
        self._fields, self._actions = zip(*self._exporters) if self._exporters else (None, None)
        self._word = ''
        self.query_interval = 0.5

    def cache_this(self, result):
        self.cache[self.word].update(result)
        return result

    def cached(self, key):
        return (self.word in self.cache) and (key in self.cache[self.word])

    def cache_result(self, key):
        return self.cache[self.word].get(key, u'')

    def _get_from_api(self):
        return {}

    def _get_field(self, key, default=u''):
        return self.cache_result(key) if self.cached(key) else self._get_from_api().get(key, default)

    @property
    def unique(self):
        return self._unique

    @unique.setter
    def unique(self, value):
        self._unique = value

    @property
    def word(self):
        return self._word

    @word.setter
    def word(self, value):
        value = re.sub(r'</?\w+[^>]*>', '', value)
        self._word = value

    @property
    def quote_word(self):
        return urllib.parse.quote(self.word)

    @property
    def support(self):
        return True

    @property
    def fields(self):
        return self._fields

    @property
    def actions(self):
        return self._actions

    @property
    def exporters(self):
        return self._exporters

    def _get_exporters(self):
        flds = dict()
        methods = inspect.getmembers(self, predicate=inspect.ismethod)
        indexes_map = getattr(self.__class__, '__export_indexes__', {})
        for method_name, method_func in methods:
            export_attrs = getattr(method_func, '__export_attrs__', None)
            if export_attrs:
                label = export_attrs[0]
                index = indexes_map.get(method_name, export_attrs[1])
                flds.update({int(index): (label, method_func)})
        sorted_flds = sorted(flds)
        return [flds[key] for key in sorted_flds]

    def active(self, fld_ord, word):
        self.word = word
        dict_title = getattr(self, 'title', self.unique)
        
        logger.info(f"[查词起点] 接收请求 | 词典: [{dict_title}] | 目标单词: [{word}] | 请求字段序号: [{fld_ord}]")
        if fld_ord >= 0 and fld_ord < len(self.actions):
            field_name = self.fields[fld_ord]
            logger.info(f"[查词分发] 将交由解析器处理 | 提取字段: [{field_name}]")
            res = self.actions[fld_ord]()
            content_str = res.get('result', '') if isinstance(res, QueryResult) else str(res)
            logger.info(f"[查词终点] 流程完成 | 返回长度: {len(content_str)} 字符")
            return res
            
        logger.warning(f"[查词异常] 请求的字段序号无效或越界，强制返回空值 | 序号: {fld_ord}")
        return QueryResult.default()

    @staticmethod
    def get_anki_label(filename, type_):
        formats = {'audio': config.sound_str, 'img': u'<img src="{0}">', 'video': u'<video controls="controls" width="100%" height="auto" src="{0}"></video>'}
        return formats[type_].format(filename)

class WebService(Service):
    def __init__(self):
        super(WebService, self).__init__()
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': _default_ua})
        self.query_interval = 1.0

    @property
    def title(self):
        return getattr(self, '__register_label__', self.unique)

    def get_response(self, url, data=None, headers=None, timeout=10):
        req_headers = headers if headers else {}
        try:
            if data:
                response = self.session.post(url, data=data, headers=req_headers, timeout=timeout)
            else:
                response = self.session.get(url, headers=req_headers, timeout=timeout)
            response.raise_for_status()
            return response.content
        except Exception as e:
            return b''

    @classmethod
    def download(cls, url, filename, timeout=15):
        try:
            response = requests.get(url, headers={'User-Agent': _default_ua}, timeout=timeout)
            response.raise_for_status()
            with open(filename, "wb") as f:
                f.write(response.content)
            return True
        except Exception:
            return False

    class TinyDownloadError(ValueError):
        pass

    def net_stream(self, targets, require=None, method='GET', awesome_ua=False, add_padding=False, custom_quoter=None, custom_headers=None):
        DEFAULT_TIMEOUT = 3
        PADDING = b'\0' * 2 ** 11
        targets = targets if isinstance(targets, list) else [targets]
        processed_targets = []
        for target in targets:
            if isinstance(target, str):
                processed_targets.append((target, None))
            else:
                url, params_dict = target[0], target[1]
                param_strs = []
                for key, val in params_dict.items():
                    quoter = custom_quoter[key] if (custom_quoter and key in custom_quoter) else urllib.parse.quote
                    encoded_val = quoter(val.encode('utf-8') if isinstance(val, str) else str(val), safe='')
                    param_strs.append(f"{key}={encoded_val}")
                processed_targets.append((url, '&'.join(param_strs)))

        require = require or {}
        payloads = []
        for number, (url, params) in enumerate(processed_targets, 1):
            desc = "web request"
            headers = {}
            if custom_headers:
                headers.update(custom_headers)
            try:
                if method == 'GET':
                    req_url = '?'.join([url, params]) if params else url
                    response = self.session.get(req_url, headers=headers, timeout=DEFAULT_TIMEOUT)
                else:
                    response = self.session.post(url, data=params, headers=headers, timeout=DEFAULT_TIMEOUT)
                if response.status_code != 200:
                    raise ValueError(f"Got {response.status_code} status")
                content_type = response.headers.get('Content-Type', '')
                if 'mime' in require and require['mime'] not in content_type.replace('/x-', '/'):
                    raise ValueError(f"Wanted mime {require['mime']}")
                payload = response.content
                if 'size' in require and len(payload) < require['size']:
                    raise self.TinyDownloadError("Download too small")
                payloads.append(payload)
            except Exception as e:
                raise IOError(str(e))
        if add_padding:
            payloads.append(PADDING)
        return b''.join(payloads)

    def net_download(self, path, *args, **kwargs):
        try:
            payload = self.net_stream(*args, **kwargs)
            with open(path, 'wb') as f:
                f.write(payload)
            return True
        except Exception:
            return False

class _DictBuilderQueueThread(QThread):
    def __init__(self, queue_ref, mdx_builders_ref, build_status_ref, mutex_ref):
        super(_DictBuilderQueueThread, self).__init__()
        self._queue = queue_ref
        self._mdx_builders = mdx_builders_ref
        self._build_status = build_status_ref
        self._mutex = mutex_ref

    def run(self):
        while True:
            try:
                func, hash_key = self._queue.get(True, timeout=1.0)
            except Empty:
                continue
            except Exception:
                continue
            try:
                builder = func()
            except Exception as e:
                logger.error(f"后台排队构建数据库失败: {str(e)}")
                builder = None
            finally:
                self._mutex.lock()
                self._mdx_builders[hash_key] = builder
                self._build_status[hash_key] = False
                self._mutex.unlock()
                self._queue.task_done()

class LocalService(Service):
    def __init__(self):
        super(LocalService, self).__init__()
        self.dict_path = ""
        self.builder = None
        self.missed_css = set()

    _mdx_builders = defaultdict(dict)
    _build_status = defaultdict(bool)
    _build_queue = Queue()
    _builder_thread = None
    _mutex_builder = QMutex()

    @staticmethod
    def _get_builder(key, func=None):
        LocalService._mutex_builder.lock()
        hash_key = md5(str(key).encode('utf-8')).hexdigest()
        if not (func is None):
            if not LocalService._mdx_builders.get(hash_key) and not LocalService._build_status.get(hash_key, False):
                LocalService._build_status[hash_key] = True 
                logger.info(f"本地词典准备就绪，加入后台解析队列 | 任务 Hash: [{hash_key}]")
                LocalService._build_queue.put((func, hash_key))
                if LocalService._builder_thread is None or not LocalService._builder_thread.isRunning():
                    LocalService._builder_thread = _DictBuilderQueueThread(
                        LocalService._build_queue, LocalService._mdx_builders,
                        LocalService._build_status, LocalService._mutex_builder
                    )
                    LocalService._builder_thread.start()

        builder = LocalService._mdx_builders.get(hash_key)
        LocalService._mutex_builder.unlock()
        return builder

    @classmethod
    def get_db_status(cls, dict_path):
        hash_key = md5(str(dict_path).encode('utf-8')).hexdigest()
        is_building = cls._build_status.get(hash_key, False)
        has_builder = cls._mdx_builders.get(hash_key) is not None
        if is_building: return "building"
        if has_builder: return "ready"
        return "uninitialized"

    @property
    def support(self):
        return os.path.isfile(self.dict_path)

    @property
    def title(self):
        return getattr(self, '__register_label__', u'Unkown')

    @property
    def _filename(self):
        return os.path.splitext(os.path.basename(self.dict_path))[0]

class MdxService(LocalService):
    def __init__(self, dict_path):
        super(MdxService, self).__init__()
        self.dict_path = dict_path
        self.media_cache = defaultdict(set)
        self.cache = defaultdict(str)
        self.html_cache = defaultdict(str)
        self.query_interval = 0.01
        self.word_links = []
        self.styles = []
        if MdxService.check(self.dict_path):
            self.builder = self._get_builder(dict_path, service_wrap(MdxBuilder, dict_path))

    @staticmethod
    def check(dict_path):
        return os.path.isfile(dict_path) and dict_path.lower().endswith('.mdx')

    @property
    def support(self):
        return MdxService.check(self.dict_path)

    @property
    def title(self):
        if not self.builder or config.use_filename or not getattr(self.builder, '_title', None) or getattr(self.builder, '_title', '').startswith('Title'):
            return self._filename
        else:
            return self.builder._title

    def active(self, fld_ord, word):
        hash_key = md5(str(self.dict_path).encode('utf-8')).hexdigest()
        if not self.builder:
            self.builder = LocalService._mdx_builders.get(hash_key)
        if LocalService._build_status.get(hash_key, False):
            return QueryResult(result="<i>词典数据库正在后台建立中，请稍后再查...</i>")
        if not self.builder:
             return QueryResult(result="<i>词典初始化失败，请检查文件。</i>")

        self.missed_css.clear()
        return super(LocalService, self).active(fld_ord, word)

    @export([u'默认', u'Default'])
    def fld_whole(self):
        html = self.get_default_html()
        js = re.findall(r'<script .*?>(.*?)</script>', html, re.DOTALL)
        jsfile = re.findall(r'<script .*?src=[\'\"](.+?)[\'\"]', html, re.DOTALL)
        return QueryResult(result=html, js=u'\n'.join(js), jsfile=jsfile)

    def _get_definition_mdx(self, word=None):
        if word is None: word = self.word
        ignorecase = config.ignore_mdx_wordcase and (word != word.lower() or word != word.upper())
        content = self.builder.mdx_lookup(word, ignorecase=ignorecase)
        str_content = ""
        if len(content) > 0:
            for c in content:
                str_content += c.replace("\r\n", "").replace("entry:/", "")
        return str_content

    def _get_definition_mdd(self, word):
        word = word.replace('/', '\\')
        ignorecase = config.ignore_mdx_wordcase and (word != word.lower() or word != word.upper())
        content = self.builder.mdd_lookup(word, ignorecase=ignorecase)
        if len(content) > 0: return [content[0]]
        return []

    def get_html(self, word=None):
        if word is None: word = self.word
        if not self.html_cache[word]:
            html = self._get_definition_mdx(word)
            if html: self.html_cache[word] = html
        return self.html_cache[word]

    def save_file(self, filepath_in_mdx, savepath):
        try:
            bytes_list = self._get_definition_mdd(filepath_in_mdx)
            if bytes_list:
                if not os.path.exists(savepath):
                    with open(savepath, 'wb') as f:
                        f.write(bytes_list[0])
                return savepath
        except sqlite3.OperationalError:
            pass
        return ''

    def get_default_html(self):
        if not self.cache[self.word]:
            self.word_links = [self.word.upper()]
            self._get_default_html(self.word)
        return self.cache[self.word]

    def _get_default_html(self, word=None):
        html = u''
        if word is None: word = self.word
        result = self.get_html(word)
        if result:
            if result.upper().find(u"@@@LINK=") > -1:
                raw_html, _, result = result.partition("@@@LINK=")
                words = [i.strip() for i in filter(None, result.split('@@@LINK='))]
                html_list = [raw_html, ] if raw_html else []
                for redirect_word in words:
                    if not redirect_word.upper() in self.word_links:
                        self.word_links.append(redirect_word.upper())
                        html_list.append(self._get_default_html(redirect_word))
                if len(html_list) != 0:
                    html = "<br>".join(html_list)
            else:
                html = result
        self.cache[word] = self.adapt_to_anki(html)
        return html

    def _get_default_html_one_word(self):
        html = u''
        result = self.get_html()
        if result:
            if result.upper().find(u"@@@LINK=") > -1:
                word = result[len(u"@@@LINK="):].strip()
                if not word.upper() in self.word_links:
                    self.word_links.append(word.upper())
                    self.word = word
                    return self._get_default_html()
            html = self.adapt_to_anki(result)
        self.cache[self.word] = html
        return self.cache[self.word]

    # ========================================================
    # 🌟 智能读取模糊匹配勾选状态：多行配置联动，只要有一行开启即全局生效
    # ========================================================
    def _is_fuzzy_enabled(self):
        return getattr(config, 'fuzzy_match', True)

    def adapt_to_anki(self, html):
        logger.info(f"[HTML 适配器] 开始进行媒体资源正则提取...")
        media_files_set = set()
        mcss = re.findall(r'href=[\',"](\S+?\.css)[\',"]', html)
        media_files_set.update(set(mcss))
        mjs = re.findall(r'src="([\w\./]\S+?\.js)"', html)
        media_files_set.update(set(mjs))
        msrc = re.findall(r'<img.*?src="([\w\./]\S+?)".*?>', html)
        media_files_set.update(set(msrc))
        msound = re.findall(r'href="sound:(.*?\.(?:mp3|wav|aac|ogg|spx))"', html)
        
        # ==========================================
        # 🌟 核心接入点：精确查找 -> 失败则流入模糊匹配引擎
        # ==========================================
        if self._is_fuzzy_enabled():
            logger.info("[执行策略] 启动媒体资源【先精确再模糊】降级过滤引擎...")
            fuzzy_candidates = set(msrc).union(set(msound))
            fuzzy_targets = set()
            
            for original_name in fuzzy_candidates:
                # 先用 URL 解码后的名字，去 MDD 里尝试严格匹配
                unquoted_name = urllib.parse.unquote(original_name)
                exact_pattern = '*\\' + os.path.basename(unquoted_name.replace('\\', os.path.sep))
                exact_keys = self.builder.get_mdd_keys(exact_pattern)
                
                if exact_keys:
                    logger.debug(f"[精确匹配命中] 资源存在，跳过模糊处理: {original_name}")
                else:
                    logger.info(f"[精确匹配失败] 资源缺失，移交模糊匹配队列: {original_name}")
                    fuzzy_targets.add(original_name)
            
# 对精确查找失败的文件执行白名单模糊纠错
# 对精确查找失败的文件执行白名单模糊纠错
            if fuzzy_targets:
                replacement_map = process_fuzzy_media(
                    self.builder, 
                    self.title, 
                    fuzzy_targets, 
                    self.save_default_file 
                )
                
                # 在 HTML 源码中，将原始的错误标签替换为模糊匹配后产生的正确 Anki 标签
                for original_name, anki_tag in replacement_map.items():
                    html = re.sub(rf'href="sound:{re.escape(original_name)}"[^>]*?>.*?</a>', anki_tag, html)
                    # 修复这里的引号解析报错
                    if '"' in anki_tag:
                        extracted_url = anki_tag.split('"')[1]
                        html = html.replace(f'src="{original_name}"', f'src="{extracted_url}"')
                
                # 将已模糊匹配成功的文件从原生处理清单中剔除
                media_files_set = set(mcss).union(set(mjs)).union(fuzzy_candidates.difference(fuzzy_targets))
        else:
            if config.export_media:
                media_files_set.update(set(msound))
        # ==========================================
        
        css_style = ''
        if len(mcss) != 0:
            css_list = ["@import url(_{});".format(sanitize_to_safe_encoding(i)) for i in mcss]
            css_style = "\n".join(css_list)
            css_style = "<style> {} </style>".format(css_style)
        logger.info(f"[HTML 适配器] 开始实施 Anki 安全编码与前缀覆盖。")
        for original_name in media_files_set:
            # 使用我们的全局安全编码器，防止手机端解析报错
            safe_name = sanitize_to_safe_encoding(original_name)
            if not original_name.lower().endswith(('.mp3', '.wav', '.ogg', '.aac', '.spx')):
                html = html.replace(original_name, u'_' + safe_name)
            
        if html != '' and css_style != '':
            html = css_style + html
            
        # ==========================================
        # 🌟 音频回填：使用正则回调，保证原始请求名称也能正确转换为安全名称
        # ==========================================
        def sound_repl(match):
            orig = match.group(1)
            text = match.group(2)
            safe_name = sanitize_to_safe_encoding(orig)
            return f"[sound:mdx-{self.title}-{safe_name}]{text}"
            
        p = re.compile(r'<a[^>]+?href=\"sound:(.*?\.(?:mp3|wav|aac|ogg|spx))\"[^>]*?>(.*?)</a>')
        html = p.sub(sound_repl, html)
        
        self.save_media_files(media_files_set)
        
        # CSS 沙盒包裹处理
        for f in mcss:
            basename = os.path.basename(f.replace('\\', os.path.sep))
            if not basename: continue
            
            safe_css_name = sanitize_to_safe_encoding(basename)
            cssfile = u'_{}'.format(safe_css_name)
            if not os.path.exists(cssfile):
                css_src = os.path.join(os.path.dirname(self.dict_path), basename) # 原始寻找时仍用旧名
                if os.path.exists(css_src) and os.path.isfile(css_src):
                    shutil.copy(css_src, cssfile)
                else:
                    self.missed_css.add(cssfile[1:])
                    
            new_css_file, wrap_class_name = wrap_css(cssfile)
            html = html.replace(cssfile, new_css_file)
            html = u'<div class="{0}">{1}</div>'.format(wrap_class_name, html)

        return html

    def save_default_file(self, filepath_in_mdx, savepath=None):
        '''
        自动将资源文件落地至物理硬盘，同时强制实施安全重命名。
        '''
        basename = os.path.basename(filepath_in_mdx.replace('\\', os.path.sep))
        if not basename:
            return ''
            
        if savepath is None:
            # 🌟 核心拦截点：所有通过此处存入硬盘的文件都会变成安全名字
            safe_base = sanitize_to_safe_encoding(basename)
            if safe_base.lower().endswith(("mp3", "wav", "ogg", "aac", "spx")):
                savepath = "mdx-" + self.title + "-" + safe_base
            else:
                savepath = '_' + safe_base
                
        if os.path.exists(savepath):
            return savepath
            
        try:
            src_fn = os.path.join(os.path.dirname(self.dict_path), basename)
            if os.path.exists(src_fn) and os.path.isfile(src_fn):
                shutil.copy(src_fn, savepath)
                return savepath
            else:
                ignorecase = config.ignore_mdx_wordcase and (
                        filepath_in_mdx != filepath_in_mdx.lower() or filepath_in_mdx != filepath_in_mdx.upper())
                bytes_list = self.builder.mdd_lookup(filepath_in_mdx, ignorecase=ignorecase)
                if bytes_list:
                    with open(savepath, 'wb') as f:
                        f.write(bytes_list[0])
                    return savepath
        except sqlite3.OperationalError as e:
            logger.error(f"[资源抽取中断] 操作键名: [{filepath_in_mdx}] | Trace: {str(e)}")
            pass
        return ''

    def save_media_files(self, data):
        diff = data.difference(self.media_cache['files'])
        self.media_cache['files'].update(diff)
        lst, errors = list(), list()

        # 🌟 获取真实的 MDD 查询键：必须解除 URL 编码，才能从 MDD 查出真正的文件！
        wild = [
            '*\\' + os.path.basename(urllib.parse.unquote(each).replace('\\', os.path.sep)) 
            for each in diff
        ]
            
        try:
            for each in wild:
                keys = self.builder.get_mdd_keys(each)
                if not keys:
                    errors.append(each)
                    lst.append(each[1:])
                else:
                    lst.extend(keys)
                    
            for each in lst:
                self.save_default_file(each)
        except AttributeError as e:
            pass

        return errors

class StardictService(LocalService):
    def __init__(self, dict_path):
        super(StardictService, self).__init__()
        self.dict_path = dict_path
        self.query_interval = 0.05
        if StardictService.check(self.dict_path):
            dict_path = dict_path[:-4]
            self.builder = self._get_builder(dict_path, service_wrap(StardictBuilder, dict_path, in_memory=False))

    @staticmethod
    def check(dict_path): return os.path.isfile(dict_path) and dict_path.lower().endswith('.ifo')

    @property
    def support(self): return StardictService.check(self.dict_path)

    @property
    def title(self):
        if not self.builder or config.use_filename or not getattr(self.builder.ifo, 'bookname', None): return self._filename
        else: return self.builder.ifo.bookname

    def active(self, fld_ord, word):
        hash_key = md5(str(self.dict_path[:-4]).encode('utf-8')).hexdigest()
        if not self.builder: self.builder = LocalService._mdx_builders.get(hash_key)
        if LocalService._build_status.get(hash_key, False): return QueryResult(result="<i>词典数据库正在后台排队中...</i>")
        if not self.builder: return QueryResult(result="<i>词典初始化失败。</i>")
        self.missed_css.clear()
        return super(LocalService, self).active(fld_ord, word)

    @export([u'默认', u'Default'])
    def fld_whole(self):
        try:
            result = self.builder[self.word]
            result = result.strip().replace('\r\n', '<br />').replace('\r', '<br />').replace('\n', '<br />')
            return QueryResult(result=result)
        except KeyError:
            return QueryResult.default()

class QueryResult(MapDict):
    def __init__(self, *args, **kwargs):
        super(QueryResult, self).__init__(*args, **kwargs)
        if self['result'] is None: self['result'] = ""
    def set_styles(self, **kwargs):
        for key, value in kwargs.items(): self[key] = value
    @classmethod
    def default(cls):
        return QueryResult(result="")