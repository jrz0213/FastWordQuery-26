
'''
词典原帖:https://forum.freemdict.com/t/topic/30466
词典下载：
我用夸克网盘给你分享了「牛津高阶英汉双解词典第10版完美版」，点击链接或复制整段内容，打开「夸克网盘APP」即可获取。
/~811e3Ztezy~:/
链接：https://pan.quark.cn/s/1a9e58b59ca6?pwd=D3XB
提取码：D3XB
'''
#-*- coding:utf-8 -*-
import os
import re
import urllib.parse
import random
import hashlib
from ..base import *

DICT_PATH = r'C:/Users/jiang/Desktop/oaldpe 10th/oaldpe.mdx'

@register([u'本地OALD10', u'MDXOALD10'])
class MDX_Oald10(MdxService):

    def __init__(self):
        dict_path = DICT_PATH
        if not dict_path:
            from ...service import service_manager, service_pool
            for clazz in service_manager.mdx_services:
                service = service_pool.get(clazz.__unique__)
                title = service.builder._title if service and service.support else u''
                service_pool.put(service)
                if title.startswith(u'OALD10') or title.startswith(u'牛津高阶'):
                    dict_path = service.dict_path
                    break
        super(Oald10, self).__init__(dict_path)

    @property
    def title(self):
        return getattr(self, '__register_label__', self.unique)

    def _process_audio_link(self, raw_audio_path, is_example=False):
        if not raw_audio_path:
            return ""
        mdd_key = raw_audio_path.replace('sound://', '').strip()
        mdd_key = urllib.parse.unquote(mdd_key)
        if not mdd_key.startswith('/') and not mdd_key.startswith('\\'):
            mdd_key = '\\' + mdd_key
        normalized_path = mdd_key.replace('\\', '/')
        base_name = normalized_path.split('/')[-1]
        
        export_name = base_name
        if is_example:
            export_name = export_name.replace('.ogg', '.mp3')
            
        name = f"mdx-{self.unique.lower()}-{export_name}"
        saved_name = self.save_file(mdd_key, name) 
        final_name = saved_name if saved_name else name
        return self.get_anki_label(final_name, 'audio')

    def _extract_us_audios_from_example(self, ex_node):
        us_audio_links = []
        a_tags = ex_node.findAll('a')
        for a in a_tags:
            href = a.get('href', '')
            if href.startswith('sound://'):
                clean_href = href.replace('sound://', '')
                class_str = " ".join(a.get('class', [])).lower()
                if 'audio_us' in class_str or 'pron-us' in class_str or '_us' in clean_href.lower() or '_am' in clean_href.lower():
                    us_audio_links.append(clean_href)
                    
        if not us_audio_links:
            brackets = re.findall(r'\[sound:(.*?)\]', str(ex_node))
            us_audio_links.extend([b for b in brackets if '_us' in b.lower() or '_am' in b.lower()])
        return us_audio_links

    def _extract_and_replace_audio_tags(self, html_text, strip_all=False):
        if strip_all:
            html_text = re.sub(r'<a[^>]+?href=["\']sound://[^"\']+["\'][^>]*>.*?</a>', '', html_text)
            html_text = re.sub(r'\[sound:(.*?)\]', '', html_text)
            return html_text
            
        def repl_a_tag(match):
            return self._process_audio_link(match.group(1), is_example=False)
        html_text = re.sub(r'<a[^>]+?href=["\']sound://([^"\']+)["\'][^>]*>.*?</a>', repl_a_tag, html_text)
        
        def repl_bracket(match):
            path = match.group(1)
            if path.startswith('mdx-'):
                return f"[sound:{path}]"
            return self._process_audio_link(path, is_example=False)
        html_text = re.sub(r'\[sound:(.*?)\]', repl_bracket, html_text)
        return html_text

    def _clean_example_node(self, ex_node):
        xt_span = ex_node.find('xt')
        translation = xt_span.text if xt_span else ""
        if xt_span:
            xt_span.extract()
            
        for a in ex_node.findAll('a'):
            if a.get('href', '').startswith('sound://'):
                a.extract()
                
        en_sentence = "".join([str(c) for c in ex_node.contents])
        en_sentence = re.sub(r'\[sound:.*?\]', '', en_sentence)
        en_sentence = re.sub(r'\s+', ' ', en_sentence).strip()
        return en_sentence, translation

    def _get_example_prefix(self, x_span):
        prefix_texts = []
        if not x_span or not x_span.parent:
            return ""
        for child in x_span.parent.children:
            if child == x_span:
                break
            if child.name in ['span', 'strong', 'b', 'i']:
                text = child.get_text().strip()
                if text:
                    prefix_texts.append(text)
        return " ".join(prefix_texts).strip()

    # ====== 核心抽取辅助方法 ======
    def _get_first_preferred_example(self, html):
        """获取首个例句（有音频优先）"""
        soup = parse_html(html)
        examples = soup.findAll('span', {'class': 'x'})
        if not examples: return None, []
        
        ex_list = []
        for ex in examples:
            us_audios = self._extract_us_audios_from_example(ex)
            ex_list.append((ex, us_audios))
            
        ex_list.sort(key=lambda item: len(item[1]) > 0, reverse=True)
        return ex_list[0]

    def _get_seeded_random_example(self, html):
        """获取随机带音频例句（基于词条HTML生成固定种子，保证前后两次调用抽出同一个例句）"""
        soup = parse_html(html)
        examples = soup.findAll('span', {'class': 'x'})
        valid_candidates = []
        for ex in examples:
            us_audios = self._extract_us_audios_from_example(ex)
            if us_audios: 
                valid_candidates.append((ex, us_audios))
                
        if not valid_candidates:
            return None, []
            
        # 根据 HTML 内容生成哈希种子，保证对于同一个单词，随机结果是固定的
        seed_val = int(hashlib.md5(html.encode('utf-8')).hexdigest(), 16)
        rnd = random.Random(seed_val)
        return rnd.choice(valid_candidates)

    def _build_dict_html(self, html, include_audio=True):
        """构建完整的词典 HTML (控制是否包含音频)"""
        soup = parse_html(html)
        senses = soup.findAll('li', {'class': 'sense'})
        
        my_str = '<div class="dict-block">\n'
        for sense in senses:
            def_span = sense.find('span', {'class': 'def'})
            deft_span = sense.find('deft')
            en_def = def_span.text if def_span else ""
            cn_def = deft_span.text if deft_span else ""
            
            my_str += f'<details open class="dict-sense">\n'
            my_str += f'  <summary class="dict-def-title"><span class="dict-def-en">{en_def}</span> <span class="dict-def-cn">({cn_def})</span></summary>\n'
            
            examples = sense.findAll('span', {'class': 'x'})
            if examples:
                ex_list = []
                for ex in examples:
                    us_audios = self._extract_us_audios_from_example(ex)
                    ex_list.append((ex, us_audios))
                
                ex_list.sort(key=lambda item: len(item[1]) > 0, reverse=True)
                ex_list = ex_list[:3]
                
                my_str += '  <div class="dict-examples">\n'
                for ex, us_audios in ex_list:
                    prefix_str = self._get_example_prefix(ex)
                    prefix_html = f'<span class="dict-ex-prefix">{prefix_str}</span>：' if prefix_str else ""
                    en_sentence, translation = self._clean_example_node(ex)
                    
                    audio_labels = ""
                    if include_audio and us_audios:
                        audio_labels = " " + "".join([self._process_audio_link(a, True) for a in us_audios])
                    
                    my_str += f'    <div class="dict-ex">\n'
                    my_str += f'      <div class="dict-ex-en"><span class="dict-audio-wrap">{audio_labels}</span> <span class="dict-text-wrap">{prefix_html}{en_sentence}</span></div>\n'
                    if translation:
                        my_str += f'      <div class="dict-ex-cn">{translation}</div>\n'
                    my_str += f'    </div>\n'
                my_str += '  </div>\n'
                
            synonyms_box = sense.find('span', {'unbox': 'synonyms'})
            if synonyms_box:
                body = synonyms_box.find('span', {'class': 'body'})
                if body:
                    for ex_ul in body.findAll('ul', {'class': 'examples'}):
                        ex_ul.decompose()
                    
                    first_line_terms = []
                    for unbox_span in body.findAll('span', {'class': 'unbox'}):
                        text = re.sub(r'\s+', ' ', unbox_span.get_text()).strip()
                        first_line_terms.append(text)
                        unbox_span.decompose()
                        
                    first_line_text = " ▪ ".join(first_line_terms).replace("▪ ▪", "▪").replace("▪  ▪", "▪")
                    
                    for block_span in body.findAll(['span'], class_=['defpara', 'p', 'patterns']):
                        block_span['class'] = "dict-syn-block"
                    
                    for eb_span in body.findAll('span', {'class': 'eb'}):
                        eb_span['class'] = "dict-syn-eb"
                        parent = eb_span.parent
                        if parent and parent.name == 'span' and 'defpara' in parent.get('class', []):
                            if not eb_span.get_text().endswith('：') and not eb_span.get_text().endswith(':'):
                                eb_span.append("：")
                        
                    # 判断是否剔除同义词里的发音
                    syn_content = self._extract_and_replace_audio_tags(str(body), strip_all=(not include_audio))
                    
                    my_str += f'  <details class="dict-synonyms-box">\n'
                    my_str += f'    <summary class="dict-synonyms-title">Synonyms 同义词辨析</summary>\n'
                    my_str += f'    <div class="dict-synonyms-content">\n'
                    if first_line_text:
                        my_str += f'      <div class="dict-synonyms-header">{first_line_text}</div>\n'
                    my_str += f'      <div>{syn_content}</div>\n'
                    my_str += f'    </div>\n'
                    my_str += '  </details>\n'
                
            my_str += '</details>\n'
        my_str += '</div>'
        return self._css(my_str)


    # ==============================================================================
    # 以下为严格按照要求的 9 个导出字段
    # ==============================================================================

    @export([u'1. 英标和发音（英）', u'UK Phonetics and Audio'])
    def fld_uk_phonetics(self):
        html = self.get_html()
        if not html: return '' 
        soup = parse_html(html)
        br_div = soup.find('div', {'class': 'phons_br'})
        if br_div:
            br_div.name = 'span'
            br_div['class'] = 'dict-phonetics'
            return self._css(u"英: " + self._extract_and_replace_audio_tags(str(br_div)))
        return ''

    @export([u'2. 英标和发音（美）', u'US Phonetics and Audio'])
    def fld_us_phonetics(self):
        html = self.get_html()
        if not html: return '' 
        soup = parse_html(html)
        am_div = soup.find('div', {'class': 'phons_n_am'})
        if am_div:
            am_div.name = 'span'
            am_div['class'] = 'dict-phonetics'
            return self._css(u"美: " + self._extract_and_replace_audio_tags(str(am_div)))
        return ''

    @export([u'3. 首个例句(有音频优先)', u'First Example (Audio Preferred)'])
    def fld_first_audio_example_en(self):
        html = self.get_html()
        if not html: return ''
        ex_node, us_audios = self._get_first_preferred_example(html)
        if not ex_node: return ''
        
        prefix_str = self._get_example_prefix(ex_node)
        prefix_html = f'<span class="dict-ex-prefix">{prefix_str}</span>：' if prefix_str else ""
        en_sentence, _ = self._clean_example_node(ex_node)
        audio_labels = " " + "".join([self._process_audio_link(a, True) for a in us_audios]) if us_audios else ""
        
        return self._css(f'<div class="dict-ex-en"><span class="dict-audio-wrap">{audio_labels}</span> <span class="dict-text-wrap">{prefix_html}{en_sentence}</span></div>')

    @export([u'4. 3中例句对应的翻译', u'Translation for Field 3'])
    def fld_first_audio_example_cn(self):
        html = self.get_html()
        if not html: return ''
        ex_node, _ = self._get_first_preferred_example(html)
        if not ex_node: return ''
        
        _, translation = self._clean_example_node(ex_node)
        if not translation: return ''
        return self._css(f'<div class="dict-ex-cn">{translation}</div>')

    @export([u'5. 随机有发音的例句', u'Random Audio Example (EN)'])
    def fld_random_audio_example_en(self):
        html = self.get_html()
        if not html: return ''
        ex_node, us_audios = self._get_seeded_random_example(html)
        if not ex_node: return ''
        
        prefix_str = self._get_example_prefix(ex_node)
        prefix_html = f'<span class="dict-ex-prefix">{prefix_str}</span>：' if prefix_str else ""
        en_sentence, _ = self._clean_example_node(ex_node)
        audio_labels = " " + "".join([self._process_audio_link(a, True) for a in us_audios])
        
        return self._css(f'<div class="dict-ex-en"><span class="dict-audio-wrap">{audio_labels}</span> <span class="dict-text-wrap">{prefix_html}{en_sentence}</span></div>')

    @export([u'6. 随机有发音的例句的翻译（和5对应）', u'Translation for Field 5'])
    def fld_random_audio_example_cn(self):
        html = self.get_html()
        if not html: return ''
        ex_node, _ = self._get_seeded_random_example(html)
        if not ex_node: return ''
        
        _, translation = self._clean_example_node(ex_node)
        if not translation: return ''
        return self._css(f'<div class="dict-ex-cn">{translation}</div>')

    @export([u'7. 释义（英语和中文）', u'Definitions Only'])
    def fld_defs_only(self):
        html = self.get_html()
        if not html: return ''
        
        soup = parse_html(html)
        senses = soup.findAll('li', {'class': 'sense'})
        my_str = '<div class="dict-block">\n'
        for sense in senses:
            def_span = sense.find('span', {'class': 'def'})
            deft_span = sense.find('deft')
            en_def = def_span.text if def_span else ""
            cn_def = deft_span.text if deft_span else ""
            if en_def or cn_def:
                my_str += f'<div class="dict-sense" style="border-bottom:1px dashed #ccc; padding-bottom:4px; margin-bottom:6px;">\n'
                my_str += f'  <span class="dict-def-en"><b>{en_def}</b></span> <span class="dict-def-cn">({cn_def})</span>\n'
                my_str += f'</div>\n'
        my_str += '</div>'
        return self._css(my_str)

    @export([u'8. mini词典（无音频）', u'Mini Dict (No Audio)'])
    def fld_mini_dict_no_audio(self):
        html = self.get_html()
        if not html: return ''
        return self._build_dict_html(html, include_audio=False)

    @export([u'9. 完整词典（含音频）', u'Full Dict (With Audio)'])
    def fld_full_dict_with_audio(self):
        html = self.get_html()
        if not html: return ''
        return self._build_dict_html(html, include_audio=True)

    def _css(self, val):
        return val