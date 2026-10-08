"""网盘订阅的自动同步引擎：搜索频道 → 过滤选优 → 转存 → 记录。

与参考实现的关键差异（刻意简化）：
- 「缺失」判定只看本插件自己的转存记录，不扫描宿主媒体库；
- 候选体积通过 115 分享解析（``share/snap``）**真实获取**后再套用体积上下限，
  避免把整季大包误转；
- 仅转存配置允许的网盘类型（默认只有 115，与驱动能力一致）。
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional

from ..drive.p115 import P115Client, P115Error
from .matching import match_season, score_preference, split_words
from .subscription import Subscription, SubscriptionStore
from .tg import ChannelSearcher

__all__ = ["SubscriptionSyncer"]


class SubscriptionSyncer:
    """按订阅自动搜索并转存网盘资源。"""

    def __init__(
        self,
        config: Dict[str, Any],
        store: SubscriptionStore,
        on_transferred: Optional[Callable[[Dict[str, Any], Dict[str, Any]], None]] = None,
    ) -> None:
        """初始化同步器。

        :param config: 插件配置字典
        :param store: 订阅存储
        :param on_transferred: 转存成功回调，入参为 (订阅信息, 转存记录)
        """
        self._config = dict(config or {})
        self._store = store
        self._on_transferred = on_transferred

    # ------------------------------------------------------------------ 对外
    def run_all(self, subscription_id: str = "", media_type: str = "") -> Dict[str, Any]:
        """执行订阅同步。

        :param subscription_id: 只执行指定订阅；为空表示全部已启用的订阅
        :param media_type: 只执行指定类型的订阅（``movie``/``tv``）
        :return: 汇总结果
        """
        targets = self._store.list_by_type(media_type or None)
        if subscription_id:
            targets = [item for item in targets if item.id == subscription_id]
        targets = [item for item in targets if item.enabled]
        reports: List[Dict[str, Any]] = []
        for subscription in targets:
            reports.append(self.run_one(subscription))
        total = sum(int(item.get("transferred") or 0) for item in reports)
        return {
            "success": True,
            "message": f"已处理 {len(reports)} 个订阅，共转存 {total} 个资源",
            "reports": reports,
        }

    def run_one(self, subscription: Subscription) -> Dict[str, Any]:
        """执行单个订阅的同步。

        :param subscription: 订阅对象
        :return: 单个订阅的执行报告
        """
        started = time.time()
        errors: List[str] = []
        try:
            items = self._search(subscription, errors)
        except Exception as error:  # noqa: BLE001 - 单个订阅失败不影响其余
            message = f"搜索失败：{type(error).__name__}: {error}"
            self._store.record_run(subscription.id, 0, message)
            return {"subscription_id": subscription.id, "title": subscription.title, "candidates": 0, "transferred": 0, "message": message, "errors": errors}

        candidates = self._filter_candidates(subscription, items)
        if not candidates:
            message = "未发现新的候选资源"
            self._store.record_run(subscription.id, 0, message, seen=self._seen_keys(items))
            return {"subscription_id": subscription.id, "title": subscription.title, "candidates": 0, "transferred": 0, "message": message, "errors": errors}

        limit = int(self._config.get("auto_sync_max_per_run") or 3)
        transferred: List[Dict[str, Any]] = []
        skipped: List[str] = []
        for candidate in candidates[: max(limit, 1)]:
            outcome = self._try_transfer(subscription, candidate)
            if outcome.get("ok"):
                transferred.append(outcome["record"])
            else:
                skipped.append(str(outcome.get("message") or "转存失败"))

        if transferred:
            message = f"转存 {len(transferred)} 个资源（候选 {len(candidates)} 个）"
        elif skipped:
            message = f"候选 {len(candidates)} 个，均未转存：{skipped[0]}"
        else:
            message = "无可用候选"

        self._store.record_run(
            subscription.id,
            len(candidates),
            message,
            transferred=transferred,
            seen=self._seen_keys(items),
        )
        return {
            "subscription_id": subscription.id,
            "title": subscription.title,
            "candidates": len(candidates),
            "transferred": len(transferred),
            "message": message,
            "records": transferred,
            "errors": errors,
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    # ------------------------------------------------------------------ 内部
    def _search(self, subscription: Subscription, errors: List[str]) -> List[Dict[str, Any]]:
        """在配置的频道中搜索订阅主题。

        :param subscription: 订阅对象
        :param errors: 用于回传频道级错误的列表
        :return: 资源条目列表
        """
        searcher = ChannelSearcher(
            base_url=str(self._config.get("search_base_url") or "https://t.me/s"),
            timeout=int(self._config.get("search_timeout") or 20),
            proxy=str(self._config.get("search_proxy") or "") or None,
        )
        result = searcher.search(
            keyword=subscription.title,
            channels=self._config.get("channels"),
            limit=int(self._config.get("search_limit") or 30),
            filter_by_keyword=bool(self._config.get("search_filter")),
        )
        errors.extend(str(item.get("message")) for item in (result.get("errors") or []))
        return list(result.get("items") or [])

    def _filter_candidates(self, subscription: Subscription, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """把搜索命中过滤成可转存候选，并按偏好排序。

        :param subscription: 订阅对象
        :param items: 搜索命中
        :return: 候选列表（元素含 ``key`` / ``url`` / ``title`` / ``item``）
        """
        allowed_types = set(self._config.get("auto_sync_cloud_types") or ["p115"])
        exclude_words = split_words(subscription.exclude_keywords or self._config.get("auto_sync_exclude_keywords"))
        prefer_words = split_words(subscription.prefer_keywords or self._config.get("auto_sync_prefer_keywords"))
        seen = set(subscription.seen)
        done = {str(record.get("key")) for record in subscription.transferred}
        candidates: List[Dict[str, Any]] = []
        for item in items:
            haystack = f"{item.get('title', '')} {item.get('content', '')}"
            if any(word and word.lower() in haystack.lower() for word in exclude_words):
                continue
            if subscription.media_type == "tv" and subscription.season and not match_season(haystack, int(subscription.season)):
                continue
            for link in item.get("cloud_links") or []:
                if link.get("cloud_type") not in allowed_types:
                    continue
                key = f"{item.get('channel_id')}:{item.get('message_id')}:{link.get('url')}"
                if key in seen or key in done:
                    continue
                candidates.append(
                    {
                        "key": key,
                        "url": link.get("url"),
                        "title": item.get("title") or "",
                        "score": score_preference(haystack, prefer_words),
                        "pub_date": item.get("pub_date") or "",
                        "item": item,
                    }
                )
        candidates.sort(key=lambda entry: (entry["score"], entry["pub_date"]), reverse=True)
        return candidates

    def _try_transfer(self, subscription: Subscription, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """解析体积、套用体积上下限后转存。

        :param subscription: 订阅对象
        :param candidate: 候选（见 :meth:`_filter_candidates`）
        :return: 含 ``ok`` / ``record`` / ``message`` 的结果
        """
        cookie = str(self._config.get("p115_cookie") or "")
        if not cookie:
            return {"ok": False, "message": "未配置 115 Cookie"}
        client = P115Client(
            cookie=cookie,
            timeout=int(self._config.get("search_timeout") or 20),
            proxy=str(self._config.get("search_proxy") or "") or None,
        )
        size_gb = self._resolve_size(client, subscription, candidate)
        if size_gb is None:
            return {"ok": False, "message": "分享解析失败或提取码无效"}
        min_gb = float(subscription.min_size_gb or self._config.get("auto_sync_min_size_gb") or 0)
        max_gb = float(subscription.max_size_gb or self._config.get("auto_sync_max_size_gb") or 0)
        if min_gb and size_gb < min_gb:
            return {"ok": False, "message": f"体积 {size_gb:.2f}GB 小于下限 {min_gb:g}GB"}
        if max_gb and size_gb > max_gb:
            return {"ok": False, "message": f"体积 {size_gb:.2f}GB 超过上限 {max_gb:g}GB"}
        cid = str(self._config.get("p115_transfer_cid") or "0")
        try:
            result = client.transfer_url(candidate["url"], cid=cid)
        except P115Error as error:
            return {"ok": False, "message": f"转存失败：{error}"}
        if not result.get("ok"):
            return {"ok": False, "message": str(result.get("message") or "转存失败")}
        record = {
            "key": candidate["key"],
            "title": candidate.get("title") or "",
            "channel_id": (candidate.get("item") or {}).get("channel_id") or "",
            "message_id": (candidate.get("item") or {}).get("message_id") or "",
            "url": candidate["url"],
            "file_name": result.get("file_name") or "",
            "size_gb": round(size_gb, 3),
            "at": int(time.time()),
        }
        if self._on_transferred:
            try:
                self._on_transferred(subscription, record)
            except Exception:  # noqa: BLE001 - 回调失败不影响转存结果
                pass
        return {"ok": True, "record": record, "message": "转存成功"}

    @staticmethod
    def _resolve_size(client: P115Client, subscription: Subscription, candidate: Dict[str, Any]) -> Optional[float]:
        """解析候选分享的总体积（GB）。

        :param client: 115 客户端
        :param subscription: 订阅对象
        :param candidate: 候选
        :return: 体积（GB）；解析失败返回 ``None``
        """
        from .models import parse_share_url

        parsed = parse_share_url(str(candidate.get("url") or ""))
        if not parsed:
            return None
        try:
            files = client.share_info(parsed["share_code"], parsed["receive_code"])
        except P115Error:
            return None
        total_bytes = sum(int(item.get("file_size") or 0) for item in files)
        return total_bytes / 1024 / 1024 / 1024




    @staticmethod
    def _seen_keys(items: List[Dict[str, Any]]) -> List[str]:
        """汇总本次搜索命中的全部资源键（用于下次去重）。

        :param items: 搜索命中
        :return: 资源键列表
        """
        keys: List[str] = []
        for item in items:
            for link in item.get("cloud_links") or []:
                keys.append(f"{item.get('channel_id')}:{item.get('message_id')}:{link.get('url')}")
        return keys
