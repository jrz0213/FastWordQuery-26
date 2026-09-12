#-*- coding:utf-8 -*-
import os
import re
import urllib.parse
from ..base import *

DICT_PATH = r'C:/Users/jiang/Desktop/oaldpe 10th/oaldpe.mdx'

@register([u'本地词典-OALD10', u'MDX-OALD10'])
class Oald10(MdxService):

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

    def _extract_and_replace_audio_tags(self, html_text):
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

    @export([u'1. 英标和发音', u'Phonetics and Audio'])
    def fld_phonetics(self):
        html = self.get_html()
        if not html: return '' 
        
        soup = parse_html(html)
        result = []
        
        br_div = soup.find('div', {'class': 'phons_br'})
        if br_div:
            br_div.name = 'span'  
            result.append(u"英: " + self._extract_and_replace_audio_tags(str(br_div)))
            
        am_div = soup.find('div', {'class': 'phons_n_am'})
        if am_div:
            am_div.name = 'span'
            result.append(u"美: " + self._extract_and_replace_audio_tags(str(am_div)))
            
        return self._css("&nbsp;&nbsp;&nbsp;&nbsp;".join(result))

    @export([u'2. 英式和发音', u'UK Phonetics and Audio'])
    def fld_uk_phonetics(self):
        html = self.get_html()
        if not html: return '' 
        soup = parse_html(html)
        br_div = soup.find('div', {'class': 'phons_br'})
        if br_div:
            br_div.name = 'span'
            return self._css(u"英: " + self._extract_and_replace_audio_tags(str(br_div)))
        return ''

    @export([u'3. 美式和发音', u'US Phonetics and Audio'])
    def fld_us_phonetics(self):
        html = self.get_html()
        if not html: return '' 
        soup = parse_html(html)
        am_div = soup.find('div', {'class': 'phons_n_am'})
        if am_div:
            am_div.name = 'span'
            return self._css(u"美: " + self._extract_and_replace_audio_tags(str(am_div)))
        return ''



    @export([u'4. 首例句(无音频)和翻译', u'First Example with details translation'])
    def fld_first_example(self):
        html = self.get_html()
        if not html: return ''
        
        soup = parse_html(html)
        x_span = soup.find('span', {'class': 'x'})
        if x_span:
            en_sentence, translation = self._clean_example_node(x_span)
            return self._css(
                f'<details style="margin-bottom: 5px; color: #555;">\n'
                f'  <summary style="cursor: pointer;">{en_sentence}</summary>\n'
                f'  <div style="color: #999; font-size: 0.9em; padding-left: 15px;">{translation}</div>\n'
                f'</details>'
            )
        return ''

    @export([u'5. 一个例句(有音频文件的优先)', u'One Example (Audio Preferred)'])
    def fld_one_audio_example(self):
        html = self.get_html()
        if not html: return ''
        
        soup = parse_html(html)
        examples = soup.findAll('span', {'class': 'x'})
        
        ex_list = []
        for ex in examples:
            us_audios = self._extract_us_audios_from_example(ex)
            ex_list.append((ex, us_audios))
            
        ex_list.sort(key=lambda item: len(item[1]) > 0, reverse=True)
        if not ex_list: return ''
            
        target_ex, target_audios = ex_list[0]
        en_sentence, translation = self._clean_example_node(target_ex)
        audio_labels = " " + "".join([self._process_audio_link(a, True) for a in target_audios]) if target_audios else ""
        
        return self._css(
            f'<details style="margin-bottom: 5px; color: #555;">\n'
            f'  <summary style="cursor: pointer;">{en_sentence}{audio_labels}</summary>\n'
            f'  <div style="color: #999; font-size: 0.9em; padding-left: 15px;">{translation}</div>\n'
            f'</details>'
        )
    @export([u'6. 仅释义(无例句和同义词)', u'Definitions Only'])
    def fld_defs_only(self):
        """轻量级：仅提取释义，不含例句和同义词"""
        html = self.get_html()
        if not html: return ''
        
        soup = parse_html(html)
        senses = soup.findAll('li', {'class': 'sense'})
        my_str = ''
        for sense in senses:
            def_span = sense.find('span', {'class': 'def'})
            deft_span = sense.find('deft')
            en_def = def_span.text if def_span else ""
            cn_def = deft_span.text if deft_span else ""
            if en_def or cn_def:
                my_str += f'<div style="font-size:1.1em; margin-bottom:6px; border-bottom:1px dashed #ccc; padding-bottom:4px;"><b>{en_def}</b> ({cn_def})</div>\n'
        return self._css(my_str)
    @export([u'7. 释义与前3个例句和翻译', u'Definitions and 3 Examples (No Audio)'])
    def fld_def_and_3_examples(self):
        html = self.get_html()
        if not html: return ''
        
        soup = parse_html(html)
        senses = soup.findAll('li', {'class': 'sense'})
        
        my_str = ''
        for sense in senses:
            def_span = sense.find('span', {'class': 'def'})
            deft_span = sense.find('deft')
            en_def = def_span.text if def_span else ""
            cn_def = deft_span.text if deft_span else ""
            
            my_str += f'<details open style="font-size:1.1em; margin-bottom:10px; border-bottom:1px dashed #ccc; padding-bottom:5px;">\n'
            my_str += f'  <summary><b>{en_def}</b> ({cn_def})</summary>\n'
            
            examples = sense.findAll('span', {'class': 'x'})
            if examples:
                ex_list = []
                for ex in examples:
                    us_audios = self._extract_us_audios_from_example(ex)
                    ex_list.append((ex, us_audios))
                
                ex_list.sort(key=lambda item: len(item[1]) > 0, reverse=True)
                ex_list = ex_list[:3]
                
                my_str += '  <div style="margin-top: 5px; border-left: 2px solid #ddd; padding-left: 10px;">\n'
                for ex, _ in ex_list:
                    prefix_str = self._get_example_prefix(ex)
                    prefix_html = f"<b>{prefix_str}</b>：" if prefix_str else ""
                    en_sentence, translation = self._clean_example_node(ex)
                    
                    my_str += f'    <div style="font-size:0.9em; color:#555; margin-bottom:6px;">\n'
                    my_str += f'      <div>{prefix_html}{en_sentence}</div>\n'
                    if translation:
                        my_str += f'      <div style="color:#999; font-size:0.9em;">{translation}</div>\n'
                    my_str += f'    </div>\n'
                my_str += '  </div>\n'
                
            my_str += '</details>\n'
        
        return self._css(my_str)

    @export([u'8. 完整释义/例句/音频/同义词', u'Full Defs, Audio Examples & Synonyms'])
    def fld_full_defs_and_synonyms(self):
        html = self.get_html()
        if not html: return ''
        
        soup = parse_html(html)
        senses = soup.findAll('li', {'class': 'sense'})
        
        my_str = ''
        for sense in senses:
            def_span = sense.find('span', {'class': 'def'})
            deft_span = sense.find('deft')
            en_def = def_span.text if def_span else ""
            cn_def = deft_span.text if deft_span else ""
            
            my_str += f'<details open style="font-size:1.1em; margin-bottom:10px; border-bottom:1px dashed #ccc; padding-bottom:5px;">\n'
            my_str += f'  <summary><b>{en_def}</b> ({cn_def})</summary>\n'
            
            examples = sense.findAll('span', {'class': 'x'})
            if examples:
                ex_list = []
                for ex in examples:
                    us_audios = self._extract_us_audios_from_example(ex)
                    ex_list.append((ex, us_audios))
                
                ex_list.sort(key=lambda item: len(item[1]) > 0, reverse=True)
                ex_list = ex_list[:3]
                
                my_str += '  <div style="margin-top: 5px; border-left: 2px solid #ddd; padding-left: 10px;">\n'
                for ex, us_audios in ex_list:
                    prefix_str = self._get_example_prefix(ex)
                    prefix_html = f"<b>{prefix_str}</b>：" if prefix_str else ""
                    en_sentence, translation = self._clean_example_node(ex)
                    audio_labels = " " + "".join([self._process_audio_link(a, True) for a in us_audios]) if us_audios else ""
                    
                    my_str += f'    <div style="font-size:0.9em; color:#555; margin-bottom:6px;">\n'
                    my_str += f'      <div>{prefix_html}{en_sentence}{audio_labels}</div>\n'
                    if translation:
                        my_str += f'      <div style="color:#999; font-size:0.9em;">{translation}</div>\n'
                    my_str += f'    </div>\n'
                my_str += '  </div>\n'
                
            synonyms_box = sense.find('span', {'unbox': 'synonyms'})
            if synonyms_box:
                body = synonyms_box.find('span', {'class': 'body'})
                if body:
                    # 简化清理逻辑
                    for ex_ul in body.findAll('ul', {'class': 'examples'}):
                        ex_ul.decompose()
                    
                    first_line_terms = []
                    for unbox_span in body.findAll('span', {'class': 'unbox'}):
                        text = re.sub(r'\s+', ' ', unbox_span.get_text()).strip()
                        first_line_terms.append(text)
                        unbox_span.decompose()
                        
                    first_line_text = " ▪ ".join(first_line_terms).replace("▪ ▪", "▪").replace("▪  ▪", "▪")
                    
                    # 简化样式插入
                    for block_span in body.findAll(['span'], class_=['defpara', 'p', 'patterns']):
                        block_span['style'] = "display:block; margin-bottom:4px;"
                    
                    for eb_span in body.findAll('span', {'class': 'eb'}):
                        eb_span['style'] = "font-weight:bold;"
                        parent = eb_span.parent
                        if parent and parent.name == 'span' and 'defpara' in parent.get('class', []):
                            if not eb_span.get_text().endswith('：') and not eb_span.get_text().endswith(':'):
                                eb_span.append("：")
                        
                    syn_content = self._extract_and_replace_audio_tags(str(body))
                    
                    # 字号 1em, 简化边框
                    my_str += f'  <details style="border:1px solid #ccc; padding:8px; margin-top:8px;">\n'
                    my_str += f'    <summary style="font-size:1em; text-align:center;"><b>Synonyms 同义词辨析</b></summary>\n'
                    my_str += f'    <div style="font-size:0.9em; margin-top:8px; color:#444;">\n'
                    if first_line_text:
                        my_str += f'      <div style="font-weight:bold; margin-bottom:6px;">{first_line_text}</div>\n'
                    my_str += f'      <div>{syn_content}</div>\n'
                    my_str += f'    </div>\n'
                    my_str += '  </details>\n'
                
            my_str += '</details>\n'
                
        return self._css(my_str)

    def _css(self, val):
        return val