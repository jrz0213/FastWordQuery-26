# -*- coding: utf-8 -*-

import json
import os
import re
import sqlite3
import glob  # 新增：用于匹配分卷文件
import zlib
from io import BytesIO
from struct import pack, unpack
from urllib.parse import unquote  # 原生 Python 3 模块，替代原有的降级兼容

from .readmdict import MDD, MDX

# LZO compression is used for engine version < 2.0
try:
    import lzo
except ImportError:
    lzo = None

version = '1.1'


class IndexBuilder(object):
    #todo: enable history
    def __init__(self,
                 fname,
                 encoding="",
                 passcode=None,
                 force_rebuild=False,
                 enable_history=False,
                 sql_index=True,
                 check=False):
        self._mdx_file = fname
        self._mdd_files = []  # 修改：用列表存储所有的 mdd 分卷文件
        self._encoding = ''
        self._stylesheet = {}
        self._title = ''
        self._version = ''
        self._description = ''
        self._sql_index = sql_index
        self._check = check
        _filename, _file_extension = os.path.splitext(fname)
        assert (_file_extension == '.mdx')
        assert (os.path.isfile(fname))
        self._mdx_db = _filename + ".mdx.db"
        
        # 集中扫描主 mdd 和 分卷 mdd (如 .1.mdd, .2.mdd)
        if os.path.isfile(_filename + '.mdd'):
            self._mdd_files.append(_filename + ".mdd")
        split_mdds = glob.glob(_filename + '.*.mdd')
        self._mdd_files.extend(sorted(split_mdds))
        
        # 如果存在任何 mdd 文件，则设定共用的数据库路径
        if self._mdd_files:
            self._mdd_db = _filename + ".mdd.db"
        else:
            self._mdd_db = ""

        # make index anyway
        if force_rebuild:
            self._make_mdx_index(self._mdx_db)
            if self._mdd_files:
                self._make_mdd_index(self._mdd_db)

        if os.path.isfile(self._mdx_db):
            #read from META table
            conn = sqlite3.connect(self._mdx_db)
            cursor = conn.execute("SELECT * FROM META WHERE key = \"version\"")
            #判断有无版本号
            for cc in cursor:
                self._version = cc[1]
            ################# if not version in fo #############
            if not self._version:
                print("version info not found")
                conn.close()
                self._make_mdx_index(self._mdx_db)
                print("mdx.db rebuilt!")
                if self._mdd_files:
                    self._make_mdd_index(self._mdd_db)
                    print("mdd.db rebuilt!")
                return None
            cursor = conn.execute(
                "SELECT * FROM META WHERE key = \"encoding\"")
            for cc in cursor:
                self._encoding = cc[1]
            cursor = conn.execute(
                "SELECT * FROM META WHERE key = \"stylesheet\"")
            for cc in cursor:
                self._stylesheet = json.loads(cc[1])

            cursor = conn.execute("SELECT * FROM META WHERE key = \"title\"")
            for cc in cursor:
                self._title = cc[1]

            cursor = conn.execute(
                "SELECT * FROM META WHERE key = \"description\"")
            for cc in cursor:
                self._description = cc[1]

        else:
            self._make_mdx_index(self._mdx_db)

        if self._mdd_files:
            if not os.path.isfile(self._mdd_db):
                self._make_mdd_index(self._mdd_db)
            else:
                # 【修复核心1】：检查旧数据库是否需要强制重建（是否缺少 mdd_file 字段）
                try:
                    conn = sqlite3.connect(self._mdd_db)
                    cursor = conn.execute("PRAGMA table_info(MDX_INDEX)")
                    cols = [c[1] for c in cursor]
                    conn.close()
                    if 'mdd_file' not in cols:
                        self._make_mdd_index(self._mdd_db)
                except Exception:
                    self._make_mdd_index(self._mdd_db)
        pass

    def _replace_stylesheet(self, txt):
        # substitute stylesheet definition
        encoding = 'utf-8'
        if isinstance(txt, bytes):
            txt = txt.decode(encoding)
        txt_list = re.split(r'`\d+`', txt)
        txt_tag = re.findall(r'`\d+`', txt)
        txt_styled = txt_list[0]
        for j, p in enumerate(txt_list[1:]):
            style = self._stylesheet[txt_tag[j][1:-1]]
            if p and p[-1] == '\n':
                txt_styled = txt_styled + style[0] + p.rstrip(
                ) + style[1] + '\r\n'
            else:
                txt_styled = txt_styled + style[0] + p + style[1]
        return txt_styled.encode(encoding)

    def _make_mdx_index(self, db_name):
        if os.path.exists(db_name):
            os.remove(db_name)
        mdx = MDX(self._mdx_file)
        self._mdx_db = db_name
        returned_index = mdx.get_index(check_block=self._check)
        index_list = returned_index['index_dict_list']
        conn = sqlite3.connect(db_name)
        c = conn.cursor()
        c.execute(''' CREATE TABLE MDX_INDEX
               (key_text text not null,
                file_pos integer,
                compressed_size integer,
                decompressed_size integer,
                record_block_type integer,
                record_start integer,
                record_end integer,
                offset integer
                )''')

        tuple_list = [(item['key_text'], item['file_pos'],
                       item['compressed_size'], item['decompressed_size'],
                       item['record_block_type'], item['record_start'],
                       item['record_end'], item['offset'])
                      for item in index_list]
        c.executemany('INSERT INTO MDX_INDEX VALUES (?,?,?,?,?,?,?,?)',
                      tuple_list)
        # build the metadata table
        meta = returned_index['meta']
        c.execute('''CREATE TABLE META
               (key text,
                value text
                )''')

        c.executemany('INSERT INTO META VALUES (?,?)',
                      [('encoding', meta['encoding']),
                       ('stylesheet', meta['stylesheet']),
                       ('title', meta['title']),
                       ('description', meta['description']),
                       ('version', version)])

        if self._sql_index:
            c.execute('''
                CREATE INDEX key_index ON MDX_INDEX (key_text)
                ''')

        conn.commit()
        conn.close()
        #set class member
        self._encoding = meta['encoding']
        self._stylesheet = json.loads(meta['stylesheet'])
        self._title = meta['title']
        self._description = meta['description']

    def _make_mdd_index(self, db_name):
        if os.path.exists(db_name):
            os.remove(db_name)
            
        conn = sqlite3.connect(db_name)
        c = conn.cursor()
        # 修改：新增 mdd_file 字段
        c.execute(''' CREATE TABLE MDX_INDEX
               (key_text text not null unique,
                file_pos integer,
                compressed_size integer,
                decompressed_size integer,
                record_block_type integer,
                record_start integer,
                record_end integer,
                offset integer,
                mdd_file text
                )''')

        # 循环遍历所有收集到的 mdd 文件
        for mdd_file in self._mdd_files:
            mdd = MDD(mdd_file)
            index_list = mdd.get_index(check_block=self._check)
            
            tuple_list = [(item['key_text'], item['file_pos'],
                           item['compressed_size'], item['decompressed_size'],
                           item['record_block_type'], item['record_start'],
                           item['record_end'], item['offset'], mdd_file)
                          for item in index_list]
            
            # 使用 INSERT OR IGNORE 避免分卷间同名文件导致主键冲突崩溃
            c.executemany('INSERT OR IGNORE INTO MDX_INDEX VALUES (?,?,?,?,?,?,?,?,?)',
                          tuple_list)
                          
        if self._sql_index:
            c.execute('''
                CREATE UNIQUE INDEX key_index ON MDX_INDEX (key_text)
                ''')

        conn.commit()
        conn.close()

    @staticmethod
    def get_data_by_index(fmdx, index):
        fmdx.seek(index['file_pos'])
        record_block_compressed = fmdx.read(index['compressed_size'])
        record_block_type = record_block_compressed[:4]
        record_block_type = index['record_block_type']
        decompressed_size = index['decompressed_size']
        if record_block_type == 0:
            _record_block = record_block_compressed[8:]
            # lzo compression
        elif record_block_type == 1:
            if lzo is None:
                print("LZO compression is not supported")
                # decompress
            header = b'\xf0' + pack('>I', index['decompressed_size'])
            _record_block = lzo.decompress(
                record_block_compressed[8:],
                initSize=decompressed_size,
                blockSize=1308672)
            # zlib compression
        elif record_block_type == 2:
            # decompress
            _record_block = zlib.decompress(record_block_compressed[8:])
        data = _record_block[index['record_start'] -
                             index['offset']:index['record_end'] -
                             index['offset']]
        return data

    def get_mdx_by_index(self, fmdx, index):
        data = self.get_data_by_index(fmdx, index)
        record = data.decode(
            self._encoding, errors='ignore').strip(u'\x00').encode('utf-8')
        if self._stylesheet:
            record = self._replace_stylesheet(record)
        record = record.decode('utf-8')
        return record

    def get_mdd_by_index(self, fmdx, index):
        return self.get_data_by_index(fmdx, index)

    @staticmethod
    def lookup_indexes(db, keyword, ignorecase=None):
        indexes = []
        # 【修复】：使用参数化查询（?），彻底防止由于包含引号等特殊字符导致的 SQL 崩溃或注入漏洞
        if ignorecase:
            sql = 'SELECT * FROM MDX_INDEX WHERE lower(key_text) = lower(?)'
        else:
            sql = 'SELECT * FROM MDX_INDEX WHERE key_text = ?'
            
        with sqlite3.connect(db) as conn:
            cursor = conn.execute(sql, (keyword,))
            for result in cursor:
                index = {}
                index['file_pos'] = result[1]
                index['compressed_size'] = result[2]
                index['decompressed_size'] = result[3]
                index['record_block_type'] = result[4]
                index['record_start'] = result[5]
                index['record_end'] = result[6]
                index['offset'] = result[7]
                
                if len(result) > 8:
                    index['mdd_file'] = result[8]
                indexes.append(index)
        return indexes

    def mdx_lookup(self, keyword, ignorecase=None):
        lookup_result_list = []
        indexes = self.lookup_indexes(self._mdx_db, keyword, ignorecase)
        with open(self._mdx_file, 'rb') as mdx_file:
            for index in indexes:
                lookup_result_list.append(
                    self.get_mdx_by_index(mdx_file, index))
        return lookup_result_list

    def mdd_lookup(self, keyword, ignorecase=None):
        lookup_result_list = []
        
        indexes = self.lookup_indexes(self._mdd_db, keyword, ignorecase)

        for index in indexes:
            mdd_file_path = index.get('mdd_file')
            
            # 【修复核心3】：极早期数据库容错，若为空则强制使用第一个 mdd
            if not mdd_file_path and self._mdd_files:
                mdd_file_path = self._mdd_files[0]
                
            if mdd_file_path and os.path.isfile(mdd_file_path):
                with open(mdd_file_path, 'rb') as mdd_file:
                    lookup_result_list.append(
                        self.get_mdd_by_index(mdd_file, index))
                        
        return lookup_result_list

    @staticmethod
    def get_keys(db, query=''):
        if not db:
            return []
            
        # 【修复】：使用参数化查询（?），防止 SQL 注入或语法错误
        if query:
            if '*' in query:
                query = query.replace('*', '%')
            else:
                query = query + '%'
            sql = 'SELECT key_text FROM MDX_INDEX WHERE key_text LIKE ?'
            
            with sqlite3.connect(db) as conn:
                cursor = conn.execute(sql, (query,))
                keys = [item[0] for item in cursor]
                return keys
        else:
            sql = 'SELECT key_text FROM MDX_INDEX'
            with sqlite3.connect(db) as conn:
                cursor = conn.execute(sql)
                keys = [item[0] for item in cursor]
                return keys

    def get_mdd_keys(self, query=''):
        # 【修复】：已在头部引入 unquote，移除了这里针对 Python 2 的 try...except 降级判断
        return self.get_keys(self._mdd_db, unquote(query))

    def get_mdx_keys(self, query=''):
        return self.get_keys(self._mdx_db, query)