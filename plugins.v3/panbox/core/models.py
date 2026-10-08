"""PanBox 数据模型与网盘链接识别。

本模块只做纯数据处理，不发起网络请求，便于单测。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

__all__ = [
    "CLOUD_LABELS",
    "CLOUD_PATTERNS",
    "CloudLink",
    "ResourceItem",
    "classify_cloud_links",
    "classify_cloud_type",
    "extract_receive_code",
    "parse_share_url",
]

#: 各网盘的分享链接识别正则。键为内部代号，值为正则表达式。
CLOUD_PATTERNS: Dict[str, str] = {
    "baidu": r"https?://(?:pan|yun)\.baidu\.com/[^\s<>\"']+",
    "tianyi": r"https?://cloud\.189\.cn/[^\s<>\"']+",
    "aliyun": r"https?://[\w-]+\.(?:alipan|aliyundrive)\.com/[^\s<>\"']+",
    "p115": r"https?://(?:115|anxia|115cdn)\.com/s/[^\s<>\"']+",
    "p123": r"https?://(?:www\.)?123[^/\s<>\"']+\.com/s/[^\s<>\"']+",
    "quark": r"https?://pan\.quark\.cn/[^\s<>\"']+",
    "yun139": r"https?://caiyun\.139\.com/[^\s<>\"']+",
}

#: 网盘代号到中文名称的映射，用于界面展示。
CLOUD_LABELS: Dict[str, str] = {
    "baidu": "百度网盘",
    "tianyi": "天翼云盘",
    "aliyun": "阿里云盘",
    "p115": "115网盘",
    "p123": "123网盘",
    "quark": "夸克网盘",
    "yun139": "移动云盘",
}

_SHARE_CODE_RE = re.compile(r"/s/([A-Za-z0-9_-]+)")
_PASSWORD_KEYS = ("password", "pwd", "receive_code", "code")
_PASSWORD_RE = re.compile(
    r"(?:提取码|访问码|密码|密\s*码|pwd|password|code)\s*[:：=]?\s*([A-Za-z0-9]{4,8})",
    re.IGNORECASE,
)


@dataclass
class CloudLink:
    """一条从消息中识别出的网盘分享链接。"""

    cloud_type: str
    url: str
    receive_code: str = ""

    def to_dict(self) -> Dict[str, str]:
        """转换为可序列化字典。"""
        return {
            "cloud_type": self.cloud_type,
            "label": CLOUD_LABELS.get(self.cloud_type, self.cloud_type),
            "url": self.url,
            "receive_code": self.receive_code,
        }


@dataclass
class ResourceItem:
    """一条频道资源消息。"""

    channel_id: str
    channel_name: str = ""
    message_id: str = ""
    title: str = ""
    content: str = ""
    pub_date: str = ""
    tags: List[str] = field(default_factory=list)
    cloud_links: List[CloudLink] = field(default_factory=list)

    @property
    def url(self) -> str:
        """返回消息在 Telegram 上的原始链接。"""
        if not self.channel_id or not self.message_id:
            return ""
        return f"https://t.me/{self.channel_id}/{self.message_id}"

    @property
    def cloud_types(self) -> List[str]:
        """返回该消息包含的网盘类型列表。"""
        return sorted({link.cloud_type for link in self.cloud_links})

    def to_dict(self) -> Dict[str, Any]:
        """转换为可序列化字典。"""
        data = asdict(self)
        data["cloud_links"] = [link.to_dict() for link in self.cloud_links]
        data["cloud_types"] = self.cloud_types
        data["url"] = self.url
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceItem":
        """从字典还原资源条目（用于历史与收藏持久化）。"""
        links = [
            CloudLink(
                cloud_type=str(item.get("cloud_type") or ""),
                url=str(item.get("url") or ""),
                receive_code=str(item.get("receive_code") or ""),
            )
            for item in (data.get("cloud_links") or [])
            if isinstance(item, dict)
        ]
        return cls(
            channel_id=str(data.get("channel_id") or ""),
            channel_name=str(data.get("channel_name") or ""),
            message_id=str(data.get("message_id") or ""),
            title=str(data.get("title") or ""),
            content=str(data.get("content") or ""),
            pub_date=str(data.get("pub_date") or ""),
            tags=[str(tag) for tag in (data.get("tags") or [])],
            cloud_links=links,
        )


def classify_cloud_links(text: str) -> List[CloudLink]:
    """从一段文本中识别各类网盘分享链接并去重。

    :param text: 待识别的文本（通常为消息正文与链接的拼接）
    :return: 去重后的网盘链接列表，保持网盘类型的固定顺序
    """
    if not text:
        return []
    found: List[CloudLink] = []
    seen: set[str] = set()
    for cloud_type, pattern in CLOUD_PATTERNS.items():
        for url in re.findall(pattern, text):
            cleaned = url.rstrip(".,;)]}\u3002\uff0c")
            if cleaned in seen:
                continue
            seen.add(cleaned)
            found.append(CloudLink(cloud_type=cloud_type, url=cleaned))
    return found


def parse_share_url(url: str) -> Optional[Dict[str, str]]:
    """从网盘分享链接中解析出分享码与提取码。

    :param url: 分享链接，例如 ``https://115cdn.com/s/swsvxg73fwl?password=i2e8``
    :return: 含 ``cloud_type`` / ``share_code`` / ``receive_code`` 的字典；无法识别时返回 ``None``
    """
    if not url:
        return None
    match = _SHARE_CODE_RE.search(url)
    if not match:
        return None
    query = parse_qs(urlparse(url).query)
    receive_code = ""
    for key in _PASSWORD_KEYS:
        values = query.get(key)
        if values:
            receive_code = values[0]
            break
    # 提取码只从查询串取值；消息正文里以「提取码：xxxx」等形式给出的口令
    # 由上层调用方在解析消息文本时补充，避免在 URL 内部做模糊猜测。
    return {
        "cloud_type": classify_cloud_type(url),
        "share_code": match.group(1),
        "receive_code": receive_code,
    }


def classify_cloud_type(url: str) -> str:
    """判断单个链接属于哪个网盘。

    :param url: 待判断的链接
    :return: 网盘内部代号；无法识别时返回空字符串
    """
    if not url:
        return ""
    for cloud_type, pattern in CLOUD_PATTERNS.items():
        if re.match(pattern, url):
            return cloud_type
    return ""


def extract_receive_code(text: str) -> str:
    """从消息正文中提取网盘提取码。

    :param text: 消息正文或标题
    :return: 提取码；未匹配时返回空字符串
    """
    if not text:
        return ""
    match = _PASSWORD_RE.search(text)
    return match.group(1) if match else ""
