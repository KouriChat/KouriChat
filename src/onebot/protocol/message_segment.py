"""
消息段处理模块
负责 OneBot 消息格式的互相转换：
- CQ 码字符串（v11 字符串格式）
- 消息段数组（v11 数组格式 / v12 格式）
- 纯文本（供 KouriChat LLM 处理）
"""

import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger('onebot.message_segment')


# ─────────────────────────────────────────────
# CQ 码解析
# ─────────────────────────────────────────────

def parse_cq_params(params_str: str) -> Dict[str, str]:
    """解析 CQ 码参数字符串，例如 'file=xxx,type=flash' → {'file':'xxx','type':'flash'}"""
    result = {}
    if not params_str:
        return result
    for part in params_str.split(','):
        if '=' in part:
            k, _, v = part.partition('=')
            result[k.strip()] = unescape_cq(v.strip())
    return result


def unescape_cq(text: str) -> str:
    """CQ 码参数值反转义"""
    return (text
            .replace('&#44;', ',')
            .replace('&#91;', '[')
            .replace('&#93;', ']')
            .replace('&amp;', '&'))


def escape_cq(text: str) -> str:
    """CQ 码参数值转义"""
    return (text
            .replace('&', '&amp;')
            .replace('[', '&#91;')
            .replace(']', '&#93;')
            .replace(',', '&#44;'))


def cq_to_array(cq_text: str) -> List[Dict[str, Any]]:
    """
    将 CQ 码字符串转换为消息段数组。
    例如：'你好[CQ:at,qq=123]世界' →
    [
        {"type": "text", "data": {"text": "你好"}},
        {"type": "at", "data": {"qq": "123"}},
        {"type": "text", "data": {"text": "世界"}}
    ]
    """
    segments = []
    pattern = re.compile(r'\[CQ:([a-zA-Z0-9_]+)(?:,([^\]]*))?\]')
    pos = 0

    for match in pattern.finditer(cq_text):
        # 匹配前的纯文本
        if match.start() > pos:
            plain = cq_text[pos:match.start()]
            if plain:
                segments.append(build_text_segment(plain))

        cq_type = match.group(1)
        params_str = match.group(2) or ''
        params = parse_cq_params(params_str)
        segments.append({'type': cq_type, 'data': params})

        pos = match.end()

    # 末尾纯文本
    if pos < len(cq_text):
        plain = cq_text[pos:]
        if plain:
            segments.append(build_text_segment(plain))

    return segments if segments else [build_text_segment(cq_text)]


def array_to_cq(segments: List[Dict[str, Any]]) -> str:
    """
    将消息段数组转换为 CQ 码字符串。
    """
    parts = []
    for seg in segments:
        seg_type = seg.get('type', 'text')
        data = seg.get('data', {})

        if seg_type == 'text':
            parts.append(escape_cq(data.get('text', '')))
        else:
            params = ','.join(f"{k}={escape_cq(str(v))}" for k, v in data.items() if v is not None)
            if params:
                parts.append(f"[CQ:{seg_type},{params}]")
            else:
                parts.append(f"[CQ:{seg_type}]")

    return ''.join(parts)


def array_to_text(segments: List[Dict[str, Any]]) -> str:
    """
    从消息段数组提取纯文本内容（用于 LLM 处理）。
    图片、语音等非文本类型附加可读描述。
    """
    parts = []
    for seg in segments:
        seg_type = seg.get('type', 'text')
        data = seg.get('data', {})

        if seg_type == 'text':
            parts.append(data.get('text', ''))
        elif seg_type == 'image':
            parts.append('[图片]')
        elif seg_type in ('record', 'voice'):
            parts.append('[语音]')
        elif seg_type == 'video':
            parts.append('[视频]')
        elif seg_type == 'at':
            qq = data.get('qq', data.get('user_id', ''))
            parts.append(f'@{qq}')
        elif seg_type == 'face':
            parts.append('[表情]')
        elif seg_type == 'reply':
            parts.append('[回复]')
        elif seg_type == 'forward':
            parts.append('[合并转发]')
        elif seg_type == 'location':
            name = data.get('title', '未知地点')
            parts.append(f'[位置: {name}]')
        elif seg_type == 'share':
            title = data.get('title', '')
            parts.append(f'[分享: {title}]' if title else '[分享]')
        else:
            parts.append(f'[{seg_type}]')

    return ''.join(parts)


def extract_image_urls(segments: List[Dict[str, Any]]) -> List[str]:
    """从消息段中提取图片 URL 或文件路径"""
    urls = []
    for seg in segments:
        if seg.get('type') == 'image':
            data = seg.get('data', {})
            url = data.get('url') or data.get('file', '')
            if url:
                urls.append(url)
    return urls


# ─────────────────────────────────────────────
# 消息段构建器
# ─────────────────────────────────────────────

def build_text_segment(text: str) -> Dict[str, Any]:
    """构建纯文本消息段"""
    return {'type': 'text', 'data': {'text': text}}


def build_image_segment(file: str, url: Optional[str] = None) -> Dict[str, Any]:
    """构建图片消息段"""
    data: Dict[str, Any] = {'file': file}
    if url:
        data['url'] = url
    return {'type': 'image', 'data': data}


def build_at_segment(user_id: str) -> Dict[str, Any]:
    """构建 @ 消息段"""
    return {'type': 'at', 'data': {'qq': str(user_id)}}


def build_voice_segment(file: str) -> Dict[str, Any]:
    """构建语音消息段"""
    return {'type': 'record', 'data': {'file': file}}


def build_face_segment(face_id: int) -> Dict[str, Any]:
    """构建 QQ 表情消息段"""
    return {'type': 'face', 'data': {'id': str(face_id)}}


def build_reply_segment(message_id: int) -> Dict[str, Any]:
    """构建回复消息段"""
    return {'type': 'reply', 'data': {'id': str(message_id)}}


def normalize_message(message: Any) -> List[Dict[str, Any]]:
    """
    将任意格式的 message 归一化为消息段数组。
    支持：字符串（含CQ码）、列表（消息段数组）。
    """
    if isinstance(message, str):
        return cq_to_array(message)
    elif isinstance(message, list):
        # 验证并标准化每个消息段
        result = []
        for seg in message:
            if isinstance(seg, dict) and 'type' in seg:
                result.append({
                    'type': seg['type'],
                    'data': seg.get('data', {})
                })
        return result if result else [build_text_segment('')]
    elif isinstance(message, dict):
        # 单个消息段
        return [{'type': message.get('type', 'text'), 'data': message.get('data', {})}]
    else:
        return [build_text_segment(str(message))]
