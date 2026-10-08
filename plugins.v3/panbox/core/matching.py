"""资源匹配的纯逻辑：季号识别、关键词拆分与偏好打分。

单独成模块的原因：这些规则与网络/网盘 I/O 无关，抽出来后既能被同步引擎复用，
也能在宿主之外直接单测（不触发 ``app.sdk`` 导入）。
"""

from __future__ import annotations

import re
from typing import Any, List

__all__ = ["match_season", "score_preference", "split_words"]

#: 常见的季号写法（含中文数字，如「第三季」「第十二季」）
SEASON_PATTERNS = (
    r"[Ss](\d{1,2})\b",
    r"第\s*([0-9]{1,2})\s*[季部]",
    r"第\s*([一二三四五六七八九十]{1,3})\s*[季部]",
    r"[Ss]eason\s*(\d{1,2})\b",
)

#: 中文数字字符表
_CN_DIGITS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def parse_number(value: str) -> int:
    """把阿拉伯数字或中文数字（一~九十九）解析成整数。

    :param value: 数字文本，如 ``"3"``、``"三"``、``"十二"``、``"二十三"``
    :return: 解析出的整数；无法解析返回 ``0``
    """
    text = (value or "").strip()
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    if text == "十":
        return 10
    if text.startswith("十"):
        return 10 + _CN_DIGITS.get(text[1:2], 0)
    if "十" in text:
        tens, _, ones = text.partition("十")
        return _CN_DIGITS.get(tens[:1], 0) * 10 + _CN_DIGITS.get(ones[:1], 0)
    return _CN_DIGITS.get(text[:1], 0)


def match_season(text: str, season: int) -> bool:
    """判断文本中是否出现指定季。

    :param text: 标题或正文
    :param season: 季号
    :return: 是否命中
    """
    if not text or not season:
        return False
    for pattern in SEASON_PATTERNS:
        for match in re.finditer(pattern, text):
            if parse_number(match.group(1)) == int(season):
                return True
    return False


def score_preference(text: str, prefer_words: List[str]) -> int:
    """按偏好关键词计算命中分。

    :param text: 标题与正文
    :param prefer_words: 偏好词列表
    :return: 命中数量
    """
    lowered = (text or "").lower()
    return sum(1 for word in prefer_words if word and word.lower() in lowered)


def split_words(raw: Any) -> List[str]:
    """把逗号/空格分隔的关键词串拆成列表。

    :param raw: 原始字符串或列表
    :return: 关键词列表
    """
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [part.strip() for part in re.split(r"[,，\s]+", str(raw or "")) if part.strip()]
