"""Telegram 公开频道预览页抓取与消息解析客户端。"""

from __future__ import annotations

import html
import re
import time
from typing import Any, Dict, List

from app.log import logger
from app.sdk.network import RequestUtils

from ...utils.cache import create_platform_ttl_cache
from ...utils.http_client import normalize_proxies


class TelegramChannelError(RuntimeError):
    """Telegram 频道预览页请求或解析失败。"""


class TelegramChannelClient:
    """抓取 ``https://t.me/s/<频道>?q=<关键词>`` 并解析出频道消息。"""

    BASE_URL = "https://t.me"
    #: 频道用户名只允许字母、数字与下划线，长度 3~64。
    _CHANNEL_RE = re.compile(r"^[A-Za-z0-9_]{3,64}$")
    _HREF_PREFIXES = ("http://", "https://")
    #: 预览页缓存有效期（秒）与容量。
    _CACHE_TTL = 15 * 60
    _CACHE_SIZE = 256
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    def __init__(
            self,
            proxy: Any = None,
            request_timeout: int = 15,
            request_interval: float = 1.0,
    ) -> None:
        """初始化客户端：只保留连接参数，频道列表由服务层逐条传入。"""
        self._proxies = normalize_proxies(proxy)
        self.request_timeout = max(5, min(int(request_timeout or 15), 60))
        self.request_interval = max(0.0, min(float(request_interval or 0.0), 10.0))
        identity = f"{self.BASE_URL}|{self._proxies.get('https') if self._proxies else ''}"
        self._cache = create_platform_ttl_cache(
            "tg_channel:search", identity, maxsize=self._CACHE_SIZE, ttl=self._CACHE_TTL
        )

    @classmethod
    def normalize_channel(cls, value: Any) -> str:
        """把配置里的频道写法归一为不含 ``@`` 与 ``t.me/s/`` 前缀的用户名。"""
        text = str(value or "").strip()
        if not text:
            return ""
        text = re.sub(r"^https?://", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^(?:www\.)?t\.me/", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^(?:s/|joinchat/|c/)", "", text, flags=re.IGNORECASE)
        text = text.lstrip("@").split("?")[0].split("/")[0].strip()
        return text if cls._CHANNEL_RE.match(text) else ""

    @classmethod
    def normalize_channels(cls, values: Any) -> List[str]:
        """批量归一化频道列表，按原顺序去重并丢弃非法项。"""
        rows = values if isinstance(values, (list, tuple, set)) else [values]
        channels: List[str] = []
        for value in rows:
            channel = cls.normalize_channel(value)
            if channel and channel not in channels:
                channels.append(channel)
        return channels

    def search_channel(
            self, channel: Any, keyword: Any, message_limit: int = 0
    ) -> List[Dict[str, Any]]:
        """按关键词抓取单个频道的公开预览页并解析消息，失败时抛出异常。"""
        normalized = self.normalize_channel(channel)
        text = str(keyword or "").strip()
        if not normalized:
            raise TelegramChannelError(f"频道名不合法：{channel}")
        if not text:
            return []
        cache_key = f"{normalized}|{text.casefold()}|{int(message_limit or 0)}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return [dict(item) for item in cached]

        response = RequestUtils(
            headers=dict(self._HEADERS),
            proxies=self._proxies,
            timeout=self.request_timeout,
        ).get_res(f"{self.BASE_URL}/s/{normalized}", params={"q": text})
        try:
            if response is None:
                raise TelegramChannelError("请求未返回响应")
            status = int(getattr(response, "status_code", 0) or 0)
            if status != 200:
                raise TelegramChannelError(f"HTTP {status}")
            messages = self.parse_messages(response.text, normalized, message_limit)
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception as error:
                    logger.debug(f"TG 频道 {normalized} 响应释放失败：{error}")

        self._cache[cache_key] = messages
        return [dict(item) for item in messages]

    @classmethod
    def parse_messages(
            cls, page_html: Any, channel: str, message_limit: int = 0
    ) -> List[Dict[str, Any]]:
        """解析频道预览页 HTML，抽取消息正文、链接、发布时间与消息地址。"""
        content = str(page_html or "")
        if not content:
            return []
        # 延迟导入：BeautifulSoup 只在真正解析时加载。
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(content, "html.parser")
        messages: List[Dict[str, Any]] = []
        for node in soup.select("div.tgme_widget_message[data-post]"):
            message_id = cls._message_id(node.get("data-post"))
            if not message_id:
                continue
            text_node = node.select_one("div.tgme_widget_message_text")
            messages.append({
                "channel": channel,
                "message_id": message_id,
                "url": f"{cls.BASE_URL}/{channel}/{message_id}",
                "text": cls._node_text(text_node),
                "links": cls._message_links(node, text_node),
                "published": cls._published_at(node),
            })
            if message_limit and len(messages) >= int(message_limit):
                break
        return messages

    @staticmethod
    def _message_id(data_post: Any) -> str:
        """从 ``data-post="频道/消息ID"`` 中取出消息 ID。"""
        text = str(data_post or "").strip()
        return text.rsplit("/", 1)[-1].strip() if "/" in text else ""

    @staticmethod
    def _node_text(node: Any) -> str:
        """把正文节点渲染为保留换行的纯文本并反转义 HTML 实体。"""
        if node is None:
            return ""
        raw = node.get_text("\n", strip=True)
        lines = [line.strip() for line in str(raw or "").split("\n")]
        return html.unescape("\n".join(line for line in lines if line)).strip()

    @staticmethod
    def _published_at(node: Any) -> str:
        """读取消息发布时间（ISO8601），缺失时返回空串。"""
        time_node = node.select_one("a.tgme_widget_message_date time")
        if time_node is None:
            return ""
        return str(time_node.get("datetime") or "").strip()

    @classmethod
    def _message_links(cls, node: Any, text_node: Any) -> List[str]:
        """汇总正文与内联按钮中的绝对链接（跳过 ``?q=`` 话题链接与 ``tg://``）。"""
        anchors = list(text_node.select("a[href]") if text_node is not None else [])
        anchors += list(node.select("div.tgme_widget_message_inline_keyboard a[href]"))
        links: List[str] = []
        for anchor in anchors:
            href = str(anchor.get("href") or "").strip()
            if not href.lower().startswith(cls._HREF_PREFIXES):
                continue
            if href not in links:
                links.append(href)
        return links

    def clear_cache(self) -> int:
        """清空预览页缓存并返回被清理的条目数。"""
        count = len(list(self._cache.items()))
        self._cache.clear()
        return count

    def sleep_between_channels(self) -> None:
        """在连续抓取不同频道之间按配置间隔休眠，降低被限流概率。"""
        if self.request_interval > 0:
            time.sleep(self.request_interval)
