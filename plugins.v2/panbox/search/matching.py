"""外部资源站点的媒体标题匹配工具。"""

import html
import re
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

import unicodedata

_TITLE_SEPARATOR_RE = re.compile(
    r"[\s\u3000\-_:：~～·•丨｜|¦.,，。!！?？'\"“”‘’()（）\[\]【】/\\]+"
)
_ROMAN_SEASON_PATTERN = re.compile(
    r"(?i)(?<=[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af])"
    r"[\s\u3000._-]*(VIII|VII|VI|IV|III|II|IX|X|V|I)"
    r"(?=$|[\s\u3000._:：~～-])"
)
_SEASON_PATTERNS = (
    re.compile(r"(?i)\bS(?:eason)?[ ._-]*0*(\d{1,3})\b"),
    re.compile(r"(?i)\bSeason[ ._-]*0*(\d{1,3})\b"),
    _ROMAN_SEASON_PATTERN,
    re.compile(r"第\s*([零〇一二两三四五六七八九十百\d]{1,6})\s*季"),
)
#: 合并季集写法（如 ``S02E03``）：``_SEASON_PATTERNS`` 第一项因 ``\b`` 边界无法命中，
#: 需要单独识别，否则「电影拒收带季号候选」的规则会静默失效。
_SEASON_EPISODE_PATTERN = re.compile(
    r"(?i)\bS(?:eason)?[ ._-]*0*(\d{1,3})[ ._-]*E\d{1,4}\b"
)
_ROMAN_NUMBERS = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
    "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
}

#: 统一媒体类型三态取值；禁止把判不出的结果默认成电影。
MEDIA_TYPE_MOVIE = "movie"
MEDIA_TYPE_TV = "tv"
MEDIA_TYPE_UNKNOWN = "unknown"

#: 话题标签中的媒体类型词（中日韩词按「包含」判定）；电影类词在前，命中即返回。
_MEDIA_TAG_WORD_TYPES = (
    ("电影", MEDIA_TYPE_MOVIE),
    ("影片", MEDIA_TYPE_MOVIE),
    ("剧场版", MEDIA_TYPE_MOVIE),
    ("院线", MEDIA_TYPE_MOVIE),
    ("电视剧", MEDIA_TYPE_TV),
    ("剧集", MEDIA_TYPE_TV),
    ("连续剧", MEDIA_TYPE_TV),
    ("国产剧", MEDIA_TYPE_TV),
    ("美剧", MEDIA_TYPE_TV),
    ("韩剧", MEDIA_TYPE_TV),
    ("日剧", MEDIA_TYPE_TV),
    ("泰剧", MEDIA_TYPE_TV),
    ("港剧", MEDIA_TYPE_TV),
    ("台剧", MEDIA_TYPE_TV),
    ("动漫", MEDIA_TYPE_TV),
    ("动画", MEDIA_TYPE_TV),
    ("番剧", MEDIA_TYPE_TV),
    ("综艺", MEDIA_TYPE_TV),
    ("短剧", MEDIA_TYPE_TV),
)
#: ASCII 标签词必须整词相等，避免「tvb」这类词误命中。
_MEDIA_ASCII_TAG_TYPES = {
    "movie": MEDIA_TYPE_MOVIE,
    "movies": MEDIA_TYPE_MOVIE,
    "film": MEDIA_TYPE_MOVIE,
    "tv": MEDIA_TYPE_TV,
    "series": MEDIA_TYPE_TV,
    "tvseries": MEDIA_TYPE_TV,
    "tv series": MEDIA_TYPE_TV,
    "tv-series": MEDIA_TYPE_TV,
}
#: 站点结构化类型字段的取值映射（中英文），用于「channel」来源判定。
_MEDIA_CHANNEL_TYPE_MAP = {
    "movie": MEDIA_TYPE_MOVIE,
    "movies": MEDIA_TYPE_MOVIE,
    "film": MEDIA_TYPE_MOVIE,
    "电影": MEDIA_TYPE_MOVIE,
    "影片": MEDIA_TYPE_MOVIE,
    "院线": MEDIA_TYPE_MOVIE,
    "tv": MEDIA_TYPE_TV,
    "series": MEDIA_TYPE_TV,
    "tv series": MEDIA_TYPE_TV,
    "电视剧": MEDIA_TYPE_TV,
    "剧集": MEDIA_TYPE_TV,
    "连续剧": MEDIA_TYPE_TV,
    "动漫": MEDIA_TYPE_TV,
    "动画": MEDIA_TYPE_TV,
    "番剧": MEDIA_TYPE_TV,
    "综艺": MEDIA_TYPE_TV,
    "短剧": MEDIA_TYPE_TV,
}
#: 季集/集数标记：命中即判定为剧集。
_MEDIA_SEASON_EPISODE_RE = re.compile(
    r"(?i)(?:"
    r"\bS\d{1,3}\s*E\d{1,4}\b"
    r"|\bS\d{1,3}\b"
    r"|\bSeason[ ._-]*\d{1,3}\b"
    r"|第\s*\d{1,3}\s*季"
    r"|\bE\d{1,4}\b"
    r"|\bEP\d{1,4}\b"
    r"|第\s*\d{1,4}\s*[集话期]"
    r"|更新至\s*\d{1,4}\s*[集话]"
    r"|全\s*\d{1,4}\s*[集话期]"
    r"|\b\d{1,4}\s*集\b"
    r")"
)
#: 剧集类关键词（季集标记之外仍可判定为剧集的词）。
_MEDIA_TV_KEYWORD_RE = re.compile(
    r"(?:连载|番剧|综艺|动漫|短剧|合集|完结|全集"
    r"|第\s*[0-9一二三四五六七八九十百]{1,4}\s*[季期])"
)
#: 电影类关键词：显式电影词，或「年份 + 发行规格」且全篇无季集标记的发布名。
_MEDIA_MOVIE_KEYWORD_RE = re.compile(
    r"(?:剧场版|电影|影片|院线|\bmovie\b"
    r"|(?:19|20)\d{2}[^\d\r\n]{0,12}"
    r"(?:4K|2160P|1080P|720P|REMUX|BLU-?RAY|WEB-?DL|WEB-?RIP|HDTV))",
    re.IGNORECASE,
)
#: 标题内联话题标签（如「某某 #电视剧」）。
_MEDIA_INLINE_HASHTAG_RE = re.compile(r"#([^\s#，,。;；|/]+)")

_TAG_LANGUAGE_INNER_RE = re.compile(
    r"内封(?:简繁英|简繁中英|简繁|简中|繁中|中文|英语|英文)", re.IGNORECASE
)
_TRASH_TAG_WORDS = frozenset({
    "盘酱酱", "panweb", "国产剧", "美剧", "日韩剧", "韩剧", "日剧", "泰剧",
    "动漫", "电影", "电视剧", "全集", "合集", "更新", "更新至", "最新",
    "分享", "免费", "链接", "未删减", "超清", "高清", "热播", "完结",
    "首发", "独家", "推荐", "资源",
})
_SEASON_EPISODE_TAG_RE = re.compile(
    r"^(?:s\d+|e\d+|ep\d+|第[0-9一二三四五六七八九十]+[季期集]|19\d\d|20\d\d)$",
    re.IGNORECASE
)
_RESOURCE_WORD_SPLIT_RE = re.compile(
    r"[\s\u3000:：·•.,，。!！?？（）【】\[\]/／\\＼_-]+|(?<=[a-zA-Z])(?=\d)|(?<=\d)(?=[a-zA-Z])"
)
_TAG_SPLIT_RE = re.compile(r"[\s,，;；|/]+")


def unique_texts(
        values: Iterable[object],
        normalizer: Optional[Callable[[str], str]] = None,
) -> List[str]:
    """清理、按原顺序去重一组文本，并可统一规范化。"""
    result = []
    seen = set()
    for value in values or []:
        text = str(value or "").strip()
        if normalizer:
            text = normalizer(text)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def media_identifier_queries(
        tmdb_id: object = None,
        douban_id: object = None,
        imdb_id: object = None,
) -> List[Tuple[str, str, str]]:
    """按统一优先级返回可用的媒体 ID 查询：TMDB、豆瓣、IMDb。"""
    result = []
    seen = set()
    for label, value, response_field in (
            ("TMDB", tmdb_id, "tmdb_id"),
            ("豆瓣", douban_id, "douban_id"),
            ("IMDb", imdb_id, "imdb_id"),
    ):
        query = str(value or "").strip()
        normalized = query.casefold()
        if not query or normalized in seen:
            continue
        seen.add(normalized)
        result.append((label, query, response_field))
    return result


def positive_ints(values: Iterable[object]) -> set:
    """返回有效正整数集合，忽略外部接口中的空值和非法值。"""
    result = set()
    for value in values or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            result.add(number)
    return result


def normalize_title(value: object) -> str:
    """生成忽略空白、标点和大小写的标题指纹。"""
    text = unicodedata.normalize("NFKC", html.unescape(str(value or ""))).casefold()
    return _TITLE_SEPARATOR_RE.sub("", text)


def _chinese_number(value: str) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3,
              "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100}
    total = 0
    current = 0
    for char in text:
        if char in digits:
            current = digits[char]
        elif char in units:
            total += (current or 1) * units[char]
            current = 0
        else:
            return None
    return total + current


def extract_season(value: object) -> Optional[int]:
    """从中英文发布标题提取季号（含 ``S02E03`` 这类合并季集写法）。"""
    text = unicodedata.normalize("NFKC", html.unescape(str(value or "")))
    merged = _SEASON_EPISODE_PATTERN.search(text)
    if merged:
        return int(merged.group(1))
    for index, pattern in enumerate(_SEASON_PATTERNS):
        matched = pattern.search(text)
        if not matched:
            continue
        if index < 2:
            return int(matched.group(1))
        if pattern is _ROMAN_SEASON_PATTERN:
            return _ROMAN_NUMBERS.get(matched.group(1).upper())
        return _chinese_number(matched.group(1))
    return None


def normalize_media_type(value: Any) -> str:
    """把 ``MediaType`` 枚举、中英文类型文本规范为 movie / tv / unknown。"""
    if value is None:
        return MEDIA_TYPE_UNKNOWN
    raw = getattr(value, "value", value)
    text = str(raw or "").strip().casefold()
    if text in {MEDIA_TYPE_MOVIE, MEDIA_TYPE_TV}:
        return text
    mapped = _MEDIA_CHANNEL_TYPE_MAP.get(text)
    if mapped:
        return mapped
    name = str(getattr(value, "name", "") or "").strip().casefold()
    if name in {MEDIA_TYPE_MOVIE, MEDIA_TYPE_TV}:
        return name
    return _MEDIA_CHANNEL_TYPE_MAP.get(name, MEDIA_TYPE_UNKNOWN)


def _tag_media_type(tag: object) -> str:
    """把单个话题标签映射为媒体类型；识别不出时返回空串。"""
    text = str(tag or "").strip().lstrip("#").strip().casefold()
    if not text:
        return ""
    if text in _MEDIA_ASCII_TAG_TYPES:
        return _MEDIA_ASCII_TAG_TYPES[text]
    for word, media_type in _MEDIA_TAG_WORD_TYPES:
        if word in text:
            return media_type
    return ""


def infer_media_type(
        title: object = "",
        *,
        tags: Optional[Iterable[object]] = None,
        channel_media_type: object = None,
        query_media_type: object = None,
) -> Tuple[str, str]:
    """按可靠性顺序推断资源候选的媒体类型，并返回判定来源。

    判定顺序（命中即返回）：

    1. 话题标签：``#电影`` / ``#电视剧`` 等原始标签，来源 ``hashtag``；
    2. 站点结构化类型：搜索结果 meta 中的类型列，来源 ``channel``；
    3. 季集/集数标记：``S02E03`` / ``第12集`` / ``更新至12集`` 等，来源 ``season``；
    4. 关键词：``全24集`` / ``完结`` / ``剧场版`` / ``合集`` 等，来源 ``keyword``；
    5. 搜索意图：仅在前四步均无线索时采用调用方查询类型，来源 ``query``；
    6. 仍无法判定时返回 ``unknown``。

    :param title: 资源发布标题
    :param tags: 原始话题标签（应传未被显示层过滤的原始标签）
    :param channel_media_type: 站点结构化类型（如 SeedHub 搜索 meta 的类型列）
    :param query_media_type: 调用方搜索意图类型，优先级最低
    :return: ``(media_type, source)``，``source`` 取值 hashtag / channel / season / keyword / query / unknown
    """
    raw_title = str(title or "")
    hashtags = list(tags or ()) + _MEDIA_INLINE_HASHTAG_RE.findall(raw_title)
    for tag in hashtags:
        media_type = _tag_media_type(tag)
        if media_type:
            return media_type, "hashtag"

    channel_type = normalize_media_type(channel_media_type)
    if channel_type != MEDIA_TYPE_UNKNOWN:
        return channel_type, "channel"

    if _MEDIA_SEASON_EPISODE_RE.search(raw_title):
        return MEDIA_TYPE_TV, "season"

    if _MEDIA_TV_KEYWORD_RE.search(raw_title):
        return MEDIA_TYPE_TV, "keyword"
    if _MEDIA_MOVIE_KEYWORD_RE.search(raw_title):
        return MEDIA_TYPE_MOVIE, "keyword"

    query_type = normalize_media_type(query_media_type)
    if query_type != MEDIA_TYPE_UNKNOWN:
        return query_type, "query"
    return MEDIA_TYPE_UNKNOWN, "unknown"


def infer_candidate_media_type(
        candidate: Any = None,
        *,
        channel_media_type: object = None,
        query_media_type: object = None,
) -> Dict[str, str]:
    """基于候选自身的标题与标签推断媒体类型，返回可直接合并进候选的字段。

    :param candidate: 候选字典（读取 ``title``、``tags``、``site_media_type``）
    :param channel_media_type: 站点结构化类型，缺省时回落到候选的 ``site_media_type``
    :param query_media_type: 调用方搜索意图类型，优先级最低
    :return: ``{"media_type": ..., "media_type_source": ...}``
    """
    data = candidate if isinstance(candidate, Mapping) else {}
    raw_tags = data.get("tags")
    tags = (
        list(raw_tags)
        if isinstance(raw_tags, (list, tuple, set, frozenset))
        else None
    )
    media_type, source = infer_media_type(
        data.get("title"),
        tags=tags,
        channel_media_type=(
            channel_media_type
            if channel_media_type
            else data.get("site_media_type")
        ),
        query_media_type=query_media_type,
    )
    return {"media_type": media_type, "media_type_source": source}


def normalize_season(value: Any, default: int = 1) -> int:
    """规范化季号：None 或空字符串回退默认季号；0 视为真实的特别篇 S00。"""
    try:
        return max(0, int(default if value is None or value == "" else value))
    except (TypeError, ValueError):
        return default


def title_without_season(value: object) -> str:
    """移除季号后生成标题指纹，用于剧集作品级匹配。"""
    text = unicodedata.normalize("NFKC", html.unescape(str(value or "")))
    for pattern in _SEASON_PATTERNS:
        text = pattern.sub(" ", text)
    return normalize_title(text)


def title_matches(candidate: object, expected_titles: Iterable[object]) -> bool:
    """要求候选标题与至少一个期望标题在作品级精确一致。"""
    candidate_normalized = title_without_season(candidate)
    if not candidate_normalized:
        return False
    return any(
        candidate_normalized == title_without_season(expected)
        for expected in expected_titles
        if str(expected or "").strip()
    )


def resource_title_matches(
        resource_title: object,
        expected_titles: Iterable[object],
        expected_year: Optional[object] = None,
        strict_year: bool = False,
) -> bool:
    """检查资源/发布标题中是否包含至少一个目标媒体标题（按词边界匹配）。"""
    raw_res = str(resource_title or "").strip()
    if not raw_res:
        return False
    norm_res = unicodedata.normalize("NFKC", html.unescape(raw_res)).casefold()
    comp_res = _RESOURCE_WORD_SPLIT_RE.sub(" ", norm_res).strip()
    if not comp_res:
        return False

    exp_year = str(expected_year or "").strip()
    if strict_year and exp_year:
        years = set(re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", norm_res))
        if years and exp_year not in years:
            return False

    def is_word_char(ch: str) -> bool:
        return bool(ch) and (ch.isalnum() or "\u3400" <= ch <= "\u9fff")

    for raw_title in expected_titles:
        if not raw_title:
            continue
        norm_title = unicodedata.normalize("NFKC", html.unescape(str(raw_title))).casefold()
        comp_title = _RESOURCE_WORD_SPLIT_RE.sub(" ", norm_title).strip()
        if not comp_title:
            continue
        start = 0
        while True:
            idx = comp_res.find(comp_title, start)
            if idx < 0:
                break
            prev_char = comp_res[idx - 1] if idx > 0 else ""
            next_idx = idx + len(comp_title)
            next_char = comp_res[next_idx] if next_idx < len(comp_res) else ""
            if not is_word_char(prev_char) and not is_word_char(next_char):
                return True
            start = idx + 1
    return False


def extract_year(value: object) -> str:
    matched = re.search(r"\b(19\d{2}|20\d{2})\b", str(value or ""))
    return matched.group(1) if matched else ""


def extract_mikan_rss_params(text: object) -> Optional[Tuple[str, Optional[str]]]:
    """从文本或 URL 中提取 Mikan RSS 的 bangumiId 和 subgroupid。"""
    raw = str(text or "").strip()
    if not raw:
        return None
    match = re.search(r"bangumiId=(\d+)", raw, re.I)
    if not match:
        return None
    bangumi_id = match.group(1)
    subgroup_match = re.search(r"subgroupid=(\d+)", raw, re.I)
    subgroup_id = subgroup_match.group(1) if subgroup_match else None
    return bangumi_id, subgroup_id


def is_anime_media(media: Any, candidate: Optional[Any] = None) -> bool:
    """精确判断媒体是否属于日本动漫番剧或动画电影（日漫）。

    后端统一定义与标记：支持 MediaInfo 对象、候选 Candidate 或字典结构。
    注意：日漫才是 Mikan 专职订阅与搜索范畴，普通国产动画或欧美动画不属于日漫，防止过度过滤与误展示。
    """
    targets = [t for t in (candidate, media) if t is not None]
    if not targets:
        return False

    def _get(obj: Any, key: str) -> Any:
        if isinstance(obj, dict):
            return obj.get(key)
        val = getattr(obj, key, None)
        if hasattr(val, "_mock_return_value"):
            return None
        return val

    # 1. 显式二次元平台 ID 标记（Bangumi, AniList, AniDB）
    for target in targets:
        for id_field in ("bangumi_id", "bgm_id", "anilist_id", "anidb_id"):
            val = _get(target, id_field)
            if val is not None:
                sval = str(val).strip()
                if sval and sval != "0":
                    return True

    # 2. 纯动漫渠道来源（Mikan, Bangumi, AniList）
    for target in targets:
        source = str(_get(target, "source") or "").lower()
        if source in ("mikan", "bangumi", "anilist"):
            return True

    # 3. 分类明确标明日番/日本动画
    for target in targets:
        category = str(_get(target, "category") or "")
        if "日番" in category or "日本动画" in category:
            return True

    # 4. 原产语言为日语 (ja) 且具备动画/二次元特征
    for target in targets:
        lang = str(_get(target, "original_language") or "").lower()
        if lang == "ja":
            genre_ids = _get(target, "genre_ids")
            if genre_ids:
                if isinstance(genre_ids, str):
                    genre_id_list = [g.strip() for g in genre_ids.split(",") if g.strip()]
                elif isinstance(genre_ids, (list, tuple, set)):
                    genre_id_list = [str(g).strip() for g in genre_ids if str(g).strip()]
                else:
                    genre_id_list = [str(genre_ids).strip()]
                if any(gid in {"16", "Animation"} for gid in genre_id_list):
                    return True
            genres = _get(target, "genres") or []
            if isinstance(genres, (list, tuple, set)):
                for g in genres:
                    name = str(g.get("name") if isinstance(g, dict) else g or "")
                    if any(kw in name for kw in ("动画", "Animation", "动漫", "Anime")):
                        return True
            category = str(_get(target, "category") or "")
            if any(kw in category for kw in ("动漫", "动画", "番剧", "Anime")):
                return True

    return False


def extract_resource_tags(
        title: str,
        existing_tags: Optional[Iterable[Any]] = None,
) -> List[str]:
    """从资源标题和已有标签中直接提取并规范化全部规格标签。"""
    specs: List[str] = []
    seen_upper = set()

    def add_spec(val: str) -> None:
        if not val:
            return
        upper_val = val.upper()
        if upper_val not in seen_upper:
            seen_upper.add(upper_val)
            specs.append(val)

    raw_title = str(title or "").strip()
    upper_title = raw_title.upper()

    # 分辨率
    if re.search(r"(?:\b|\[|\.)(?:4K|2160P|UHD)(?:\b|\]|\.)", upper_title, re.I):
        add_spec("4K")
    elif re.search(r"(?:\b|\[|\.)(?:1080P|1080I|FHD)(?:\b|\]|\.)", upper_title, re.I):
        add_spec("1080P")
    elif re.search(r"(?:\b|\[|\.)(?:720P)(?:\b|\]|\.)", upper_title, re.I):
        add_spec("720P")

    # 制作来源与媒介
    if re.search(r"\.ISO\b|\[\d+(?:\.\d+)?GB\]\.ISO", upper_title, re.I):
        add_spec("原盘ISO")
    elif "REMUX" in upper_title:
        add_spec("REMUX")
    elif re.search(r"(?:\b|\[|\.)(?:BDMV|BLURAY|BLU-RAY)(?:\b|\]|\.)", upper_title, re.I):
        add_spec("BluRay")
    elif re.search(r"WEB-?RIP", upper_title, re.I):
        add_spec("WebRip")
    elif re.search(r"WEB-?DL", upper_title, re.I):
        add_spec("WEB-DL")

    # 动态范围
    if re.search(r"DV|DOLBY\s*VISION|杜比视界", upper_title, re.I):
        add_spec("杜比视界")
    if "HDR10+" in upper_title:
        add_spec("HDR10+")
    elif re.search(r"(?:\b|\[|\.)HDR10?(?:\b|\]|\.)", upper_title, re.I):
        add_spec("HDR")

    # 帧率
    if re.search(r"60FPS|60帧", upper_title, re.I):
        add_spec("60帧")
    elif re.search(r"120FPS|120帧", upper_title, re.I):
        add_spec("120帧")

    # 字幕与配音
    # 先检测「无中字」否定标记，再检测正向中文字幕标记，避免「无中字」中的「中字」被误识别
    has_no_chs = bool(re.search(r"无(?:中文字幕|中字|字幕)|RAW|生肉", upper_title, re.I))
    lang_match = _TAG_LANGUAGE_INNER_RE.search(raw_title)
    if has_no_chs:
        add_spec("无中字")
    elif lang_match:
        add_spec(lang_match.group(0))
    elif re.search(r"(?<![无没])(?:中字|内嵌|简繁|双语|中英|\bCHS\b|\bCHT\b)", raw_title, re.I):
        add_spec("中字")
    if re.search(r"国语|国配|国粤", upper_title, re.I):
        add_spec("国语")
    if re.search(r"粤语|国粤", upper_title, re.I):
        add_spec("粤语")

    # 音效
    if re.search(r"ATMOS|全景声", upper_title, re.I):
        add_spec("杜比全景声")

    # 合并并清洗已有 tags
    if existing_tags:
        lower_title = raw_title.lower()
        for tag in existing_tags:
            if not tag:
                continue
            parts = _TAG_SPLIT_RE.split(str(tag).strip())
            for part in parts:
                clean = part.lstrip("#").strip()
                if not clean or len(clean) < 2 or len(clean) > 10:
                    continue
                clean_lower = clean.lower()
                if clean_lower in _TRASH_TAG_WORDS or any(w in clean_lower for w in _TRASH_TAG_WORDS):
                    continue
                if _SEASON_EPISODE_TAG_RE.match(clean):
                    continue
                if lower_title and clean_lower == lower_title:
                    continue
                add_spec(clean)
                if len(specs) >= 8:
                    break
            if len(specs) >= 8:
                break
    return specs


def media_aliases(mediainfo: Any) -> List[str]:
    """提取媒体元数据中附带的多语言译名与别名。"""
    if not mediainfo:
        return []
    names = getattr(mediainfo, "names", None)
    alias_list: List[str] = list(names) if isinstance(names, (list, tuple)) else []
    for field in ("en_title", "hk_title", "tw_title", "sg_title", "cn_name", "en_name"):
        val = getattr(mediainfo, field, None)
        if val and isinstance(val, str):
            alias_list.append(val)
    return unique_texts(alias_list)


def search_keyword_candidates(
        base_titles: Iterable[Any],
        aliases: Iterable[Any],
        limit: int = 6,
) -> List[str]:
    """构建优先包含中英文等多译名的高优先级搜索关键词序列。"""
    base = unique_texts(base_titles)
    alias_items = unique_texts(aliases)
    chinese_aliases = [t for t in alias_items if re.search(r"[\u4e00-\u9fff]", t)]
    ordered = unique_texts([*base[:1], *chinese_aliases, *base[1:], *alias_items])
    return ordered[:limit]
