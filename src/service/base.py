# -*- coding:utf-8 -*-
# Copyright (C) 2018 sthoo <sth201807@gmail.com>
# Support: Report an issue at https://github.com/sth2018/FastWordQuery/issues
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version; http://www.gnu.org/copyleft/gpl.html.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

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


__all__ = [
    'register', 'export', 'copy_static_file', 'with_styles', 'parse_html', 'service_wrap', 'get_hex_name',
    'Service', 'WebService', 'LocalService', 'MdxService', 'StardictService', 'QueryResult'
]

_default_ua = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 ' \
              '(KHTML, like Gecko) Chrome/70.0.3538.67 Safari/537.36'


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
    """
    register the dict service with a labels, which will be shown in the dicts list.
    """
    def _deco(cls):
        cls.__register_label__ = _cl(labels)

        methods = inspect.getmembers(cls, predicate=_is_method_or_func)
        exports = []
        for method_name, method_func in methods:
            attrs = getattr(method_func, '__export_attrs__', None)
            if attrs:
                exports.append((
                    getattr(method_func, '__def_index__', 0),
                    method_name,
                    method_func
                ))
        exports = sorted(exports)
        
        cls.__export_indexes__ = {}
        for index, item in enumerate(exports):
            method_name = item[1]
            cls.__export_indexes__[method_name] = index

        logger.info(f"成功注册词典服务类: [{cls.__name__}] | 标签: [{cls.__register_label__}] | 共绑定导出字段: {len(exports)} 个")
        
        return cls

    return _deco



def export(labels):
    """
    export dict field function with a labels, which will be shown in the fields list.
    """

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
    """
    copy file in static directory to media folder
    """
    abspath = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                           static_dir,
                           filename)
    shutil.copy(abspath, new_filename if new_filename else filename)


def with_styles(**styles):
    """
    cssfile: specify the css file in static folder
    css: css strings
    js: js strings
    jsfile: specify the js file in static folder
    """

    def _with(fld_func):
        @wraps(fld_func)
        def _deco(cls, *args, **kwargs):
            res = fld_func(cls, *args, **kwargs)
            cssfile, css, jsfile, js, need_wrap_css, class_wrapper = \
                styles.get('cssfile', None), \
                    styles.get('css', None), \
                    styles.get('jsfile', None), \
                    styles.get('js', None), \
                    styles.get('need_wrap_css', False), \
                    styles.get('wrap_class', '')

            def wrap(html, css_obj, is_file=True):
                # wrap css and html
                if need_wrap_css and class_wrapper:
                    html = u'<div class="{}">{}</div>'.format(
                        class_wrapper, html)
                    return html, wrap_css(css_obj, is_file=is_file, class_wrapper=class_wrapper)[0]
                return html, css_obj

            if cssfile:
                new_cssfile = cssfile if cssfile.startswith('_') \
                    else u'_' + cssfile
                copy_static_file(cssfile, new_cssfile)
                res, new_cssfile = wrap(res, new_cssfile)
                res = u'<link type="text/css" rel="stylesheet" href="{0}" />{1}'.format(
                    new_cssfile, res)
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


_BS_LOCKS = [_threading.Lock(), _threading.Lock()]  # bs4 threading lock, overload protection


def parse_html(html):
    '''
    use bs4 lib parse HTML, run only 2 BS at the same time
    '''
    lock = random.choice(_BS_LOCKS)
    lock.acquire()
    soup = BeautifulSoup(html, 'html.parser')
    lock.release()
    return soup


def service_wrap(service, *args, **kwargs):
    """
    wrap the service class constructor
    """

    def _service():
        return service(*args, **kwargs)

    return _service


class Service(object):
    '''
    Dictionary Service Abstract Class
    '''

    def __init__(self):
        self.cache = defaultdict(defaultdict)
        self._unique = self.__class__.__name__
        self._exporters = self._get_exporters()
        self._fields, self._actions = zip(*self._exporters) \
            if self._exporters else (None, None)
        self._word = ''
        # query interval: default 500ms
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
            logger.info(f"[查词分发] 将交由解析器方法 {self.actions[fld_ord].__name__}() 处理 | 提取字段: [{field_name}]")
            
            res = self.actions[fld_ord]()
            
            content_str = res.get('result', '') if isinstance(res, QueryResult) else str(res)
            logger.info(f"[查词终点] 查词流程完成 | 词典: [{dict_title}] | 返回结果总长度: {len(content_str)} 字符 | 返回内容: {content_str}")
            return res
            
        logger.warning(f"[查词异常] 请求的字段序号无效或越界，强制返回空值 | 词典: [{dict_title}] | 序号: {fld_ord}")
        return QueryResult.default()

    @staticmethod
    def get_anki_label(filename, type_):
        formats = {'audio': config.sound_str,
                   'img': u'<img src="{0}">',
                   'video': u'<video controls="controls" width="100%" height="auto" src="{0}"></video>'}
        return formats[type_].format(filename)


class WebService(Service):
    """
    Web Dictionary Service (Refactored to use 'requests')
    """

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
        logger.info(f"[网络词典] 准备发起 HTTP 请求 | URL: {url} | Method: {'POST' if data else 'GET'} | 超时设置: {timeout}s")
        try:
            if data:
                response = self.session.post(url, data=data, headers=req_headers, timeout=timeout)
            else:
                response = self.session.get(url, headers=req_headers, timeout=timeout)
            response.raise_for_status()
            logger.info(f"[网络词典] 请求成功 | 状态码: {response.status_code} | 获取数据大小: {len(response.content)} bytes | 响应片段: {response.text}")
            return response.content
        except Exception as e:
            logger.error(f"[网络词典] 网络请求中断 | URL: [{url}] | 错误详情: {str(e)}")
            return b''

    @classmethod
    def download(cls, url, filename, timeout=15):
        logger.info(f"[网络下载] 启动外部资源下载 | 来源 URL: [{url}] -> 目标存储: [{filename}]")
        try:
            response = requests.get(url, headers={'User-Agent': _default_ua}, timeout=timeout)
            response.raise_for_status()
            with open(filename, "wb") as f:
                f.write(response.content)
            logger.info(f"[网络下载] 下载完成并已落盘 | 文件大小: {len(response.content)} bytes")
            return True
        except Exception as e:
            logger.error(f"[网络下载] 下载失败中止 | URL: [{url}] | 错误详情: {str(e)}")
            return False

    class TinyDownloadError(ValueError):
        """Raises when a download is too small."""

    def net_stream(self, targets, require=None, method='GET',
                   awesome_ua=False, add_padding=False,
                   custom_quoter=None, custom_headers=None):
        DEFAULT_TIMEOUT = 3
        PADDING = b'\0' * 2 ** 11

        assert method in ['GET', 'POST'], "method must be GET or POST"

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
            desc = "web request" if len(targets) == 1 \
                else "web request (%d of %d)" % (number, len(targets))

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
                    value_error = ValueError("Got %d status for %s" % (response.status_code, desc))
                    value_error.payload = response.content
                    raise value_error
                    
                content_type = response.headers.get('Content-Type', '')
                if 'mime' in require and require['mime'] not in content_type.replace('/x-', '/'):
                    value_error = ValueError(
                        "Request got %s Content-Type for %s; wanted %s" %
                        (content_type, desc, require['mime'])
                    )
                    value_error.got_mime = content_type
                    value_error.wanted_mime = require['mime']
                    raise value_error

                payload = response.content
                if 'size' in require and len(payload) < require['size']:
                    raise self.TinyDownloadError(
                        "Request got %d-byte stream for %s; wanted %d+ bytes" %
                        (len(payload), desc, require['size'])
                    )

                payloads.append(payload)
            except requests.exceptions.RequestException as e:
                raise IOError("No response for %s: %s" % (desc, str(e)))

        if add_padding:
            payloads.append(PADDING)
        return b''.join(payloads)

    def net_download(self, path, *args, **kwargs):
        """
        Downloads a file to the given path from the specified target(s).
        See net_stream() for information about available options.
        """
        try:
            payload = self.net_stream(*args, **kwargs)
            with open(path, 'wb') as f:
                f.write(payload)
            return True
        except Exception:
            return False


class _DictBuilderQueueThread(QThread):
    """单例后台队列构建线程，一次只允许建立一个词典（排队处理）"""

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
    """
    Local Dictionary Service
    """

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
                        LocalService._build_queue,
                        LocalService._mdx_builders,
                        LocalService._build_status,
                        LocalService._mutex_builder
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
        
        if is_building:
            return "building"
        if has_builder:
            return "ready"
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
    """
    MDX Local Dictionary Service
    """

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
            logger.info(f"[{self.title}] 数据库当前正在建立，放弃本次查词: [{word}]")
            return QueryResult(result="<i>词典数据库正在后台建立中，请稍后再查...</i>")
            
        if not self.builder:
             logger.warning(f"[{self.title}] Builder 实例未获取，初始化失败或文件丢失。")
             return QueryResult(result="<i>词典初始化失败，请检查文件。</i>")

        self.missed_css.clear()
        return super(LocalService, self).active(fld_ord, word)

    @export([u'默认', u'Default'])
    def fld_whole(self):
        html = self.get_default_html()
        
        logger.info(f"[抽取 JS 脚本] 开始从渲染好的 HTML 中分离独立 Script 块及 JS 文件链接。")
        js = re.findall(r'<script .*?>(.*?)</script>', html, re.DOTALL)
        jsfile = re.findall(r'<script .*?src=[\'\"](.+?)[\'\"]', html, re.DOTALL)
        if js: logger.info(f"[抽取 JS 脚本] 抽取到 {len(js)} 块内联脚本，内容: {js}")
        if jsfile: logger.info(f"[抽取 JS 脚本] 抽取到 {len(jsfile)} 个外联 JS: {jsfile}")
        
        return QueryResult(result=html, js=u'\n'.join(js), jsfile=jsfile)

    def _get_definition_mdx(self, word=None):
        """according to the word return mdx dictionary page"""
        if word is None:
            word = self.word
        ignorecase = config.ignore_mdx_wordcase and (word != word.lower() or word != word.upper())
        
        logger.info(f"[MDX 引擎查词] 正在向 MDX Builder 下发查询指令 | 关键词: [{word}] | 忽略大小写: {ignorecase}")
        content = self.builder.mdx_lookup(word, ignorecase=ignorecase)
        str_content = ""
        if len(content) > 0:
            for c in content:
                str_content += c.replace("\r\n", "").replace("entry:/", "")
            logger.info(f"[MDX 引擎查词] 命中词条！获取 {len(content)} 块数据，清理后合并为: {str_content}")
        else:
            logger.warning(f"[MDX 引擎查词] 未能查找到相关词条。")

        return str_content

    def _get_definition_mdd(self, word):
        """according to the keyword(param word) return the media file contents"""
        word = word.replace('/', '\\')
        ignorecase = config.ignore_mdx_wordcase and (word != word.lower() or word != word.upper())
        
        logger.info(f"[MDD 引擎提取] 正在向 MDD Builder 申请资源数据 | 目标地址: [{word}]")
        content = self.builder.mdd_lookup(word, ignorecase=ignorecase)
        if len(content) > 0:
            logger.info(f"[MDD 引擎提取] 提取成功，成功抽取出媒体字节流块，大小: {len(content[0])} bytes")
            return [content[0]]
        else:
            logger.warning(f"[MDD 引擎提取] 提取失败，MDD 文件内不存在该资源关联。")
            return []

    def get_html(self, word=None):
        """get self.word's html page from MDX"""
        if word is None:
            word = self.word
            
        logger.info(f"[内存缓存检查] 核对单词 [{word}] 的 HTML 缓存状态...")
        if not self.html_cache[word]:
            logger.info(f"[内存缓存检查] 缓存缺失 (Cache Miss)，即将触发底层拉取。")
            html = self._get_definition_mdx(word)
            if html:
                self.html_cache[word] = html
        else:
            logger.info(f"[内存缓存检查] 缓存命中 (Cache Hit)！直接复用上次拉取的 HTML。")
            
        return self.html_cache[word]

    def save_file(self, filepath_in_mdx, savepath):
        """according to filepath_in_mdx to get media file and save it to savepath"""
        try:
            bytes_list = self._get_definition_mdd(filepath_in_mdx)
            if bytes_list:
                if not os.path.exists(savepath):
                    with open(savepath, 'wb') as f:
                        f.write(bytes_list[0])
                    logger.info(f"[磁盘写入] 资源文件落地成功 | 目标路径: [{savepath}]")
                else:
                    logger.info(f"[磁盘写入] 文件已存在于磁盘中，已跳过覆盖写入 | 目标路径: [{savepath}]")
                return savepath
            else:
                pass # 已经在 mdd_lookup 里打印了 warn
        except sqlite3.OperationalError as e:
            logger.error(f"[磁盘写入] SQLite 或 I/O 发生严重异常，中止写入 | 目标路径: [{savepath}] | 错误: {str(e)}")
            pass
        return ''

    def get_default_html(self):
        '''
        default get html from mdx interface
        '''
        if not self.cache[self.word]:
            self.word_links = [self.word.upper()]
            self._get_default_html(self.word)
        return self.cache[self.word]

    def _get_default_html(self, word=None):
        """    
        :param self: Refer to the instance of the class
        :param word: Pass the word to be searched for
        :return: The no adapt_to_anki html of the word
        """
        html = u''
        if word is None:
            word = self.word
            
        result = self.get_html(word)
        if result:
            logger.info(f"[内部重定向检测] 正在扫描原始 HTML，判断是否存在跳转标签 `@@@LINK=`...")
            if result.upper().find(u"@@@LINK=") > -1:
                raw_html, _, result = result.partition("@@@LINK=")
                words = list(filter(None, result.split('@@@LINK=')))
                words = [i.strip() for i in words]
                
                logger.info(f"[内部重定向检测] 发现多重或单向跳转，导向目标集合为: {words}")
                
                if raw_html:
                    html_list = [raw_html, ]
                else:
                    html_list = []

                for redirect_word in words:
                    logger.info(f"[内部重定向执行] [{word}] -> 触发自动跳转，查询下一跳单词: [{redirect_word}]")
                    if not redirect_word.upper() in self.word_links:
                        self.word_links.append(redirect_word.upper())
                        html_list.append(self._get_default_html(redirect_word))
                    else:
                        logger.info(f"[内部重定向执行] 检测到成环死循环跳转，拦截抛弃词汇: [{redirect_word}]")
                        
                if len(html_list) != 0:
                    html = "<br>".join(html_list)

            else:
                logger.info(f"[内部重定向检测] 未发现重定向，将使用当前 HTML 作为基础源。")
                html = result

        logger.info(f"[内容适配器] 即将向 adapt_to_anki() 输送原始 HTML 以处理媒体及标签替换。输入数据: {html}")
        self.cache[word] = self.adapt_to_anki(html)
        return html

    def _get_default_html_one_word(self):
        html = u''
        result = self.get_html()
        if result:
            if result.upper().find(u"@@@LINK=") > -1:
                word = result[len(u"@@@LINK="):].strip()
                logger.info(f"[独显重定向] 当前模式仅处理一次跳转。来源: [{self.word}] -> 重写为: [{word}]")
                if not word.upper() in self.word_links:
                    self.word_links.append(word.upper())
                    self.word = word
                    return self._get_default_html()
            html = self.adapt_to_anki(result)
        self.cache[self.word] = html
        return self.cache[self.word]

    def adapt_to_anki(self, html):
        """
        1. convert the media path to actual path in anki's collection media folder.
        2. remove the js codes (js inside will expires.)
        """
        logger.info(f"[HTML 适配器] 开始进行正则洗稿，扫描提取全部媒体资源 (css, js, img, audio) ...")
        media_files_set = set()
        mcss = re.findall(r'href=[\',"](\S+?\.css)[\',"]', html)
        media_files_set.update(set(mcss))
        mjs = re.findall(r'src="([\w\./]\S+?\.js)"', html)
        media_files_set.update(set(mjs))
        msrc = re.findall(r'<img.*?src="([\w\./]\S+?)".*?>', html)
        media_files_set.update(set(msrc))
        msound = re.findall(r'href="sound:(.*?\.(?:mp3|wav|aac))"', html)
        
        logger.info(f"[HTML 适配器] 正则扫除完毕。捕获资产清单如下：\n- CSS: {mcss}\n- JS: {mjs}\n- 图像: {msrc}\n- 音频: {msound}")

        css_style = ''
        if len(mcss) != 0:
            css_list = ["@import url(_{});".format(i) for i in mcss]
            css_style = "\n".join(css_list)
            css_style = "<style> {} </style>".format(css_style)
            
        if config.export_media:
            logger.info(f"[HTML 适配器] 由于启用导出媒体设置，将 {len(msound)} 份音频也一并列入处理队列。")
            media_files_set.update(set(msound))
            
        logger.info(f"[HTML 适配器] 开始对文档内的引用实施 Anki `_` 前缀覆盖。")
        for each in media_files_set:
            html = html.replace(each, u'_' + each.split('/')[-1])
            
        if html != '' and css_style != '':
            html = css_style + html
            
        # find sounds
        p = re.compile(
            r'<a[^>]+?href=\"sound:_(.*?\.(?:mp3|wav|aac))\"[^>]*?>(.*?)</a>')
        html = p.sub("[sound:mdx-" + self.title + "-" + u"\\1]\\2", html)
        
        self.save_media_files(media_files_set)
        
        logger.info(f"[HTML 适配器] CSS 补全与沙盒隔离混淆处理阶段启动...")
        for f in mcss:
            basename = os.path.basename(f.replace('\\', os.path.sep))
            if not basename:
                continue
                
            cssfile = u'_{}'.format(basename)
            if not os.path.exists(cssfile):
                css_src = os.path.join(os.path.dirname(self.dict_path), f)
                if os.path.exists(css_src) and os.path.isfile(css_src):
                    shutil.copy(css_src, cssfile)
                    logger.info(f"[HTML 适配器] 发现同级独立存在的 CSS，已完成补全复制: [{cssfile}]")
                else:
                    self.missed_css.add(cssfile[1:])
                    logger.warning(f"[HTML 适配器] CSS 资源下落不明，已推入 missed_css 记录器中以备后续处理: [{cssfile}]")
                    
            logger.info(f"[HTML 适配器] 执行 wrap_css 混淆操作，挂载沙盒隔离类名 -> 目标文件: {cssfile}")
            new_css_file, wrap_class_name = wrap_css(cssfile)
            html = html.replace(cssfile, new_css_file)
            html = u'<div class="{0}">{1}</div>'.format(
                wrap_class_name, html)

        logger.info(f"[HTML 适配器] 适配阶段圆满收工。产出结果 HTML 呈现: {html}")
        return html

    def save_default_file(self, filepath_in_mdx, savepath=None):
        '''
        default save file interface
        '''
        basename = os.path.basename(filepath_in_mdx.replace('\\', os.path.sep))
        if not basename:
            return ''
            
        if savepath is None:
            savepath = '_' + basename
            if basename.lower().endswith(("mp3", "wav")):
                savepath = "mdx-" + self.title + "-" + basename
                
        if os.path.exists(savepath):
            return savepath
            
        try:
            src_fn = os.path.join(os.path.dirname(self.dict_path), basename)
            if os.path.exists(src_fn) and os.path.isfile(src_fn):
                logger.info(f"[资源外置抽取] 检测到本地裸露文件，放弃查库直接平移 | 源头: [{src_fn}] -> 去向: [{savepath}]")
                shutil.copy(src_fn, savepath)
                return savepath
            else:
                ignorecase = config.ignore_mdx_wordcase and (
                        filepath_in_mdx != filepath_in_mdx.lower() or filepath_in_mdx != filepath_in_mdx.upper())
                logger.info(f"[资源内嵌抽取] 外部探测无果，提交给 MDD 解析引擎深度查询 | 目标键名: [{filepath_in_mdx}]")
                bytes_list = self.builder.mdd_lookup(filepath_in_mdx, ignorecase=ignorecase)
                if bytes_list:
                    with open(savepath, 'wb') as f:
                        f.write(bytes_list[0])
                    logger.info(f"[资源内嵌抽取] MDD 输出数据已捕获，落盘成功 | 本地地址: [{savepath}]")
                    return savepath
        except sqlite3.OperationalError as e:
            logger.error(f"[资源抽取中断] 数据库句柄崩溃 | 操作键名: [{filepath_in_mdx}] | Trace: {str(e)}")
            pass
        return ''

    def save_media_files(self, data):
        """
        get the necessary static files from local mdx dictionary
        ** kwargs: data = list
        """
        diff = data.difference(self.media_cache['files'])
        self.media_cache['files'].update(diff)
        lst, errors = list(), list()

        logger.info(f"[导出列队分析] 比对当前运行期缓存后，筛选出需实际操作的 {len(diff)} 个增量媒体资源。")
        wild = [
            '*\\' + os.path.basename(each.replace('\\', os.path.sep)) for each in diff]
            
        try:
            for each in wild:
                keys = self.builder.get_mdd_keys(each)
                if not keys:
                    errors.append(each)
                    lst.append(each[1:])
                else:
                    lst.extend(keys)
                    
            logger.info(f"[导出列队规划] 队列准备下发执行... 共计衍生 {len(lst)} 个存储指令，{len(errors)} 项未命中数据库映射树。")
            for each in lst:
                self.save_default_file(each)

        except AttributeError as e:
            logger.error(f"[导出列队规划] 遇到反射异常: {str(e)}")
            pass

        return errors


class StardictService(LocalService):
    '''
    Stardict Local Dictionary Service
    '''

    def __init__(self, dict_path):
        super(StardictService, self).__init__()
        self.dict_path = dict_path
        self.query_interval = 0.05
        if StardictService.check(self.dict_path):
            dict_path = dict_path[:-4]
            self.builder = self._get_builder(
                dict_path,
                service_wrap(StardictBuilder, dict_path, in_memory=False)
            )

    @staticmethod
    def check(dict_path):
        return os.path.isfile(dict_path) and dict_path.lower().endswith('.ifo')

    @property
    def support(self):
        return StardictService.check(self.dict_path)

    @property
    def title(self):
        if not self.builder or config.use_filename or not getattr(self.builder.ifo, 'bookname', None):
            return self._filename
        else:
            return self.builder.ifo.bookname

    def active(self, fld_ord, word):
        hash_key = md5(str(self.dict_path[:-4]).encode('utf-8')).hexdigest()
        
        if not self.builder:
            self.builder = LocalService._mdx_builders.get(hash_key)

        if LocalService._build_status.get(hash_key, False):
            logger.info(f"[{self.title}] 数据库建立中，跳过实体查词: [{word}]")
            return QueryResult(result="<i>词典数据库正在后台排队/建立中，请稍后再查...</i>")
            
        if not self.builder:
             logger.warning(f"[{self.title}] Stardict Builder 初始化失败。")
             return QueryResult(result="<i>词典初始化失败，请检查文件。</i>")

        self.missed_css.clear()
        return super(LocalService, self).active(fld_ord, word)

    @export([u'默认', u'Default'])
    def fld_whole(self):
        try:
            logger.info(f"[Stardict引擎] 准备触发字典实体键值检索，向词库游标查询当前缓存词汇: [{self.word}]")
            result = self.builder[self.word]
            logger.info(f"[Stardict引擎] 检索命中！提取成功并开始清洗换行符。原始内容: {result}")
            result = result.strip().replace('\r\n', '<br />') \
                .replace('\r', '<br />').replace('\n', '<br />')
            return QueryResult(result=result)
        except KeyError:
            logger.warning(f"[Stardict引擎] 查词游标抛出 KeyError：当前词典 [{self.title}] 未收录单词 [{self.word}]")
            return QueryResult.default()


class QueryResult(MapDict):
    """Query Result structure"""

    def __init__(self, *args, **kwargs):
        super(QueryResult, self).__init__(*args, **kwargs)
        if self['result'] is None:
            self['result'] = ""

    def set_styles(self, **kwargs):
        for key, value in kwargs.items():
            self[key] = value

    @classmethod
    def default(cls):
        return QueryResult(result="")