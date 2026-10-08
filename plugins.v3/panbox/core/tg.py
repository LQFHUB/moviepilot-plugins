"""Telegram 公开频道的资源搜索与解析。

实现原理：抓取 ``https://t.me/s/<频道>`` 的公开预览页 HTML，解析其中的消息块，
再按网盘分享链接正则识别资源。带关键词时使用 Telegram 站内搜索参数 ``?q=``，
该搜索为模糊匹配，因此解析后需要按关键词做一次后置过滤。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

from app.sdk.network import RequestUtils
from bs4 import BeautifulSoup

from .models import CloudLink, ResourceItem, classify_cloud_links, extract_receive_code

__all__ = ["ChannelSearcher", "DEFAULT_CHANNELS"]

#: Telegram 频道预览页基址，可通过配置覆盖（部分网络环境需要镜像）。
DEFAULT_BASE_URL = "https://t.me/s"

#: 默认频道列表，取自用户原有 CloudSaver 中的频道配置。
DEFAULT_CHANNELS: List[Dict[str, str]] = [
    {"id": "QukanMovie", "name": "115影视资源分享频道"},
    {"id": "Lsp115", "name": "115网盘资源分享频道"},
    {"id": "Quark_Movies", "name": "夸克云盘影视资源频道"},
    {"id": "shareAliyun", "name": "阿里云盘发布频道"},
    {"id": "Remux4KFilm", "name": "奥斯卡4K蓝光(精品)影视磁力站"},
]

_WHITESPACE_RE = re.compile(r"\s+")


class ChannelSearcher:
    """Telegram 频道资源搜索器。"""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 20,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """初始化搜索器。

        :param base_url: 频道预览页基址，默认 ``https://t.me/s``
        :param timeout: 单次请求超时秒数
        :param proxy: 可选代理地址，形如 ``http://127.0.0.1:7890``
        :param user_agent: 可选自定义 User-Agent
        """
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = timeout or 20
        self._proxies = {"http": proxy, "https": proxy} if proxy else None
        self._ua = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

    def search(
        self,
        keyword: str = "",
        channels: Optional[Iterable[Dict[str, Any]]] = None,
        limit: int = 30,
        filter_by_keyword: bool = True,
    ) -> Dict[str, Any]:
        """在多个频道中搜索资源。

        :param keyword: 搜索关键词，为空表示抓取频道最新消息
        :param channels: 频道列表，元素含 ``id`` 与可选 ``name``；为空时使用默认频道
        :param limit: 单个频道最多返回的结果条数
        :param filter_by_keyword: 是否按关键词对标题/正文做后置过滤
        :return: 含 ``items``（结果列表）与 ``errors``（失败频道说明）的字典
        """
        channel_list = self._normalize_channels(channels)
        items: List[ResourceItem] = []
        errors: List[Dict[str, str]] = []
        for channel in channel_list:
            channel_id = channel["id"]
            try:
                html = self._fetch(channel_id, keyword)
            except Exception as error:  # noqa: BLE001 - 单频道失败不影响整体搜索
                errors.append({"channel_id": channel_id, "message": f"{type(error).__name__}: {error}"})
                continue
            if not html:
                errors.append({"channel_id": channel_id, "message": "频道返回空内容或不可访问"})
                continue
            parsed = self._parse(html, channel)
            if keyword and filter_by_keyword:
                parsed = [item for item in parsed if _match_keyword(item, keyword)]
            items.extend(parsed[: max(limit or 0, 0)] if limit else parsed)
        items.sort(key=lambda item: item.pub_date, reverse=True)
        return {"items": [item.to_dict() for item in items], "errors": errors}

    def _normalize_channels(self, channels: Optional[Iterable[Dict[str, Any]]]) -> List[Dict[str, str]]:
        """把配置中的频道项规整为 ``id``/``name`` 结构。

        :param channels: 原始频道配置
        :return: 规整后的频道列表；全部无效时回退到默认频道
        """
        normalized: List[Dict[str, str]] = []
        for item in channels or []:
            if isinstance(item, str):
                channel_id, name = item.strip(), ""
            elif isinstance(item, dict):
                channel_id = str(item.get("id") or "").strip()
                name = str(item.get("name") or "").strip()
            else:
                continue
            if not channel_id:
                continue
            normalized.append({"id": channel_id.lstrip("@"), "name": name or channel_id})
        return normalized or list(DEFAULT_CHANNELS)

    def _fetch(self, channel_id: str, keyword: str) -> Optional[str]:
        """抓取指定频道的预览页。

        :param channel_id: 频道 ID（不含 @）
        :param keyword: 搜索关键词
        :return: 页面 HTML；请求失败时返回 ``None``
        """
        url = f"{self._base_url}/{quote(channel_id)}"
        if keyword:
            url = f"{url}?q={quote(keyword)}"
        client = RequestUtils(
            ua=self._ua,
            accept_type="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            referer=self._base_url,
            timeout=self._timeout,
            proxies=self._proxies,
            verify=True,
        )
        return client.get(url)

    @staticmethod
    def _parse(html: str, channel: Dict[str, str]) -> List[ResourceItem]:
        """解析频道页面 HTML 中的资源消息。

        :param html: 频道预览页 HTML
        :param channel: 所属频道信息
        :return: 资源条目列表（仅保留含网盘链接的消息）
        """
        soup = BeautifulSoup(html, "html.parser")
        results: List[ResourceItem] = []
        for wrap in soup.select(".tgme_widget_message_wrap"):
            message = wrap.select_one(".tgme_widget_message")
            text_element = wrap.select_one(".js-message_text")
            if text_element is None:
                continue
            title, body = _split_title_and_body(text_element)
            content = body
            link_hrefs = [anchor.get("href") or "" for anchor in text_element.find_all("a")]
            tags = [
                anchor.get_text(strip=True)
                for anchor in text_element.find_all("a")
                if anchor.get_text(strip=True).startswith("#")
            ]
            links = classify_cloud_links(" ".join(link_hrefs) + " " + content)
            if not links:
                continue
            receive_code = extract_receive_code(content) or extract_receive_code(title)
            if receive_code:
                links = [
                    link if link.receive_code else CloudLink(link.cloud_type, link.url, receive_code)
                    for link in links
                ]
            time_element = wrap.select_one("time")
            post = (message.get("data-post") if message else "") or ""
            message_id = post.rsplit("/", 1)[-1] if "/" in post else ""
            results.append(
                ResourceItem(
                    channel_id=channel["id"],
                    channel_name=channel.get("name") or channel["id"],
                    message_id=message_id,
                    title=title,
                    content=content,
                    pub_date=(time_element.get("datetime") if time_element else "") or "",
                    tags=tags,
                    cloud_links=links,
                )
            )
        return results


def _split_title_and_body(text_element: Any) -> tuple[str, str]:
    """把消息文本拆成「标题」与「正文」。

    标题取第一个 ``<br>`` 之前的内容，正文为剩余文本。

    :param text_element: BeautifulSoup 的 ``.js-message_text`` 节点
    :return: (标题, 正文)
    """
    title_parts: List[str] = []
    body_parts: List[str] = []
    in_title = True
    for child in text_element.children:
        if getattr(child, "name", None) == "br":
            in_title = False
            body_parts.append("\n")
            continue
        text = child.get_text() if hasattr(child, "get_text") else str(child)
        if in_title:
            title_parts.append(text)
        else:
            body_parts.append(text)
    title = _WHITESPACE_RE.sub(" ", "".join(title_parts)).strip()
    body = _WHITESPACE_RE.sub(" ", "".join(body_parts)).strip()
    if not title:
        title, body = body, ""
    return title, body


def _match_keyword(item: ResourceItem, keyword: str) -> bool:
    """判断资源条目是否与关键词相关（用于 Telegram 模糊搜索结果的后置过滤）。

    :param item: 资源条目
    :param keyword: 搜索关键词
    :return: 是否命中
    """
    needle = keyword.strip().lower()
    if not needle:
        return True
    haystack = f"{item.title} {item.content}".lower()
    if needle in haystack:
        return True
    # 支持「多个关键词用空格分隔，需全部命中」的用法
    parts = [part for part in needle.split() if part]
    return len(parts) > 1 and all(part in haystack for part in parts)
