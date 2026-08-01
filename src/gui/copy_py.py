import os
import re
from anki.utils import is_mac # 如果有需要

def process_and_copy_custom_py(mdx_path, py_path, dict_folder_path):
    """
    处理自定义的 .py 脚本，替换路径和注册名称，并复制到 dict 文件夹中
    """
    # 获取纯文件名作为词典名 (例如 "oaldpe 10th")
    dict_name = os.path.splitext(os.path.basename(mdx_path))[0]
    
    # 读取原始 .py 文件
    with open(py_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. 替换 DICT_PATH (兼容单引号、双引号和带 r 的情况)
    # 将 DICT_PATH = r'...' 替换为当前的真实 mdx_path
    # 注意处理 Windows 下路径的斜杠转义
    safe_mdx_path = mdx_path.replace('\\', '\\\\') 
    content = re.sub(
        r"DICT_PATH\s*=\s*[rR]?['\"].*?['\"]", 
        f"DICT_PATH = r'{safe_mdx_path}'", 
        content
    )

    # 2. 替换 @register
    # 将 @register([u'...', u'...']) 替换为当前提取的名字
    content = re.sub(
        r"@register\(\[.*?\]\)", 
        f"@register([u'本地词典-{dict_name}', u'MDX-{dict_name}'])", 
        content
    )

    # 3. 将修改后的文件写入到插件的 dict/ 文件夹下
    dest_py_path = os.path.join(dict_folder_path, os.path.basename(py_path))
    with open(dest_py_path, 'w', encoding='utf-8') as f:
        f.write(content)