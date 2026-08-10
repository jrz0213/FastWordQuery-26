# -*- coding:utf-8 -*-
import os
import re
import urllib.parse
from ..utils.logger import logger

# ==========================================
# 定义常见的互换白名单（同类后缀才允许互换）
# ==========================================
AUDIO_EXTS = {'mp3', 'ogg', 'wav', 'spx', 'aac', 'm4a', 'flac', 'wma'}
IMAGE_EXTS = {'jpg', 'jpeg', 'png', 'gif', 'svg', 'bmp', 'webp', 'tif', 'tiff', 'ico'}
VIDEO_EXTS = {'mp4', 'webm', 'mkv', 'avi', 'mov', 'flv', 'wmv'}

def build_fuzzy_pattern(filename):
    """
    底层模糊匹配 GLOB 表达式构建器：
    放宽标点符号限制，使用星号 '*' 扩大数据库搜索范围
    """
    decoded = urllib.parse.unquote(filename)
    clean_basename = re.split(r'[\\/]', decoded)[-1]
    base_name, _ = os.path.splitext(clean_basename)
    
    # 将连续的非字母数字字符统一替换为一个 '*'
    fuzzy_base = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5]+', '*', base_name)
    fuzzy_base = fuzzy_base.strip('*')
    
    glob_pattern = f"*{fuzzy_base}*.*"
    glob_pattern = re.sub(r'\*+', '*', glob_pattern)
    return glob_pattern

def process_fuzzy_media(builder, dict_title, html_media_list, save_func):
    """
    处理媒体文件的模糊匹配逻辑。
    """
    replacement_map = {}
    
    for original_name in html_media_list:
        # 1. 构建底层数据库搜索规则
        pattern = build_fuzzy_pattern(original_name)
        
        # ========================================================
        # 🌟 核心防伪技术：提取纯字母数字核心，用于拦截子串误伤
        # ========================================================
        decoded = urllib.parse.unquote(original_name)
        clean_basename = re.split(r'[\\/]', decoded)[-1]
        req_base_no_ext, _ = os.path.splitext(clean_basename)
        # 例如: "_option#_us_2" -> "optionus2"
        req_core = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5]', '', req_base_no_ext).lower()
        
        try:
            matched_keys = builder.get_mdd_keys(pattern)
            if not matched_keys:
                logger.warning(f"[模糊匹配] MDD 库中未找到符合规则的文件: {pattern}")
                continue
                
            original_ext = original_name.lower().split('.')[-1] if '.' in original_name else ''
            matched = False
            
            for matched_key in matched_keys:
                actual_basename = os.path.basename(matched_key.replace('\\', os.path.sep))
                actual_base_no_ext, actual_ext_with_dot = os.path.splitext(actual_basename)
                
                # ========================================================
                # 🌟 执行防伪校验：比对实际文件的字母核心
                # ========================================================
                # 例如: "nuclear_option_us_2" -> "nuclearoptionus2"
                actual_core = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5]', '', actual_base_no_ext).lower()
                
                if req_core != actual_core:
                    logger.debug(f"[模糊匹配] 核心字符校验不符，已拦截子串误伤: 期望[{req_core}] 实际捞取[{actual_core}]")
                    continue
                # ========================================================
                
                ext = actual_ext_with_dot.strip('.').lower()
                
                # ==== 核心过滤逻辑：防止后缀跨界误伤 ====
                is_valid_match = False
                if original_ext in AUDIO_EXTS and ext in AUDIO_EXTS:
                    is_valid_match = True
                elif original_ext in IMAGE_EXTS and ext in IMAGE_EXTS:
                    is_valid_match = True
                elif original_ext in VIDEO_EXTS and ext in VIDEO_EXTS:
                    is_valid_match = True
                elif original_ext == ext:
                    is_valid_match = True
                    
                if not is_valid_match:
                    continue
                # ========================================

                logger.info(f"[模糊匹配] 命中有效且安全的实体文件: [{actual_basename}]")
                
                saved_path = save_func(matched_key)
                if saved_path:
                    if ext in AUDIO_EXTS:
                        tag = f"[sound:{saved_path}]"
                    elif ext in IMAGE_EXTS:
                        tag = f'<img src="{saved_path}">'
                    elif ext in VIDEO_EXTS:
                        tag = f'<video controls="controls" width="100%" height="auto" src="{saved_path}"></video>'
                    else:
                        tag = f'<a href="{saved_path}">附件</a>'
                        
                    replacement_map[original_name] = tag
                    matched = True
                    break
            
            if not matched:
                logger.warning(f"[模糊匹配] 找到了文件，但因核心校验不符或媒体类型不符被拦截。")
                
        except Exception as e:
            logger.error(f"[模糊匹配] 匹配解析期间发生异常: {str(e)}")
            
    return replacement_map