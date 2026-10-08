"""网盘订阅的数据模型与存储。

订阅的本意：**盯住某个影视条目，定期在配置的 Telegram 频道里找网盘资源，命中后自动转存到网盘**。
「缺失」的判定基于本插件自己的转存记录（不依赖宿主媒体库），因此历史干净、可解释。

存储使用宿主插件 KV（``save_data`` / ``get_data``），键为 ``subscriptions``。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

__all__ = ["Subscription", "SubscriptionStore", "SUBSCRIPTIONS_KEY"]

#: 宿主 KV 中的订阅数据键
SUBSCRIPTIONS_KEY = "subscriptions"

#: 订阅类型取值
MEDIA_TYPES = ("movie", "tv")


@dataclass
class Subscription:
    """一条网盘订阅。"""

    id: str
    title: str
    media_type: str = "movie"
    year: str = ""
    poster: str = ""
    media_source: str = ""
    media_id: str = ""
    tmdb_id: Optional[int] = None
    douban_id: Optional[str] = None
    season: Optional[int] = None
    enabled: bool = True
    prefer_keywords: str = ""
    exclude_keywords: str = ""
    max_size_gb: float = 0.0
    min_size_gb: float = 0.0
    created_at: int = 0
    last_run_at: int = 0
    last_message: str = ""
    last_candidates: int = 0
    transferred: List[Dict[str, Any]] = field(default_factory=list)
    seen: List[str] = field(default_factory=list)

    @property
    def poster_url(self) -> str:
        """海报地址（宿主榜单返回的是完整 URL）。"""
        return self.poster or ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为前端可用的字典。"""
        data = asdict(self)
        data["poster_url"] = self.poster_url
        data["transferred_count"] = len(self.transferred)
        return data

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Subscription":
        """从字典还原订阅（自动补齐缺失字段与类型）。"""
        payload = dict(raw or {})
        media_type = str(payload.get("media_type") or "movie").lower()
        return cls(
            id=str(payload.get("id") or uuid.uuid4().hex[:16]),
            title=str(payload.get("title") or "").strip(),
            media_type=media_type if media_type in MEDIA_TYPES else "movie",
            year=str(payload.get("year") or ""),
            poster=str(payload.get("poster") or ""),
            media_source=str(payload.get("media_source") or ""),
            media_id=str(payload.get("media_id") or ""),
            tmdb_id=payload.get("tmdb_id") or None,
            douban_id=payload.get("douban_id") or None,
            season=payload.get("season") or None,
            enabled=bool(payload.get("enabled", True)),
            prefer_keywords=str(payload.get("prefer_keywords") or ""),
            exclude_keywords=str(payload.get("exclude_keywords") or ""),
            max_size_gb=float(payload.get("max_size_gb") or 0),
            min_size_gb=float(payload.get("min_size_gb") or 0),
            created_at=int(payload.get("created_at") or 0),
            last_run_at=int(payload.get("last_run_at") or 0),
            last_message=str(payload.get("last_message") or ""),
            last_candidates=int(payload.get("last_candidates") or 0),
            transferred=list(payload.get("transferred") or []),
            seen=[str(item) for item in (payload.get("seen") or [])],
        )


class SubscriptionStore:
    """基于宿主插件 KV 的订阅存储。"""

    def __init__(self, plugin: Any) -> None:
        """初始化存储。

        :param plugin: 插件实例，需提供 ``get_data`` / ``save_data``
        """
        self._plugin = plugin

    def all(self) -> List[Subscription]:
        """读取全部订阅。"""
        return [Subscription.from_dict(item) for item in (self._plugin.get_data(SUBSCRIPTIONS_KEY) or [])]

    def list_by_type(self, media_type: Optional[str] = None) -> List[Subscription]:
        """按类型读取订阅。

        :param media_type: ``movie`` / ``tv``；为空表示全部
        :return: 订阅列表（按创建时间倒序）
        """
        items = self.all()
        if media_type:
            items = [item for item in items if item.media_type == media_type]
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def get(self, subscription_id: str) -> Optional[Subscription]:
        """按 ID 读取订阅。"""
        return next((item for item in self.all() if item.id == subscription_id), None)

    def find_by_media(self, media_id: str, media_type: str) -> Optional[Subscription]:
        """按媒体 ID 与类型查找订阅（用于判重）。"""
        if not media_id:
            return None
        key = str(media_id)
        return next(
            (item for item in self.all() if item.media_type == media_type and str(item.media_id) == key),
            None,
        )

    def save_all(self, items: List[Subscription]) -> None:
        """整体写回订阅列表。"""
        self._plugin.save_data(SUBSCRIPTIONS_KEY, [item.to_dict() for item in items])

    def add(self, payload: Dict[str, Any]) -> Subscription:
        """新增订阅。

        :param payload: 订阅字段（含可选 ``overrides``）
        :return: 新建的订阅
        """
        data = dict(payload or {})
        overrides = data.pop("overrides", None) or {}
        subscription = Subscription.from_dict(data)
        subscription.id = uuid.uuid4().hex[:16]
        subscription.created_at = int(time.time())
        if isinstance(overrides, dict):
            for key in ("prefer_keywords", "exclude_keywords", "max_size_gb", "min_size_gb", "season"):
                if overrides.get(key) not in (None, ""):
                    setattr(subscription, key, overrides[key])
        items = self.all()
        items.append(subscription)
        self.save_all(items)
        return subscription

    def update(self, subscription_id: str, patch: Dict[str, Any]) -> Optional[Subscription]:
        """更新订阅的指定字段。

        :param subscription_id: 订阅 ID
        :param patch: 待更新字段
        :return: 更新后的订阅；未找到返回 ``None``
        """
        items = self.all()
        target = next((item for item in items if item.id == subscription_id), None)
        if target is None:
            return None
        allowed = {
            "title",
            "enabled",
            "season",
            "prefer_keywords",
            "exclude_keywords",
            "max_size_gb",
            "min_size_gb",
        }
        for key, value in (patch or {}).items():
            if key in allowed:
                setattr(target, key, value)
        self.save_all(items)
        return target

    def delete(self, subscription_id: str) -> bool:
        """删除订阅。

        :param subscription_id: 订阅 ID
        :return: 是否删除成功
        """
        items = self.all()
        remaining = [item for item in items if item.id != subscription_id]
        if len(remaining) == len(items):
            return False
        self.save_all(remaining)
        return True

    def record_run(
        self,
        subscription_id: str,
        candidates: int,
        message: str,
        transferred: Optional[List[Dict[str, Any]]] = None,
        seen: Optional[List[str]] = None,
    ) -> Optional[Subscription]:
        """记录一次同步结果。

        :param subscription_id: 订阅 ID
        :param candidates: 本次命中的候选数
        :param message: 结果说明
        :param transferred: 本次成功转存的记录
        :param seen: 本次见过的资源键（避免重复转存）
        :return: 更新后的订阅
        """
        items = self.all()
        target = next((item for item in items if item.id == subscription_id), None)
        if target is None:
            return None
        target.last_run_at = int(time.time())
        target.last_candidates = int(candidates or 0)
        target.last_message = str(message or "")
        if transferred:
            target.transferred.extend(transferred)
            # 只保留最近 200 条转存记录，避免 KV 无限膨胀
            target.transferred = target.transferred[-200:]
        if seen:
            merged = list(dict.fromkeys([*target.seen, *seen]))
            target.seen = merged[-2000:]
        self.save_all(items)
        return target
