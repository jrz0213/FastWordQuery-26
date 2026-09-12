# -*- coding:utf-8 -*-
import os
from ..base import *
'''
我用夸克网盘给你分享了「百词斩」，点击链接或复制整段内容，打开「夸克网盘APP」即可获取。
/~09f83Zuayn~:/
链接：https://pan.quark.cn/s/83e94647b048?pwd=PsRW
提取码：PsRW

'''

DICT_PATH = r'C:/dic/百词斩.1/百词斩图解词典.mdx'

@register([u'百词斩词典', u'Baicizhan'])
class BaicizhanService(MdxService):
    """
    百词斩词典专用提取脚本。
    继承自 MdxService，支持从本地 mdx/mdd 文件中提取文本及图片。
    """

    def __init__(self, dict_path=DICT_PATH):
        # 传递路径给 MdxService 进行初始化
        super(BaicizhanService, self).__init__(dict_path)

    @property
    def title(self):
        # 默认返回 @register 注册的名称
        return getattr(self, '__register_label__', self.unique)

    @export([u'音标', u'Phonetic'])
    def fld_phonetic(self):
        """提取音标"""
        html = self.get_html()
        soup = parse_html(html)
        pron_span = soup.find('span', {'class': 'pron'})
        
        if pron_span:
            return pron_span.get_text(strip=True)
        return ''

    @export([u'基本释义', u'Definition'])
    def fld_definition(self):
        """提取词性与中文释义"""
        html = self.get_html()
        soup = parse_html(html)
        mean_div = soup.find('div', {'class': 'mean_cn'})
        
        if mean_div:
            # 查找到所有的 explain 标签
            explains = mean_div.find_all('span', {'class': 'explain'})
            # 使用换行符拼接不同的词性和解释
            return '<br>'.join([span.get_text(strip=True) for span in explains])
        return ''

    @export([u'例句', u'Example'])
    def fld_sentence(self):
        """提取英文例句及其中文翻译"""
        html = self.get_html()
        soup = parse_html(html)
        exg_div = soup.find('div', {'class': 'exg'})
        
        if exg_div:
            st = exg_div.find('span', {'class': 'st'})
            sttr = exg_div.find('span', {'class': 'sttr'})
            
            st_text = st.get_text(strip=True) if st else ''
            sttr_text = sttr.get_text(strip=True) if sttr else ''
            
            if st_text or sttr_text:
                return f"{st_text}<br>{sttr_text}"
        return ''

    @export([u'图片', u'Image'])
    def fld_image(self):
        """提取情景插图并保存至 Anki 媒体库"""
        html = self.get_html()
        soup = parse_html(html)
        img = soup.find('img', {'class': 'illu'})
        
        if img and img.get('src'):
            src = img.get('src')
            # MDD 字典资源索引一般需要 '/' 开头
            val = '/' + src if not src.startswith('/') else src
            
            # 提取文件扩展名
            file_extension = os.path.splitext(src)[1][1:].strip().lower()
            
            # 使用 base 提供的哈希重命名方法，避免同名图片覆盖
            name = get_hex_name('mdx-'+self.unique.lower(), val, file_extension)
            
            # 从 MDD 文件内物理提取该资源
            saved_name = self.save_file(val, name)
            if saved_name:
                # 转换为 Anki 标准媒体标签
                return self.get_anki_label(saved_name, 'img')
            
            # 若提取失败，保留原始标签尝试直接渲染
            return f'<img src="{src}">'
        return ''