"""PanBox 持久化封装。

历史与收藏这类小体量数据直接使用宿主插件的 ``save_data`` / ``get_data``，
不额外引入数据库；需要分页或聚合查询时再考虑宿主提供的插件自有数据库。
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

__all__ = ["PanBoxStore"]

#: 宿主 KV 中使用的数据键
HISTORY_KEY = "search_history"
FAVORITES_KEY = "favorites"


class PanBoxStore:
    """基于宿主插件 KV 的轻量存储。"""

    def __init__(self, plugin: Any, history_limit: int = 500) -> None:
        """初始化存储。

        :param plugin: 插件实例，需提供 ``get_data`` / ``save_data``
        :param history_limit: 历史记录最大保留条数
        """
        self._plugin = plugin
        self._history_limit = history_limit

    # ------------------------------------------------------------------ 历史
    def history(self) -> List[Dict[str, Any]]:
        """读取全部历史记录（按时间倒序）。"""
        return list(self._plugin.get_data(HISTORY_KEY) or [])

    def add_history(self, item: Dict[str, Any], source: str = "search") -> Dict[str, Any]:
        """追加一条历史记录。

        同一来源（``source`` 相同）下重复写入同一资源（频道 + 消息 ID 均存在且相同）时
        不新增条目，而是把原记录移到最前并更新时间，避免反复搜索堆积重复项；
        同一资源的搜索记录与转存记录会各自保留，便于区分「搜到过」与「转存过」。

        :param item: 资源条目字典
        :param source: 来源标记，``search``（搜索命中）或 ``transfer``（转存）
        :return: 已落盘的记录
        """
        records = self.history()
        key = self._item_key(item)
        record = {
            "id": uuid.uuid4().hex[:16],
            "created_at": int(time.time()),
            "source": source,
            "item": item,
        }
        if key:
            existing = next(
                (
                    entry
                    for entry in records
                    if entry.get("source") == source and self._item_key(entry.get("item") or {}) == key
                ),
                None,
            )
            if existing is not None:
                record["id"] = existing.get("id") or record["id"]
                records = [entry for entry in records if entry is not existing]
        records.insert(0, record)
        if len(records) > self._history_limit:
            records = records[: self._history_limit]
        self._plugin.save_data(HISTORY_KEY, records)
        return record

    def query_history(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: str = "",
        source: str = "",
    ) -> Dict[str, Any]:
        """分页查询历史记录。

        :param page: 页码，从 1 开始
        :param page_size: 每页条数
        :param keyword: 标题/正文关键词过滤
        :param source: 来源过滤（``search``/``transfer``）
        :return: 含 ``items`` / ``total`` / ``page`` / ``page_size`` 的字典
        """
        records = self.history()
        if source:
            records = [item for item in records if item.get("source") == source]
        if keyword:
            needle = keyword.strip().lower()
            records = [
                item
                for item in records
                if needle in f"{(item.get('item') or {}).get('title', '')} {(item.get('item') or {}).get('content', '')}".lower()
            ]
        total = len(records)
        page = max(page, 1)
        page_size = max(min(page_size, 200), 1)
        start = (page - 1) * page_size
        return {"items": records[start : start + page_size], "total": total, "page": page, "page_size": page_size}

    def clear_history(self) -> int:
        """清空历史记录。

        :return: 被清除的记录条数
        """
        count = len(self.history())
        self._plugin.save_data(HISTORY_KEY, [])
        return count

    def delete_history(self, record_id: str) -> bool:
        """删除一条历史记录。

        :param record_id: 记录 ID
        :return: 是否删除成功
        """
        records = self.history()
        remaining = [item for item in records if item.get("id") != record_id]
        if len(remaining) == len(records):
            return False
        self._plugin.save_data(HISTORY_KEY, remaining)
        return True

    # ------------------------------------------------------------------ 收藏
    def favorites(self) -> List[Dict[str, Any]]:
        """读取全部收藏（按时间倒序）。"""
        return list(self._plugin.get_data(FAVORITES_KEY) or [])

    def add_favorite(self, item: Dict[str, Any], note: str = "") -> Optional[Dict[str, Any]]:
        """新增一条收藏；同一消息重复收藏时返回 ``None``。

        :param item: 资源条目字典
        :param note: 备注
        :return: 新收藏记录，或 ``None`` 表示已存在
        """
        records = self.favorites()
        key = self._item_key(item)
        if any(self._item_key(item.get("item") or {}) == key for item in records):
            return None
        record = {
            "id": uuid.uuid4().hex[:16],
            "created_at": int(time.time()),
            "note": note,
            "item": item,
        }
        records.insert(0, record)
        self._plugin.save_data(FAVORITES_KEY, records)
        return record

    def remove_favorite(self, record_id: str) -> bool:
        """按记录 ID 删除收藏。

        :param record_id: 收藏记录 ID
        :return: 是否删除成功
        """
        records = self.favorites()
        remaining = [item for item in records if item.get("id") != record_id]
        if len(remaining) == len(records):
            return False
        self._plugin.save_data(FAVORITES_KEY, remaining)
        return True

    @staticmethod
    def _item_key(item: Dict[str, Any]) -> str:
        """生成资源条目的去重键。

        优先用「频道 + 消息 ID」；缺失时退化为消息链接或首个网盘链接；
        三者都没有时返回空字符串，表示该条目不参与去重。

        :param item: 资源条目字典
        :return: 去重键；无法确定时返回空字符串
        """
        channel_id = str(item.get("channel_id") or "")
        message_id = str(item.get("message_id") or "")
        if channel_id and message_id:
            return f"{channel_id}:{message_id}"
        url = str(item.get("url") or "")
        if url:
            return f"url:{url}"
        links = item.get("cloud_links") or []
        if links and isinstance(links[0], dict):
            link_url = str(links[0].get("url") or "")
            if link_url:
                return f"link:{link_url}"
        return ""
