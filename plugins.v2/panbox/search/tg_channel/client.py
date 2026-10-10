"""Telegram 公开频道预览页抓取与消息解析客户端。"""

from __future__ import annotations

import html
import re
import time
from typing import Any, Dict, List, Mapping, Optional

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
    #: 频道展示信息（名称/头像）变化极少，缓存有效期与容量单独放宽。
    _INFO_CACHE_TTL = 7 * 24 * 60 * 60
    _INFO_CACHE_SIZE = 512
    #: 频道对象中用户名、名称与图标的候选键名（兼容旧值与其他写法）。
    _ID_KEYS = ("id", "username", "user_name", "value", "channel", "url", "link")
    _NAME_KEYS = ("name", "title", "display_name", "channel_name")
    _ICON_KEYS = ("icon", "avatar", "avatar_url", "photo", "image", "icon_url")
    _TITLE_SUFFIX_RE = re.compile(
        r"\s*[–—\-|]\s*Telegram(?:\s+Messenger)?(?:\s+Web)?\s*$",
        re.IGNORECASE,
    )
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
        self._info_cache = create_platform_ttl_cache(
            "tg_channel:info", identity,
            maxsize=self._INFO_CACHE_SIZE, ttl=self._INFO_CACHE_TTL,
        )

    @staticmethod
    def _first_text(source: Mapping[str, Any], keys: Any) -> str:
        """按候选键名顺序取出第一个非空文本值。"""
        for key in keys:
            value = source.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    @classmethod
    def normalize_channel(cls, value: Any) -> str:
        """把配置里的频道写法归一为不含 ``@`` 与 ``t.me/s/`` 前缀的用户名。

        兼容两种配置形态：纯字符串（旧值），以及 ``{id, name, icon}`` 对象。
        """
        if isinstance(value, Mapping):
            value = (
                cls._first_text(value, cls._ID_KEYS)
                or cls._first_text(value, cls._NAME_KEYS)
            )
        text = str(value or "").strip()
        if not text:
            return ""
        text = re.sub(r"^https?://", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^(?:www\.)?t\.me/", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^(?:s/|joinchat/|c/)", "", text, flags=re.IGNORECASE)
        text = text.lstrip("@").split("?")[0].split("/")[0].strip()
        return text if cls._CHANNEL_RE.match(text) else ""

    @staticmethod
    def _normalize_icon(value: Any) -> str:
        """归一化图标地址：补全协议相对地址，丢弃带空白或过长的值。"""
        text = str(value or "").strip()
        if not text or len(text) > 1024 or re.search(r"\s", text):
            return ""
        if text.startswith("//"):
            return f"https:{text}"
        return text

    @classmethod
    def normalize_channel_items(cls, values: Any) -> List[Dict[str, str]]:
        """把频道配置归一为 ``{id, name, icon}`` 对象列表，兼容纯字符串旧值。

        名称缺省时回落为频道用户名，图标缺省时留空表示交给自动获取。
        """
        rows = values if isinstance(values, (list, tuple, set)) else [values]
        items: List[Dict[str, str]] = []
        seen = set()
        for value in rows:
            raw = value if isinstance(value, Mapping) else {}
            channel = cls.normalize_channel(value)
            if not channel or channel.casefold() in seen:
                continue
            seen.add(channel.casefold())
            name = cls._first_text(raw, cls._NAME_KEYS)
            items.append({
                "id": channel,
                "name": name or channel,
                "icon": cls._normalize_icon(cls._first_text(raw, cls._ICON_KEYS)),
            })
        return items

    @classmethod
    def normalize_channels(cls, values: Any) -> List[str]:
        """批量归一化频道用户名列表，按原顺序去重并丢弃非法项。"""
        return [item["id"] for item in cls.normalize_channel_items(values)]

    def _fetch_text(
            self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> str:
        """请求 Telegram 公开页面并返回 HTML 文本，失败时抛出异常。"""
        response = RequestUtils(
            headers=dict(self._HEADERS),
            proxies=self._proxies,
            timeout=self.request_timeout,
        ).get_res(f"{self.BASE_URL}{path}", params=params or None)
        try:
            if response is None:
                raise TelegramChannelError("请求未返回响应")
            status = int(getattr(response, "status_code", 0) or 0)
            if status != 200:
                raise TelegramChannelError(f"HTTP {status}")
            return str(getattr(response, "text", "") or "")
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception as error:
                    logger.debug(f"TG 页面 {path} 响应释放失败：{error}")

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

        page_html = self._fetch_text(f"/s/{normalized}", {"q": text})
        messages = self.parse_messages(page_html, normalized, message_limit)
        # 预览页同时携带频道信息块，顺手缓存频道名称与头像，避免额外请求。
        info = self.parse_channel_info(page_html, normalized)
        if info.get("name") or info.get("icon"):
            self._info_cache[normalized] = info

        self._cache[cache_key] = messages
        return [dict(item) for item in messages]

    @classmethod
    def parse_channel_info(
            cls, page_html: Any, channel: str = ""
    ) -> Dict[str, str]:
        """从频道公开页解析展示信息：用户名、名称与头像地址。

        兼容两种页面形态：``t.me/s/<频道>`` 预览页（头像在
        ``i.tgme_page_photo_image > img`` 内）与 ``t.me/<频道>`` 主页
        （``img.tgme_page_photo_image`` 自身即头像）。
        """
        normalized = cls.normalize_channel(channel)
        result = {"id": normalized, "name": "", "icon": ""}
        content = str(page_html or "")
        if not content:
            return result
        # 延迟导入：BeautifulSoup 只在真正解析时加载。
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(content, "html.parser")
        photo = soup.select_one(
            ".tgme_page_photo_image img, img.tgme_page_photo_image, "
            ".tgme_header_link img"
        )
        if photo is not None:
            result["icon"] = cls._normalize_icon(photo.get("src"))
        title_node = (
            soup.select_one(".tgme_channel_info_header_title")
            or soup.select_one(".tgme_page_title")
        )
        if title_node is not None:
            result["name"] = cls._inline_text(title_node)
        if not result["name"]:
            meta = soup.select_one('meta[property="og:title"]')
            if meta is not None:
                result["name"] = cls._TITLE_SUFFIX_RE.sub(
                    "", cls._inline_text(meta.get("content"))
                ).strip()
        username_node = soup.select_one(".tgme_channel_info_header_username a")
        if username_node is not None:
            resolved = cls.normalize_channel(username_node.get_text(" ", strip=True))
            if resolved:
                result["id"] = resolved
        if not result["id"]:
            result["id"] = normalized
        return result

    @staticmethod
    def _inline_text(node: Any) -> str:
        """把节点渲染为单行文本（保留表情等内联内容）。"""
        if node is None:
            return ""
        if isinstance(node, str):
            raw = node
        else:
            raw = node.get_text(" ", strip=True)
        return re.sub(r"\s+", " ", html.unescape(str(raw or ""))).strip()

    def fetch_channel_info(
            self, channel: Any, force: bool = False
    ) -> Dict[str, str]:
        """抓取频道主页并解析名称与头像，结果按长有效期缓存。

        主页体积远小于预览页；``force=True`` 时忽略缓存强制刷新。
        """
        normalized = self.normalize_channel(channel)
        if not normalized:
            raise TelegramChannelError(f"频道名不合法：{channel}")
        if not force:
            cached = self._info_cache.get(normalized)
            if cached:
                return dict(cached)
        page_html = self._fetch_text(f"/{normalized}")
        info = self.parse_channel_info(page_html, normalized)
        info["fetched"] = True
        self._info_cache[normalized] = info
        return dict(info)

    def resolve_channel_info(self, channel: Any) -> Dict[str, str]:
        """返回频道展示信息：优先用预览页已解析结果，缺项时补抓主页。

        抓取失败不抛异常，回落到频道用户名，避免影响搜索主流程。
        """
        normalized = self.normalize_channel(channel)
        fallback = {"id": normalized, "name": normalized, "icon": ""}
        if not normalized:
            return fallback
        cached = self._info_cache.get(normalized)
        if cached and (
                cached.get("fetched")
                or (cached.get("name") and cached.get("icon"))
        ):
            return dict(cached)
        try:
            info = self.fetch_channel_info(normalized)
        except TelegramChannelError as error:
            logger.debug(f"TG 频道 {normalized} 头像信息获取失败：{error}")
            return dict(cached) if cached else fallback
        if cached:
            merged = dict(cached)
            merged.update({k: v for k, v in info.items() if v})
            return merged
        return info

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
        """清空预览页与频道信息缓存，返回被清理的条目总数。"""
        count = len(list(self._cache.items()))
        self._cache.clear()
        count += len(list(self._info_cache.items()))
        self._info_cache.clear()
        return count

    def sleep_between_channels(self) -> None:
        """在连续抓取不同频道之间按配置间隔休眠，降低被限流概率。"""
        if self.request_interval > 0:
            time.sleep(self.request_interval)
