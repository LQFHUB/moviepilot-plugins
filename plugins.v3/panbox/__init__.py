"""PanBox：网盘助手。

聚合 Telegram 公开频道资源搜索与网盘转存能力：
- 搜索：自建抓取 ``t.me/s/<频道>`` 公开预览页，识别 115/夸克/阿里/天翼/123 等分享链接；
- 转存：首批支持 115 网盘（自研 HTTP 驱动，不引入第三方 SDK）；
- 数据：搜索历史与收藏使用宿主插件 KV（``save_data`` / ``get_data``）；
- 界面：Vue 联邦组件 + 主界面侧栏整页入口。

本插件为独立实现，仅参考同类插件的功能边界与接口事实，未复制其代码。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from app.sdk.plugin import _PluginBase

from .core.config import DEFAULT_CONFIG, build_config
from .core.media import RANK_TABS, MediaCatalog
from .core.models import parse_share_url
from .core.storage import PanBoxStore
from .core.subscription import SubscriptionStore
from .core.sync import SubscriptionSyncer
from .core.tg import ChannelSearcher
from .drive.p115 import P115Client, P115Error

__all__ = ["PanBox"]


class PanBox(_PluginBase):
    """网盘助手插件。"""

    plugin_name = "网盘助手"
    plugin_desc = "自建 Telegram 频道资源搜索，并把网盘分享一键转存到自己的网盘。"
    plugin_icon = "panbox.png"
    plugin_version = "0.2.2"
    plugin_order = 100

    def __init__(self) -> None:
        """初始化插件实例状态。"""
        super().__init__()
        self._config: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self._store = PanBoxStore(self, history_limit=int(DEFAULT_CONFIG["history_limit"]))
        self._subs = SubscriptionStore(self)
        self._catalog = MediaCatalog()

    # ------------------------------------------------------------ 生命周期
    def init_plugin(self, config: Optional[Dict[str, Any]] = None) -> None:
        """根据插件配置初始化运行状态。

        :param config: 宿主传入的插件配置
        """
        self.stop_service()
        self._config = build_config(config)
        self._store = PanBoxStore(self, history_limit=int(self._config.get("history_limit") or 500))
        self._subs = SubscriptionStore(self)

    def get_state(self) -> bool:
        """获取插件启用状态。"""
        return bool(self._config.get("enabled"))

    def stop_service(self) -> None:
        """停止插件后台服务（本插件无常驻服务，仅保留契约实现）。"""
        return None

    # ------------------------------------------------------------ 界面契约
    @staticmethod
    def get_render_mode() -> Tuple[str, Optional[str]]:
        """声明插件使用 Vue 联邦组件渲染，并给出构建产物目录。"""
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        """Vue 模式下返回默认配置，配置界面由远程 Config 组件渲染。"""
        return None, dict(self._config or DEFAULT_CONFIG)

    def get_page(self) -> Optional[List[dict]]:
        """Vue 模式下详情页由远程 Page 组件渲染。"""
        return None

    def get_sidebar_nav(self) -> List[Dict[str, Any]]:
        """声明主界面侧栏整页入口（仅启用的 Vue 插件会被聚合）。

        刻意复用宿主自带菜单的分组语义：
        - ``section="discovery"`` → 落在「探索」分组（网盘资源搜索，与探索页同参同源）；
        - ``section="subscribe"`` → 落在「订阅」分组（电影 / 剧集各一个入口，仿「订阅 → 电影/电视剧」）；
        - ``section="system"`` → 落在「系统」分组（本插件的管理页：历史 / 收藏 / 账号）。
        """
        if not self.get_state():
            return []
        return [
            {
                "nav_key": "resource",
                "title": "网盘资源",
                "icon": "mdi-cloud-search-outline",
                "section": "discovery",
                "permission": "discovery",
                "order": 30,
            },
            {
                "nav_key": "movie",
                "title": "网盘电影订阅",
                "icon": "mdi-movie-open-outline",
                "section": "subscribe",
                "permission": "subscribe",
                "order": 31,
            },
            {
                "nav_key": "tv",
                "title": "网盘剧集订阅",
                "icon": "mdi-television-classic",
                "section": "subscribe",
                "permission": "subscribe",
                "order": 32,
            },
            {
                "nav_key": "main",
                "title": "网盘助手",
                "icon": "mdi-cloud-cog-outline",
                "section": "system",
                "permission": "manage",
                "order": 10,
            },
        ]

    # ------------------------------------------------------------ 插件 API
    def get_api(self) -> List[Dict[str, Any]]:
        """注册插件 API（路径会被宿主加上 ``/plugin/{plugin_id}`` 前缀）。"""
        return [
            {
                "path": "/meta",
                "endpoint": self.api_meta,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取插件状态与配置摘要",
            },
            {
                "path": "/search",
                "endpoint": self.api_search,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "在配置的频道中搜索资源",
            },
            {
                "path": "/transfer",
                "endpoint": self.api_transfer,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "把资源转存到网盘",
            },
            {
                "path": "/drive/folders",
                "endpoint": self.api_drive_folders,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取网盘目标目录列表",
            },
            {
                "path": "/drive/preview",
                "endpoint": self.api_drive_preview,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "预览网盘分享内容（只读，不转存）",
            },
            {
                "path": "/drive/check",
                "endpoint": self.api_drive_check,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "校验网盘 Cookie 是否可用",
            },
            {
                "path": "/history",
                "endpoint": self.api_history,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "分页查询搜索历史",
            },
            {
                "path": "/history/delete",
                "endpoint": self.api_history_delete,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "删除单条历史记录",
            },
            {
                "path": "/history/clear",
                "endpoint": self.api_history_clear,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "清空历史记录",
            },
            {
                "path": "/favorites",
                "endpoint": self.api_favorites,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取收藏列表",
            },
            {
                "path": "/favorites/add",
                "endpoint": self.api_favorite_add,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "新增收藏",
            },
            {
                "path": "/favorites/delete",
                "endpoint": self.api_favorite_delete,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "删除收藏",
            },
            {
                "path": "/discover/tabs",
                "endpoint": self.api_discover_tabs,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取网盘资源的榜单页签（复用探索的豆瓣/TMDB）",
            },
            {
                "path": "/discover/rank",
                "endpoint": self.api_discover_rank,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "按页签获取榜单条目",
            },
            {
                "path": "/media/search",
                "endpoint": self.api_media_search,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "按标题搜索媒体（多源）",
            },
            {
                "path": "/media/resources",
                "endpoint": self.api_media_resources,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "按标题在频道中检索网盘资源（按频道分组）",
            },
            {
                "path": "/subscriptions",
                "endpoint": self.api_subscriptions,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "按类型获取网盘订阅列表",
            },
            {
                "path": "/subscriptions/add",
                "endpoint": self.api_subscription_add,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "新增网盘订阅",
            },
            {
                "path": "/subscriptions/update",
                "endpoint": self.api_subscription_update,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "更新网盘订阅",
            },
            {
                "path": "/subscriptions/delete",
                "endpoint": self.api_subscription_delete,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "删除网盘订阅",
            },
            {
                "path": "/subscriptions/run",
                "endpoint": self.api_subscription_run,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即执行网盘订阅同步",
            },
        ]

    def api_meta(self) -> Dict[str, Any]:
        """返回插件状态与配置摘要，供侧栏页面初始化。"""
        return {
            "success": True,
            "data": {
                "enabled": self.get_state(),
                "version": self.plugin_version,
                "channels": self._config.get("channels") or DEFAULT_CONFIG["channels"],
                "search_limit": self._config.get("search_limit"),
                "search_filter": self._config.get("search_filter"),
                "p115": {
                    "enabled": bool(self._config.get("p115_enabled")),
                    "configured": bool(self._config.get("p115_cookie")),
                    "transfer_cid": self._config.get("p115_transfer_cid") or "0",
                    "transfer_path": self._config.get("p115_transfer_path") or "",
                },
                "history_count": len(self._store.history()),
                "favorite_count": len(self._store.favorites()),
            },
        }

    def api_search(
        self,
        keyword: str = "",
        channel_id: str = "",
        limit: int = 0,
        record: bool = True,
    ) -> Dict[str, Any]:
        """在配置的频道中搜索资源。

        :param keyword: 搜索关键词
        :param channel_id: 只搜索指定频道（为空表示全部）
        :param limit: 单频道结果上限，``0`` 表示使用配置值
        :param record: 是否把命中结果写入历史
        :return: 搜索结果
        """
        if not self.get_state():
            return {"success": False, "message": "插件未启用"}
        channels = self._config.get("channels") or DEFAULT_CONFIG["channels"]
        if channel_id:
            channels = [item for item in channels if item.get("id") == channel_id]
            if not channels:
                return {"success": False, "message": f"频道 {channel_id} 不在配置中"}
        searcher = ChannelSearcher(
            base_url=str(self._config.get("search_base_url") or "https://t.me/s"),
            timeout=int(self._config.get("search_timeout") or 20),
        )
        started = time.time()
        result = searcher.search(
            keyword=keyword,
            channels=channels,
            limit=int(limit or self._config.get("search_limit") or 30),
            filter_by_keyword=bool(self._config.get("search_filter")),
        )
        if record and self._config.get("history_auto_record"):
            for item in result["items"]:
                self._store.add_history(item, source="search")
        result.update(
            {
                "success": True,
                "keyword": keyword,
                "count": len(result["items"]),
                "elapsed_ms": int((time.time() - started) * 1000),
            }
        )
        return result

    def api_transfer(self, payload: Optional[dict] = None) -> Dict[str, Any]:
        """把资源转存到网盘。

        请求体支持两种形式：``{"url": "...", "receive_code": "...", "cid": "0"}``
        或 ``{"items": [{"url": "..."}, ...]}``。

        :param payload: 请求体
        :return: 转存结果
        """
        if not self.get_state():
            return {"success": False, "message": "插件未启用"}
        data = dict(payload or {})
        items: List[Dict[str, Any]] = data.get("items") if isinstance(data.get("items"), list) else []
        if not items and data.get("url"):
            items = [data]
        if not items:
            return {"success": False, "message": "缺少待转存的链接"}
        if not self._config.get("p115_enabled"):
            return {"success": False, "message": "115 网盘未启用（请在插件配置中开启）"}
        cookie = str(self._config.get("p115_cookie") or "")
        if not cookie:
            return {"success": False, "message": "未配置 115 Cookie"}
        client = P115Client(
            cookie=cookie,
            timeout=int(self._config.get("search_timeout") or 20),
        )
        cid = str(data.get("cid") or self._config.get("p115_transfer_cid") or "0")
        results: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            try:
                outcome = self._transfer_one(client, url, cid)
            except P115Error as error:
                outcome = {"ok": False, "message": f"115 转存失败：{error}"}
            except Exception as error:  # noqa: BLE001 - 单条失败不影响其余条目
                outcome = {"ok": False, "message": f"{type(error).__name__}: {error}"}
            outcome["url"] = url
            results.append(outcome)
            if outcome.get("ok") and self._config.get("history_auto_record"):
                self._store.add_history(
                    {
                        "channel_id": str(item.get("channel_id") or ""),
                        "channel_name": str(item.get("channel_name") or ""),
                        "message_id": str(item.get("message_id") or ""),
                        "title": str(item.get("title") or outcome.get("file_name") or url),
                        "content": str(item.get("content") or ""),
                        "pub_date": str(item.get("pub_date") or ""),
                        "cloud_links": [
                            {"cloud_type": "p115", "url": url, "receive_code": str(item.get("receive_code") or "")}
                        ],
                    },
                    source="transfer",
                )
        succeeded = sum(1 for item in results if item.get("ok"))
        return {
            "success": succeeded > 0,
            "message": f"转存完成：成功 {succeeded} / 共 {len(results)}",
            "results": results,
        }

    def _transfer_one(self, client: P115Client, url: str, cid: str) -> Dict[str, Any]:
        """转存单条链接。

        :param client: 115 客户端
        :param url: 分享链接
        :param cid: 目标目录 ID
        :return: 单条结果
        """
        return client.transfer_url(url, cid=cid)

    def api_drive_folders(self, cid: str = "0") -> Dict[str, Any]:
        """获取网盘目标目录列表。

        :param cid: 父目录 ID
        :return: 目录列表
        """
        cookie = str(self._config.get("p115_cookie") or "")
        if not cookie:
            return {"success": False, "message": "未配置 115 Cookie"}
        client = P115Client(
            cookie=cookie,
            timeout=int(self._config.get("search_timeout") or 20),
        )
        try:
            folders = client.folders(cid)
        except P115Error as error:
            return {"success": False, "message": str(error)}
        return {"success": True, "data": folders}

    def api_drive_check(self, payload: Optional[dict] = None) -> Dict[str, Any]:
        """校验网盘 Cookie 是否可用。

        :param payload: 请求体，可含 ``cookie`` 以校验尚未保存的 Cookie
        :return: 校验结果
        """
        cookie = str((payload or {}).get("cookie") or self._config.get("p115_cookie") or "").strip()
        if not cookie:
            return {"success": False, "message": "未配置 115 Cookie"}
        client = P115Client(
            cookie=cookie,
            timeout=int(self._config.get("search_timeout") or 20),
        )
        result = client.check()
        return {"success": bool(result.get("ok")), "message": result.get("message")}

    def api_drive_preview(self, payload: Optional[dict] = None) -> Dict[str, Any]:
        """预览 115 分享链接里的文件清单（**只读**，不会转存）。

        用于转存前确认分享内容与体积，避免误转超大资源。

        :param payload: 请求体，含 ``url``（115 分享链接），可选 ``receive_code``
        :return: 分享码、提取码与文件清单
        """
        data = dict(payload or {})
        url = str(data.get("url") or "").strip()
        if not url:
            return {"success": False, "message": "缺少分享链接"}
        parsed = parse_share_url(url)
        if not parsed or parsed.get("cloud_type") != "p115":
            return {"success": False, "message": "不是可识别的 115 分享链接"}
        receive_code = str(data.get("receive_code") or parsed.get("receive_code") or "").strip()
        cookie = str(self._config.get("p115_cookie") or "")
        if not cookie:
            return {"success": False, "message": "未配置 115 Cookie"}
        client = P115Client(
            cookie=cookie,
            timeout=int(self._config.get("search_timeout") or 20),
        )
        try:
            files = client.share_info(parsed["share_code"], receive_code)
        except P115Error as error:
            return {"success": False, "message": f"115 分享解析失败：{error}"}
        total_size = sum(int(item.get("file_size") or 0) for item in files)
        return {
            "success": True,
            "message": f"分享内共 {len(files)} 个文件",
            "data": {
                "share_code": parsed["share_code"],
                "receive_code": receive_code,
                "total_size": total_size,
                "files": files,
            },
        }

    def api_history(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: str = "",
        source: str = "",
    ) -> Dict[str, Any]:
        """分页查询搜索历史。

        :param page: 页码
        :param page_size: 每页条数
        :param keyword: 关键词过滤
        :param source: 来源过滤
        :return: 分页结果
        """
        return {"success": True, "data": self._store.query_history(page, page_size, keyword, source)}

    def api_history_delete(self, payload: Optional[dict] = None) -> Dict[str, Any]:
        """删除单条历史记录。

        :param payload: 请求体，含 ``id``
        :return: 删除结果
        """
        record_id = str((payload or {}).get("id") or "")
        if not record_id:
            return {"success": False, "message": "缺少记录 ID"}
        return {"success": self._store.delete_history(record_id), "message": "已删除" if record_id else ""}

    def api_history_clear(self) -> Dict[str, Any]:
        """清空历史记录。"""
        return {"success": True, "message": f"已清空 {self._store.clear_history()} 条记录"}

    def api_favorites(self) -> Dict[str, Any]:
        """获取收藏列表。"""
        return {"success": True, "data": self._store.favorites()}

    def api_favorite_add(self, payload: Optional[dict] = None) -> Dict[str, Any]:
        """新增收藏。

        :param payload: 请求体，含 ``item`` 与可选 ``note``
        :return: 新增结果
        """
        data = dict(payload or {})
        item = data.get("item")
        if not isinstance(item, dict):
            return {"success": False, "message": "缺少资源条目"}
        record = self._store.add_favorite(item, note=str(data.get("note") or ""))
        if record is None:
            return {"success": False, "message": "该资源已在收藏中"}
        return {"success": True, "data": record}

    def api_favorite_delete(self, payload: Optional[dict] = None) -> Dict[str, Any]:
        """删除收藏。

        :param payload: 请求体，含 ``id``
        :return: 删除结果
        """
        record_id = str((payload or {}).get("id") or "")
        if not record_id:
            return {"success": False, "message": "缺少收藏 ID"}
        return {"success": self._store.remove_favorite(record_id), "message": "已删除"}

    # ------------------------------------------------- 榜单 / 媒体（网盘资源页）
    def api_discover_tabs(self) -> Dict[str, Any]:
        """返回「网盘资源」页的榜单页签定义（复用宿主探索的豆瓣 / TMDB 数据源）。"""
        return {"success": True, "data": RANK_TABS}

    async def api_discover_rank(
        self,
        key: str = "douban_movie",
        sort: str = "",
        page: int = 1,
        count: int = 24,
    ) -> Dict[str, Any]:
        """按页签获取榜单条目。

        :param key: 页签 key（见 ``RANK_TABS``）
        :param sort: 排序取值；为空用该页签默认
        :param page: 页码
        :param count: 每页条数
        :return: 榜单条目
        """
        if not self.get_state():
            return {"success": False, "message": "插件未启用"}
        try:
            items = await self._catalog.rank_items(key, sort_value=sort, page=page, count=count)
        except Exception as error:  # noqa: BLE001 - 宿主链异常需回传可读信息
            return {"success": False, "message": f"获取榜单失败：{type(error).__name__}: {error}"}
        return {"success": True, "data": items, "page": page, "count": len(items)}

    async def api_media_search(self, keyword: str = "", media_type: str = "") -> Dict[str, Any]:
        """按标题搜索媒体，用于把资源与标准影视条目对齐。

        :param keyword: 标题关键词
        :param media_type: 可选类型过滤（``movie``/``tv``）
        :return: 媒体条目
        """
        if not self.get_state():
            return {"success": False, "message": "插件未启用"}
        try:
            items = await self._catalog.search(keyword, media_type=media_type)
        except Exception as error:  # noqa: BLE001
            return {"success": False, "message": f"媒体搜索失败：{type(error).__name__}: {error}"}
        return {"success": True, "data": items, "count": len(items)}

    def api_media_resources(self, title: str = "", media_type: str = "", season: int = 0) -> Dict[str, Any]:
        """按标题在频道中检索网盘资源，并按频道分组返回（供详情对话框的频道页签）。

        :param title: 影视标题
        :param media_type: 可选类型提示（``movie``/``tv``）
        :param season: 剧集季号，``0`` 表示不过滤
        :return: 按频道分组的资源
        """
        if not self.get_state():
            return {"success": False, "message": "插件未启用"}
        text = (title or "").strip()
        if not text:
            return {"success": False, "message": "缺少标题"}
        searcher = ChannelSearcher(
            base_url=str(self._config.get("search_base_url") or "https://t.me/s"),
            timeout=int(self._config.get("search_timeout") or 20),
        )
        result = searcher.search(
            keyword=text,
            channels=self._config.get("channels") or DEFAULT_CONFIG["channels"],
            limit=int(self._config.get("search_limit") or 30),
            filter_by_keyword=bool(self._config.get("search_filter")),
        )
        channels: Dict[str, Dict[str, Any]] = {}
        for item in result.get("items") or []:
            channel_id = str(item.get("channel_id") or "")
            bucket = channels.setdefault(
                channel_id,
                {"channel_id": channel_id, "channel_name": item.get("channel_name") or channel_id, "items": []},
            )
            bucket["items"].append(item)
        grouped = sorted(channels.values(), key=lambda entry: len(entry["items"]), reverse=True)
        return {
            "success": True,
            "title": text,
            "media_type": media_type,
            "season": season,
            "channels": grouped,
            "total": sum(len(entry["items"]) for entry in grouped),
            "errors": result.get("errors") or [],
        }

    # ------------------------------------------------------------- 网盘订阅
    def api_subscriptions(self, media_type: str = "") -> Dict[str, Any]:
        """按类型获取订阅列表。

        :param media_type: ``movie`` / ``tv``；为空表示全部
        :return: 订阅列表
        """
        items = [item.to_dict() for item in self._subs.list_by_type(media_type or None)]
        return {"success": True, "data": items, "count": len(items)}

    def api_subscription_add(self, payload: Optional[dict] = None) -> Dict[str, Any]:
        """新增订阅（同一媒体重复订阅会被拒绝）。

        :param payload: 请求体，含 ``title`` / ``media_type`` / 海报等
        :return: 新增结果
        """
        data = dict(payload or {})
        title = str(data.get("title") or "").strip()
        if not title:
            return {"success": False, "message": "缺少标题"}
        media_type = str(data.get("media_type") or "movie").lower()
        if media_type not in ("movie", "tv"):
            return {"success": False, "message": "媒体类型必须是 movie 或 tv"}
        media_id = str(data.get("media_id") or "")
        if media_id and self._subs.find_by_media(media_id, media_type):
            return {"success": False, "message": "该条目已在订阅列表中"}
        subscription = self._subs.add({**data, "title": title, "media_type": media_type})
        return {"success": True, "message": "订阅已添加", "data": subscription.to_dict()}

    def api_subscription_update(self, payload: Optional[dict] = None) -> Dict[str, Any]:
        """更新订阅（启停、季号、过滤词、体积上下限）。

        :param payload: 请求体，含 ``id`` 与待更新字段
        :return: 更新结果
        """
        data = dict(payload or {})
        subscription_id = str(data.get("id") or "")
        if not subscription_id:
            return {"success": False, "message": "缺少订阅 ID"}
        patch = {key: value for key, value in data.items() if key != "id"}
        updated = self._subs.update(subscription_id, patch)
        if updated is None:
            return {"success": False, "message": "订阅不存在"}
        return {"success": True, "message": "已更新", "data": updated.to_dict()}

    def api_subscription_delete(self, payload: Optional[dict] = None) -> Dict[str, Any]:
        """删除订阅。

        :param payload: 请求体，含 ``id``
        :return: 删除结果
        """
        subscription_id = str((payload or {}).get("id") or "")
        if not subscription_id:
            return {"success": False, "message": "缺少订阅 ID"}
        return {"success": self._subs.delete(subscription_id), "message": "已删除"}

    def api_subscription_run(self, payload: Optional[dict] = None) -> Dict[str, Any]:
        """立即执行订阅同步（搜索 + 转存）。

        :param payload: 请求体，可含 ``id``（只跑一个）或 ``media_type``
        :return: 执行结果
        """
        if not self.get_state():
            return {"success": False, "message": "插件未启用"}
        data = dict(payload or {})
        return self.run_subscription_sync(
            subscription_id=str(data.get("id") or ""),
            media_type=str(data.get("media_type") or ""),
        )

    # --------------------------------------------------------- 定时同步服务
    def run_subscription_sync(self, subscription_id: str = "", media_type: str = "") -> Dict[str, Any]:
        """执行订阅同步（供定时服务与「立即执行」共用）。

        :param subscription_id: 只执行指定订阅
        :param media_type: 只执行指定类型
        :return: 执行结果
        """
        if not self._config.get("p115_enabled"):
            return {"success": False, "message": "115 网盘未启用，无法自动转存"}
        syncer = SubscriptionSyncer(self._config, self._subs, on_transferred=self._on_subscription_transferred)
        return syncer.run_all(subscription_id=subscription_id, media_type=media_type)

    def _on_subscription_transferred(self, subscription: Any, record: Dict[str, Any]) -> None:
        """把自动转存结果写入历史，便于审计。

        :param subscription: 订阅对象
        :param record: 转存记录
        """
        if not self._config.get("history_auto_record"):
            return
        self._store.add_history(
            {
                "channel_id": record.get("channel_id") or "",
                "channel_name": "",
                "message_id": record.get("message_id") or "",
                "title": record.get("title") or subscription.title,
                "content": f"订阅自动转存：{subscription.title}",
                "pub_date": "",
                "cloud_links": [{"cloud_type": "p115", "url": record.get("url") or "", "receive_code": ""}],
            },
            source="transfer",
        )

    def get_service(self) -> List[Dict[str, Any]]:
        """声明定时同步服务（仅在开启自动同步且 115 可用时注册）。"""
        if not self.get_state() or not self._config.get("auto_sync_enabled"):
            return []
        if not self._config.get("p115_enabled"):
            return []
        trigger: Any = "cron"
        trigger_kwargs: Dict[str, Any] = {"hour": "*/6", "minute": 10}
        cron_text = str(self._config.get("auto_sync_cron") or "").strip()
        if cron_text:
            try:
                from apscheduler.triggers.cron import CronTrigger

                trigger = CronTrigger.from_crontab(cron_text)
                trigger_kwargs = {}
            except Exception:  # noqa: BLE001 - 表达式非法时退回每 6 小时
                trigger = "cron"
                trigger_kwargs = {"hour": "*/6", "minute": 10}
        return [
            {
                "id": "auto_sync",
                "name": "网盘订阅自动同步",
                "trigger": trigger,
                "func": self.run_subscription_sync,
                "kwargs": trigger_kwargs,
                "func_kwargs": {},
            }
        ]
