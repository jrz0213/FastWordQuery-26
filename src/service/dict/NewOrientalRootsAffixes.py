# -*- coding:utf-8 -*-
import re
from ..base import *

# ！！！请把这里的路径替换为你电脑上词典的实际绝对路径！！！
# 例如：DICT_PATH = u'D:\\Anki\\addon\\Dicts\\新东方词根词缀.mdx'
DICT_PATH = r'C:/dic/新东方词根词缀/NewOrientalRootsAffixes.mdx'

@register([u'新东方词根词缀', u'NewOrientalRootsAffixes'])
class MDXNewOrientalRoots(MdxService): #[cite: 1, 2]

    def __init__(self):
        # 优先使用硬编码的路径
        dict_path = DICT_PATH
        
        # 如果没有填写固定路径，则尝试自动探测
        if not dict_path:
            from ...service import service_manager, service_pool
            for clazz in service_manager.mdx_services:
                service = service_pool.get(clazz.__unique__)
                title = service.builder._title if service and service.support else u''
                service_pool.put(service)
                # 尝试匹配词典标题
                if u'新东方' in title or u'NewOriental' in title:
                    dict_path = service.dict_path
                    break
                    
        super(MDXNewOrientalRoots, self).__init__(dict_path) #

    @property
    def title(self):
        return getattr(self, '__register_label__', self.unique) #[cite: 2]

    # ==========================================
    # 需求 1：提取所有同词根的词（仅词汇列表）
    # ==========================================
    @export([u'同词根单词列表', u'Root Words List']) #[cite: 1, 2]
    def fld_word_list(self):
        html = self.get_html() #[cite: 2]
        if not html:
            return '未获取到词典内容，请检查路径是否正确'
        
        soup = parse_html(html) #[cite: 1, 2]
        head_words_div = soup.find('div', {'class': 'head-words'})
        
        if head_words_div:
            # 提取所有 <a> 标签内的单词纯文本
            words = [a.text.strip() for a in head_words_div.find_all('a')]
            return ", ".join(words)
        return ''

    # ==========================================
    # 需求 2：提取当前单词的词缀记忆
    # ==========================================
    @export([u'词缀记忆(当前单词)', u'Affix Memory']) #[cite: 1, 2]
    def fld_affix_memory(self):
        html = self.get_html() #[cite: 2]
        if not html:
            return ''
            
        soup = parse_html(html) #[cite: 1, 2]
        
        root_h2 = soup.find('h2')
        root_title = root_h2.text.strip() if root_h2 else ""
        
        target_entry = None
        # self.word 是 FastWordQuery 传入的当前查询单词[cite: 1]
        word_spans = soup.find_all('span', {'class': 'bold'})
        for span in word_spans:
            if span.text.strip() == self.word:
                target_entry = span.find_parent('div', class_=re.compile(r'word-entry'))
                break
                
        if not target_entry:
            return ''
            
        sense_block = target_entry.find_parent('div', {'class': 'sense'})
        sense_text = sense_block.find('p', {'class': 'sense'}).text.strip() if sense_block else ""
        
        meaning = target_entry.find('p', {'class': 'meaning'})
        meaning_text = meaning.text.strip() if meaning else ""
        
        derive = target_entry.find('p', {'class': 'derive'})
        derive_text = derive.text.strip() if derive else ""
        
        res_parts = [root_title, sense_text, meaning_text, derive_text]
        return "<br>".join([part for part in res_parts if part])

    # ==========================================
    # 需求 3：提取词根常见作用及附带解释的列表
    # ==========================================
    @export([u'词根作用及单词释义', u'Root Functions and Meanings']) #[cite: 1, 2]
    def fld_root_functions_meanings(self):
        html = self.get_html() #[cite: 2]
        if not html:
            return ''
            
        soup = parse_html(html) #[cite: 1, 2]
        res_html = ""
        
        senses = soup.find_all('div', {'class': 'sense'})
        for sense in senses:
            sense_p = sense.find('p', {'class': 'sense'})
            if sense_p:
                res_html += u"<b>{}</b><br>".format(sense_p.text.strip())
                
            entries = sense.find_all('div', class_=re.compile(r'word-entry'))
            for entry in entries:
                word_span = entry.find('span', {'class': 'bold'})
                meaning_p = entry.find('p', {'class': 'meaning'})
                
                w_text = word_span.text.strip() if word_span else ""
                m_text = meaning_p.text.strip() if meaning_p else ""
                
                if w_text:
                    res_html += u"{} : {}<br>".format(w_text, m_text)
                    
            res_html += "<br>"
            
        return res_html