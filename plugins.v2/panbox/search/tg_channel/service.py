"""Telegram 频道搜索服务：正文后置过滤与网盘链接、提取码提取。"""

from __future__ import annotations

import re
import time
from itertools import zip_longest
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

from app.log import logger
from app.schemas.types import MediaType

from .client import TelegramChannelClient, TelegramChannelError
from ..magnet import (
    extract_magnet_hash,
    extract_magnet_links,
    normalize_magnets,
    parse_size_str,
)
from ..matching import (
    extract_resource_tags,
    extract_season,
    extract_year,
    media_aliases,
    normalize_season,
    resource_title_matches,
    unique_texts,
)
from ..types import (
    SHARE_PASSWORD_QUERY_KEYS,
    SUPPORTED_RESOURCE_TYPES,
    append_share_password,
    resource_type_from_url,
)
from ...core.search import SearchQuery


class TelegramChannelSearchService:
    """把 TG 频道消息转换为 PanBox 统一搜索候选。"""

    #: 标题行前缀（如「名称：」）与提取码描述文本的识别正则。
    _TITLE_PREFIX_RE = re.compile(r"^(?:资源)?(?:名称|标题|片名|影片名)\s*[:：]\s*")
    _PASSWORD_RE = re.compile(
        r"(?:提取码|访问码|密码|口令|pwd|password|code)\s*[:：=]?\s*([A-Za-z0-9]{4,16})",
        re.IGNORECASE,
    )
    #: 每个频道最多尝试的关键词数量，避免站内模糊搜索反复请求。
    _MAX_KEYWORDS_PER_CHANNEL = 2
    _MAX_TITLE_LENGTH = 120
    _MAX_DESCRIPTION_LENGTH = 600
    #: 正文话题标签（TG 频道常用 #剧情 #4K 之类标注），作为候选标签的来源之一。
    _HASHTAG_RE = re.compile(r"#([A-Za-z0-9\u3400-\u9fff_]{2,16})")
    #: 只识别带单位的体积描述，避免把标题里的年份等纯数字当成字节数。
    _SIZE_TEXT_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:PB|TB|GB|MB|KB)\b", re.IGNORECASE)

    def __init__(
            self,
            client: TelegramChannelClient,
            channels: Any = (),
            result_limit: int = 20,
            timeout: float = 60.0,
    ) -> None:
        """初始化服务：频道列表与数量、总超时均来自渠道配置。"""
        self._client = client
        self._channel_items = TelegramChannelClient.normalize_channel_items(channels)
        self._channels = [item["id"] for item in self._channel_items]
        self._channel_config = {
            item["id"]: item for item in self._channel_items
        }
        self._result_limit = max(1, int(result_limit or 20))
        self._timeout = max(5.0, min(float(timeout or 60.0), 120.0))

    def _channel_meta(self, channel: str) -> Dict[str, str]:
        """汇总频道展示信息：配置的名称/图标优先，缺项用公开页自动获取补齐。"""
        entry = self._channel_config.get(channel) or {}
        info: Dict[str, Any] = {}
        try:
            info = self._client.resolve_channel_info(channel) or {}
        except Exception as error:
            logger.debug(f"[TG频道] {channel} 频道信息读取失败：{error}")
        configured_name = str(entry.get("name") or "").strip()
        if not configured_name or configured_name == channel:
            configured_name = str(info.get("name") or "").strip()
        icon = str(entry.get("icon") or "").strip() or str(
            info.get("icon") or ""
        ).strip()
        return {
            "id": channel,
            "name": configured_name or channel,
            "icon": icon,
            "url": f"{TelegramChannelClient.BASE_URL}/{channel}",
        }

    @staticmethod
    def _keywords(mediainfo: Any, media_type: Any, season: Optional[int]) -> List[str]:
        """按媒体标题生成 TG 站内搜索关键词：电影带年份，剧集用纯标题。"""
        titles = unique_texts((
            getattr(mediainfo, "title", ""),
            getattr(mediainfo, "original_title", ""),
            getattr(mediainfo, "original_name", ""),
        ))
        year = extract_year(getattr(mediainfo, "year", None))
        if media_type == MediaType.MOVIE and year:
            return unique_texts([f"{title} {year}" for title in titles] + titles)
        return titles

    @staticmethod
    def _expected_titles(mediainfo: Any) -> List[str]:
        """汇总用于正文匹配的媒体标题，包含多语言别名。"""
        return unique_texts((
            getattr(mediainfo, "title", ""),
            getattr(mediainfo, "original_title", ""),
            getattr(mediainfo, "original_name", ""),
            *media_aliases(mediainfo),
        ))

    @classmethod
    def extract_password(cls, url: Any, text: Any) -> str:
        """从分享链接查询参数或正文描述中提取提取码。

        查询参数键表复用 ``search/types.py`` 的 ``SHARE_PASSWORD_QUERY_KEYS``，
        与 ``append_share_password`` 写入端的口径保持一致。
        """
        try:
            query = parse_qs(urlparse(str(url or "")).query)
        except ValueError:
            query = {}
        for key in (*SHARE_PASSWORD_QUERY_KEYS.values(), "code", "passcode"):
            values = query.get(key) or []
            if values and str(values[0]).strip():
                return str(values[0]).strip()
        matched = cls._PASSWORD_RE.search(str(text or ""))
        return matched.group(1).strip() if matched else ""

    @classmethod
    def _extract_title(cls, text: Any) -> str:
        """取正文首个有效行作为标题，去掉「名称：」前缀与纯表情行。"""
        for line in str(text or "").split("\n"):
            candidate = cls._TITLE_PREFIX_RE.sub("", line).strip()
            if not candidate:
                continue
            if not any(
                    ch.isalnum() or "\u3400" <= ch <= "\u9fff" for ch in candidate
            ):
                continue
            return candidate[:cls._MAX_TITLE_LENGTH]
        collapsed = re.sub(r"\s+", " ", str(text or "")).strip()
        return collapsed[:cls._MAX_TITLE_LENGTH]

    @staticmethod
    def _description(text: Any) -> str:
        """压缩正文空白并截断，作为候选描述下发前端。"""
        collapsed = re.sub(r"\s+", " ", str(text or "")).strip()
        return collapsed[:TelegramChannelSearchService._MAX_DESCRIPTION_LENGTH]

    @classmethod
    def _extract_size(cls, text: Any) -> int:
        """从正文中提取带单位的体积（复用 ``parse_size_str`` 做单位换算）。"""
        matched = cls._SIZE_TEXT_RE.search(str(text or ""))
        return parse_size_str(matched.group(0)) if matched else 0

    @classmethod
    def _hashtags(cls, text: Any) -> List[str]:
        """提取正文中的话题标签，与 CloudSaver 的标签口径保持一致。"""
        return [
            matched.group(1)
            for matched in cls._HASHTAG_RE.finditer(str(text or ""))
        ]

    @classmethod
    def _matches_media(
            cls,
            text: str,
            titles: List[str],
            expected_year: str,
            expected_season: Optional[int],
    ) -> bool:
        """对 TG 模糊搜索结果做后置过滤：标题按词边界命中并校验年份/季号。

        剧集正文常带更新日期等干扰年份，因此只对电影启用严格年份校验。
        """
        strict_year = bool(expected_year) and expected_season is None
        if not resource_title_matches(text, titles, expected_year, strict_year=strict_year):
            return False
        if expected_season is not None:
            season = extract_season(text)
            if season is not None and season != expected_season:
                return False
        return True

    @staticmethod
    def _merge_round_robin(
            groups: Iterable[List[Dict[str, Any]]], limit: int
    ) -> List[Dict[str, Any]]:
        """按频道轮转合并候选，避免单个频道占满结果上限。"""
        rows = [group for group in groups if group]
        if not rows:
            return []
        merged = [
            item for column in zip_longest(*rows) for item in column
            if item is not None
        ]
        return merged[:limit]

    @classmethod
    def _message_links(cls, message: Dict[str, Any]) -> List[Dict[str, str]]:
        """汇总消息中的网盘与磁力链接，按「类型 + 链接」去重。"""
        candidates = list(message.get("links") or [])
        candidates += extract_magnet_links(message.get("text") or "")
        rows: List[Dict[str, str]] = []
        seen = set()
        for url in candidates:
            resource_type = resource_type_from_url(url)
            if resource_type not in SUPPORTED_RESOURCE_TYPES:
                continue
            if resource_type == "magnet" and not extract_magnet_hash(url):
                continue
            key = (resource_type, str(url).split("#")[0])
            if key in seen:
                continue
            seen.add(key)
            rows.append({"url": url, "resource_type": resource_type})
        return rows

    @classmethod
    def _build_candidates(
            cls,
            messages: List[Dict[str, Any]],
            titles: List[str],
            expected_year: str,
            expected_season: Optional[int],
            limit: int,
            channel_meta: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """把命中媒体的消息转换为统一候选（一条消息可产出多条链接候选）。

        字段口径与 pansou、seedhub 等既有渠道对齐，并额外携带来源频道的
        分组信息（``group_key``、``group_title``、``group_icon``）与频道明细。
        同一频道内重复转发的同一链接只保留最新一条消息的元数据。
        """
        meta = dict(channel_meta or {})
        channel_id = str(meta.get("id") or "").strip()
        channel_name = str(meta.get("name") or "").strip() or channel_id
        channel_icon = str(meta.get("icon") or "").strip()
        channel_url = str(meta.get("url") or "").strip()
        candidates: List[Dict[str, Any]] = []
        positions: Dict[tuple, int] = {}
        for message in messages:
            text = str(message.get("text") or "")
            if not cls._matches_media(text, titles, expected_year, expected_season):
                continue
            message_channel = str(message.get("channel") or "").strip() or channel_id
            message_url = str(message.get("url") or "")
            title = cls._extract_title(text)
            description = cls._description(text)
            size = cls._extract_size(text)
            tags = extract_resource_tags(text, cls._hashtags(text))
            for link in cls._message_links(message):
                password = cls.extract_password(link["url"], text)
                target = append_share_password(
                    link["resource_type"], link["url"], password
                )
                provider_data: Dict[str, Any] = {
                    "channel": message_channel,
                    "channel_name": channel_name,
                    "channel_icon": channel_icon,
                    "channel_url": channel_url,
                    "message_id": str(message.get("message_id") or ""),
                    "message_url": message_url,
                }
                candidate: Dict[str, Any] = {
                    "url": target,
                    "title": title,
                    "resource_type": link["resource_type"],
                    "source": "tg_channel",
                    "source_url": message_url,
                    "description": description,
                    "size": size,
                    "update_time": str(message.get("published") or ""),
                    "tags": list(tags),
                    "group_key": f"tg_channel:{message_channel}",
                    "group_title": channel_name,
                    "group_icon": channel_icon,
                    "group_subtitle": (
                        f"@{message_channel}" if message_channel else ""
                    ),
                    "provider_data": provider_data,
                }
                if password:
                    # 与 pansou 的顶层 ``password`` 以及既有的 ``share_password`` 同时对齐。
                    candidate["password"] = password
                    candidate["share_password"] = password
                    provider_data["password"] = password
                key = (link["resource_type"], target)
                if key in positions:
                    candidates[positions[key]] = candidate
                    continue
                positions[key] = len(candidates)
                candidates.append(candidate)
                if len(candidates) >= limit:
                    return candidates
        return candidates

    def _search_channel(
            self, channel: str, keywords: List[str], message_limit: int
    ) -> List[Dict[str, Any]]:
        """逐个关键词抓取单个频道，命中即返回，失败向上抛出。"""
        for keyword in keywords[:self._MAX_KEYWORDS_PER_CHANNEL]:
            messages = self._client.search_channel(channel, keyword, message_limit)
            if messages:
                return messages
        return []

    def search(self, query: SearchQuery) -> List[Dict[str, Any]]:
        """逐频道检索并按媒体做后置过滤，输出统一候选列表。"""
        mediainfo = query.mediainfo
        if not mediainfo:
            return []
        if not self._channels:
            logger.debug("[TG频道] 未配置任何频道，跳过检索")
            return []
        keywords = self._keywords(mediainfo, query.media_type, query.season)
        if not keywords:
            return []
        limit = max(1, int(query.result_limit or self._result_limit))
        titles = self._expected_titles(mediainfo)
        expected_year = extract_year(getattr(mediainfo, "year", None))
        expected_season = (
            normalize_season(query.season)
            if query.media_type == MediaType.TV else None
        )
        # 单频道原始消息上限：留出过滤余量，避免模糊命中挤满候选。
        message_limit = max(limit * 3, 20)
        deadline = time.monotonic() + self._timeout
        groups: List[List[Dict[str, Any]]] = []
        for index, channel in enumerate(self._channels):
            if time.monotonic() >= deadline:
                logger.debug(
                    f"[TG频道] 搜索超时（{self._timeout:.0f} 秒），"
                    f"已跳过剩余 {len(self._channels) - index} 个频道"
                )
                break
            if index:
                self._client.sleep_between_channels()
            try:
                messages = self._search_channel(channel, keywords, message_limit)
            except TelegramChannelError as error:
                logger.warning(f"[TG频道] 频道 {channel} 检索失败：{error}")
                continue
            except Exception as error:
                logger.warning(f"[TG频道] 频道 {channel} 检索异常：{error}")
                continue
            channel_meta = self._channel_meta(channel)
            candidates = self._build_candidates(
                messages, titles, expected_year, expected_season, limit,
                channel_meta=channel_meta,
            )
            if candidates:
                groups.append(candidates)
            logger.debug(
                f"[TG频道] 频道 {channel} 命中 {len(messages)} 条消息，"
                f"产出候选 {len(candidates)} 个"
            )

        candidates = normalize_magnets(
            self._merge_round_robin(groups, limit), "tg_channel"
        )
        logger.debug(
            f"[TG频道] 检索完成：频道 {len(self._channels)} 个，"
            f"有效候选 {len(candidates[:limit])} 个"
        )
        return candidates[:limit]

    def clear_cache(self) -> int:
        """清理频道预览页缓存。"""
        return int(self._client.clear_cache() or 0)
