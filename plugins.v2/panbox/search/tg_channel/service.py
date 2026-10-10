"""Telegram 频道搜索服务：正文后置过滤与网盘链接、提取码提取。"""

from __future__ import annotations

import re
import time
import unicodedata
from itertools import zip_longest
from typing import Any, Dict, Iterable, List, Optional, Tuple
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
    normalize_resource_type,
    resource_type_from_url,
)
from ...core.search import SearchQuery


class TelegramChannelSearchService:
    """把 TG 频道消息转换为 PanBox 统一搜索候选。"""

    #: 标题行前缀（如「名称：」）与提取码描述文本的识别正则。
    _TITLE_PREFIX_RE = re.compile(r"^(?:资源)?(?:名称|标题|片名|影片名)\s*[:：]\s*")
    #: 提取码标签之后紧跟的字母数字值；标签命中即可信，长度放宽到 16。
    _PASSWORD_RE = re.compile(
        r"(?:提取码|访问码|提取密码|分享密码|密码|口令|pwd|password|passcode|code)"
        r"\s*[:：=]?\s*([A-Za-z0-9]{4,16})",
        re.IGNORECASE,
    )
    #: 无标签回落时，整行去装饰后必须正好是 4~8 位纯字母数字。
    _PASSWORD_PURE_RE = re.compile(r"[A-Za-z0-9]{4,8}")
    #: 明显属于年份/集数/体积/分辨率/编码的词，不能当提取码。
    _PASSWORD_NOISE_RE = re.compile(
        r"(?i)^(?:"
        r"s\d{1,3}(?:\s*e\d{1,4})?"                 # S01 / S01E187
        r"|e\d{1,4}|ep\d{1,4}"                      # E187 / EP194
        r"|\d+(?:\.\d+)?(?:pb|tb|gb|mb|kb|g|m|t)"   # 体积 12.5GB / 2.5G / 1.2T
        r"|\d{1,4}[pik]"                            # 1080P / 4K
        r"|hdr\d*"                                  # HDR10
        r"|(?:x|h)26[45]|\d{1,2}bit"                # x264 / H265 / 10bit
        r"|ed2k|magnet|torrent|remux|bluray|webrip|webdl|hdtv"
        r"|\d+(?:\.\d+)?"                           # 纯数字/小数（年份、集数、评分）
        r")$"
    )
    #: 每个频道最多尝试的关键词数量，避免站内模糊搜索反复请求。
    _MAX_KEYWORDS_PER_CHANNEL = 2
    #: 发布名（完整资源名）长度上限：要容纳规格/音轨/字幕/体积等元数据。
    _MAX_TITLE_LENGTH = 200
    _MAX_DESCRIPTION_LENGTH = 600
    #: 「发布名头部块」最多向后收集的连续有效行数，避免把整段简介并入标题；
    #: 纯表情/装饰行不计入该数量（TG 帖子常把 emoji 与文字拆成独立行）。
    _MAX_HEADER_LINES = 4
    #: 头部块向后扫描的硬上限，防止装饰行过多时无限循环。
    _MAX_HEADER_SCAN = 10
    #: 正文话题标签（TG 频道常用 #剧情 #4K 之类标注），作为候选标签的来源之一。
    _HASHTAG_RE = re.compile(r"#([A-Za-z0-9\u3400-\u9fff_]{2,16})")
    #: 只识别「数字 + 紧邻单位」的体积描述：年份/集数/评分等纯数字一律不匹配。
    #: 单位支持 PB/TB/GB/MB/KB 与 G/M/T 简写；P/K 简写不使用，避免误吞 1080P、4K。
    _SIZE_TEXT_RE = re.compile(
        r"(?<![\d.])(\d+(?:\.\d+)?)\s*(PB|TB|GB|MB|KB|[GMT])(?![A-Za-z])",
        re.IGNORECASE,
    )
    #: 体积标签（大小/体积/容量…），用于在同一条消息的多个体积里挑选主资源。
    _SIZE_LABEL_RE = re.compile(
        r"(?:文件大小|大小|体积|容量|size)\s*[:：]?\s*$", re.IGNORECASE
    )
    #: 单字母单位到标准单位的映射（``parse_size_str`` 只认两字母单位）。
    _SIZE_UNIT_ALIASES = {"G": "GB", "M": "MB", "T": "TB"}
    #: 标题里的表情与格式控制符（emoji、变体选择符、LRM 等），清洗时统一剔除。
    _TITLE_DECORATION_RE = re.compile(
        r"[\U0001F000-\U0001FAFF\u2190-\u21FF\u2300-\u23FF\u2460-\u24FF"
        r"\u25A0-\u27BF\u2B00-\u2BFF\uFE0F\u200B-\u200F\u202A-\u202E\u2060]"
    )
    #: 标题主体之后的元数据段落（评分/类型/简介/大小…），标题在此截断。
    _TITLE_NOISE_RE = re.compile(
        r"\s*(?:评分|类型|地区|语言|主演|简介|大小|体积|容量|链接|标签"
        r"|描述|频道|投稿人|投稿|搜索|机场|公费服|收录版本|状态)\s*[:：]"
    )
    #: 紧跟空白、但省略冒号的元数据关键词（如「凡人修仙传 评分8.8」）；要求前置
    #: 空白，避免把《大小谎言》这类以关键词开头的片名误截断。
    _TITLE_TRAILING_NOISE_RE = re.compile(
        r"\s+(?:评分|类型|地区|语言|主演|简介|大小|体积|容量|链接|标签"
        r"|描述|频道|投稿人|投稿|搜索|机场|公费服|收录版本|状态)\s*[:：]?"
    )
    #: 标题主体首尾的装饰符与分隔符（全角竖线、书名号、括号等）。
    _TITLE_EDGE_RE = re.compile(
        r"^[\s\u3000#*·•・.,，。;；:：!！?？\-_~～|｜¦/／\\＼\[\]【】()（）"
        r"<>《》\"“”'‘’]+|[\s\u3000#*·•・.,，。;；:：!！?？\-_~～|｜¦/／\\＼"
        r"\[\]【】()（）<>《》\"“”'‘’]+$"
    )
    #: 发布名头部块的终止行（元数据/栏目标签、小节标题）：关键词后必须紧跟冒号
    #: 或行尾，避免把「类型转换」这类以关键词开头的行误判为标签。
    _HEADER_STOP_RE = re.compile(
        r"^(?:资源信息|资源详情|资源简介|内容简介|剧情简介|简介|描述|详情|评分|类型"
        r"|地区|语言|主演|导演|编剧|发行时间|上映时间|首播|片长|集数|单集片长|大小"
        r"|体积|容量|链接|标签|频道|群组|投稿人|投稿|搜索|机场|公费服|收录版本|状态"
        r"|最新评论|版权|来自|更新时间|发布时间|资源名称|磁力|网盘|提取码|密码|别名"
        r"|又名)(?=\s*[:：]|$)"
    )
    #: 纯栏目/分类行（「动漫」「更新」等，经装饰清洗后整行即一个分类词），
    #: 作为最后的标题回落时必须排除。
    _CATEGORY_ONLY_RE = re.compile(
        r"^(?:动漫|动画|电影|电视剧|剧集|美剧|韩剧|日剧|国漫|综艺|纪录片|体育|音乐"
        r"|短剧|合集|资源|分享|推荐|最新|更新|已更新|完结|连载)$"
    )
    #: 发布名首尾的装饰分隔符（**不含括号**）：与 ``_TITLE_EDGE_RE`` 的区别是
    #: 保留成对括号，避免把「(2026)」这类发布名末尾的括号当成装饰吃掉。
    _TITLE_EDGE_SAFE_RE = re.compile(
        r"^[\s\u3000#*·•・.,，。;；:：!！?？\-_~～|｜¦/／\\＼<>\"“”'‘’]+"
        r"|[\s\u3000#*·•・.,，。;；:：!！?？\-_~～|｜¦/／\\＼<>\"“”'‘’]+$"
    )
    #: 发布名开头的「独占栏目前缀」包裹块（【更新】【完结】（合集）等）。
    _TITLE_LEAD_PREFIX_RE = re.compile(
        r"^[【\[（(《「『]\s*(?:更新|已更新|完结|已完结|全集|合集|最新|推荐|首发"
        r"|独家|热播|资源|分享|超前|连载)\s*[】\]）)》」』]"
    )
    #: 季/集标记：标题主体缺少季集信息时，从相邻行补一个。
    _EPISODE_MARKER_RE = re.compile(
        r"(?i)(?:S\d{1,3}\s*E\d{1,4}|E\d{1,4}\b|第\s*\d{1,4}\s*[集话期]"
        r"|\d{1,4}\s*集|更新至\s*\d{1,4}\s*[集话])"
    )

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
        #: 频道在配置中的顺序：作为候选的 ``group_order`` 下发给前端，
        #: 保证结果里的分组顺序与「TG 频道列表」配置顺序一致。
        self._channel_order = {
            item["id"]: index for index, item in enumerate(self._channel_items)
        }
        self._result_limit = max(1, int(result_limit or 20))
        self._timeout = max(5.0, min(float(timeout or 60.0), 120.0))

    def _channel_meta(self, channel: str) -> Dict[str, Any]:
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
            "order": self._channel_order.get(channel, 0),
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
    def _password_from_url(cls, url: Any) -> str:
        """从分享链接的查询参数提取提取码。

        查询参数是结构化字段，因此允许 4~16 位；频道模板有时把集数等噪声直接
        拼进参数值（如 ``?password=e8d9第176集单集``），这里只取开头的连续
        字母数字段，其余一律丢弃。
        """
        try:
            query = parse_qs(urlparse(str(url or "")).query)
        except ValueError:
            return ""
        for key in (*SHARE_PASSWORD_QUERY_KEYS.values(), "code", "passcode"):
            values = query.get(key) or []
            if not values:
                continue
            matched = re.match(
                r"([A-Za-z0-9]{4,16})", str(values[0] or "").strip()
            )
            if matched:
                return matched.group(1)
        return ""

    @classmethod
    def _password_line_candidate(cls, raw_line: Any) -> str:
        """把一行正文判定为「独立成词」的提取码候选，不符合返回空串。

        「独立成词」收紧为：整行去掉表情/装饰后只剩这一个 4~8 位字母数字词
        （即该行只有一段 ASCII 字母数字），且不以 ``@``/``#`` 开头、至少含一个
        数字，并排除体积/分辨率/编码/季集等样式。

        实测依据：放宽到「正文任意独立词」时，默认 5 个频道里会被命中的 20 个
        词全是误报（``360GB``、``S01E187``、``EP194``、``@Lsp115``、``#ed2k``…），
        故按「宁可留空，不要错」收紧为整行判定。
        """
        line = cls._TITLE_DECORATION_RE.sub(" ", str(raw_line or "")).strip()
        if not line or line[0] in "@#":
            return ""
        # 整行必须只有这一小段 ASCII 字母数字（URL、频道名、规格行都排除）。
        runs = list(re.finditer(r"[A-Za-z0-9]+", line))
        if len(runs) != 1:
            return ""
        start, candidate = runs[0].start(), runs[0].group(0)
        if start and line[start - 1] in "@#":
            return ""
        if not cls._PASSWORD_PURE_RE.fullmatch(candidate):
            return ""
        if not any(char.isdigit() for char in candidate):
            return ""
        if cls._PASSWORD_NOISE_RE.match(candidate):
            return ""
        return candidate

    @classmethod
    def _password_from_text(cls, text: Any) -> str:
        """从正文提取提取码：先认标签，再认独占一行的字母数字词。

        标签命中即可信（``提取码：e8d9``、``密码 ab12``）；无标签时逐行判定，
        只接受整行就是 4~8 位字母数字且至少含一个数字的词（``ab12``），并排除
        体积/分辨率/编码/季集/频道名等样式。宁可返回空串，也不猜。
        """
        raw = str(text or "")
        matched = cls._PASSWORD_RE.search(raw)
        if matched:
            return matched.group(1).strip()
        for raw_line in raw.split("\n"):
            candidate = cls._password_line_candidate(raw_line)
            if candidate:
                return candidate
        return ""

    @classmethod
    def extract_password(cls, url: Any, text: Any) -> str:
        """从分享链接查询参数或正文描述中提取提取码。

        顺序：链接查询参数（结构化字段）→ 正文标签（提取码/访问码/密码/口令/
        pwd/password/code…）→ 正文中独立成词的 4~8 位字母数字。查询参数键表
        复用 ``search/types.py`` 的 ``SHARE_PASSWORD_QUERY_KEYS``，与
        ``append_share_password`` 写入端的口径保持一致；解析不到时返回空串。
        """
        return cls._password_from_url(url) or cls._password_from_text(text)

    @classmethod
    def _sync_share_password_param(
            cls, url: Any, resource_type: Any, password: Any
    ) -> str:
        """把分享链接里已有的提取码参数就地改写为清洗后的值。

        ``append_share_password`` 只在参数缺失时追加，若原链接带着被污染的
        ``?password=e8d9第176集单集`` 则不会覆盖；这里先改写，保证顶层
        ``password`` 与真正下发的分享链接一致。仅在能识别出提取码时改写。
        """
        target = str(url or "")
        secret = str(password or "").strip()
        if not target or not secret:
            return target
        key = SHARE_PASSWORD_QUERY_KEYS.get(normalize_resource_type(resource_type))
        if not key:
            return target
        pattern = re.compile(rf"([?&]{re.escape(key)}=)[^&#\s]*", re.IGNORECASE)
        if not pattern.search(target):
            return target
        return pattern.sub(lambda matched: f"{matched.group(1)}{secret}", target)

    @classmethod
    def _clean_title_text(cls, value: Any) -> str:
        """清洗发布名文本：去装饰符、剥独占栏目前缀、截断内联元数据、去首尾分隔符。

        与旧实现的区别：首尾只清理装饰分隔符与「（【更新】）」这类独占栏目前缀，
        **保留成对括号**，避免把 ``功夫女足 (2026)`` 末尾的括号当成装饰吃掉。
        """
        text = unicodedata.normalize("NFKC", str(value or ""))
        text = cls._TITLE_DECORATION_RE.sub(" ", text)
        text = cls._TITLE_NOISE_RE.split(text, 1)[0]
        text = cls._TITLE_TRAILING_NOISE_RE.split(text, 1)[0]
        text = re.sub(r"\s+", " ", text).strip()
        # 站内搜索结果页会把命中的关键词用高亮节点切开（如「（2026）」变成
        # 「（」「2026」「）」三行），拼接后需把括号内侧多余的空格收回。
        text = re.sub(r"([(\[【（《「『])\s+", r"\1", text)
        text = re.sub(r"\s+([)）\]】》」』,，。;；:：!！?？])", r"\1", text)
        text = cls._TITLE_EDGE_SAFE_RE.sub("", text)
        previous = None
        while previous != text:
            previous = text
            text = cls._TITLE_LEAD_PREFIX_RE.sub("", text, count=1).strip()
            text = cls._TITLE_EDGE_SAFE_RE.sub("", text)
        return text.strip()

    @staticmethod
    def _match_title_position(line: Any, titles: Optional[List[str]]) -> int:
        """在标题行中定位与目标媒体匹配的片名起始下标，未命中返回 -1。

        命中判定复用 ``matching.resource_title_matches``（词边界），按标题长度
        从长到短匹配，避免短别名盖过长别名；全角/大小写差异回落到 NFKC 归一化
        查找，仍找不到时退回行首（此时该行本身已被判定为片名行）。
        """
        raw = str(line or "")
        if not raw:
            return -1
        folded = raw.casefold()
        normalized = unicodedata.normalize("NFKC", raw).casefold()
        for title in sorted(unique_texts(titles or []), key=len, reverse=True):
            if not resource_title_matches(raw, [title]):
                continue
            needle = str(title).casefold()
            position = folded.find(needle)
            if position < 0:
                position = normalized.find(
                    unicodedata.normalize("NFKC", str(title)).casefold()
                )
            return max(position, 0)
        return -1

    @classmethod
    def _line_is_stop(cls, text: Any) -> bool:
        """判断装饰清洗后的一行是否为元数据标签行、栏目标签行或链接行。

        这类行是「发布名头部块」的边界：出现即停止收集后续行，避免把
        ``评分：`` / ``资源信息`` / ``• 体积：20GB`` 之类的元数据并进发布名。
        """
        stripped = str(text or "").strip()
        if not stripped:
            return False
        if stripped[0] in "#@•·▪◦‣*":
            return True
        lowered = stripped.casefold()
        if lowered.startswith(
                ("http://", "https://", "magnet:", "ed2k://", "t.me/", "www.")
        ):
            return True
        return bool(cls._HEADER_STOP_RE.match(stripped))

    @classmethod
    def _line_is_meaningful(cls, line: Any) -> bool:
        """判断一行能否作为标题回落项：排除纯栏目行、标签行与装饰行。"""
        text = unicodedata.normalize("NFKC", str(line or ""))
        text = cls._TITLE_DECORATION_RE.sub(" ", text)
        text = cls._TITLE_EDGE_RE.sub("", text).strip()
        if len(text) < 2 or cls._CATEGORY_ONLY_RE.match(text):
            return False
        return not cls._line_is_stop(text)

    @classmethod
    def _header_block(cls, lines: List[str], index: int, position: int) -> str:
        """从片名行起拼出「完整发布名」块。

        规则：以片名起始位置所在行的剩余内容为起点，向后收集连续行；
        纯表情/装饰行跳过但不终止（TG 帖子常把 emoji 与文字拆成独立行），
        遇到元数据标签行或链接行即停止。返回未做长度裁剪的拼接文本。
        """
        parts = [lines[index][max(position, 0):]]
        collected = 0
        for line in lines[index + 1:index + 1 + cls._MAX_HEADER_SCAN]:
            stripped = cls._TITLE_DECORATION_RE.sub(
                " ", unicodedata.normalize("NFKC", str(line or ""))
            ).strip()
            if not stripped:
                continue
            if cls._line_is_stop(stripped):
                break
            parts.append(line)
            collected += 1
            if collected >= cls._MAX_HEADER_LINES:
                break
        return " ".join(part for part in parts if str(part or "").strip())

    @classmethod
    def _append_episode_marker(
            cls, body: str, lines: List[str], index: int
    ) -> str:
        """发布名里没有季/集信息时，从紧随其后的若干行补一个集数标记。

        只扫描发布名头部块同一段（遇到元数据标签行或链接行即停），避免把
        分享链接里的 ``…e8`` 之类片段误当集数；集数若已包含在发布名里则原样
        返回，不重复追加。
        """
        if cls._EPISODE_MARKER_RE.search(body):
            return body[:cls._MAX_TITLE_LENGTH]
        for line in lines[index + 1:index + 6]:
            stripped = cls._TITLE_DECORATION_RE.sub(
                " ", unicodedata.normalize("NFKC", str(line or ""))
            ).strip()
            if not stripped:
                continue
            if cls._line_is_stop(stripped):
                break
            matched = cls._EPISODE_MARKER_RE.search(stripped)
            if not matched:
                continue
            marker = cls._TITLE_EDGE_RE.sub("", matched.group(0)).strip()
            if marker and marker not in body:
                return f"{body} {marker}"[:cls._MAX_TITLE_LENGTH]
        return body[:cls._MAX_TITLE_LENGTH]

    @classmethod
    def _extract_title(
            cls,
            text: Any,
            titles: Optional[List[str]] = None,
            expected_season: Optional[int] = None,
    ) -> str:
        """取正文中与目标媒体匹配的「完整发布名」，而不是只留片名。

        取值顺序：

        1. 逐行定位命中 ``titles``（含多语言别名）的片名行，取该行片名之后的
           内容并向后拼接「发布名头部块」（跳过纯装饰行，遇 ``评分：`` /
           ``资源信息`` / ``• 体积：`` 等标签行或链接行即止），保留规格、编码、
           音轨、字幕、体积等信息，例如
           ``功夫女足 (2026) 4K SDR + DV 杜比视界``；多行命中时优先季号与
           目标一致的；片名前的「动漫｜」「已更新：」等前缀被自然丢弃；
        2. 头部块为空时，回落到命中媒体名的最长行；
        3. 再回落到整段正文中匹配片名所在的那一行；
        4. 均未命中时取正文中最长的有效行——排除「动漫」「更新」这类纯栏目行，
           宁可给较长的原始片段，也不要把栏目名当作标题。

        发布名中若已带集数则保留，不重复追加。
        """
        raw = str(text or "")
        lines = [
            cls._TITLE_PREFIX_RE.sub("", line).strip()
            for line in raw.split("\n")
        ]
        lines = [line for line in lines if line]

        spans: List[Tuple[int, int]] = []
        for index, line in enumerate(lines):
            position = cls._match_title_position(line, titles)
            if position >= 0:
                spans.append((index, position))
        if spans:
            chosen = spans[0]
            if expected_season is not None:
                for span in spans:
                    if extract_season(lines[span[0]]) == expected_season:
                        chosen = span
                        break
            index, position = chosen
            body = cls._clean_title_text(cls._header_block(lines, index, position))
            if body:
                return cls._append_episode_marker(body, lines, index)

        if spans:
            # 回落一：命中媒体名的最长行（片名与规格被拆到多行时信息最全的那行）。
            index = max((span[0] for span in spans), key=lambda item: len(lines[item]))
            position = max(cls._match_title_position(lines[index], titles), 0)
            body = cls._clean_title_text(cls._header_block(lines, index, position))
            if body:
                return cls._append_episode_marker(body, lines, index)

        position = cls._match_title_position(raw, titles)
        if position >= 0:
            tail = raw[position:].split("\n", 1)[0]
            body = cls._clean_title_text(tail)
            if body:
                return body[:cls._MAX_TITLE_LENGTH]

        # 回落二：最长有效行（排除纯栏目行、标签行与装饰行）。
        valid_lines = [line for line in lines if cls._line_is_meaningful(line)]
        if valid_lines:
            body = cls._clean_title_text(max(valid_lines, key=len))
            if body:
                return body[:cls._MAX_TITLE_LENGTH]

        collapsed = re.sub(r"\s+", " ", raw).strip()
        return collapsed[:cls._MAX_TITLE_LENGTH]

    @staticmethod
    def _description(text: Any) -> str:
        """压缩正文空白并截断，作为候选描述下发前端。"""
        collapsed = re.sub(r"\s+", " ", str(text or "")).strip()
        return collapsed[:TelegramChannelSearchService._MAX_DESCRIPTION_LENGTH]

    @classmethod
    def _extract_size(cls, text: Any) -> int:
        """从正文中提取带单位的体积（复用 ``parse_size_str`` 做单位换算）。

        只有「数字 + 紧邻单位」才认定为体积（单位支持 PB/TB/GB/MB/KB 与 G/M/T
        简写、全角写法），年份、集数、评分、频道人数等无单位数字一律不匹配。
        一条消息里有多个体积时，优先取带「大小/体积/容量/size」标签的那些，
        再在其中取数值最大的一项（标签项最贴近主资源，最大值覆盖合集总容量），
        解析不到时返回 0，不猜。
        """
        normalized = unicodedata.normalize("NFKC", str(text or ""))
        matches: List[Tuple[int, bool]] = []
        for matched in cls._SIZE_TEXT_RE.finditer(normalized):
            unit = matched.group(2).upper()
            size = parse_size_str(
                f"{matched.group(1)} {cls._SIZE_UNIT_ALIASES.get(unit, unit)}"
            )
            if size <= 0:
                continue
            labeled = bool(cls._SIZE_LABEL_RE.search(normalized[:matched.start()]))
            matches.append((size, labeled))
        if not matches:
            return 0
        labeled_sizes = [item[0] for item in matches if item[1]]
        return max(labeled_sizes or [item[0] for item in matches])

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
            channel_meta: Optional[Dict[str, Any]] = None,
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
            title = cls._extract_title(text, titles, expected_season)
            description = cls._description(text)
            size = cls._extract_size(text)
            tags = extract_resource_tags(text, cls._hashtags(text))
            for link in cls._message_links(message):
                password = cls.extract_password(link["url"], text)
                target = append_share_password(
                    link["resource_type"],
                    cls._sync_share_password_param(
                        link["url"], link["resource_type"], password
                    ),
                    password,
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
                    # 分组顺序：频道在配置里的下标，前端据此排序（越小越靠前）。
                    "group_order": int(meta.get("order") or 0),
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
