"""媒体元数据适配层：复用 MoviePilot「探索」菜单的豆瓣 / TMDB 榜单与媒体搜索。

设计要点：
- 榜单参数为**实例实测可用值**（豆瓣 ``sort`` 取 R/T/S、``tags`` 取豆瓣高分；TMDB ``sort_by`` 取
  ``popularity.desc`` / ``vote_average.desc``），与宿主探索页同源同参；
- 宿主链（``app.chain.*``）在插件进程内可直接调用；这些符号在宿主的稳定入口里没有暴露，
  因此按需在函数内导入（同时让本模块的纯逻辑可在宿主外单测）；
- 海报 ``poster_path`` 由宿主返回**完整 URL**，前端直接使用。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = ["RANK_TABS", "MediaCatalog"]

#: 榜单分类页签，与宿主「探索」菜单的豆瓣 / TMDB 两个数据源对应
RANK_TABS: List[Dict[str, Any]] = [
    {
        "key": "douban_movie",
        "title": "豆瓣电影",
        "source": "douban",
        "media_type": "movie",
        "icon": "mdi-movie-open-outline",
        "sorts": [
            {"value": "S:豆瓣高分", "label": "豆瓣高分", "sort": "S", "tags": "豆瓣高分"},
            {"value": "T:", "label": "热门", "sort": "T", "tags": ""},
            {"value": "R:", "label": "最新", "sort": "R", "tags": ""},
        ],
    },
    {
        "key": "douban_tv",
        "title": "豆瓣剧集",
        "source": "douban",
        "media_type": "tv",
        "icon": "mdi-television-classic",
        "sorts": [
            {"value": "S:豆瓣高分", "label": "豆瓣高分", "sort": "S", "tags": "豆瓣高分"},
            {"value": "T:", "label": "热门", "sort": "T", "tags": ""},
            {"value": "R:", "label": "最新", "sort": "R", "tags": ""},
        ],
    },
    {
        "key": "tmdb_movie",
        "title": "TMDB电影",
        "source": "tmdb",
        "media_type": "movie",
        "icon": "mdi-filmstrip-box-multiple",
        "sorts": [
            {"value": "popularity.desc|0", "label": "流行", "sort_by": "popularity.desc", "vote_count": 0},
            {"value": "vote_average.desc|300", "label": "高分", "sort_by": "vote_average.desc", "vote_count": 300},
            {"value": "primary_release_date.desc|0", "label": "最新", "sort_by": "primary_release_date.desc", "vote_count": 0},
        ],
    },
    {
        "key": "tmdb_tv",
        "title": "TMDB剧集",
        "source": "tmdb",
        "media_type": "tv",
        "icon": "mdi-television-play",
        "sorts": [
            {"value": "popularity.desc|0", "label": "流行", "sort_by": "popularity.desc", "vote_count": 0},
            {"value": "vote_average.desc|300", "label": "高分", "sort_by": "vote_average.desc", "vote_count": 300},
            {"value": "first_air_date.desc|0", "label": "最新", "sort_by": "first_air_date.desc", "vote_count": 0},
        ],
    },
]


class MediaCatalog:
    """豆瓣 / TMDB 榜单与媒体搜索的适配器。"""

    # ------------------------------------------------------------------ 榜单
    async def rank_items(
        self,
        key: str,
        sort_value: str = "",
        page: int = 1,
        count: int = 24,
    ) -> List[Dict[str, Any]]:
        """按页签与排序取值返回榜单条目。

        :param key: 页签 key（见 :data:`RANK_TABS`）
        :param sort_value: 排序取值（``value`` 字段）；为空时使用该页签第一项
        :param page: 页码
        :param count: 每页条数
        :return: 序列化后的媒体条目列表
        """
        tab = next((item for item in RANK_TABS if item["key"] == key), None)
        if tab is None:
            return []
        sort_option = next(
            (item for item in tab["sorts"] if item["value"] == sort_value),
            tab["sorts"][0],
        )
        medias: Optional[List[Any]]
        if tab["source"] == "douban":
            medias = await self._douban_rank(
                tab["media_type"],
                sort=str(sort_option.get("sort") or "S"),
                tags=str(sort_option.get("tags") or ""),
                page=page,
                count=count,
            )
        else:
            medias = await self._tmdb_rank(
                tab["media_type"],
                sort_by=str(sort_option.get("sort_by") or "popularity.desc"),
                vote_count=int(sort_option.get("vote_count") or 0),
                page=page,
            )
        return [self._serialize(media, tab["media_type"]) for media in (medias or [])]

    @staticmethod
    async def _douban_rank(
        media_type: str,
        sort: str,
        tags: str,
        page: int,
        count: int,
    ) -> Optional[List[Any]]:
        """调用宿主豆瓣链获取榜单。

        :param media_type: ``movie`` / ``tv``
        :param sort: 排序码（R/T/S）
        :param tags: 标签（如「豆瓣高分」）
        :param page: 页码
        :param count: 每页条数
        :return: 宿主的 MediaInfo 列表
        """
        from app.chain.douban import DoubanChain
        from app.schemas.types import MediaType

        mtype = MediaType.TV if media_type == "tv" else MediaType.MOVIE
        return await DoubanChain().async_douban_discover(
            mtype=mtype, sort=sort, tags=tags, page=page, count=count
        )

    @staticmethod
    async def _tmdb_rank(
        media_type: str,
        sort_by: str,
        vote_count: int,
        page: int,
    ) -> Optional[List[Any]]:
        """调用宿主 TMDB 链获取榜单。

        :param media_type: ``movie`` / ``tv``
        :param sort_by: TMDB 排序字段
        :param vote_count: 最少投票数
        :param page: 页码
        :return: 宿主的 MediaInfo 列表
        """
        from app.chain.tmdb import TmdbChain
        from app.schemas.types import MediaType

        mtype = MediaType.TV if media_type == "tv" else MediaType.MOVIE
        return await TmdbChain().async_tmdb_discover(
            mtype=mtype,
            sort_by=sort_by,
            vote_count=vote_count,
            page=page,
        )

    # ------------------------------------------------------------------ 搜索
    async def search(self, keyword: str, media_type: str = "") -> List[Dict[str, Any]]:
        """按标题搜索媒体（多源，与宿主探索/订阅的搜索一致）。

        :param keyword: 标题关键词
        :param media_type: 为空表示不过滤类型
        :return: 序列化后的媒体条目列表
        """
        text = (keyword or "").strip()
        if not text:
            return []
        from app.chain.media import MediaChain
        from app.domain.metainfo import MetaInfo

        meta = MetaInfo(title=text)
        medias = await MediaChain().async_search_medias(meta)
        results: List[Dict[str, Any]] = []
        for media in medias or []:
            item = self._serialize(media, media_type or "")
            if media_type and item.get("media_type") != media_type:
                continue
            results.append(item)
        return results

    # ------------------------------------------------------------- 序列化
    @staticmethod
    def _serialize(media: Any, fallback_type: str) -> Dict[str, Any]:
        """把宿主 MediaInfo 压缩成前端需要的字段。

        :param media: 宿主 MediaInfo 对象
        :param fallback_type: 宿主未给类型时的兜底（``movie``/``tv``）
        :return: 前端字典
        """
        raw_type = str(getattr(media, "type", "") or "")
        media_type = "tv" if "剧" in raw_type or raw_type.lower() in {"tv", "电视剧"} else "movie"
        if not raw_type and fallback_type:
            media_type = fallback_type
        return {
            "title": str(getattr(media, "title", "") or ""),
            "year": str(getattr(media, "year", "") or ""),
            "media_type": media_type,
            "media_source": str(getattr(media, "media_source", "") or ""),
            "media_id": str(getattr(media, "media_id", "") or ""),
            "tmdb_id": getattr(media, "tmdb_id", None),
            "douban_id": getattr(media, "douban_id", None),
            "poster": str(getattr(media, "poster_path", "") or ""),
            "backdrop": str(getattr(media, "backdrop_path", "") or ""),
            "vote_average": float(getattr(media, "vote_average", 0) or 0),
            "overview": str(getattr(media, "overview", "") or ""),
            "season": getattr(media, "season", None),
        }
